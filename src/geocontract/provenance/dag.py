"""Traceable execution lineage DAG aligned with W3C PROV-JSON (Member Submission 2013-04-24) (D2-P6)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from geocontract._version import __version__


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_sha256(source: str | bytes | Path) -> str:
    """Compute SHA-256 hex digest of a file path, bytes, or UTF-8 string."""
    h = hashlib.sha256()
    if isinstance(source, Path) and source.is_file():
        with source.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    if isinstance(source, str) and len(source) < 512 and "\n" not in source and Path(source).is_file():
        return compute_sha256(Path(source))
    raw = source if isinstance(source, bytes) else str(source).encode("utf-8")
    h.update(raw)
    return h.hexdigest()


@dataclass
class LineageEntity:
    entity_id: str
    label: str
    role: str  # "input" | "intermediate" | "output" | "contract"
    sha256: str
    crs: str | None = None
    geometry_type: str | None = None
    path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageActivity:
    activity_id: str
    activity_type: str  # "OperatorCall" | "VerificationPass" | "RepairRound"
    tool: str
    tool_version: str
    start_time: str
    end_time: str
    parameters: dict[str, Any] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    status: str = "accepted"
    repair_round: int = 0


class LineageDAG:
    """Records spatial execution entities, activities, SHA-256 fingerprints, and repair traces."""

    def __init__(
        self,
        run_id: str,
        *,
        contract_id: str | None = None,
        agent_label: str = f"geocontract/{__version__}",
    ) -> None:
        self.run_id = run_id
        self.contract_id = contract_id
        self.agent_id = "geo:agent_geocontract"
        self.agent_label = agent_label
        self.created_at = utc_now_rfc3339()
        self.entities: dict[str, LineageEntity] = {}
        self.activities: list[LineageActivity] = []
        self._entity_order: list[str] = []

    def register_entity(
        self,
        entity_id: str,
        *,
        label: str,
        role: str,
        payload_or_path: str | bytes | Path,
        crs: str | None = None,
        geometry_type: str | None = None,
        path: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> LineageEntity:
        eid = entity_id if ":" in entity_id else f"geo:{entity_id}"
        ent = LineageEntity(
            entity_id=eid,
            label=label,
            role=role,
            sha256=compute_sha256(payload_or_path),
            crs=crs,
            geometry_type=geometry_type,
            path=path or (str(payload_or_path) if isinstance(payload_or_path, Path) else None),
            extra=dict(extra or {}),
        )
        self.entities[eid] = ent
        if eid not in self._entity_order:
            self._entity_order.append(eid)
        return ent

    def record_activity(
        self,
        activity_id: str,
        *,
        activity_type: str = "OperatorCall",
        tool: str,
        tool_version: str = __version__,
        parameters: dict[str, Any] | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        violations: list[dict[str, Any]] | None = None,
        status: str = "accepted",
        repair_round: int = 0,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> LineageActivity:
        aid = activity_id if ":" in activity_id else f"geo:{activity_id}"
        now = utc_now_rfc3339()
        norm_in = [i if ":" in i else f"geo:{i}" for i in (inputs or [])]
        norm_out = [o if ":" in o else f"geo:{o}" for o in (outputs or [])]
        act = LineageActivity(
            activity_id=aid,
            activity_type=activity_type,
            tool=tool,
            tool_version=tool_version,
            start_time=start_time or now,
            end_time=end_time or now,
            parameters=dict(parameters or {}),
            inputs=norm_in,
            outputs=norm_out,
            violations=list(violations or []),
            status=status,
            repair_round=repair_round,
        )
        self.activities.append(act)
        return act

    def to_prov_json(self) -> dict[str, Any]:
        """Serialize lineage DAG to W3C PROV-JSON (Member Submission 2013-04-24)."""
        prov_entities: dict[str, dict[str, Any]] = {}
        for eid in self._entity_order:
            e = self.entities[eid]
            attrs: dict[str, Any] = {
                "prov:type": "prov:Collection" if e.role == "input" else "prov:Entity",
                "prov:label": e.label,
                "geo:role": e.role,
                "geo:sha256": e.sha256,
            }
            if e.crs:
                attrs["geo:crs"] = e.crs
            if e.geometry_type:
                attrs["geo:geometry_type"] = e.geometry_type
            if e.path:
                attrs["geo:path"] = e.path
            for k, v in e.extra.items():
                attrs[f"geo:{k}"] = v
            prov_entities[eid] = attrs

        prov_activities: dict[str, dict[str, Any]] = {}
        used: dict[str, dict[str, Any]] = {}
        was_generated_by: dict[str, dict[str, Any]] = {}
        was_associated_with: dict[str, dict[str, Any]] = {}
        was_derived_from: dict[str, dict[str, Any]] = {}
        was_informed_by: dict[str, dict[str, Any]] = {}

        u_idx = g_idx = a_idx = d_idx = i_idx = 0
        prev_aid: str | None = None

        for act in self.activities:
            prov_activities[act.activity_id] = {
                "prov:type": f"geo:{act.activity_type}",
                "prov:startTime": act.start_time,
                "prov:endTime": act.end_time,
                "geo:tool": act.tool,
                "geo:tool_version": act.tool_version,
                "geo:status": act.status,
                "geo:repair_round": act.repair_round,
                "geo:parameters": json.dumps(act.parameters, sort_keys=True, ensure_ascii=False),
                "geo:violation_count": len(act.violations),
            }
            a_idx += 1
            assoc: dict[str, Any] = {
                "prov:activity": act.activity_id,
                "prov:agent": self.agent_id,
            }
            if self.contract_id:
                assoc["prov:plan"] = f"geo:{self.contract_id}"
            was_associated_with[f"_:a{a_idx}"] = assoc

            if prev_aid is not None:
                i_idx += 1
                was_informed_by[f"_:i{i_idx}"] = {
                    "prov:informed": act.activity_id,
                    "prov:informant": prev_aid,
                }
            prev_aid = act.activity_id

            for inp in act.inputs:
                u_idx += 1
                used[f"_:u{u_idx}"] = {"prov:activity": act.activity_id, "prov:entity": inp}

            for out in act.outputs:
                g_idx += 1
                was_generated_by[f"_:g{g_idx}"] = {"prov:entity": out, "prov:activity": act.activity_id}
                for inp in act.inputs:
                    d_idx += 1
                    deriv: dict[str, Any] = {
                        "prov:generatedEntity": out,
                        "prov:usedEntity": inp,
                    }
                    if act.repair_round > 0 or act.activity_type == "RepairRound":
                        deriv["prov:type"] = "prov:Revision"
                    was_derived_from[f"_:d{d_idx}"] = deriv

        return {
            "prefix": {
                "geo": "https://geocontract.org/ns/prov#",
                "prov": "http://www.w3.org/ns/prov#",
            },
            "entity": prov_entities,
            "activity": prov_activities,
            "agent": {
                self.agent_id: {
                    "prov:type": "prov:SoftwareAgent",
                    "prov:label": self.agent_label,
                }
            },
            "used": used,
            "wasGeneratedBy": was_generated_by,
            "wasAssociatedWith": was_associated_with,
            "wasDerivedFrom": was_derived_from,
            "wasInformedBy": was_informed_by,
        }
