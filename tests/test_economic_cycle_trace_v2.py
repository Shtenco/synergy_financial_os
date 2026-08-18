import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sinergy_financial_os.core import AccountingInvariantError
from sinergy_financial_os.economic_cycle_trace_v2 import (
    EconomicCycleTraceV2,
    PHASE_CONTRACTS_V2,
    make_reference_v2,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/economic_cycle_trace_v2_complete.json"
START = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
EXPECTED_DIGEST = "9876d96b68c429d60c128770db0bf39c80a5bf93820d84d2fed86c64601a3823"


def _subject(phase: str) -> str:
    if phase == "FUNDING_STATE":
        return "cohort-001"
    if phase in {"PROJECT_PROPOSAL", "PROJECT_SCREENING", "CAPITAL_AUTHORIZATION", "PROJECT_EVIDENCE"}:
        return "project-001"
    return {
        "FUNDING_SETTLEMENT": "funding-settlement-001",
        "REVENUE_SETTLEMENT": "revenue-settlement-001",
        "ACCOUNTING_SNAPSHOT": "financial-snapshot-001",
        "TRUST_COMMITMENT": "cycle-commitment-001",
    }[phase]


def _digest_for_phase(index: int, phase: str) -> str:
    if phase == "CAPITAL_AUTHORIZATION":
        return "1e814153a18850865543e08b498b60d9bce80dbd34bfb2f4c378f3fe502fe89f"
    return f"{index + 1:02x}" * 32


def _refs(count: int):
    return tuple(
        make_reference_v2(
            phase,
            digest=_digest_for_phase(index, phase),
            subject_id=_subject(phase),
            observed_at=START + timedelta(hours=index),
        )
        for index, (phase, _, _) in enumerate(PHASE_CONTRACTS_V2[:count])
    )


def test_v2_producer_reproduces_exact_complete_fixture() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    trace = EconomicCycleTraceV2(
        cycle_id="cycle-002",
        household_or_funding_subject="cohort-001",
        project_id="project-001",
        references=_refs(9),
    )
    assert trace.digest == EXPECTED_DIGEST
    assert trace.to_dict() == expected


def test_v2_fourth_phase_requires_destination_bound_authorization_v2() -> None:
    ref = _refs(4)[3]
    assert ref.schema_id == "capital.authorization/v2"
    with pytest.raises(AccountingInvariantError):
        type(ref)(
            phase="CAPITAL_AUTHORIZATION",
            schema_id="capital.authorization/v1",
            digest=ref.digest,
            source_repository=ref.source_repository,
            subject_id=ref.subject_id,
            observed_at=ref.observed_at,
        )


def test_v2_still_forbids_skipping_authorization_before_settlement() -> None:
    refs = list(_refs(3))
    refs.append(
        make_reference_v2(
            "FUNDING_SETTLEMENT",
            digest="aa" * 32,
            subject_id="funding-settlement-001",
            observed_at=START + timedelta(hours=3),
        )
    )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTraceV2(
            cycle_id="cycle-skip-v2",
            household_or_funding_subject="cohort-001",
            project_id="project-001",
            references=tuple(refs),
        )


def test_v2_trace_remains_provenance_only() -> None:
    trace = EconomicCycleTraceV2(
        cycle_id="cycle-partial-v2",
        household_or_funding_subject="cohort-001",
        project_id="project-001",
        references=_refs(4),
    )
    assert trace.status == "TRACE_PARTIAL"
    assert trace.authority == "PROVENANCE_ONLY"
    assert trace.profit_recognition == "NOT_PERFORMED"
    assert trace.execution_authority == "NONE"
