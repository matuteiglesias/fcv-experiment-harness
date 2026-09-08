import unittest
from dataclasses import replace

import pandas as pd

from fcv_harness.current_e2_reference import run_current_e2_from_bundles
from fcv_harness.current_e2_scope import scope_current_geography
from tests_current_e2_reference import CurrentE2ReferenceTests


class CurrentE2CountryScopeTests(unittest.TestCase):
    @staticmethod
    def scoped_inputs():
        geography, geography_dataset, treatment, outcome = (
            CurrentE2ReferenceTests.synthetic_inputs()
        )
        treatment = replace(
            treatment,
            measurement=treatment.measurement.model_copy(
                update={
                    "parameters": {
                        **treatment.measurement.parameters,
                        "covered_country_iso3": ["AAA"],
                    }
                }
            ),
        )
        outcome = replace(
            outcome,
            measurement=outcome.measurement.model_copy(
                update={
                    "parameters": {
                        **outcome.measurement.parameters,
                        "certified_country_iso3": ["AAA", "BBB"],
                    }
                }
            ),
        )
        extra = geography.iloc[:2].copy()
        extra["source_geo_id"] = ["BBB.1_1", "BBB.2_1"]
        extra["geo_uid"] = ["geo-bbb-1", "geo-bbb-2"]
        extra["country_iso3"] = "BBB"
        geography = pd.concat([geography, extra], ignore_index=True)
        return geography, geography_dataset, treatment, outcome

    def test_scope_uses_treatment_contract_not_full_governed_geography(self):
        geography, geography_dataset, treatment, outcome = self.scoped_inputs()
        spec = CurrentE2ReferenceTests.spec()

        scoped, evidence = scope_current_geography(geography, treatment, outcome, spec)

        self.assertEqual(set(scoped["country_iso3"]), {"AAA"})
        self.assertEqual(len(scoped), 40)
        self.assertEqual(evidence["analysis_country_iso3"], ["AAA"])
        self.assertEqual(evidence["excluded_governed_country_iso3"], ["BBB"])
        self.assertEqual(evidence["governed_geography_rows"], 42)
        self.assertEqual(evidence["analysis_geography_rows"], 40)

        result = run_current_e2_from_bundles(
            scoped,
            geography_dataset,
            treatment,
            outcome,
            spec,
            run_observability=False,
        )
        primary = result["calibration"]["cells"]["record_present"]
        self.assertTrue(primary["estimate"]["ok"])
        self.assertEqual(primary["estimate"]["n"], 120)

    def test_scope_fails_when_certified_outcome_misses_treatment_country(self):
        geography, _, treatment, outcome = self.scoped_inputs()
        outcome = replace(
            outcome,
            measurement=outcome.measurement.model_copy(
                update={
                    "parameters": {
                        **outcome.measurement.parameters,
                        "certified_country_iso3": ["BBB"],
                    }
                }
            ),
        )
        with self.assertRaisesRegex(ValueError, "does not cover all treatment countries"):
            scope_current_geography(
                geography,
                treatment,
                outcome,
                CurrentE2ReferenceTests.spec(),
            )

    def test_scope_fails_without_explicit_treatment_country_contract(self):
        geography, _, treatment, outcome = self.scoped_inputs()
        treatment = replace(
            treatment,
            measurement=treatment.measurement.model_copy(
                update={
                    "parameters": {
                        key: value
                        for key, value in treatment.measurement.parameters.items()
                        if key != "covered_country_iso3"
                    }
                }
            ),
        )
        with self.assertRaisesRegex(ValueError, "covered_country_iso3"):
            scope_current_geography(
                geography,
                treatment,
                outcome,
                CurrentE2ReferenceTests.spec(),
            )


if __name__ == "__main__":
    unittest.main()
