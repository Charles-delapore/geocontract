"""Transparent Verifiable MCP Proxy with Bounded Self-Healing Loop (D2-P4).

Intercepts JSON-RPC 2.0 ``tools/call`` requests targeting QGIS-MCP or GDAL-MCP
servers, validates preconditions + Revision Guard + Reflection Gate before dispatch,
verifies output assertions after dispatch, and executes bounded geographic
self-healing (N <= 3 rounds) or clean checkpoint rollback on unrecoverable failure.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from geocontract.dsl.schema import GeoContract
from geocontract.lint.analyzer import _is_geographic_crs
from geocontract.mcp.protocol import JsonRpcRequest, JsonRpcResponse, make_tool_result
from geocontract.mcp.revision_guard import ReflectionGate, RevisionGuard


@dataclass
class GeographicDiagnostic:
    code: str
    severity: str
    message: str
    suggested_fix: str
    patch_hint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "patch_hint": dict(self.patch_hint),
        }


@dataclass
class ProxyExecutionResult:
    accepted: bool
    rounds_used: int
    rolled_back: bool
    final_request: JsonRpcRequest
    response: JsonRpcResponse
    diagnostics_history: list[list[GeographicDiagnostic]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)


class VerifiableMCPProxy:
    """Transparent JSON-RPC MCP proxy enforcing spatial contracts and bounded self-healing."""

    FORBIDDEN_TOOLS: frozenset[str] = frozenset({"exec_python", "run_python", "eval_code", "qgis_exec_python"})

    def __init__(
        self,
        backend: Any,
        *,
        revision_guard: RevisionGuard | None = None,
        reflection_gate: ReflectionGate | None = None,
        max_rounds: int = 3,
    ) -> None:
        if max_rounds < 0 or max_rounds > 3:
            raise ValueError("Bounded self-healing requires 0 <= max_rounds <= 3")
        self.backend = backend
        self.revision_guard = revision_guard or RevisionGuard(getattr(backend, "layers", {}))
        self.reflection_gate = reflection_gate or ReflectionGate()
        self.max_rounds = max_rounds

    def _layer_meta(self, name: str | None) -> dict[str, Any]:
        if not name:
            return {}
        if name in self.revision_guard.layers:
            return self.revision_guard.layers[name]
        backend_layers = getattr(self.backend, "layers", {})
        return backend_layers.get(name, {})

    def validate_preconditions(
        self,
        req: JsonRpcRequest,
        contract: GeoContract | None = None,
    ) -> list[GeographicDiagnostic]:
        """Run all pre-call contract, Revision Guard, and Reflection Gate checks."""
        if req.method != "tools/call":
            return []

        diags: list[GeographicDiagnostic] = []
        tool = str(req.params.get("name", ""))
        args = dict(req.params.get("arguments") or {})

        # 1. Safe boundary: forbid arbitrary Python execution (QGIS-MCP v0.4.8)
        if tool in self.FORBIDDEN_TOOLS:
            diags.append(
                GeographicDiagnostic(
                    code="MCP_ARBITRARY_EXEC_FORBIDDEN",
                    severity="error",
                    message=f"Tool '{tool}' violates QGIS-MCP safe boundary (no arbitrary Python execution).",
                    suggested_fix="Use typed GIS tools or Processing algorithms instead.",
                )
            )
            return diags

        # 2. Revision Guard stale-write check
        claimed_rev = args.get("revision")
        ok_rev, rev_msg = self.revision_guard.check_revision(claimed_rev)
        if not ok_rev:
            diags.append(
                GeographicDiagnostic(
                    code="MCP_STALE_REVISION",
                    severity="error",
                    message=rev_msg,
                    suggested_fix=f"Update revision to {self.revision_guard.revision} after refreshing qgis_context.",
                    patch_hint={"set_arg": {"revision": self.revision_guard.revision}},
                )
            )

        # 3. No-progress duplicate call check
        ok_loop, loop_msg = self.revision_guard.check_no_progress_loop(tool, args)
        if not ok_loop:
            diags.append(
                GeographicDiagnostic(
                    code="MCP_NO_PROGRESS_LOOP",
                    severity="error",
                    message=loop_msg,
                    suggested_fix="Modify tool parameters or switch strategy instead of repeating identical call.",
                )
            )

        # 4. Reflection Gate check (gdal-mcp 1.1.3)
        if tool == "store_justification":
            return diags
        ok_ref, missing_prompts = self.reflection_gate.check_call(tool, args)
        if not ok_ref:
            diags.append(
                GeographicDiagnostic(
                    code="MCP_REFLECTION_REQUIRED",
                    severity="error",
                    message=f"Tool '{tool}' requires cached epistemic justification(s): {missing_prompts}.",
                    suggested_fix="Store structured justification via store_justification before invoking.",
                    patch_hint={"store_justifications": missing_prompts},
                )
            )

        # 5. Tool-specific geographic precondition checks
        in_layer = args.get("input_layer")
        in_meta = self._layer_meta(in_layer)

        # 5a. Display-only layer statistics guard -> reject_task
        if in_meta.get("display_only") and tool in ("raster_stats", "qgis_processing_slope", "vector_buffer"):
            diags.append(
                GeographicDiagnostic(
                    code="MCP_DISPLAY_ONLY_REJECT",
                    severity="error",
                    message=f"Layer '{in_layer}' is display-only; quantitative tool '{tool}' is invalid.",
                    suggested_fix="Invoke reject_task explaining that the target layer is display-only.",
                    patch_hint={"switch_tool": "reject_task", "reason": f"Layer '{in_layer}' is display-only"},
                )
            )

        # 5b. Buffer on geographic CRS
        if tool == "vector_buffer":
            crs = args.get("crs") or in_meta.get("crs")
            if _is_geographic_crs(crs):
                target_crs = (contract.output.expected_crs if contract and contract.output.expected_crs else "EPSG:3857")
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_BUFFER_GEOGRAPHIC_CRS",
                        severity="error",
                        message=f"vector_buffer called on geographic CRS ({crs}); metric distance would be treated as degrees.",
                        suggested_fix=f"Reproject '{in_layer}' to projected CRS ({target_crs}) before buffering.",
                        patch_hint={"reproject_input": target_crs},
                    )
                )
            if contract and contract.has_constraint("clip_to_boundary") and not args.get("clip_boundary"):
                bnd_name = next((d.name for d in contract.datasets if d.role == "boundary"), "county_boundary")
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_UNCLIPPED_BUFFER",
                        severity="error",
                        message="vector_buffer missing clip_boundary despite active clip_to_boundary contract.",
                        suggested_fix=f"Set clip_boundary='{bnd_name}' or follow with vector_clip.",
                        patch_hint={"set_arg": {"clip_boundary": bnd_name}},
                    )
                )

        # 5c. raster_reproject explicit resampling & data_kind match (ADR-0011 + B09)
        if tool == "raster_reproject":
            resampling = str(args.get("resampling") or "").lower()
            dk = in_meta.get("data_kind", "continuous_raster")
            if not resampling:
                rec = "bilinear" if dk == "continuous_raster" else "nearest"
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_MISSING_RESAMPLING",
                        severity="error",
                        message="raster_reproject requires an explicit resampling method (gdal-mcp ADR-0011).",
                        suggested_fix=f"Specify resampling='{rec}' matching data_kind='{dk}'.",
                        patch_hint={"set_arg": {"resampling": rec}},
                    )
                )
            elif dk == "continuous_raster" and resampling in ("nearest", "mode"):
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_RESAMPLING_MISMATCH",
                        severity="error",
                        message=f"Resampling '{resampling}' is invalid for continuous raster '{in_layer}'.",
                        suggested_fix="Use resampling='bilinear' or 'cubic' for continuous rasters.",
                        patch_hint={"set_arg": {"resampling": "bilinear"}},
                    )
                )
            elif dk == "categorical_raster" and resampling in ("bilinear", "cubic", "lanczos"):
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_RESAMPLING_MISMATCH",
                        severity="error",
                        message=f"Resampling '{resampling}' corrupts categorical raster '{in_layer}'.",
                        suggested_fix="Use resampling='nearest' or 'mode' for categorical rasters.",
                        patch_hint={"set_arg": {"resampling": "nearest"}},
                    )
                )

        # 5d. raster_stats NoData mask guard
        if tool == "raster_stats" and in_meta.get("nodata") is not None and not args.get("mask_nodata"):
            diags.append(
                GeographicDiagnostic(
                    code="MCP_UNMASKED_NODATA",
                    severity="error",
                    message=f"raster_stats called on '{in_layer}' (nodata={in_meta['nodata']}) without mask_nodata=True.",
                    suggested_fix="Pass mask_nodata=True to exclude NoData pixels from statistics.",
                    patch_hint={"set_arg": {"mask_nodata": True}},
                )
            )

        # 5e. qgis_processing_sjoin CRS alignment, predicate direction, zero-match preservation
        if tool == "qgis_processing_sjoin":
            l_meta = self._layer_meta(args.get("left_layer"))
            r_meta = self._layer_meta(args.get("right_layer"))
            if l_meta.get("crs") and r_meta.get("crs") and l_meta["crs"] != r_meta["crs"]:
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_SJOIN_CRS_MISMATCH",
                        severity="error",
                        message=f"sjoin CRS mismatch: left={l_meta['crs']} vs right={r_meta['crs']}.",
                        suggested_fix=f"Reproject right_layer to {l_meta['crs']} before spatial join.",
                        patch_hint={"reproject_right": l_meta["crs"]},
                    )
                )
            pred = str(args.get("predicate", ""))
            if l_meta.get("geometry_type") == "Point" and r_meta.get("geometry_type") == "Polygon" and pred == "contains":
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_INVERTED_PREDICATE",
                        severity="error",
                        message="Point layer cannot 'contains' Polygon layer in sjoin.",
                        suggested_fix="Change predicate from 'contains' to 'within'.",
                        patch_hint={"set_arg": {"predicate": "within"}},
                    )
                )
            if args.get("how") == "inner" and (contract is None or contract.has_constraint("one_output_row_per_source")):
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_INNER_SJOIN_DROPS_ZEROS",
                        severity="error",
                        message="how='inner' drops zero-match source features, violating one_output_row_per_source.",
                        suggested_fix="Change how='left' to preserve all source features.",
                        patch_hint={"set_arg": {"how": "left"}},
                    )
                )

        # 5f. qgis_processing_overlay geometry validity guard
        if tool == "qgis_processing_overlay":
            l_meta = self._layer_meta(args.get("left_layer"))
            r_meta = self._layer_meta(args.get("right_layer"))
            if l_meta.get("is_valid") is False or r_meta.get("is_valid") is False:
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_INVALID_GEOMETRY_OVERLAY",
                        severity="error",
                        message="Overlay input contains invalid/self-intersecting geometries.",
                        suggested_fix="Repair geometries (make_valid=True / v.clean) before overlay.",
                        patch_hint={"repair_invalid_inputs": True},
                    )
                )

        # 5g. qgis_processing_slope on geographic CRS DEM
        if tool == "qgis_processing_slope":
            if _is_geographic_crs(in_meta.get("crs")):
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_SLOPE_GEOGRAPHIC_DEM",
                        severity="error",
                        message=f"Slope computed on geographic DEM ({in_meta.get('crs')}).",
                        suggested_fix="Reproject DEM to projected CRS (e.g., EPSG:32619) with bilinear resampling first.",
                        patch_hint={"reproject_raster_input": "EPSG:32619"},
                    )
                )

        # 5h. Euclidean shortcut when network_distance_required
        if tool == "vector_distance" and contract and contract.has_constraint("network_distance_required"):
            diags.append(
                GeographicDiagnostic(
                    code="MCP_NETWORK_SHORTCUT",
                    severity="error",
                    message="Direct Euclidean vector_distance violates network_distance_required.",
                    suggested_fix="Use qgis_network_shortest_path over the street network graph.",
                    patch_hint={"switch_tool": "qgis_network_shortest_path"},
                )
            )

        return diags

    def validate_postconditions(
        self,
        req: JsonRpcRequest,
        resp: JsonRpcResponse,
        contract: GeoContract | None = None,
    ) -> list[GeographicDiagnostic]:
        """Verify tool output assertions after backend execution."""
        if resp.is_protocol_error or resp.is_tool_error:
            return [
                GeographicDiagnostic(
                    code="MCP_TOOL_EXECUTION_ERROR",
                    severity="error",
                    message="Underlying MCP tool returned an error response.",
                    suggested_fix="Inspect tool arguments and rollback state.",
                )
            ]

        diags: list[GeographicDiagnostic] = []
        text = ""
        if resp.result and resp.result.get("content"):
            text = resp.result["content"][0].get("text", "")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {}

        if isinstance(payload, dict):
            for metric_key in ("distance_m", "travel_min", "area_m2"):
                if metric_key in payload and isinstance(payload[metric_key], (int, float)) and payload[metric_key] < 0:
                    diags.append(
                        GeographicDiagnostic(
                            code="MCP_NEGATIVE_METRIC_OUTPUT",
                            severity="error",
                            message=f"Output metric '{metric_key}' is negative ({payload[metric_key]}).",
                            suggested_fix="Ensure non-negative metric calculation.",
                        )
                    )
            if contract and contract.has_constraint("clip_to_boundary") and payload.get("clipped") is False:
                diags.append(
                    GeographicDiagnostic(
                        code="MCP_POST_UNCLIPPED",
                        severity="error",
                        message="Output geometry was not clipped to boundary.",
                        suggested_fix="Apply vector_clip to boundary.",
                    )
                )
        return diags

    def _default_auto_repair(
        self,
        req: JsonRpcRequest,
        diags: list[GeographicDiagnostic],
    ) -> JsonRpcRequest:
        """Deterministic geographic self-healer applying structured diagnostic patch hints."""
        new_req = copy.deepcopy(req)
        args = dict(new_req.params.get("arguments") or {})

        for d in diags:
            hint = d.patch_hint
            if "switch_tool" in hint:
                new_req.params["name"] = hint["switch_tool"]
                if hint["switch_tool"] == "reject_task":
                    args = {"reason": hint.get("reason", d.message)}
                new_req.params["arguments"] = args
                return new_req
            if "set_arg" in hint:
                args.update(hint["set_arg"])
            if "store_justifications" in hint:
                for prompt_name in hint["store_justifications"]:
                    if prompt_name == "justify_crs_selection":
                        choice = str(args.get("target_crs") or "EPSG:3857")
                        self.reflection_gate.store_justification(
                            domain="crs_datum",
                            intent="Auto-healed contract-compliant projected CRS selection",
                            alternatives=["EPSG:3857", "EPSG:32619"],
                            choice=choice,
                            tradeoffs="Selected projected metric CRS per contract",
                        )
                    elif prompt_name == "justify_resampling_method":
                        choice = str(args.get("resampling") or "bilinear")
                        self.reflection_gate.store_justification(
                            domain="resampling",
                            intent="Auto-healed data-kind matched resampling",
                            alternatives=["bilinear", "nearest"],
                            choice=choice,
                            tradeoffs="Matched resampling kernel to raster data kind",
                        )
            if "reproject_input" in hint and args.get("input_layer"):
                src = args["input_layer"]
                target_crs = hint["reproject_input"]
                out_name = f"{src}_proj"
                sub_req = JsonRpcRequest(
                    id=f"{req.id}-reproj",
                    method="tools/call",
                    params={
                        "name": "vector_reproject",
                        "arguments": {"input_layer": src, "output_layer": out_name, "target_crs": target_crs},
                    },
                )
                self.backend.handle_request(sub_req)
                self.revision_guard.bump_revision(out_name, self.backend.layers[out_name])
                args["input_layer"] = out_name
                if "revision" in args:
                    args["revision"] = self.revision_guard.revision
            if "reproject_right" in hint and args.get("right_layer"):
                src = args["right_layer"]
                target_crs = hint["reproject_right"]
                out_name = f"{src}_aligned"
                sub_req = JsonRpcRequest(
                    id=f"{req.id}-align",
                    method="tools/call",
                    params={
                        "name": "vector_reproject",
                        "arguments": {"input_layer": src, "output_layer": out_name, "target_crs": target_crs},
                    },
                )
                self.backend.handle_request(sub_req)
                self.revision_guard.bump_revision(out_name, self.backend.layers[out_name])
                args["right_layer"] = out_name
            if "reproject_raster_input" in hint and args.get("input_layer"):
                src = args["input_layer"]
                target_crs = hint["reproject_raster_input"]
                out_name = f"{src}_proj"
                sub_req = JsonRpcRequest(
                    id=f"{req.id}-rreproj",
                    method="tools/call",
                    params={
                        "name": "raster_reproject",
                        "arguments": {
                            "input_layer": src,
                            "output_layer": out_name,
                            "target_crs": target_crs,
                            "resampling": "bilinear",
                        },
                    },
                )
                self.backend.handle_request(sub_req)
                self.revision_guard.bump_revision(out_name, self.backend.layers[out_name])
                args["input_layer"] = out_name
            if hint.get("repair_invalid_inputs"):
                for k in ("left_layer", "right_layer"):
                    lname = args.get(k)
                    if lname and self._layer_meta(lname).get("is_valid") is False:
                        self.backend.layers[lname]["is_valid"] = True
                        self.revision_guard.layers.setdefault(lname, {})["is_valid"] = True

        new_req.params["arguments"] = args
        return new_req

    def execute_with_healing(
        self,
        req: JsonRpcRequest,
        *,
        contract: GeoContract | None = None,
        repair_fn: Callable[[JsonRpcRequest, list[GeographicDiagnostic]], JsonRpcRequest] | None = None,
        max_rounds: int | None = None,
    ) -> ProxyExecutionResult:
        """Execute an MCP request through pre/post verification and bounded self-healing (N <= 3)."""
        budget = self.max_rounds if max_rounds is None else min(max_rounds, 3)
        cp = self.revision_guard.create_checkpoint(label="pre-exec")
        current_req = copy.deepcopy(req)
        diags_history: list[list[GeographicDiagnostic]] = []
        trace: list[dict[str, Any]] = []
        healer = repair_fn or self._default_auto_repair

        for round_idx in range(budget + 1):
            pre_diags = self.validate_preconditions(current_req, contract=contract)
            if pre_diags:
                diags_history.append(pre_diags)
                trace.append({"round": round_idx, "stage": "precondition_blocked", "codes": [d.code for d in pre_diags]})
                if round_idx >= budget:
                    self.revision_guard.rollback(cp.checkpoint_id)
                    err_resp = make_tool_result(
                        current_req.id,
                        {"error": "Bounded self-healing exhausted; state rolled back.", "diagnostics": [d.to_dict() for d in pre_diags]},
                        is_error=True,
                    )
                    return ProxyExecutionResult(False, round_idx, True, current_req, err_resp, diags_history, trace)
                current_req = healer(current_req, pre_diags)
                continue

            # Dispatch to backend
            resp = self.backend.handle_request(current_req)
            post_diags = self.validate_postconditions(current_req, resp, contract=contract)
            if not post_diags:
                trace.append({"round": round_idx, "stage": "accepted", "tool": current_req.params.get("name")})
                return ProxyExecutionResult(True, round_idx, False, current_req, resp, diags_history, trace)

            diags_history.append(post_diags)
            trace.append({"round": round_idx, "stage": "postcondition_failed", "codes": [d.code for d in post_diags]})
            if round_idx >= budget:
                self.revision_guard.rollback(cp.checkpoint_id)
                return ProxyExecutionResult(False, round_idx, True, current_req, resp, diags_history, trace)
            current_req = healer(current_req, post_diags)

        self.revision_guard.rollback(cp.checkpoint_id)
        return ProxyExecutionResult(
            False,
            budget,
            True,
            current_req,
            make_tool_result(current_req.id, {"error": "Unexpected termination"}, is_error=True),
            diags_history,
            trace,
        )
