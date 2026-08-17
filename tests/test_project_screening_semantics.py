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


def _bundle(finality: str = "SETTLED") -> dict:
    payload = {
        "schema": "project.evidence/v1",
        "project_id": "project-1",
        "as_of": "2026-08-17T12:00:00+05:00",
        "items": [
            {
                "evidence_id": "e1",
                "evidence_class": "BANK_SETTLEMENT",
                "source_system": "bank-a",
                "reference": "ref-1",
                "observed_at": "2026-08-17T11:50:00+05:00",
                "finality_level": finality,
                "evidence_digest": "ab" * 32,
                "metadata": {},
            }
        ],
    }
    payload["digest"] = _digest(payload)
    return payload


def _proposal(status: str, bundle_digest: str | None) -> dict:
    return {
        "schema": "project.proposal/v1",
        "project_id": "project-1",
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
        "risk_score": 0.2,
        "first_loss_capital": [{"asset": "KZT", "amount": "7", "source_ref": None}],
        "dependencies": [],
        "milestones": [],
        "evidence_status": status,
        "evidence_bundle_digest": bundle_digest,
        "source_vintage": "2026-08-17",
        "metadata": {},
    }


def _policy(**changes) -> ProjectScreeningPolicy:
    kwargs = {
        "policy_id": "policy-1",
        "minimum_evidence_status": "MODEL_ESTIMATE",
        "maximum_risk_score": "0.5",
        "minimum_private_to_requested_ratio": "0.3",
        "minimum_first_loss_to_requested_ratio": "0.1",
        "minimum_foreign_fx_hedged_fraction": "0.5",
        "maximum_maturity_weeks": 100,
    }
    kwargs.update(changes)
    return ProjectScreeningPolicy(**kwargs)


def test_observed_claim_with_digest_but_without_bundle_is_no_action() -> None:
    proposal = _proposal("OBSERVED_OPERATIONAL", "ab" * 32)
    result = screen_project_for_financial_review(
        proposal,
        _policy(),
        reporting_currency="KZT",
    )
    assert result.status == "NO_ACTION"
    assert "EVIDENCE_BUNDLE_NOT_SUPPLIED" in result.blockers


def test_externally_settled_claim_requires_settled_or_audited_item() -> None:
    bundle = _bundle("OBSERVED")
    result = screen_project_for_financial_review(
        _proposal("EXTERNALLY_SETTLED", bundle["digest"]),
        _policy(),
        reporting_currency="KZT",
        evidence_bundle=bundle,
    )
    assert result.status == "NO_ACTION"
    assert "EVIDENCE_FINALITY_BELOW_CLAIM" in result.blockers


def test_audited_claim_requires_audited_item() -> None:
    bundle = _bundle("SETTLED")
    result = screen_project_for_financial_review(
        _proposal("AUDITED", bundle["digest"]),
        _policy(),
        reporting_currency="KZT",
        evidence_bundle=bundle,
    )
    assert result.status == "NO_ACTION"
    assert "EVIDENCE_FINALITY_BELOW_CLAIM" in result.blockers


def test_audited_claim_with_audited_bundle_can_be_reviewable() -> None:
    bundle = _bundle("AUDITED")
    result = screen_project_for_financial_review(
        _proposal("AUDITED", bundle["digest"]),
        _policy(minimum_evidence_status="AUDITED"),
        reporting_currency="KZT",
        evidence_bundle=bundle,
    )
    assert result.status == "REVIEWABLE"
    assert result.blockers == ()


def test_policy_digest_changes_when_threshold_changes() -> None:
    base = _policy()
    changed = _policy(maximum_risk_score="0.4")
    assert base.policy_id == changed.policy_id
    assert base.digest != changed.digest


def test_translation_set_digest_changes_with_fx_rate_or_evidence() -> None:
    proposal = _proposal("MODEL_ESTIMATE", None)
    first = screen_project_for_financial_review(
        proposal,
        _policy(minimum_private_to_requested_ratio="0"),
        reporting_currency="USD",
        translations={
            "KZT": ProjectMoneyTranslation(
                "KZT", "USD", "0.002", translation_evidence_digest="aa" * 32
            )
        },
    )
    second = screen_project_for_financial_review(
        proposal,
        _policy(minimum_private_to_requested_ratio="0"),
        reporting_currency="USD",
        translations={
            "KZT": ProjectMoneyTranslation(
                "KZT", "USD", "0.0021", translation_evidence_digest="bb" * 32
            )
        },
    )
    assert first.translation_set_digest != second.translation_set_digest
    assert first.digest != second.digest


def test_project_screening_result_contains_policy_and_translation_digests() -> None:
    result = screen_project_for_financial_review(
        _proposal("MODEL_ESTIMATE", None),
        _policy(),
        reporting_currency="KZT",
    )
    payload = result.to_dict()
    assert payload["schema"] == "project.screening/v1"
    assert len(payload["policy_digest"]) == 64
    assert len(payload["translation_set_digest"]) == 64
    assert len(payload["digest"]) == 64
    assert payload["status"] in {"REVIEWABLE", "NO_ACTION"}


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_project_screening_rejects_non_finite_numeric_inputs(bad: str) -> None:
    proposal = _proposal("MODEL_ESTIMATE", None)
    proposal["risk_score"] = bad
    with pytest.raises(AccountingInvariantError):
        screen_project_for_financial_review(
            proposal,
            _policy(),
            reporting_currency="KZT",
        )
