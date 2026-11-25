"""Declarative Spatial Contract Schema (GeoContract DSL).

Implements the 6-tuple spatial task contract ``τ = (q, D, Y, C, M+, M-)``
inspired by GeoContra (arXiv:2605.00782v1, CC-BY 4.0), extended with:
- ``reject_task`` guard (GeoBenchX / GeoNatureAgent, arXiv:2606.12821)
- ``clip_to_boundary`` guard (GeoContract extension inspired by GISAgentBench's
  ``clip_point_buffers_to_containing_polygons``)
- GISAgentBench practitioner caveats (CRS, boundary ambiguity, topology, NoData, unit mismatch).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

VALID_FAMILIES: tuple[str, ...] = (
    "buffer_counting",
    "spatial_joins",
    "nearest_neighbor",
    "network_accessibility",
    "overlay_areas",
    "raster_sampling",
    "zonal_statistics",
    "topology_quality",
    "multi_step_workflow",
)

VALID_GEOMETRY_TYPES: tuple[str, ...] = (
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
    "Raster",
    "Graph",
    "Table",
    "Any",
)

KNOWN_CONSTRAINTS: frozenset[str] = frozenset(
    {
        # GeoContra §4.1 explicit constraints
        "crs_projected_required",
        "one_output_row_per_source",
        "nonnegative_counts",
        "network_distance_required",
        "travel_time_unit_minutes",
        # GeoContra §4.3 / GISAgentBench caveats
        "crs_aligned_required",
        "no_invented_fields",
        "valid_geometry_required",
        "nodata_mask_required",
        "ratios_in_unit_interval",
        "nonnegative_metrics",
        "unique_id_required",
        "predicate_direction_checked",
        "operation_order_enforced",
        "resampling_matches_data_kind",
        "header_resolution_required",
        "boundary_predicate_explicit",
        "output_file_required",
        # GeoContract-defined guard (inspired by GISAgentBench)
        "clip_to_boundary",
        # GeoBenchX / GeoNatureAgent guard
        "reject_task",
        "close_value_epsilon_guard",
        "conservation_of_area",
        "conservation_of_rows",
    }
)

CRS_PATTERN = re.compile(r"^(EPSG|ESRI|OGC|IGNF):[A-Za-z0-9_]+$|^PROJ:.+|^WKT:.+")

CONTRACT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GeoContract",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "contract_id",
        "version",
        "family",
        "query",
        "datasets",
        "output",
        "constraints",
        "allowed_methods",
        "forbidden_shortcuts",
    ],
    "properties": {
        "contract_id": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+(\.\d+)?$"},
        "family": {"type": "string", "enum": list(VALID_FAMILIES)},
        "query": {"type": "string", "minLength": 1},
        "datasets": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "path", "role", "geometry_type", "crs"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "role": {
                        "type": "string",
                        "enum": ["source", "target", "boundary", "network", "raster", "reference"],
                    },
                    "geometry_type": {"type": "string", "enum": list(VALID_GEOMETRY_TYPES)},
                    "crs": {"type": "string", "minLength": 1},
                    "fields": {"type": "array", "items": {"type": "string"}},
                    "row_count": {"type": ["integer", "null"], "minimum": 0},
                    "nodata": {"type": ["number", "string", "null"]},
                    "resolution": {"type": ["number", "null"], "exclusiveMinimum": 0},
                    "data_kind": {
                        "type": "string",
                        "enum": ["vector", "continuous_raster", "categorical_raster", "graph", "table"],
                    },
                    "display_only": {"type": "boolean"},
                },
            },
        },
        "output": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path", "format", "required_columns"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "format": {
                    "type": "string",
                    "enum": ["csv", "geojson", "gpkg", "parquet", "geotiff", "json"],
                },
                "required_columns": {"type": "array", "items": {"type": "string"}},
                "id_column": {"type": ["string", "null"]},
                "unique_id": {"type": "boolean"},
                "row_count_rule": {
                    "type": "string",
                    "enum": ["any_nonempty", "equal_to_source", "lte_source", "exact", "allow_empty"],
                },
                "expected_rows": {"type": ["integer", "null"], "minimum": 0},
                "expected_crs": {"type": ["string", "null"]},
                "metric_unit": {"type": ["string", "null"]},
                "value_ranges": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "min": {"type": ["number", "null"]},
                            "max": {"type": ["number", "null"]},
                        },
                        "additionalProperties": False,
                    },
                },
            },
        },
        "constraints": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "severity": {"type": "string", "enum": ["error", "warning"]},
                    "params": {"type": "object"},
                    "provenance": {"type": "string"},
                },
            },
        },
        "allowed_methods": {"type": "array", "items": {"type": "string"}},
        "forbidden_shortcuts": {"type": "array", "items": {"type": "string"}},
        "repair_policy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "max_rounds": {"type": "integer", "minimum": 0, "maximum": 3},
                "rollback_on_failure": {"type": "boolean"},
            },
        },
        "reject_policy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "unsolvable_triggers": {"type": "array", "items": {"type": "string"}},
                "bidirectional_check": {"type": "boolean"},
            },
        },
        "metadata": {"type": "object"},
    },
}


class ContractValidationError(ValueError):
    """Raised when a GeoContract fails JSON Schema or semantic validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or [message]


