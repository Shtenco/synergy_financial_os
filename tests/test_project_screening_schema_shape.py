import json
from pathlib import Path

from sinergy_financial_os import (
    ProjectScreeningPolicy,
    screen_project_for_financial_review,
)


ROOT = Path(__file__).resolve().parents[1]


def _proposal() -> dict:
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
        "evidence_status": "MODEL_ESTIMATE",
        "evidence_bundle_digest": None,
        "source_vintage": "2026-08-17",
        "metadata": {},
    }


def _result_payload() -> dict:
    result = screen_project_for_financial_review(
        _proposal(),
        ProjectScreeningPolicy(
            policy_id="policy-1",
            minimum_evidence_status="MODEL_ESTIMATE",
            maximum_risk_score="0.5",
            minimum_private_to_requested_ratio="0.3",
            minimum_first_loss_to_requested_ratio="0.1",
            minimum_foreign_fx_hedged_fraction="0",
            maximum_maturity_weeks=100,
        ),
        reporting_currency="KZT",
    )
    return result.to_dict()


def test_project_screening_runtime_emits_exact_required_top_level_shape() -> None:
    schema = json.loads(
        (ROOT / "schemas/project_screening_v1.schema.json").read_text(encoding="utf-8")
    )
    payload = _result_payload()
    assert set(payload) == set(schema["required"])
    assert payload["schema"] == "project.screening/v1"


def test_project_screening_runtime_emits_no_undeclared_fields() -> None:
    schema = json.loads(
        (ROOT / "schemas/project_screening_v1.schema.json").read_text(encoding="utf-8")
    )
    payload = _result_payload()
    assert set(payload) <= set(schema["properties"])


def test_project_screening_schema_has_no_authorizing_status() -> None:
    schema = json.loads(
        (ROOT / "schemas/project_screening_v1.schema.json").read_text(encoding="utf-8")
    )
    statuses = set(schema["properties"]["status"]["enum"])
    assert statuses == {"REVIEWABLE", "NO_ACTION"}
    assert statuses.isdisjoint({"APPROVED", "FUNDED", "AUTHORIZED", "QE_AUTHORIZED"})
