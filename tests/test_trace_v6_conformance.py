from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import jsonschema

from sinergy_financial_os.accounting_close_v2 import (
    AccountingCloseV2,
    LedgerInclusionProofV2,
    verify_accounting_close_v2,
    verify_financial_snapshot_v2_payload,
    verify_ledger_inclusion_proof_v2,
)
from sinergy_financial_os.economic_cycle_trace_v6 import CycleReferenceV6, EconomicCycleTraceV6
from sinergy_financial_os.ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2


ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures/conformance"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_fixed_v6_vectors_reconstruct_the_same_close_proof_and_trace() -> None:
    event = load("ledger_event_v2_recognized_revenue.json")
    snapshot = load("financial_snapshot_v2_cycle_003.json")
    close_payload = load("accounting_close_v2_cycle_003.json")
    proof_payload = load("ledger_inclusion_proof_v2_cycle_003.json")
    trace_payload = load("economic_cycle_trace_v6_complete.json")

    verify_ledger_event_v2(event)
    verify_financial_snapshot_v2_payload(snapshot)
    assert ledger_event_v2_digest(event) == "6711f4bc972b8c36f8866ba747c6458cf3165deaf5e1e66c0209f89edf9b2776"

    close = AccountingCloseV2(
        close_id=close_payload["close_id"],
        financial_snapshot_digest=close_payload["financial_snapshot_digest"],
        snapshot_sequence=close_payload["snapshot_sequence"],
        snapshot_ledger_digest=close_payload["snapshot_ledger_digest"],
        snapshot_ledger_last_entry_digest=close_payload["snapshot_ledger_last_entry_digest"],
        account_registry_digest=close_payload["account_registry_digest"],
        ledger_root=close_payload["ledger_root"],
        event_count=close_payload["event_count"],
        closed_at=dt(close_payload["closed_at"]),
        valuation_policy_digest=close_payload["valuation_policy_digest"],
        requirement_registry_digest=close_payload["requirement_registry_digest"],
        snapshot_schema=close_payload["snapshot_schema"],
        ledger_event_schema=close_payload["ledger_event_schema"],
        authority=close_payload["authority"],
        profit_recognition=close_payload["profit_recognition"],
        execution_authority=close_payload["execution_authority"],
    )
    assert close.digest == close_payload["digest"]
    assert verify_accounting_close_v2([event], snapshot, close) is True

    proof = LedgerInclusionProofV2(
        close_digest=proof_payload["close_digest"],
        ledger_root=proof_payload["ledger_root"],
        event_digest=proof_payload["event_digest"],
        reporting_entry_digest=proof_payload["reporting_entry_digest"],
        event_id=proof_payload["event_id"],
        event_sequence=proof_payload["event_sequence"],
        leaf_index=proof_payload["leaf_index"],
        event_count=proof_payload["event_count"],
        siblings=(),
        authority=proof_payload["authority"],
        execution_authority=proof_payload["execution_authority"],
    )
    assert proof.digest == proof_payload["digest"]
    assert verify_ledger_inclusion_proof_v2(event, proof, close) is True

    refs = tuple(
        CycleReferenceV6(
            item["phase"], item["schema_id"], item["digest"], item["source_repository"],
            item["subject_id"], dt(item["observed_at"])
        )
        for item in trace_payload["references"]
    )
    trace = EconomicCycleTraceV6(
        trace_payload["cycle_id"],
        trace_payload["household_or_funding_subject"],
        trace_payload["project_id"],
        refs,
        authority=trace_payload["authority"],
        profit_recognition=trace_payload["profit_recognition"],
        accounting_close_authority=trace_payload["accounting_close_authority"],
        execution_authority=trace_payload["execution_authority"],
        trust_finalization=trace_payload["trust_finalization"],
    )
    assert trace.digest == trace_payload["digest"]

    for schema_name, payload in (
        ("ledger_event_v2.schema.json", event),
        ("financial_snapshot_v2.schema.json", snapshot),
        ("accounting_close_v2.schema.json", close_payload),
        ("ledger_inclusion_proof_v2.schema.json", proof_payload),
        ("economic_cycle_trace_v6.schema.json", trace_payload),
    ):
        schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(payload)