@dataclass
class DatasetSpec:
    name: str
    path: str
    role: str
    geometry_type: str
    crs: str
    fields: list[str] = field(default_factory=list)
    row_count: int | None = None
    nodata: float | int | str | None = None
    resolution: float | None = None
    data_kind: str = "vector"
    display_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "role": self.role,
            "geometry_type": self.geometry_type,
            "crs": self.crs,
            "fields": list(self.fields),
            "data_kind": self.data_kind,
            "display_only": self.display_only,
        }
        if self.row_count is not None:
            d["row_count"] = self.row_count
        if self.nodata is not None:
            d["nodata"] = self.nodata
        if self.resolution is not None:
            d["resolution"] = self.resolution
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DatasetSpec:
        return cls(
            name=raw["name"],
            path=raw["path"],
            role=raw["role"],
            geometry_type=raw["geometry_type"],
            crs=raw["crs"],
            fields=list(raw.get("fields", [])),
            row_count=raw.get("row_count"),
            nodata=raw.get("nodata"),
            resolution=raw.get("resolution"),
            data_kind=raw.get("data_kind", "vector"),
            display_only=bool(raw.get("display_only", False)),
        )


@dataclass
class OutputSpec:
    path: str
    format: str
    required_columns: list[str] = field(default_factory=list)
    id_column: str | None = None
    unique_id: bool = True
    row_count_rule: str = "any_nonempty"
    expected_rows: int | None = None
    expected_crs: str | None = None
    metric_unit: str | None = None
    value_ranges: dict[str, dict[str, float | None]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "path": self.path,
            "format": self.format,
            "required_columns": list(self.required_columns),
            "unique_id": self.unique_id,
            "row_count_rule": self.row_count_rule,
        }
        if self.id_column is not None:
            d["id_column"] = self.id_column
        if self.expected_rows is not None:
            d["expected_rows"] = self.expected_rows
        if self.expected_crs is not None:
            d["expected_crs"] = self.expected_crs
        if self.metric_unit is not None:
            d["metric_unit"] = self.metric_unit
        if self.value_ranges:
            d["value_ranges"] = dict(self.value_ranges)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> OutputSpec:
        return cls(
            path=raw["path"],
            format=raw["format"],
            required_columns=list(raw.get("required_columns", [])),
            id_column=raw.get("id_column"),
            unique_id=bool(raw.get("unique_id", True)),
            row_count_rule=raw.get("row_count_rule", "any_nonempty"),
            expected_rows=raw.get("expected_rows"),
            expected_crs=raw.get("expected_crs"),
            metric_unit=raw.get("metric_unit"),
            value_ranges=dict(raw.get("value_ranges", {})),
        )


@dataclass
class SpatialConstraint:
    name: str
    severity: str = "error"
    params: dict[str, Any] = field(default_factory=dict)
    provenance: str = "geocontract"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "severity": self.severity,
            "provenance": self.provenance,
        }
        if self.params:
            d["params"] = dict(self.params)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SpatialConstraint:
        return cls(
            name=raw["name"],
            severity=raw.get("severity", "error"),
            params=dict(raw.get("params", {})),
            provenance=raw.get("provenance", "geocontract"),
        )


@dataclass
class GeoContract:
    """Six-tuple spatial task contract τ = (q, D, Y, C, M+, M-)."""

    contract_id: str
    version: str
    family: str
    query: str
    datasets: list[DatasetSpec]
    output: OutputSpec
    constraints: list[SpatialConstraint]
    allowed_methods: list[str]
    forbidden_shortcuts: list[str]
    repair_policy: dict[str, Any] = field(
        default_factory=lambda: {"max_rounds": 3, "rollback_on_failure": True}
    )
    reject_policy: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "unsolvable_triggers": [
                "missing_entity",
                "display_only_layer",
                "missing_indicator",
                "missing_crs_metadata",
            ],
            "bidirectional_check": True,
        }
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_constraint(self, name: str) -> bool:
        return any(c.name == name for c in self.constraints)

    def get_constraint(self, name: str) -> SpatialConstraint | None:
        for c in self.constraints:
            if c.name == name:
                return c
        return None

    def all_known_fields(self) -> set[str]:
        fields: set[str] = set()
        for ds in self.datasets:
            fields.update(ds.fields)
        return fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "family": self.family,
            "query": self.query,
            "datasets": [d.to_dict() for d in self.datasets],
            "output": self.output.to_dict(),
            "constraints": [c.to_dict() for c in self.constraints],
            "allowed_methods": list(self.allowed_methods),
            "forbidden_shortcuts": list(self.forbidden_shortcuts),
            "repair_policy": dict(self.repair_policy),
            "reject_policy": dict(self.reject_policy),
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, strict: bool = True) -> GeoContract:
        if strict:
            validate_contract_dict(raw)
        return cls(
            contract_id=raw["contract_id"],
            version=raw["version"],
            family=raw["family"],
            query=raw["query"],
            datasets=[DatasetSpec.from_dict(d) for d in raw["datasets"]],
            output=OutputSpec.from_dict(raw["output"]),
            constraints=[SpatialConstraint.from_dict(c) for c in raw["constraints"]],
            allowed_methods=list(raw["allowed_methods"]),
            forbidden_shortcuts=list(raw["forbidden_shortcuts"]),
            repair_policy=dict(
                raw.get("repair_policy", {"max_rounds": 3, "rollback_on_failure": True})
            ),
            reject_policy=dict(
                raw.get(
                    "reject_policy",
                    {
                        "enabled": True,
                        "unsolvable_triggers": [
                            "missing_entity",
                            "display_only_layer",
                            "missing_indicator",
                        ],
                        "bidirectional_check": True,
                    },
                )
            ),
            metadata=dict(raw.get("metadata", {})),
        )


