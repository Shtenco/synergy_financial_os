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
from sinergy_financial_os.accounting_period_chain_v1 import (
    AccountingPeriodChainV1Error,
    build_accounting_period_chain_proof_v1,
    verify_accounting_period_chain_proof_v1,
)
from sinergy_financial_os.accounting_period_v1 import AccountingPeriodV1, build_period_close_v1
from sinergy_financial_os.authorized_revenue_adjustment_v1 import (
    AuthorizedRevenueAdjustmentV1Error,
    RevenueAdjustmentAccountsV1,
    post_authorized_revenue_adjustment_v1,
)
from sinergy_financial_os.ledger_event_v2 import (
    export_reporting_entry_as_ledger_event_v2,
    ledger_event_v2_digest,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.revenue_adjustment_v1 import (
    RevenueAdjustmentAuthorizationV1,
    RevenueAdjustmentV1Error,
    verify_revenue_adjustment_context_v1,
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
        recognition_id=p["recognition_id"],
        project_id=p["project_id"],
        decision=p["decision"],
        settlement_receipt_digest=p["settlement_receipt_digest"],
        capital_authorization_digest=p["capital_authorization_digest"],
        project_evidence_digest=p["project_evidence_digest"],
        counterparty_id=p["counterparty_id"],
        counterparty_relation=p["counterparty_relation"],
        counterparty_evidence_digest=p["counterparty_evidence_digest"],
        revenue_destination_id=p["revenue_destination_id"],
        contract_digest=p["contract_digest"],
        invoice_digest=p["invoice_digest"],
        invoice_reporting_amount=Decimal(p["invoice_reporting_amount"]),
        delivery_evidence_digest=p["delivery_evidence_digest"],
        accounting_policy_digest=p["accounting_policy_digest"],
        settlement_asset=p["settlement_asset"],
        settlement_amount=Decimal(p["settlement_amount"]),
        reporting_currency=p["reporting_currency"],
        fx_rate_to_reporting=Decimal(p["fx_rate_to_reporting"]),
        gross_reporting_amount=Decimal(p["gross_reporting_amount"]),
        tax_reporting_amount=Decimal(p["tax_reporting_amount"]),
        refund_reserve_reporting_amount=Decimal(p["refund_reserve_reporting_amount"]),
        recognized_reporting_amount=Decimal(p["recognized_reporting_amount"]),
        performance_state=p["performance_state"],
        dispute_state=p["dispute_state"],
        recognized_at=dt(p["recognized_at"]),
        blockers=tuple(p["blockers"]),
        fx_evidence_digest=p["fx_evidence_digest"],
        accounting_authority=p["accounting_authority"],
        ledger_posting_authority=p["ledger_posting_authority"],
        ai_authority=p["ai_authority"],
    )


def book() -> ReportingLedger:
    ledger = ReportingLedger("USDC")
    ledger.register_account(ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    ledger.register_account(ReportingAccountSpec("tax_receivable", "Tax recoverable", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "TAX_REC"))
    ledger.register_account(ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"))
    ledger.register_account(ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    ledger.register_account(ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    ledger.register_account(ReportingAccountSpec("tax_expense", "Nonrecoverable tax", AccountClass.EXPENSE, ConsolidationClass.EXTERNAL, "EXPENSE"))
    ledger.register_account(ReportingAccountSpec("processor_fee", "Processor/chargeback fee", AccountClass.EXPENSE, ConsolidationClass.EXTERNAL, "EXPENSE"))
    return ledger


def valuation_policy() -> ValuationPolicy:
    return ValuationPolicy(
        "cycle-policy-v1",
        "USDC",
        dt("2026-08-19T10:29:00Z"),
        (
            ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),
            ValuationRule("TAX_REC", Decimal("1"), Decimal("1"), Decimal("1"), "AUDITED_NAV"),
        ),
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
    entry = post_recognized_external_revenue_v2(
        ledger,
        rec,
        RevenuePostingAccountsV2("cash", "revenue", "tax", "refund"),
        event_id="revenue-event-001",
    )
    event = export_reporting_entry_as_ledger_event_v2(
        entry,
        ledger,
        effective_at=rec.recognized_at,
        evidence_class="PROJECT",
    )
    snap = capture_financial_snapshot_v2(
        ledger,
        valuation_policy(),
        as_of=dt("2026-08-19T11:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("125")),
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    )
    close = build_accounting_close_v2(
        [event],
        snap.to_dict(),
        close_id="close-period-n",
        closed_at=dt("2026-08-19T11:01:00Z"),
        requirement_registry_digest=REQ,
    )
    proof = build_ledger_inclusion_proof_v2(
        [event], snap.to_dict(), event_index=0, close=close
    )
    period = AccountingPeriodV1(
        "period-n",
        dt("2026-08-19T00:00:00Z"),
        dt("2026-08-19T11:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
    )
    period_close = build_period_close_v1(
        period,
        close,
        financial_snapshot=snap.to_dict(),
        sealed_ledger_events=[event],
        closed_at=dt("2026-08-19T11:02:00Z"),
    )
    return ledger, rec, entry, event, snap, close, proof, period, period_close


def close_intermediate_period_with_tax_remittance(ctx):
    ledger, rec, entry, event1, snap1, close1, proof1, period1, period_close1 = ctx
    period2 = AccountingPeriodV1(
        "period-n-plus-1",
        dt("2026-08-19T11:00:00Z"),
        dt("2026-08-19T12:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close1.digest,
    )
    tax_entry = ledger.post(
        event_id="tax-remittance",
        reference="tax-remittance-001",
        flow_type=FlowType.EXTERNAL_EXPENSE,
        lines=(
            ReportingLine("tax", debit=Decimal("5")),
            ReportingLine("cash", credit=Decimal("5")),
        ),
        evidence_digest="bb" * 32,
        metadata={"economic_class": "TAX_REMITTANCE"},
    )
    tax_event = export_reporting_entry_as_ledger_event_v2(
        tax_entry,
        ledger,
        effective_at=dt("2026-08-19T11:30:00Z"),
        evidence_class="AUDITED",
    )
    snap2 = capture_financial_snapshot_v2(
        ledger,
        valuation_policy(),
        as_of=dt("2026-08-19T12:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("120")),
        previous_snapshot=snap1,
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    )
    close2 = build_accounting_close_v2(
        [event1, tax_event],
        snap2.to_dict(),
        close_id="close-period-n-plus-1",
        closed_at=dt("2026-08-19T12:01:00Z"),
        requirement_registry_digest=REQ,
    )
    period_close2 = build_period_close_v1(
        period2,
        close2,
        financial_snapshot=snap2.to_dict(),
        sealed_ledger_events=[event1, tax_event],
        closed_at=dt("2026-08-19T12:02:00Z"),
    )
    return period2, tax_entry, tax_event, snap2, close2, period_close2


def adjustment_accounts() -> RevenueAdjustmentAccountsV1:
    return RevenueAdjustmentAccountsV1(
        "cash",
        "revenue",
        "tax",
        "refund",
        tax_recoverable_asset_account="tax_receivable",
        tax_expense_account="tax_expense",
        external_fee_expense_account="processor_fee",
    )


def make_auth(ctx, target, chain_proof, **changes) -> RevenueAdjustmentAuthorizationV1:
    _, rec, entry, event, _, close, _, _, period_close = ctx
    values = dict(
        authorization_id="adjustment-auth-001",
        target_period_id=target.period_id,
        project_id=rec.project_id,
        reason="CHARGEBACK",
        original_period_close_digest=period_close.digest,
        original_accounting_close_digest=close.digest,
        original_revenue_recognition_digest=rec.digest,
        original_ledger_event_digest=ledger_event_v2_digest(event),
        original_reporting_entry_digest=entry.digest,
        period_chain_proof_digest=chain_proof.digest,
        customer_refund_amount=Decimal("30"),
        revenue_reduction_amount=Decimal("27"),
        refund_reserve_release_amount=Decimal("1"),
        tax_adjustment_amount=Decimal("2"),
        tax_treatment="RECOVERABLE_RECEIVABLE",
        external_fee_expense_amount=Decimal("1"),
        external_refund_evidence_digest="88" * 32,
        tax_evidence_digest="99" * 32,
        fee_evidence_digest="aa" * 32,
        decision_evidence_digest="ab" * 32,
        accounting_policy_digest=POLICY,
        requirement_registry_digest=REQ,
        decision_authority="MULTISIG_GOVERNANCE",
        decided_at=dt("2026-08-19T12:10:00Z"),
        effective_at=dt("2026-08-19T12:20:00Z"),
    )
    values.update(changes)
    return RevenueAdjustmentAuthorizationV1(**values)


def test_partial_refund_after_tax_remittance_in_later_period_is_explicit_and_balanced():
    ctx = original_closed_period()
    ledger, rec, original_entry, original_event, snap1, close1, proof1, _, period_close1 = ctx
    _, _, tax_event, snap2, _, period_close2 = close_intermediate_period_with_tax_remittance(ctx)
    target = AccountingPeriodV1(
        "period-n-plus-2",
        dt("2026-08-19T12:00:00Z"),
        dt("2026-08-19T14:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close2.digest,
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1, period_close2],
        target,
        generated_at=dt("2026-08-19T12:05:00Z"),
    )
    auth = make_auth(ctx, target, chain)
    assert verify_revenue_adjustment_context_v1(
        auth,
        target,
        chain,
        [period_close1, period_close2],
        close1,
        rec,
        original_event,
        proof1,
    )

    adjustment = post_authorized_revenue_adjustment_v1(
        ledger,
        auth,
        target,
        chain,
        [period_close1, period_close2],
        close1,
        rec,
        original_event,
        proof1,
        adjustment_accounts(),
        event_id="partial-chargeback-001",
    )
    assert adjustment.flow_type == FlowType.EXTERNAL_EXPENSE
    assert adjustment.evidence_digest == auth.digest
    assert ledger.balance("cash") == Decimal("89")
    assert ledger.balance("revenue") == Decimal("91")
    assert ledger.balance("refund") == Decimal("1")
    assert ledger.balance("tax") == Decimal("0")
    assert ledger.balance("tax_receivable") == Decimal("2")
    assert ledger.balance("processor_fee") == Decimal("1")

    adjustment_event = export_reporting_entry_as_ledger_event_v2(
        adjustment,
        ledger,
        effective_at=auth.effective_at,
        evidence_class="PROJECT",
    )
    snap3 = capture_financial_snapshot_v2(
        ledger,
        valuation_policy(),
        as_of=dt("2026-08-19T14:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("91")),
        previous_snapshot=snap2,
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="DEFENSE",
    )
    assert snap2.hard_nav == Decimal("118")
    assert snap3.hard_nav == Decimal("90")
    assert snap3.realized_external_revenue == Decimal("0")
    assert snap3.realized_external_pnl == Decimal("-28")
    assert snap3.period_profit_budget == Decimal("0")
    close3 = build_accounting_close_v2(
        [original_event, tax_event, adjustment_event],
        snap3.to_dict(),
        close_id="close-period-n-plus-2",
        closed_at=dt("2026-08-19T14:01:00Z"),
        requirement_registry_digest=REQ,
    )
    assert verify_accounting_close_v2(
        [original_event, tax_event, adjustment_event], snap3.to_dict(), close3
    )
    period_close3 = build_period_close_v1(
        target,
        close3,
        financial_snapshot=snap3.to_dict(),
        sealed_ledger_events=[original_event, tax_event, adjustment_event],
        adjustment_authorization_digests=(auth.digest,),
        closed_at=dt("2026-08-19T14:02:00Z"),
    )
    assert period_close3.previous_period_close_digest == period_close2.digest
    assert period_close3.adjustment_authorization_digests == (auth.digest,)


def test_cumulative_adjustments_cannot_exceed_original_recognition_components():
    ctx = original_closed_period()
    ledger, rec, _, event, _, close1, proof1, _, period_close1 = ctx
    _, _, _, _, _, period_close2 = close_intermediate_period_with_tax_remittance(ctx)
    target = AccountingPeriodV1(
        "period-n-plus-2",
        dt("2026-08-19T12:00:00Z"),
        dt("2026-08-19T14:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close2.digest,
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1, period_close2], target, generated_at=dt("2026-08-19T12:05:00Z")
    )
    first = make_auth(ctx, target, chain)
    post_authorized_revenue_adjustment_v1(
        ledger, first, target, chain, [period_close1, period_close2], close1, rec, event, proof1,
        adjustment_accounts(), event_id="adjustment-1"
    )
    second = make_auth(
        ctx,
        target,
        chain,
        authorization_id="adjustment-auth-002",
        customer_refund_amount=Decimal("100"),
        revenue_reduction_amount=Decimal("100"),
        refund_reserve_release_amount=Decimal("0"),
        tax_adjustment_amount=Decimal("0"),
        tax_treatment="NONE",
        external_fee_expense_amount=Decimal("0"),
        tax_evidence_digest=None,
        fee_evidence_digest=None,
        decided_at=dt("2026-08-19T12:30:00Z"),
        effective_at=dt("2026-08-19T12:40:00Z"),
    )
    with pytest.raises(AuthorizedRevenueAdjustmentV1Error, match="cumulative revenue reduction exceeds"):
        post_authorized_revenue_adjustment_v1(
            ledger, second, target, chain, [period_close1, period_close2], close1, rec, event, proof1,
            adjustment_accounts(), event_id="adjustment-2"
        )


def test_direct_successor_partial_refund_can_release_unpaid_tax_liability():
    ctx = original_closed_period()
    ledger, rec, _, event, _, close1, proof1, _, period_close1 = ctx
    target = AccountingPeriodV1(
        "period-n-plus-1",
        dt("2026-08-19T11:00:00Z"),
        dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close1.digest,
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1], target, generated_at=dt("2026-08-19T11:05:00Z")
    )
    auth = make_auth(
        ctx,
        target,
        chain,
        authorization_id="liability-release-001",
        reason="REFUND",
        customer_refund_amount=Decimal("10"),
        revenue_reduction_amount=Decimal("9"),
        refund_reserve_release_amount=Decimal("0"),
        tax_adjustment_amount=Decimal("1"),
        tax_treatment="LIABILITY_RELEASE",
        external_fee_expense_amount=Decimal("0"),
        tax_evidence_digest="cc" * 32,
        fee_evidence_digest=None,
        decided_at=dt("2026-08-19T11:10:00Z"),
        effective_at=dt("2026-08-19T11:20:00Z"),
    )
    post_authorized_revenue_adjustment_v1(
        ledger, auth, target, chain, [period_close1], close1, rec, event, proof1,
        adjustment_accounts(), event_id="partial-refund-tax-liability"
    )
    assert ledger.balance("cash") == Decimal("115")
    assert ledger.balance("revenue") == Decimal("109")
    assert ledger.balance("tax") == Decimal("4")
    assert ledger.balance("refund") == Decimal("2")


def test_period_chain_proof_blocks_tampered_ancestry_and_postdated_proof():
    ctx = original_closed_period()
    _, rec, _, event, _, close1, proof1, _, period_close1 = ctx
    _, _, _, _, _, period_close2 = close_intermediate_period_with_tax_remittance(ctx)
    target = AccountingPeriodV1(
        "period-n-plus-2",
        dt("2026-08-19T12:00:00Z"),
        dt("2026-08-19T14:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close2.digest,
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1, period_close2], target, generated_at=dt("2026-08-19T12:15:00Z")
    )
    auth = make_auth(ctx, target, chain, decided_at=dt("2026-08-19T12:10:00Z"))
    with pytest.raises(RevenueAdjustmentV1Error, match="generated after the decision"):
        verify_revenue_adjustment_context_v1(
            auth, target, chain, [period_close1, period_close2], close1, rec, event, proof1
        )
    with pytest.raises(AccountingPeriodChainV1Error):
        verify_accounting_period_chain_proof_v1(
            chain, [period_close2, period_close1], target
        )


def test_tax_and_fee_evidence_are_fail_closed():
    ctx = original_closed_period()
    _, _, _, _, _, _, _, _, period_close1 = ctx
    target = AccountingPeriodV1(
        "period-n-plus-1",
        dt("2026-08-19T11:00:00Z"),
        dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED",
        "USDC",
        POLICY,
        REQ,
        period_close1.digest,
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1], target, generated_at=dt("2026-08-19T11:05:00Z")
    )
    with pytest.raises(RevenueAdjustmentV1Error, match="tax evidence"):
        make_auth(ctx, target, chain, tax_evidence_digest=None)
    with pytest.raises(RevenueAdjustmentV1Error, match="fee evidence"):
        make_auth(ctx, target, chain, fee_evidence_digest=None)
