"""Offline mock QGIS-MCP & GDAL-MCP server for end-to-end proxy verification (D2-P4)."""

from __future__ import annotations

import copy
from typing import Any

from geocontract.mcp.protocol import (
    SUPPORTED_PROTOCOL_VERSIONS,
    JsonRpcRequest,
    JsonRpcResponse,
    make_protocol_error,
    make_tool_result,
)


class MockGeoMCPServer:
    """In-memory offline MCP server simulating QGIS-MCP v0.4.8 and gdal-mcp 1.1.3 tools."""

    TOOLS: list[dict[str, Any]] = [
        {"name": "qgis_context", "description": "Return revisioned project snapshot within byte budget."},
        {"name": "raster_info", "description": "Inspect raster CRS, resolution, bands, and nodata."},
        {"name": "raster_convert", "description": "Convert raster format with compression/COG."},
        {"name": "raster_reproject", "description": "Reproject raster with explicit resampling method."},
        {"name": "raster_stats", "description": "Compute band statistics with optional NoData mask."},
        {"name": "vector_info", "description": "Inspect vector CRS, geometry type, and attributes."},
        {"name": "vector_reproject", "description": "Transform vector layer to target CRS."},
        {"name": "vector_convert", "description": "Convert vector format (SHP/GPKG/GeoJSON)."},
        {"name": "vector_clip", "description": "Clip vector layer to boundary polygon."},
        {"name": "vector_buffer", "description": "Create metric buffer around vector features."},
        {"name": "vector_simplify", "description": "Simplify vector geometries."},
        {"name": "store_justification", "description": "Cache epistemic reflection justification."},
        {"name": "qgis_processing_sjoin", "description": "Spatial join between two vector layers."},
        {"name": "qgis_processing_overlay", "description": "Overlay intersection between two polygon layers."},
        {"name": "qgis_processing_slope", "description": "Compute terrain slope from DEM raster."},
        {"name": "qgis_network_shortest_path", "description": "Compute street-network shortest path."},
        {"name": "vector_distance", "description": "Compute direct Euclidean distance between layers."},
        {"name": "reject_task", "description": "Explicitly reject an unsolvable spatial task."},
    ]

    def __init__(self, initial_layers: dict[str, dict[str, Any]] | None = None) -> None:
        self.layers: dict[str, dict[str, Any]] = copy.deepcopy(
            initial_layers
            or {
                "schools": {
                    "crs": "EPSG:4326",
                    "geometry_type": "Point",
                    "row_count": 20,
                    "is_valid": True,
                    "data_kind": "vector",
                },
                "tracts": {
                    "crs": "EPSG:3857",
                    "geometry_type": "Polygon",
                    "row_count": 10,
                    "is_valid": True,
                    "data_kind": "vector",
                },
                "dirty_parcels": {
                    "crs": "EPSG:3857",
                    "geometry_type": "Polygon",
                    "row_count": 15,
                    "is_valid": False,
                    "data_kind": "vector",
                },
                "county_boundary": {
                    "crs": "EPSG:3857",
                    "geometry_type": "Polygon",
                    "row_count": 1,
                    "is_valid": True,
                    "data_kind": "vector",
                },
                "dem_4326": {
                    "crs": "EPSG:4326",
                    "geometry_type": "Raster",
                    "nodata": -9999.0,
                    "resolution": 0.000277,
                    "data_kind": "continuous_raster",
                },
                "nlcd_5070": {
                    "crs": "EPSG:5070",
                    "geometry_type": "Raster",
                    "nodata": 0,
                    "resolution": 30.0,
                    "data_kind": "categorical_raster",
                },
                "basemap_tiles": {
                    "crs": "EPSG:3857",
                    "geometry_type": "Raster",
                    "data_kind": "categorical_raster",
                    "display_only": True,
                },
            }
        )
        self.call_log: list[dict[str, Any]] = []

    def handle_request(self, req: JsonRpcRequest) -> JsonRpcResponse:
        if req.method == "initialize":
            ver = req.params.get("protocolVersion", "2025-03-26")
            chosen = ver if ver in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[-1]
            return JsonRpcResponse(
                id=req.id,
                result={
                    "protocolVersion": chosen,
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "mock-geo-mcp", "version": "0.1.0"},
                },
            )
        if req.method == "tools/list":
            return JsonRpcResponse(id=req.id, result={"tools": self.TOOLS})
        if req.method != "tools/call":
            return make_protocol_error(req.id, -32601, f"Method not found: {req.method}")

        name = req.params.get("name", "")
        args = dict(req.params.get("arguments") or {})
        self.call_log.append({"tool": name, "arguments": copy.deepcopy(args)})

        if name == "vector_reproject":
            src = args["input_layer"]
            out = args.get("output_layer", f"{src}_reproj")
            meta = copy.deepcopy(self.layers[src])
            meta["crs"] = args["target_crs"]
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "crs": meta["crs"]})

        if name == "raster_reproject":
            src = args["input_layer"]
            out = args.get("output_layer", f"{src}_reproj")
            meta = copy.deepcopy(self.layers[src])
            meta["crs"] = args["target_crs"]
            meta["resampling"] = args.get("resampling")
            meta["resampled"] = True
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "crs": meta["crs"], "resampling": meta["resampling"]})

        if name == "vector_buffer":
            src = args["input_layer"]
            out = args.get("output_layer", f"{src}_buf")
            meta = copy.deepcopy(self.layers[src])
            meta["geometry_type"] = "Polygon"
            meta["clipped"] = bool(args.get("clip_boundary"))
            meta["area_m2"] = float(args.get("distance", 100.0)) ** 2 * 3.14159
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "crs": meta["crs"], "clipped": meta["clipped"], "area_m2": meta["area_m2"]})

        if name == "vector_clip":
            src = args["input_layer"]
            out = args.get("output_layer", f"{src}_clipped")
            meta = copy.deepcopy(self.layers[src])
            meta["clipped"] = True
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "clipped": True})

        if name == "qgis_processing_sjoin":
            left = args["left_layer"]
            out = args.get("output_layer", f"{left}_sjoin")
            meta = copy.deepcopy(self.layers[left])
            meta["row_count"] = meta.get("row_count", 10) if args.get("how", "left") == "left" else max(1, meta.get("row_count", 10) - 4)
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "row_count": meta["row_count"], "predicate": args.get("predicate")})

        if name == "qgis_processing_overlay":
            left = args["left_layer"]
            out = args.get("output_layer", f"{left}_overlay")
            meta = copy.deepcopy(self.layers[left])
            meta["is_valid"] = True
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "is_valid": True})

        if name == "qgis_processing_slope":
            src = args["input_layer"]
            out = args.get("output_layer", f"{src}_slope")
            meta = copy.deepcopy(self.layers[src])
            meta["derived_from_slope"] = True
            self.layers[out] = meta
            return make_tool_result(req.id, {"status": "ok", "output_layer": out, "crs": meta["crs"]})

        if name == "raster_stats":
            src = args["input_layer"]
            masked = bool(args.get("mask_nodata", False))
            mean_val = 42.5 if masked else -4820.0
            return make_tool_result(req.id, {"status": "ok", "input_layer": src, "mask_nodata": masked, "mean": mean_val})

        if name == "qgis_network_shortest_path":
            return make_tool_result(req.id, {"status": "ok", "travel_min": 12.4, "distance_m": 4200.0})

        if name == "vector_distance":
            return make_tool_result(req.id, {"status": "ok", "distance_m": 3100.0, "method": "euclidean"})

        if name == "reject_task":
            return make_tool_result(req.id, {"status": "rejected", "reason": args.get("reason", "unsolvable")})

        if name in ("raster_info", "vector_info"):
            src = args.get("input_layer", "")
            if src not in self.layers:
                return make_tool_result(req.id, {"error": f"Layer '{src}' not found"}, is_error=True)
            return make_tool_result(req.id, {"status": "ok", "layer": src, "metadata": self.layers[src]})

        if name == "qgis_context":
            return make_tool_result(req.id, {"status": "ok", "layers": list(self.layers.keys())})

        return make_tool_result(req.id, {"error": f"Unknown tool: {name}"}, is_error=True)
