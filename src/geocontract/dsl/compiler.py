"""Natural-language intent to GeoContract skeleton compiler (D2-P1).

Deterministic, offline rule-based compiler that maps English or Chinese spatial
analysis prompts to strictly validated ``GeoContract`` skeletons grounded in
the 36-template library.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from geocontract.dsl.schema import (
    GeoContract,
    SpatialConstraint,
    validate_contract_dict,
)
from geocontract.dsl.templates import get_template

_FAMILY_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "network_accessibility",
        "tpl-net-shortest-path-time",
        (
            "road network", "street network", "shortest path", "travel time", "driving time",
            "walking time", "isochrone", "route", "路网", "通行时间", "最短路径", "可达性", "等时圈",
        ),
    ),
    (
        "zonal_statistics",
        "tpl-zonal-mean-continuous",
        (
            "zonal", "mean per", "average per", "by watershed", "by district", "by municipality",
            "分区统计", "区域均值", "每个行政区", "按流域",
        ),
    ),
    (
        "raster_sampling",
        "tpl-raster-reproject-before-slope",
        (
            "slope", "aspect", "dem", "resample", "elevation", "ndvi", "raster", "pixel",
            "坡度", "高程", "重采样", "栅格", "像元",
        ),
    ),
    (
        "overlay_areas",
        "tpl-overlay-flood-ratio",
        (
            "overlay", "floodplain", "intersect area", "area ratio", "fraction covered",
            "land use", "landuse", "dissolve", "symmetric difference",
            "叠加", "相交面积", "洪泛区", "面积占比", "土地利用",
        ),
    ),
    (
        "buffer_counting",
        "tpl-buffer-count-points",
        (
            "buffer", "within", "radius", "corridor", "缓冲", "半径", "范围内", "周围",
        ),
    ),
    (
        "nearest_neighbor",
        "tpl-nn-nearest-facility",
        (
            "nearest", "closest", "knn", "k-nearest", "最近", "邻近",
        ),
    ),
    (
        "topology_quality",
        "tpl-topo-validate-repair",
        (
            "topology", "self-intersect", "sliver", "invalid geometry", "repair geometry",
            "拓扑", "自相交", "狭长", "无效几何", "修复几何",
        ),
    ),
    (
        "spatial_joins",
        "tpl-sjoin-points-in-polygons",
        (
            "spatial join", "sjoin", "points in polygon", "inside polygon", "count per tract",
            "空间连接", "点面", "落入",
        ),
    ),
]

_DIST_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:(km|kilometers?|m|meters?|metres?|miles?|mi)\b|(米|公里|千米))", re.I)
_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:(min|mins|minutes?)\b|(分钟))", re.I)
_EPSG_RE = re.compile(r"EPSG:\d{4,5}", re.I)


def compile_intent_to_contract(
    query: str,
    *,
    contract_id: str | None = None,
    datasets: list[dict[str, Any]] | None = None,
    output_path: str | None = None,
) -> GeoContract:
    """Compile a natural-language geospatial query into a validated GeoContract skeleton."""
    q_clean = query.strip()
    if not q_clean:
        raise ValueError("Query must be a non-empty string")
    q_low = q_clean.lower()

    # 1. Select best-matching base template
    chosen_template = "tpl-workflow-site-suitability"
    matched_signals: list[str] = []
    best_score = 0
    for _fam, tpl_id, keywords in _FAMILY_RULES:
        hits = [kw for kw in keywords if kw in q_low]
        if len(hits) > best_score:
            best_score = len(hits)
            chosen_template = tpl_id
            matched_signals = hits

    # Refine template selection on sub-intent cues
    if chosen_template == "tpl-buffer-count-points" and any(
        w in q_low for w in ("clip", "boundary", "county", "city limit", "裁剪", "边界", "县界")
    ):
        chosen_template = "tpl-buffer-clipped-boundary"
    elif chosen_template == "tpl-raster-reproject-before-slope" and "slope" not in q_low and "坡度" not in q_low:
        if any(w in q_low for w in ("landcover", "land cover", "categorical", "nlcd", "分类")):
            chosen_template = "tpl-raster-sample-categorical"
        elif "ndvi" in q_low:
            chosen_template = "tpl-raster-ndvi-sample"
        else:
            chosen_template = "tpl-raster-sample-dem"

    contract = get_template(chosen_template)
    digest = hashlib.sha256(q_clean.encode("utf-8")).hexdigest()[:8]
    contract.contract_id = contract_id or f"gc-compiled-{digest}"
    contract.query = q_clean

    if output_path:
        contract.output.path = output_path

    # 2. Extract CRS hint if explicitly mentioned
    epsg_hits = [m.group(0).upper() for m in _EPSG_RE.finditer(q_clean)]
    if epsg_hits:
        for code in epsg_hits:
            if code != "EPSG:4326":
                contract.output.expected_crs = code
                break

    # 3. Extract distance or travel-time parameters
    dist_m = _DIST_RE.search(q_clean)
    if dist_m:
        val = float(dist_m.group(1))
        unit = (dist_m.group(2) or dist_m.group(3)).lower()
        if unit in ("km", "kilometer", "kilometers", "公里", "千米"):
            val_m = val * 1000.0
        elif unit in ("mi", "mile", "miles"):
            val_m = val * 1609.344
        else:
            val_m = val
        contract.metadata["extracted_distance_meters"] = val_m
        if not contract.has_constraint("crs_projected_required"):
            contract.constraints.append(
                SpatialConstraint("crs_projected_required", params={"unit": "meters"}, provenance="compiler")
            )

    time_m = _TIME_RE.search(q_clean)
    if time_m:
        contract.metadata["extracted_time_minutes"] = float(time_m.group(1))
        if not contract.has_constraint("travel_time_unit_minutes"):
            contract.constraints.append(
                SpatialConstraint("travel_time_unit_minutes", provenance="compiler")
            )

    # 4. Inject conditional guards from query cues
    if any(w in q_low for w in ("clip", "within county", "within boundary", "裁剪", "县内", "边界内")):
        if not contract.has_constraint("clip_to_boundary"):
            contract.constraints.append(
                SpatialConstraint("clip_to_boundary", provenance="geocontract_gisagentbench")
            )

    if any(w in q_low for w in ("compare", "higher than", "versus", "vs", "对比", "比较")):
        if not contract.has_constraint("close_value_epsilon_guard"):
            contract.constraints.append(
                SpatialConstraint("close_value_epsilon_guard", params={"epsilon": 0.5}, provenance="geonatureagent")
            )

    if any(w in q_low for w in ("if missing", "reject", "unavailable", "non-existent", "拒答", "不存在")):
        if not contract.has_constraint("reject_task"):
            contract.constraints.append(
                SpatialConstraint("reject_task", provenance="geobenchx_geonatureagent")
            )

    if any(w in q_low for w in ("preserve zero", "keep all", "all sources", "保留零匹配", "行数守恒")):
        if not contract.has_constraint("one_output_row_per_source"):
            contract.constraints.append(
                SpatialConstraint("one_output_row_per_source", provenance="geocontra")
            )

    if datasets:
        from geocontract.dsl.schema import DatasetSpec

        contract.datasets = [DatasetSpec.from_dict(d) for d in datasets]

    contract.metadata["compiled_from_template"] = chosen_template
    contract.metadata["matched_signals"] = matched_signals
    validate_contract_dict(contract.to_dict())
    return contract
