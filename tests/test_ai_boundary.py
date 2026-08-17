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
    requirement_registry_digest,
    review_ai_policy_proposal,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _requirement_registry() -> dict:
    return {
        "schema": "sinergy.requirement-registry/v1",
        "as_of": "2026-08-17",
        "default_verification_status": "PENDING_RUNNER",
        "requirements": [
            {
                "id": "REQ-FIN-009",
                "statement": "LCR is computed only after explicit horizon outflows.",
            },
            {
                "id": "REQ-AI-001",
                "statement": "AI outputs remain proposals only.",
            },
        ],
    }


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


def _proposal(snapshot, registry, *, decision="PROPOSE") -> dict:
    actions = []
    mode = None
    refs = []
    if decision == "PROPOSE":
        actions = [
            {
                "action_type": "CREDIT_CAP",
                "target": "productive-credit",
                "value": "0.2",
                "unit": "ratio",
                "lower_bound": "0",
                "upper_bound": "0.3",
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
        "input_requirement_registry_digest": requirement_registry_digest(registry),
        "decision": decision,
        "authorization": "NONE",
        "proposed_policy_mode": mode,
        "actions": actions,
        "hard_invariant_refs": refs,
        "evidence_refs": ["ef" * 32],
        "project_screening_refs": [],
        "notes": None,
    }


def _review(proposal: dict, snapshot, registry, *, now=None):
    return review_ai_policy_proposal(
        proposal,
        snapshot,
        now=now or NOW + timedelta(minutes=2),
        requirement_registry=registry,
    )


def test_exact_current_snapshot_and_constitution_is_reviewable_not_executable() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    review = _review(_proposal(snapshot, registry), snapshot, registry)
    assert review.status == "REVIEWABLE"
    assert review.reviewable is True
    assert review.requirement_registry_digest == requirement_registry_digest(registry)
    assert review.status not in {"APPROVED", "EXECUTABLE", "AUTHORIZED"}


def test_changed_snapshot_digest_makes_proposal_stale() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["input_snapshot_digest"] = "11" * 32
    review = _review(proposal, snapshot, registry)
    assert review.status == "STALE"
    assert "STALE_INPUT_SNAPSHOT" in review.blockers


def test_changed_ledger_sequence_or_valuation_policy_makes_proposal_stale() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["input_ledger_sequence"] = snapshot.sequence + 1
    proposal["input_valuation_policy_digest"] = "22" * 32
    review = _review(proposal, snapshot, registry)
    assert review.status == "STALE"
    assert "STALE_LEDGER_SEQUENCE" in review.blockers
    assert "STALE_VALUATION_POLICY" in review.blockers


def test_changed_requirement_meaning_under_same_ids_makes_proposal_stale() -> None:
    snapshot = _snapshot()
    original_registry = _requirement_registry()
    proposal = _proposal(snapshot, original_registry)

    changed_registry = deepcopy(original_registry)
    changed_registry["requirements"][0]["statement"] = (
        "LCR may be approximated from incomplete browser data."
    )
    assert {
        item["id"] for item in original_registry["requirements"]
    } == {item["id"] for item in changed_registry["requirements"]}
    assert requirement_registry_digest(original_registry) != requirement_registry_digest(
        changed_registry
    )

    review = _review(proposal, snapshot, changed_registry)
    assert review.status == "STALE"
    assert "STALE_REQUIREMENT_REGISTRY" in review.blockers


def test_expired_proposal_is_stale() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    review = _review(
        _proposal(snapshot, registry),
        snapshot,
        registry,
        now=NOW + timedelta(hours=1),
    )
    assert review.status == "STALE"
    assert "PROPOSAL_EXPIRED" in review.blockers


def test_snapshot_invariant_failure_blocks_otherwise_current_proposal() -> None:
    snapshot = _snapshot(invariant_failures=("LCR_1W_BELOW_FLOOR",))
    registry = _requirement_registry()
    review = _review(_proposal(snapshot, registry), snapshot, registry)
    assert review.status == "BLOCKED"
    assert "CURRENT_SNAPSHOT_INVARIANT:LCR_1W_BELOW_FLOOR" in review.blockers


def test_no_action_remains_no_action_but_is_still_constitution_bound() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    review = _review(
        _proposal(snapshot, registry, decision="NO_ACTION"),
        snapshot,
        registry,
    )
    assert review.status == "NO_ACTION"
    assert review.reviewable is False
    assert review.requirement_registry_digest == requirement_registry_digest(registry)


def test_unknown_requirement_reference_is_rejected_even_with_current_registry_digest() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["hard_invariant_refs"] = ["REQ-FAKE-999"]
    with pytest.raises(AccountingInvariantError, match="unknown hard invariant reference"):
        _review(proposal, snapshot, registry)


def test_duplicate_hard_requirement_references_are_rejected() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["hard_invariant_refs"] = ["REQ-FIN-009", "REQ-FIN-009"]
    with pytest.raises(AccountingInvariantError, match="must be unique"):
        _review(proposal, snapshot, registry)


def test_authorization_other_than_none_is_rejected() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["authorization"] = "EXECUTE"
    with pytest.raises(AccountingInvariantError):
        _review(proposal, snapshot, registry)


def test_action_outside_declared_bounds_is_rejected() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["actions"][0]["value"] = "0.4"
    with pytest.raises(AccountingInvariantError):
        _review(proposal, snapshot, registry)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_action_values_are_rejected(bad: str) -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["actions"][0]["value"] = bad
    with pytest.raises(AccountingInvariantError):
        _review(proposal, snapshot, registry)


@pytest.mark.parametrize("bad", ["0.20", "00", "-0"])
def test_noncanonical_action_decimal_text_is_rejected(bad: str) -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    proposal = _proposal(snapshot, registry)
    proposal["actions"][0]["value"] = bad
    with pytest.raises(AccountingInvariantError, match="canonical decimal"):
        _review(proposal, snapshot, registry)


def test_duplicate_or_invalid_evidence_refs_are_rejected() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()

    duplicate = _proposal(snapshot, registry)
    duplicate["evidence_refs"] = ["ef" * 32, "ef" * 32]
    with pytest.raises(AccountingInvariantError, match="unique digests"):
        _review(duplicate, snapshot, registry)

    invalid = _proposal(snapshot, registry)
    invalid["project_screening_refs"] = ["not-a-digest"]
    with pytest.raises(AccountingInvariantError, match="64-character hex"):
        _review(invalid, snapshot, registry)


def test_unsafe_or_boolean_ledger_sequence_is_rejected() -> None:
    snapshot = _snapshot()
    registry = _requirement_registry()
    for bad in (True, 9_007_199_254_740_992):
        proposal = _proposal(snapshot, registry)
        proposal["input_ledger_sequence"] = bad
        with pytest.raises(AccountingInvariantError, match="safe integer"):
            _review(proposal, snapshot, registry)
