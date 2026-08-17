from dataclasses import dataclass, field
from typing import List, Optional
import json
import numpy as np
import pandas as pd

@dataclass
class ExperimentSpec:
    experiment_id: str
    outcome: str
    pre_outcome: Optional[str] = None
    radius_km: float = 30.0
    bandwidth_grid_km: List[float] = field(default_factory=lambda: [10, 20, 30, 40, 50])
    covariates: List[str] = field(default_factory=list)
    fixed_effects: List[str] = field(default_factory=list)
    min_completed: int = 30
    min_planned: int = 30
    max_ambiguous_share: float = 0.10
    max_abs_pre_smd: float = 0.25
    placebo_max_abs_effect: float = 0.20
    plausible_effect: float = -0.20
    power_target: float = 0.80
    bootstrap_draws: int = 200
    seed: int = 20260817

    @classmethod
    def from_json(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))

def _num(x):
    return None if pd.isna(x) else float(x)

def classify_project_state(
    obs_year,
    agreement_year,
    actual_start_year=np.nan,
    scheduled_start_year=np.nan,
    actual_end_year=np.nan,
    scheduled_end_year=np.nan,
    source_status=None,
    last_source_year=2014,
):
    # Blair-inspired timing resolution, generalized to preserve ambiguity.
    if pd.isna(obs_year) or pd.isna(agreement_year):
        return "ambiguous"

    obs = float(obs_year)
    agr = float(agreement_year)

    if obs < agr:
        return "planned"

    start = _num(actual_start_year)
    if start is None:
        s = _num(scheduled_start_year)
        start = None if s is None else s + 1.0

    end = _num(actual_end_year)
    if end is None:
        e = _num(scheduled_end_year)
        end = None if e is None else e + 1.0

    if end is not None and obs >= end:
        return "completed"
    if start is not None and obs >= start:
        return "active"

    if str(source_status).lower() == "completed" and obs >= last_source_year:
        return "completed"

    return "ambiguous"

def add_project_state(links, projects, observations):
    merged = (
        links.merge(projects, on="project_id", how="left", validate="many_to_many")
             .merge(observations[["obs_id", "obs_year"]], on="obs_id", how="left", validate="many_to_one")
    )

    merged["project_state_at_obs"] = merged.apply(
        lambda r: classify_project_state(
            r["obs_year"],
            r.get("agreement_year"),
            r.get("actual_start_year"),
            r.get("scheduled_start_year"),
            r.get("actual_end_year"),
            r.get("scheduled_end_year"),
            r.get("source_status"),
        ),
        axis=1,
    )
    return merged

def build_exposure_state(observations, projects, exposure_links, radius_km):
    linked = add_project_state(exposure_links, projects, observations)
    near = linked.loc[linked["distance_km"] <= radius_km].copy()

    state_order = {"never": 0, "ambiguous": 1, "planned": 2, "active": 3, "completed": 4}

    if near.empty:
        out = observations.copy()
        out["exposure_state"] = "never"
        for s in ["planned", "active", "completed", "ambiguous"]:
            out[f"n_{s}_projects"] = 0
        out["n_near_projects"] = 0
        return out

    counts = (
        near.groupby(["obs_id", "project_state_at_obs"]).size()
            .unstack(fill_value=0)
            .reindex(columns=["planned", "active", "completed", "ambiguous"], fill_value=0)
    )
    counts.columns = [f"n_{c}_projects" for c in counts.columns]
    counts["n_near_projects"] = counts.sum(axis=1)

    def choose_state(g):
        states = g["project_state_at_obs"].tolist()
        return max(states, key=lambda s: state_order.get(s, -1))

    state = near.groupby("obs_id").apply(choose_state).rename("exposure_state")

    out = observations.merge(state, left_on="obs_id", right_index=True, how="left")
    out = out.merge(counts, left_on="obs_id", right_index=True, how="left")
    out["exposure_state"] = out["exposure_state"].fillna("never")

    cols = ["n_planned_projects", "n_active_projects", "n_completed_projects",
            "n_ambiguous_projects", "n_near_projects"]
    for c in cols:
        out[c] = out[c].fillna(0).astype(int)
    return out
