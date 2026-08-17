from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from sinergy_financial_os import (
    AccountClass,
    AccountingInvariantError,
    ConsolidationClass,
    FlowType,
    LiquidityHorizonState,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    ValuationPolicy,
    ValuationRule,
    capture_financial_snapshot_v2,
    review_ai_policy_proposal,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _snapshot(*, invariant_failures=()):
    ledger = ReportingLedger("USD")
    ledger.register_account(
        ReportingAccountSpec(
            "asset:cash",
            "Cash",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "HARD_EXTERNAL_ASSET",
        )
    )
    ledger.register_account(
        ReportingAccountSpec(
            "equity:capital",
            "Capital",
            AccountClass.EQUITY,
            ConsolidationClass.EXTERNAL,
            "EQUITY_ACCOUNT",
        )
    )
    ledger.post(
        event_id="capital",
        reference="capital-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest="ab" * 32,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    policy = ValuationPolicy(
        "policy-v1",
        "USD",
        NOW,
        (
            ValuationRule(
                "HARD_EXTERNAL_ASSET", "1", "1", "1", "BANK_BALANCE"
            ),
        ),
    )
    return capture_financial_snapshot_v2(
        ledger,
        policy,
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=(
            LiquidityHorizonState(1, "100", "10"),
            LiquidityHorizonState(4, "100", "20"),
            LiquidityHorizonState(8, "100", "30"),
        ),
        invariant_failures=invariant_failures,
    )


def _proposal(snapshot, *, decision="PROPOSE") -> dict:
    actions = []
    mode = None
    refs = []
    if decision == "PROPOSE":
        actions = [
            {
                "action_type": "CREDIT_CAP",
                "target": "productive-credit",
                "value": "0.20",
                "unit": "ratio",
                "lower_bound": "0",
                "upper_bound": "0.30",
                "reason_code": "HEALTHY_LIQUIDITY",
            }
        ]
        mode = "NORMAL"
        refs = ["REQ-FIN-009"]
    return {
        "schema": "ai.policy-proposal/v2",
        "proposal_id": "proposal-1",
        "generated_at": (NOW + timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=31)).isoformat(),
        "model_id": "NEXUS-policy-review",
        "model_artifact_digest": "cd" * 32,
        "input_snapshot_schema": "financial.snapshot/v2",
        "input_snapshot_digest": snapshot.digest,
        "input_ledger_sequence": snapshot.sequence,
        "input_valuation_policy_digest": snapshot.valuation_policy_digest,
        "decision": decision,
        "authorization": "NONE",
        "proposed_policy_mode": mode,
        "actions": actions,
        "hard_invariant_refs": refs,
        "evidence_refs": ["ef" * 32],
        "project_screening_refs": [],
        "notes": None,
    }


def test_exact_current_snapshot_proposal_is_reviewable_not_executable() -> None:
    snapshot = _snapshot()
    review = review_ai_policy_proposal(
        _proposal(snapshot),
        snapshot,
        now=NOW + timedelta(minutes=2),
    )
    assert review.status == "REVIEWABLE"
    assert review.reviewable is True
    assert review.status not in {"APPROVED", "EXECUTABLE", "AUTHORIZED"}


def test_changed_snapshot_digest_makes_proposal_stale() -> None:
    snapshot = _snapshot()
    proposal = _proposal(snapshot)
    proposal["input_snapshot_digest"] = "11" * 32
    review = review_ai_policy_proposal(
        proposal,
        snapshot,
        now=NOW + timedelta(minutes=2),
    )
    assert review.status == "STALE"
    assert "STALE_INPUT_SNAPSHOT" in review.blockers


def test_changed_ledger_sequence_or_valuation_policy_makes_proposal_stale() -> None:
    snapshot = _snapshot()
    proposal = _proposal(snapshot)
    proposal["input_ledger_sequence"] = snapshot.sequence + 1
    proposal["input_valuation_policy_digest"] = "22" * 32
    review = review_ai_policy_proposal(
        proposal,
        snapshot,
        now=NOW + timedelta(minutes=2),
    )
    assert review.status == "STALE"
    assert "STALE_LEDGER_SEQUENCE" in review.blockers
    assert "STALE_VALUATION_POLICY" in review.blockers


def test_expired_proposal_is_stale() -> None:
    snapshot = _snapshot()
    review = review_ai_policy_proposal(
        _proposal(snapshot),
        snapshot,
        now=NOW + timedelta(hours=1),
    )
    assert review.status == "STALE"
    assert "PROPOSAL_EXPIRED" in review.blockers


def test_snapshot_invariant_failure_blocks_otherwise_current_proposal() -> None:
    snapshot = _snapshot(invariant_failures=("LCR_1W_BELOW_FLOOR",))
    review = review_ai_policy_proposal(
        _proposal(snapshot),
        snapshot,
        now=NOW + timedelta(minutes=2),
    )
    assert review.status == "BLOCKED"
    assert "CURRENT_SNAPSHOT_INVARIANT:LCR_1W_BELOW_FLOOR" in review.blockers


def test_no_action_remains_no_action() -> None:
    snapshot = _snapshot()
    review = review_ai_policy_proposal(
        _proposal(snapshot, decision="NO_ACTION"),
        snapshot,
        now=NOW + timedelta(minutes=2),
    )
    assert review.status == "NO_ACTION"
    assert review.reviewable is False


def test_authorization_other_than_none_is_rejected() -> None:
    snapshot = _snapshot()
    proposal = _proposal(snapshot)
    proposal["authorization"] = "EXECUTE"
    with pytest.raises(AccountingInvariantError):
        review_ai_policy_proposal(
            proposal,
            snapshot,
            now=NOW + timedelta(minutes=2),
        )


def test_action_outside_declared_bounds_is_rejected() -> None:
    snapshot = _snapshot()
    proposal = _proposal(snapshot)
    proposal["actions"][0]["value"] = "0.40"
    with pytest.raises(AccountingInvariantError):
        review_ai_policy_proposal(
            proposal,
            snapshot,
            now=NOW + timedelta(minutes=2),
        )


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_action_values_are_rejected(bad: str) -> None:
    snapshot = _snapshot()
    proposal = _proposal(snapshot)
    proposal["actions"][0]["value"] = bad
    with pytest.raises(AccountingInvariantError):
        review_ai_policy_proposal(
            proposal,
            snapshot,
            now=NOW + timedelta(minutes=2),
        )


def test_duplicate_or_invalid_evidence_refs_are_rejected() -> None:
    snapshot = _snapshot()
    duplicate = _proposal(snapshot)
    duplicate["evidence_refs"] = ["ef" * 32, "ef" * 32]
    with pytest.raises(AccountingInvariantError):
        review_ai_policy_proposal(
            duplicate,
            snapshot,
            now=NOW + timedelta(minutes=2),
        )

    invalid = _proposal(snapshot)
    invalid["project_screening_refs"] = ["not-a-digest"]
    with pytest.raises(AccountingInvariantError):
        review_ai_policy_proposal(
            invalid,
            snapshot,
            now=NOW + timedelta(minutes=2),
        )
