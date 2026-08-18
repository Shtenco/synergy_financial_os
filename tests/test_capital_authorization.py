from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os.capital_authorization import (
    CapitalAuthorization,
    verify_authorization_context,
)
from sinergy_financial_os.core import AccountingInvariantError


NOW = datetime(2026, 8, 18, 19, 0, tzinfo=UTC)


def _authorization(**changes) -> CapitalAuthorization:
    kwargs = {
        "authorization_id": "auth-001",
        "project_id": "project-001",
        "decision": "APPROVED",
        "decision_authority": "HUMAN_COMMITTEE",
        "funding_asset": "USDC",
        "approved_amount": "1000.00",
        "screening_digest": "aa" * 32,
        "financial_snapshot_digest": "bb" * 32,
        "valuation_policy_digest": "cc" * 32,
        "requirement_registry_digest": "dd" * 32,
        "decision_evidence_digest": "ee" * 32,
        "decided_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "financial_snapshot_sequence": 42,
    }
    kwargs.update(changes)
    return CapitalAuthorization(**kwargs)


def test_approved_authorization_requires_positive_amount() -> None:
    with pytest.raises(AccountingInvariantError):
        _authorization(approved_amount="0")


def test_rejected_authorization_must_have_zero_amount() -> None:
    rejected = _authorization(decision="REJECTED", approved_amount="0")
    assert rejected.decision == "REJECTED"
    with pytest.raises(AccountingInvariantError):
        _authorization(decision="REJECTED", approved_amount="1")


def test_ai_cannot_be_capital_decision_authority() -> None:
    with pytest.raises(AccountingInvariantError):
        _authorization(decision_authority="AI")
    with pytest.raises(AccountingInvariantError):
        _authorization(ai_authority="PROPOSE_AND_APPROVE")


def test_authorization_does_not_embed_payment_execution_authority() -> None:
    with pytest.raises(AccountingInvariantError):
        _authorization(execution_authority="EXECUTE_PAYMENT")
    assert _authorization().execution_authority == "SEPARATE_METAPAY_HANDOFF"


def test_authorization_is_bound_to_exact_financial_context() -> None:
    auth = _authorization()
    ok, blockers = verify_authorization_context(
        auth,
        current_financial_snapshot_digest="bb" * 32,
        current_financial_snapshot_sequence=42,
        current_valuation_policy_digest="cc" * 32,
        current_requirement_registry_digest="dd" * 32,
        now=NOW + timedelta(minutes=30),
    )
    assert ok is True
    assert blockers == ()


def test_changed_snapshot_sequence_policy_or_constitution_blocks_handoff() -> None:
    auth = _authorization()
    ok, blockers = verify_authorization_context(
        auth,
        current_financial_snapshot_digest="11" * 32,
        current_financial_snapshot_sequence=43,
        current_valuation_policy_digest="22" * 32,
        current_requirement_registry_digest="33" * 32,
        now=NOW + timedelta(minutes=30),
    )
    assert ok is False
    assert set(blockers) == {
        "STALE_FINANCIAL_SEQUENCE",
        "STALE_FINANCIAL_SNAPSHOT",
        "STALE_REQUIREMENT_REGISTRY",
        "STALE_VALUATION_POLICY",
    }


def test_expired_authorization_blocks_handoff() -> None:
    auth = _authorization(expires_at=NOW + timedelta(minutes=5))
    ok, blockers = verify_authorization_context(
        auth,
        current_financial_snapshot_digest="bb" * 32,
        current_financial_snapshot_sequence=42,
        current_valuation_policy_digest="cc" * 32,
        current_requirement_registry_digest="dd" * 32,
        now=NOW + timedelta(minutes=6),
    )
    assert ok is False
    assert blockers == ("AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID",)


def test_serialization_is_canonical_and_digest_bound() -> None:
    auth = _authorization(approved_amount="1000.000")
    payload = auth.to_dict()
    assert payload["approved_amount"] == "1000"
    assert payload["digest"] == auth.digest
    assert len(auth.digest) == 64


def test_decision_window_must_be_forward_and_timezone_aware() -> None:
    with pytest.raises(AccountingInvariantError):
        _authorization(expires_at=NOW)
    with pytest.raises(AccountingInvariantError):
        _authorization(decided_at=datetime(2026, 8, 18, 19, 0))


def test_snapshot_sequence_is_safe_integer() -> None:
    with pytest.raises(AccountingInvariantError):
        _authorization(financial_snapshot_sequence=True)
    with pytest.raises(AccountingInvariantError):
        _authorization(financial_snapshot_sequence=9_007_199_254_740_992)
