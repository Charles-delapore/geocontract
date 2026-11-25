"""Adversarial Geographic Near-Miss Benchmark Suite: 160 structured cases (D2-P7).

Grounded in the 34 anti-pattern classes collected in Muse Wave 1
``NEAR_MISS_CASES/near_miss_cases.md`` (GeoContra A01–A12, GISAgentBench B01–B12,
GeoNatureAgent C01–C05, Axis Spatial D01–D05).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NearMissCase:
    case_id: str
    category: str
    source_class: str
    difficulty: str  # "easy" | "medium" | "hard"
    kind: str  # "static_code" | "runtime_reject" | "runtime_close_value"
    description: str
    template_id: str | None
    expected_guard: str
    bare_code: str = ""
    repaired_code: str = ""
    runtime_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "source_class": self.source_class,
            "difficulty": self.difficulty,
            "kind": self.kind,
            "description": self.description,
            "template_id": self.template_id,
            "expected_guard": self.expected_guard,
        }


def build_near_miss_suite() -> list[NearMissCase]:
    """Construct 160 structured adversarial Near-Miss benchmark cases (16 categories x 10 variants)."""
    cases: list[NearMissCase] = []
    idx = 0

    def _next_id(prefix: str) -> str:
        nonlocal idx
        idx += 1
        return f"NM-{idx:03d}-{prefix}"

    # 1. Degree/meter buffer confusion (A01) — 10 variants
    radii = [100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000, 10000]
    proj_epsgs = ["EPSG:3857", "EPSG:26986", "EPSG:32619", "EPSG:32610", "EPSG:3035", "EPSG:27700", "EPSG:2154", "EPSG:5070", "EPSG:32618", "EPSG:25832"]
    for i, (r, epsg) in enumerate(zip(radii, proj_epsgs)):
        cases.append(
            NearMissCase(
                case_id=_next_id("BUF4326"),
                category="degree_meter_buffer",
                source_class="A01",
                difficulty="easy" if i < 4 else "medium",
                kind="static_code",
                description=f"Buffer {r}m directly on EPSG:4326 points instead of projecting to {epsg}.",
                template_id="tpl-buffer-count-points",
                expected_guard="G001",
                bare_code=(
                    f'import geopandas as gpd\n'
                    f'sources = gpd.read_file("sources_{i}.geojson")\n'
                    f'bufs = sources.geometry.buffer({r})\n'
                    f'res = gpd.sjoin(sources, targets.to_crs(sources.crs), how="left", predicate="intersects").groupby("source_id").size()\n'
                    f'res.to_csv("out/buffer_counts.csv")\n'
                ),
                repaired_code=(
                    f'import geopandas as gpd\n'
                    f'sources = gpd.read_file("sources_{i}.geojson").to_crs("{epsg}")\n'
                    f'bufs = sources.geometry.buffer({r})\n'
                    f'res = gpd.sjoin(sources, targets.to_crs("{epsg}"), how="left", predicate="intersects").groupby("source_id").size()\n'
                    f'res.to_csv("out/buffer_counts.csv")\n'
                ),
            )
        )

    # 2. Geographic CRS area/length computation (A01) — 10 variants
    for i, epsg in enumerate(proj_epsgs):
        op = "area" if i % 2 == 0 else "length"
        rule = "G002" if op == "area" else "G003"
        cases.append(
            NearMissCase(
                case_id=_next_id("GEOM4326"),
                category="degree_area_length",
                source_class="A01",
                difficulty="easy",
                kind="static_code",
                description=f"Compute .{op} directly on EPSG:4326 layer instead of {epsg}.",
                template_id=None,
                expected_guard=rule,
                bare_code=f'import geopandas as gpd\nlayer = gpd.read_file("layer_{i}.geojson")\nm = layer.geometry.{op}\n',
                repaired_code=f'import geopandas as gpd\nlayer = gpd.read_file("layer_{i}.geojson").to_crs("{epsg}")\nm = layer.geometry.{op}\n',
            )
        )

    # 3. Unaligned CRS sjoin (A04) — 10 variants
    for i, epsg in enumerate(proj_epsgs):
        cases.append(
            NearMissCase(
                case_id=_next_id("SJOINCRS"),
                category="crs_mismatch_sjoin",
                source_class="A04",
                difficulty="medium",
                kind="static_code",
                description=f"gpd.sjoin between EPSG:4326 polygons and {epsg} points without alignment.",
                template_id="tpl-sjoin-points-in-polygons",
                expected_guard="G005",
                bare_code=(
                    f'import geopandas as gpd\n'
                    f'polygons = gpd.read_file("tracts_{i}.geojson")\n'
                    f'points = gpd.read_file("pts_{i}_3857.gpkg")\n'
                    f'joined = gpd.sjoin(polygons, points, how="left", predicate="contains")\n'
                    f'counts = joined.groupby("tract_id").size()\n'
                    f'counts.to_csv("out/tract_counts.csv")\n'
                ),
                repaired_code=(
                    f'import geopandas as gpd\n'
                    f'polygons = gpd.read_file("tracts_{i}.geojson").to_crs("{epsg}")\n'
                    f'points = gpd.read_file("pts_{i}_3857.gpkg").to_crs("{epsg}")\n'
                    f'joined = gpd.sjoin(polygons, points, how="left", predicate="contains")\n'
                    f'counts = joined.groupby("tract_id").size()\n'
                    f'counts.to_csv("out/tract_counts.csv")\n'
                ),
            )
        )

    # 4. Unaligned CRS overlay (A04) — 10 variants
    for i, epsg in enumerate(proj_epsgs):
        cases.append(
            NearMissCase(
                case_id=_next_id("OVLYCRS"),
                category="crs_mismatch_overlay",
                source_class="A04",
                difficulty="medium",
                kind="static_code",
                description=f"gpd.overlay between EPSG:4326 tracts and {epsg} floodplain without CRS alignment.",
                template_id="tpl-overlay-flood-ratio",
                expected_guard="G006",
                bare_code=(
                    f'import geopandas as gpd\n'
                    f'tracts = gpd.read_file("tracts_{i}.geojson").make_valid()\n'
                    f'floodplain = gpd.read_file("fp_{i}_3857.gpkg").make_valid()\n'
                    f'ov = gpd.overlay(tracts, floodplain, how="intersection")\n'
                    f'ov.to_csv("out/flood_exposure.csv")\n'
                ),
                repaired_code=(
                    f'import geopandas as gpd\n'
                    f'tracts = gpd.read_file("tracts_{i}.geojson").to_crs("{epsg}").make_valid()\n'
                    f'floodplain = gpd.read_file("fp_{i}_3857.gpkg").to_crs("{epsg}").make_valid()\n'
                    f'ov = gpd.overlay(tracts, floodplain, how="intersection")\n'
                    f'ov.to_csv("out/flood_exposure.csv")\n'
                ),
            )
        )

    # 5. Unclipped buffer across boundary (B12 / D01) — 10 variants
    for i, r in enumerate(radii):
        cases.append(
            NearMissCase(
                case_id=_next_id("UNCLIP"),
                category="unclipped_boundary_buffer",
                source_class="B12",
                difficulty="hard",
                kind="static_code",
                description=f"Compute {r}m buffer area without clipping to containing polygon boundary.",
                template_id="tpl-buffer-clipped-boundary",
                expected_guard="G010",
                bare_code=(
                    f'import geopandas as gpd\n'
                    f'proj = points.to_crs("EPSG:3857")\n'
                    f'bnd = boundary.to_crs("EPSG:3857")\n'
                    f'bufs = proj.buffer({r})\n'
                    f'areas = bufs.area\n'
                    f'areas.to_csv("out/clipped_buffers.geojson")\n'
                ),
                repaired_code=(
                    f'import geopandas as gpd\n'
                    f'proj = points.to_crs("EPSG:3857")\n'
                    f'bnd = boundary.to_crs("EPSG:3857")\n'
                    f'bufs = proj.buffer({r})\n'
                    f'clipped = gpd.clip(bufs, bnd)\n'
                    f'areas = clipped.area\n'
                    f'areas.to_csv("out/clipped_buffers.geojson")\n'
                ),
            )
        )

    # 6. Euclidean distance shortcut instead of road network (A02) — 10 variants
    for i in range(10):
        cases.append(
            NearMissCase(
                case_id=_next_id("NETSHORT"),
                category="euclidean_network_shortcut",
                source_class="A02",
                difficulty="hard",
                kind="static_code",
                description=f"Use direct geometry .distance() instead of shortest_path on road graph (variant {i}).",
                template_id="tpl-net-shortest-path-time",
                expected_guard="G007",
                bare_code=(
                    f'orig = origins.to_crs("EPSG:3857")\n'
                    f'hosp = hospitals.to_crs("EPSG:3857")\n'
                    f'dist_{i} = orig.geometry.distance(hosp.geometry)\n'
                ),
                repaired_code=(
                    f'G = load_graphml("data/streets.graphml")\n'
                    f'u = nearest_nodes(G, ox_{i}, oy_{i})\n'
                    f'v = nearest_nodes(G, hx_{i}, hy_{i})\n'
                    f'dist_{i} = shortest_path_length(G, u, v, weight="length")\n'
                ),
            )
        )

    # 7. Unmasked NoData raster reduction (A05) — 10 variants
    reducers = ["mean", "sum", "min", "max", "std", "mean", "sum", "min", "max", "median"]
    for i, red in enumerate(reducers):
        cases.append(
            NearMissCase(
                case_id=_next_id("NODATA"),
                category="nodata_unmasked_stats",
                source_class="A05",
                difficulty="medium",
                kind="static_code",
                description=f"Compute raster .{red}() on unmasked array ignoring NoData values (variant {i}).",
                template_id=None,
                expected_guard="G008",
                bare_code=f'arr = src.read(1)\nval_{i} = arr.{red}()\n',
                repaired_code=f'arr = src.read(1, masked=True)\nval_{i} = arr.{red}()\n',
            )
        )

    # 8. Lat/Lon axis order swap (G009) — 10 real-world city coordinates
    cities = [
        ("San Francisco", 37.7749, -122.4194),
        ("Tokyo", 35.6762, 139.6503),
        ("Beijing", 39.9042, 116.4074),
        ("Sydney", -33.8688, 151.2093),
        ("Los Angeles", 34.0522, -118.2437),
        ("Seattle", 47.6062, -122.3321),
        ("Shanghai", 31.2304, 121.4737),
        ("Seoul", 37.5665, 126.9780),
        ("Melbourne", -37.8136, 144.9631),
        ("Singapore", 1.3521, 103.8198),
    ]
    for city, lat, lon in cities:
        cases.append(
            NearMissCase(
                case_id=_next_id("LATLON"),
                category="lat_lon_axis_swap",
                source_class="G009",
                difficulty="easy",
                kind="static_code",
                description=f"Point({lat}, {lon}) swaps (lat, lon) order for {city}.",
                template_id=None,
                expected_guard="G009",
                bare_code=f"from shapely.geometry import Point\np = Point({lat}, {lon})\n",
                repaired_code=f"from shapely.geometry import Point\np = Point({lon}, {lat})\n",
            )
        )

    # 9. Inverted point-polygon predicate (A07) — 10 variants
    for i in range(10):
        cases.append(
            NearMissCase(
                case_id=_next_id("PREDINV"),
                category="inverted_predicate_direction",
                source_class="A07",
                difficulty="medium",
                kind="static_code",
                description=f"Inverted point-polygon predicate 'contains' on (points, polygons) variant {i}.",
                template_id=None,
                expected_guard="G013",
                bare_code=f'r_{i} = gpd.sjoin(points, polygons, how="left", predicate="contains")\n',
                repaired_code=f'r_{i} = gpd.sjoin(points, polygons, how="left", predicate="within")\n',
            )
        )

    # 10. Inner sjoin dropping zero-match source rows (A08) — 10 variants
    for i in range(10):
        cases.append(
            NearMissCase(
                case_id=_next_id("INNERDROP"),
                category="inner_sjoin_zero_drop",
                source_class="A08",
                difficulty="medium",
                kind="static_code",
                description=f"Inner spatial join drops zero-match source features (variant {i}).",
                template_id="tpl-buffer-count-points",
                expected_guard="G012",
                bare_code=(
                    f'b = sources.to_crs("EPSG:3857").buffer(500)\n'
                    f'j = gpd.sjoin(b, targets.to_crs("EPSG:3857"), how="inner", predicate="intersects")\n'
                    f'c = j.groupby("source_id").size()\n'
                    f'c.to_csv("out/buffer_counts.csv")\n'
                ),
                repaired_code=(
                    f'b = sources.to_crs("EPSG:3857").buffer(500)\n'
                    f'j = gpd.sjoin(b, targets.to_crs("EPSG:3857"), how="left", predicate="intersects")\n'
                    f'c = j.groupby("source_id").size()\n'
                    f'c.to_csv("out/buffer_counts.csv")\n'
                ),
            )
        )

    # 11. Operation order error: slope before resample (B02) — 10 variants
    for i, res in enumerate([5, 10, 15, 20, 25, 30, 50, 60, 90, 100]):
        cases.append(
            NearMissCase(
                case_id=_next_id("SLOPEORD"),
                category="slope_before_resample",
                source_class="B02",
                difficulty="hard",
                kind="static_code",
                description=f"Compute slope before resampling DEM to {res}m resolution.",
                template_id="tpl-raster-reproject-before-slope",
                expected_guard="G016",
                bare_code=(
                    f'dem_p = raster_reproject(dem, target_crs="EPSG:32619", resampling="bilinear")\n'
                    f'sl = slope(dem_p)\n'
                    f'out_{i} = resample(sl, method="bilinear")\n'
                ),
                repaired_code=(
                    f'dem_p = raster_reproject(dem, target_crs="EPSG:32619", resampling="bilinear")\n'
                    f'dem_r = resample(dem_p, method="bilinear")\n'
                    f'out_{i} = slope(dem_r)\n'
                ),
            )
        )

    # 12. Resampling method mismatches raster data kind (B09) — 10 variants
    for i in range(10):
        if i % 2 == 0:
            bare = f'out_{i} = resample(dem, method="nearest")\n'
            fixed = f'out_{i} = resample(dem, method="bilinear")\n'
            desc = f"Nearest-neighbor resampling on continuous DEM (variant {i})."
        else:
            bare = f'out_{i} = resample(nlcd, method="bilinear")\n'
            fixed = f'out_{i} = resample(nlcd, method="nearest")\n'
            desc = f"Bilinear resampling on categorical NLCD land cover (variant {i})."
        cases.append(
            NearMissCase(
                case_id=_next_id("RESAMP"),
                category="wrong_resampling_method",
                source_class="B09",
                difficulty="medium",
                kind="static_code",
                description=desc,
                template_id=None,
                expected_guard="G017",
                bare_code=bare,
                repaired_code=fixed,
            )
        )

    # 13. Brittle ID float cast (A10) — 10 variants
    id_cols = ["tract_id", "parcel_id", "school_id", "stop_id", "zone_id", "fips", "geoid", "muni_id", "site_id", "cell_id"]
    for i, col in enumerate(id_cols):
        cases.append(
            NearMissCase(
                case_id=_next_id("IDCAST"),
                category="brittle_id_float_cast",
                source_class="A10",
                difficulty="easy",
                kind="static_code",
                description=f"Cast identifier column '{col}' to float causing join-key drift.",
                template_id=None,
                expected_guard="G011",
                bare_code=f'df["{col}"] = df["{col}"].astype(float)\n',
                repaired_code=f'df["{col}"] = df["{col}"].astype(str)\n',
            )
        )

    # 14. Unsolvable task refusal & bidirectional check (C02 / D02 / D03) — 10 variants (7 unsolvable + 3 solvable)
    for i in range(10):
        if i < 4:
            payload = {
                "requested_entities": [f"NonExistentTown_{i}"],
                "available_entities": ["Murcia", "Cordoba", "Sevilla"],
                "requested_indicators": ["green_pct"],
                "available_indicators": ["green_pct"],
                "target_layers": [{"name": "green_cover", "display_only": False, "crs": "EPSG:3035"}],
                "bare_rejected": False,
            }
            desc = f"Query requests non-existent municipality NonExistentTown_{i} (must reject_task)."
        elif i < 7:
            payload = {
                "requested_entities": ["Murcia"],
                "available_entities": ["Murcia", "Cordoba"],
                "requested_indicators": ["green_pct"],
                "available_indicators": ["green_pct"],
                "target_layers": [{"name": f"basemap_display_{i}", "display_only": True, "crs": "EPSG:3857"}],
                "bare_rejected": False,
            }
            desc = f"Query computes quantitative stats from display-only basemap_{i} (must reject_task)."
        else:
            # Bidirectional check: solvable task that an overly cautious baseline falsely rejects
            payload = {
                "requested_entities": ["Murcia"],
                "available_entities": ["Murcia", "Cordoba"],
                "requested_indicators": ["green_pct"],
                "available_indicators": ["green_pct"],
                "target_layers": [{"name": "green_cover", "display_only": False, "crs": "EPSG:3035"}],
                "bare_rejected": True,
            }
            desc = f"Solvable query falsely rejected by baseline (bidirectional refusal check {i})."
        cases.append(
            NearMissCase(
                case_id=_next_id("REJECT"),
                category="unsolvable_reject_task",
                source_class="C02" if i < 7 else "D03",
                difficulty="hard",
                kind="runtime_reject",
                description=desc,
                template_id="tpl-workflow-unsolvable-guard",
                expected_guard="reject_task",
                runtime_payload=payload,
            )
        )

    # 15. Close-value directional fabrication (C01) — 10 variants
    pairs = [
        (68.5, 68.4), (41.2, 41.0), (55.3, 55.5), (12.8, 12.6), (79.1, 79.4),
        (33.0, 32.8), (64.7, 64.9), (21.5, 21.2), (88.4, 88.1), (50.0, 50.3),
    ]
    for i, (va, vb) in enumerate(pairs):
        cases.append(
            NearMissCase(
                case_id=_next_id("CLOSEVAL"),
                category="close_value_directional_fabrication",
                source_class="C01",
                difficulty="hard",
                kind="runtime_close_value",
                description=f"Compare {va}% vs {vb}% (|diff|={abs(va-vb):.1f}pp <= 0.5pp) without fabricating directional claim.",
                template_id="tpl-zonal-close-value-compare",
                expected_guard="close_value_epsilon_guard",
                runtime_payload={
                    "value_a": va,
                    "value_b": vb,
                    "epsilon": 0.5,
                    "bare_claim": "higher" if va >= vb else "lower",
                    "repaired_claim": "effectively_equal",
                },
            )
        )

    # 16. Overlay without geometry validation (B06) — 10 variants
    for i, epsg in enumerate(proj_epsgs):
        cases.append(
            NearMissCase(
                case_id=_next_id("TOPOVAL"),
                category="invalid_geometry_overlay",
                source_class="B06",
                difficulty="hard",
                kind="static_code",
                description=f"Overlay dirty polygon layers in {epsg} without .make_valid() / .is_valid check.",
                template_id="tpl-overlay-flood-ratio",
                expected_guard="G022",
                bare_code=(
                    f't = tracts.to_crs("{epsg}")\n'
                    f'f = floodplain.to_crs("{epsg}")\n'
                    f'ov_{i} = gpd.overlay(t, f, how="intersection")\n'
                ),
                repaired_code=(
                    f't = tracts.to_crs("{epsg}").make_valid()\n'
                    f'f = floodplain.to_crs("{epsg}").make_valid()\n'
                    f'ov_{i} = gpd.overlay(t, f, how="intersection")\n'
                ),
            )
        )

    return cases
