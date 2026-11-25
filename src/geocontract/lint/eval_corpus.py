"""Labeled positive/negative corpus for evaluating geolint recall and false-positive rate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geocontract.dsl.schema import GeoContract
from geocontract.dsl.templates import get_template
from geocontract.lint.analyzer import lint_code


@dataclass(frozen=True)
class LintCorpusSample:
    sample_id: str
    is_buggy: bool
    expected_rule: str | None
    code: str
    template_id: str | None = None


def build_eval_corpus() -> list[LintCorpusSample]:
    """Return 60 labeled samples (30 buggy positives across G001-G028 + 30 clean negatives)."""
    positives = [
        LintCorpusSample("POS-01", True, "G001", 'import geopandas as gpd\ng = gpd.read_file("schools.geojson")\nb = g.geometry.buffer(500)\n'),
        LintCorpusSample("POS-02", True, "G002", 'import geopandas as gpd\ng = gpd.read_file("tracts.geojson")\na = g.geometry.area\n'),
        LintCorpusSample("POS-03", True, "G003", 'import geopandas as gpd\ng = gpd.read_file("roads.geojson")\nl = g.geometry.length\n'),
        LintCorpusSample("POS-04", True, "G004", 'import geopandas as gpd\ng = gpd.read_file("pts.geojson")\nd = g.geometry.distance(g.geometry.iloc[0])\n'),
        LintCorpusSample("POS-05", True, "G005", 'import geopandas as gpd\na = gpd.read_file("a.geojson")\nb = gpd.read_file("b_3857.gpkg")\nr = gpd.sjoin(a, b, how="left", predicate="within")\n'),
        LintCorpusSample("POS-06", True, "G006", 'import geopandas as gpd\na = gpd.read_file("a.geojson")\nb = gpd.read_file("b_3857.gpkg")\nr = gpd.overlay(a, b, how="intersection")\n'),
        LintCorpusSample("POS-07", True, "G007", 'd = origins.geometry.distance(hospitals.geometry)\n', "tpl-net-shortest-path-time"),
        LintCorpusSample("POS-08", True, "G008", 'arr = src.read(1)\nm = arr.mean()\n'),
        LintCorpusSample("POS-09", True, "G009", 'from shapely.geometry import Point\np = Point(lat, lon)\n'),
        LintCorpusSample("POS-10", True, "G009", 'from shapely.geometry import Point\np = Point(42.36, -71.06)\n'),
        LintCorpusSample("POS-11", True, "G010", 'proj = points.to_crs("EPSG:3857")\nbufs = proj.buffer(500)\na = bufs.area\n', "tpl-buffer-clipped-boundary"),
        LintCorpusSample("POS-12", True, "G011", 'df["tract_id"] = df["tract_id"].astype(float)\n'),
        LintCorpusSample("POS-13", True, "G012", 'r = gpd.sjoin(sources, targets, how="inner", predicate="intersects")\n', "tpl-buffer-count-points"),
        LintCorpusSample("POS-14", True, "G013", 'r = gpd.sjoin(points, polygons, how="left", predicate="contains")\n'),
        LintCorpusSample("POS-15", True, "G013", 'r = polygons.within(points)\n'),
        LintCorpusSample("POS-16", True, "G014", 'j = gpd.sjoin(polygons, points.to_crs(polygons.crs), how="left", predicate="contains")\n', "tpl-sjoin-points-in-polygons"),
        LintCorpusSample("POS-17", True, "G015", 'inside = tracts.centroid.within(floodplain)\n'),
        LintCorpusSample("POS-18", True, "G016", 'sl = slope(dem_3857)\nres = resample(sl, method="bilinear")\n'),
        LintCorpusSample("POS-19", True, "G017", 'r = resample(dem, method="nearest")\n'),
        LintCorpusSample("POS-20", True, "G017", 'r = resample(nlcd, method="bilinear")\n'),
        LintCorpusSample("POS-21", True, "G018", 'g = g.set_crs("EPSG:3857", allow_override=True)\n'),
        LintCorpusSample("POS-22", True, "G018", 'import subprocess\nsubprocess.run(["gdal_edit.py", "-a_srs", "EPSG:3857", "a.tif"])\n'),
        LintCorpusSample("POS-23", True, "G019", 'x = polygons["pop_2099"]\n', "tpl-sjoin-points-in-polygons"),
        LintCorpusSample("POS-24", True, "G020", 'x = 1\ny = x + 2\n', "tpl-topo-schema-crs-audit"),
        LintCorpusSample("POS-25", True, "G021", 'dem = open("dem_30m.tif")\npixel_size = 30\n'),
        LintCorpusSample("POS-26", True, "G022", 'o = gpd.overlay(tracts.to_crs("EPSG:3857"), floodplain.to_crs("EPSG:3857"))\n', "tpl-overlay-flood-ratio"),
        LintCorpusSample("POS-27", True, "G023", 'r = gpd.sjoin(a, b, how="left", op="intersects")\n'),
        LintCorpusSample("POS-28", True, "G024", 'r = gpd.sjoin(features, boundary, how="left", predicate="within")\n', "tpl-sjoin-boundary-inclusive"),
        LintCorpusSample("POS-29", True, "G025", 'dem = open("dem_4326.tif")\ns = slope(dem)\n'),
        LintCorpusSample("POS-30", True, "G026", 'df["travel_min"] = (df["t_arr"] - df["t_dep"]) / 60\n'),
    ]

    negatives = [
        LintCorpusSample("NEG-01", False, None, 'import geopandas as gpd\ng = gpd.read_file("schools.geojson").to_crs("EPSG:3857")\nb = g.geometry.buffer(500)\n'),
        LintCorpusSample("NEG-02", False, None, 'import geopandas as gpd\ng = gpd.read_file("tracts.geojson").to_crs("EPSG:26986")\na = g.geometry.area\n'),
        LintCorpusSample("NEG-03", False, None, 'import geopandas as gpd\ng = gpd.read_file("roads.geojson").to_crs("EPSG:3857")\nl = g.geometry.length\n'),
        LintCorpusSample("NEG-04", False, None, 'import geopandas as gpd\ng = gpd.read_file("pts.geojson").to_crs("EPSG:3857")\nd = g.geometry.distance(g.geometry.iloc[0])\n'),
        LintCorpusSample("NEG-05", False, None, 'import geopandas as gpd\na = gpd.read_file("a.geojson")\nb = gpd.read_file("b_3857.gpkg").to_crs(a.crs)\nr = gpd.sjoin(a, b, how="left", predicate="within")\n'),
        LintCorpusSample("NEG-06", False, None, 'import geopandas as gpd\na = gpd.read_file("a_3857.gpkg")\nb = gpd.read_file("b_3857.gpkg")\nr = gpd.overlay(a, b, how="intersection")\n'),
        LintCorpusSample("NEG-07", False, None, 'G = load_graphml("streets.graphml")\nu = nearest_nodes(G, x, y)\nd = shortest_path_length(G, u, v, weight="length")\n', "tpl-net-shortest-path-time"),
        LintCorpusSample("NEG-08", False, None, 'arr = src.read(1, masked=True)\nm = arr.mean()\n'),
        LintCorpusSample("NEG-09", False, None, 'arr = src.read(1)\nvalid = arr[arr != src.nodata]\nm = valid.mean()\n'),
        LintCorpusSample("NEG-10", False, None, 'from shapely.geometry import Point\np = Point(lon, lat)\n'),
        LintCorpusSample("NEG-11", False, None, 'from shapely.geometry import Point\np = Point(-71.06, 42.36)\n'),
        LintCorpusSample("NEG-12", False, None, 'proj = points.to_crs("EPSG:3857")\nbnd = boundary.to_crs("EPSG:3857")\nbufs = proj.buffer(500)\nclipped = gpd.clip(bufs, bnd)\na = clipped.area\n', "tpl-buffer-clipped-boundary"),
        LintCorpusSample("NEG-13", False, None, 'df["tract_id"] = df["tract_id"].astype(str)\n'),
        LintCorpusSample("NEG-14", False, None, 'df["score"] = df["score"].astype(float)\n'),
        LintCorpusSample("NEG-15", False, None, 'r = gpd.sjoin(sources, targets, how="left", predicate="intersects")\ncounts = r.groupby("source_id").size()\n', "tpl-buffer-count-points"),
        LintCorpusSample("NEG-16", False, None, 'r = gpd.sjoin(points, polygons, how="left", predicate="within")\n'),
        LintCorpusSample("NEG-17", False, None, 'r = gpd.sjoin(polygons, points, how="left", predicate="contains")\n'),
        LintCorpusSample("NEG-18", False, None, 'j = gpd.sjoin(polygons, points.to_crs(polygons.crs), how="left", predicate="contains")\ncounts = j.groupby("tract_id").size()\ncounts.to_csv("out/tract_counts.csv")\n', "tpl-sjoin-points-in-polygons"),
        LintCorpusSample("NEG-19", False, None, 'inside = tracts.intersects(floodplain)\n'),
        LintCorpusSample("NEG-20", False, None, 'dem_p = raster_reproject(dem, target_crs="EPSG:32619", resampling="bilinear")\nsl = slope(dem_p)\n'),
        LintCorpusSample("NEG-21", False, None, 'r = resample(dem, method="bilinear")\n'),
        LintCorpusSample("NEG-22", False, None, 'r = resample(nlcd, method="nearest")\n'),
        LintCorpusSample("NEG-23", False, None, 'g = g.to_crs("EPSG:3857")\n'),
        LintCorpusSample("NEG-24", False, None, 'import subprocess\nsubprocess.run(["gdalwarp", "-t_srs", "EPSG:3857", "a.tif", "b.tif"])\n'),
        LintCorpusSample("NEG-25", False, None, 'x = polygons["tract_id"]\n', "tpl-sjoin-points-in-polygons"),
        LintCorpusSample("NEG-26", False, None, 'df = layer[["feature_id", "label"]]\ndf.to_csv("out/audited.csv")\n', "tpl-topo-schema-crs-audit"),
        LintCorpusSample("NEG-27", False, None, 'dem = open("dem_30m.tif")\npixel_size = dem.res[0]\n'),
        LintCorpusSample("NEG-28", False, None, 't = tracts.to_crs("EPSG:3857").make_valid()\nf = floodplain.to_crs("EPSG:3857").make_valid()\no = gpd.overlay(t, f)\n', "tpl-overlay-flood-ratio"),
        LintCorpusSample("NEG-29", False, None, 'r = gpd.sjoin(features, boundary, how="left", predicate="intersects")\n', "tpl-sjoin-boundary-inclusive"),
        LintCorpusSample("NEG-30", False, None, 'df["travel_min"] = (df["t_arr"] - df["t_dep"]) / 60\nassert (df["travel_min"] >= 0).all()\n'),
    ]
    return positives + negatives


def evaluate_geolint_corpus() -> dict[str, Any]:
    """Run geolint over the 60-sample labeled corpus and compute recall & FPR."""
    corpus = build_eval_corpus()
    tp = fn = fp = tn = 0
    details: list[dict[str, Any]] = []

    for s in corpus:
        contract: GeoContract | None = get_template(s.template_id) if s.template_id else None
        findings = lint_code(s.code, file_path=f"{s.sample_id}.py", contract=contract)
        found_ids = {f.rule_id for f in findings}
        if s.is_buggy:
            hit = s.expected_rule in found_ids
            if hit:
                tp += 1
            else:
                fn += 1
            details.append({"id": s.sample_id, "label": "pos", "expected": s.expected_rule, "found": sorted(found_ids), "ok": hit})
        else:
            clean = len(findings) == 0
            if clean:
                tn += 1
            else:
                fp += 1
            details.append({"id": s.sample_id, "label": "neg", "expected": None, "found": sorted(found_ids), "ok": clean})

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return {
        "total": len(corpus),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "precision": round(precision, 4),
        "details": details,
    }
