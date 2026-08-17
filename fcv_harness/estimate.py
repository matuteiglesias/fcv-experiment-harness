import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from .core import build_exposure_state

def _formula(outcome, covariates, fixed_effects):
    rhs = ["C(exposure_state, Treatment(reference='never'))"]
    rhs += list(covariates)
    rhs += [f"C({c})" for c in fixed_effects]
    return f"{outcome} ~ " + " + ".join(rhs)

def spatial_did(df, outcome, covariates=(), fixed_effects=(), cluster_col="cluster_id"):
    sample = df[df["exposure_state"].isin(["completed", "planned", "never"])].copy()
    if sample["exposure_state"].nunique() < 3:
        return {"ok": False, "reason": "Need completed, planned, and never observations."}

    model = smf.ols(_formula(outcome, covariates, fixed_effects), data=sample)
    if cluster_col in sample.columns and sample[cluster_col].nunique() > 1:
        fit = model.fit(cov_type="cluster", cov_kwds={"groups": sample[cluster_col]})
    else:
        fit = model.fit(cov_type="HC1")

    c_name = "C(exposure_state, Treatment(reference='never'))[T.completed]"
    p_name = "C(exposure_state, Treatment(reference='never'))[T.planned]"
    if c_name not in fit.params or p_name not in fit.params:
        return {"ok": False, "reason": "Model could not identify completed/planned coefficients."}

    diff = float(fit.params[c_name] - fit.params[p_name])
    cov = fit.cov_params()
    var = float(cov.loc[c_name, c_name] + cov.loc[p_name, p_name] - 2 * cov.loc[c_name, p_name])
    se = np.sqrt(max(var, 0.0))
    z = diff / se if se > 0 else np.nan

    return {
        "ok": True,
        "effect_completed_minus_planned": diff,
        "se": float(se),
        "z": float(z) if np.isfinite(z) else np.nan,
        "n": int(len(sample)),
        "n_completed": int((sample.exposure_state == "completed").sum()),
        "n_planned": int((sample.exposure_state == "planned").sum()),
        "n_never": int((sample.exposure_state == "never").sum()),
    }

def bandwidth_sweep(observations, projects, links, spec):
    rows = []
    for radius in spec.bandwidth_grid_km:
        df = build_exposure_state(observations, projects, links, radius)
        est = spatial_did(df, spec.outcome, spec.covariates, spec.fixed_effects)
        rows.append({"radius_km": radius, **est})
    return pd.DataFrame(rows)
