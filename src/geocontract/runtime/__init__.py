"""Runtime spatial invariant assertions and guards package (D2-P3)."""

from geocontract.runtime.assertions import (
    RuntimeReport,
    RuntimeViolation,
    check_area_conservation,
    check_boundary_clip,
    check_geometry_validity,
    check_numeric_invariants,
    check_resampling_drift,
    check_row_conservation,
    verify_output_contract,
)

__all__ = [
    "RuntimeReport",
    "RuntimeViolation",
    "check_area_conservation",
    "check_boundary_clip",
    "check_geometry_validity",
    "check_numeric_invariants",
    "check_resampling_drift",
    "check_row_conservation",
    "verify_output_contract",
]
