"""Rule definitions for ``geolint`` static AST spatial code linter (D2-P2).

Defines 28 geographic anti-pattern rules (G001–G028) grounded in GeoContra
(arXiv:2605.00782v1), GISAgentBench (arXiv:2608.01645v1), and GeoNatureAgent
(arXiv:2606.12821).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LintRule:
    rule_id: str
    slug: str
    title: str
    severity: str  # "error" | "warning"
    category: str
    description: str
    suggested_fix: str
    provenance: str


@dataclass
class LintFinding:
    rule_id: str
    slug: str
    severity: str
    line: int
    col: int
    message: str
    suggested_fix: str
    file_path: str = "<string>"

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "slug": self.slug,
            "severity": self.severity,
            "file_path": self.file_path,
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
        }


RULES: dict[str, LintRule] = {
    r.rule_id: r
    for r in [
        LintRule(
            "G001",
            "buffer-on-geographic-crs",
            "Buffer called on geographic CRS (degrees treated as meters)",
            "error",
            "crs",
            "Calling .buffer() on EPSG:4326 / geographic coordinates interprets metric radii as degrees.",
            "Reproject to a metric projected CRS via .to_crs('EPSG:3857') or local UTM before calling .buffer().",
            "GeoContra A01",
        ),
        LintRule(
            "G002",
            "area-on-geographic-crs",
            "Area computed on geographic CRS (square degrees)",
            "error",
            "crs",
            "Accessing .area on a geographic CRS returns square degrees rather than square meters.",
            "Reproject to an equal-area or local projected CRS via .to_crs(...) before computing .area.",
            "GeoContra A01",
        ),
        LintRule(
            "G003",
            "length-on-geographic-crs",
            "Length computed on geographic CRS (degrees)",
            "error",
            "crs",
            "Accessing .length on a geographic CRS returns degrees rather than meters.",
            "Reproject to a metric projected CRS via .to_crs(...) before computing .length.",
            "GeoContra A01",
        ),
        LintRule(
            "G004",
            "distance-on-geographic-crs",
            "Distance computed on geographic CRS (degrees)",
            "error",
            "crs",
            "Calling .distance() on geographic coordinates yields Euclidean degrees instead of meters.",
            "Reproject both geometries to a metric projected CRS or use geodesic distance (pyproj.Geod).",
            "GeoContra A01",
        ),
        LintRule(
            "G005",
            "unaligned-crs-sjoin",
            "Spatial join (sjoin) with unaligned CRS",
            "error",
            "crs",
            "Calling gpd.sjoin(left, right) on layers with different CRS silently produces empty or misaligned joins.",
            "Align CRS explicitly before sjoin: gpd.sjoin(left, right.to_crs(left.crs), ...).",
            "GeoContra A04",
        ),
        LintRule(
            "G006",
            "unaligned-crs-overlay",
            "Spatial overlay with unaligned CRS",
            "error",
            "crs",
            "Calling gpd.overlay(df1, df2) with mismatched CRS causes invalid or empty overlay outputs.",
            "Align CRS via df2.to_crs(df1.crs) in a projected CRS before calling gpd.overlay().",
            "GeoContra A04",
        ),
        LintRule(
            "G007",
            "euclidean-instead-of-network",
            "Euclidean geometry distance used instead of road-network distance",
            "error",
            "network",
            "Using .distance() or sjoin_nearest() violates network_distance_required when a road graph is required.",
            "Use graph routing (nearest_nodes + shortest_path / shortest_path_length) on the street network.",
            "GeoContra A02",
        ),
        LintRule(
            "G008",
            "nodata-unmasked-reduction",
            "Raster reduction without NoData masking",
            "error",
            "raster",
            "Computing .mean()/.sum()/.min()/.max() on rasterio .read() without masked=True or nodata filtering corrupts stats.",
            "Pass masked=True to src.read(1, masked=True) or filter arr[arr != src.nodata] before reducing.",
            "GeoContra A05 / GISAgentBench",
        ),
        LintRule(
            "G009",
            "lat-lon-axis-swapped",
            "Suspected (lat, lon) axis order inversion in Point(x, y)",
            "error",
            "coordinates",
            "Shapely Point(x, y) expects (longitude, latitude); passing (lat, lon) places points in the wrong hemisphere.",
            "Swap arguments to Point(lon, lat) / Point(x, y).",
            "GeoContract Coordinate Guard",
        ),
        LintRule(
            "G010",
            "unclipped-buffer-area",
            "Buffer area computed without clipping to boundary",
            "error",
            "boundary",
            "Computing .area directly on .buffer() violates clip_to_boundary by counting area outside the study polygon.",
            "Clip buffers to the containing boundary via gpd.clip(bufs, boundary) or .intersection(boundary.unary_union).",
            "GISAgentBench B12",
        ),
        LintRule(
            "G011",
            "brittle-id-float-cast",
            "Brittle float cast on identifier column",
            "error",
            "schema",
            "Casting an ID column to float (.astype(float)) introduces floating-point drift (e.g. '1' vs '1.0').",
            "Preserve ID columns as string or nullable integer (Int64) rather than float.",
            "GeoContra A10",
        ),
        LintRule(
            "G012",
            "inner-sjoin-drops-zeros",
            "Inner spatial join drops zero-match source features",
            "error",
            "completeness",
            "Using how='inner' in gpd.sjoin discards source rows with zero matches, violating one_output_row_per_source.",
            "Use how='left' in gpd.sjoin and fill unmatched counts with 0.",
            "GeoContra A08",
        ),
        LintRule(
            "G013",
            "inverted-point-polygon-predicate",
            "Point-polygon spatial predicate direction inverted",
            "error",
            "predicate",
            "Using predicate='contains' with points on the left and polygons on the right (or polygons.within(points)) is inverted.",
            "Use predicate='within' for (points, polygons) or swap operand order to (polygons, points, predicate='contains').",
            "GeoContra A07",
        ),
        LintRule(
            "G014",
            "plain-sjoin-missing-aggregation",
            "Plain spatial join without required groupby aggregation",
            "warning",
            "aggregation",
            "Exporting raw sjoin output without aggregating back to source IDs inflates row count.",
            "Aggregate joined results via .groupby(source_id).size() or .agg(...) before exporting.",
            "GISAgentBench B03",
        ),
        LintRule(
            "G015",
            "centroid-proxy-for-polygon-overlay",
            "Centroid shortcut used instead of polygon overlay/intersection",
            "warning",
            "semantics",
            "Testing .centroid.within(...) misses partial polygon overlaps in floodplain/zone exposure tasks.",
            "Use polygon .intersects(...) or gpd.overlay(..., how='intersection') for areal exposure.",
            "GeoContra A12",
        ),
        LintRule(
            "G016",
            "slope-before-resample",
            "Raster resampled after computing slope (wrong operation order)",
            "error",
            "order",
            "Computing slope on coarse DEM before resampling distorts terrain derivatives.",
            "Reproject and resample the DEM to target resolution first, then compute slope.",
            "GISAgentBench B02",
        ),
        LintRule(
            "G017",
            "wrong-resampling-method",
            "Resampling algorithm mismatches raster data kind",
            "error",
            "raster",
            "Using nearest on continuous elevation/temperature or bilinear/cubic on categorical land-cover corrupts values.",
            "Use bilinear/cubic for continuous rasters and nearest/mode for categorical rasters.",
            "GISAgentBench B09",
        ),
        LintRule(
            "G018",
            "assign-srs-instead-of-reproject",
            "Overwriting CRS metadata (set_crs allow_override / -a_srs) instead of reprojecting",
            "error",
            "crs",
            "Overriding CRS metadata does not transform coordinates and corrupts spatial alignment.",
            "Use .to_crs(target_crs) or gdalwarp -t_srs to actually reproject coordinates.",
            "GDAL / GeoContract CRS Guard",
        ),
        LintRule(
            "G019",
            "invented-schema-field",
            "Reference to column not present in contract dataset schema",
            "error",
            "schema",
            "Indexing a field absent from input dataset schemas and not locally derived risks KeyError or hallucinated attributes.",
            "Use only declared schema columns from the contract or explicitly compute derived columns first.",
            "GeoContra A06",
        ),
        LintRule(
            "G020",
            "missing-required-output-write",
            "Script never writes the contract-required output file",
            "error",
            "output",
            "Computing results in memory without writing to the contract output path causes silent task failure.",
            "Write the final result to the exact contract output path via .to_csv() / .to_file() / json.dump().",
            "GISAgentBench B11",
        ),
        LintRule(
            "G021",
            "filename-resolution-assumption",
            "Hardcoding raster resolution from filename instead of metadata header",
            "warning",
            "units",
            "Nominal resolution embedded in filenames often disagrees with the actual raster pixel grid.",
            "Read pixel resolution dynamically from dataset metadata (src.res or src.transform).",
            "GISAgentBench B07",
        ),
        LintRule(
            "G022",
            "overlay-without-geometry-validation",
            "Polygon overlay performed without prior geometry validation/repair",
            "warning",
            "topology",
            "Overlaying layers with self-intersections or slivers causes TopologyException or double-counted areas.",
            "Check .is_valid and repair via .make_valid() before calling gpd.overlay().",
            "GISAgentBench B06",
        ),
        LintRule(
            "G023",
            "deprecated-geopandas-op-arg",
            "Deprecated 'op=' keyword used in gpd.sjoin()",
            "error",
            "api",
            "GeoPandas 1.0+ removed the 'op=' parameter in sjoin in favor of 'predicate='.",
            "Replace op=... with predicate=... in gpd.sjoin().",
            "GeoContra §4.2 Stable API",
        ),
        LintRule(
            "G024",
            "ambiguous-boundary-within",
            "Predicate 'within' excludes features touching boundary",
            "warning",
            "boundary",
            "Contract specifies boundary-inclusive semantics, but predicate='within' drops boundary-touching features.",
            "Use predicate='intersects' or predicate='covers' per the contract boundary specification.",
            "GISAgentBench B05",
        ),
        LintRule(
            "G025",
            "geographic-raster-slope",
            "Slope computed on geographic CRS (EPSG:4326) DEM",
            "error",
            "raster",
            "Computing slope on a geographic DEM mixes degree horizontal units with meter vertical units.",
            "Reproject the DEM to a projected metric CRS (e.g., UTM) before computing slope.",
            "GISAgentBench B08",
        ),
        LintRule(
            "G026",
            "unchecked-negative-travel-time",
            "Travel time computed without non-negativity guard",
            "warning",
            "metrics",
            "Raw subtraction for travel_time / travel_min can yield negative values if timestamps or order are inverted.",
            "Assert non-negativity (df['travel_min'] >= 0).all() or validate arrival >= departure.",
            "GeoContra A03",
        ),
        LintRule(
            "G027",
            "display-layer-statistics",
            "Statistical computation attempted on display-only basemap layer",
            "error",
            "unsolvable",
            "Display-only tile/basemap layers cannot support quantitative spatial statistics; invoke reject_task.",
            "Reject quantitative requests over display-only layers via reject_task.",
            "GeoNatureAgent C02",
        ),
        LintRule(
            "G028",
            "fragile-crs-string-parsing",
            "Fragile string slicing on CRS object instead of .to_epsg()",
            "warning",
            "schema",
            "Parsing str(gdf.crs) via string slicing or int() fails on WKT2/PROJ strings.",
            "Use gdf.crs.to_epsg() or pyproj.CRS.from_user_input(...) for safe CRS inspection.",
            "GeoContra A10",
        ),
    ]
}


def list_rules() -> list[LintRule]:
    return [RULES[k] for k in sorted(RULES)]