def validate_contract_dict(raw: dict[str, Any], *, strict_constraints: bool = True) -> list[str]:
    """Validate a raw dict against JSON Schema and semantic rules.

    Returns an empty list on success; raises ``ContractValidationError`` on failure.
    """
    validator = jsonschema.Draft202012Validator(CONTRACT_JSON_SCHEMA)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(raw), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) or "<root>"
        errors.append(f"Schema error at {loc}: {err.message}")

    if not errors:
        # Semantic checks beyond JSON Schema
        seen_names: set[str] = set()
        for ds in raw["datasets"]:
            if ds["name"] in seen_names:
                errors.append(f"Duplicate dataset name: {ds['name']}")
            seen_names.add(ds["name"])
            if not CRS_PATTERN.match(ds["crs"]):
                errors.append(f"Invalid CRS identifier '{ds['crs']}' on dataset '{ds['name']}'")

        out = raw["output"]
        if out.get("row_count_rule") == "exact" and out.get("expected_rows") is None:
            errors.append("output.expected_rows is required when row_count_rule == 'exact'")
        if out.get("expected_crs") and not CRS_PATTERN.match(out["expected_crs"]):
            errors.append(f"Invalid output.expected_crs: {out['expected_crs']}")

        for col, bounds in out.get("value_ranges", {}).items():
            lo = bounds.get("min")
            hi = bounds.get("max")
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"output.value_ranges.{col}: min ({lo}) > max ({hi})")

        if strict_constraints:
            for c in raw["constraints"]:
                if c["name"] not in KNOWN_CONSTRAINTS:
                    errors.append(f"Unknown spatial constraint: '{c['name']}'")

        # Mutual exclusion between M+ and M-
        overlap = set(raw["allowed_methods"]) & set(raw["forbidden_shortcuts"])
        if overlap:
            errors.append(f"Methods cannot appear in both M+ and M-: {sorted(overlap)}")

    if errors:
        raise ContractValidationError(
            f"GeoContract validation failed with {len(errors)} error(s): " + "; ".join(errors),
            errors=errors,
        )
    return []


def load_contract(source: str | Path, *, fmt: str | None = None, strict: bool = True) -> GeoContract:
    """Load and strictly validate a GeoContract from a JSON/YAML string or file path."""
    path_obj: Path | None = None
    if isinstance(source, Path):
        path_obj = source
        text = source.read_text(encoding="utf-8")
    else:
        stripped = source.strip()
        if not stripped.startswith("{") and "\n" not in stripped and Path(stripped).is_file():
            path_obj = Path(stripped)
            text = path_obj.read_text(encoding="utf-8")
        else:
            text = source

    detected = fmt
    if detected is None:
        if path_obj is not None:
            suffix = path_obj.suffix.lower()
            detected = "json" if suffix == ".json" else "yaml"
        else:
            detected = "json" if text.lstrip().startswith("{") else "yaml"

    if detected == "json":
        raw = json.loads(text)
    elif detected in ("yaml", "yml"):
        raw = yaml.safe_load(text)
    else:
        raise ContractValidationError(f"Unsupported contract format: {detected}")

    if not isinstance(raw, dict):
        raise ContractValidationError("Contract document must deserialize to a mapping/object")

    return GeoContract.from_dict(raw, strict=strict)


def dump_contract(contract: GeoContract, dest: str | Path, *, fmt: str | None = None) -> Path:
    """Serialize a validated GeoContract to JSON or YAML on disk."""
    validate_contract_dict(contract.to_dict())
    out_path = Path(dest)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    detected = fmt or ("json" if out_path.suffix.lower() == ".json" else "yaml")
    content = contract.to_json() if detected == "json" else contract.to_yaml()
    out_path.write_text(content, encoding="utf-8")
    return out_path
