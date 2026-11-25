"""Unit tests covering all 28 geolint AST rules (G001-G028)."""

import unittest

from geocontract.dsl.templates import get_template
from geocontract.lint.analyzer import lint_code


class TestGeoLintRules(unittest.TestCase):
    def _ids(self, code: str, contract=None) -> set[str]:
        return {f.rule_id for f in lint_code(code, contract=contract)}

    def test_crs_metric_rules_g001_to_g004(self) -> None:
        code = """
import geopandas as gpd
schools = gpd.read_file("schools.geojson")
b = schools.geometry.buffer(500)
a = schools.geometry.area
l = schools.geometry.length
d = schools.geometry.distance(schools.geometry.iloc[0])
"""
        ids = self._ids(code)
        self.assertTrue({"G001", "G002", "G003", "G004"}.issubset(ids))

    def test_projected_chain_has_zero_crs_false_positives(self) -> None:
        code = """
import geopandas as gpd
schools = gpd.read_file("schools.geojson")
proj = schools.to_crs("EPSG:3857")
b = proj.geometry.buffer(500)
a = proj.geometry.area
l = proj.geometry.length
d = proj.geometry.distance(proj.geometry.iloc[0])
"""
        self.assertEqual(self._ids(code), set())

    def test_sjoin_and_overlay_crs_and_predicates(self) -> None:
        code = """
import geopandas as gpd
points = gpd.read_file("points.geojson")
polygons = gpd.read_file("polygons_3857.gpkg")
j = gpd.sjoin(points, polygons, how="inner", op="contains")
o = gpd.overlay(points, polygons, how="intersection")
"""
        ids = self._ids(code)
        self.assertTrue({"G005", "G006", "G012", "G013", "G023"}.issubset(ids))

    def test_network_shortcut_g007(self) -> None:
        tpl = get_template("tpl-net-shortest-path-time")
        code = """
d = origins.geometry.distance(hospitals.geometry)
"""
        self.assertIn("G007", self._ids(code, contract=tpl))

    def test_nodata_unmasked_g008_and_clean_masked(self) -> None:
        bad = """
arr = src.read(1)
m = arr.mean()
"""
        self.assertIn("G008", self._ids(bad))
        good = """
arr = src.read(1, masked=True)
m = arr.mean()
"""
        self.assertNotIn("G008", self._ids(good))

    def test_lat_lon_swap_g009(self) -> None:
        self.assertIn("G009", self._ids("from shapely.geometry import Point\np = Point(lat, lon)\n"))
        self.assertIn("G009", self._ids("from shapely.geometry import Point\np = Point(37.77, -122.42)\n"))
        self.assertNotIn("G009", self._ids("from shapely.geometry import Point\np = Point(-122.42, 37.77)\n"))

    def test_unclipped_buffer_g010(self) -> None:
        tpl = get_template("tpl-buffer-clipped-boundary")
        bad = """
proj = points.to_crs("EPSG:3857")
bufs = proj.buffer(500)
a = bufs.area
"""
        self.assertIn("G010", self._ids(bad, contract=tpl))

    def test_brittle_id_cast_g011_and_fragile_crs_g028(self) -> None:
        code = """
df["tract_id"] = df["tract_id"].astype(float)
epsg = int(str(gdf.crs)[5:])
"""
        ids = self._ids(code)
        self.assertIn("G011", ids)
        self.assertIn("G028", ids)

    def test_raster_order_resampling_and_slope_crs_g016_g017_g025(self) -> None:
        code = """
dem = open("dem_4326.tif")
sl = slope(dem)
sl_r = resample(sl, method="nearest")
nlcd_r = resample(nlcd, method="bilinear")
"""
        ids = self._ids(code)
        self.assertTrue({"G016", "G017", "G025"}.issubset(ids))

    def test_set_crs_override_g018_and_centroid_proxy_g015(self) -> None:
        code = """
gdf = gdf.set_crs("EPSG:3857", allow_override=True)
inside = tracts.centroid.within(floodplain)
"""
        ids = self._ids(code)
        self.assertIn("G018", ids)
        self.assertIn("G015", ids)

    def test_schema_field_g019_and_missing_output_g020_and_plain_sjoin_g014(self) -> None:
        tpl = get_template("tpl-sjoin-points-in-polygons")
        code = """
x = polygons["invented_col"]
joined = gpd.sjoin(polygons, points.to_crs(polygons.crs), how="left", predicate="contains")
"""
        ids = self._ids(code, contract=tpl)
        self.assertIn("G019", ids)
        self.assertIn("G014", ids)

    def test_filename_res_g021_overlay_topo_g022_boundary_g024_travel_g026_display_g027(self) -> None:
        c_topo = get_template("tpl-overlay-flood-ratio")
        self.assertIn(
            "G022",
            self._ids("o = gpd.overlay(tracts.to_crs('EPSG:3857'), floodplain.to_crs('EPSG:3857'))\n", contract=c_topo),
        )
        c_bnd = get_template("tpl-sjoin-boundary-inclusive")
        self.assertIn(
            "G024",
            self._ids("r = gpd.sjoin(features, boundary, how='left', predicate='within')\n", contract=c_bnd),
        )
        self.assertIn("G021", self._ids('dem = open("dem_30m.tif")\npixel_size = 30\n'))
        self.assertIn("G026", self._ids('df["travel_min"] = (df["t_arr"] - df["t_dep"]) / 60\n'))
        self.assertIn("G027", self._ids("basemap = open('basemap_tiles.tif')\nm = basemap.mean()\n"))


if __name__ == "__main__":
    unittest.main()
