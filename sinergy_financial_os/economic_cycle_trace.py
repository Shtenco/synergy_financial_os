from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from .core import AccountingInvariantError


SCHEMA = "economic.cycle-trace/v1"
HEX = frozenset("0123456789abcdef")

PHASE_CONTRACTS: tuple[tuple[str, str, str], ...] = (
    ("FUNDING_STATE", "maturity.snapshot/v1", "Shtenco/synergy_matrix_sota"),
    ("PROJECT_PROPOSAL", "project.proposal/v2", "Shtenco/synergy_eurasian"),
    ("PROJECT_SCREENING", "project.screening/v1", "Shtenco/synergy_financial_os"),
    ("CAPITAL_AUTHORIZATION", "capital.authorization/v1", "Shtenco/synergy_financial_os"),
    ("FUNDING_SETTLEMENT", "settlement.receipt/v1", "Shtenco/synergy_pay_system"),
    ("PROJECT_EVIDENCE", "project.evidence/v1", "Shtenco/synergy_eurasian"),
    ("REVENUE_SETTLEMENT", "settlement.receipt/v1", "Shtenco/synergy_pay_system"),
    ("ACCOUNTING_SNAPSHOT", "financial.snapshot/v2", "Shtenco/synergy_financial_os"),
    ("TRUST_COMMITMENT", "commitment.envelope/v2", "Shtenco/synergy_ai_blockchain"),
)
PHASE_INDEX = {phase: index for index, (phase, _, _) in enumerate(PHASE_CONTRACTS)}
PHASE_SCHEMA = {phase: schema for phase, schema, _ in PHASE_CONTRACTS}
PHASE_SOURCE = {phase: source for phase, _, source in PHASE_CONTRACTS}


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise AccountingInvariantError(f"{field_name} must be text")
    result = value.strip()
    if not result:
        raise AccountingInvariantError(f"{field_name} is required")
    return result


def _hex64(value: str, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(char not in HEX for char in result):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return result


def _time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


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
class CycleReference:
    phase: str
    schema_id: str
    digest: str
    source_repository: str
    subject_id: str
    observed_at: datetime

    def __post_init__(self) -> None:
        phase = _text(self.phase, "phase").upper()
        if phase not in PHASE_INDEX:
            raise AccountingInvariantError(f"unsupported economic-cycle phase: {phase}")
        schema_id = _text(self.schema_id, "schema_id")
        source = _text(self.source_repository, "source_repository")
        subject = _text(self.subject_id, "subject_id")
        if schema_id != PHASE_SCHEMA[phase]:
            raise AccountingInvariantError(
                f"{phase} requires schema {PHASE_SCHEMA[phase]}, got {schema_id}"
            )
        if source != PHASE_SOURCE[phase]:
            raise AccountingInvariantError(
                f"{phase} requires source {PHASE_SOURCE[phase]}, got {source}"
            )
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "schema_id", schema_id)
        object.__setattr__(self, "digest", _hex64(self.digest, "digest"))
        object.__setattr__(self, "source_repository", source)
        object.__setattr__(self, "subject_id", subject)
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
class EconomicCycleTrace:
    cycle_id: str
    household_or_funding_subject: str
    project_id: str
    references: tuple[CycleReference, ...]
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
            raise AccountingInvariantError("economic cycle trace is provenance only")
        if self.profit_recognition != "NOT_PERFORMED":
            raise AccountingInvariantError(
                "economic cycle trace cannot recognize consolidated profit"
            )
        if self.execution_authority != "NONE":
            raise AccountingInvariantError("economic cycle trace cannot execute financial actions")
        references = tuple(self.references)
        if not references:
            raise AccountingInvariantError("economic cycle trace requires at least one reference")
        if any(not isinstance(item, CycleReference) for item in references):
            raise AccountingInvariantError("references must contain CycleReference values")

        phases = [item.phase for item in references]
        if len(phases) != len(set(phases)):
            raise AccountingInvariantError("economic cycle phases must be unique")
        expected_prefix = [phase for phase, _, _ in PHASE_CONTRACTS[: len(phases)]]
        if phases != expected_prefix:
            raise AccountingInvariantError(
                "economic cycle references must form the canonical causal prefix without skipped phases"
            )
        times = [item.observed_at for item in references]
        if times != sorted(times):
            raise AccountingInvariantError(
                "economic cycle observed_at values must be non-decreasing"
            )

        for item in references:
            if item.phase in {
                "PROJECT_PROPOSAL",
                "PROJECT_SCREENING",
                "CAPITAL_AUTHORIZATION",
                "PROJECT_EVIDENCE",
            } and item.subject_id != project_id:
                raise AccountingInvariantError(
                    f"{item.phase} subject_id must equal trace project_id"
                )
        if references[0].subject_id != funding_subject:
            raise AccountingInvariantError(
                "FUNDING_STATE subject_id must equal household_or_funding_subject"
            )

        object.__setattr__(self, "cycle_id", cycle_id)
        object.__setattr__(self, "household_or_funding_subject", funding_subject)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "references", references)

    @property
    def complete(self) -> bool:
        return len(self.references) == len(PHASE_CONTRACTS)

    @property
    def status(self) -> str:
        return "TRACE_COMPLETE" if self.complete else "TRACE_PARTIAL"

    @property
    def missing_phases(self) -> tuple[str, ...]:
        return tuple(phase for phase, _, _ in PHASE_CONTRACTS[len(self.references) :])

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "cycle_id": self.cycle_id,
            "household_or_funding_subject": self.household_or_funding_subject,
            "project_id": self.project_id,
            "status": self.status,
            "complete": self.complete,
            "missing_phases": list(self.missing_phases),
            "references": [item.to_dict() for item in self.references],
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


def make_reference(
    phase: str,
    *,
    digest: str,
    subject_id: str,
    observed_at: datetime,
) -> CycleReference:
    normalized = phase.upper().strip()
    if normalized not in PHASE_INDEX:
        raise AccountingInvariantError(f"unsupported economic-cycle phase: {normalized}")
    return CycleReference(
        phase=normalized,
        schema_id=PHASE_SCHEMA[normalized],
        digest=digest,
        source_repository=PHASE_SOURCE[normalized],
        subject_id=subject_id,
        observed_at=observed_at,
    )


def build_trace(
    cycle_id: str,
    household_or_funding_subject: str,
    project_id: str,
    references: Iterable[CycleReference],
) -> EconomicCycleTrace:
    return EconomicCycleTrace(
        cycle_id=cycle_id,
        household_or_funding_subject=household_or_funding_subject,
        project_id=project_id,
        references=tuple(references),
    )
