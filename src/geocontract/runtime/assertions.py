"""Runtime spatial invariant probes and property assertion engine (D2-P3).

Supports GeoPandas, Shapely, and NumPy when installed, with automatic pure-Python
fallbacks for GeoJSON dicts, row-dict tables, and nested numeric lists.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from geocontract.dsl.schema import GeoContract

try:
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None  # type: ignore[assignment]

try:
    from shapely.geometry import shape as _shapely_shape
    from shapely.geometry.base import BaseGeometry as _BaseGeometry
except ImportError:  # pragma: no cover
    _shapely_shape = None  # type: ignore[assignment]
    _BaseGeometry = None  # type: ignore[assignment]


@dataclass
class RuntimeViolation:
    code: str
    severity: str
    message: str
    suggested_fix: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "details": dict(self.details),
        }


@dataclass
class RuntimeReport:
    passed: bool
    violations: list[RuntimeViolation] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "metrics": dict(self.metrics),
        }


# ── Pure-Python geometry fallbacks ────────────────────────────────────────

def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    o1 = _orient(p1, p2, p3)
    o2 = _orient(p1, p2, p4)
    o3 = _orient(p3, p4, p1)
    o4 = _orient(p3, p4, p2)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _pure_ring_valid(ring: Sequence[Sequence[float]]) -> bool:
    if len(ring) < 4:
        return False
    if tuple(ring[0][:2]) != tuple(ring[-1][:2]):
        return False
    pts = [(float(p[0]), float(p[1])) for p in ring]
    n = len(pts) - 1
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_intersect(pts[i], pts[i + 1], pts[j], pts[j + 1]):
                return False
    return True


def _pure_ring_area(ring: Sequence[Sequence[float]]) -> float:
    area = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = float(ring[i][0]), float(ring[i][1])
        x2, y2 = float(ring[i + 1][0]), float(ring[i + 1][1])
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _pure_geojson_bbox(geom: dict[str, Any]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def _walk(coords: Any) -> None:
        if isinstance(coords, (list, tuple)) and coords:
            if isinstance(coords[0], (int, float)):
                xs.append(float(coords[0]))
                ys.append(float(coords[1]))
            else:
                for sub in coords:
                    _walk(sub)

    _walk(geom.get("coordinates", []))
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _extract_geometries(obj: Any) -> list[Any]:
    if hasattr(obj, "geometry") and not isinstance(obj, dict):
        return list(obj.geometry)
    if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        return [f.get("geometry") for f in obj.get("features", [])]
    if isinstance(obj, dict) and "type" in obj and "coordinates" in obj:
        return [obj]
    if isinstance(obj, (list, tuple)):
        return list(obj)
    return [obj]


def _geom_is_valid(g: Any, *, force_pure_python: bool = False) -> bool:
    if g is None:
        return False
    if not force_pure_python and _BaseGeometry is not None and isinstance(g, _BaseGeometry):
        return bool(g.is_valid and not g.is_empty)
    if isinstance(g, dict):
        if not force_pure_python and _shapely_shape is not None:
            try:
                sg = _shapely_shape(g)
                return bool(sg.is_valid and not sg.is_empty)
            except Exception:
                return False
        gtype = g.get("type")
        coords = g.get("coordinates")
        if gtype == "Point":
            return isinstance(coords, (list, tuple)) and len(coords) >= 2
        if gtype == "LineString":
            return isinstance(coords, (list, tuple)) and len(coords) >= 2
        if gtype == "Polygon":
            return bool(coords) and all(_pure_ring_valid(r) for r in coords)
        if gtype == "MultiPolygon":
            return bool(coords) and all(all(_pure_ring_valid(r) for r in poly) for poly in coords)
    return False


def _geom_area(g: Any, *, force_pure_python: bool = False) -> float:
    if g is None:
        return 0.0
    if not force_pure_python and _BaseGeometry is not None and isinstance(g, _BaseGeometry):
        return float(g.area)
    if isinstance(g, dict):
        if not force_pure_python and _shapely_shape is not None:
            return float(_shapely_shape(g).area)
        gtype = g.get("type")
        coords = g.get("coordinates", [])
        if gtype == "Polygon" and coords:
            outer = _pure_ring_area(coords[0])
            holes = sum(_pure_ring_area(r) for r in coords[1:])
            return max(0.0, outer - holes)
        if gtype == "MultiPolygon":
            return sum(
                max(0.0, _pure_ring_area(p[0]) - sum(_pure_ring_area(r) for r in p[1:]))
                for p in coords
                if p
            )
    return 0.0


def _flatten_numeric(data: Any, nodata: float | None = None, *, force_pure_python: bool = False) -> list[float]:
    if not force_pure_python and _np is not None and isinstance(data, _np.ndarray):
        arr = data.astype(float).ravel()
        mask = ~_np.isnan(arr) & ~_np.isinf(arr)
        if nodata is not None:
            mask &= arr != float(nodata)
        return [float(x) for x in arr[mask]]

    out: list[float] = []

    def _walk(item: Any) -> None:
        if isinstance(item, (list, tuple)):
            for x in item:
                _walk(x)
        elif item is not None:
            v = float(item)
            if math.isnan(v) or math.isinf(v):
                return
            if nodata is not None and v == float(nodata):
                return
            out.append(v)

    _walk(data)
    return out


# ── Probe functions ───────────────────────────────────────────────────────

def check_geometry_validity(geoms: Any, *, force_pure_python: bool = False) -> RuntimeReport:
    items = _extract_geometries(geoms)
    invalid_idx = [i for i, g in enumerate(items) if not _geom_is_valid(g, force_pure_python=force_pure_python)]
    violations = []
    if invalid_idx:
        violations.append(
            RuntimeViolation(
                code="RT_INVALID_GEOMETRY",
                severity="error",
                message=f"Found {len(invalid_idx)} invalid or empty geometries (indices: {invalid_idx[:10]}).",
                suggested_fix="Apply .make_valid() or GRASS v.clean before spatial operations.",
                details={"invalid_count": len(invalid_idx), "indices": invalid_idx[:20]},
            )
        )
    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"total_geometries": len(items), "invalid_count": len(invalid_idx)},
    )


def check_area_conservation(
    before: Any,
    after: Any,
    *,
    rel_tol: float = 0.01,
    allow_shrink: bool = False,
    force_pure_python: bool = False,
) -> RuntimeReport:
    def _total(x: Any) -> float:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, (list, tuple)) and x and isinstance(x[0], (int, float)):
            return float(sum(x))
        return sum(_geom_area(g, force_pure_python=force_pure_python) for g in _extract_geometries(x))

    a_before = _total(before)
    a_after = _total(after)
    violations = []
    if a_before <= 0:
        rel_diff = 0.0 if a_after == 0 else float("inf")
    else:
        rel_diff = abs(a_after - a_before) / a_before

    if allow_shrink:
        if a_after > a_before * (1.0 + rel_tol):
            violations.append(
                RuntimeViolation(
                    code="RT_AREA_EXCEEDS_SOURCE",
                    severity="error",
                    message=f"Output area ({a_after:.4f}) exceeds source area ({a_before:.4f}) beyond tol={rel_tol}.",
                    suggested_fix="Clip output geometries to source boundary and deduplicate overlaps.",
                    details={"before": a_before, "after": a_after, "rel_diff": rel_diff},
                )
            )
    elif rel_diff > rel_tol:
        violations.append(
            RuntimeViolation(
                code="RT_AREA_CONSERVATION",
                severity="error",
                message=f"Area drift {rel_diff:.4%} exceeds tolerance {rel_tol:.4%} (before={a_before:.4f}, after={a_after:.4f}).",
                suggested_fix="Repair overlapping polygons/slivers or verify projection units.",
                details={"before": a_before, "after": a_after, "rel_diff": rel_diff},
            )
        )
    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"area_before": a_before, "area_after": a_after, "rel_diff": rel_diff},
    )


def check_row_conservation(
    source_rows: int,
    output_rows: int,
    *,
    rule: str = "equal_to_source",
    expected_rows: int | None = None,
) -> RuntimeReport:
    violations = []
    if rule == "equal_to_source" and output_rows != source_rows:
        violations.append(
            RuntimeViolation(
                code="RT_ROW_COUNT_MISMATCH",
                severity="error",
                message=f"Expected {source_rows} rows (one_output_row_per_source), got {output_rows}.",
                suggested_fix="Use how='left' spatial join and aggregate back to unique source IDs.",
                details={"source_rows": source_rows, "output_rows": output_rows},
            )
        )
    elif rule == "lte_source" and output_rows > source_rows:
        violations.append(
            RuntimeViolation(
                code="RT_ROW_COUNT_INFLATED",
                severity="error",
                message=f"Output rows ({output_rows}) exceed source rows ({source_rows}).",
                suggested_fix="Deduplicate or aggregate joined features.",
                details={"source_rows": source_rows, "output_rows": output_rows},
            )
        )
    elif rule == "exact" and expected_rows is not None and output_rows != expected_rows:
        violations.append(
            RuntimeViolation(
                code="RT_ROW_COUNT_EXACT",
                severity="error",
                message=f"Expected exactly {expected_rows} rows, got {output_rows}.",
                suggested_fix="Verify join cardinality and filtering criteria.",
                details={"expected_rows": expected_rows, "output_rows": output_rows},
            )
        )
    elif rule == "any_nonempty" and output_rows == 0:
        violations.append(
            RuntimeViolation(
                code="RT_EMPTY_OUTPUT",
                severity="error",
                message="Output dataset is empty (0 rows).",
                suggested_fix="Check CRS alignment and spatial predicate direction.",
                details={"output_rows": output_rows},
            )
        )
    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"source_rows": source_rows, "output_rows": output_rows, "rule": rule},
    )


def check_numeric_invariants(
    rows: Sequence[dict[str, Any]],
    *,
    nonnegative_cols: Iterable[str] = (),
    ratio_cols: Iterable[str] = (),
    value_ranges: dict[str, dict[str, float | None]] | None = None,
) -> RuntimeReport:
    violations: list[RuntimeViolation] = []
    ranges = dict(value_ranges or {})
    for col in nonnegative_cols:
        ranges.setdefault(col, {"min": 0.0, "max": None})
    for col in ratio_cols:
        ranges[col] = {"min": 0.0, "max": 1.0}

    for col, bounds in ranges.items():
        lo = bounds.get("min")
        hi = bounds.get("max")
        bad_vals: list[float] = []
        for row in rows:
            if col not in row or row[col] is None or row[col] == "":
                continue
            val = float(row[col])
            if math.isnan(val) or math.isinf(val):
                bad_vals.append(val)
            elif (lo is not None and val < lo) or (hi is not None and val > hi):
                bad_vals.append(val)
        if bad_vals:
            violations.append(
                RuntimeViolation(
                    code="RT_NUMERIC_BOUNDS",
                    severity="error",
                    message=f"Column '{col}' has {len(bad_vals)} out-of-range value(s) for [{lo}, {hi}] (sample: {bad_vals[:5]}).",
                    suggested_fix=f"Verify units, sign, and denominator for '{col}'.",
                    details={"column": col, "min": lo, "max": hi, "sample_bad": bad_vals[:5]},
                )
            )
    return RuntimeReport(passed=not violations, violations=violations, metrics={"checked_columns": sorted(ranges)})


def check_boundary_clip(
    geoms: Any,
    boundary: Any,
    *,
    tol: float = 1e-6,
    force_pure_python: bool = False,
) -> RuntimeReport:
    items = _extract_geometries(geoms)
    b_items = _extract_geometries(boundary)
    violations: list[RuntimeViolation] = []
    outside_idx: list[int] = []

    if not force_pure_python and _BaseGeometry is not None and _shapely_shape is not None:
        from shapely.ops import unary_union

        b_shapes = [g if isinstance(g, _BaseGeometry) else _shapely_shape(g) for g in b_items]
        b_union = unary_union(b_shapes).buffer(tol)
        for i, g in enumerate(items):
            sg = g if isinstance(g, _BaseGeometry) else _shapely_shape(g)
            if not b_union.covers(sg):
                outside_idx.append(i)
    else:
        b_boxes = [_pure_geojson_bbox(b) for b in b_items if isinstance(b, dict)]
        bx0 = min(b[0] for b in b_boxes) - tol
        by0 = min(b[1] for b in b_boxes) - tol
        bx1 = max(b[2] for b in b_boxes) + tol
        by1 = max(b[3] for b in b_boxes) + tol
        for i, g in enumerate(items):
            if isinstance(g, dict):
                gx0, gy0, gx1, gy1 = _pure_geojson_bbox(g)
                if gx0 < bx0 or gy0 < by0 or gx1 > bx1 or gy1 > by1:
                    outside_idx.append(i)

    if outside_idx:
        violations.append(
            RuntimeViolation(
                code="RT_UNCLIPPED_BOUNDARY",
                severity="error",
                message=f"{len(outside_idx)} geometry feature(s) extend outside the study boundary.",
                suggested_fix="Clip geometries to boundary using gpd.clip() or .intersection(boundary.unary_union).",
                details={"outside_count": len(outside_idx), "indices": outside_idx[:20]},
            )
        )
    return RuntimeReport(
        passed=not violations,
        violations=violations,
        metrics={"checked": len(items), "outside_count": len(outside_idx)},
    )


def check_resampling_drift(
    before_values: Any,
    after_values: Any,
    *,
    nodata: float | None = None,
    max_mean_rel_drift: float = 0.05,
    max_std_rel_drift: float = 0.15,
    force_pure_python: bool = False,
) -> RuntimeReport:
    v1 = _flatten_numeric(before_values, nodata=nodata, force_pure_python=force_pure_python)
    v2 = _flatten_numeric(after_values, nodata=nodata, force_pure_python=force_pure_python)
    violations: list[RuntimeViolation] = []

    if not v1 or not v2:
        violations.append(
            RuntimeViolation(
                code="RT_EMPTY_RASTER",
                severity="error",
                message="Raster contains no valid pixels after NoData masking.",
                suggested_fix="Check NoData value and spatial extent overlap.",
            )
        )
        return RuntimeReport(passed=False, violations=violations)

    m1 = sum(v1) / len(v1)
    m2 = sum(v2) / len(v2)
    s1 = math.sqrt(sum((x - m1) ** 2 for x in v1) / len(v1))
    s2 = math.sqrt(sum((x - m2) ** 2 for x in v2) / len(v2))
    mean_drift = abs(m2 - m1) / max(abs(m1), 1e-9)
    std_drift = abs(s2 - s1) / max(abs(s1), 1e-9) if s1 > 1e-9 else 0.0

    if mean_drift > max_mean_rel_drift:
        violations.append(
            RuntimeViolation(
                code="RT_RESAMPLING_MEAN_DRIFT",
                severity="error",
                message=f"Resampled raster mean drifted by {mean_drift:.2%} (before={m1:.4f}, after={m2:.4f}).",
                suggested_fix="Verify NoData masking and choose appropriate resampling method (bilinear/cubic vs nearest).",
                details={"mean_before": m1, "mean_after": m2, "mean_rel_drift": mean_drift},
            )
        )
    if std_drift > max_std_rel_drift:
        violations.append(
            RuntimeViolation(
                code="RT_RESAMPLING_STD_DRIFT",
                severity="warning",
                message=f"Resampled raster std drifted by {std_drift:.2%} (before={s1:.4f}, after={s2:.4f}).",
                suggested_fix="Inspect resampling kernel and operation order (resample before slope).",
                details={"std_before": s1, "std_after": s2, "std_rel_drift": std_drift},
            )
        )
    return RuntimeReport(
        passed=not any(v.severity == "error" for v in violations),
        violations=violations,
        metrics={
            "mean_before": m1,
            "mean_after": m2,
            "std_before": s1,
            "std_after": s2,
            "mean_rel_drift": mean_drift,
            "std_rel_drift": std_drift,
        },
    )


def verify_output_contract(
    contract: GeoContract,
    output_path: str | Path | None = None,
) -> RuntimeReport:
    """Verify an output file (CSV/JSON/GeoJSON) against contract Y (output spec)."""
    target = Path(output_path or contract.output.path)
    violations: list[RuntimeViolation] = []
    if not target.is_file():
        violations.append(
            RuntimeViolation(
                code="RT_MISSING_OUTPUT_FILE",
                severity="error",
                message=f"Required output file does not exist: {target}",
                suggested_fix=f"Ensure workflow writes output to '{target}'.",
            )
        )
        return RuntimeReport(passed=False, violations=violations)

    rows: list[dict[str, Any]] = []
    cols: list[str] = []
    fmt = contract.output.format.lower()
    try:
        if fmt == "csv":
            with target.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                cols = list(reader.fieldnames or [])
                rows = list(reader)
        elif fmt == "geojson":
            payload = json.loads(target.read_text(encoding="utf-8"))
            feats = payload.get("features", [])
            rows = [dict(ft.get("properties") or {}) for ft in feats]
            cols = sorted({k for r in rows for k in r})
            geom_rep = check_geometry_validity(payload)
            violations.extend(geom_rep.violations)
        elif fmt == "json":
            payload = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                rows = [r for r in payload if isinstance(r, dict)]
            elif isinstance(payload, dict):
                rows = [payload]
            cols = sorted({k for r in rows for k in r})
    except Exception as exc:
        violations.append(
            RuntimeViolation(
                code="RT_UNREADABLE_OUTPUT",
                severity="error",
                message=f"Failed to read output '{target}': {exc}",
                suggested_fix="Write well-formed CSV/JSON/GeoJSON matching contract.output.format.",
            )
        )
        return RuntimeReport(passed=False, violations=violations)

    missing_cols = [c for c in contract.output.required_columns if c not in cols]
    if missing_cols:
        violations.append(
            RuntimeViolation(
                code="RT_MISSING_COLUMNS",
                severity="error",
                message=f"Output missing required column(s): {missing_cols}",
                suggested_fix="Include all contract.output.required_columns in output schema.",
                details={"missing": missing_cols, "present": cols},
            )
        )

    id_col = contract.output.id_column
    if id_col and contract.output.unique_id and id_col in cols:
        ids = [r.get(id_col) for r in rows]
        if len(ids) != len(set(ids)):
            violations.append(
                RuntimeViolation(
                    code="RT_DUPLICATE_ID",
                    severity="error",
                    message=f"Duplicate values found in unique ID column '{id_col}'.",
                    suggested_fix="Aggregate or deduplicate records by source ID before writing.",
                )
            )

    source_rows = next((d.row_count for d in contract.datasets if d.role == "source" and d.row_count is not None), 0)
    row_rep = check_row_conservation(
        source_rows,
        len(rows),
        rule=contract.output.row_count_rule,
        expected_rows=contract.output.expected_rows,
    )
    violations.extend(row_rep.violations)

    num_rep = check_numeric_invariants(rows, value_ranges=contract.output.value_ranges)
    violations.extend(num_rep.violations)

    return RuntimeReport(
        passed=not any(v.severity == "error" for v in violations),
        violations=violations,
        metrics={"row_count": len(rows), "columns": cols},
    )
