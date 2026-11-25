"""QGIS-MCP Revision Guard, Checkpoints, and gdal-mcp Reflection Gate (D2-P4).

Implements:
1. ``RevisionGuard``: Revisioned snapshot tracking, ``since_revision`` stale-write
   rejection, checkpoint/rollback, 2–32 KiB ``qgis_context`` byte budget, and
   repeated-call no-progress detection (GISAgentBench B04).
2. ``ReflectionGate``: Epistemic reflection middleware inspired by gdal-mcp 1.1.3
   requiring SHA-256 cached structured justifications before methodology-sensitive
   CRS or resampling calls.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Checkpoint:
    checkpoint_id: str
    revision: int
    layers_state: dict[str, dict[str, Any]]


class RevisionGuard:
    """Tracks live project revision, enforces stale-revision rejection, and manages rollbacks."""

    MAX_CONTEXT_BYTES = 32 * 1024  # QGIS-MCP v0.4.8: 2-32 KiB budget

    def __init__(self, initial_layers: dict[str, dict[str, Any]] | None = None) -> None:
        self.revision: int = 1
        self.layers: dict[str, dict[str, Any]] = copy.deepcopy(initial_layers or {})
        self.deleted_layers: list[str] = []
        self.checkpoints: list[Checkpoint] = []
        self._recent_call_fingerprints: dict[str, int] = {}

    def snapshot_context(
        self,
        *,
        since_revision: int | None = None,
        byte_budget: int = MAX_CONTEXT_BYTES,
    ) -> dict[str, Any]:
        budget = min(max(2048, byte_budget), self.MAX_CONTEXT_BYTES)
        if since_revision is not None and since_revision == self.revision:
            changed = {}
        else:
            changed = copy.deepcopy(self.layers)
        pack = {
            "revision": self.revision,
            "since_revision": since_revision,
            "layers": changed,
            "deleted_layers": list(self.deleted_layers),
            "byte_budget": budget,
        }
        encoded = json.dumps(pack, ensure_ascii=False).encode("utf-8")
        if len(encoded) > budget:
            # Trim layer metadata to summaries to obey strict byte budget
            pack["layers"] = {
                k: {"crs": v.get("crs"), "geometry_type": v.get("geometry_type")}
                for k, v in changed.items()
            }
            pack["truncated_to_summary"] = True
        return pack

    def check_revision(self, claimed_revision: int | None) -> tuple[bool, str]:
        if claimed_revision is None:
            return True, "ok"
        if claimed_revision != self.revision:
            return (
                False,
                f"Stale revision guard triggered: caller sent revision={claimed_revision}, "
                f"current project revision={self.revision}. Refresh qgis_context before writing.",
            )
        return True, "ok"

    def create_checkpoint(self, label: str = "auto") -> Checkpoint:
        cp = Checkpoint(
            checkpoint_id=f"cp-{self.revision}-{label}-{len(self.checkpoints)}",
            revision=self.revision,
            layers_state=copy.deepcopy(self.layers),
        )
        self.checkpoints.append(cp)
        return cp

    def rollback(self, checkpoint_id: str | None = None) -> Checkpoint:
        if not self.checkpoints:
            raise RuntimeError("No checkpoints available for rollback")
        if checkpoint_id is None:
            cp = self.checkpoints.pop()
        else:
            matches = [c for c in self.checkpoints if c.checkpoint_id == checkpoint_id]
            if not matches:
                raise KeyError(f"Checkpoint '{checkpoint_id}' not found")
            cp = matches[-1]
        self.layers = copy.deepcopy(cp.layers_state)
        self.revision = cp.revision
        return cp

    def bump_revision(self, layer_name: str, layer_meta: dict[str, Any]) -> int:
        self.layers[layer_name] = copy.deepcopy(layer_meta)
        self.revision += 1
        return self.revision

    def check_no_progress_loop(self, tool_name: str, arguments: dict[str, Any], *, max_repeats: int = 2) -> tuple[bool, str]:
        """Detect repeated identical failing calls (GISAgentBench B04)."""
        fp = hashlib.sha256(
            json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        count = self._recent_call_fingerprints.get(fp, 0) + 1
        self._recent_call_fingerprints[fp] = count
        if count > max_repeats:
            return (
                False,
                f"No-progress loop detected: identical call to '{tool_name}' repeated {count} times.",
            )
        return True, "ok"

    def reset_call_history(self) -> None:
        self._recent_call_fingerprints.clear()


@dataclass
class JustificationRecord:
    domain: str
    intent: str
    alternatives: list[str]
    choice: str
    tradeoffs: str
    confidence: float
    digest: str = ""

    def compute_digest(self) -> str:
        payload = json.dumps(
            {
                "domain": self.domain,
                "intent": self.intent,
                "alternatives": sorted(self.alternatives),
                "choice": self.choice,
                "tradeoffs": self.tradeoffs,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ReflectionGate:
    """gdal-mcp 1.1.3 style epistemic reflection gate with SHA-256 justification cache."""

    GATED_TOOLS: dict[str, list[str]] = {
        "raster_reproject": ["crs_datum", "resampling"],
        "vector_reproject": ["crs_datum"],
    }

    DOMAIN_PROMPTS: dict[str, str] = {
        "crs_datum": "justify_crs_selection",
        "resampling": "justify_resampling_method",
    }

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], JustificationRecord] = {}  # (domain, choice) -> record
        self._by_digest: dict[str, JustificationRecord] = {}

    def store_justification(
        self,
        *,
        domain: str,
        intent: str,
        alternatives: list[str],
        choice: str,
        tradeoffs: str,
        confidence: float = 0.9,
    ) -> JustificationRecord:
        if not intent or not choice or not tradeoffs:
            raise ValueError("Justification requires non-empty intent, choice, and tradeoffs")
        rec = JustificationRecord(
            domain=domain,
            intent=intent,
            alternatives=list(alternatives),
            choice=choice,
            tradeoffs=tradeoffs,
            confidence=confidence,
        )
        rec.digest = rec.compute_digest()
        self._cache[(domain, choice.lower())] = rec
        self._by_digest[rec.digest] = rec
        return rec

    def check_call(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, list[str]]:
        """Return (allowed, missing_prompts) for a methodology-sensitive tool call."""
        domains = self.GATED_TOOLS.get(tool_name, [])
        if not domains:
            return True, []

        missing_prompts: list[str] = []
        for dom in domains:
            choice = ""
            if dom == "crs_datum":
                choice = str(arguments.get("target_crs", "")).lower()
            elif dom == "resampling":
                choice = str(arguments.get("resampling", "")).lower()
            if (dom, choice) not in self._cache:
                missing_prompts.append(self.DOMAIN_PROMPTS[dom])
        return (len(missing_prompts) == 0), missing_prompts
