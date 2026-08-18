import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sinergy_financial_os.capital_authorization_v2 import (
    CapitalAuthorizationV2,
    verify_authorization_v2_context,
)
from sinergy_financial_os.core import AccountingInvariantError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/capital_authorization_v2_canonical.json"
NOW = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)
EXPECTED_DIGEST = "1e814153a18850865543e08b498b60d9bce80dbd34bfb2f4c378f3fe502fe89f"


def _auth(**changes) -> CapitalAuthorizationV2:
    kwargs = {
        "authorization_id": "auth-funding-v2-001",
        "project_id": "project-001",
        "decision": "APPROVED",
        "decision_authority": "MULTISIG_GOVERNANCE",
        "funding_asset": "USDC",
        "approved_amount": "1000.000",
        "funding_source_id": "sinergy-capital-account",
        "funding_destination_id": "project-001-escrow",
        "payment_idempotency_key": "capital-project-001-auth-v2-001",
        "screening_digest": "aa" * 32,
        "financial_snapshot_digest": "bb" * 32,
        "valuation_policy_digest": "cc" * 32,
        "requirement_registry_digest": "dd" * 32,
        "decision_evidence_digest": "ee" * 32,
        "approver_policy_digest": "ff" * 32,
        "decided_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "financial_snapshot_sequence": 42,
    }
    kwargs.update(changes)
    return CapitalAuthorizationV2(**kwargs)


def test_authoritative_producer_reproduces_exact_v2_fixture() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    auth = _auth()
    assert auth.digest == EXPECTED_DIGEST
    assert auth.to_dict() == expected


def test_v2_binds_source_destination_purpose_and_idempotency_key() -> None:
    auth = _auth()
    assert auth.funding_source_id == "sinergy-capital-account"
    assert auth.funding_destination_id == "project-001-escrow"
    assert auth.payment_purpose == "productive_capital_funding"
    assert auth.payment_idempotency_key == "capital-project-001-auth-v2-001"
    assert auth.usage_policy == "SINGLE_EXACT_PAYMENT"


def test_empty_source_destination_or_idempotency_key_fail_closed() -> None:
    for field in ("funding_source_id", "funding_destination_id", "payment_idempotency_key"):
        with pytest.raises(AccountingInvariantError):
            _auth(**{field: " "})


def test_v2_does_not_allow_partial_or_repeated_usage_policy() -> None:
    with pytest.raises(AccountingInvariantError):
        _auth(usage_policy="PARTIAL_DRAWDOWN")
    with pytest.raises(AccountingInvariantError):
        _auth(usage_policy="REUSABLE")


def test_approver_policy_change_makes_authorization_stale() -> None:
    ok, blockers = verify_authorization_v2_context(
        _auth(),
        current_financial_snapshot_digest="bb" * 32,
        current_financial_snapshot_sequence=42,
        current_valuation_policy_digest="cc" * 32,
        current_requirement_registry_digest="dd" * 32,
        current_approver_policy_digest="11" * 32,
        now=NOW + timedelta(minutes=30),
    )
    assert ok is False
    assert blockers == ("STALE_APPROVER_POLICY",)


def test_exact_v2_context_is_valid_until_expiry() -> None:
    ok, blockers = verify_authorization_v2_context(
        _auth(),
        current_financial_snapshot_digest="bb" * 32,
        current_financial_snapshot_sequence=42,
        current_valuation_policy_digest="cc" * 32,
        current_requirement_registry_digest="dd" * 32,
        current_approver_policy_digest="ff" * 32,
        now=NOW + timedelta(minutes=30),
    )
    assert ok is True
    assert blockers == ()


def test_ai_and_embedded_execution_authority_remain_forbidden() -> None:
    with pytest.raises(AccountingInvariantError):
        _auth(ai_authority="APPROVE")
    with pytest.raises(AccountingInvariantError):
        _auth(execution_authority="SEND")


def test_rejected_v2_has_zero_amount_and_remains_nonexecutable() -> None:
    rejected = _auth(decision="REJECTED", approved_amount="0")
    assert rejected.decision == "REJECTED"
    assert rejected.is_valid_at(NOW + timedelta(minutes=1)) is False
    with pytest.raises(AccountingInvariantError):
        _auth(decision="REJECTED", approved_amount="1")
