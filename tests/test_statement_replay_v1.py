from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os.account_registry_v1 import build_account_registry_v1
from sinergy_financial_os.accounting_close_v2 import build_accounting_close_v2
from sinergy_financial_os.accounting_period_v1 import AccountingPeriodV1, build_period_close_v1
from sinergy_financial_os.accounting_restatement_view_v1 import (
    AccountingRestatementOverlayV1,
    build_restated_period_view_v1,
)
from sinergy_financial_os.ledger_event_v2 import export_reporting_entry_as_ledger_event_v2
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.statement_replay_v1 import StatementReplayV1Error, build_statement_replay_v1
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule
from sinergy_financial_os.valuation_policy_artifact_v1 import build_valuation_policy_artifact_v1


REQ = "77" * 32
ACCOUNTING_POLICY = "55" * 32


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def specs():
    return (
        ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"),
        ReportingAccountSpec("equity", "External capital", AccountClass.EQUITY, ConsolidationClass.EXTERNAL, "EQUITY"),
        ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"),
        ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True),
        ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True),
    )


def book():
    ledger = ReportingLedger("USDC")
    for spec in specs():
        ledger.register_account(spec)
    return ledger


def valuation_policy():
    return ValuationPolicy(
        "statement-replay-policy-v1",
        "USDC",
        dt("2026-08-20T00:00:00Z"),
        (ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )


def horizons(amount: Decimal):
    return (
        LiquidityHorizonState(1, amount, Decimal("0")),
        LiquidityHorizonState(4, amount, Decimal("0")),
        LiquidityHorizonState(8, amount, Decimal("0")),
    )


def context():
    ledger = book()
    policy = valuation_policy()
    registry = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-20T00:01:00Z"), expected_ledger=ledger
    )
    policy_artifact = build_valuation_policy_artifact_v1(policy, generated_at=dt("2026-08-20T00:02:00Z"))

    capital = ledger.post(
        event_id="capital-001",
        reference="capital-ref-001",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("100")), ReportingLine("equity", credit=Decimal("100"))),
        evidence_digest="11" * 32,
        metadata={"economic_class": "EXTERNAL_CAPITAL"},
    )
    capital_event = export_reporting_entry_as_ledger_event_v2(
        capital, ledger, effective_at=dt("2026-08-20T00:30:00Z"), evidence_class="BANK"
    )
    snap0 = capture_financial_snapshot_v2(
        ledger,
        policy,
        as_of=dt("2026-08-20T01:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("100")),
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    )
    close0 = build_accounting_close_v2(
        [capital_event], snap0.to_dict(), close_id="close-0", closed_at=dt("2026-08-20T01:01:00Z"), requirement_registry_digest=REQ
    )
    period0 = AccountingPeriodV1(
        "period-0", dt("2026-08-20T00:00:00Z"), dt("2026-08-20T01:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", ACCOUNTING_POLICY, REQ
    )
    period_close0 = build_period_close_v1(
        period0, close0, financial_snapshot=snap0.to_dict(), sealed_ledger_events=[capital_event], closed_at=dt("2026-08-20T01:02:00Z")
    )

    revenue = ledger.post(
        event_id="revenue-erroneous-001",
        reference="invoice-duplicate-001",
        flow_type=FlowType.EXTERNAL_REVENUE,
        lines=(
            ReportingLine("cash", debit=Decimal("125")),
            ReportingLine("revenue", credit=Decimal("118")),
            ReportingLine("tax", credit=Decimal("5")),
            ReportingLine("refund", credit=Decimal("2")),
        ),
        evidence_digest="22" * 32,
        metadata={"economic_class": "PROJECT_REVENUE"},
    )
    revenue_event = export_reporting_entry_as_ledger_event_v2(
        revenue, ledger, effective_at=dt("2026-08-20T01:30:00Z"), evidence_class="PROJECT"
    )
    snap1 = capture_financial_snapshot_v2(
        ledger,
        policy,
        as_of=dt("2026-08-20T02:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("225")),
        previous_snapshot=snap0,
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    )
    events = [capital_event, revenue_event]
    close1 = build_accounting_close_v2(
        events, snap1.to_dict(), close_id="close-1", closed_at=dt("2026-08-20T02:01:00Z"), requirement_registry_digest=REQ
    )
    period1 = AccountingPeriodV1(
        "period-1", dt("2026-08-20T01:00:00Z"), dt("2026-08-20T02:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", ACCOUNTING_POLICY, REQ, period_close0.digest
    )
    period_close1 = build_period_close_v1(
        period1, close1, financial_snapshot=snap1.to_dict(), sealed_ledger_events=events, closed_at=dt("2026-08-20T02:02:00Z")
    )

    overlay = AccountingRestatementOverlayV1(
        overlay_id="overlay-revenue-duplicate-001",
        affected_period_id=period1.period_id,
        correction_target_period_id="period-2",
        original_period_close_digest=period_close1.digest,
        original_accounting_close_digest=close1.digest,
        original_ledger_event_digest="33" * 32,
        original_reporting_entry_digest=revenue.digest,
        correction_authorization_digest="44" * 32,
        period_chain_proof_digest="45" * 32,
        correction_period_close_digest="46" * 32,
        correction_accounting_close_digest="47" * 32,
        correction_ledger_event_digest="48" * 32,
        correction_reporting_entry_digest="49" * 32,
        generated_at=dt("2026-08-20T03:00:00Z"),
    )
    view = build_restated_period_view_v1(
        [overlay], view_id="restated-period-1-v1", generated_at=dt("2026-08-20T03:01:00Z")
    )
    return {
        "registry": registry,
        "policy_artifact": policy_artifact,
        "capital_event": capital_event,
        "revenue_event": revenue_event,
        "events": events,
        "snap0": snap0,
        "snap1": snap1,
        "close0": close0,
        "close1": close1,
        "period_close0": period_close0,
        "period_close1": period_close1,
        "period1": period1,
        "revenue": revenue,
        "overlay": overlay,
        "view": view,
    }


def replay(c):
    return build_statement_replay_v1(
        replay_id="statement-replay-001",
        period=c["period1"],
        period_close=c["period_close1"],
        accounting_close=c["close1"],
        financial_snapshot=c["snap1"].to_dict(),
        ledger_events=c["events"],
        account_registry=c["registry"],
        valuation_policy_artifact=c["policy_artifact"],
        restated_view=c["view"],
        restatement_overlays=[c["overlay"]],
        opening_period_close=c["period_close0"],
        opening_accounting_close=c["close0"],
        generated_at=dt("2026-08-20T03:02:00Z"),
    )


def test_replay_excludes_proven_erroneous_period_entry_and_preserves_opening_capital():
    c = context()
    result = replay(c)
    assert c["snap1"].hard_nav == Decimal("218")
    assert result.opening_sequence == 1
    assert result.closing_sequence == 2
    assert result.original_event_count == 2
    assert result.excluded_event_count == 1
    assert result.retained_event_count == 1
    assert result.hard_external_assets == Decimal("100")
    assert result.external_liabilities == Decimal("0")
    assert result.hard_nav == Decimal("100")
    assert result.liquid_nav == Decimal("100")
    assert result.economic_nav == Decimal("100")
    assert result.realized_external_revenue == Decimal("0")
    assert result.realized_external_pnl == Decimal("0")
    assert result.liquidity_metrics == "NOT_PERFORMED"
    assert result.distribution_metrics == "NOT_PERFORMED"
    assert result.to_dict()["hard_nav"] == "100"


def test_replay_refuses_exclusion_outside_affected_period():
    c = context()
    bad_overlay = AccountingRestatementOverlayV1(
        overlay_id="bad-overlay",
        affected_period_id=c["period1"].period_id,
        correction_target_period_id="period-2",
        original_period_close_digest=c["period_close1"].digest,
        original_accounting_close_digest=c["close1"].digest,
        original_ledger_event_digest="aa" * 32,
        original_reporting_entry_digest=c["capital_event"]["reporting_entry_digest"],
        correction_authorization_digest="ab" * 32,
        period_chain_proof_digest="ac" * 32,
        correction_period_close_digest="ad" * 32,
        correction_accounting_close_digest="ae" * 32,
        correction_ledger_event_digest="af" * 32,
        correction_reporting_entry_digest="b0" * 32,
        generated_at=dt("2026-08-20T03:00:00Z"),
    )
    bad_view = build_restated_period_view_v1(
        [bad_overlay], view_id="bad-view", generated_at=dt("2026-08-20T03:01:00Z")
    )
    with pytest.raises(StatementReplayV1Error, match="affected period"):
        build_statement_replay_v1(
            replay_id="bad-replay", period=c["period1"], period_close=c["period_close1"],
            accounting_close=c["close1"], financial_snapshot=c["snap1"].to_dict(), ledger_events=c["events"],
            account_registry=c["registry"], valuation_policy_artifact=c["policy_artifact"],
            restated_view=bad_view, restatement_overlays=[bad_overlay], opening_period_close=c["period_close0"],
            opening_accounting_close=c["close0"], generated_at=dt("2026-08-20T03:02:00Z")
        )


def test_replay_refuses_wrong_opening_close_context():
    c = context()
    with pytest.raises(StatementReplayV1Error, match="opening PeriodClose"):
        build_statement_replay_v1(
            replay_id="bad-opening", period=c["period1"], period_close=c["period_close1"],
            accounting_close=c["close1"], financial_snapshot=c["snap1"].to_dict(), ledger_events=c["events"],
            account_registry=c["registry"], valuation_policy_artifact=c["policy_artifact"],
            restated_view=c["view"], restatement_overlays=[c["overlay"]], opening_period_close=None,
            opening_accounting_close=None, generated_at=dt("2026-08-20T03:02:00Z")
        )
