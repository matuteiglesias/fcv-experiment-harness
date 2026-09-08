from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


@dataclass(frozen=True)
class ObservabilityDesign:
    """Prepared stochastic substrate for paired known-truth simulations."""

    sample: pd.DataFrame
    fitted: np.ndarray
    residual: np.ndarray
    treatment: np.ndarray
    outcome_sd: float
    treated: int
    control: int
    treatment_share: float
    unit_col: str
    period_col: str
    country_col: str
    outcome_col: str
    pre_outcome_col: str
    treatment_col: str
    nuisance_formula: str


@dataclass(frozen=True)
class ObservabilityWorld:
    """One paired stochastic realization with one declared injected truth."""

    frame: pd.DataFrame
    repetition_id: int
    derived_seed: int
    effect_size_sd: float
    truth_effect: float
    outcome_sd: float
    stochastic_outcome_col: str

    @property
    def world_id(self) -> str:
        return f"rep-{self.repetition_id:06d}__delta-{self.effect_size_sd:+.12g}"


def derive_repetition_seed(root_seed: int, repetition_id: int) -> int:
    """Derive one deterministic Monte Carlo seed from an explicit root seed."""
    root = int(root_seed)
    repetition = int(repetition_id)
    if root < 0:
        raise ValueError("root_seed must be non-negative")
    if repetition < 0:
        raise ValueError("repetition_id must be non-negative")
    state = np.random.SeedSequence([root, repetition]).generate_state(1, dtype=np.uint64)
    return int(state[0])


def wild_cluster_signs(unit_values: pd.Series, derived_seed: int) -> np.ndarray:
    """Return one Rademacher draw per cluster, aligned to supplied rows."""
    units = pd.Series(unit_values, copy=False).astype(str)
    unique_units = sorted(units.unique().tolist())
    rng = np.random.default_rng(int(derived_seed))
    draws = rng.choice(np.array([-1.0, 1.0]), size=len(unique_units))
    sign_by_unit = pd.Series(draws, index=unique_units, dtype=float)
    return units.map(sign_by_unit).to_numpy(dtype=float)


def inject_known_effect(
    outcome: Sequence[float] | np.ndarray | pd.Series,
    treatment: Sequence[float] | np.ndarray | pd.Series,
    *,
    delta_sd: float,
    outcome_sd: float,
) -> np.ndarray:
    """Apply Y* = Y + delta_sd * outcome_sd * T without mutating inputs."""
    delta = float(delta_sd)
    sd = float(outcome_sd)
    if not np.isfinite(delta):
        raise ValueError("delta_sd must be finite")
    if not np.isfinite(sd) or sd <= 0:
        raise ValueError("outcome_sd must be finite and positive")
    y = np.asarray(outcome, dtype=float)
    t = np.asarray(treatment, dtype=float)
    if y.shape != t.shape:
        raise ValueError("outcome and treatment must have the same shape")
    return y + delta * sd * t


def _analysis_sample(
    frame: pd.DataFrame,
    *,
    unit_col: str,
    period_col: str,
    country_col: str,
    outcome_col: str,
    pre_outcome_col: str,
    treatment_col: str,
    eligible_col: str,
) -> pd.DataFrame:
    required = {
        unit_col,
        period_col,
        country_col,
        outcome_col,
        pre_outcome_col,
        treatment_col,
        eligible_col,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"Observability frame missing required columns: {missing}")

    sample = frame.loc[frame[eligible_col].astype(bool)].copy()
    sample = sample.dropna(
        subset=[
            unit_col,
            period_col,
            country_col,
            outcome_col,
            pre_outcome_col,
            treatment_col,
        ]
    ).copy()
    if sample.empty:
        raise ValueError("Observability model-complete sample is empty")
    if sample[treatment_col].nunique() < 2:
        raise ValueError("Observability sample requires treatment variation")
    if sample[unit_col].nunique() < 2:
        raise ValueError("Observability sample requires at least two clusters")
    return sample


