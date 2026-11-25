"""Runtime refusal guard (``reject_task``), close-value guard, and semantic verifier Vt (D2-P3).

Attributions:
- ``reject_task`` originates from GeoBenchX and GeoNatureAgent Benchmark (arXiv:2606.12821).
- Bidirectional refusal verification follows Axis Spatial methodology (Index v1.0, 2026-10-16).
- Close-value epsilon guard addresses GeoNatureAgent §4.5.1 (C01).
- Semantic verifier Vt implements GeoContra Algorithm 5 (arXiv:2605.00782v1 §4.3).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Iterable

from geocontract.dsl.schema import GeoContract
from geocontract.runtime.assertions import RuntimeReport, RuntimeViolation


@dataclass
class RejectDecision:
    should_reject: bool
    reasons: list[str] = field(default_factory=list)
    missing_entities: list[str] = field(default_factory=list)
    missing_indicators: list[str] = field(default_factory=list)
    display_only_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_reject": self.should_reject,
            "reasons": list(self.reasons),
            "missing_entities": list(self.missing_entities),
            "missing_indicators": list(self.missing_indicators),
            "display_only_targets": list(self.display_only_targets),
        }


def evaluate_reject_task(
    *,
    requested_entities: Iterable[str] = (),
    available_entities: Iterable[str] = (),
    requested_indicators: Iterable[str] = (),
    available_indicators: Iterable[str] = (),
    target_layers: Iterable[dict[str, Any]] = (),
    metric_op_requested: bool = False,
) -> RejectDecision:
    """Determine whether a geospatial query is unsolvable from the provided data."""
    avail_ent = {e.strip().lower() for e in available_entities}
    avail_ind = {i.strip().lower() for i in available_indicators}

    missing_ent = [e for e in requested_entities if e.strip().lower() not in avail_ent]
    missing_ind = [i for i in requested_indicators if i.strip().lower() not in avail_ind]
    display_only: list[str] = []
    missing_crs: list[str] = []

    for layer in target_layers:
        lname = str(layer.get("name", "<unnamed>"))
        if layer.get("display_only", False):
            display_only.append(lname)
        if metric_op_requested and not layer.get("crs"):
            missing_crs.append(lname)

    reasons: list[str] = []
    if missing_ent:
        reasons.append(f"Requested entity/entities not found in dataset: {missing_ent}")
    if missing_ind:
        reasons.append(f"Requested indicator/field(s) not available: {missing_ind}")
    if display_only:
        reasons.append(f"Quantitative analysis requested on display-only layer(s): {display_only}")
    if missing_crs:
        reasons.append(f"Metric operation requested on layer(s) with missing CRS metadata: {missing_crs}")

    return RejectDecision(
        should_reject=bool(reasons),
        reasons=reasons,
        missing_entities=missing_ent,
        missing_indicators=missing_ind,
        display_only_targets=display_only,
    )


def verify_bidirectional_refusal(
    decision: RejectDecision,
    *,
    agent_rejected: bool,
) -> RuntimeReport:
    """Bidirectional refusal check (Axis Spatial D02/D03):
    - Unsolvable task answered (not rejected) -> violation (hallucination).
    - Solvable task refused (rejected) -> violation (false refusal).
    """
    violations: list[RuntimeViolation] = []
    if decision.should_reject and not agent_rejected:
        violations.append(
            RuntimeViolation(
                code="RT_HALLUCINATED_UNSOLVABLE",
                severity="error",
                message="Agent answered an unsolvable task instead of invoking reject_task.",
                suggested_fix="Call reject_task with explicit missing entity/indicator/layer reasons.",
                details=decision.to_dict(),
            )
        )
    elif not decision.should_reject and agent_rejected:
        violations.append(
            RuntimeViolation(
                code="RT_FALSE_REFUSAL",
                severity="error",
                message="Agent invoked reject_task on a solvable task whose required data is present.",
                suggested_fix="Proceed with verified spatial analysis instead of refusing.",
                details=decision.to_dict(),
            )
        )
    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"should_reject": decision.should_reject, "agent_rejected": agent_rejected},
    )


def check_close_value_comparison(
    value_a: float,
    value_b: float,
    *,
    claimed_relation: str,
    epsilon: float = 0.5,
) -> RuntimeReport:
    """Guard against fabricating directional differences when |a - b| <= epsilon (GeoNatureAgent C01).

    ``claimed_relation`` must be one of ``"higher"``, ``"lower"``, or ``"effectively_equal"``.
    """
    diff = value_a - value_b
    abs_diff = abs(diff)
    violations: list[RuntimeViolation] = []

    if abs_diff <= epsilon:
        if claimed_relation != "effectively_equal":
            violations.append(
                RuntimeViolation(
                    code="RT_CLOSE_VALUE_DIRECTIONAL_CLAIM",
                    severity="error",
                    message=(
                        f"Values {value_a} and {value_b} differ by {abs_diff:.4f} <= epsilon ({epsilon}), "
                        f"so claiming '{claimed_relation}' fabricates a directional difference."
                    ),
                    suggested_fix="Report the two regions as 'effectively_equal' and state the exact delta.",
                    details={"value_a": value_a, "value_b": value_b, "diff": diff, "epsilon": epsilon},
                )
            )
    else:
        expected = "higher" if diff > 0 else "lower"
        if claimed_relation != expected:
            violations.append(
                RuntimeViolation(
                    code="RT_WRONG_COMPARISON_DIRECTION",
                    severity="error",
                    message=f"Claimed '{claimed_relation}' for ({value_a}, {value_b}), expected '{expected}'.",
                    suggested_fix=f"Report '{expected}' with exact difference {diff:+.4f}.",
                    details={"value_a": value_a, "value_b": value_b, "diff": diff, "expected": expected},
                )
            )

    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"diff": diff, "abs_diff": abs_diff, "epsilon": epsilon},
    )


# ── Semantic Verifier Vt (GeoContra Algorithm 5) ──────────────────────────

_FAMILY_REQUIRED_TOKEN_GROUPS: dict[str, list[tuple[str, set[str]]]] = {
    "buffer_counting": [
        ("buffer operation", {"buffer", "vector_buffer"}),
        ("spatial join / aggregation", {"sjoin", "groupby", "intersection", "clip", "intersects", "contains", "within"}),
    ],
    "spatial_joins": [
        ("spatial join / predicate", {"sjoin", "intersects", "within", "contains", "covers", "overlay"}),
    ],
    "nearest_neighbor": [
        ("nearest-neighbor / distance", {"sjoin_nearest", "distance", "nearest_points", "cKDTree", "KDTree"}),
    ],
    "network_accessibility": [
        ("graph nearest-node snapping", {"nearest_nodes", "get_nearest_node"}),
        ("network shortest-path / ego-graph", {"shortest_path", "shortest_path_length", "dijkstra_path", "ego_graph"}),
    ],
    "overlay_areas": [
        ("overlay / intersection / clip / dissolve", {"overlay", "intersection", "clip", "dissolve", "symmetric_difference", "difference"}),
    ],
    "raster_sampling": [
        ("raster read / sample / reproject / slope", {"read", "sample", "raster_reproject", "gdalwarp", "slope", "resample", "band_math"}),
    ],
    "zonal_statistics": [
        ("zonal statistics / aggregation", {"zonal_stats", "raster_stats", "compare_areas", "groupby", "mean", "sum"}),
    ],
    "topology_quality": [
        ("geometry validation / repair", {"is_valid", "make_valid", "v.build", "v.clean", "validate_schema", "check_crs"}),
    ],
}


def verify_semantic_contract(source: str, contract: GeoContract) -> RuntimeReport:
    """Verify semantic operation presence (Vt) dispatched by contract.family."""
    tree = ast.parse(source)
    called_tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_tokens.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_tokens.add(node.func.attr)
        elif isinstance(node, ast.Attribute):
            called_tokens.add(node.attr)

    # If task explicitly invoked reject_task and contract enables reject_policy, accept early
    if "reject_task" in called_tokens and contract.reject_policy.get("enabled", False):
        return RuntimeReport(passed=True, metrics={"family": contract.family, "rejected": True})

    violations: list[RuntimeViolation] = []
    req_groups = _FAMILY_REQUIRED_TOKEN_GROUPS.get(contract.family, [])
    for label, token_set in req_groups:
        if not (called_tokens & token_set):
            violations.append(
                RuntimeViolation(
                    code="VT_MISSING_REQUIRED_OP",
                    severity="error",
                    message=f"Task family '{contract.family}' requires {label} (expected one of {sorted(token_set)}).",
                    suggested_fix=f"Implement {label} using allowed methods {contract.allowed_methods}.",
                    details={"family": contract.family, "expected_any": sorted(token_set)},
                )
            )

    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"family": contract.family, "observed_tokens": sorted(called_tokens)},
    )
