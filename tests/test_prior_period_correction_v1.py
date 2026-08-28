from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os.accounting_close_v2 import (
    build_accounting_close_v2,
    build_ledger_inclusion_proof_v2,
    verify_accounting_close_v2,
)
from sinergy_financial_os.accounting_period_chain_v1 import build_accounting_period_chain_proof_v1
from sinergy_financial_os.accounting_period_v1 import AccountingPeriodV1, build_period_close_v1
from sinergy_financial_os.authorized_prior_period_correction_v1 import (
    AuthorizedPriorPeriodCorrectionV1Error,
    post_authorized_prior_period_entry_void_v1,
)
from sinergy_financial_os.ledger_event_v2 import (
    export_reporting_entry_as_ledger_event_v2,
    ledger_event_v2_digest,
)
from sinergy_financial_os.prior_period_correction_v1 import PriorPeriodCorrectionAuthorizationV1
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.revenue_posting_v2 import (
    RevenuePostingAccountsV2,
    post_recognized_external_revenue_v2,
)
from sinergy_financial_os.revenue_recognition_v2 import RevenueRecognitionDecisionV2
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule


ROOT = Path(__file__).resolve().parents[1]
RECOGNITION = ROOT / "fixtures/conformance/revenue_recognition_v2_canonical.json"
REQ = "77" * 32
POLICY = "55" * 32


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def recognition() -> RevenueRecognitionDecisionV2:
    p = load(RECOGNITION)
    return RevenueRecognitionDecisionV2(
        recognition_id=p["recognition_id"], project_id=p["project_id"], decision=p["decision"],
        settlement_receipt_digest=p["settlement_receipt_digest"], capital_authorization_digest=p["capital_authorization_digest"],
        project_evidence_digest=p["project_evidence_digest"], counterparty_id=p["counterparty_id"],
        counterparty_relation=p["counterparty_relation"], counterparty_evidence_digest=p["counterparty_evidence_digest"],
        revenue_destination_id=p["revenue_destination_id"], contract_digest=p["contract_digest"], invoice_digest=p["invoice_digest"],
        invoice_reporting_amount=Decimal(p["invoice_reporting_amount"]), delivery_evidence_digest=p["delivery_evidence_digest"],
        accounting_policy_digest=p["accounting_policy_digest"], settlement_asset=p["settlement_asset"],
        settlement_amount=Decimal(p["settlement_amount"]), reporting_currency=p["reporting_currency"],
        fx_rate_to_reporting=Decimal(p["fx_rate_to_reporting"]), gross_reporting_amount=Decimal(p["gross_reporting_amount"]),
        tax_reporting_amount=Decimal(p["tax_reporting_amount"]), refund_reserve_reporting_amount=Decimal(p["refund_reserve_reporting_amount"]),
        recognized_reporting_amount=Decimal(p["recognized_reporting_amount"]), performance_state=p["performance_state"],
        dispute_state=p["dispute_state"], recognized_at=dt(p["recognized_at"]), blockers=tuple(p["blockers"]),
        fx_evidence_digest=p["fx_evidence_digest"], accounting_authority=p["accounting_authority"],
        ledger_posting_authority=p["ledger_posting_authority"], ai_authority=p["ai_authority"],
    )


