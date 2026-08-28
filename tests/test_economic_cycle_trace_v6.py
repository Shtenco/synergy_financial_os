from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import jsonschema

from sinergy_financial_os.accounting_close_v2 import (
    build_accounting_close_v2,
    build_ledger_inclusion_proof_v2,
)
from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.economic_cycle_trace_v6 import (
    EconomicCycleTraceV6,
    make_reference_v6,
    verify_complete_trace_artifacts_v6,
)
from sinergy_financial_os.ledger_event_v2 import (
    export_reporting_entry_as_ledger_event_v2,
    ledger_event_v2_digest,
    verify_ledger_event_v2,
)
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
AUTH = ROOT / "fixtures/conformance/capital_authorization_v2_canonical.json"
FUNDING = ROOT / "fixtures/conformance/settlement_receipt_v2_funding.json"
REVENUE = ROOT / "fixtures/conformance/settlement_receipt_v2_revenue.json"
RECOGNITION = ROOT / "fixtures/conformance/revenue_recognition_v2_canonical.json"
REQ_DIGEST = "77" * 32


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def authorization() -> CapitalAuthorizationV2:
    p = load(AUTH)
    return CapitalAuthorizationV2(
        authorization_id=p["authorization_id"],
        project_id=p["project_id"],
        decision=p["decision"],
        decision_authority=p["decision_authority"],
        funding_asset=p["funding_asset"],
        approved_amount=Decimal(p["approved_amount"]),
        funding_source_id=p["funding_source_id"],
        funding_destination_id=p["funding_destination_id"],
        payment_idempotency_key=p["payment_idempotency_key"],
        payment_purpose=p["payment_purpose"],
        usage_policy=p["usage_policy"],
        screening_digest=p["screening_digest"],
        financial_snapshot_digest=p["financial_snapshot_digest"],
        financial_snapshot_sequence=p["financial_snapshot_sequence"],
        valuation_policy_digest=p["valuation_policy_digest"],
        requirement_registry_digest=p["requirement_registry_digest"],
        decision_evidence_digest=p["decision_evidence_digest"],
        approver_policy_digest=p["approver_policy_digest"],
        notes_digest=p["notes_digest"],
        decided_at=dt(p["decided_at"]),
        expires_at=dt(p["expires_at"]),
        execution_authority=p["execution_authority"],
        ai_authority=p["ai_authority"],
    )


