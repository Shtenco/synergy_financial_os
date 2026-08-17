from copy import deepcopy

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    ProjectScreeningPolicy,
    project_proposal_v2_digest,
    screen_project_for_financial_review,
    screen_project_v2_for_financial_review,
)


def _policy() -> ProjectScreeningPolicy:
    return ProjectScreeningPolicy(
        policy_id="project-screen-v2",
        minimum_evidence_status="MODEL_ESTIMATE",
        maximum_risk_score="0.5",
        minimum_private_to_requested_ratio="0.3",
        minimum_first_loss_to_requested_ratio="0.1",
        minimum_foreign_fx_hedged_fraction="0.5",
        maximum_maturity_weeks=100,
    )


def _v2() -> dict:
    return {
        "schema": "project.proposal/v2",
        "project_id": "project-v2",
        "jurisdiction": "KZ",
        "sector": "energy",
        "capex": [{"asset": "KZT", "amount": "100", "source_ref": None}],
        "requested_funding": [{"asset": "KZT", "amount": "70", "source_ref": None}],
        "private_capital": [{"asset": "KZT", "amount": "30", "source_ref": None}],
        "opex_annual": [],
        "maturity_weeks": 52,
        "expected_cash_flows": [],
        "energy_requirement": None,
        "labor_requirement": None,
        "logistics_requirement": None,
        "fx_exposures": [],
        "risk_score": "0.2",
        "first_loss_capital": [{"asset": "KZT", "amount": "7", "source_ref": None}],
        "dependencies": [],
        "milestones": [],
        "evidence_status": "MODEL_ESTIMATE",
        "evidence_bundle_digest": None,
        "source_vintage": "2026-08-17",
        "metadata": {"revision": 2, "scenario": "base"},
    }


def _v1_from_v2(v2: dict) -> dict:
    proposal = deepcopy(v2)
    proposal["schema"] = "project.proposal/v1"
    proposal["risk_score"] = 0.2
    return proposal


def test_v2_screening_preserves_original_v2_proposal_digest() -> None:
    proposal = _v2()
    expected = project_proposal_v2_digest(proposal)
    result = screen_project_v2_for_financial_review(
        proposal,
        _policy(),
        reporting_currency="KZT",
    )
    assert result.status == "REVIEWABLE"
    assert result.proposal_digest == expected
    assert result.proposal_digest != "0" * 64


def test_v2_and_legacy_v1_have_same_economic_screening_verdict() -> None:
    v2 = _v2()
    v1 = _v1_from_v2(v2)
    old_result = screen_project_for_financial_review(
        v1,
        _policy(),
        reporting_currency="KZT",
    )
    new_result = screen_project_v2_for_financial_review(
        v2,
        _policy(),
        reporting_currency="KZT",
    )
    assert old_result.status == new_result.status == "REVIEWABLE"
    assert old_result.requested_funding == new_result.requested_funding
    assert old_result.private_capital == new_result.private_capital
    assert old_result.first_loss_capital == new_result.first_loss_capital
    assert old_result.risk_score == new_result.risk_score


def test_v1_bridge_remains_available_after_v2_adapter_is_added() -> None:
    result = screen_project_for_financial_review(
        _v1_from_v2(_v2()),
        _policy(),
        reporting_currency="KZT",
    )
    assert result.status == "REVIEWABLE"


def test_v2_digest_rejects_float_anywhere_in_payload() -> None:
    proposal = _v2()
    proposal["metadata"]["score"] = 0.25
    with pytest.raises(AccountingInvariantError, match="contains float"):
        project_proposal_v2_digest(proposal)


def test_v2_digest_rejects_decimal_object_anywhere_in_payload() -> None:
    from decimal import Decimal

    proposal = _v2()
    proposal["metadata"]["score"] = Decimal("0.25")
    with pytest.raises(AccountingInvariantError, match="Decimal object"):
        project_proposal_v2_digest(proposal)


def test_v2_digest_rejects_unsafe_integer_anywhere_in_payload() -> None:
    proposal = _v2()
    proposal["metadata"]["counter"] = 9_007_199_254_740_992
    with pytest.raises(AccountingInvariantError, match="safe range"):
        project_proposal_v2_digest(proposal)


def test_v2_screening_rejects_legacy_numeric_risk_score_float() -> None:
    proposal = _v2()
    proposal["risk_score"] = 0.2
    with pytest.raises(AccountingInvariantError, match="contains float"):
        screen_project_v2_for_financial_review(
            proposal,
            _policy(),
            reporting_currency="KZT",
        )


def test_v2_digest_changes_when_decimal_text_changes() -> None:
    first = _v2()
    second = deepcopy(first)
    second["risk_score"] = "0.20"
    assert project_proposal_v2_digest(first) != project_proposal_v2_digest(second)
