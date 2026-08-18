import json
from datetime import UTC, datetime
from pathlib import Path

from sinergy_financial_os.economic_cycle_trace import EconomicCycleTrace, make_reference


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/economic_cycle_trace_v1.schema.json"


def _payload() -> dict:
    return EconomicCycleTrace(
        cycle_id="cycle-schema-001",
        household_or_funding_subject="cohort-001",
        project_id="project-001",
        references=(
            make_reference(
                "FUNDING_STATE",
                digest="aa" * 32,
                subject_id="cohort-001",
                observed_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
            ),
        ),
    ).to_dict()


def test_runtime_emits_exact_declared_shape() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _payload()
    assert set(payload) == set(schema["required"])
    assert set(payload) <= set(schema["properties"])
    assert payload["schema"] == "economic.cycle-trace/v1"


def test_trace_schema_locks_non_authorizing_semantics() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["authority"] == {"const": "PROVENANCE_ONLY"}
    assert schema["properties"]["profit_recognition"] == {"const": "NOT_PERFORMED"}
    assert schema["properties"]["execution_authority"] == {"const": "NONE"}
