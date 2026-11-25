"""GeoContract DSL package (D2-P1)."""

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
    "dump_contract",
    "load_contract",
    "validate_contract_dict",
]
