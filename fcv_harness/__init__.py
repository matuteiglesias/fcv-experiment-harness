from .core import ExperimentSpec, classify_project_state, build_exposure_state
from .estimate import spatial_did, bandwidth_sweep
from .gates import run_gates, render_gate_report
from .panel import (
    PanelExperimentSpec,
    build_panel_analysis_frame,
    panel_baseline_estimate,
    run_panel_gates,
)
from .canonical import (
    SourceContract,
    CanonicalPanelSpec,
    audit_sources,
    build_canonical_panel,
    run_canonical_checkpoint,
    write_checkpoint_outputs,
)
from .lattice_diagnostics import (
    derive_country_iso3,
    attach_country_iso3,
    build_source_outside_lattice_diagnostics,
)
from .canonical_experiment import (
    TreatmentMeasurementSpec,
    EligibilitySpec,
    OutcomeMeasurementSpec,
    CanonicalPanelExperimentSpec,
    resolve_treatment_measurement,
    resolve_outcome_measurement,
    prepare_experiment_measurement_frame,
    build_input_eligibility_report,
    run_experiment_preflight,
)
from .analysis_surface import (
    AnalysisUniverseSpec,
    AreaPeriodOutcomeResolutionSpec,
    AnalysisSurfaceSpec,
    build_analysis_universe,
    resolve_area_period_outcome,
    attach_resolved_outcome,
    build_acled_measurement_audit,
    run_analysis_surface_checkpoint,
    write_analysis_surface_outputs,
)
from .calibration import (
    CalibrationCellSpec,
    CalibrationThresholds,
    CalibrationMatrixSpec,
    build_cell_experiment_spec,
    attach_pre_outcome,
    placebo_estimate,
    synthetic_signal_recovery,
    run_calibration_gates,
    run_calibration_cell,
    run_calibration_matrix,
    write_calibration_outputs,
)
from .empirical_input import (
    EmpiricalCompatibilityError,
    EmpiricalInputError,
    EmpiricalMeasurementBundle,
    load_empirical_measurement,
    require_same_geography,
    require_same_period_scheme,
)
from .measurement_projection import (
    ExperimentProjectionReport,
    MeasurementProjectionError,
    MeasurementProjectionSpec,
    ProjectionResult,
    project_empirical_measurement,
    write_projection_report,
)
from .contracted_surface import (
    ContractedAnalysisSurfaceSpec,
    attach_contracted_measurement,
    build_projection_audit,
    run_contracted_analysis_surface_checkpoint,
    write_contracted_analysis_surface_outputs,
)
from .contracted_experiment import (
    ContractedPanelExperimentSpec,
    prepare_contracted_experiment_frame,
    run_contracted_experiment_preflight,
    write_contracted_experiment_preflight_outputs,
)
from .contracted_calibration import (
    build_contracted_cell_experiment_spec,
    run_contracted_calibration_cell,
    run_contracted_calibration_matrix,
    write_contracted_calibration_outputs,
)
from .fully_contracted_experiment import (
    FullyContractedExperimentError,
    FullyContractedPanelExperimentSpec,
    FullyContractedPreflightResult,
    TreatmentDerivationSpec,
    TreatmentEligibilitySpec,
    build_fully_contracted_eligibility_report,
    build_fully_contracted_support_by_period,
    prepare_fully_contracted_experiment_frame,
    run_fully_contracted_experiment_preflight,
    write_fully_contracted_preflight_outputs,
)
from .fully_contracted_calibration import (
    FullyContractedCalibrationSpec,
    FullyContractedTreatmentCellSpec,
    experiment_for_treatment_cell,
    run_fully_contracted_calibration_cell,
    run_fully_contracted_calibration_matrix,
    write_fully_contracted_calibration_outputs,
)
from .observability import (
    derive_repetition_seed,
    inject_known_effect,
    run_e2_observability,
    run_observability_grid,
    summarize_observability,
    wild_cluster_signs,
    write_observability_outputs,
)
