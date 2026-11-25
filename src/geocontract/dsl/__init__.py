"""GeoContract DSL package (D2-P1)."""

from geocontract.dsl.compiler import compile_intent_to_contract
from geocontract.dsl.schema import (
    CONTRACT_JSON_SCHEMA,
    KNOWN_CONSTRAINTS,
    VALID_FAMILIES,
    VALID_GEOMETRY_TYPES,
    ContractValidationError,
    DatasetSpec,
    GeoContract,
    OutputSpec,
    SpatialConstraint,
    dump_contract,
    load_contract,
    validate_contract_dict,
)
from geocontract.dsl.templates import get_template, list_templates, template_counts_by_family

__all__ = [
    "CONTRACT_JSON_SCHEMA",
    "KNOWN_CONSTRAINTS",
    "VALID_FAMILIES",
    "VALID_GEOMETRY_TYPES",
    "ContractValidationError",
    "DatasetSpec",
    "GeoContract",
    "OutputSpec",
    "SpatialConstraint",
    "compile_intent_to_contract",
    "dump_contract",
    "get_template",
    "list_templates",
    "load_contract",
    "template_counts_by_family",
    "validate_contract_dict",
]
