from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.accounting_close_v2 import (
    AccountingCloseV2Error,
    build_accounting_close_v2,
    build_ledger_inclusion_proof_v2,
    verify_accounting_close_v2,
    verify_ledger_inclusion_proof_v2,
)
from sinergy_financial_os.ledger_event_v2 import (
    export_reporting_entry_as_ledger_event_v2,
    ledger_event_v2_digest,
    verify_ledger_event_v2,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule


ROOT = Path(__file__).resolve().parents[1]
GENESIS = "0" * 64
RECOGNITION_DIGEST = "422f66737f129a3b714c16a1212287dc0ccf243efa51c4ce1a7eb65cd56fbfa3"
REQ_DIGEST = "77" * 32


def dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def ledger() -> ReportingLedger:
    result = ReportingLedger("USDC")
    result.register_account(
        ReportingAccountSpec(
            "cash", "External cash", AccountClass.ASSET,
            ConsolidationClass.EXTERNAL, "CASH"
        )
    )
    result.register_account(
        ReportingAccountSpec(
            "revenue", "External revenue", AccountClass.REVENUE,
            ConsolidationClass.EXTERNAL, "REVENUE"
        )
    )
    result.register_account(
        ReportingAccountSpec(
            "tax", "Tax payable", AccountClass.LIABILITY,
            ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True
        )
    )
    result.register_account(
        ReportingAccountSpec(
            "refund", "Refund reserve", AccountClass.LIABILITY,
            ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True
        )
    )
    return result


def post_revenue(result: ReportingLedger):
    return result.post(
        event_id="revenue-event-001",
        reference="revrec-001",
        flow_type=FlowType.EXTERNAL_REVENUE,
        lines=(
            ReportingLine("cash", debit=Decimal("125")),
            ReportingLine("revenue", credit=Decimal("118")),
            ReportingLine("tax", credit=Decimal("5")),
            ReportingLine("refund", credit=Decimal("2")),
        ),
        evidence_digest=RECOGNITION_DIGEST,
        metadata={
            "accounting_policy_digest": "55" * 32,
            "capital_authorization_digest": "1e814153a18850865543e08b498b60d9bce80dbd34bfb2f4c378f3fe502fe89f",
            "project_evidence_digest": "66" * 32,
            "project_id": "project-001",
            "revenue_recognition_schema": "revenue.recognition/v2",
            "settlement_receipt_digest": "cd3a1886789eb431dde2b06feb4236bcf0f5d6f97f327de9204ec437fb8222e8",
        },
    )


def valuation_policy() -> ValuationPolicy:
    return ValuationPolicy(
        policy_id="cycle-policy-v1",
        reporting_currency="USDC",
        as_of=dt("2026-08-19T10:29:00Z"),
        rules=(
            ValuationRule(
                valuation_class="CASH",
                hard_factor=Decimal("1"),
                liquid_factor=Decimal("1"),
                economic_factor=Decimal("1"),
                price_source_class="BANK_BALANCE",
            ),
        ),
    )


def snapshot(result: ReportingLedger):
    return capture_financial_snapshot_v2(
        result,
        valuation_policy(),
        as_of=dt("2026-08-19T11:00:00Z"),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=(
            LiquidityHorizonState(1, Decimal("125"), Decimal("0")),
            LiquidityHorizonState(4, Decimal("125"), Decimal("0")),
            LiquidityHorizonState(8, Decimal("125"), Decimal("0")),
        ),
        required_hard_nav_buffer=Decimal("0"),
        policy_mode="NORMAL",
    )


def fresh_chain():
    book = ledger()
    entry = post_revenue(book)
    event = export_reporting_entry_as_ledger_event_v2(
        entry, book, effective_at=dt("2026-08-19T10:30:00Z"), evidence_class="PROJECT"
    )
    snap = snapshot(book).to_dict()
    close = build_accounting_close_v2(
        [event], snap,
        close_id="close-cycle-003-v2",
        closed_at=dt("2026-08-19T11:05:00Z"),
        requirement_registry_digest=REQ_DIGEST,
    )
    proof = build_ledger_inclusion_proof_v2(
        [event], snap, event_index=0, close=close
    )
    return book, entry, event, snap, close, proof


def test_real_reporting_entry_reaches_snapshot_through_close_and_merkle_proof() -> None:
    book, entry, event, snap, close, proof = fresh_chain()
    assert entry.previous_entry_digest == GENESIS
    assert event["previous_reporting_entry_digest"] == GENESIS
    assert event["reporting_entry_digest"] == entry.digest
    assert snap["sequence"] == 1
    assert snap["ledger_last_entry_digest"] == entry.digest
    assert close.snapshot_sequence == 1
    assert close.snapshot_ledger_last_entry_digest == entry.digest
    assert close.snapshot_ledger_digest == book.digest
    assert verify_accounting_close_v2([event], snap, close) is True
    assert verify_ledger_inclusion_proof_v2(event, proof, close) is True
    assert proof.reporting_entry_digest == entry.digest
    assert proof.event_digest == ledger_event_v2_digest(event)


def test_v2_objects_conform_to_strict_schemas() -> None:
    _, _, event, _, close, proof = fresh_chain()
    for schema_name, payload in (
        ("ledger_event_v2.schema.json", event),
        ("accounting_close_v2.schema.json", close.to_dict()),
        ("ledger_inclusion_proof_v2.schema.json", proof.to_dict()),
    ):
        schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(payload)


def _recompute_reporting_entry_digest(event: dict) -> str:
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
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _rehash_snapshot(snapshot_payload: dict) -> dict:
    result = copy.deepcopy(snapshot_payload)
    result.pop("digest", None)
    result["digest"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return result


def test_fresh_hash_attack_cannot_reuse_old_accounting_close() -> None:
    _, _, event, snap, close, _ = fresh_chain()
    forged_event = copy.deepcopy(event)
    forged_event["lines"][0]["debit"] = "126"
    forged_event["lines"][1]["credit"] = "119"
    forged_event["reporting_entry_digest"] = _recompute_reporting_entry_digest(forged_event)
    verify_ledger_event_v2(forged_event)

    forged_snapshot = copy.deepcopy(snap)
    forged_snapshot["ledger_last_entry_digest"] = forged_event["reporting_entry_digest"]
    forged_snapshot = _rehash_snapshot(forged_snapshot)

    with pytest.raises(AccountingCloseV2Error):
        verify_accounting_close_v2([forged_event], forged_snapshot, close)


def test_hidden_pre_prefix_is_rejected_even_with_valid_event_digest() -> None:
    _, _, event, snap, _, _ = fresh_chain()
    forged = copy.deepcopy(event)
    forged["sequence"] = 2
    forged["previous_reporting_entry_digest"] = "99" * 32
    forged["reporting_entry_digest"] = _recompute_reporting_entry_digest(forged)
    verify_ledger_event_v2(forged)
    forged_snapshot = copy.deepcopy(snap)
    forged_snapshot["sequence"] = 2
    forged_snapshot["ledger_last_entry_digest"] = forged["reporting_entry_digest"]
    forged_snapshot = _rehash_snapshot(forged_snapshot)
    with pytest.raises(AccountingCloseV2Error, match="start at sequence 1"):
        build_accounting_close_v2(
            [forged], forged_snapshot,
            close_id="hidden-prefix",
            closed_at=dt("2026-08-19T11:05:00Z"),
            requirement_registry_digest=REQ_DIGEST,
        )


def test_old_merkle_proof_cannot_prove_changed_event() -> None:
    _, _, event, _, close, proof = fresh_chain()
    forged = copy.deepcopy(event)
    forged["evidence_digest"] = "99" * 32
    forged["reporting_entry_digest"] = _recompute_reporting_entry_digest(forged)
    verify_ledger_event_v2(forged)
    with pytest.raises(AccountingCloseV2Error):
        verify_ledger_inclusion_proof_v2(forged, proof, close)
