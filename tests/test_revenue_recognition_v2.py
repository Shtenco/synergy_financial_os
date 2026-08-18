from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLedger,
)
from sinergy_financial_os.revenue_posting_v2 import (
    RevenuePostingAccountsV2,
    RevenuePostingV2Error,
    post_recognized_external_revenue_v2,
)
from sinergy_financial_os.revenue_recognition_v2 import (
    RevenueRecognitionRequestV2,
    evaluate_revenue_recognition_v2,
)

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "fixtures/conformance/capital_authorization_v2_canonical.json"
REVENUE = ROOT / "fixtures/conformance/settlement_receipt_v2_revenue.json"
DECISION = ROOT / "fixtures/conformance/revenue_recognition_v2_canonical.json"
SCHEMA = ROOT / "schemas/revenue_recognition_v2.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def authorization() -> CapitalAuthorizationV2:
    p = load(AUTH)
    return CapitalAuthorizationV2(
        authorization_id=p["authorization_id"], project_id=p["project_id"], decision=p["decision"],
        decision_authority=p["decision_authority"], funding_asset=p["funding_asset"],
        approved_amount=Decimal(p["approved_amount"]), funding_source_id=p["funding_source_id"],
        funding_destination_id=p["funding_destination_id"], payment_idempotency_key=p["payment_idempotency_key"],
        payment_purpose=p["payment_purpose"], usage_policy=p["usage_policy"], screening_digest=p["screening_digest"],
        financial_snapshot_digest=p["financial_snapshot_digest"], financial_snapshot_sequence=p["financial_snapshot_sequence"],
        valuation_policy_digest=p["valuation_policy_digest"], requirement_registry_digest=p["requirement_registry_digest"],
        decision_evidence_digest=p["decision_evidence_digest"], approver_policy_digest=p["approver_policy_digest"],
        notes_digest=p["notes_digest"], decided_at=dt(p["decided_at"]), expires_at=dt(p["expires_at"]),
        execution_authority=p["execution_authority"], ai_authority=p["ai_authority"],
    )


def request(**changes) -> RevenueRecognitionRequestV2:
    kwargs = dict(
        recognition_id="revrec-001",
        project_id="project-001",
        project_evidence_digest="66" * 32,
        counterparty_id="external-customer-001",
        counterparty_relation="EXTERNAL_NON_RELATED",
        counterparty_evidence_digest="11" * 32,
        revenue_destination_id="project-001-revenue-account",
        contract_digest="22" * 32,
        invoice_digest="33" * 32,
        invoice_reporting_amount=Decimal("125"),
        delivery_evidence_digest="44" * 32,
        performance_state="SATISFIED",
        dispute_state="CLEAR",
        reporting_currency="USDC",
        fx_rate_to_reporting=Decimal("1"),
        tax_reporting_amount=Decimal("5"),
        refund_reserve_reporting_amount=Decimal("2"),
        accounting_policy_digest="55" * 32,
        recognized_at=dt("2026-08-19T10:30:00Z"),
    )
    kwargs.update(changes)
    return RevenueRecognitionRequestV2(**kwargs)


