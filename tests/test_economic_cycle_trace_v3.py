from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema

from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.economic_cycle_trace_v3 import (
    CycleReferenceV3,
    EconomicCycleTraceV3,
    verify_complete_trace_artifacts_v3,
)


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "fixtures/conformance/capital_authorization_v2_canonical.json"
FUNDING_PATH = ROOT / "fixtures/conformance/settlement_receipt_v2_funding.json"
REVENUE_PATH = ROOT / "fixtures/conformance/settlement_receipt_v2_revenue.json"
TRACE_PATH = ROOT / "fixtures/conformance/economic_cycle_trace_v3_complete.json"
SCHEMA_PATH = ROOT / "schemas/economic_cycle_trace_v3.schema.json"
PROJECT_EVIDENCE_DIGEST = "66" * 32


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _authorization() -> CapitalAuthorizationV2:
    p = _load(AUTH_PATH)
    return CapitalAuthorizationV2(
        authorization_id=p["authorization_id"], project_id=p["project_id"],
        decision=p["decision"], decision_authority=p["decision_authority"],
        funding_asset=p["funding_asset"], approved_amount=Decimal(p["approved_amount"]),
        funding_source_id=p["funding_source_id"], funding_destination_id=p["funding_destination_id"],
        payment_idempotency_key=p["payment_idempotency_key"], payment_purpose=p["payment_purpose"],
        usage_policy=p["usage_policy"], screening_digest=p["screening_digest"],
        financial_snapshot_digest=p["financial_snapshot_digest"],
        financial_snapshot_sequence=p["financial_snapshot_sequence"],
        valuation_policy_digest=p["valuation_policy_digest"],
        requirement_registry_digest=p["requirement_registry_digest"],
        decision_evidence_digest=p["decision_evidence_digest"],
        approver_policy_digest=p["approver_policy_digest"], notes_digest=p["notes_digest"],
        decided_at=_dt(p["decided_at"]), expires_at=_dt(p["expires_at"]),
        execution_authority=p["execution_authority"], ai_authority=p["ai_authority"],
    )


def _trace(payload: dict | None = None) -> EconomicCycleTraceV3:
    p = payload or _load(TRACE_PATH)
    references = tuple(
        CycleReferenceV3(
            phase=r["phase"], schema_id=r["schema_id"], digest=r["digest"],
            source_repository=r["source_repository"], subject_id=r["subject_id"],
            observed_at=_dt(r["observed_at"]),
        )
        for r in p["references"]
    )
    return EconomicCycleTraceV3(
        cycle_id=p["cycle_id"],
        household_or_funding_subject=p["household_or_funding_subject"],
        project_id=p["project_id"],
        references=references,
        authority=p["authority"],
        profit_recognition=p["profit_recognition"],
        execution_authority=p["execution_authority"],
    )


def _rehash_receipt(receipt: dict) -> dict:
    p = copy.deepcopy(receipt)
    p.pop("receipt_digest", None)
    p["receipt_digest"] = hashlib.sha256(
        json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return p


def _replace_ref_digest(trace_payload: dict, phase: str, digest: str) -> dict:
    p = copy.deepcopy(trace_payload)
    for ref in p["references"]:
        if ref["phase"] == phase:
            ref["digest"] = digest
            break
    p.pop("digest", None)
    p["digest"] = hashlib.sha256(
        json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return p


def test_complete_trace_v3_fixture_has_expected_digest_and_schema() -> None:
    fixture = _load(TRACE_PATH)
    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(fixture)
    trace = _trace(fixture)
    assert trace.complete is True
    assert trace.digest == fixture["digest"]
    assert trace.digest == "94e3c28f0abd86ded00e0177387a551eb6663343a5b13f597d4245a70368f897"


def test_complete_trace_v3_verifies_actual_cross_object_arrows() -> None:
    review = verify_complete_trace_artifacts_v3(
        _trace(), authorization=_authorization(),
        funding_receipt=_load(FUNDING_PATH), revenue_receipt=_load(REVENUE_PATH),
        project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.verified is True
    assert review.blockers == ()
    assert review.profit_recognition == "NOT_PERFORMED"
    assert review.accounting_entry_allowed is False


def test_rehashed_redirected_receipt_and_rehashed_trace_still_fail_authorization_link() -> None:
    funding = _load(FUNDING_PATH)
    funding["payee_id"] = "attacker-controlled-destination"
    funding = _rehash_receipt(funding)
    trace_payload = _replace_ref_digest(
        _load(TRACE_PATH), "FUNDING_SETTLEMENT", funding["receipt_digest"]
    )
    review = verify_complete_trace_artifacts_v3(
        _trace(trace_payload), authorization=_authorization(), funding_receipt=funding,
        revenue_receipt=_load(REVENUE_PATH), project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.verified is False
    assert "FUNDING_DESTINATION_MISMATCH" in review.blockers


def test_rehashed_trace_cannot_replace_screening_used_by_authorization() -> None:
    trace_payload = _replace_ref_digest(_load(TRACE_PATH), "PROJECT_SCREENING", "12" * 32)
    review = verify_complete_trace_artifacts_v3(
        _trace(trace_payload), authorization=_authorization(),
        funding_receipt=_load(FUNDING_PATH), revenue_receipt=_load(REVENUE_PATH),
        project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.verified is False
    assert "SCREENING_AUTHORIZATION_LINK_MISMATCH" in review.blockers


def test_trace_requires_settlement_reference_time_to_equal_receipt_finality() -> None:
    p = _load(TRACE_PATH)
    for ref in p["references"]:
        if ref["phase"] == "REVENUE_SETTLEMENT":
            ref["observed_at"] = "2026-08-19T10:02:00Z"
    p.pop("digest", None)
    p["digest"] = hashlib.sha256(
        json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    review = verify_complete_trace_artifacts_v3(
        _trace(p), authorization=_authorization(),
        funding_receipt=_load(FUNDING_PATH), revenue_receipt=_load(REVENUE_PATH),
        project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.verified is False
    assert "REVENUE_FINALITY_TIME_MISMATCH" in review.blockers
