"""Human-auditable HTML/Markdown evidence report and replayable script exporter (D2-P6)."""

from __future__ import annotations

import html
import json
from pathlib import Path

from geocontract.provenance.dag import LineageDAG
from geocontract.provenance.stac import export_stac_item


def render_markdown_audit(dag: LineageDAG) -> str:
    """Render a human-auditable Markdown evidence report for a LineageDAG."""
    lines: list[str] = [
        f"# GeoContract Audit Evidence Report — `{dag.run_id}`",
        "",
        f"- **Contract ID**: `{dag.contract_id or 'N/A'}`",
        f"- **Agent**: `{dag.agent_label}`",
        f"- **Created (UTC)**: `{dag.created_at}`",
        f"- **Entities Tracked**: {len(dag.entities)}",
        f"- **Activities / Rounds**: {len(dag.activities)}",
        "",
        "## 1. Data & Artifact Fingerprints (SHA-256)",
        "",
        "| Entity ID | Label | Role | CRS | Geometry | SHA-256 |",
        "|---|---|---|---|---|---|",
    ]
    for eid, ent in dag.entities.items():
        lines.append(
            f"| `{eid}` | {ent.label} | {ent.role} | `{ent.crs or '-'}` | "
            f"`{ent.geometry_type or '-'}` | `{ent.sha256[:16]}...` |"
        )

    lines.extend(
        [
            "",
            "## 2. Execution, Verification & Repair Trace",
            "",
            "| Activity | Type | Tool | Round | Status | Violations | Parameters |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for act in dag.activities:
        params_s = json.dumps(act.parameters, ensure_ascii=False, sort_keys=True)
        lines.append(
            f"| `{act.activity_id}` | {act.activity_type} | `{act.tool}` | "
            f"{act.repair_round} | **{act.status}** | {len(act.violations)} | `{params_s}` |"
        )

    all_viols = [(act.activity_id, v) for act in dag.activities for v in act.violations]
    if all_viols:
        lines.extend(["", "## 3. Intercepted Violations & Diagnostics", ""])
        for aid, v in all_viols:
            lines.append(f"- `{aid}` **[{v.get('code', 'VIOLATION')}]**: {v.get('message', '')}")

    lines.append("")
    return "\n".join(lines)


def render_html_audit(dag: LineageDAG) -> str:
    """Render a standalone, self-contained HTML5 audit report."""
    esc = html.escape
    ent_rows = "\n".join(
        f"<tr><td><code>{esc(eid)}</code></td><td>{esc(e.label)}</td><td>{esc(e.role)}</td>"
        f"<td><code>{esc(e.crs or '-')}</code></td><td><code>{esc(e.sha256[:20])}...</code></td></tr>"
        for eid, e in dag.entities.items()
    )
    act_rows = "\n".join(
        f"<tr><td><code>{esc(a.activity_id)}</code></td><td>{esc(a.activity_type)}</td>"
        f"<td><code>{esc(a.tool)}</code></td><td>{a.repair_round}</td>"
        f"<td><span class='badge badge-{esc(a.status)}'>{esc(a.status)}</span></td>"
        f"<td>{len(a.violations)}</td></tr>"
        for a in dag.activities
    )
    prov_pretty = esc(json.dumps(dag.to_prov_json(), indent=2, ensure_ascii=False))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GeoContract Audit Report — {esc(dag.run_id)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 2rem auto; padding: 0 1rem; color: #1e293b; line-height: 1.5; }}
  h1, h2 {{ color: #0f172a; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; font-size: 0.92rem; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 0.5rem 0.7rem; text-align: left; }}
  th {{ background: #f1f5f9; }}
  code {{ background: #f8fafc; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.88em; }}
  .badge {{ padding: 0.15rem 0.5rem; border-radius: 999px; font-weight: 600; font-size: 0.82em; }}
  .badge-accepted {{ background: #dcfce7; color: #166534; }}
  .badge-rejected, .badge-failed {{ background: #fee2e2; color: #991b1b; }}
  pre {{ background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.82rem; }}
</style>
</head>
<body>
<h1>GeoContract Audit Report: <code>{esc(dag.run_id)}</code></h1>
<p><strong>Contract:</strong> <code>{esc(dag.contract_id or 'N/A')}</code> &middot;
<strong>Agent:</strong> <code>{esc(dag.agent_label)}</code> &middot;
<strong>UTC:</strong> <code>{esc(dag.created_at)}</code></p>
<h2>1. Entity SHA-256 Fingerprints</h2>
<table><thead><tr><th>Entity</th><th>Label</th><th>Role</th><th>CRS</th><th>SHA-256</th></tr></thead>
<tbody>{ent_rows}</tbody></table>
<h2>2. Execution &amp; Repair Trace</h2>
<table><thead><tr><th>Activity</th><th>Type</th><th>Tool</th><th>Round</th><th>Status</th><th>Violations</th></tr></thead>
<tbody>{act_rows}</tbody></table>
<h2>3. W3C PROV-JSON (Member Submission)</h2>
<pre>{prov_pretty}</pre>
</body>
</html>
"""


def render_replay_script(dag: LineageDAG) -> str:
    """Generate a standalone, syntactically valid Python replay script from the lineage DAG."""
    steps = [
        {
            "activity_id": act.activity_id,
            "tool": act.tool,
            "parameters": act.parameters,
            "inputs": act.inputs,
            "outputs": act.outputs,
            "repair_round": act.repair_round,
            "status": act.status,
        }
        for act in dag.activities
    ]
    fingerprints = {
        eid: {"path": e.path, "sha256": e.sha256, "role": e.role}
        for eid, e in dag.entities.items()
    }
    return f'''#!/usr/bin/env python3
"""Auto-generated GeoContract reproducible replay script for run {dag.run_id}."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RUN_ID = {dag.run_id!r}
CONTRACT_ID = {dag.contract_id!r}
EXPECTED_FINGERPRINTS = json.loads({json.dumps(fingerprints, ensure_ascii=False)!r})
REPLAY_STEPS = json.loads({json.dumps(steps, ensure_ascii=False)!r})


def verify_input_fingerprints() -> list[str]:
    """Verify SHA-256 digests of any existing local input files."""
    mismatches: list[str] = []
    for eid, meta in EXPECTED_FINGERPRINTS.items():
        if meta.get("role") != "input" or not meta.get("path"):
            continue
        p = Path(meta["path"])
        if not p.is_file():
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            mismatches.append(f"{{eid}}: expected {{meta['sha256']}}, got {{digest}}")
    return mismatches


def replay(executor=None) -> list[dict]:
    """Replay verified workflow steps using an optional callable executor(tool, params)."""
    mismatches = verify_input_fingerprints()
    if mismatches:
        raise RuntimeError("Input SHA-256 mismatch: " + "; ".join(mismatches))
    log = []
    for step in REPLAY_STEPS:
        if step["status"] != "accepted":
            continue
        result = executor(step["tool"], step["parameters"]) if executor else {{"simulated": True}}
        log.append({{"activity_id": step["activity_id"], "tool": step["tool"], "result": result}})
    return log


if __name__ == "__main__":
    print(json.dumps({{"run_id": RUN_ID, "replayed": replay()}}, indent=2, ensure_ascii=False))
'''


def export_audit_bundle(dag: LineageDAG, output_dir: str | Path) -> dict[str, Path]:
    """Export PROV-JSON, STAC Item, Markdown report, HTML report, and replay script."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "prov_json": out / f"{dag.run_id}.prov.json",
        "stac_json": out / f"{dag.run_id}.stac.json",
        "markdown": out / f"{dag.run_id}.audit.md",
        "html": out / f"{dag.run_id}.audit.html",
        "replay_py": out / f"{dag.run_id}.replay.py",
    }
    files["prov_json"].write_text(json.dumps(dag.to_prov_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files["stac_json"].write_text(json.dumps(export_stac_item(dag), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    files["markdown"].write_text(render_markdown_audit(dag), encoding="utf-8")
    files["html"].write_text(render_html_audit(dag), encoding="utf-8")
    files["replay_py"].write_text(render_replay_script(dag), encoding="utf-8")
    return files
