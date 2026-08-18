from datetime import UTC, datetime, timedelta

import pytest

from sinergy_financial_os.core import AccountingInvariantError
from sinergy_financial_os.economic_cycle_trace import (
    EconomicCycleTrace,
    PHASE_CONTRACTS,
    make_reference,
)


START = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
PROJECT_ID = "project-001"
FUNDING_SUBJECT = "household-cohort-001"


def _subject(phase: str) -> str:
    if phase == "FUNDING_STATE":
        return FUNDING_SUBJECT
    if phase in {
        "PROJECT_PROPOSAL",
        "PROJECT_SCREENING",
        "CAPITAL_AUTHORIZATION",
        "PROJECT_EVIDENCE",
    }:
        return PROJECT_ID
    return f"{phase.lower()}-subject"


def _refs(count: int):
    refs = []
    for index, (phase, _, _) in enumerate(PHASE_CONTRACTS[:count]):
        refs.append(
            make_reference(
                phase,
                digest=f"{index + 1:02x}" * 32,
                subject_id=_subject(phase),
                observed_at=START + timedelta(hours=index),
            )
        )
    return tuple(refs)


def test_partial_trace_is_exact_causal_prefix_and_lists_missing_phases() -> None:
    trace = EconomicCycleTrace(
        cycle_id="cycle-001",
        household_or_funding_subject=FUNDING_SUBJECT,
        project_id=PROJECT_ID,
        references=_refs(4),
    )
    assert trace.status == "TRACE_PARTIAL"
    assert trace.complete is False
    assert trace.missing_phases[0] == "FUNDING_SETTLEMENT"
    assert trace.profit_recognition == "NOT_PERFORMED"
    assert trace.execution_authority == "NONE"


def test_complete_trace_contains_all_nine_required_phases() -> None:
    trace = EconomicCycleTrace(
        cycle_id="cycle-complete",
        household_or_funding_subject=FUNDING_SUBJECT,
        project_id=PROJECT_ID,
        references=_refs(len(PHASE_CONTRACTS)),
    )
    assert trace.status == "TRACE_COMPLETE"
    assert trace.complete is True
    assert trace.missing_phases == ()
    assert len(trace.references) == 9
    assert len(trace.digest) == 64


def test_later_phase_cannot_skip_capital_authorization() -> None:
    refs = list(_refs(3))
    refs.append(
        make_reference(
            "FUNDING_SETTLEMENT",
            digest="aa" * 32,
            subject_id="funding-payment-1",
            observed_at=START + timedelta(hours=3),
        )
    )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-skip",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=tuple(refs),
        )


def test_accounting_snapshot_cannot_exist_in_trace_before_revenue_settlement() -> None:
    refs = list(_refs(7))
    refs[-1] = make_reference(
        "ACCOUNTING_SNAPSHOT",
        digest="aa" * 32,
        subject_id="snapshot-1",
        observed_at=START + timedelta(hours=6),
    )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-bad-order",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=tuple(refs),
        )


def test_phase_schema_and_source_repository_are_fixed() -> None:
    ref = make_reference(
        "PROJECT_PROPOSAL",
        digest="aa" * 32,
        subject_id=PROJECT_ID,
        observed_at=START,
    )
    assert ref.schema_id == "project.proposal/v2"
    assert ref.source_repository == "Shtenco/synergy_eurasian"
    with pytest.raises(AccountingInvariantError):
        type(ref)(
            phase="PROJECT_PROPOSAL",
            schema_id="project.proposal/v1",
            digest="aa" * 32,
            source_repository="Shtenco/synergy_eurasian",
            subject_id=PROJECT_ID,
            observed_at=START,
        )


def test_project_domain_subjects_must_match_trace_project() -> None:
    refs = list(_refs(2))
    proposal = refs[1]
    refs[1] = type(proposal)(
        phase=proposal.phase,
        schema_id=proposal.schema_id,
        digest=proposal.digest,
        source_repository=proposal.source_repository,
        subject_id="other-project",
        observed_at=proposal.observed_at,
    )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-wrong-project",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=tuple(refs),
        )


def test_observation_time_cannot_move_backwards() -> None:
    refs = list(_refs(3))
    screening = refs[2]
    refs[2] = type(screening)(
        phase=screening.phase,
        schema_id=screening.schema_id,
        digest=screening.digest,
        source_repository=screening.source_repository,
        subject_id=screening.subject_id,
        observed_at=START - timedelta(seconds=1),
    )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-time-travel",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=tuple(refs),
        )


def test_trace_cannot_claim_profit_or_execution_authority() -> None:
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-profit",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=_refs(1),
            profit_recognition="RECOGNIZED",
        )
    with pytest.raises(AccountingInvariantError):
        EconomicCycleTrace(
            cycle_id="cycle-execute",
            household_or_funding_subject=FUNDING_SUBJECT,
            project_id=PROJECT_ID,
            references=_refs(1),
            execution_authority="EXECUTE",
        )
