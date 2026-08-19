from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import (
    AccountingCloseV2,
    LedgerInclusionProofV2,
    verify_ledger_inclusion_proof_v2,
)
from .accounting_period_chain_v1 import (
    AccountingPeriodChainProofV1,
    verify_accounting_period_chain_proof_v1,
)
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2


SCHEMA = "accounting.prior-period-correction-authorization/v1"
CORRECTION_SCOPE = "EXACT_ENTRY_VOID"
CURRENT_PERIOD_PNL_TREATMENT = "EXCLUDED_FROM_CURRENT_PERIOD_PNL"
REASONS = frozenset(
    {"DUPLICATE_ENTRY", "ERRONEOUS_RECOGNITION", "MISCLASSIFIED_ENTRY", "DATA_ERROR"}
)
AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})
HEX = frozenset("0123456789abcdef")


class PriorPeriodCorrectionV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PriorPeriodCorrectionV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise PriorPeriodCorrectionV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PriorPeriodCorrectionV1Error(f"{field_name} must be timezone-aware datetime")
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
class PriorPeriodCorrectionAuthorizationV1:
    authorization_id: str
    affected_period_id: str
    target_period_id: str
    reason: str
    original_period_close_digest: str
    original_accounting_close_digest: str
    original_ledger_event_digest: str
    original_reporting_entry_digest: str
    period_chain_proof_digest: str
    correction_evidence_digest: str
    decision_evidence_digest: str
    accounting_policy_digest: str
    requirement_registry_digest: str
    decision_authority: str
    decided_at: datetime
    effective_at: datetime
    correction_scope: str = CORRECTION_SCOPE
    current_period_pnl_treatment: str = CURRENT_PERIOD_PNL_TREATMENT
    posting_authority: str = "SEPARATE_CORRECTION_POSTING"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        reason = _text(self.reason, "reason").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        if reason not in REASONS:
            raise PriorPeriodCorrectionV1Error(f"unsupported correction reason: {reason}")
        if authority not in AUTHORITIES:
            raise PriorPeriodCorrectionV1Error(
                "prior-period correction requires human committee or multisig authority"
            )
        if self.correction_scope != CORRECTION_SCOPE:
            raise PriorPeriodCorrectionV1Error("v1 supports EXACT_ENTRY_VOID only")
        if self.current_period_pnl_treatment != CURRENT_PERIOD_PNL_TREATMENT:
            raise PriorPeriodCorrectionV1Error(
                "v1 prior-period correction must remain excluded from current-period P&L"
            )
        if self.posting_authority != "SEPARATE_CORRECTION_POSTING" or self.ai_authority != "NONE":
            raise PriorPeriodCorrectionV1Error(
                "correction authorization cannot post entries and AI cannot authorize"
            )
        decided = _utc(self.decided_at, "decided_at")
        effective = _utc(self.effective_at, "effective_at")
        if effective < decided:
            raise PriorPeriodCorrectionV1Error("effective_at cannot precede decision")
        for field_name in (
            "authorization_id",
            "affected_period_id",
            "target_period_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in (
            "original_period_close_digest",
            "original_accounting_close_digest",
            "original_ledger_event_digest",
            "original_reporting_entry_digest",
            "period_chain_proof_digest",
            "correction_evidence_digest",
            "decision_evidence_digest",
            "accounting_policy_digest",
            "requirement_registry_digest",
        ):
            object.__setattr__(self, field_name, _hex64(getattr(self, field_name), field_name))
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "effective_at", effective)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "affected_period_id": self.affected_period_id,
            "target_period_id": self.target_period_id,
            "reason": self.reason,
            "correction_scope": self.correction_scope,
            "current_period_pnl_treatment": self.current_period_pnl_treatment,
            "original_period_close_digest": self.original_period_close_digest,
            "original_accounting_close_digest": self.original_accounting_close_digest,
            "original_ledger_event_digest": self.original_ledger_event_digest,
            "original_reporting_entry_digest": self.original_reporting_entry_digest,
            "period_chain_proof_digest": self.period_chain_proof_digest,
            "correction_evidence_digest": self.correction_evidence_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "accounting_policy_digest": self.accounting_policy_digest,
            "requirement_registry_digest": self.requirement_registry_digest,
            "decision_authority": self.decision_authority,
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "effective_at": self.effective_at.isoformat().replace("+00:00", "Z"),
            "posting_authority": self.posting_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def verify_prior_period_correction_context_v1(
    authorization: PriorPeriodCorrectionAuthorizationV1,
    target_period: AccountingPeriodV1,
    period_chain_proof: AccountingPeriodChainProofV1,
    period_close_chain: Sequence[AccountingPeriodCloseV1],
    original_accounting_close: AccountingCloseV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
) -> bool:
    if authorization.target_period_id != target_period.period_id:
        raise PriorPeriodCorrectionV1Error("correction target period mismatch")
    if authorization.period_chain_proof_digest != period_chain_proof.digest:
        raise PriorPeriodCorrectionV1Error("period-chain proof digest mismatch")
    verify_accounting_period_chain_proof_v1(
        period_chain_proof,
        period_close_chain,
        target_period,
    )
    if period_chain_proof.generated_at > authorization.decided_at:
        raise PriorPeriodCorrectionV1Error(
            "authorization cannot rely on a period-chain proof generated after the decision"
        )
    if not period_close_chain:
        raise PriorPeriodCorrectionV1Error("period close chain cannot be empty")
    original_period_close = period_close_chain[0]
    if authorization.affected_period_id != original_period_close.period_id:
        raise PriorPeriodCorrectionV1Error("affected period id mismatch")
    if authorization.original_period_close_digest != original_period_close.digest:
        raise PriorPeriodCorrectionV1Error("original PeriodClose digest mismatch")
    if original_period_close.accounting_close_digest != original_accounting_close.digest:
        raise PriorPeriodCorrectionV1Error("original PeriodClose/AccountingClose mismatch")
    if authorization.original_accounting_close_digest != original_accounting_close.digest:
        raise PriorPeriodCorrectionV1Error("authorization AccountingClose mismatch")
    if authorization.decided_at <= original_period_close.closed_at:
        raise PriorPeriodCorrectionV1Error(
            "prior-period correction must be authorized after original period close"
        )
    if not target_period.contains(authorization.effective_at):
        raise PriorPeriodCorrectionV1Error("correction effective_at must lie in target period")
    if authorization.accounting_policy_digest != target_period.accounting_policy_digest:
        raise PriorPeriodCorrectionV1Error("target-period accounting policy mismatch")
    if authorization.requirement_registry_digest != target_period.requirement_registry_digest:
        raise PriorPeriodCorrectionV1Error("target-period requirement registry mismatch")

    event = verify_ledger_event_v2(original_ledger_event)
    if authorization.original_ledger_event_digest != ledger_event_v2_digest(event):
        raise PriorPeriodCorrectionV1Error("original LedgerEvent digest mismatch")
    if authorization.original_reporting_entry_digest != event.get("reporting_entry_digest"):
        raise PriorPeriodCorrectionV1Error("original ReportingEntry digest mismatch")
    verify_ledger_inclusion_proof_v2(
        event,
        original_inclusion_proof,
        original_accounting_close,
    )
    return True
