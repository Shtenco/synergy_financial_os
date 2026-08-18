from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .core import AccountingInvariantError
from .settlement_receipt_v2 import (
    verify_funding_receipt_against_authorization_v2,
    verify_revenue_receipt_lineage_v2,
    verify_settlement_receipt_v2_integrity,
)


SCHEMA = "economic.cycle-trace/v3"
HEX = frozenset("0123456789abcdef")
PHASE_CONTRACTS_V3: tuple[tuple[str, str, str], ...] = (
    ("FUNDING_STATE", "maturity.snapshot/v1", "Shtenco/synergy_matrix_sota"),
    ("PROJECT_PROPOSAL", "project.proposal/v2", "Shtenco/synergy_eurasian"),
    ("PROJECT_SCREENING", "project.screening/v1", "Shtenco/synergy_financial_os"),
    ("CAPITAL_AUTHORIZATION", "capital.authorization/v2", "Shtenco/synergy_financial_os"),
    ("FUNDING_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("PROJECT_EVIDENCE", "project.evidence/v1", "Shtenco/synergy_eurasian"),
    ("REVENUE_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("ACCOUNTING_SNAPSHOT", "financial.snapshot/v2", "Shtenco/synergy_financial_os"),
    ("TRUST_COMMITMENT", "commitment.envelope/v2", "Shtenco/synergy_ai_blockchain"),
)
INDEX = {phase: index for index, (phase, _, _) in enumerate(PHASE_CONTRACTS_V3)}
SCHEMAS = {phase: schema for phase, schema, _ in PHASE_CONTRACTS_V3}
SOURCES = {phase: source for phase, _, source in PHASE_CONTRACTS_V3}
PROJECT_PHASES = frozenset(
    {"PROJECT_PROPOSAL", "PROJECT_SCREENING", "CAPITAL_AUTHORIZATION", "PROJECT_EVIDENCE"}
)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingInvariantError(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(char not in HEX for char in result):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return result


def _time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _time_text(value: str, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise AccountingInvariantError(f"{field_name} must be canonical UTC Z time")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise AccountingInvariantError(f"{field_name} is invalid") from exc


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class CycleReferenceV3:
    phase: str
    schema_id: str
    digest: str
    source_repository: str
    subject_id: str
    observed_at: datetime

    def __post_init__(self) -> None:
        phase = _text(self.phase, "phase").upper()
        if phase not in INDEX:
            raise AccountingInvariantError(f"unsupported cycle phase: {phase}")
        schema = _text(self.schema_id, "schema_id")
        source = _text(self.source_repository, "source_repository")
        if schema != SCHEMAS[phase]:
            raise AccountingInvariantError(f"{phase} requires schema {SCHEMAS[phase]}")
        if source != SOURCES[phase]:
            raise AccountingInvariantError(f"{phase} requires source {SOURCES[phase]}")
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "schema_id", schema)
        object.__setattr__(self, "source_repository", source)
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
class EconomicCycleTraceV3:
    cycle_id: str
    household_or_funding_subject: str
    project_id: str
    references: tuple[CycleReferenceV3, ...]
    authority: str = "PROVENANCE_ONLY"
    profit_recognition: str = "NOT_PERFORMED"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        cycle_id = _text(self.cycle_id, "cycle_id")
        funding_subject = _text(
            self.household_or_funding_subject, "household_or_funding_subject"
        )
        project_id = _text(self.project_id, "project_id")
        if self.authority != "PROVENANCE_ONLY":
            raise AccountingInvariantError("cycle trace is provenance only")
        if self.profit_recognition != "NOT_PERFORMED":
            raise AccountingInvariantError("cycle trace cannot recognize profit")
        if self.execution_authority != "NONE":
            raise AccountingInvariantError("cycle trace cannot execute financial actions")
        references = tuple(self.references)
        if not references or any(not isinstance(ref, CycleReferenceV3) for ref in references):
            raise AccountingInvariantError("trace requires CycleReferenceV3 values")
        phases = [ref.phase for ref in references]
        if len(phases) != len(set(phases)):
            raise AccountingInvariantError("cycle phases must be unique")
        expected = [phase for phase, _, _ in PHASE_CONTRACTS_V3[: len(phases)]]
        if phases != expected:
            raise AccountingInvariantError("trace must form canonical causal prefix")
        times = [ref.observed_at for ref in references]
        if times != sorted(times):
            raise AccountingInvariantError("trace time cannot move backwards")
        for ref in references:
            if ref.phase in PROJECT_PHASES and ref.subject_id != project_id:
                raise AccountingInvariantError(f"{ref.phase} subject must match project_id")
        if references[0].subject_id != funding_subject:
            raise AccountingInvariantError("FUNDING_STATE subject must match funding subject")
        object.__setattr__(self, "cycle_id", cycle_id)
        object.__setattr__(self, "household_or_funding_subject", funding_subject)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "references", references)

    @property
    def complete(self) -> bool:
        return len(self.references) == len(PHASE_CONTRACTS_V3)

    @property
    def status(self) -> str:
        return "TRACE_COMPLETE" if self.complete else "TRACE_PARTIAL"

    @property
    def missing_phases(self) -> tuple[str, ...]:
        return tuple(phase for phase, _, _ in PHASE_CONTRACTS_V3[len(self.references) :])

    def reference(self, phase: str) -> CycleReferenceV3:
        normalized = phase.upper().strip()
        for ref in self.references:
            if ref.phase == normalized:
                return ref
        raise AccountingInvariantError(f"trace does not contain phase {normalized}")

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
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


@dataclass(frozen=True)
class CycleArtifactReviewV3:
    status: str
    blockers: tuple[str, ...]
    trace_digest: str
    profit_recognition: str = "NOT_PERFORMED"
    accounting_entry_allowed: bool = False

    @property
    def verified(self) -> bool:
        return self.status == "CAUSAL_GRAPH_VERIFIED"


def verify_complete_trace_artifacts_v3(
    trace: EconomicCycleTraceV3,
    *,
    authorization: CapitalAuthorizationV2,
    funding_receipt: Mapping[str, Any],
    revenue_receipt: Mapping[str, Any],
    project_evidence_digest: str,
) -> CycleArtifactReviewV3:
    """Verify cross-object arrows; does not recognize revenue or execute transactions."""

    blockers: set[str] = set()
    if not trace.complete:
        blockers.add("TRACE_NOT_COMPLETE")
        return CycleArtifactReviewV3(
            status="CAUSAL_GRAPH_BLOCKED",
            blockers=tuple(sorted(blockers)),
            trace_digest=trace.digest,
        )

    expected_project_evidence = _hex64(project_evidence_digest, "project_evidence_digest")
    funding = verify_settlement_receipt_v2_integrity(funding_receipt)
    revenue = verify_settlement_receipt_v2_integrity(revenue_receipt)
    funding_review = verify_funding_receipt_against_authorization_v2(
        funding, authorization
    )
    revenue_review = verify_revenue_receipt_lineage_v2(
        revenue,
        authorization,
        expected_project_evidence_digest=expected_project_evidence,
    )
    blockers.update(funding_review.blockers)
    blockers.update(revenue_review.blockers)

    screening_ref = trace.reference("PROJECT_SCREENING")
    authorization_ref = trace.reference("CAPITAL_AUTHORIZATION")
    funding_ref = trace.reference("FUNDING_SETTLEMENT")
    evidence_ref = trace.reference("PROJECT_EVIDENCE")
    revenue_ref = trace.reference("REVENUE_SETTLEMENT")

    if screening_ref.digest != authorization.screening_digest:
        blockers.add("SCREENING_AUTHORIZATION_LINK_MISMATCH")
    if authorization_ref.digest != authorization.digest:
        blockers.add("AUTHORIZATION_REFERENCE_MISMATCH")
    if funding_ref.digest != funding["receipt_digest"]:
        blockers.add("FUNDING_RECEIPT_REFERENCE_MISMATCH")
    if evidence_ref.digest != expected_project_evidence:
        blockers.add("PROJECT_EVIDENCE_REFERENCE_MISMATCH")
    if revenue_ref.digest != revenue["receipt_digest"]:
        blockers.add("REVENUE_RECEIPT_REFERENCE_MISMATCH")

    funding_finality = _time_text(funding["finality_time"], "funding.finality_time")
    revenue_finality = _time_text(revenue["finality_time"], "revenue.finality_time")
    if authorization_ref.observed_at != authorization.decided_at:
        blockers.add("AUTHORIZATION_TIME_MISMATCH")
    if funding_ref.observed_at != funding_finality:
        blockers.add("FUNDING_FINALITY_TIME_MISMATCH")
    if revenue_ref.observed_at != revenue_finality:
        blockers.add("REVENUE_FINALITY_TIME_MISMATCH")

    funding_causal = funding["causal_binding"]
    revenue_causal = revenue["causal_binding"]
    if funding_causal["project_id"] != trace.project_id:
        blockers.add("FUNDING_PROJECT_MISMATCH")
    if revenue_causal["project_id"] != trace.project_id:
        blockers.add("REVENUE_PROJECT_MISMATCH")
    if funding_causal["capital_authorization_digest"] != authorization.digest:
        blockers.add("FUNDING_AUTHORIZATION_LINK_MISMATCH")
    if revenue_causal["capital_authorization_digest"] != authorization.digest:
        blockers.add("REVENUE_AUTHORIZATION_LINK_MISMATCH")
    if revenue_causal["project_evidence_digest"] != expected_project_evidence:
        blockers.add("REVENUE_EVIDENCE_LINK_MISMATCH")

    return CycleArtifactReviewV3(
        status="CAUSAL_GRAPH_BLOCKED" if blockers else "CAUSAL_GRAPH_VERIFIED",
        blockers=tuple(sorted(blockers)),
        trace_digest=trace.digest,
        profit_recognition="NOT_PERFORMED",
        accounting_entry_allowed=False,
    )


def make_reference_v3(
    phase: str, *, digest: str, subject_id: str, observed_at: datetime
) -> CycleReferenceV3:
    normalized = phase.upper().strip()
    if normalized not in INDEX:
        raise AccountingInvariantError(f"unsupported cycle phase: {normalized}")
    return CycleReferenceV3(
        phase=normalized,
        schema_id=SCHEMAS[normalized],
        digest=digest,
        source_repository=SOURCES[normalized],
        subject_id=subject_id,
        observed_at=observed_at,
    )


def build_trace_v3(
    cycle_id: str,
    household_or_funding_subject: str,
    project_id: str,
    references: Iterable[CycleReferenceV3],
) -> EconomicCycleTraceV3:
    return EconomicCycleTraceV3(
        cycle_id=cycle_id,
        household_or_funding_subject=household_or_funding_subject,
        project_id=project_id,
        references=tuple(references),
    )
