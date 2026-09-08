from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


REFERENCE_IDENTITY_SCHEMA = "current_e2_reference_identity.v1"
REFERENCE_LOCK_SCHEMA = "current_e2_reference_lock.v1"


@dataclass(frozen=True)
class CurrentE2ReferenceLock:
    lock_id: str
    reference_id: str
    config_sha256: str
    primary_cell_id: str
    geography_sha256: str
    treatment_sha256: str
    outcome_sha256: str
    expected_analysis_country_count: int

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2ReferenceLock":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != REFERENCE_LOCK_SCHEMA:
            raise ValueError("unsupported current E2 reference lock schema")
        expected = payload["expected_inputs"]
        return cls(
            lock_id=str(payload["lock_id"]),
            reference_id=str(payload["reference_id"]),
            config_sha256=str(payload["config_sha256"]),
            primary_cell_id=str(payload["primary_cell_id"]),
            geography_sha256=str(expected["geography_sha256"]),
            treatment_sha256=str(expected["treatment_sha256"]),
            outcome_sha256=str(expected["outcome_sha256"]),
            expected_analysis_country_count=int(payload["expected_analysis_country_count"]),
        )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_frame_sha256(
    frame: pd.DataFrame,
    *,
    unit_col: str,
    period_col: str,
) -> str:
    ordered = frame.sort_values([unit_col, period_col]).reset_index(drop=True)
    return hashlib.sha256(
        ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_versions() -> dict[str, str | None]:
    packages = (
        "fcv-experiment-harness",
        "empirical-data-contracts",
        "spatial-data-foundation",
        "numpy",
        "pandas",
        "scipy",
        "statsmodels",
        "pyarrow",
    )
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def collect_runtime_environment() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": _package_versions(),
    }


def discover_git_state(repo_root: str | Path | None = None) -> dict[str, Any]:
    explicit = os.environ.get("FCV_HARNESS_COMMIT")
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return {
            "commit": commit,
            "dirty": bool(status.strip()),
            "source": "git",
        }
    except (OSError, subprocess.CalledProcessError):
        return {
            "commit": explicit,
            "dirty": None,
            "source": "FCV_HARNESS_COMMIT" if explicit else "unavailable",
        }


def _dataset_sha(dataset: Any, label: str) -> str:
    value = getattr(dataset, "content_sha256", None)
    if not value:
        raise ValueError(f"{label} DatasetRef must carry content_sha256")
    return str(value)


def build_current_e2_reference_identity(
    result: Mapping[str, Any],
    *,
    config_path: str | Path,
    lock: CurrentE2ReferenceLock | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build stable analysis identity plus exact numerical execution identity.

    The analysis hash names the exact scientific frame and upstream bytes. The
    execution hash additionally binds software versions and the harness commit.
    Neither operation persists the analysis frame itself.
    """
    spec = result["spec"]
    calibration = result["calibration"]
    primary_cell_id = spec.primary_cell.cell_id
    primary = calibration["cells"][primary_cell_id]
    country_scope = result.get("country_scope")
    if not isinstance(country_scope, Mapping):
        raise ValueError("current E2 reference identity requires explicit country_scope")
    countries = tuple(str(value) for value in country_scope["analysis_country_iso3"])

    geography_dataset = result["geography_dataset"]
    treatment_bundle = result["treatment_bundle"]
    outcome_bundle = result["outcome_bundle"]
    config_sha = sha256_file(config_path)
    frame_sha = stable_frame_sha256(
        primary["frame"],
        unit_col=spec.unit_col,
        period_col=spec.period_col,
    )

    analysis_payload = {
        "schema": REFERENCE_IDENTITY_SCHEMA,
        "reference_id": spec.reference_id,
        "config_sha256": config_sha,
        "primary_cell_id": primary_cell_id,
        "inputs": {
            "geography_sha256": _dataset_sha(geography_dataset, "geography"),
            "treatment_sha256": _dataset_sha(treatment_bundle.dataset, "treatment"),
            "outcome_sha256": _dataset_sha(outcome_bundle.dataset, "outcome"),
        },
        "analysis_country_iso3": list(countries),
        "analysis_country_count": len(countries),
        "primary_frame_sha256": frame_sha,
        "analysis_frame_persisted": False,
    }
    analysis_sha = _canonical_sha256(analysis_payload)
    git_state = discover_git_state(repo_root)
    runtime = collect_runtime_environment()
    execution_payload = {
        "analysis_identity_sha256": analysis_sha,
        "harness_git": git_state,
        "runtime_environment": runtime,
    }
    execution_sha = _canonical_sha256(execution_payload)
    identity = {
        **analysis_payload,
        "analysis_identity_sha256": analysis_sha,
        "execution": execution_payload,
        "execution_identity_sha256": execution_sha,
    }
    if lock is not None:
        verify_current_e2_reference_lock(identity, lock)
        identity["lock"] = {
            "lock_id": lock.lock_id,
            "verified": True,
            "expected": asdict(lock),
        }
    return identity


def verify_current_e2_reference_lock(
    identity: Mapping[str, Any],
    lock: CurrentE2ReferenceLock,
) -> None:
    failures: list[str] = []
    if identity.get("reference_id") != lock.reference_id:
        failures.append("reference_id")
    if identity.get("config_sha256") != lock.config_sha256:
        failures.append("config_sha256")
    if identity.get("primary_cell_id") != lock.primary_cell_id:
        failures.append("primary_cell_id")
    inputs = identity.get("inputs", {})
    if inputs.get("geography_sha256") != lock.geography_sha256:
        failures.append("geography_sha256")
    if inputs.get("treatment_sha256") != lock.treatment_sha256:
        failures.append("treatment_sha256")
    if inputs.get("outcome_sha256") != lock.outcome_sha256:
        failures.append("outcome_sha256")
    if int(identity.get("analysis_country_count", -1)) != lock.expected_analysis_country_count:
        failures.append("analysis_country_count")
    if failures:
        raise ValueError(
            "current E2 reference lock mismatch: " + ", ".join(failures)
        )


def write_reference_identity(identity: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(identity), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "REFERENCE_IDENTITY_SCHEMA",
    "REFERENCE_LOCK_SCHEMA",
    "CurrentE2ReferenceLock",
    "sha256_file",
    "stable_frame_sha256",
    "collect_runtime_environment",
    "discover_git_state",
    "build_current_e2_reference_identity",
    "verify_current_e2_reference_lock",
    "write_reference_identity",
]