def recognition() -> RevenueRecognitionDecisionV2:
    p = load(RECOGNITION)
    decision = RevenueRecognitionDecisionV2(
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
    assert decision.digest == p["digest"]
    return decision


def ledger() -> ReportingLedger:
    result = ReportingLedger("USDC")
    result.register_account(ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    result.register_account(ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"))
    result.register_account(ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    result.register_account(ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True))
    return result


def policy() -> ValuationPolicy:
    return ValuationPolicy(
        "cycle-policy-v1",
        "USDC",
        dt("2026-08-19T10:29:00Z"),
        (ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )


def make_chain():
    auth = authorization()
    decision = recognition()
    funding = load(FUNDING)
    revenue = load(REVENUE)
    book = ledger()
    entry = post_recognized_external_revenue_v2(
        book,
        decision,
        RevenuePostingAccountsV2("cash", "revenue", "tax", "refund"),
        event_id="revenue-event-001",
    )
    event = export_reporting_entry_as_ledger_event_v2(
        entry, book, effective_at=decision.recognized_at, evidence_class="PROJECT"
    )
    snap = capture_financial_snapshot_v2(
        book,
        policy(),
        as_of=dt("2026-08-19T11:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=(
            LiquidityHorizonState(1, Decimal("125"), Decimal("0")),
            LiquidityHorizonState(4, Decimal("125"), Decimal("0")),
            LiquidityHorizonState(8, Decimal("125"), Decimal("0")),
        ),
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    ).to_dict()
    close = build_accounting_close_v2(
        [event],
        snap,
        close_id="close-cycle-003-v2",
        closed_at=dt("2026-08-19T11:05:00Z"),
        requirement_registry_digest=REQ_DIGEST,
    )
    proof = build_ledger_inclusion_proof_v2(
        [event], snap, event_index=0, close=close
    )
    refs = (
        make_reference_v6("FUNDING_STATE", digest="01" * 32, subject_id="cohort-001", observed_at=dt("2026-08-18T17:00:00Z")),
        make_reference_v6("PROJECT_PROPOSAL", digest="02" * 32, subject_id="project-001", observed_at=dt("2026-08-18T17:30:00Z")),
        make_reference_v6("PROJECT_SCREENING", digest=auth.screening_digest, subject_id="project-001", observed_at=dt("2026-08-18T18:30:00Z")),
        make_reference_v6("CAPITAL_AUTHORIZATION", digest=auth.digest, subject_id="project-001", observed_at=dt("2026-08-18T19:00:00Z")),
        make_reference_v6("FUNDING_SETTLEMENT", digest=funding["receipt_digest"], subject_id=funding["settlement_id"], observed_at=dt(funding["finality_time"])),
        make_reference_v6("PROJECT_EVIDENCE", digest="66" * 32, subject_id="project-001", observed_at=dt("2026-08-19T09:00:00Z")),
        make_reference_v6("REVENUE_SETTLEMENT", digest=revenue["receipt_digest"], subject_id=revenue["settlement_id"], observed_at=dt(revenue["finality_time"])),
        make_reference_v6("REVENUE_RECOGNITION", digest=decision.digest, subject_id="project-001", observed_at=decision.recognized_at),
        make_reference_v6("LEDGER_EVENT", digest=ledger_event_v2_digest(event), subject_id=event["event_id"], observed_at=decision.recognized_at),
        make_reference_v6("ACCOUNTING_SNAPSHOT", digest=snap["digest"], subject_id="financial-snapshot-cycle-003", observed_at=dt(snap["as_of"])),
        make_reference_v6("ACCOUNTING_CLOSE", digest=close.digest, subject_id=close.close_id, observed_at=close.closed_at),
        make_reference_v6("LEDGER_INCLUSION_PROOF", digest=proof.digest, subject_id=proof.event_id, observed_at=close.closed_at + timedelta(minutes=1)),
    )
    trace = EconomicCycleTraceV6("cycle-006", "cohort-001", "project-001", refs)
    return auth, decision, funding, revenue, book, event, snap, close, proof, trace


def review(chain):
    auth, decision, funding, revenue, _, event, snap, close, proof, trace = chain
    return verify_complete_trace_artifacts_v6(
        trace,
        authorization=auth,
        funding_receipt=funding,
        revenue_receipt=revenue,
        project_evidence_digest="66" * 32,
        recognition=decision,
        ledger_event=event,
        ledger_prefix=[event],
        financial_snapshot=snap,
        accounting_close=close,
        inclusion_proof=proof,
    )


def test_trace_v6_proves_revenue_event_in_snapshot_bound_close() -> None:
    chain = make_chain()
    result = review(chain)
    assert result.verified is True
    assert result.blockers == ()
    assert result.accounting_close_verified is True
    assert result.target_ledger_event_included is True
    trace = chain[-1]
    schema = load(ROOT / "schemas/economic_cycle_trace_v6.schema.json")
    jsonschema.Draft202012Validator(schema).validate(trace.to_dict())


def _recompute_entry_digest(event: dict) -> str:
    body = {
        "sequence": event["sequence"],
        "event_id": event["event_id"],
        "reference": event["external_reference"],
        "flow_type": event["event_type"],
        "lines": [
            {"account_id": line["account"], "debit": line["debit"], "credit": line["credit"]}
            for line in event["lines"]
        ],
        "previous_entry_digest": event["previous_reporting_entry_digest"],
        "evidence_digest": event["evidence_digest"],
        "metadata": dict(sorted(event["metadata"].items())),
    }
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _rehash_snapshot(payload: dict) -> dict:
    result = copy.deepcopy(payload)
    result.pop("digest", None)
    result["digest"] = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return result


def test_rebuilt_downstream_hashes_cannot_change_recognized_economics() -> None:
    chain = make_chain()
    auth, decision, funding, revenue, _, event, snap, _, _, _ = chain
    forged_event = copy.deepcopy(event)
    forged_event["lines"][0]["debit"] = "126"
    forged_event["lines"][1]["credit"] = "119"
    forged_event["reporting_entry_digest"] = _recompute_entry_digest(forged_event)
    verify_ledger_event_v2(forged_event)

    forged_snapshot = copy.deepcopy(snap)
    forged_snapshot["ledger_last_entry_digest"] = forged_event["reporting_entry_digest"]
    forged_snapshot["ledger_digest"] = "88" * 32
    forged_snapshot = _rehash_snapshot(forged_snapshot)
    forged_close = build_accounting_close_v2(
        [forged_event], forged_snapshot,
        close_id="forged-close",
        closed_at=dt("2026-08-19T11:05:00Z"),
        requirement_registry_digest=REQ_DIGEST,
    )
    forged_proof = build_ledger_inclusion_proof_v2(
        [forged_event], forged_snapshot, event_index=0, close=forged_close
    )
    original_trace = chain[-1]
    replacements = {
        "LEDGER_EVENT": ledger_event_v2_digest(forged_event),
        "ACCOUNTING_SNAPSHOT": forged_snapshot["digest"],
        "ACCOUNTING_CLOSE": forged_close.digest,
        "LEDGER_INCLUSION_PROOF": forged_proof.digest,
    }
    refs = []
    for ref in original_trace.references:
        digest = replacements.get(ref.phase, ref.digest)
        subject = forged_close.close_id if ref.phase == "ACCOUNTING_CLOSE" else ref.subject_id
        refs.append(make_reference_v6(ref.phase, digest=digest, subject_id=subject, observed_at=ref.observed_at))
    forged_trace = EconomicCycleTraceV6("cycle-006-forged", "cohort-001", "project-001", tuple(refs))
    result = verify_complete_trace_artifacts_v6(
        forged_trace,
        authorization=auth,
        funding_receipt=funding,
        revenue_receipt=revenue,
        project_evidence_digest="66" * 32,
        recognition=decision,
        ledger_event=forged_event,
        ledger_prefix=[forged_event],
        financial_snapshot=forged_snapshot,
        accounting_close=forged_close,
        inclusion_proof=forged_proof,
    )
    assert result.verified is False
    assert "LEDGER_GROSS_DEBIT_MISMATCH" in result.blockers
    assert "LEDGER_RECOGNITION_CREDIT_COMPONENTS_MISMATCH" in result.blockers
