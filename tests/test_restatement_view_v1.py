from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os.accounting_close_v2 import (
    build_accounting_close_v2,
    build_ledger_inclusion_proof_v2,
)
from sinergy_financial_os.accounting_period_chain_v1 import build_accounting_period_chain_proof_v1
from sinergy_financial_os.accounting_period_v1 import AccountingPeriodV1, build_period_close_v1
from sinergy_financial_os.accounting_restatement_view_v1 import (
    AccountingRestatementOverlayV1,
    AccountingRestatementViewV1Error,
    build_accounting_restatement_overlay_v1,
    build_restated_period_view_v1,
)
from sinergy_financial_os.authorized_prior_period_correction_v1 import (
    post_authorized_prior_period_entry_void_v1,
)
from sinergy_financial_os.ledger_event_v2 import export_reporting_entry_as_ledger_event_v2
from sinergy_financial_os.prior_period_correction_v1 import PriorPeriodCorrectionAuthorizationV1
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLedger,
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


def ledger_book() -> ReportingLedger:
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


def build_context():
    ledger = ledger_book()
    rec = recognition()
    original_entry = post_recognized_external_revenue_v2(
        ledger,
        rec,
        RevenuePostingAccountsV2("cash", "revenue", "tax", "refund"),
        event_id="revenue-event-001",
    )
    original_event = export_reporting_entry_as_ledger_event_v2(
        original_entry, ledger, effective_at=rec.recognized_at, evidence_class="PROJECT"
    )
    snap1 = capture_financial_snapshot_v2(
        ledger, valuation_policy(), as_of=dt("2026-08-19T11:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED", liquidity_horizons=horizons(Decimal("125")),
        required_hard_nav_buffer=Decimal("0"), policy_mode="NORMAL"
    )
    close1 = build_accounting_close_v2(
        [original_event], snap1.to_dict(), close_id="close-period-n",
        closed_at=dt("2026-08-19T11:01:00Z"), requirement_registry_digest=REQ
    )
    original_proof = build_ledger_inclusion_proof_v2(
        [original_event], snap1.to_dict(), event_index=0, close=close1
    )
    period1 = AccountingPeriodV1(
        "period-n", dt("2026-08-19T00:00:00Z"), dt("2026-08-19T11:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ
    )
    period_close1 = build_period_close_v1(
        period1, close1, financial_snapshot=snap1.to_dict(), sealed_ledger_events=[original_event],
        closed_at=dt("2026-08-19T11:02:00Z")
    )
    target = AccountingPeriodV1(
        "period-n-plus-1", dt("2026-08-19T11:00:00Z"), dt("2026-08-19T13:00:00Z"),
        "SINERGY_CONSOLIDATED", "USDC", POLICY, REQ, period_close1.digest
    )
    chain = build_accounting_period_chain_proof_v1(
        [period_close1], target, generated_at=dt("2026-08-19T11:05:00Z")
    )
    auth = PriorPeriodCorrectionAuthorizationV1(
        authorization_id="prior-error-void-001", affected_period_id=period1.period_id,
        target_period_id=target.period_id, reason="DUPLICATE_ENTRY",
        original_period_close_digest=period_close1.digest, original_accounting_close_digest=close1.digest,
        original_ledger_event_digest=__import__("sinergy_financial_os.ledger_event_v2", fromlist=["ledger_event_v2_digest"]).ledger_event_v2_digest(original_event),
        original_reporting_entry_digest=original_entry.digest, period_chain_proof_digest=chain.digest,
        correction_evidence_digest="88" * 32, decision_evidence_digest="99" * 32,
        accounting_policy_digest=POLICY, requirement_registry_digest=REQ,
        decision_authority="MULTISIG_GOVERNANCE", decided_at=dt("2026-08-19T11:10:00Z"),
        effective_at=dt("2026-08-19T11:20:00Z")
    )
    original_close_digest = close1.digest
    original_period_close_digest = period_close1.digest
    correction_entry = post_authorized_prior_period_entry_void_v1(
        ledger, auth, target, chain, [period_close1], close1, original_event, original_proof,
        event_id="prior-error-void-event-001"
    )
    correction_event = export_reporting_entry_as_ledger_event_v2(
        correction_entry, ledger, effective_at=auth.effective_at, evidence_class="AUDITED"
    )
    snap2 = capture_financial_snapshot_v2(
        ledger, valuation_policy(), as_of=dt("2026-08-19T13:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED", liquidity_horizons=horizons(Decimal("0")),
        previous_snapshot=snap1, required_hard_nav_buffer=Decimal("0"), policy_mode="DEFENSE"
    )
    close2 = build_accounting_close_v2(
        [original_event, correction_event], snap2.to_dict(), close_id="close-period-n-plus-1",
        closed_at=dt("2026-08-19T13:01:00Z"), requirement_registry_digest=REQ
    )
    correction_proof = build_ledger_inclusion_proof_v2(
        [original_event, correction_event], snap2.to_dict(), event_index=1, close=close2
    )
    period_close2 = build_period_close_v1(
        target, close2, financial_snapshot=snap2.to_dict(), sealed_ledger_events=[original_event, correction_event],
        adjustment_authorization_digests=(auth.digest,), closed_at=dt("2026-08-19T13:02:00Z")
    )
    return {
        "ledger": ledger, "original_entry": original_entry, "original_event": original_event,
        "snap1": snap1, "close1": close1, "original_proof": original_proof, "period1": period1,
        "period_close1": period_close1, "target": target, "chain": chain, "auth": auth,
        "correction_entry": correction_entry, "correction_event": correction_event, "snap2": snap2,
        "close2": close2, "correction_proof": correction_proof, "period_close2": period_close2,
        "original_close_digest": original_close_digest, "original_period_close_digest": original_period_close_digest,
    }


def test_exact_void_can_create_presentation_overlay_and_view_without_mutating_close_n():
    c = build_context()
    overlay = build_accounting_restatement_overlay_v1(
        overlay_id="overlay-001", authorization=c["auth"], target_period=c["target"],
        period_chain_proof=c["chain"], period_close_chain=[c["period_close1"]],
        original_accounting_close=c["close1"], original_ledger_event=c["original_event"],
        original_inclusion_proof=c["original_proof"], correction_period_close=c["period_close2"],
        correction_accounting_close=c["close2"], correction_ledger_event=c["correction_event"],
        correction_inclusion_proof=c["correction_proof"], generated_at=dt("2026-08-19T13:05:00Z")
    )
    assert overlay.presentation_action == "EXCLUDE_ORIGINAL_ENTRY"
    assert overlay.original_reporting_entry_digest == c["original_entry"].digest
    assert c["close1"].digest == c["original_close_digest"]
    assert c["period_close1"].digest == c["original_period_close_digest"]

    view = build_restated_period_view_v1(
        [overlay], view_id="restated-period-n-v1", generated_at=dt("2026-08-19T13:10:00Z")
    )
    assert view.status == "RESTATED_PRESENTATION"
    assert view.view_version == 1
    assert view.recalculated_financial_metrics == "NOT_PERFORMED"
    assert view.ledger_mutation_authority == "NONE"
    assert view.execution_authority == "NONE"
    assert view.excluded_reporting_entry_digests == (c["original_entry"].digest,)


def test_overlay_rejects_correction_event_that_is_not_exact_opposite():
    c = build_context()
    bad = dict(c["correction_event"])
    bad["metadata"] = dict(bad["metadata"])
    bad["metadata"]["restatement_required"] = "NO"
    with pytest.raises(AccountingRestatementViewV1Error, match="require restatement"):
        build_accounting_restatement_overlay_v1(
            overlay_id="overlay-bad", authorization=c["auth"], target_period=c["target"],
            period_chain_proof=c["chain"], period_close_chain=[c["period_close1"]],
            original_accounting_close=c["close1"], original_ledger_event=c["original_event"],
            original_inclusion_proof=c["original_proof"], correction_period_close=c["period_close2"],
            correction_accounting_close=c["close2"], correction_ledger_event=bad,
            correction_inclusion_proof=c["correction_proof"], generated_at=dt("2026-08-19T13:05:00Z")
        )


def test_view_versions_are_append_only_strict_supersets():
    c = build_context()
    first_overlay = build_accounting_restatement_overlay_v1(
        overlay_id="overlay-001", authorization=c["auth"], target_period=c["target"],
        period_chain_proof=c["chain"], period_close_chain=[c["period_close1"]],
        original_accounting_close=c["close1"], original_ledger_event=c["original_event"],
        original_inclusion_proof=c["original_proof"], correction_period_close=c["period_close2"],
        correction_accounting_close=c["close2"], correction_ledger_event=c["correction_event"],
        correction_inclusion_proof=c["correction_proof"], generated_at=dt("2026-08-19T13:05:00Z")
    )
    view1 = build_restated_period_view_v1(
        [first_overlay], view_id="view-1", generated_at=dt("2026-08-19T13:10:00Z")
    )
    second_overlay = AccountingRestatementOverlayV1(
        overlay_id="overlay-002", affected_period_id=first_overlay.affected_period_id,
        correction_target_period_id="period-n-plus-2",
        original_period_close_digest=first_overlay.original_period_close_digest,
        original_accounting_close_digest="12" * 32,
        original_ledger_event_digest="13" * 32,
        original_reporting_entry_digest="14" * 32,
        correction_authorization_digest="15" * 32,
        period_chain_proof_digest="16" * 32,
        correction_period_close_digest="17" * 32,
        correction_accounting_close_digest="18" * 32,
        correction_ledger_event_digest="19" * 32,
        correction_reporting_entry_digest="1a" * 32,
        generated_at=dt("2026-08-19T14:00:00Z")
    )
    view2 = build_restated_period_view_v1(
        [first_overlay, second_overlay], view_id="view-2", generated_at=dt("2026-08-19T14:10:00Z"), previous_view=view1
    )
    assert view2.view_version == 2
    assert view2.previous_restated_view_digest == view1.digest
    assert set(view1.overlay_digests) < set(view2.overlay_digests)
    with pytest.raises(AccountingRestatementViewV1Error, match="strict superset"):
        build_restated_period_view_v1(
            [first_overlay], view_id="bad-view-2", generated_at=dt("2026-08-19T14:20:00Z"), previous_view=view1
        )
