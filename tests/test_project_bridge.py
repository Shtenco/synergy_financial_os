import hashlib
import json
from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    ProjectMoneyTranslation,
    ProjectScreeningPolicy,
    screen_project_for_financial_review,
)


def _digest(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal(
    *,
    evidence_status: str = "MODEL_ESTIMATE",
    risk_score: float | None = 0.25,
    private_amount: str = "30000000",
    first_loss_amount: str = "7000000",
    hedge: float = 0.60,
    requested_asset: str = "KZT",
    requested_amount: str = "70000000",
    evidence_bundle_digest: str | None = None,
) -> dict:
    return {
        "schema": "project.proposal/v1",
        "project_id": "kz-datacenter-01",
        "jurisdiction": "KZ",
        "sector": "data-centers",
        "capex": [
            {"asset": "KZT", "amount": "100000000", "source_ref": None},
            {"asset": "CNY", "amount": "500000", "source_ref": None},
        ],
        "requested_funding": [
            {"asset": requested_asset, "amount": requested_amount, "source_ref": None}
        ],
        "private_capital": [
            {"asset": "KZT", "amount": private_amount, "source_ref": None}
        ],
        "opex_annual": [],
        "maturity_weeks": 156,
        "expected_cash_flows": [
            {"period": "2028-Q1", "asset": "KZT", "amount": "12000000", "note": None}
        ],
        "energy_requirement": None,
        "labor_requirement": None,
        "logistics_requirement": None,
        "fx_exposures": [
            {
                "asset": "CNY",
                "amount": "500000",
                "direction": "PAYABLE",
                "hedged_fraction": hedge,
            }
        ],
        "risk_score": risk_score,
        "first_loss_capital": [
            {"asset": "KZT", "amount": first_loss_amount, "source_ref": None}
        ],
        "dependencies": [],
        "milestones": [],
        "evidence_status": evidence_status,
        "evidence_bundle_digest": evidence_bundle_digest,
        "source_vintage": "2026-08-17",
        "metadata": {},
    }


def _policy(**overrides) -> ProjectScreeningPolicy:
    kwargs = {
        "policy_id": "productive-screen-v1",
        "minimum_evidence_status": "MODEL_ESTIMATE",
        "maximum_risk_score": Decimal("0.40"),
        "minimum_private_to_requested_ratio": Decimal("0.30"),
        "minimum_first_loss_to_requested_ratio": Decimal("0.10"),
        "minimum_foreign_fx_hedged_fraction": Decimal("0.50"),
        "maximum_maturity_weeks": 200,
    }
    kwargs.update(overrides)
    return ProjectScreeningPolicy(**kwargs)


def _cny_translation() -> dict[str, ProjectMoneyTranslation]:
    return {
        "CNY": ProjectMoneyTranslation(
            "CNY",
            "KZT",
            "70",
            translation_evidence_digest="cd" * 32,
        )
    }


def _evidence_bundle(project_id: str = "kz-datacenter-01") -> dict:
    payload = {
        "schema": "project.evidence/v1",
        "project_id": project_id,
        "as_of": "2026-08-17T12:00:00+05:00",
        "items": [
            {
                "evidence_id": "bank-settlement-1",
                "evidence_class": "BANK_SETTLEMENT",
                "source_system": "bank-a",
                "reference": "bank-ref-1",
                "observed_at": "2026-08-17T11:55:00+05:00",
                "finality_level": "SETTLED",
                "evidence_digest": "ab" * 32,
                "metadata": {},
            }
        ],
    }
    payload["digest"] = _digest(payload)
    return payload


def test_clean_model_estimate_is_reviewable_but_never_approved() -> None:
    result = screen_project_for_financial_review(
        _proposal(),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "REVIEWABLE"
    assert result.reviewable is True
    assert result.blockers == ()
    assert result.status not in {"APPROVED", "FUNDED", "QE_AUTHORIZED"}
    assert result.requested_funding == Decimal("70000000")
    assert result.private_to_requested_ratio > Decimal("0.42")
    assert result.first_loss_to_requested_ratio == Decimal("0.10")


def test_missing_risk_score_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(risk_score=None),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "RISK_SCORE_MISSING" in result.blockers


def test_high_risk_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(risk_score=0.80),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "RISK_SCORE_ABOVE_POLICY" in result.blockers


def test_insufficient_private_match_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(private_amount="10000000"),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "PRIVATE_MATCH_BELOW_POLICY" in result.blockers


def test_insufficient_first_loss_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(first_loss_amount="1000000"),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "FIRST_LOSS_BELOW_POLICY" in result.blockers


def test_insufficient_foreign_fx_hedge_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(hedge=0.40),
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "FX_HEDGE_BELOW_POLICY:CNY" in result.blockers


def test_scenario_below_policy_evidence_level_returns_no_action() -> None:
    result = screen_project_for_financial_review(
        _proposal(evidence_status="SCENARIO"),
        _policy(minimum_evidence_status="MODEL_ESTIMATE"),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert any(blocker.startswith("EVIDENCE_BELOW_POLICY") for blocker in result.blockers)


def test_observed_claim_requires_matching_verified_evidence_bundle() -> None:
    bundle = _evidence_bundle()
    proposal = _proposal(
        evidence_status="EXTERNALLY_SETTLED",
        evidence_bundle_digest=bundle["digest"],
    )
    result = screen_project_for_financial_review(
        proposal,
        _policy(minimum_evidence_status="OBSERVED_OPERATIONAL"),
        reporting_currency="KZT",
        translations=_cny_translation(),
        evidence_bundle=bundle,
    )
    assert result.status == "REVIEWABLE"
    assert result.evidence_bundle_digest == bundle["digest"]


def test_wrong_project_evidence_bundle_fails_closed() -> None:
    bundle = _evidence_bundle(project_id="another-project")
    proposal = _proposal(
        evidence_status="OBSERVED_OPERATIONAL",
        evidence_bundle_digest=bundle["digest"],
    )
    with pytest.raises(AccountingInvariantError):
        screen_project_for_financial_review(
            proposal,
            _policy(),
            reporting_currency="KZT",
            translations=_cny_translation(),
            evidence_bundle=bundle,
        )


def test_tampered_evidence_bundle_fails_closed() -> None:
    bundle = _evidence_bundle()
    proposal = _proposal(
        evidence_status="OBSERVED_OPERATIONAL",
        evidence_bundle_digest=bundle["digest"],
    )
    bundle["items"][0]["reference"] = "tampered"
    with pytest.raises(AccountingInvariantError):
        screen_project_for_financial_review(
            proposal,
            _policy(),
            reporting_currency="KZT",
            translations=_cny_translation(),
            evidence_bundle=bundle,
        )


def test_foreign_requested_funding_requires_translation_evidence() -> None:
    proposal = _proposal(requested_asset="CNY", requested_amount="1000000")
    with pytest.raises(AccountingInvariantError):
        screen_project_for_financial_review(
            proposal,
            _policy(),
            reporting_currency="KZT",
            translations={},
        )

    result = screen_project_for_financial_review(
        proposal,
        _policy(),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.requested_funding == Decimal("70000000")


def test_maturity_above_policy_returns_no_action() -> None:
    proposal = _proposal()
    proposal["maturity_weeks"] = 260
    result = screen_project_for_financial_review(
        proposal,
        _policy(maximum_maturity_weeks=200),
        reporting_currency="KZT",
        translations=_cny_translation(),
    )
    assert result.status == "NO_ACTION"
    assert "MATURITY_ABOVE_POLICY" in result.blockers
