"""Unit tests for D2-P1 GeoContract DSL schema and JSON/YAML validation."""

import tempfile
import unittest
from pathlib import Path

from geocontract.dsl.schema import (
    ContractValidationError,
    DatasetSpec,
    GeoContract,
    OutputSpec,
    SpatialConstraint,
    dump_contract,
    load_contract,
    validate_contract_dict,
)


def _sample_contract() -> GeoContract:
    return GeoContract(
        contract_id="gc-buffer-001",
        version="1.0.0",
        family="buffer_counting",
        query="Count transit stops within 500m of each school in Boston.",
        datasets=[
            DatasetSpec(
                name="schools",
                path="data/schools.geojson",
                role="source",
                geometry_type="Point",
                crs="EPSG:4326",
                fields=["school_id", "name"],
                row_count=125,
            ),
            DatasetSpec(
                name="stops",
                path="data/stops.geojson",
                role="target",
                geometry_type="Point",
                crs="EPSG:4326",
                fields=["stop_id", "route"],
                row_count=1800,
            ),
        ],
        output=OutputSpec(
            path="out/school_stops.csv",
            format="csv",
            required_columns=["school_id", "stop_count"],
            id_column="school_id",
            unique_id=True,
            row_count_rule="equal_to_source",
            expected_crs="EPSG:26986",
            metric_unit="meters",
            value_ranges={"stop_count": {"min": 0, "max": None}},
        ),
        constraints=[
            SpatialConstraint("crs_projected_required", params={"target_crs": "EPSG:26986"}),
            SpatialConstraint("one_output_row_per_source"),
            SpatialConstraint("nonnegative_counts"),
        ],
        allowed_methods=["to_crs", "buffer", "sjoin", "groupby"],
        forbidden_shortcuts=["buffer_on_geographic_crs", "inner_sjoin_dropping_zeros"],
    )


class TestGeoContractSchema(unittest.TestCase):
    def test_valid_contract_json_and_yaml_roundtrip(self) -> None:
        c = _sample_contract()
        self.assertEqual(validate_contract_dict(c.to_dict()), [])

        c_from_json = load_contract(c.to_json(), fmt="json")
        c_from_yaml = load_contract(c.to_yaml(), fmt="yaml")
        self.assertEqual(c_from_json.to_dict(), c.to_dict())
        self.assertEqual(c_from_yaml.to_dict(), c.to_dict())
        self.assertTrue(c.has_constraint("crs_projected_required"))
        self.assertEqual(c.all_known_fields(), {"school_id", "name", "stop_id", "route"})

    def test_dump_and_reload_files(self) -> None:
        c = _sample_contract()
        with tempfile.TemporaryDirectory() as tmp:
            jpath = dump_contract(c, Path(tmp) / "contract.json")
            ypath = dump_contract(c, Path(tmp) / "contract.yaml")
            self.assertEqual(load_contract(jpath).contract_id, "gc-buffer-001")
            self.assertEqual(load_contract(ypath).family, "buffer_counting")

    def test_rejects_invalid_crs_and_unknown_constraint(self) -> None:
        raw = _sample_contract().to_dict()
        raw["datasets"][0]["crs"] = "WGS84_INVALID"
        with self.assertRaises(ContractValidationError):
            validate_contract_dict(raw)

        raw2 = _sample_contract().to_dict()
        raw2["constraints"].append({"name": "totally_made_up_guard"})
        with self.assertRaises(ContractValidationError):
            validate_contract_dict(raw2)

    def test_rejects_method_overlap_and_bad_bounds(self) -> None:
        raw = _sample_contract().to_dict()
        raw["forbidden_shortcuts"].append("buffer")
        with self.assertRaises(ContractValidationError):
            validate_contract_dict(raw)

        raw2 = _sample_contract().to_dict()
        raw2["output"]["value_ranges"] = {"ratio": {"min": 2.0, "max": 1.0}}
        with self.assertRaises(ContractValidationError):
            validate_contract_dict(raw2)

    def test_rejects_repair_rounds_over_3(self) -> None:
        raw = _sample_contract().to_dict()
        raw["repair_policy"] = {"max_rounds": 5, "rollback_on_failure": True}
        with self.assertRaises(ContractValidationError):
            validate_contract_dict(raw)


if __name__ == "__main__":
    unittest.main()
