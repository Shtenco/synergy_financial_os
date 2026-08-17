import json
from pathlib import Path

from sinergy_financial_os import (
    ProjectScreeningPolicy,
    project_proposal_v2_digest,
    screen_project_v2_for_financial_review,
)
from sinergy_financial_os.canonical_json import canonical_json_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/project_proposal_v2_kz_energy_pilot.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _policy() -> ProjectScreeningPolicy:
    return ProjectScreeningPolicy(
        policy_id="kz-energy-conformance-policy-v1",
        minimum_evidence_status="MODEL_ESTIMATE",
        maximum_risk_score="0.5",
        minimum_private_to_requested_ratio="0.3",
        minimum_first_loss_to_requested_ratio="0.1",
        minimum_foreign_fx_hedged_fraction="0.5",
        maximum_maturity_weeks=200,
    )


def test_shared_project_v2_fixture_has_one_canonical_digest() -> None:
    payload = _payload()
    assert project_proposal_v2_digest(payload) == canonical_json_digest(payload)
    assert len(project_proposal_v2_digest(payload)) == 64


def test_shared_project_v2_fixture_is_reviewable_under_explicit_reference_policy() -> None:
    payload = _payload()
    proposal_digest = project_proposal_v2_digest(payload)
    result = screen_project_v2_for_financial_review(
        payload,
        _policy(),
        reporting_currency="KZT",
    )
    assert result.status == "REVIEWABLE"
    assert result.blockers == ()
    assert result.proposal_digest == proposal_digest
    assert result.requested_funding == 70_000_000
    assert result.private_capital == 30_000_000
    assert result.first_loss_capital == 7_000_000


def test_shared_project_v2_fixture_fails_closed_when_policy_tightens() -> None:
    payload = _payload()
    strict = ProjectScreeningPolicy(
        policy_id="kz-energy-conformance-policy-strict",
        minimum_evidence_status="MODEL_ESTIMATE",
        maximum_risk_score="0.2",
        minimum_private_to_requested_ratio="0.5",
        minimum_first_loss_to_requested_ratio="0.2",
        minimum_foreign_fx_hedged_fraction="0.9",
        maximum_maturity_weeks=100,
    )
    result = screen_project_v2_for_financial_review(
        payload,
        strict,
        reporting_currency="KZT",
    )
    assert result.status == "NO_ACTION"
    assert "RISK_SCORE_ABOVE_POLICY" in result.blockers
    assert "PRIVATE_MATCH_BELOW_POLICY" in result.blockers
    assert "FIRST_LOSS_BELOW_POLICY" in result.blockers
    assert "FX_HEDGE_BELOW_POLICY:USD" in result.blockers
    assert "MATURITY_ABOVE_POLICY" in result.blockers


def test_screening_never_upgrades_fixture_into_authorization() -> None:
    result = screen_project_v2_for_financial_review(
        _payload(),
        _policy(),
        reporting_currency="KZT",
    )
    assert result.status not in {"APPROVED", "FUNDED", "AUTHORIZED", "QE_AUTHORIZED"}
