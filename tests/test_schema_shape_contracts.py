import json
from datetime import UTC, datetime
from pathlib import Path

from sinergy_financial_os import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    ValuationPolicy,
    ValuationRule,
)
from sinergy_financial_os.snapshot import (
    LiquidityHorizonState,
    capture_financial_snapshot_v2,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _snapshot_dict() -> dict:
    ledger = ReportingLedger("USD")
    ledger.register_account(
        ReportingAccountSpec(
            "asset:cash",
            "Cash",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "HARD_EXTERNAL_ASSET",
        )
    )
    ledger.register_account(
        ReportingAccountSpec(
            "equity:capital",
            "Capital",
            AccountClass.EQUITY,
            ConsolidationClass.EXTERNAL,
            "EQUITY_ACCOUNT",
        )
    )
    ledger.post(
        event_id="capital-1",
        reference="capital-ref-1",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest="ab" * 32,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    policy = ValuationPolicy(
        "policy-v1",
        "USD",
        NOW,
        (
            ValuationRule(
                "HARD_EXTERNAL_ASSET",
                "1",
                "1",
                "1",
                "BANK_BALANCE",
            ),
        ),
    )
    snapshot = capture_financial_snapshot_v2(
        ledger,
        policy,
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=(
            LiquidityHorizonState(1, "100", "0"),
            LiquidityHorizonState(4, "100", "0"),
            LiquidityHorizonState(8, "100", "0"),
        ),
    )
    return snapshot.to_dict()


def test_financial_snapshot_runtime_emits_every_required_v2_schema_field() -> None:
    schema = json.loads(
        (ROOT / "schemas/financial_snapshot_v2.schema.json").read_text(encoding="utf-8")
    )
    payload = _snapshot_dict()
    assert set(schema["required"]) == set(payload)
    assert payload["schema"] == "financial.snapshot/v2"


def test_financial_snapshot_runtime_does_not_emit_undeclared_top_level_fields() -> None:
    schema = json.loads(
        (ROOT / "schemas/financial_snapshot_v2.schema.json").read_text(encoding="utf-8")
    )
    payload = _snapshot_dict()
    assert set(payload) <= set(schema["properties"])
