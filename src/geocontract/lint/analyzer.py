"""Python AST static spatial code analyzer (``geolint`` engine, D2-P2).

Performs lightweight dataflow tracking over CRS state, geometry kind, raster
NoData masking, operation ordering, and contract schema constraints to detect
28 geographic anti-patterns (G001–G028) with high recall and low false-positive rate.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from geocontract.dsl.schema import GeoContract
from geocontract.lint.rules import RULES, LintFinding

GEOGRAPHIC_CRS_CODES: frozenset[str] = frozenset(
    {"EPSG:4326", "EPSG:4269", "EPSG:4267", "EPSG:4258", "OGC:CRS84", "4326"}
)
_EPSG_NUM_RE = re.compile(r"EPSG:(\d+)", re.I)
_RES_IN_NAME_RE = re.compile(r"(?:^|[_\-/])(\d+(?:\.\d+)?)m(?:[_\-/.]|$)", re.I)

_POINT_HINTS = ("point", "pts", "pt", "school", "stop", "station", "clinic", "sensor", "site", "origin", "dest", "incident", "hydrant")
_POLY_HINTS = ("poly", "tract", "parcel", "county", "district", "boundary", "zone", "watershed", "muni", "flood", "city", "region", "area", "grid")
_CONT_RASTER_HINTS = ("dem", "elev", "elevation", "temp", "temperature", "precip", "ndvi", "slope", "dsm", "dtm")
_CAT_RASTER_HINTS = ("nlcd", "landcover", "land_cover", "lulc", "class", "categorical", "lc")
_DISPLAY_HINTS = ("basemap", "display_only", "tile_layer", "hillshade_rgb", "wms_display")
_ID_COL_RE = re.compile(r"(^id$|_id$|id$|^fips$|^geoid$|^tract_code$)", re.I)


def _is_geographic_crs(crs_val: str | None) -> bool:
    if not crs_val:
        return False
    up = crs_val.strip().upper()
    if up in GEOGRAPHIC_CRS_CODES:
        return True
    m = _EPSG_NUM_RE.search(up)
    return bool(m and m.group(1) in {"4326", "4269", "4267", "4258"})


def _extract_const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_const_num(node: ast.AST | None) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _extract_const_num(node.operand)
        return -inner if inner is not None else None
    return None


def _root_name(node: ast.AST) -> str | None:
    cur = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _kw_arg(node: ast.Call, name: str) -> ast.AST | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _expr_contains_call(node: ast.AST, func_names: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_name(child) in func_names:
            return True
    return False


def _infer_geom_kind(name: str) -> str | None:
    low = name.lower()
    if any(h in low for h in _DISPLAY_HINTS):
        return "display_only"
    if any(h in low for h in _CAT_RASTER_HINTS):
        return "categorical_raster"
    if any(h in low for h in _CONT_RASTER_HINTS):
        return "continuous_raster"
    if any(h in low for h in _POINT_HINTS):
        return "point"
    if any(h in low for h in _POLY_HINTS):
        return "polygon"
    return None


class SpatialASTAnalyzer(ast.NodeVisitor):
    """AST visitor implementing geolint rules G001–G028."""

    def __init__(
        self,
        source: str,
        *,
        file_path: str = "<string>",
        contract: GeoContract | None = None,
    ) -> None:
        self.source = source
        self.file_path = file_path
        self.contract = contract
        self.findings: list[LintFinding] = []
        self._seen: set[tuple[str, int]] = set()

        # Symbol tables
        self.crs_state: dict[str, str] = {}  # var -> "EPSG:4326" | "EPSG:3857" | "PROJECTED" | "UNKNOWN"
        self.geom_kind: dict[str, str] = {}
        self.raw_raster_arrays: set[str] = set()
        self.masked_raster_arrays: set[str] = set()
        self.buffer_vars: set[str] = set()
        self.clipped_vars: set[str] = set()
        self.validated_vars: set[str] = set()
        self.sjoin_vars: dict[str, int] = {}  # var -> line
        self.aggregated_vars: set[str] = set()
        self.slope_vars: set[str] = set()
        self.derived_columns: set[str] = set()
        self.has_graph_context: bool = False
        self.has_boundary_var: bool = False
        self.has_output_write: bool = False
        self.has_travel_time_guard: bool = False
        self.travel_time_assign_line: int | None = None
        self.filename_res_map: dict[str, float] = {}  # var -> nominal res parsed from filename

        # Seed from contract if provided
        self._contract_fields: set[str] = set()
        self._contract_path_crs: dict[str, str] = {}
        self._contract_display_names: set[str] = set()
        if contract is not None:
            self._contract_fields = contract.all_known_fields()
            self._contract_fields.update(contract.output.required_columns)
            for ds in contract.datasets:
                self._contract_path_crs[ds.path] = ds.crs
                self._contract_path_crs[Path(ds.path).name] = ds.crs
                self.crs_state[ds.name] = ds.crs
                if ds.display_only:
                    self.geom_kind[ds.name] = "display_only"
                    self._contract_display_names.add(ds.name)
                elif ds.data_kind in ("continuous_raster", "categorical_raster"):
                    self.geom_kind[ds.name] = ds.data_kind
                elif ds.geometry_type in ("Point", "MultiPoint"):
                    self.geom_kind[ds.name] = "point"
                elif ds.geometry_type in ("Polygon", "MultiPolygon"):
                    self.geom_kind[ds.name] = "polygon"
                if ds.role == "boundary":
                    self.has_boundary_var = True
                if ds.role == "network" or ds.data_kind == "graph":
                    self.has_graph_context = True
            if contract.has_constraint("network_distance_required"):
                self.has_graph_context = True

    def _emit(self, rule_id: str, node: ast.AST, detail: str | None = None) -> None:
        line = getattr(node, "lineno", 1)
        col = getattr(node, "col_offset", 0)
        key = (rule_id, line)
        if key in self._seen:
            return
        self._seen.add(key)
        rule = RULES[rule_id]
        self.findings.append(
            LintFinding(
                rule_id=rule.rule_id,
                slug=rule.slug,
                severity=rule.severity,
                line=line,
                col=col,
                message=detail or rule.title,
                suggested_fix=rule.suggested_fix,
                file_path=self.file_path,
            )
        )

    def _resolve_expr_crs(self, node: ast.AST) -> str | None:
        """Infer CRS of an arbitrary expression, honoring inline .to_crs(...)."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "to_crs":
                if node.args:
                    s = _extract_const_str(node.args[0])
                    if s:
                        return s.upper()
                    if isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "crs":
                        other = _root_name(node.args[0].value)
                        if other and other in self.crs_state:
                            return self.crs_state[other]
                    return "PROJECTED"
                return "PROJECTED"
            cname = _call_name(node)
            if cname in ("read_file", "open", "GeoDataFrame", "set_crs", "reproject", "raster_reproject", "gdalwarp", "warp"):
                return self._infer_assigned_crs(node)
            # Propagate through chaining methods like .geometry, .copy(), .make_valid()
            return self._resolve_expr_crs(node.func.value)
        if isinstance(node, ast.Attribute):
            return self._resolve_expr_crs(node.value)
        if isinstance(node, ast.Subscript):
            return self._resolve_expr_crs(node.value)
        if isinstance(node, ast.Name):
            return self.crs_state.get(node.id)
        return None

    def _resolve_expr_kind(self, node: ast.AST) -> str | None:
        r = _root_name(node)
        if r:
            if r in self.geom_kind:
                return self.geom_kind[r]
            return _infer_geom_kind(r)
        return None

    def _infer_assigned_crs(self, value: ast.AST) -> str | None:
        if isinstance(value, ast.Call):
            cname = _call_name(value)
            if cname == "to_crs":
                return self._resolve_expr_crs(value)
            if cname in ("read_file", "open"):
                path_str = _extract_const_str(value.args[0]) if value.args else None
                if path_str:
                    if path_str in self._contract_path_crs:
                        return self._contract_path_crs[path_str]
                    fname = Path(path_str).name
                    if fname in self._contract_path_crs:
                        return self._contract_path_crs[fname]
                    low = path_str.lower()
                    if "4326" in low or "wgs84" in low:
                        return "EPSG:4326"
                    if "3857" in low:
                        return "EPSG:3857"
                    if re.search(r"(?:epsg:|_)326\d{2}", low) or "proj" in low or "utm" in low or "5070" in low or "26986" in low:
                        return "PROJECTED"
                    if low.endswith(".geojson") or low.endswith(".json"):
                        return "EPSG:4326"
            if cname == "GeoDataFrame":
                crs_kw = _kw_arg(value, "crs")
                crs_s = _extract_const_str(crs_kw)
                if crs_s:
                    return crs_s.upper()
            if cname == "set_crs":
                crs_arg = value.args[0] if value.args else _kw_arg(value, "crs")
                crs_s = _extract_const_str(crs_arg)
                if crs_s:
                    return crs_s.upper()
            if cname in ("reproject", "raster_reproject", "gdalwarp", "warp"):
                crs_kw = _kw_arg(value, "target_crs") or _kw_arg(value, "dst_crs")
                crs_s = _extract_const_str(crs_kw)
                return crs_s.upper() if crs_s else "PROJECTED"
        return self._resolve_expr_crs(value)

    def _check_post_pass(self, tree: ast.Module) -> None:
        # G020: Missing required output write when contract requires output file
        if self.contract is not None and not self.has_output_write:
            if (
                self.contract.has_constraint("output_file_required")
                or self.contract.output.path
            ):
                # Only trigger if script is non-trivial (>= 2 statements) and has no reject_task call
                has_reject = _expr_contains_call(tree, {"reject_task"})
                if len(tree.body) >= 2 and not has_reject and self.contract.has_constraint("output_file_required"):
                    self._emit(
                        "G020",
                        tree.body[-1],
                        f"Script never writes required output path '{self.contract.output.path}'.",
                    )

        # G014: Plain sjoin exported without aggregation when one_output_row_per_source or count contract
        if self.contract is not None and self.contract.has_constraint("one_output_row_per_source"):
            for var, line in self.sjoin_vars.items():
                if var not in self.aggregated_vars:
                    dummy = ast.Pass()
                    dummy.lineno = line
                    dummy.col_offset = 0
                    self._emit(
                        "G014",
                        dummy,
                        f"Spatial join variable '{var}' is never aggregated back to source rows.",
                    )

        # G026: Travel time subtraction without non-negativity guard
        if self.travel_time_assign_line is not None and not self.has_travel_time_guard:
            dummy = ast.Pass()
            dummy.lineno = self.travel_time_assign_line
            dummy.col_offset = 0
            self._emit(
                "G026",
                dummy,
                "Travel time computed by subtraction without a non-negativity assertion or clip(lower=0).",
            )

    def analyze(self) -> list[LintFinding]:
        tree = ast.parse(self.source, filename=self.file_path)
        self.visit(tree)
        self._check_post_pass(tree)
        self.findings.sort(key=lambda f: (f.line, f.col, f.rule_id))
        return self.findings

    # ── Visitors ──────────────────────────────────────────────────────────

    def visit_Assign(self, node: ast.Assign) -> None:
        # Track column derivation: df["new_col"] = ...
        for tgt in node.targets:
            if isinstance(tgt, ast.Subscript):
                col = _extract_const_str(tgt.slice)
                if col:
                    self.derived_columns.add(col)
                    if any(k in col.lower() for k in ("travel_min", "travel_time", "duration_min")):
                        if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub) for n in ast.walk(node.value)):
                            if not _expr_contains_call(node.value, {"clip", "maximum", "max", "abs"}):
                                self.travel_time_assign_line = node.lineno
            elif isinstance(tgt, ast.Name):
                var = tgt.id
                if any(h in var.lower() for h in ("boundary", "county", "city_limit", "study_area")):
                    self.has_boundary_var = True
                if any(h in var.lower() for h in ("graph", "road_net", "street_net", "walk_net")) or var == "G":
                    self.has_graph_context = True

                inferred_crs = self._infer_assigned_crs(node.value)
                if inferred_crs:
                    self.crs_state[var] = inferred_crs
                inferred_kind = _infer_geom_kind(var) or self._resolve_expr_kind(node.value)
                if inferred_kind:
                    self.geom_kind[var] = inferred_kind

                # Track filename resolution hint
                if isinstance(node.value, ast.Call) and _call_name(node.value) in ("open", "read_file"):
                    pstr = _extract_const_str(node.value.args[0]) if node.value.args else None
                    if pstr:
                        rm = _RES_IN_NAME_RE.search(pstr)
                        if rm:
                            self.filename_res_map[var] = float(rm.group(1))
                        if "display" in pstr.lower() or "basemap" in pstr.lower():
                            self.geom_kind[var] = "display_only"
                elif isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    rm = _RES_IN_NAME_RE.search(node.value.value)
                    if rm:
                        self.filename_res_map[var] = float(rm.group(1))

                # G021: Hardcoding resolution matching filename nominal resolution
                if any(k in var.lower() for k in ("res", "pixel_size", "cell_size")) and self.filename_res_map:
                    num = _extract_const_num(node.value)
                    if num is not None and num in self.filename_res_map.values():
                        self._emit(
                            "G021",
                            node,
                            f"Resolution '{var} = {num}' appears hardcoded from filename instead of reading dataset metadata (src.res).",
                        )

                # Track raster read() with or without masked=True
                if isinstance(node.value, ast.Call) and _call_name(node.value) == "read":
                    masked_kw = _kw_arg(node.value, "masked")
                    if isinstance(masked_kw, ast.Constant) and masked_kw.value is True:
                        self.masked_raster_arrays.add(var)
                    else:
                        self.raw_raster_arrays.add(var)

                # Track explicit nodata masking assignment
                if isinstance(node.value, ast.Subscript) and isinstance(node.value.value, ast.Name):
                    if node.value.value.id in self.raw_raster_arrays:
                        self.masked_raster_arrays.add(var)
                if _expr_contains_call(node.value, {"masked_equal", "masked_values", "masked_where", "where"}):
                    self.masked_raster_arrays.add(var)

                # Track buffer, clip, make_valid, sjoin, slope
                if _expr_contains_call(node.value, {"buffer"}):
                    self.buffer_vars.add(var)
                if _expr_contains_call(node.value, {"clip", "intersection"}):
                    self.clipped_vars.add(var)
                if _expr_contains_call(node.value, {"make_valid", "buffer_zero"}):
                    self.validated_vars.add(var)
                if _expr_contains_call(node.value, {"sjoin"}):
                    self.sjoin_vars[var] = node.lineno
                    if _expr_contains_call(node.value, {"groupby", "agg", "size", "count"}):
                        self.aggregated_vars.add(var)
                if _expr_contains_call(node.value, {"slope", "gdaldem"}):
                    self.slope_vars.add(var)
                if _expr_contains_call(node.value, {"groupby", "agg", "pivot_table"}):
                    rname = _root_name(node.value)
                    if rname:
                        self.aggregated_vars.add(rname)
                if _expr_contains_call(node.value, {"load_graphml", "graph_from_place", "graph_from_bbox"}):
                    self.has_graph_context = True

        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        src_seg = ast.dump(node.test)
        if "travel" in src_seg or "GtE" in src_seg or "Gt" in src_seg:
            self.has_travel_time_guard = True
        if "is_valid" in src_seg:
            rname = _root_name(node.test)
            if rname:
                self.validated_vars.add(rname)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # G002: .area on geographic CRS
        if node.attr == "area":
            crs = self._resolve_expr_crs(node.value)
            if _is_geographic_crs(crs):
                self._emit(
                    "G002",
                    node,
                    f"Accessing .area on geographic CRS ({crs}) returns square degrees instead of square meters.",
                )
            # G010: Unclipped buffer area when clip_to_boundary or boundary variable present
            rname = _root_name(node.value)
            is_buf = (rname in self.buffer_vars and rname not in self.clipped_vars) or (
                _expr_contains_call(node.value, {"buffer"})
                and not _expr_contains_call(node.value, {"clip", "intersection"})
            )
            need_clip = self.has_boundary_var or (
                self.contract is not None and self.contract.has_constraint("clip_to_boundary")
            )
            if is_buf and need_clip:
                self._emit(
                    "G010",
                    node,
                    "Computing .area directly on unclipped buffer geometry while a boundary constraint is active.",
                )

        # G003: .length on geographic CRS
        elif node.attr == "length":
            crs = self._resolve_expr_crs(node.value)
            if _is_geographic_crs(crs):
                self._emit(
                    "G003",
                    node,
                    f"Accessing .length on geographic CRS ({crs}) returns degrees instead of meters.",
                )

        # Track is_valid checks
        elif node.attr == "is_valid":
            rname = _root_name(node.value)
            if rname:
                self.validated_vars.add(rname)

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # G028: Fragile string slicing on str(gdf.crs)[...]
        if isinstance(node.value, ast.Call) and _call_name(node.value) == "str":
            if node.value.args and isinstance(node.value.args[0], ast.Attribute) and node.value.args[0].attr == "crs":
                self._emit("G028", node)

        # G019: Invented schema field when contract provides dataset schema
        if self.contract is not None and self._contract_fields:
            col = _extract_const_str(node.slice)
            rname = _root_name(node.value)
            if (
                col
                and rname
                and rname in {d.name for d in self.contract.datasets}
                and col != "geometry"
                and col not in self._contract_fields
                and col not in self.derived_columns
            ):
                # Skip if this subscript is the LHS target of an assignment
                self._emit(
                    "G019",
                    node,
                    f"Column '{col}' on dataset '{rname}' is not in contract schema {sorted(self._contract_fields)}.",
                )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        cname = _call_name(node)

        # Track output writes
        if cname in ("to_csv", "to_file", "to_parquet", "to_json", "dump", "write_text", "write"):
            self.has_output_write = True

        # Track aggregation on sjoin vars
        if cname in ("groupby", "agg", "size", "count"):
            rname = _root_name(node.func)
            if rname:
                self.aggregated_vars.add(rname)

        # G001: .buffer() on geographic CRS
        if cname == "buffer" and isinstance(node.func, ast.Attribute):
            crs = self._resolve_expr_crs(node.func.value)
            if _is_geographic_crs(crs):
                self._emit(
                    "G001",
                    node,
                    f"Calling .buffer() on geographic CRS ({crs}) treats distance units as degrees.",
                )

        # G004 & G007: .distance() on geographic CRS or violating network_distance_required
        elif cname == "distance" and isinstance(node.func, ast.Attribute):
            crs = self._resolve_expr_crs(node.func.value)
            if _is_geographic_crs(crs):
                self._emit(
                    "G004",
                    node,
                    f"Calling .distance() on geographic CRS ({crs}) computes Euclidean degrees.",
                )
            if self.has_graph_context or (
                self.contract is not None and self.contract.has_constraint("network_distance_required")
            ):
                self._emit(
                    "G007",
                    node,
                    "Direct geometry .distance() used when road-network shortest-path distance is required.",
                )

        # G005, G012, G013, G023, G024: gpd.sjoin(...)
        elif cname == "sjoin":
            if _kw_arg(node, "op") is not None:
                self._emit("G023", node)

            if len(node.args) >= 2:
                left_crs = self._resolve_expr_crs(node.args[0])
                right_crs = self._resolve_expr_crs(node.args[1])
                if left_crs and right_crs and left_crs != right_crs:
                    self._emit(
                        "G005",
                        node,
                        f"gpd.sjoin() called with misaligned CRS: left={left_crs}, right={right_crs}.",
                    )

                pred_node = _kw_arg(node, "predicate") or _kw_arg(node, "op")
                pred = _extract_const_str(pred_node)
                left_kind = self._resolve_expr_kind(node.args[0])
                right_kind = self._resolve_expr_kind(node.args[1])
                # G013: Point contains Polygon or Polygon within Point
                if (left_kind == "point" and right_kind == "polygon" and pred == "contains") or (
                    left_kind == "polygon" and right_kind == "point" and pred == "within"
                ):
                    self._emit(
                        "G013",
                        node,
                        f"Inverted spatial predicate '{pred}' for ({left_kind}, {right_kind}) in sjoin().",
                    )
                # G024: boundary_predicate_explicit violated by within
                if pred == "within" and self.contract is not None:
                    bc = self.contract.get_constraint("boundary_predicate_explicit")
                    if bc and bc.params.get("predicate") in ("intersects", "covers"):
                        self._emit(
                            "G024",
                            node,
                            f"Contract requires boundary-inclusive predicate '{bc.params['predicate']}', got 'within'.",
                        )

            how_str = _extract_const_str(_kw_arg(node, "how"))
            if how_str == "inner":
                if self.contract is None or self.contract.has_constraint("one_output_row_per_source"):
                    self._emit("G012", node)

        # G006 & G022: gpd.overlay(...)
        elif cname == "overlay":
            if len(node.args) >= 2:
                c1 = self._resolve_expr_crs(node.args[0])
                c2 = self._resolve_expr_crs(node.args[1])
                if c1 and c2 and c1 != c2:
                    self._emit(
                        "G006",
                        node,
                        f"gpd.overlay() called with misaligned CRS: left={c1}, right={c2}.",
                    )
                if self.contract is not None and self.contract.has_constraint("valid_geometry_required"):
                    n1 = _root_name(node.args[0])
                    n2 = _root_name(node.args[1])
                    if (n1 and n1 not in self.validated_vars) or (n2 and n2 not in self.validated_vars):
                        self._emit("G022", node)

        # G007: sjoin_nearest under network contract
        elif cname == "sjoin_nearest":
            if self.contract is not None and self.contract.has_constraint("network_distance_required"):
                self._emit("G007", node)

        # G008 & G027: Raster reduction without NoData mask or on display-only layer
        elif cname in ("mean", "sum", "min", "max", "std", "median"):
            target_expr: ast.AST | None = None
            if isinstance(node.func, ast.Attribute):
                target_expr = node.func.value
            elif node.args:
                target_expr = node.args[0]

            if target_expr is not None:
                # Check if direct unmasked raw raster array (not subscripted with mask)
                if isinstance(target_expr, ast.Name) and target_expr.id in self.raw_raster_arrays:
                    if target_expr.id not in self.masked_raster_arrays:
                        self._emit(
                            "G008",
                            node,
                            f"Calling .{cname}() on raw raster array '{target_expr.id}' without NoData masking.",
                        )
                kind = self._resolve_expr_kind(target_expr)
                if kind == "display_only":
                    self._emit(
                        "G027",
                        node,
                        f"Statistical operation '{cname}' attempted on display-only layer.",
                    )

        # G009: Point(lat, lon) axis swap
        elif cname == "Point" and len(node.args) >= 2:
            a0, a1 = node.args[0], node.args[1]
            n0, n1 = _root_name(a0), _root_name(a1)
            if n0 and n1 and ("lat" in n0.lower() and ("lon" in n1.lower() or "lng" in n1.lower())):
                self._emit("G009", node, f"Point({n0}, {n1}) passes latitude before longitude.")
            else:
                v0, v1 = _extract_const_num(a0), _extract_const_num(a1)
                if v0 is not None and v1 is not None:
                    # |lat| <= 90 and |lon| > 90 strongly indicates (lat, lon) swap
                    if abs(v0) <= 90.0 and 90.0 < abs(v1) <= 180.0:
                        self._emit("G009", node, f"Point({v0}, {v1}) likely swaps (lat, lon) order.")

        # G011: Brittle float cast on ID column
        elif cname == "astype" and isinstance(node.func, ast.Attribute):
            arg0 = node.args[0] if node.args else None
            is_float = (isinstance(arg0, ast.Name) and arg0.id == "float") or (
                _extract_const_str(arg0) in ("float", "float32", "float64")
            )
            if is_float and isinstance(node.func.value, ast.Subscript):
                col = _extract_const_str(node.func.value.slice)
                if col and _ID_COL_RE.search(col):
                    self._emit("G011", node, f"Casting ID column '{col}' to float risks key drift.")

        # G013 & G015: Direct .within() / .contains() / .centroid.within()
        elif cname in ("within", "contains", "intersects") and isinstance(node.func, ast.Attribute):
            # G015: centroid proxy for polygon overlay
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "centroid":
                if cname in ("within", "intersects"):
                    self._emit("G015", node)
            # G013: polygons.within(points) or points.contains(polygons)
            if node.args:
                lk = self._resolve_expr_kind(node.func.value)
                rk = self._resolve_expr_kind(node.args[0])
                if (lk == "polygon" and rk == "point" and cname == "within") or (
                    lk == "point" and rk == "polygon" and cname == "contains"
                ):
                    self._emit("G013", node, f"Inverted geometry predicate: {lk}.{cname}({rk}).")

        # G016: Slope before resample
        elif cname in ("resample", "reproject", "raster_reproject"):
            if node.args:
                a0 = node.args[0]
                if _expr_contains_call(a0, {"slope", "gdaldem"}) or (
                    isinstance(a0, ast.Name) and a0.id in self.slope_vars
                ):
                    self._emit("G016", node)

            # G017: Wrong resampling method for data kind
            method_node = _kw_arg(node, "resampling") or _kw_arg(node, "method")
            method_str = (_extract_const_str(method_node) or "").lower()
            if method_str and node.args:
                kind = self._resolve_expr_kind(node.args[0])
                if kind == "continuous_raster" and method_str in ("nearest", "mode"):
                    self._emit("G017", node, f"Resampling method '{method_str}' is unsuitable for continuous raster.")
                elif kind == "categorical_raster" and method_str in ("bilinear", "cubic", "lanczos", "average"):
                    self._emit("G017", node, f"Resampling method '{method_str}' corrupts categorical raster classes.")

        # G025: Slope computed on geographic CRS raster
        elif cname in ("slope", "gdaldem"):
            if node.args:
                crs = self._resolve_expr_crs(node.args[0])
                if _is_geographic_crs(crs):
                    self._emit("G025", node, f"Slope computed on geographic CRS raster ({crs}).")

        # G018: set_crs(allow_override=True) instead of to_crs()
        elif cname == "set_crs":
            ov = _kw_arg(node, "allow_override")
            if isinstance(ov, ast.Constant) and ov.value is True:
                self._emit("G018", node)

        # G018: subprocess/command using -a_srs instead of gdalwarp -t_srs
        elif cname in ("run", "check_call", "Popen", "system"):
            for arg in node.args:
                s = _extract_const_str(arg)
                if s and "-a_srs" in s and "gdalwarp" not in s:
                    self._emit("G018", node, "Using '-a_srs' assigns CRS metadata without reprojecting coordinates.")
                elif isinstance(arg, (ast.List, ast.Tuple)):
                    elts = [_extract_const_str(e) or "" for e in arg.elts]
                    if "-a_srs" in elts and "gdalwarp" not in " ".join(elts):
                        self._emit("G018", node, "Using '-a_srs' assigns CRS metadata without reprojecting coordinates.")

        # G027: zonal_stats / raster_stats on display-only layer
        elif cname in ("zonal_stats", "raster_stats"):
            for arg in node.args:
                if self._resolve_expr_kind(arg) == "display_only":
                    self._emit("G027", node)

        self.generic_visit(node)


def lint_code(
    source: str,
    *,
    file_path: str = "<string>",
    contract: GeoContract | None = None,
) -> list[LintFinding]:
    """Lint Python source code string and return sorted geographic findings."""
    return SpatialASTAnalyzer(source, file_path=file_path, contract=contract).analyze()


def lint_file(path: str | Path, *, contract: GeoContract | None = None) -> list[LintFinding]:
    """Lint a Python file on disk."""
    p = Path(path)
    return lint_code(p.read_text(encoding="utf-8"), file_path=str(p), contract=contract)
