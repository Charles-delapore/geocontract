"""Built-in library of 36 standard GeoContract templates across 9 spatial analysis families.

Covers all 9 task families from GeoContra (arXiv:2605.00782v1 §5.1) with 4
strictly schema-validated templates per family (36 total).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from geocontract.dsl.schema import (
    VALID_FAMILIES,
    DatasetSpec,
    GeoContract,
    OutputSpec,
    SpatialConstraint,
    validate_contract_dict,
)


def _c(name: str, provenance: str = "geocontract", **params: Any) -> SpatialConstraint:
    return SpatialConstraint(name=name, params=params, provenance=provenance)


def _build_templates() -> dict[str, GeoContract]:
    templates: list[GeoContract] = [
        # 1. buffer_counting (4)
        GeoContract(
            contract_id="tpl-buffer-count-points",
            version="1.0.0",
            family="buffer_counting",
            query="Count target points within a metric buffer radius of each source point.",
            datasets=[
                DatasetSpec("sources", "data/sources.geojson", "source", "Point", "EPSG:4326", ["source_id", "name"], 100),
                DatasetSpec("targets", "data/targets.geojson", "target", "Point", "EPSG:4326", ["target_id", "category"], 1000),
            ],
            output=OutputSpec("out/buffer_counts.csv", "csv", ["source_id", "target_count"], "source_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"target_count": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra", unit="meters"),
                _c("one_output_row_per_source", "geocontra"),
                _c("nonnegative_counts", "geocontra"),
                _c("no_invented_fields", "geocontra"),
            ],
            allowed_methods=["to_crs", "buffer", "sjoin", "groupby"],
            forbidden_shortcuts=["buffer_on_geographic_crs", "inner_sjoin_dropping_zeros"],
        ),
        GeoContract(
            contract_id="tpl-buffer-clipped-boundary",
            version="1.0.0",
            family="buffer_counting",
            query="Compute point buffers clipped to their containing administrative boundary.",
            datasets=[
                DatasetSpec("points", "data/points.geojson", "source", "Point", "EPSG:4326", ["pt_id", "district_id"], 50),
                DatasetSpec("boundary", "data/boundary.geojson", "boundary", "Polygon", "EPSG:4326", ["district_id", "name"], 10),
            ],
            output=OutputSpec("out/clipped_buffers.geojson", "geojson", ["pt_id", "clipped_area_m2"], "pt_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="square_meters", value_ranges={"clipped_area_m2": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra", unit="meters"),
                _c("clip_to_boundary", "geocontract_gisagentbench", boundary_dataset="boundary"),
                _c("conservation_of_area", "geocontract", max_ratio=1.0),
                _c("valid_geometry_required", "gisagentbench"),
            ],
            allowed_methods=["to_crs", "buffer", "clip", "intersection"],
            forbidden_shortcuts=["unclipped_buffer_area", "buffer_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-buffer-line-corridor",
            version="1.0.0",
            family="buffer_counting",
            query="Count facilities within a corridor buffer around transit lines.",
            datasets=[
                DatasetSpec("corridors", "data/corridors.geojson", "source", "LineString", "EPSG:4326", ["line_id", "route_name"], 25),
                DatasetSpec("facilities", "data/facilities.geojson", "target", "Point", "EPSG:4326", ["fac_id", "type"], 500),
            ],
            output=OutputSpec("out/corridor_counts.csv", "csv", ["line_id", "facility_count"], "line_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"facility_count": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra", unit="meters"),
                _c("one_output_row_per_source", "geocontra"),
                _c("nonnegative_counts", "geocontra"),
            ],
            allowed_methods=["to_crs", "buffer", "sjoin", "groupby"],
            forbidden_shortcuts=["buffer_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-buffer-multi-ring-density",
            version="1.0.0",
            family="buffer_counting",
            query="Compute point density across concentric metric buffer rings.",
            datasets=[
                DatasetSpec("centers", "data/centers.geojson", "source", "Point", "EPSG:4326", ["center_id"], 20),
                DatasetSpec("events", "data/events.geojson", "target", "Point", "EPSG:4326", ["event_id", "weight"], 2000),
            ],
            output=OutputSpec("out/ring_density.csv", "csv", ["center_id", "ring_m", "density_per_km2"], "center_id", False, "any_nonempty", expected_crs="EPSG:3857", metric_unit="km2", value_ranges={"density_per_km2": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra", unit="meters"),
                _c("nonnegative_metrics", "geocontra"),
                _c("output_file_required", "gisagentbench"),
            ],
            allowed_methods=["to_crs", "buffer", "difference", "sjoin", "area"],
            forbidden_shortcuts=["buffer_on_geographic_crs", "area_on_geographic_crs"],
        ),

        # 2. spatial_joins (4)
        GeoContract(
            contract_id="tpl-sjoin-points-in-polygons",
            version="1.0.0",
            family="spatial_joins",
            query="Aggregate point counts into containing polygons while preserving zero-count polygons.",
            datasets=[
                DatasetSpec("polygons", "data/tracts.geojson", "source", "Polygon", "EPSG:4326", ["tract_id", "name"], 200),
                DatasetSpec("points", "data/incidents.geojson", "target", "Point", "EPSG:3857", ["inc_id", "severity"], 4000),
            ],
            output=OutputSpec("out/tract_counts.csv", "csv", ["tract_id", "incident_count"], "tract_id", True, "equal_to_source", value_ranges={"incident_count": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_aligned_required", "geocontra"),
                _c("predicate_direction_checked", "geocontra", expected_predicate="contains"),
                _c("one_output_row_per_source", "geocontra"),
                _c("nonnegative_counts", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin", "groupby"],
            forbidden_shortcuts=["unaligned_sjoin", "inverted_point_polygon_predicate", "plain_sjoin_without_aggregation"],
        ),
        GeoContract(
            contract_id="tpl-sjoin-boundary-inclusive",
            version="1.0.0",
            family="spatial_joins",
            query="Select all features inside or touching the study boundary using explicit covers/intersects semantics.",
            datasets=[
                DatasetSpec("features", "data/features.geojson", "source", "Point", "EPSG:4326", ["feat_id"], 300),
                DatasetSpec("boundary", "data/study_area.geojson", "boundary", "Polygon", "EPSG:4326", ["area_id"], 1),
            ],
            output=OutputSpec("out/retained_features.geojson", "geojson", ["feat_id"], "feat_id", True, "lte_source"),
            constraints=[
                _c("crs_aligned_required", "geocontra"),
                _c("boundary_predicate_explicit", "gisagentbench", predicate="intersects"),
                _c("unique_id_required", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin", "intersects", "covers"],
            forbidden_shortcuts=["ambiguous_within_excluding_boundary"],
        ),
        GeoContract(
            contract_id="tpl-sjoin-area-weighted-transfer",
            version="1.0.0",
            family="spatial_joins",
            query="Transfer polygon attributes from source zones to target zones via areal interpolation.",
            datasets=[
                DatasetSpec("source_zones", "data/census.geojson", "source", "Polygon", "EPSG:4326", ["zone_id", "population"], 80),
                DatasetSpec("target_zones", "data/grid.geojson", "target", "Polygon", "EPSG:4326", ["cell_id"], 150),
            ],
            output=OutputSpec("out/grid_population.csv", "csv", ["cell_id", "est_population"], "cell_id", True, "any_nonempty", expected_crs="EPSG:3857", value_ranges={"est_population": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("conservation_of_area", "geocontract"),
                _c("nonnegative_metrics", "geocontra"),
                _c("valid_geometry_required", "gisagentbench"),
            ],
            allowed_methods=["to_crs", "overlay", "area", "groupby"],
            forbidden_shortcuts=["centroid_join_shortcut", "area_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-sjoin-lines-crossing-zones",
            version="1.0.0",
            family="spatial_joins",
            query="Identify road segments intersecting or crossing administrative districts.",
            datasets=[
                DatasetSpec("roads", "data/roads.geojson", "source", "LineString", "EPSG:4326", ["road_id", "highway"], 600),
                DatasetSpec("districts", "data/districts.geojson", "target", "Polygon", "EPSG:4326", ["dist_id"], 15),
            ],
            output=OutputSpec("out/road_districts.csv", "csv", ["road_id", "dist_id"], None, False, "any_nonempty"),
            constraints=[
                _c("crs_aligned_required", "geocontra"),
                _c("predicate_direction_checked", "geocontra", expected_predicate="intersects"),
                _c("no_invented_fields", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin", "intersects"],
            forbidden_shortcuts=["unaligned_sjoin"],
        ),

        # 3. nearest_neighbor (4)
        GeoContract(
            contract_id="tpl-nn-nearest-facility",
            version="1.0.0",
            family="nearest_neighbor",
            query="Find the nearest emergency clinic and projected Euclidean distance for each parcel.",
            datasets=[
                DatasetSpec("parcels", "data/parcels.geojson", "source", "Point", "EPSG:4326", ["parcel_id"], 500),
                DatasetSpec("clinics", "data/clinics.geojson", "target", "Point", "EPSG:4326", ["clinic_id", "name"], 30),
            ],
            output=OutputSpec("out/nearest_clinic.csv", "csv", ["parcel_id", "clinic_id", "distance_m"], "parcel_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"distance_m": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra", unit="meters"),
                _c("one_output_row_per_source", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin_nearest", "distance"],
            forbidden_shortcuts=["distance_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-nn-knn-summary",
            version="1.0.0",
            family="nearest_neighbor",
            query="Compute mean distance to the k=3 nearest parks for each neighborhood centroid.",
            datasets=[
                DatasetSpec("neighborhoods", "data/nbh.geojson", "source", "Point", "EPSG:4326", ["nbh_id"], 40),
                DatasetSpec("parks", "data/parks.geojson", "target", "Point", "EPSG:4326", ["park_id"], 120),
            ],
            output=OutputSpec("out/knn_parks.csv", "csv", ["nbh_id", "mean_dist_m"], "nbh_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"mean_dist_m": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
                _c("unique_id_required", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin_nearest", "distance", "groupby"],
            forbidden_shortcuts=["distance_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-nn-point-to-line",
            version="1.0.0",
            family="nearest_neighbor",
            query="Measure perpendicular distance from each monitoring sensor to the nearest river reach.",
            datasets=[
                DatasetSpec("sensors", "data/sensors.geojson", "source", "Point", "EPSG:4326", ["sensor_id"], 75),
                DatasetSpec("rivers", "data/rivers.geojson", "target", "LineString", "EPSG:4326", ["reach_id"], 200),
            ],
            output=OutputSpec("out/sensor_river_dist.csv", "csv", ["sensor_id", "reach_id", "distance_m"], "sensor_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"distance_m": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin_nearest", "distance"],
            forbidden_shortcuts=["distance_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-nn-constrained-radius",
            version="1.0.0",
            family="nearest_neighbor",
            query="Find nearest hydrant within 250m while retaining unmatched buildings as null.",
            datasets=[
                DatasetSpec("buildings", "data/buildings.geojson", "source", "Point", "EPSG:4326", ["bldg_id"], 400),
                DatasetSpec("hydrants", "data/hydrants.geojson", "target", "Point", "EPSG:4326", ["hyd_id"], 300),
            ],
            output=OutputSpec("out/building_hydrants.csv", "csv", ["bldg_id", "hyd_id", "distance_m"], "bldg_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="meters", value_ranges={"distance_m": {"min": 0, "max": 250}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
            ],
            allowed_methods=["to_crs", "sjoin_nearest"],
            forbidden_shortcuts=["distance_on_geographic_crs", "inner_sjoin_dropping_zeros"],
        ),

        # 4. network_accessibility (4)
        GeoContract(
            contract_id="tpl-net-shortest-path-time",
            version="1.0.0",
            family="network_accessibility",
            query="Compute street-network driving travel time in minutes from each origin to nearest hospital.",
            datasets=[
                DatasetSpec("origins", "data/origins.geojson", "source", "Point", "EPSG:4326", ["origin_id"], 100),
                DatasetSpec("hospitals", "data/hospitals.geojson", "target", "Point", "EPSG:4326", ["hosp_id"], 12),
                DatasetSpec("road_graph", "data/streets.graphml", "network", "Graph", "EPSG:4326", ["length", "travel_time"], None, data_kind="graph"),
            ],
            output=OutputSpec("out/hospital_access.csv", "csv", ["origin_id", "hosp_id", "travel_min"], "origin_id", True, "equal_to_source", metric_unit="minutes", value_ranges={"travel_min": {"min": 0, "max": None}}),
            constraints=[
                _c("network_distance_required", "geocontra"),
                _c("travel_time_unit_minutes", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["load_graphml", "nearest_nodes", "shortest_path", "shortest_path_length"],
            forbidden_shortcuts=["direct_geometry_distance", "euclidean_distance_shortcut"],
        ),
        GeoContract(
            contract_id="tpl-net-service-area-isochrone",
            version="1.0.0",
            family="network_accessibility",
            query="Generate 15-minute walking network isochrones clipped to municipal boundary.",
            datasets=[
                DatasetSpec("stations", "data/stations.geojson", "source", "Point", "EPSG:4326", ["station_id"], 18),
                DatasetSpec("walk_net", "data/walk.graphml", "network", "Graph", "EPSG:4326", ["length"], None, data_kind="graph"),
                DatasetSpec("city", "data/city.geojson", "boundary", "Polygon", "EPSG:4326", ["city_id"], 1),
            ],
            output=OutputSpec("out/isochrones.geojson", "geojson", ["station_id", "area_km2"], "station_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="km2", value_ranges={"area_km2": {"min": 0, "max": None}}),
            constraints=[
                _c("network_distance_required", "geocontra"),
                _c("clip_to_boundary", "geocontract_gisagentbench", boundary_dataset="city"),
                _c("crs_projected_required", "geocontra"),
            ],
            allowed_methods=["load_graphml", "nearest_nodes", "ego_graph", "clip"],
            forbidden_shortcuts=["direct_geometry_distance", "buffer_instead_of_isochrone"],
        ),
        GeoContract(
            contract_id="tpl-net-od-matrix",
            version="1.0.0",
            family="network_accessibility",
            query="Build an origin-destination road network distance matrix between warehouses and stores.",
            datasets=[
                DatasetSpec("warehouses", "data/warehouses.geojson", "source", "Point", "EPSG:4326", ["wh_id"], 5),
                DatasetSpec("stores", "data/stores.geojson", "target", "Point", "EPSG:4326", ["store_id"], 40),
                DatasetSpec("roads", "data/roads.graphml", "network", "Graph", "EPSG:4326", ["length"], None, data_kind="graph"),
            ],
            output=OutputSpec("out/od_matrix.csv", "csv", ["wh_id", "store_id", "network_dist_m"], None, False, "exact", expected_rows=200, metric_unit="meters", value_ranges={"network_dist_m": {"min": 0, "max": None}}),
            constraints=[
                _c("network_distance_required", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
                _c("conservation_of_rows", "geocontract"),
            ],
            allowed_methods=["load_graphml", "nearest_nodes", "shortest_path_length"],
            forbidden_shortcuts=["direct_geometry_distance"],
        ),
        GeoContract(
            contract_id="tpl-net-emergency-coverage",
            version="1.0.0",
            family="network_accessibility",
            query="Calculate share of households reachable within 8 minutes by fire truck over street network.",
            datasets=[
                DatasetSpec("fire_stations", "data/fire.geojson", "source", "Point", "EPSG:4326", ["fs_id"], 10),
                DatasetSpec("households", "data/households.geojson", "target", "Point", "EPSG:4326", ["hh_id"], 2500),
                DatasetSpec("streets", "data/streets.graphml", "network", "Graph", "EPSG:4326", ["length", "travel_time"], None, data_kind="graph"),
            ],
            output=OutputSpec("out/fire_coverage.csv", "csv", ["zone_id", "coverage_ratio"], "zone_id", True, "any_nonempty", metric_unit="ratio", value_ranges={"coverage_ratio": {"min": 0.0, "max": 1.0}}),
            constraints=[
                _c("network_distance_required", "geocontra"),
                _c("travel_time_unit_minutes", "geocontra"),
                _c("ratios_in_unit_interval", "geocontra"),
            ],
            allowed_methods=["load_graphml", "nearest_nodes", "shortest_path_length"],
            forbidden_shortcuts=["direct_geometry_distance"],
        ),

        # 5. overlay_areas (4)
        GeoContract(
            contract_id="tpl-overlay-flood-ratio",
            version="1.0.0",
            family="overlay_areas",
            query="Compute the fraction of each census tract covered by the 100-year floodplain.",
            datasets=[
                DatasetSpec("tracts", "data/tracts.geojson", "source", "Polygon", "EPSG:4326", ["tract_id"], 120),
                DatasetSpec("floodplain", "data/floodplain.geojson", "target", "Polygon", "EPSG:4326", ["zone_code"], 15),
            ],
            output=OutputSpec("out/flood_exposure.csv", "csv", ["tract_id", "flood_ratio"], "tract_id", True, "equal_to_source", expected_crs="EPSG:3857", metric_unit="ratio", value_ranges={"flood_ratio": {"min": 0.0, "max": 1.0}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("ratios_in_unit_interval", "geocontra"),
                _c("valid_geometry_required", "gisagentbench"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["to_crs", "make_valid", "overlay", "area"],
            forbidden_shortcuts=["centroid_inside_proxy", "area_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-overlay-landuse-clip",
            version="1.0.0",
            family="overlay_areas",
            query="Clip land-use polygons to county boundary and summarize area by class.",
            datasets=[
                DatasetSpec("landuse", "data/landuse.geojson", "source", "Polygon", "EPSG:4326", ["lu_id", "lu_class"], 900),
                DatasetSpec("county", "data/county.geojson", "boundary", "Polygon", "EPSG:4326", ["county_id"], 1),
            ],
            output=OutputSpec("out/landuse_summary.csv", "csv", ["lu_class", "area_km2"], "lu_class", True, "any_nonempty", expected_crs="EPSG:3857", metric_unit="km2", value_ranges={"area_km2": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("clip_to_boundary", "geocontract_gisagentbench", boundary_dataset="county"),
                _c("conservation_of_area", "geocontract"),
                _c("valid_geometry_required", "gisagentbench"),
            ],
            allowed_methods=["to_crs", "clip", "make_valid", "area", "groupby"],
            forbidden_shortcuts=["unclipped_overlay_area", "area_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-overlay-symdiff-change",
            version="1.0.0",
            family="overlay_areas",
            query="Quantify wetland gain and loss via symmetric difference between 2015 and 2025 layers.",
            datasets=[
                DatasetSpec("wetland_2015", "data/wetland_2015.geojson", "source", "Polygon", "EPSG:4326", ["w_id"], 60),
                DatasetSpec("wetland_2025", "data/wetland_2025.geojson", "target", "Polygon", "EPSG:4326", ["w_id"], 55),
            ],
            output=OutputSpec("out/wetland_change.csv", "csv", ["change_type", "area_ha"], "change_type", True, "any_nonempty", expected_crs="EPSG:3857", metric_unit="hectares", value_ranges={"area_ha": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("valid_geometry_required", "gisagentbench"),
                _c("nonnegative_metrics", "geocontra"),
            ],
            allowed_methods=["to_crs", "make_valid", "overlay", "area"],
            forbidden_shortcuts=["area_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-overlay-dissolve-budget",
            version="1.0.0",
            family="overlay_areas",
            query="Dissolve parcels by zoning code and verify total area conservation.",
            datasets=[
                DatasetSpec("parcels", "data/parcels.geojson", "source", "Polygon", "EPSG:3857", ["parcel_id", "zone_code"], 1500),
            ],
            output=OutputSpec("out/zoning_dissolved.geojson", "geojson", ["zone_code", "area_m2"], "zone_code", True, "any_nonempty", expected_crs="EPSG:3857", metric_unit="square_meters", value_ranges={"area_m2": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("conservation_of_area", "geocontract"),
                _c("unique_id_required", "geocontra"),
                _c("valid_geometry_required", "gisagentbench"),
            ],
            allowed_methods=["make_valid", "dissolve", "area"],
            forbidden_shortcuts=["area_on_geographic_crs"],
        ),

        # 6. raster_sampling (4)
        GeoContract(
            contract_id="tpl-raster-sample-dem",
            version="1.0.0",
            family="raster_sampling",
            query="Sample continuous DEM elevation at field plot points while masking NoData.",
            datasets=[
                DatasetSpec("plots", "data/plots.geojson", "source", "Point", "EPSG:4326", ["plot_id"], 250),
                DatasetSpec("dem", "data/dem.tif", "raster", "Raster", "EPSG:32619", [], None, nodata=-9999.0, resolution=10.0, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/plot_elevations.csv", "csv", ["plot_id", "elevation_m"], "plot_id", True, "equal_to_source", metric_unit="meters"),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("crs_aligned_required", "geocontra"),
                _c("header_resolution_required", "gisagentbench"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["to_crs", "sample", "mask_nodata"],
            forbidden_shortcuts=["ignore_nodata", "filename_resolution_assumption"],
        ),
        GeoContract(
            contract_id="tpl-raster-sample-categorical",
            version="1.0.0",
            family="raster_sampling",
            query="Sample categorical NLCD land-cover class at survey sites using nearest-neighbor only.",
            datasets=[
                DatasetSpec("sites", "data/sites.geojson", "source", "Point", "EPSG:4326", ["site_id"], 180),
                DatasetSpec("nlcd", "data/nlcd.tif", "raster", "Raster", "EPSG:5070", [], None, nodata=0, resolution=30.0, data_kind="categorical_raster"),
            ],
            output=OutputSpec("out/site_landcover.csv", "csv", ["site_id", "nlcd_class"], "site_id", True, "equal_to_source"),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("resampling_matches_data_kind", "gisagentbench", allowed=["nearest", "mode"]),
                _c("crs_aligned_required", "geocontra"),
            ],
            allowed_methods=["to_crs", "sample", "reproject_nearest"],
            forbidden_shortcuts=["bilinear_on_categorical", "ignore_nodata"],
        ),
        GeoContract(
            contract_id="tpl-raster-reproject-before-slope",
            version="1.0.0",
            family="raster_sampling",
            query="Reproject and resample a geographic DEM to projected 10m grid before computing slope.",
            datasets=[
                DatasetSpec("dem_4326", "data/dem_4326.tif", "raster", "Raster", "EPSG:4326", [], None, nodata=-9999.0, resolution=0.000277, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/slope_10m.tif", "geotiff", [], None, False, "any_nonempty", expected_crs="EPSG:32619", metric_unit="degrees"),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("operation_order_enforced", "gisagentbench", order=["reproject", "resample", "slope"]),
                _c("resampling_matches_data_kind", "gisagentbench", allowed=["bilinear", "cubic"]),
                _c("nodata_mask_required", "gisagentbench"),
            ],
            allowed_methods=["gdalwarp", "raster_reproject", "resample", "slope"],
            forbidden_shortcuts=["slope_before_resample", "slope_on_geographic_crs", "nearest_on_continuous"],
        ),
        GeoContract(
            contract_id="tpl-raster-ndvi-sample",
            version="1.0.0",
            family="raster_sampling",
            query="Compute NDVI from Red and NIR bands with NoData masking and [-1, 1] bounds verification.",
            datasets=[
                DatasetSpec("sentinel", "data/sentinel_red_nir.tif", "raster", "Raster", "EPSG:32619", [], None, nodata=0, resolution=10.0, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/ndvi_stats.csv", "csv", ["scene_id", "ndvi_mean"], "scene_id", True, "any_nonempty", value_ranges={"ndvi_mean": {"min": -1.0, "max": 1.0}}),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("output_file_required", "gisagentbench"),
            ],
            allowed_methods=["mask_nodata", "band_math"],
            forbidden_shortcuts=["ignore_nodata"],
        ),

        # 7. zonal_statistics (4)
        GeoContract(
            contract_id="tpl-zonal-mean-continuous",
            version="1.0.0",
            family="zonal_statistics",
            query="Compute NoData-masked mean temperature per watershed polygon.",
            datasets=[
                DatasetSpec("watersheds", "data/watersheds.geojson", "source", "Polygon", "EPSG:4326", ["ws_id", "name"], 45),
                DatasetSpec("temp_raster", "data/temp_c.tif", "raster", "Raster", "EPSG:3857", [], None, nodata=-9999.0, resolution=100.0, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/watershed_temp.csv", "csv", ["ws_id", "mean_temp_c"], "ws_id", True, "equal_to_source"),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("crs_aligned_required", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["to_crs", "zonal_stats", "mask_nodata"],
            forbidden_shortcuts=["ignore_nodata", "unaligned_zonal_stats"],
        ),
        GeoContract(
            contract_id="tpl-zonal-majority-categorical",
            version="1.0.0",
            family="zonal_statistics",
            query="Find dominant land-cover class per municipality from categorical raster.",
            datasets=[
                DatasetSpec("munis", "data/munis.geojson", "source", "Polygon", "EPSG:5070", ["muni_id"], 60),
                DatasetSpec("landcover", "data/landcover.tif", "raster", "Raster", "EPSG:5070", [], None, nodata=0, resolution=30.0, data_kind="categorical_raster"),
            ],
            output=OutputSpec("out/muni_landcover.csv", "csv", ["muni_id", "majority_class"], "muni_id", True, "equal_to_source"),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("resampling_matches_data_kind", "gisagentbench", allowed=["nearest", "mode"]),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["zonal_stats", "mask_nodata"],
            forbidden_shortcuts=["mean_on_categorical_raster", "ignore_nodata"],
        ),
        GeoContract(
            contract_id="tpl-zonal-population-sum",
            version="1.0.0",
            family="zonal_statistics",
            query="Sum gridded population counts per district with non-negativity and NoData masking.",
            datasets=[
                DatasetSpec("districts", "data/districts.geojson", "source", "Polygon", "EPSG:3857", ["dist_id"], 30),
                DatasetSpec("pop_grid", "data/worldpop.tif", "raster", "Raster", "EPSG:3857", [], None, nodata=-99999.0, resolution=100.0, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/district_pop.csv", "csv", ["dist_id", "pop_sum"], "dist_id", True, "equal_to_source", value_ranges={"pop_sum": {"min": 0, "max": None}}),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("crs_projected_required", "geocontra"),
                _c("nonnegative_counts", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
            ],
            allowed_methods=["zonal_stats", "mask_nodata"],
            forbidden_shortcuts=["ignore_nodata"],
        ),
        GeoContract(
            contract_id="tpl-zonal-close-value-compare",
            version="1.0.0",
            family="zonal_statistics",
            query="Compare green-cover percentage between two regions with close-value epsilon guard.",
            datasets=[
                DatasetSpec("regions", "data/regions.geojson", "source", "Polygon", "EPSG:3035", ["region_id", "region_name"], 2),
                DatasetSpec("green_cover", "data/green_cover.tif", "raster", "Raster", "EPSG:3035", [], None, nodata=255, resolution=20.0, data_kind="categorical_raster"),
            ],
            output=OutputSpec("out/region_compare.csv", "csv", ["region_id", "green_pct"], "region_id", True, "equal_to_source", value_ranges={"green_pct": {"min": 0.0, "max": 100.0}}),
            constraints=[
                _c("nodata_mask_required", "gisagentbench"),
                _c("close_value_epsilon_guard", "geonatureagent", epsilon=0.5),
                _c("reject_task", "geobenchx_geonatureagent"),
            ],
            allowed_methods=["zonal_stats", "compare_areas", "reject_task"],
            forbidden_shortcuts=["fabricate_directional_difference", "hallucinate_missing_region"],
        ),

        # 8. topology_quality (4)
        GeoContract(
            contract_id="tpl-topo-validate-repair",
            version="1.0.0",
            family="topology_quality",
            query="Validate and repair self-intersecting polygon geometries while conserving row count and unique IDs.",
            datasets=[
                DatasetSpec("raw_polys", "data/raw_polys.geojson", "source", "Polygon", "EPSG:3857", ["poly_id", "owner"], 300),
            ],
            output=OutputSpec("out/valid_polys.geojson", "geojson", ["poly_id", "was_repaired"], "poly_id", True, "equal_to_source", expected_crs="EPSG:3857"),
            constraints=[
                _c("valid_geometry_required", "gisagentbench"),
                _c("conservation_of_rows", "geocontract"),
                _c("unique_id_required", "geocontra"),
            ],
            allowed_methods=["is_valid", "make_valid", "v.build", "v.clean"],
            forbidden_shortcuts=["drop_invalid_silently"],
        ),
        GeoContract(
            contract_id="tpl-topo-sliver-cleanup",
            version="1.0.0",
            family="topology_quality",
            query="Detect and clean sliver polygons and overlaps prior to area overlay.",
            datasets=[
                DatasetSpec("parcels", "data/parcels_dirty.geojson", "source", "Polygon", "EPSG:3857", ["parcel_id"], 500),
            ],
            output=OutputSpec("out/parcels_clean.geojson", "geojson", ["parcel_id", "area_m2"], "parcel_id", True, "lte_source", expected_crs="EPSG:3857", value_ranges={"area_m2": {"min": 0, "max": None}}),
            constraints=[
                _c("valid_geometry_required", "gisagentbench"),
                _c("crs_projected_required", "geocontra"),
                _c("conservation_of_area", "geocontract"),
            ],
            allowed_methods=["make_valid", "v.clean", "area"],
            forbidden_shortcuts=["overlay_without_topology_clean"],
        ),
        GeoContract(
            contract_id="tpl-topo-gap-overlap-audit",
            version="1.0.0",
            family="topology_quality",
            query="Audit a planar partition for gaps and overlapping area totals.",
            datasets=[
                DatasetSpec("partition", "data/partition.geojson", "source", "Polygon", "EPSG:3857", ["part_id"], 100),
            ],
            output=OutputSpec("out/topo_audit.json", "json", ["overlap_area_m2", "invalid_count"], None, False, "any_nonempty", expected_crs="EPSG:3857", value_ranges={"overlap_area_m2": {"min": 0, "max": None}, "invalid_count": {"min": 0, "max": None}}),
            constraints=[
                _c("valid_geometry_required", "gisagentbench"),
                _c("crs_projected_required", "geocontra"),
                _c("nonnegative_metrics", "geocontra"),
            ],
            allowed_methods=["is_valid", "intersection", "area"],
            forbidden_shortcuts=["area_on_geographic_crs"],
        ),
        GeoContract(
            contract_id="tpl-topo-schema-crs-audit",
            version="1.0.0",
            family="topology_quality",
            query="Verify dataset schema fields, CRS metadata, and non-brittle ID types before export.",
            datasets=[
                DatasetSpec("layer", "data/layer.geojson", "source", "Any", "EPSG:4326", ["feature_id", "label"], 200),
            ],
            output=OutputSpec("out/audited.csv", "csv", ["feature_id", "label"], "feature_id", True, "equal_to_source"),
            constraints=[
                _c("no_invented_fields", "geocontra"),
                _c("unique_id_required", "geocontra"),
                _c("output_file_required", "gisagentbench"),
            ],
            allowed_methods=["validate_schema", "check_crs"],
            forbidden_shortcuts=["brittle_float_id_cast"],
        ),

        # 9. multi_step_workflow (4)
        GeoContract(
            contract_id="tpl-workflow-site-suitability",
            version="1.0.0",
            family="multi_step_workflow",
            query="Multi-criteria site suitability combining transit buffers, boundary clip, and DEM zonal slope.",
            datasets=[
                DatasetSpec("stations", "data/stations.geojson", "source", "Point", "EPSG:4326", ["st_id"], 20),
                DatasetSpec("city", "data/city.geojson", "boundary", "Polygon", "EPSG:4326", ["city_id"], 1),
                DatasetSpec("dem", "data/dem.tif", "raster", "Raster", "EPSG:32619", [], None, nodata=-9999.0, resolution=10.0, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/suitability.csv", "csv", ["site_id", "suitability_score"], "site_id", True, "any_nonempty", expected_crs="EPSG:32619", value_ranges={"suitability_score": {"min": 0.0, "max": 1.0}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("clip_to_boundary", "geocontract_gisagentbench", boundary_dataset="city"),
                _c("nodata_mask_required", "gisagentbench"),
                _c("ratios_in_unit_interval", "geocontra"),
            ],
            allowed_methods=["to_crs", "buffer", "clip", "zonal_stats", "mask_nodata"],
            forbidden_shortcuts=["buffer_on_geographic_crs", "ignore_nodata"],
        ),
        GeoContract(
            contract_id="tpl-workflow-flood-exposure",
            version="1.0.0",
            family="multi_step_workflow",
            query="Assess population exposure by reprojecting DEM, overlaying floodplain, and counting buildings.",
            datasets=[
                DatasetSpec("buildings", "data/buildings.geojson", "source", "Polygon", "EPSG:4326", ["bldg_id", "occupants"], 1200),
                DatasetSpec("floodplain", "data/floodplain.geojson", "target", "Polygon", "EPSG:4326", ["fp_id"], 10),
                DatasetSpec("dem", "data/dem.tif", "raster", "Raster", "EPSG:4326", [], None, nodata=-9999.0, resolution=0.000277, data_kind="continuous_raster"),
            ],
            output=OutputSpec("out/flood_exposure_report.csv", "csv", ["fp_id", "exposed_buildings", "exposed_occupants"], "fp_id", True, "any_nonempty", expected_crs="EPSG:3857", value_ranges={"exposed_buildings": {"min": 0, "max": None}, "exposed_occupants": {"min": 0, "max": None}}),
            constraints=[
                _c("crs_projected_required", "geocontra"),
                _c("operation_order_enforced", "gisagentbench", order=["reproject", "resample", "slope"]),
                _c("valid_geometry_required", "gisagentbench"),
                _c("nonnegative_counts", "geocontra"),
            ],
            allowed_methods=["to_crs", "make_valid", "overlay", "sjoin", "groupby"],
            forbidden_shortcuts=["slope_before_resample", "centroid_inside_proxy"],
        ),
        GeoContract(
            contract_id="tpl-workflow-transit-equity",
            version="1.0.0",
            family="multi_step_workflow",
            query="Evaluate transit equity by combining street-network access times with census zonal demographics.",
            datasets=[
                DatasetSpec("tracts", "data/tracts.geojson", "source", "Polygon", "EPSG:4326", ["tract_id", "median_income"], 150),
                DatasetSpec("stops", "data/stops.geojson", "target", "Point", "EPSG:4326", ["stop_id"], 800),
                DatasetSpec("streets", "data/streets.graphml", "network", "Graph", "EPSG:4326", ["length", "travel_time"], None, data_kind="graph"),
            ],
            output=OutputSpec("out/transit_equity.csv", "csv", ["tract_id", "travel_min", "median_income"], "tract_id", True, "equal_to_source", metric_unit="minutes", value_ranges={"travel_min": {"min": 0, "max": None}}),
            constraints=[
                _c("network_distance_required", "geocontra"),
                _c("travel_time_unit_minutes", "geocontra"),
                _c("one_output_row_per_source", "geocontra"),
                _c("close_value_epsilon_guard", "geonatureagent", epsilon=0.5),
            ],
            allowed_methods=["load_graphml", "nearest_nodes", "shortest_path_length", "groupby"],
            forbidden_shortcuts=["direct_geometry_distance", "inner_sjoin_dropping_zeros"],
        ),
        GeoContract(
            contract_id="tpl-workflow-unsolvable-guard",
            version="1.0.0",
            family="multi_step_workflow",
            query="Verify entity and indicator availability before analysis; invoke reject_task if unsolvable.",
            datasets=[
                DatasetSpec("admin_catalog", "data/municipalities.geojson", "reference", "Polygon", "EPSG:4326", ["muni_id", "muni_name"], 50),
                DatasetSpec("basemap", "data/basemap_tiles.tif", "raster", "Raster", "EPSG:3857", [], None, data_kind="categorical_raster", display_only=True),
            ],
            output=OutputSpec("out/verified_answer.json", "json", ["status", "reason"], None, False, "allow_empty"),
            constraints=[
                _c("reject_task", "geobenchx_geonatureagent"),
                _c("no_invented_fields", "geocontra"),
                _c("output_file_required", "gisagentbench"),
            ],
            allowed_methods=["lookup_entity", "list_layers", "reject_task"],
            forbidden_shortcuts=["fabricate_statistics_from_display_layer", "hallucinate_missing_entity"],
        ),
    ]
    catalog = {t.contract_id: t for t in templates}
    for t in catalog.values():
        validate_contract_dict(t.to_dict())
    return catalog


_TEMPLATE_REGISTRY: dict[str, GeoContract] = _build_templates()


def list_templates(family: str | None = None) -> list[GeoContract]:
    """Return copies of all standard templates, optionally filtered by family."""
    if family is not None and family not in VALID_FAMILIES:
        raise ValueError(f"Unknown family '{family}'. Must be one of {VALID_FAMILIES}")
    return [
        deepcopy(t)
        for t in _TEMPLATE_REGISTRY.values()
        if family is None or t.family == family
    ]


def get_template(template_id: str) -> GeoContract:
    """Return a deep copy of a standard template by ID."""
    if template_id not in _TEMPLATE_REGISTRY:
        raise KeyError(f"Template '{template_id}' not found")
    return deepcopy(_TEMPLATE_REGISTRY[template_id])


def template_counts_by_family() -> dict[str, int]:
    counts = {fam: 0 for fam in VALID_FAMILIES}
    for t in _TEMPLATE_REGISTRY.values():
        counts[t.family] += 1
    return counts
