from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .core import AccountingInvariantError
from .ledger_event_export_v1 import ledger_event_v1_digest
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2
from .settlement_receipt_v2 import (
    verify_funding_receipt_against_authorization_v2,
    verify_revenue_receipt_lineage_v2,
    verify_settlement_receipt_v2_integrity,
)

SCHEMA = "economic.cycle-trace/v5"
TRUST_FINALIZATION = "EXTERNAL_COMMITMENT_REQUIRED"
HEX = frozenset("0123456789abcdef")
PHASE_CONTRACTS_V5 = (
    ("FUNDING_STATE", "maturity.snapshot/v1", "Shtenco/synergy_matrix_sota"),
    ("PROJECT_PROPOSAL", "project.proposal/v2", "Shtenco/synergy_eurasian"),
    ("PROJECT_SCREENING", "project.screening/v1", "Shtenco/synergy_financial_os"),
    ("CAPITAL_AUTHORIZATION", "capital.authorization/v2", "Shtenco/synergy_financial_os"),
    ("FUNDING_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("PROJECT_EVIDENCE", "project.evidence/v1", "Shtenco/synergy_eurasian"),
    ("REVENUE_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("REVENUE_RECOGNITION", "revenue.recognition/v2", "Shtenco/synergy_financial_os"),
    ("LEDGER_EVENT", "ledger.event/v1", "Shtenco/synergy_financial_os"),
    ("ACCOUNTING_SNAPSHOT", "financial.snapshot/v2", "Shtenco/synergy_financial_os"),
)
INDEX = {phase: i for i, (phase, _, _) in enumerate(PHASE_CONTRACTS_V5)}
SCHEMA_BY_PHASE = {phase: schema for phase, schema, _ in PHASE_CONTRACTS_V5}
SOURCE_BY_PHASE = {phase: source for phase, _, source in PHASE_CONTRACTS_V5}
PROJECT_PHASES = frozenset(
    {"PROJECT_PROPOSAL", "PROJECT_SCREENING", "CAPITAL_AUTHORIZATION", "PROJECT_EVIDENCE", "REVENUE_RECOGNITION"}
)


class EconomicCycleTraceV5Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EconomicCycleTraceV5Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise EconomicCycleTraceV5Error(f"{field_name} must be a 64-character hex digest")
    return result


def _time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EconomicCycleTraceV5Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _time_text(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise EconomicCycleTraceV5Error(f"{field_name} must use canonical UTC Z time")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise EconomicCycleTraceV5Error(f"{field_name} is invalid") from exc


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class CycleReferenceV5:
    phase: str
    schema_id: str
    digest: str
    source_repository: str
    subject_id: str
    observed_at: datetime

    def __post_init__(self) -> None:
        phase = _text(self.phase, "phase").upper()
        if phase not in INDEX:
            raise EconomicCycleTraceV5Error(f"unsupported phase: {phase}")
        if self.schema_id != SCHEMA_BY_PHASE[phase]:
            raise EconomicCycleTraceV5Error(f"{phase} requires {SCHEMA_BY_PHASE[phase]}")
        if self.source_repository != SOURCE_BY_PHASE[phase]:
            raise EconomicCycleTraceV5Error(f"{phase} requires source {SOURCE_BY_PHASE[phase]}")
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "digest", _hex64(self.digest, "digest"))
        object.__setattr__(self, "subject_id", _text(self.subject_id, "subject_id"))
        object.__setattr__(self, "observed_at", _time(self.observed_at, "observed_at"))

    def to_dict(self) -> dict[str, str]:
        return {
            "phase": self.phase,
            "schema_id": self.schema_id,
            "digest": self.digest,
            "source_repository": self.source_repository,
            "subject_id": self.subject_id,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
        }


@dataclass(frozen=True)
class EconomicCycleTraceV5:
    cycle_id: str
    household_or_funding_subject: str
    project_id: str
    references: tuple[CycleReferenceV5, ...]
    authority: str = "PROVENANCE_ONLY"
    profit_recognition: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"
    trust_finalization: str = TRUST_FINALIZATION

    def __post_init__(self) -> None:
        cycle_id = _text(self.cycle_id, "cycle_id")
        funding_subject = _text(self.household_or_funding_subject, "household_or_funding_subject")
        project_id = _text(self.project_id, "project_id")
        if self.authority != "PROVENANCE_ONLY":
            raise EconomicCycleTraceV5Error("trace authority must remain provenance-only")
        if self.profit_recognition != "REFERENCE_ONLY":
            raise EconomicCycleTraceV5Error("trace may reference but cannot perform recognition")
        if self.execution_authority != "NONE":
            raise EconomicCycleTraceV5Error("trace cannot execute financial actions")
        if self.trust_finalization != TRUST_FINALIZATION:
            raise EconomicCycleTraceV5Error("trace must be finalized by an external commitment")
        refs = tuple(self.references)
        if not refs or any(not isinstance(ref, CycleReferenceV5) for ref in refs):
            raise EconomicCycleTraceV5Error("trace requires CycleReferenceV5 values")
        phases = [ref.phase for ref in refs]
        expected = [phase for phase, _, _ in PHASE_CONTRACTS_V5[: len(refs)]]
        if phases != expected or len(phases) != len(set(phases)):
            raise EconomicCycleTraceV5Error("trace must form a strict unique causal prefix")
        times = [ref.observed_at for ref in refs]
        if times != sorted(times):
            raise EconomicCycleTraceV5Error("trace time cannot move backwards")
        if refs[0].subject_id != funding_subject:
            raise EconomicCycleTraceV5Error("FUNDING_STATE subject mismatch")
        for ref in refs:
            if ref.phase in PROJECT_PHASES and ref.subject_id != project_id:
                raise EconomicCycleTraceV5Error(f"{ref.phase} subject must match project_id")
        object.__setattr__(self, "cycle_id", cycle_id)
        object.__setattr__(self, "household_or_funding_subject", funding_subject)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "references", refs)

    @property
    def complete(self) -> bool:
        return len(self.references) == len(PHASE_CONTRACTS_V5)

    @property
    def status(self) -> str:
        return "TRACE_COMPLETE" if self.complete else "TRACE_PARTIAL"

    @property
    def missing_phases(self) -> tuple[str, ...]:
        return tuple(phase for phase, _, _ in PHASE_CONTRACTS_V5[len(self.references) :])

    def reference(self, phase: str) -> CycleReferenceV5:
        normalized = phase.upper().strip()
        for ref in self.references:
            if ref.phase == normalized:
                return ref
        raise EconomicCycleTraceV5Error(f"missing phase {normalized}")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "cycle_id": self.cycle_id,
            "household_or_funding_subject": self.household_or_funding_subject,
            "project_id": self.project_id,
            "status": self.status,
            "complete": self.complete,
            "missing_phases": list(self.missing_phases),
            "references": [ref.to_dict() for ref in self.references],
            "authority": self.authority,
            "profit_recognition": self.profit_recognition,
            "execution_authority": self.execution_authority,
            "trust_finalization": self.trust_finalization,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class CycleArtifactReviewV5:
    status: str
    blockers: tuple[str, ...]
    trace_digest: str
    accounting_reference_only: bool = True
    external_commitment_required: bool = True
    execution_authority: str = "NONE"

    @property
    def verified(self) -> bool:
        return self.status == "CAUSAL_ACCOUNTING_GRAPH_VERIFIED"


def verify_complete_trace_artifacts_v5(
    trace: EconomicCycleTraceV5,
    *,
    authorization: CapitalAuthorizationV2,
    funding_receipt: Mapping[str, Any],
    revenue_receipt: Mapping[str, Any],
    project_evidence_digest: str,
    recognition: RevenueRecognitionDecisionV2,
    ledger_event: Mapping[str, Any],
) -> CycleArtifactReviewV5:
    blockers: set[str] = set()
    if not trace.complete:
        return CycleArtifactReviewV5(
            "CAUSAL_ACCOUNTING_GRAPH_BLOCKED", ("TRACE_NOT_COMPLETE",), trace.digest
        )
    evidence = _hex64(project_evidence_digest, "project_evidence_digest")
    funding = verify_settlement_receipt_v2_integrity(funding_receipt)
    revenue = verify_settlement_receipt_v2_integrity(revenue_receipt)
    blockers.update(verify_funding_receipt_against_authorization_v2(funding, authorization).blockers)
    blockers.update(
        verify_revenue_receipt_lineage_v2(
            revenue, authorization, expected_project_evidence_digest=evidence
        ).blockers
    )
    if recognition.decision != "RECOGNIZED" or not recognition.ledger_posting_allowed:
        blockers.add("REVENUE_NOT_RECOGNIZED")
    if recognition.settlement_receipt_digest != revenue["receipt_digest"]:
        blockers.add("RECOGNITION_RECEIPT_LINK_MISMATCH")
    if recognition.capital_authorization_digest != authorization.digest:
        blockers.add("RECOGNITION_AUTHORIZATION_LINK_MISMATCH")
    if recognition.project_evidence_digest != evidence:
        blockers.add("RECOGNITION_PROJECT_EVIDENCE_LINK_MISMATCH")
    if ledger_event.get("schema") != "ledger.event/v1" or ledger_event.get("event_type") != "EXTERNAL_REVENUE":
        blockers.add("LEDGER_EVENT_TYPE_MISMATCH")
    if ledger_event.get("evidence_digest") != recognition.digest:
        blockers.add("LEDGER_RECOGNITION_EVIDENCE_MISMATCH")

    event_digest = ledger_event_v1_digest(dict(ledger_event))
    links = (
        ("PROJECT_SCREENING", authorization.screening_digest),
        ("CAPITAL_AUTHORIZATION", authorization.digest),
        ("FUNDING_SETTLEMENT", funding["receipt_digest"]),
        ("PROJECT_EVIDENCE", evidence),
        ("REVENUE_SETTLEMENT", revenue["receipt_digest"]),
        ("REVENUE_RECOGNITION", recognition.digest),
        ("LEDGER_EVENT", event_digest),
    )
    for phase, digest in links:
        if trace.reference(phase).digest != digest:
            blockers.add(f"{phase}_REFERENCE_MISMATCH")
    if trace.reference("FUNDING_SETTLEMENT").observed_at != _time_text(funding["finality_time"], "funding.finality_time"):
        blockers.add("FUNDING_FINALITY_TIME_MISMATCH")
    if trace.reference("REVENUE_SETTLEMENT").observed_at != _time_text(revenue["finality_time"], "revenue.finality_time"):
        blockers.add("REVENUE_FINALITY_TIME_MISMATCH")
    if trace.reference("REVENUE_RECOGNITION").observed_at != recognition.recognized_at:
        blockers.add("RECOGNITION_TIME_MISMATCH")
    if trace.reference("LEDGER_EVENT").observed_at != _time_text(ledger_event.get("effective_at"), "ledger_event.effective_at"):
        blockers.add("LEDGER_EVENT_TIME_MISMATCH")

    return CycleArtifactReviewV5(
        status="CAUSAL_ACCOUNTING_GRAPH_BLOCKED" if blockers else "CAUSAL_ACCOUNTING_GRAPH_VERIFIED",
        blockers=tuple(sorted(blockers)),
        trace_digest=trace.digest,
    )


def make_reference_v5(
    phase: str, *, digest: str, subject_id: str, observed_at: datetime
) -> CycleReferenceV5:
    normalized = phase.upper().strip()
    if normalized not in INDEX:
        raise EconomicCycleTraceV5Error(f"unsupported phase: {normalized}")
    return CycleReferenceV5(
        normalized,
        SCHEMA_BY_PHASE[normalized],
        digest,
        SOURCE_BY_PHASE[normalized],
        subject_id,
        observed_at,
    )


def build_trace_v5(
    cycle_id: str,
    household_or_funding_subject: str,
    project_id: str,
    references: Iterable[CycleReferenceV5],
) -> EconomicCycleTraceV5:
    return EconomicCycleTraceV5(
        cycle_id,
        household_or_funding_subject,
        project_id,
        tuple(references),
    )
