"""E2/E3 synthetic tests including an independent Poisson full-FE comparison."""
import unittest

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from fcv_harness.w5_china_wb_vac import build_frame, fit_primary_lpm
from fcv_harness.w5_e2_e3 import (
    _separation_prune, attach_earlier_vac, build_first_recorded_riskset,
    fit_balanced_fe_ols, fit_fe_ppml, run_e3,
)
from tests_w5_china_wb_vac import _fixture


def _poisson_fixture() -> pd.DataFrame:
    rng = np.random.default_rng(20261115)
    data = []
    for ci in range(9):
        country = f"C{ci}"
        for a in range(6):
            for t in range(5):
                state=(a+t+ci)%4
                c=int(state==1)
                w=int(state==2)
                b=int(state==3)
                signal=0.23*c - 0.15*w +0.19*b + (a-2.5)*0.05 + 0.15*np.sin(t+ci)
                mean=4.5*np.exp(signal)
                y=int(rng.poisson(mean))
                data.append({
                    "geo_uid":f"{country}.{a}",
                    "country_iso3":country,
                    "period_id":f"{2001+2*t}-{2002+2*t}",
                    "country_period":f"{country}|{2001+2*t}",
                    "china_only":c,"wb_only":w,"both":b,
                    "neither_recorded":int(state==0),
                    "vac_events_next":y,"vac_fatalities_next":2*y,
                    "any_vac_next":int(y>0),
                })
    return pd.DataFrame(data)


class E2E3Tests(unittest.TestCase):
    def test_generalized_fe_ols_matches_e1_binary(self):
        inv,ac,spec=_fixture()
        f=build_frame(inv,ac,spec)
        a=fit_balanced_fe_ols(f,"any_vac_next")
        b=fit_primary_lpm(f)
        np.testing.assert_allclose(a["contrasts"][-1]["estimate"],
                                   b["results"][-1]["estimate_probability"],atol=1e-12)
        np.testing.assert_allclose(a["contrasts"][-1]["se_country_cluster"],
                                   b["results"][-1]["se_probability"],atol=1e-12)

    def test_ppml_full_fe_matches_statsmodels(self):
        frame=_poisson_fixture()
        ours=fit_fe_ppml(frame,"vac_events_next")
        self.assertEqual(ours["status"],"CONVERGED")
        self.assertEqual(ours["nobs"],len(frame))
        # Explicit full-rank FE design: area dummies, then country-period dummies
        # with one omitted baseline period for EACH country. No global intercept.
        area=pd.get_dummies(frame.geo_uid,dtype=float)
        ct=pd.get_dummies(frame.country_period,dtype=float)
        omitted=[col for col in ct.columns if col.endswith("|2001")]
        ct=ct.drop(columns=omitted)
        design=np.column_stack([frame[["china_only","wb_only","both"]].to_numpy(),
                                area.to_numpy(),ct.to_numpy()])
        self.assertEqual(np.linalg.matrix_rank(design),design.shape[1])
        standard=sm.GLM(frame.vac_events_next.to_numpy(),design,
                        family=sm.families.Poisson()).fit(
                            maxiter=100,tol=1e-11,cov_type="cluster",
                            cov_kwds={"groups":frame.country_iso3},
                        )
        self.assertTrue(standard.converged)
        np.testing.assert_allclose(
            list(ours["coefficients"].values()),standard.params[:3],
            atol=3e-6,rtol=0,
        )
        self.assertLess(ours["fixed_effect_score_max_abs"],1e-5)
        diff=np.array([1.,-1.,0.])
        independent_cluster_se=float(np.sqrt(
            diff@standard.cov_params()[:3,:3]@diff
        ))
        self.assertAlmostEqual(
            ours["contrasts"][-1]["se_country_cluster"], independent_cluster_se,
            places=7,
        )

    def test_separation_prune_removes_zero_groups(self):
        f=_poisson_fixture()
        f.loc[f.geo_uid.eq("C0.0"),"vac_events_next"]=0
        cleaned, info =_separation_prune(f,"vac_events_next")
        self.assertFalse(cleaned.geo_uid.eq("C0.0").any())
        self.assertEqual(info["pruned_rows"],5)
        self.assertEqual(info["retained_nobs"],len(f)-5)

    def test_earlier_vac_requires_complete_prior_source(self):
        inv,ac,spec=_fixture()
        f=build_frame(inv,ac,spec)
        with self.assertRaisesRegex(ValueError,"incomplete certified pre2"):
            attach_earlier_vac(f,ac,"Violence against civilians")
        # Add an explicit certified 1997-98 prior row for every synthetic area.
        earlier=ac.loc[ac.period_id.eq("1999-2000")].copy()
        earlier["period_id"]="1997-1998"
        ac=pd.concat([ac,earlier],ignore_index=True)
        v=attach_earlier_vac(f,ac,"Violence against civilians")
        self.assertEqual(len(v),len(f))
        self.assertTrue(v["vac_events_pre2"].notna().all())
        risk,report=build_first_recorded_riskset(v)
        self.assertTrue(report["future_financing_not_used_as_eligibility_condition"])
        self.assertTrue((risk[["china_only","wb_only","both","neither_recorded"]].sum(axis=1)==1).all())
        result,_=run_e3(f,ac,spec)
        self.assertEqual(result["status"],"COMPLETED_DESCRIPTIVE_DIAGNOSTICS")


if __name__=="__main__":
    unittest.main()
