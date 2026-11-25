# GeoContract (`geocontract`)

**Spatial Contracts & Verifiable Geospatial Agent Middleware**

GeoContract turns fluent but fragile geospatial code and MCP tool calls into
verifiable spatial analysis workflows grounded in explicit geographic contracts
`τ = (q, D, Y, C, M⁺, M⁻)` and three-layer verification (`Vs ∪ Vr ∪ Vt`).

## Modules (D2-P1 – D2-P7)
1. **D2-P1 `geocontract.dsl`** — Declarative Spatial Contract Schema (JSON/YAML),
   36 standard templates across 9 spatial analysis families, and NL→contract compiler.
2. **D2-P2 `geocontract.lint` (`geolint`)** — Static Python AST spatial linter
   detecting 28 geographic anti-patterns with SARIF 2.1.0 output.
3. **D2-P3 `geocontract.runtime`** — Low-intrusion runtime spatial invariant probes,
   semantic verifier (`Vt`), close-value epsilon guard, and bidirectional `reject_task` guard.
4. **D2-P4 `geocontract.mcp`** — Transparent QGIS-MCP & GDAL-MCP JSON-RPC 2.0 proxy
   with Revision Guard, SHA-256 reflection gate, checkpoints/rollback, and bounded self-healing (`Rmax <= 3`).
5. **D2-P5 `geocontract.catalog`** — Local millisecond inverted index & knowledge graph
   over 340 spatial operators (314 GRASS + GDAL + 26 QGIS/GeoContract).
6. **D2-P6 `geocontract.provenance`** — W3C PROV-JSON (Member Submission) & STAC
   Processing Extension v1.2.0 lineage DAG with SHA-256 fingerprints, HTML/Markdown audit reports,
   and replayable Python scripts.
7. **D2-P7 `geocontract.benchmark`** — 160-case adversarial Near-Miss benchmark suite
   and automated comparative evaluation harness (bare execution vs. GeoContract intercept & repair).

## Quickstart
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m geocontract --help
PYTHONPATH=src python3 -m geocontract.lint.sarif --help
```
