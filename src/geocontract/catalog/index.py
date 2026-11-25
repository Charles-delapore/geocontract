"""Millisecond local inverted index & spatial operator knowledge graph (D2-P5).

Indexes 340 spatial operators (314 GRASS+GDAL from Muse Wave 1 intake + 26 curated
QGIS/MCP/GeoContract operators) for O(1) ID lookup, inverted-index search across
name/description/geometry/CRS/pre-post conditions, and remediation chaining.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9_.:-]+")
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "operator_catalog.json"


def _tokenize(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall(text.lower()))
    expanded: set[str] = set(tokens)
    for t in tokens:
        for part in re.split(r"[._:\-]+", t):
            if len(part) >= 2:
                expanded.add(part)
    return expanded


@dataclass(frozen=True)
class OperatorNode:
    id: str
    name: str
    provider: str
    provenance_tier: str
    category: str
    input_geometry: str
    output_geometry: str
    crs_constraint: str
    preconditions: tuple[str, ...] = field(default_factory=tuple)
    postconditions: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    source_url: str = ""
    common_misuse: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "provenance_tier": self.provenance_tier,
            "category": self.category,
            "input_geometry": self.input_geometry,
            "output_geometry": self.output_geometry,
            "crs_constraint": self.crs_constraint,
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "description": self.description,
            "source_url": self.source_url,
        }


class OperatorKnowledgeGraph:
    """In-memory millisecond search index & precondition/postcondition graph."""

    def __init__(self, catalog_path: str | Path | None = None) -> None:
        path = Path(catalog_path) if catalog_path else _DEFAULT_CATALOG_PATH
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.metadata = {k: v for k, v in raw.items() if k != "operators"}
        self._by_id: dict[str, OperatorNode] = {}
        self._by_name: dict[str, list[str]] = defaultdict(list)
        self._token_index: dict[str, set[str]] = defaultdict(set)
        self._by_provider: dict[str, set[str]] = defaultdict(set)
        self._by_crs: dict[str, set[str]] = defaultdict(set)
        self._by_precond: dict[str, set[str]] = defaultdict(set)
        self._by_postcond: dict[str, set[str]] = defaultdict(set)

        for entry in raw["operators"]:
            node = OperatorNode(
                id=entry["id"],
                name=entry["name"],
                provider=entry.get("provider", "unknown"),
                provenance_tier=entry.get("provenance_tier", "muse_intake"),
                category=entry.get("category", ""),
                input_geometry=entry.get("input_geometry", ""),
                output_geometry=entry.get("output_geometry", ""),
                crs_constraint=entry.get("crs_constraint", "aligned_required"),
                preconditions=tuple(entry.get("preconditions", ())),
                postconditions=tuple(entry.get("postconditions", ())),
                description=entry.get("description_official", ""),
                source_url=entry.get("source_url", ""),
                common_misuse=entry.get("common_misuse", ""),
            )
            self._by_id[node.id] = node
            self._by_name[node.name.lower()].append(node.id)
            self._by_provider[node.provider.lower()].add(node.id)
            self._by_crs[node.crs_constraint.lower()].add(node.id)
            for p in node.preconditions:
                self._by_precond[p.lower()].add(node.id)
            for p in node.postconditions:
                self._by_postcond[p.lower()].add(node.id)

            searchable = " ".join(
                [
                    node.id,
                    node.name,
                    node.provider,
                    node.category,
                    node.input_geometry,
                    node.output_geometry,
                    node.crs_constraint,
                    node.description,
                    " ".join(node.preconditions),
                    " ".join(node.postconditions),
                ]
            )
            for tok in _tokenize(searchable):
                self._token_index[tok].add(node.id)

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, op_id_or_name: str) -> OperatorNode | None:
        if op_id_or_name in self._by_id:
            return self._by_id[op_id_or_name]
        matches = self._by_name.get(op_id_or_name.lower())
        if matches:
            return self._by_id[matches[0]]
        return None

    def search(
        self,
        query: str | None = None,
        *,
        provider: str | None = None,
        input_geometry: str | None = None,
        output_geometry: str | None = None,
        crs_constraint: str | None = None,
        precondition: str | None = None,
        postcondition: str | None = None,
        limit: int = 20,
    ) -> list[OperatorNode]:
        """Search operators in sub-millisecond time using inverted index intersection + scoring."""
        candidates: set[str] | None = None

        if provider:
            candidates = set(self._by_provider.get(provider.lower(), set()))
        if crs_constraint:
            s = self._by_crs.get(crs_constraint.lower(), set())
            candidates = s.copy() if candidates is None else (candidates & s)
        if precondition:
            s = self._by_precond.get(precondition.lower(), set())
            candidates = s.copy() if candidates is None else (candidates & s)
        if postcondition:
            s = self._by_postcond.get(postcondition.lower(), set())
            candidates = s.copy() if candidates is None else (candidates & s)

        q_tokens = _tokenize(query) if query else set()
        if q_tokens:
            token_hits: set[str] = set()
            for tok in q_tokens:
                token_hits |= self._token_index.get(tok, set())
            candidates = token_hits if candidates is None else (candidates & token_hits)

        if candidates is None:
            candidates = set(self._by_id.keys())

        scored: list[tuple[float, str, OperatorNode]] = []
        ig_low = input_geometry.lower() if input_geometry else None
        og_low = output_geometry.lower() if output_geometry else None
        q_low = (query or "").strip().lower()

        for oid in candidates:
            node = self._by_id[oid]
            if ig_low and ig_low not in node.input_geometry.lower():
                continue
            if og_low and og_low not in node.output_geometry.lower():
                continue

            score = 0.0
            if q_low:
                if node.id.lower() == q_low or node.name.lower() == q_low:
                    score += 100.0
                elif q_low in node.name.lower():
                    score += 40.0
                if q_tokens:
                    name_toks = _tokenize(node.name + " " + node.description)
                    score += 5.0 * len(q_tokens & name_toks)
            scored.append((score, node.id, node))

        scored.sort(key=lambda t: (-t[0], t[1]))
        return [t[2] for t in scored[:limit]]

    def find_remediation_operators(
        self,
        missing_precondition: str,
        *,
        geometry_hint: str | None = None,
        limit: int = 5,
    ) -> list[OperatorNode]:
        """Recommend operators whose postconditions satisfy a missing precondition."""
        target_post_map = {
            "crs_projected_required": "crs_projected_or_target",
            "crs_aligned_required": "crs_projected_or_target",
            "valid_geometry_required": "valid_geometry_required",
            "clip_to_boundary": "clip_to_boundary",
        }
        post = target_post_map.get(missing_precondition, missing_precondition)
        return self.search(
            postcondition=post,
            input_geometry=geometry_hint,
            limit=limit,
        )

    def summary_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"total": len(self._by_id)}
        for prov, ids in sorted(self._by_provider.items()):
            counts[prov] = len(ids)
        return counts


_CACHED_GRAPH: OperatorKnowledgeGraph | None = None


def get_operator_graph() -> OperatorKnowledgeGraph:
    global _CACHED_GRAPH
    if _CACHED_GRAPH is None:
        _CACHED_GRAPH = OperatorKnowledgeGraph()
    return _CACHED_GRAPH
