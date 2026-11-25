"""Verifiable QGIS-MCP & GDAL-MCP middleware package (D2-P4)."""

from geocontract.mcp.mock_server import MockGeoMCPServer
from geocontract.mcp.protocol import (
    SUPPORTED_PROTOCOL_VERSIONS,
    JsonRpcRequest,
    JsonRpcResponse,
    make_protocol_error,
    make_tool_call_request,
    make_tool_result,
)
from geocontract.mcp.proxy import GeographicDiagnostic, ProxyExecutionResult, VerifiableMCPProxy
from geocontract.mcp.revision_guard import Checkpoint, JustificationRecord, ReflectionGate, RevisionGuard

__all__ = [
    "SUPPORTED_PROTOCOL_VERSIONS",
    "Checkpoint",
    "GeographicDiagnostic",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JustificationRecord",
    "MockGeoMCPServer",
    "ProxyExecutionResult",
    "ReflectionGate",
    "RevisionGuard",
    "VerifiableMCPProxy",
    "make_protocol_error",
    "make_tool_call_request",
    "make_tool_result",
]
