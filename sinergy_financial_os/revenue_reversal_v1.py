from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from .accounting_close_v2 import (
    AccountingCloseV2,
    LedgerInclusionProofV2,
    verify_ledger_inclusion_proof_v2,
)
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .ledger_event_v2 import ledger_event_v2_digest, verify_ledger_event_v2
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2


SCHEMA = "revenue.reversal-authorization/v1"
REASONS = frozenset({"REFUND", "CHARGEBACK", "CANCELLATION"})
AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})
HEX = frozenset("0123456789abcdef")


class RevenueReversalV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RevenueReversalV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise RevenueReversalV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RevenueReversalV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RevenueReversalAuthorizationV1:
    authorization_id: str
    target_period_id: str
    project_id: str
    reason: str
    original_period_close_digest: str
    original_accounting_close_digest: str
    original_revenue_recognition_digest: str
    original_ledger_event_digest: str
    original_reporting_entry_digest: str
    external_evidence_digest: str
    decision_evidence_digest: str
    accounting_policy_digest: str
    decision_authority: str
    decided_at: datetime
    effective_at: datetime
    adjustment_scope: str = "FULL_ONLY"
    posting_authority: str = "SEPARATE_REVERSAL_POSTING"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        reason = _text(self.reason, "reason").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        if reason not in REASONS:
            raise RevenueReversalV1Error(f"unsupported reversal reason: {reason}")
        if authority not in AUTHORITIES:
            raise RevenueReversalV1Error("reversal requires human committee or multisig authority")
        if self.adjustment_scope != "FULL_ONLY":
            raise RevenueReversalV1Error("v1 supports full reversal only")
        if self.posting_authority != "SEPARATE_REVERSAL_POSTING" or self.ai_authority != "NONE":
            raise RevenueReversalV1Error("reversal authorization cannot post entries and AI cannot authorize")
        decided = _utc(self.decided_at, "decided_at")
        effective = _utc(self.effective_at, "effective_at")
        if effective < decided:
            raise RevenueReversalV1Error("effective_at cannot precede decision")
        object.__setattr__(self, "authorization_id", _text(self.authorization_id, "authorization_id"))
        object.__setattr__(self, "target_period_id", _text(self.target_period_id, "target_period_id"))
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "effective_at", effective)
        for name in (
            "original_period_close_digest",
            "original_accounting_close_digest",
            "original_revenue_recognition_digest",
            "original_ledger_event_digest",
            "original_reporting_entry_digest",
            "external_evidence_digest",
            "decision_evidence_digest",
            "accounting_policy_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "target_period_id": self.target_period_id,
            "project_id": self.project_id,
            "reason": self.reason,
            "adjustment_scope": self.adjustment_scope,
            "original_period_close_digest": self.original_period_close_digest,
            "original_accounting_close_digest": self.original_accounting_close_digest,
            "original_revenue_recognition_digest": self.original_revenue_recognition_digest,
            "original_ledger_event_digest": self.original_ledger_event_digest,
            "original_reporting_entry_digest": self.original_reporting_entry_digest,
            "external_evidence_digest": self.external_evidence_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "accounting_policy_digest": self.accounting_policy_digest,
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


def verify_revenue_reversal_context_v1(
    authorization: RevenueReversalAuthorizationV1,
    target_period: AccountingPeriodV1,
    original_period_close: AccountingPeriodCloseV1,
    original_accounting_close: AccountingCloseV2,
    original_recognition: RevenueRecognitionDecisionV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
) -> bool:
    if authorization.target_period_id != target_period.period_id:
        raise RevenueReversalV1Error("reversal target period mismatch")
    if target_period.opening_period_close_digest != original_period_close.digest:
        raise RevenueReversalV1Error("v1 reversal target must directly succeed original PeriodClose")
    if authorization.original_period_close_digest != original_period_close.digest:
        raise RevenueReversalV1Error("authorization original PeriodClose mismatch")
    if original_period_close.accounting_close_digest != original_accounting_close.digest:
        raise RevenueReversalV1Error("PeriodClose/AccountingClose mismatch")
    if authorization.original_accounting_close_digest != original_accounting_close.digest:
        raise RevenueReversalV1Error("authorization AccountingClose mismatch")
    if authorization.decided_at <= original_period_close.closed_at:
        raise RevenueReversalV1Error("closed-period reversal must be authorized after original period close")
    if not target_period.contains(authorization.effective_at):
        raise RevenueReversalV1Error("reversal effective_at must lie in target period")
    if authorization.accounting_policy_digest != target_period.accounting_policy_digest:
        raise RevenueReversalV1Error("target-period accounting policy mismatch")
    if original_recognition.decision != "RECOGNIZED" or not original_recognition.ledger_posting_allowed:
        raise RevenueReversalV1Error("only recognized revenue can be reversed")
    if authorization.project_id != original_recognition.project_id:
        raise RevenueReversalV1Error("project mismatch")
    if authorization.original_revenue_recognition_digest != original_recognition.digest:
        raise RevenueReversalV1Error("recognition digest mismatch")
    event = verify_ledger_event_v2(original_ledger_event)
    if event.get("event_type") != "EXTERNAL_REVENUE":
        raise RevenueReversalV1Error("original event must be EXTERNAL_REVENUE")
    if event.get("evidence_digest") != original_recognition.digest:
        raise RevenueReversalV1Error("original event evidence does not bind recognition")
    if authorization.original_ledger_event_digest != ledger_event_v2_digest(event):
        raise RevenueReversalV1Error("original LedgerEvent digest mismatch")
    if authorization.original_reporting_entry_digest != event.get("reporting_entry_digest"):
        raise RevenueReversalV1Error("original ReportingEntry digest mismatch")
    verify_ledger_inclusion_proof_v2(
        event, original_inclusion_proof, original_accounting_close
    )
    return True
