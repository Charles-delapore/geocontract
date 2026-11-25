"""MCP JSON-RPC 2.0 protocol primitives (D2-P4).

Follows Model Context Protocol specifications 2025-03-26 / 2025-11-25 / 2026-07-28
(modelcontextprotocol.io): tool-level errors return ``result.isError: true``
whereas protocol-level errors return a top-level JSON-RPC ``error`` object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
    "2026-07-28",
)


@dataclass
class JsonRpcRequest:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.id is not None:
            d["id"] = self.id
        if self.params:
            d["params"] = dict(self.params)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> JsonRpcRequest:
        if raw.get("jsonrpc") != "2.0" or "method" not in raw:
            raise ValueError("Invalid JSON-RPC 2.0 request")
        return cls(
            method=str(raw["method"]),
            params=dict(raw.get("params") or {}),
            id=raw.get("id"),
        )


@dataclass
class JsonRpcResponse:
    id: int | str | None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    jsonrpc: str = "2.0"

    @property
    def is_protocol_error(self) -> bool:
        return self.error is not None

    @property
    def is_tool_error(self) -> bool:
        return bool(self.result and self.result.get("isError"))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = dict(self.error)
        else:
            d["result"] = dict(self.result or {})
        return d


def make_tool_call_request(
    req_id: int | str,
    tool_name: str,
    arguments: dict[str, Any],
) -> JsonRpcRequest:
    return JsonRpcRequest(
        id=req_id,
        method="tools/call",
        params={"name": tool_name, "arguments": dict(arguments)},
    )


def make_tool_result(
    req_id: int | str | None,
    payload: dict[str, Any] | str,
    *,
    is_error: bool = False,
    metadata: dict[str, Any] | None = None,
) -> JsonRpcResponse:
    import json

    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    res: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if metadata:
        res["_meta"] = dict(metadata)
    return JsonRpcResponse(id=req_id, result=res)


def make_protocol_error(
    req_id: int | str | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> JsonRpcResponse:
    err: dict[str, Any] = {"code": code, "message": message}
    if data:
        err["data"] = data
    return JsonRpcResponse(id=req_id, error=err)