def book() -> ReportingLedger:
    ledger = ReportingLedger("USDC")
    ledger.register_account(ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    ledger.register_account(ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"))
    ledger.register_account(ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    ledger.register_account(ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    return ledger


def valuation_policy() -> ValuationPolicy:
    return ValuationPolicy(
        "cycle-policy-v1", "USDC", dt("2026-08-19T10:29:00Z"),
        (ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )


def horizons(amount: Decimal):
    return (
        LiquidityHorizonState(1, amount, Decimal("0")),
        LiquidityHorizonState(4, amount, Decimal("0")),
        LiquidityHorizonState(8, amount, Decimal("0")),
    )


def original_closed_period():
    ledger = book()
    rec = recognition()
    original_entry = post_recognized_external_revenue_v2(
        ledger, rec, RevenuePostingAccountsV2("cash", "revenue", "tax", "refund"), event_id="revenue-event-001"
    )
    original_event = export_reporting_entry_as_ledger_event_v2(
        original_entry, ledger, effective_at=rec.recognized_at, evidence_class="PROJECT"
    )
    snap1 = capture_financial_snapshot_v2(
        ledger, valuation_policy(), as_of=dt("2026-08-19T11:00:00Z"), accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("125")), required_hard_nav_buffer=Decimal("0"), policy_mode="NORMAL"
    )
    close1 = build_accounting_close_v2(
        [original_event], snap1.to_dict(), close_id="close-period-n", closed_at=dt("2026-08-19T11:01:00Z"),
        requirement_registry_digest=REQ
    )
    proof1 = build_ledger_inclusion_proof_v2([original_event], snap1.to_dict(), event_index=0, close=close1)
    period1 = AccountingPeriodV1(
        "period-n", dt("2026-08-19T00:00:00Z"), dt("2026-08-19T11:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ
    )
    period_close1 = build_period_close_v1(
        period1, close1, financial_snapshot=snap1.to_dict(), sealed_ledger_events=[original_event],
        closed_at=dt("2026-08-19T11:02:00Z")
    )
    return ledger, rec, original_entry, original_event, snap1, close1, proof1, period1, period_close1


def empty_successor_close(ctx):
    ledger, _, _, original_event, snap1, _, _, _, period_close1 = ctx
    period2 = AccountingPeriodV1(
        "period-n-plus-1", dt("2026-08-19T11:00:00Z"), dt("2026-08-19T12:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close1.digest
    )
    snap2 = capture_financial_snapshot_v2(
        ledger, valuation_policy(), as_of=dt("2026-08-19T12:00:00Z"), accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("125")), previous_snapshot=snap1,
        required_hard_nav_buffer=Decimal("0"), policy_mode="NORMAL"
    )
    close2 = build_accounting_close_v2(
        [original_event], snap2.to_dict(), close_id="close-period-n-plus-1", closed_at=dt("2026-08-19T12:01:00Z"),
        requirement_registry_digest=REQ
    )
    period_close2 = build_period_close_v1(
        period2, close2, financial_snapshot=snap2.to_dict(), sealed_ledger_events=[original_event],
        closed_at=dt("2026-08-19T12:02:00Z")
    )
    return period2, snap2, close2, period_close2


def make_auth(ctx, target, chain, **changes):
    _, _, entry, event, _, close1, _, period1, period_close1 = ctx
    values = dict(
        authorization_id="prior-error-void-001", affected_period_id=period1.period_id, target_period_id=target.period_id,
        reason="DUPLICATE_ENTRY", original_period_close_digest=period_close1.digest,
        original_accounting_close_digest=close1.digest, original_ledger_event_digest=ledger_event_v2_digest(event),
        original_reporting_entry_digest=entry.digest, period_chain_proof_digest=chain.digest,
        correction_evidence_digest="88" * 32, decision_evidence_digest="99" * 32,
        accounting_policy_digest=POLICY, requirement_registry_digest=REQ,
        decision_authority="MULTISIG_GOVERNANCE", decided_at=dt("2026-08-19T12:10:00Z"),
        effective_at=dt("2026-08-19T12:20:00Z")
    )
    values.update(changes)
    return PriorPeriodCorrectionAuthorizationV1(**values)


def test_exact_prior_period_entry_void_changes_nav_but_not_current_period_pnl():
    ctx = original_closed_period()
    ledger, _, original_entry, original_event, snap1, close1, proof1, _, period_close1 = ctx
    _, snap2, _, period_close2 = empty_successor_close(ctx)
    target = AccountingPeriodV1(
        "period-n-plus-2", dt("2026-08-19T12:00:00Z"), dt("2026-08-19T14:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close2.digest
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1, period_close2], target, generated_at=dt("2026-08-19T12:05:00Z")
    )
    auth = make_auth(ctx, target, chain)
    old_entry_digest = original_entry.digest
    old_close_digest = close1.digest
    correction = post_authorized_prior_period_entry_void_v1(
        ledger, auth, target, chain, [period_close1, period_close2], close1, original_event, proof1,
        event_id="prior-error-void-event-001"
    )
    assert correction.flow_type == FlowType.INTERNAL
    assert correction.evidence_digest == auth.digest
    assert correction.metadata["current_period_pnl_treatment"] == "EXCLUDED_FROM_CURRENT_PERIOD_PNL"
    assert correction.metadata["restatement_required"] == "YES"
    assert original_entry.digest == old_entry_digest
    assert close1.digest == old_close_digest
    assert ledger.balance("cash") == Decimal("0")
    assert ledger.balance("revenue") == Decimal("0")
    assert ledger.balance("tax") == Decimal("0")
    assert ledger.balance("refund") == Decimal("0")

    correction_event = export_reporting_entry_as_ledger_event_v2(
        correction, ledger, effective_at=auth.effective_at, evidence_class="AUDITED"
    )
    snap3 = capture_financial_snapshot_v2(
        ledger, valuation_policy(), as_of=dt("2026-08-19T14:00:00Z"), accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("0")), previous_snapshot=snap2,
        required_hard_nav_buffer=Decimal("0"), policy_mode="DEFENSE"
    )
    assert snap2.hard_nav == Decimal("118")
    assert snap3.hard_nav == Decimal("0")
    assert snap3.realized_external_revenue == Decimal("0")
    assert snap3.realized_external_pnl == Decimal("0")
    assert snap3.hard_nav_surplus_after_capital == Decimal("-118")
    assert snap3.period_profit_budget == Decimal("0")
    close3 = build_accounting_close_v2(
        [original_event, correction_event], snap3.to_dict(), close_id="close-period-n-plus-2",
        closed_at=dt("2026-08-19T14:01:00Z"), requirement_registry_digest=REQ
    )
    assert verify_accounting_close_v2([original_event, correction_event], snap3.to_dict(), close3)
    period_close3 = build_period_close_v1(
        target, close3, financial_snapshot=snap3.to_dict(), sealed_ledger_events=[original_event, correction_event],
        adjustment_authorization_digests=(auth.digest,), closed_at=dt("2026-08-19T14:02:00Z")
    )
    assert period_close3.previous_period_close_digest == period_close2.digest
    assert period_close3.adjustment_authorization_digests == (auth.digest,)


def test_exact_void_is_one_shot_even_with_second_authorization():
    ctx = original_closed_period()
    ledger, _, _, event, _, close1, proof1, _, period_close1 = ctx
    target = AccountingPeriodV1(
        "period-n-plus-1", dt("2026-08-19T11:00:00Z"), dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close1.digest
    )
    chain = build_accounting_period_chain_proof_v1([period_close1], target, generated_at=dt("2026-08-19T11:05:00Z"))
    first = make_auth(ctx, target, chain, decided_at=dt("2026-08-19T11:10:00Z"), effective_at=dt("2026-08-19T11:20:00Z"))
    post_authorized_prior_period_entry_void_v1(
        ledger, first, target, chain, [period_close1], close1, event, proof1, event_id="void-1"
    )
    second = make_auth(
        ctx, target, chain, authorization_id="prior-error-void-002",
        decided_at=dt("2026-08-19T11:30:00Z"), effective_at=dt("2026-08-19T11:40:00Z")
    )
    with pytest.raises(AuthorizedPriorPeriodCorrectionV1Error, match="PRIOR_PERIOD_ENTRY_VOID"):
        post_authorized_prior_period_entry_void_v1(
            ledger, second, target, chain, [period_close1], close1, event, proof1, event_id="void-2"
        )


def test_exact_void_refuses_entry_already_consumed_by_real_post_close_adjustment():
    ctx = original_closed_period()
    ledger, _, entry, event, _, close1, proof1, _, period_close1 = ctx
    ledger.post(
        event_id="real-economic-adjustment", reference="real-adjustment-001", flow_type=FlowType.INTERNAL,
        lines=(ReportingLine("refund", debit=Decimal("1")), ReportingLine("cash", credit=Decimal("1"))),
        evidence_digest="aa" * 32,
        metadata={"economic_class":"REVENUE_POST_CLOSE_ADJUSTMENT","original_reporting_entry_digest":entry.digest}
    )
    target = AccountingPeriodV1(
        "period-n-plus-1", dt("2026-08-19T11:00:00Z"), dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close1.digest
    )
    chain = build_accounting_period_chain_proof_v1([period_close1], target, generated_at=dt("2026-08-19T11:05:00Z"))
    auth = make_auth(ctx, target, chain, decided_at=dt("2026-08-19T11:10:00Z"), effective_at=dt("2026-08-19T11:20:00Z"))
    with pytest.raises(AuthorizedPriorPeriodCorrectionV1Error, match="REVENUE_POST_CLOSE_ADJUSTMENT"):
        post_authorized_prior_period_entry_void_v1(
            ledger, auth, target, chain, [period_close1], close1, event, proof1, event_id="void-blocked"
        )


def test_exact_void_refuses_to_guess_after_original_component_was_consumed():
    ctx = original_closed_period()
    ledger, _, _, event, _, close1, proof1, _, period_close1 = ctx
    ledger.post(
        event_id="tax-remittance", reference="tax-remittance-001", flow_type=FlowType.EXTERNAL_EXPENSE,
        lines=(ReportingLine("tax", debit=Decimal("5")), ReportingLine("cash", credit=Decimal("5"))),
        evidence_digest="bb" * 32, metadata={"economic_class":"TAX_REMITTANCE"}
    )
    target = AccountingPeriodV1(
        "period-n-plus-1", dt("2026-08-19T11:00:00Z"), dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close1.digest
    )
    chain = build_accounting_period_chain_proof_v1([period_close1], target, generated_at=dt("2026-08-19T11:05:00Z"))
    auth = make_auth(ctx, target, chain, decided_at=dt("2026-08-19T11:10:00Z"), effective_at=dt("2026-08-19T11:20:00Z"))
    with pytest.raises(AuthorizedPriorPeriodCorrectionV1Error, match="tax balance is below"):
        post_authorized_prior_period_entry_void_v1(
            ledger, auth, target, chain, [period_close1], close1, event, proof1, event_id="void-blocked-tax"
        )