def rehash_receipt(receipt: dict) -> dict:
    p = copy.deepcopy(receipt)
    p.pop("receipt_digest", None)
    p["receipt_digest"] = hashlib.sha256(
        json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return p


def ledger() -> ReportingLedger:
    l = ReportingLedger("USDC")
    l.register_account(ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    l.register_account(ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"))
    l.register_account(ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    l.register_account(ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    return l


def accounts() -> RevenuePostingAccountsV2:
    return RevenuePostingAccountsV2("cash", "revenue", "tax", "refund")


def test_canonical_external_revenue_is_recognized_and_matches_fixture() -> None:
    decision = evaluate_revenue_recognition_v2(load(REVENUE), authorization(), request())
    assert decision.decision == "RECOGNIZED"
    assert decision.gross_reporting_amount == Decimal("125")
    assert decision.recognized_reporting_amount == Decimal("118")
    assert decision.ledger_posting_allowed is True
    assert decision.to_dict() == load(DECISION)
    assert decision.digest == "422f66737f129a3b714c16a1212287dc0ccf243efa51c4ce1a7eb65cd56fbfa3"
    schema = load(SCHEMA)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(decision.to_dict())


def test_intra_group_payment_is_rejected_not_external_revenue() -> None:
    decision = evaluate_revenue_recognition_v2(
        load(REVENUE), authorization(), request(counterparty_relation="INTRA_GROUP")
    )
    assert decision.decision == "REJECTED"
    assert decision.recognized_reporting_amount == 0
    assert "INTRA_GROUP_NOT_EXTERNAL_REVENUE" in decision.blockers


def test_unsatisfied_performance_and_open_chargeback_defer_revenue() -> None:
    decision = evaluate_revenue_recognition_v2(
        load(REVENUE),
        authorization(),
        request(performance_state="PARTIAL", dispute_state="CHARGEBACK_PENDING"),
    )
    assert decision.decision == "DEFERRED"
    assert decision.recognized_reporting_amount == 0
    assert "PERFORMANCE_OBLIGATION_NOT_SATISFIED" in decision.blockers
    assert "PAYMENT_DISPUTE_OR_CHARGEBACK_OPEN" in decision.blockers


def test_rehashed_receipt_with_other_payer_is_still_rejected() -> None:
    receipt = load(REVENUE)
    receipt["payer_id"] = "related-or-attacker-entity"
    receipt = rehash_receipt(receipt)
    decision = evaluate_revenue_recognition_v2(receipt, authorization(), request())
    assert decision.decision == "REJECTED"
    assert "COUNTERPARTY_PAYER_MISMATCH" in decision.blockers


def test_rehashed_receipt_with_other_revenue_destination_is_rejected() -> None:
    receipt = load(REVENUE)
    receipt["payee_id"] = "other-account"
    receipt = rehash_receipt(receipt)
    decision = evaluate_revenue_recognition_v2(receipt, authorization(), request())
    assert decision.decision == "REJECTED"
    assert "REVENUE_DESTINATION_MISMATCH" in decision.blockers


def test_settlement_above_invoice_is_rejected() -> None:
    decision = evaluate_revenue_recognition_v2(
        load(REVENUE), authorization(), request(invoice_reporting_amount=Decimal("100"))
    )
    assert decision.decision == "REJECTED"
    assert "SETTLEMENT_EXCEEDS_INVOICE_AMOUNT" in decision.blockers


def test_cross_currency_without_external_fx_evidence_is_deferred() -> None:
    decision = evaluate_revenue_recognition_v2(
        load(REVENUE),
        authorization(),
        request(reporting_currency="KZT", fx_rate_to_reporting=Decimal("500"), invoice_reporting_amount=Decimal("62500")),
    )
    assert decision.decision == "DEFERRED"
    assert "MISSING_EXTERNAL_FX_EVIDENCE" in decision.blockers


def test_only_recognized_decision_can_post_balanced_external_revenue() -> None:
    decision = evaluate_revenue_recognition_v2(load(REVENUE), authorization(), request())
    l = ledger()
    entry = post_recognized_external_revenue_v2(l, decision, accounts(), event_id="revenue-event-001")
    assert entry.flow_type.value == "EXTERNAL_REVENUE"
    assert entry.evidence_digest == decision.digest
    assert l.balance("cash") == Decimal("125")
    assert l.balance("revenue") == Decimal("118")
    assert l.balance("tax") == Decimal("5")
    assert l.balance("refund") == Decimal("2")
    assert l.trial_balance() == (Decimal("125"), Decimal("125"))


def test_deferred_decision_cannot_post_reporting_ledger() -> None:
    deferred = evaluate_revenue_recognition_v2(
        load(REVENUE), authorization(), request(performance_state="UNSATISFIED")
    )
    with pytest.raises(RevenuePostingV2Error):
        post_recognized_external_revenue_v2(ledger(), deferred, accounts(), event_id="bad")
