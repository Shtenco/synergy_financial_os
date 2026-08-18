import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sinergy_financial_os.capital_authorization import CapitalAuthorization


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/capital_authorization_v1.schema.json"
NOW = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)


def _payload() -> dict:
    return CapitalAuthorization(
        authorization_id="auth-schema-001",
        project_id="project-001",
        decision="APPROVED",
        decision_authority="MULTISIG_GOVERNANCE",
        funding_asset="USDC",
        approved_amount="100.00",
        screening_digest="aa" * 32,
        financial_snapshot_digest="bb" * 32,
        valuation_policy_digest="cc" * 32,
        requirement_registry_digest="dd" * 32,
        decision_evidence_digest="ee" * 32,
        decided_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        financial_snapshot_sequence=7,
    ).to_dict()


def test_runtime_emits_exact_declared_shape() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = _payload()
    assert set(payload) == set(schema["required"])
    assert set(payload) <= set(schema["properties"])
    assert payload["schema"] == "capital.authorization/v1"


def test_schema_structurally_excludes_ai_and_embedded_payment_execution() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "AI" not in schema["properties"]["decision_authority"]["enum"]
    assert schema["properties"]["execution_authority"] == {
        "const": "SEPARATE_METAPAY_HANDOFF"
    }
    assert schema["properties"]["ai_authority"] == {"const": "NONE"}