def prepare_observability_design(
    frame: pd.DataFrame,
    *,
    unit_col: str,
    period_col: str,
    country_col: str,
    outcome_col: str = "outcome_value",
    pre_outcome_col: str = "outcome_pre",
    treatment_col: str = "treatment",
    eligible_col: str = "eligible",
    nuisance_formula: str | None = None,
) -> ObservabilityDesign:
    """Prepare the shared empirical stochastic substrate once.

    Both detector observability and inference calibration consume this exact
    object so stochastic worlds can be paired across effect sizes and methods.
    """
    sample = _analysis_sample(
        frame,
        unit_col=unit_col,
        period_col=period_col,
        country_col=country_col,
        outcome_col=outcome_col,
        pre_outcome_col=pre_outcome_col,
        treatment_col=treatment_col,
        eligible_col=eligible_col,
    )
    formula = nuisance_formula or (
        f"{outcome_col} ~ {pre_outcome_col} + C({period_col}) + C({country_col})"
    )
    nuisance = smf.ols(formula, data=sample).fit()
    fitted = np.asarray(nuisance.fittedvalues, dtype=float)
    residual = np.asarray(nuisance.resid, dtype=float)
    observed_outcome = pd.to_numeric(sample[outcome_col], errors="coerce").to_numpy(dtype=float)
    outcome_sd = float(np.std(observed_outcome, ddof=1))
    if not np.isfinite(outcome_sd) or outcome_sd <= 0:
        raise ValueError("Outcome has no finite positive variance for observability injection")

    treatment = pd.to_numeric(sample[treatment_col], errors="coerce").to_numpy(dtype=float)
    treated = int(np.count_nonzero(treatment == 1.0))
    control = int(np.count_nonzero(treatment == 0.0))
    support = treated + control
    treatment_share = treated / support if support else np.nan

    return ObservabilityDesign(
        sample=sample,
        fitted=fitted,
        residual=residual,
        treatment=treatment,
        outcome_sd=outcome_sd,
        treated=treated,
        control=control,
        treatment_share=float(treatment_share),
        unit_col=unit_col,
        period_col=period_col,
        country_col=country_col,
        outcome_col=outcome_col,
        pre_outcome_col=pre_outcome_col,
        treatment_col=treatment_col,
        nuisance_formula=formula,
    )


def generate_observability_world(
    design: ObservabilityDesign,
    *,
    repetition_id: int,
    root_seed: int,
    delta_sd: float,
    synthetic_outcome_col: str = "_observability_outcome",
) -> ObservabilityWorld:
    """Generate one deterministic paired world from the prepared design.

    For a fixed repetition/root seed, every effect-size cell shares the same
    cluster-level residual sign realization. Only the known injected truth
    differs. The empirical input frame is never mutated.
    """
    derived_seed = derive_repetition_seed(root_seed, repetition_id)
    signs = wild_cluster_signs(design.sample[design.unit_col], derived_seed)
    stochastic_outcome = design.fitted + design.residual * signs
    synthetic = inject_known_effect(
        stochastic_outcome,
        design.treatment,
        delta_sd=delta_sd,
        outcome_sd=design.outcome_sd,
    )
    frame = design.sample.copy()
    frame[synthetic_outcome_col] = synthetic
    return ObservabilityWorld(
        frame=frame,
        repetition_id=int(repetition_id),
        derived_seed=int(derived_seed),
        effect_size_sd=float(delta_sd),
        truth_effect=float(delta_sd * design.outcome_sd),
        outcome_sd=float(design.outcome_sd),
        stochastic_outcome_col=synthetic_outcome_col,
    )


__all__ = [
    "ObservabilityDesign",
    "ObservabilityWorld",
    "derive_repetition_seed",
    "wild_cluster_signs",
    "inject_known_effect",
    "prepare_observability_design",
    "generate_observability_world",
]
