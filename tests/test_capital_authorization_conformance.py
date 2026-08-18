import json
from datetime import UTC, datetime
from pathlib import Path

from sinergy_financial_os.capital_authorization import CapitalAuthorization


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/capital_authorization_v1_canonical.json"
EXPECTED_DIGEST = "1bf53290d288e2117ce9c339227669673658eed2c95d72dc2657236b11ae2140"


def test_financial_os_produces_exact_shared_capital_authorization_fixture() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    authorization = CapitalAuthorization(
        authorization_id="auth-funding-001",
        project_id="project-001",
        decision="APPROVED",
        decision_authority="HUMAN_COMMITTEE",
        funding_asset="USDC",
        approved_amount="1000.000",
        screening_digest="aa" * 32,
        financial_snapshot_digest="bb" * 32,
        valuation_policy_digest="cc" * 32,
        requirement_registry_digest="dd" * 32,
        decision_evidence_digest="ee" * 32,
        decided_at=datetime(2026, 8, 18, 19, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 18, 21, 0, tzinfo=UTC),
        financial_snapshot_sequence=42,
    )
    assert authorization.digest == EXPECTED_DIGEST
    assert authorization.to_dict() == expected
