"""STAC Processing Extension v1.2.0 (Candidate) & stactask workflow DAG exporter (D2-P6).

Note: Per GEOCONTRACT_DSL_NOTES.md §6.1, no official "STAC Workflow Extension"
exists in stac-extensions. This module exports a standards-compliant STAC Item
using the official Processing Extension v1.2.0 (Candidate) plus a stactask-aligned
``process`` workflow definition capturing the execution DAG.
"""

from __future__ import annotations

from typing import Any

from geocontract._version import __version__
from geocontract.provenance.dag import LineageDAG

STAC_PROCESSING_EXT_URL = "https://stac-extensions.github.io/processing/v1.2.0/schema.json"


def export_stac_item(
    dag: LineageDAG,
    *,
    bbox: list[float] | None = None,
    geometry: dict[str, Any] | None = None,
    processing_level: str = "L2",
    facility: str = "GeoContract Offline Verifiable Runtime",
) -> dict[str, Any]:
    """Export a LineageDAG as a STAC Item conforming to Processing Extension v1.2.0."""
    software: dict[str, str] = {"geocontract": __version__}
    expression_steps: list[dict[str, Any]] = []
    lineage_lines: list[str] = []

    for act in dag.activities:
        software[act.tool] = act.tool_version
        expression_steps.append(
            {
                "id": act.activity_id,
                "tool": act.tool,
                "type": act.activity_type,
                "parameters": act.parameters,
                "inputs": act.inputs,
                "outputs": act.outputs,
                "status": act.status,
                "repair_round": act.repair_round,
            }
        )
        lineage_lines.append(
            f"- `{act.activity_id}` ({act.activity_type}): tool `{act.tool}` "
            f"[round={act.repair_round}, status={act.status}]"
        )

    assets: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    for eid, ent in dag.entities.items():
        short = eid.split(":", 1)[-1]
        href = ent.path or f"./{short}"
        if ent.role == "input":
            links.append(
                {
                    "rel": "derived_from",
                    "href": href,
                    "title": ent.label,
                    "geo:sha256": ent.sha256,
                }
            )
        else:
            roles = ["metadata"] if ent.role == "contract" else ["data"]
            assets[short] = {
                "href": href,
                "title": ent.label,
                "roles": roles,
                "geo:sha256": ent.sha256,
                "geo:crs": ent.crs,
            }

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [STAC_PROCESSING_EXT_URL],
        "id": dag.run_id,
        "bbox": bbox or [-180.0, -90.0, 180.0, 90.0],
        "geometry": geometry
        or {
            "type": "Polygon",
            "coordinates": [[[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]]],
        },
        "properties": {
            "datetime": dag.created_at,
            "created": dag.created_at,
            "processing:datetime": dag.activities[-1].end_time if dag.activities else dag.created_at,
            "processing:level": processing_level,
            "processing:facility": facility,
            "processing:version": dag.contract_id or __version__,
            "processing:software": software,
            "processing:lineage": "\n".join(lineage_lines) or "No processing activities recorded.",
            "processing:expression": {
                "format": "geocontract-dag-v1",
                "expression": expression_steps,
            },
        },
        "links": links,
        "assets": assets,
        # stactask-aligned workflow process definition (no official STAC Workflow Extension exists)
        "process": [
            {
                "description": f"GeoContract reproducible workflow for run {dag.run_id}",
                "workflow_options": {"contract_id": dag.contract_id, "verifiable": True},
                "tasks": [
                    {
                        "name": act.tool,
                        "parameters": act.parameters,
                        "repair_round": act.repair_round,
                    }
                    for act in dag.activities
                ],
            }
        ],
    }
