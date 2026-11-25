# Third-Party Notices & Provenance Attribution

GeoContract (`geocontract`) is released under the MIT License. Its design,
anti-pattern taxonomy, operator metadata, and provenance schemas build on
openly documented specifications and academic literature audited in
`LICENSE_AUDIT.md` (2026-11-23). No closed-source or paywalled full-text
material was copied; no dependency on `AnacletoLAB/grape`, `ensmallen`, or
`embiggen` exists.

## Academic & Benchmark Attributions
- **GeoContra** (Xiao, Xiao & Zhang, arXiv:2605.00782v1, 2026-05-01, CC-BY 4.0):
  6-tuple spatial contract formalism `τ = (q, D, Y, C, M+, M-)`, three-layer
  verification (`Vs ∪ Vr ∪ Vt`), and bounded verifier-guided repair state machine.
  Note: Numeric repair cap `Rmax = 3` is a GeoContract engineering default; the
  paper defines `Rmax` symbolically.
- **GISAgentBench** (Pothuri, Jiang, Xu & Yang, arXiv:2608.01645v1, 2026-08-03, CC-BY 4.0):
  Practitioner caveat taxonomy (CRS misalignment, boundary ambiguity,
  geometry/topology errors, NoData, unit mismatch) and failure modes.
  `clip_to_boundary` is a GeoContract-defined guard inspired by
  `clip_point_buffers_to_containing_polygons` (not a GeoContra paper field).
- **GeoNatureAgent Benchmark** (Diaz-Ireland et al., arXiv:2606.12821, 2026, CC-BY 4.0;
  code repository Apache-2.0): `reject_task` guard (originally from GeoBenchX)
  and close-value comparison anti-patterns.
- **Axis Spatial Geospatial AI Benchmark** (2026-10-16, Index v1.0): Summary-level
  attribution for bidirectional refusal verification and code-based output checks.
- **Geospatial Agentic Services (GAS)** (Li et al., *Annals of GIS*, 2026,
  DOI:10.1080/19475683.2026.2738374): Abstract-level citation only.

## Protocol, Operator & Provenance Standards
- **Model Context Protocol (MCP)** Specification (2025-03-26 / 2025-11-25 / 2026-07-28,
  modelcontextprotocol.io): JSON-RPC 2.0 tool-call message shapes.
- **QGIS-MCP** (Aaa2122/QGIS-MCP v0.4.8, MIT): Revisioned snapshot and
  `since_revision` revision-guard interception concepts.
- **gdal-mcp** (Wayfinder-Foundry/gdal-mcp 1.1.3, MIT, Copyright (c) 2025 Jordan T Godau):
  Epistemic reflection middleware (`justify_*` + SHA-256 justification cache) concepts.
- **GRASS GIS Manual** (grass-stable, OSGeo, GPL documentation ecosystem) and
  **GDAL Programs Documentation** (gdal.org, MIT/X11 ecosystem): Factual operator
  names and one-line descriptions in `operator_catalog.json`.
- **W3C PROV-JSON** (W3C Member Submission, 2013-04-24; PROV-DM W3C Recommendation):
  Lineage DAG serialization.
- **STAC Processing Extension v1.2.0** (Candidate, `stac-extensions/processing`):
  STAC lineage metadata mapping (no official "STAC Workflow Extension" exists;
  DAG process definitions align with `stactask` / STACD concepts).
