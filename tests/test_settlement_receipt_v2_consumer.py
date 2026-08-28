from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema

from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.settlement_receipt_v2 import (
    verify_funding_receipt_against_authorization_v2,
    verify_revenue_receipt_lineage_v2,
    verify_settlement_receipt_v2_integrity,
)


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "fixtures/conformance/capital_authorization_v2_canonical.json"
FUNDING_PATH = ROOT / "fixtures/conformance/settlement_receipt_v2_funding.json"
REVENUE_PATH = ROOT / "fixtures/conformance/settlement_receipt_v2_revenue.json"
SCHEMA_PATH = ROOT / "schemas/settlement_receipt_v2.schema.json"
PROJECT_EVIDENCE_DIGEST = "66" * 32


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _authorization() -> CapitalAuthorizationV2:
    payload = _load(AUTH_PATH)
    authorization = CapitalAuthorizationV2(
        authorization_id=payload["authorization_id"],
        project_id=payload["project_id"],
        decision=payload["decision"],
        decision_authority=payload["decision_authority"],
        funding_asset=payload["funding_asset"],
        approved_amount=Decimal(payload["approved_amount"]),
        funding_source_id=payload["funding_source_id"],
        funding_destination_id=payload["funding_destination_id"],
        payment_idempotency_key=payload["payment_idempotency_key"],
        payment_purpose=payload["payment_purpose"],
        usage_policy=payload["usage_policy"],
        screening_digest=payload["screening_digest"],
        financial_snapshot_digest=payload["financial_snapshot_digest"],
        financial_snapshot_sequence=payload["financial_snapshot_sequence"],
        valuation_policy_digest=payload["valuation_policy_digest"],
        requirement_registry_digest=payload["requirement_registry_digest"],
        decision_evidence_digest=payload["decision_evidence_digest"],
        approver_policy_digest=payload["approver_policy_digest"],
        notes_digest=payload["notes_digest"],
        decided_at=_dt(payload["decided_at"]),
        expires_at=_dt(payload["expires_at"]),
        execution_authority=payload["execution_authority"],
        ai_authority=payload["ai_authority"],
    )
    assert authorization.digest == payload["digest"]
    return authorization


def _rehash(receipt: dict) -> dict:
    result = copy.deepcopy(receipt)
    result.pop("receipt_digest", None)
    digest = hashlib.sha256(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    result["receipt_digest"] = digest
    return result


def test_mirrored_schema_accepts_both_metapay_fixtures() -> None:
    schema = _load(SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(_load(FUNDING_PATH))
    validator.validate(_load(REVENUE_PATH))


def test_funding_receipt_is_accepted_only_as_causal_evidence() -> None:
    receipt = _load(FUNDING_PATH)
    review = verify_funding_receipt_against_authorization_v2(receipt, _authorization())
    assert review.accepted_as_causal_evidence is True
    assert review.blockers == ()
    assert review.receipt_digest == "cedcfe564fed28c5902cbed40361e9924afc8ccaa9f5d535b5b35cc019f06588"
    assert review.profit_recognition == "NOT_PERFORMED"
    assert review.accounting_entry_allowed is False


def test_valid_new_hash_cannot_hide_redirected_funding_destination() -> None:
    receipt = _load(FUNDING_PATH)
    receipt["payee_id"] = "attacker-controlled-destination"
    tampered = _rehash(receipt)
    verify_settlement_receipt_v2_integrity(tampered)
    review = verify_funding_receipt_against_authorization_v2(tampered, _authorization())
    assert review.accepted_as_causal_evidence is False
    assert "FUNDING_DESTINATION_MISMATCH" in review.blockers


def test_valid_new_hash_cannot_hide_changed_funding_amount() -> None:
    receipt = _load(FUNDING_PATH)
    receipt["source_amount"] = "999"
    tampered = _rehash(receipt)
    verify_settlement_receipt_v2_integrity(tampered)
    review = verify_funding_receipt_against_authorization_v2(tampered, _authorization())
    assert review.accepted_as_causal_evidence is False
    assert "FUNDING_AMOUNT_MISMATCH" in review.blockers


def test_valid_new_hash_cannot_hide_changed_idempotency_binding() -> None:
    receipt = _load(FUNDING_PATH)
    receipt["causal_binding"]["intent_idempotency_key"] = "capital-project-001-replay-999"
    tampered = _rehash(receipt)
    verify_settlement_receipt_v2_integrity(tampered)
    review = verify_funding_receipt_against_authorization_v2(tampered, _authorization())
    assert review.accepted_as_causal_evidence is False
    assert "PAYMENT_IDEMPOTENCY_KEY_MISMATCH" in review.blockers


def test_revenue_receipt_lineage_is_verified_but_not_accounted() -> None:
    receipt = _load(REVENUE_PATH)
    review = verify_revenue_receipt_lineage_v2(
        receipt,
        _authorization(),
        expected_project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.accepted_as_causal_evidence is True
    assert review.blockers == ()
    assert review.profit_recognition == "NOT_PERFORMED"
    assert review.accounting_entry_allowed is False


def test_recomputed_receipt_hash_cannot_substitute_other_project_evidence() -> None:
    receipt = _load(REVENUE_PATH)
    receipt["causal_binding"]["project_evidence_digest"] = "88" * 32
    tampered = _rehash(receipt)
    verify_settlement_receipt_v2_integrity(tampered)
    review = verify_revenue_receipt_lineage_v2(
        tampered,
        _authorization(),
        expected_project_evidence_digest=PROJECT_EVIDENCE_DIGEST,
    )
    assert review.accepted_as_causal_evidence is False
    assert "PROJECT_EVIDENCE_DIGEST_MISMATCH" in review.blockers
