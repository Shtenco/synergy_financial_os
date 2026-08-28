import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sinergy_financial_os.economic_cycle_trace import (
    EconomicCycleTrace,
    PHASE_CONTRACTS,
    make_reference,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/economic_cycle_trace_v1_complete.json"
EXPECTED_DIGEST = "c8fbff33f6eea386b5cf1c48db426aa54232f6d831169ccbf4b3a440b8a7eabf"
START = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)


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


def test_financial_os_produces_exact_shared_complete_cycle_fixture() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    references = tuple(
        make_reference(
            phase,
            digest=f"{index + 1:02x}" * 32,
            subject_id=_subject(phase),
            observed_at=START + timedelta(hours=index),
        )
        for index, (phase, _, _) in enumerate(PHASE_CONTRACTS)
    )
    trace = EconomicCycleTrace(
        cycle_id="cycle-001",
        household_or_funding_subject="cohort-001",
        project_id="project-001",
        references=references,
    )
    assert trace.digest == EXPECTED_DIGEST
    assert trace.to_dict() == expected
