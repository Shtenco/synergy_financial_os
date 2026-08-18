from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .core import AccountingInvariantError


SCHEMA = "capital.authorization/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
ALLOWED_DECISIONS = frozenset({"APPROVED", "REJECTED"})
ALLOWED_DECISION_AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})


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


def _decimal(value: Decimal | int | str, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise AccountingInvariantError(f"{field_name} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AccountingInvariantError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise AccountingInvariantError(f"{field_name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _time(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccountingInvariantError(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CapitalAuthorization:
    authorization_id: str
    project_id: str
    decision: str
    decision_authority: str
    funding_asset: str
    approved_amount: Decimal
    screening_digest: str
    financial_snapshot_digest: str
    valuation_policy_digest: str
    requirement_registry_digest: str
    decision_evidence_digest: str
    decided_at: datetime
    expires_at: datetime
    financial_snapshot_sequence: int
    notes_digest: str | None = None
    execution_authority: str = "SEPARATE_METAPAY_HANDOFF"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        authorization_id = _text(self.authorization_id, "authorization_id")
        project_id = _text(self.project_id, "project_id")
        decision = _text(self.decision, "decision").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        asset = _text(self.funding_asset, "funding_asset").upper()
        if decision not in ALLOWED_DECISIONS:
            raise AccountingInvariantError(f"unsupported capital decision: {decision}")
        if authority not in ALLOWED_DECISION_AUTHORITIES:
            raise AccountingInvariantError(
                "capital authorization requires human committee or multisig governance authority"
            )
        amount = _decimal(self.approved_amount, "approved_amount")
        if amount < ZERO:
            raise AccountingInvariantError("approved_amount must be non-negative")
        if decision == "APPROVED" and amount <= ZERO:
            raise AccountingInvariantError("APPROVED authorization requires positive amount")
        if decision == "REJECTED" and amount != ZERO:
            raise AccountingInvariantError("REJECTED authorization must have zero approved_amount")
        if self.execution_authority != "SEPARATE_METAPAY_HANDOFF":
            raise AccountingInvariantError(
                "capital authorization must not embed payment execution authority"
            )
        if self.ai_authority != "NONE":
            raise AccountingInvariantError("AI cannot be capital authorization authority")
        if (
            isinstance(self.financial_snapshot_sequence, bool)
            or not isinstance(self.financial_snapshot_sequence, int)
            or self.financial_snapshot_sequence < 0
            or self.financial_snapshot_sequence > MAX_SAFE_JSON_INTEGER
        ):
            raise AccountingInvariantError(
                "financial_snapshot_sequence must be a non-negative safe integer"
            )
        decided = _time(self.decided_at, "decided_at")
        expires = _time(self.expires_at, "expires_at")
        if expires <= decided:
            raise AccountingInvariantError("expires_at must be later than decided_at")

        object.__setattr__(self, "authorization_id", authorization_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "funding_asset", asset)
        object.__setattr__(self, "approved_amount", amount)
        object.__setattr__(self, "screening_digest", _hex64(self.screening_digest, "screening_digest"))
        object.__setattr__(
            self,
            "financial_snapshot_digest",
            _hex64(self.financial_snapshot_digest, "financial_snapshot_digest"),
        )
        object.__setattr__(
            self,
            "valuation_policy_digest",
            _hex64(self.valuation_policy_digest, "valuation_policy_digest"),
        )
        object.__setattr__(
            self,
            "requirement_registry_digest",
            _hex64(self.requirement_registry_digest, "requirement_registry_digest"),
        )
        object.__setattr__(
            self,
            "decision_evidence_digest",
            _hex64(self.decision_evidence_digest, "decision_evidence_digest"),
        )
        if self.notes_digest is not None:
            object.__setattr__(self, "notes_digest", _hex64(self.notes_digest, "notes_digest"))
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "expires_at", expires)

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    def is_valid_at(self, now: datetime) -> bool:
        current = _time(now, "now")
        return self.decision == "APPROVED" and self.decided_at <= current < self.expires_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "project_id": self.project_id,
            "decision": self.decision,
            "decision_authority": self.decision_authority,
            "funding_asset": self.funding_asset,
            "approved_amount": _decimal_text(self.approved_amount),
            "screening_digest": self.screening_digest,
            "financial_snapshot_digest": self.financial_snapshot_digest,
            "financial_snapshot_sequence": self.financial_snapshot_sequence,
            "valuation_policy_digest": self.valuation_policy_digest,
            "requirement_registry_digest": self.requirement_registry_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "notes_digest": self.notes_digest,
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = _canonical_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict(include_digest=False))


def verify_authorization_context(
    authorization: CapitalAuthorization,
    *,
    current_financial_snapshot_digest: str,
    current_financial_snapshot_sequence: int,
    current_valuation_policy_digest: str,
    current_requirement_registry_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    """Optimistic-concurrency check before a separate MetaPay handoff."""

    blockers: set[str] = set()
    if authorization.decision != "APPROVED":
        blockers.add("NOT_APPROVED")
    if authorization.financial_snapshot_digest != _hex64(
        current_financial_snapshot_digest, "current_financial_snapshot_digest"
    ):
        blockers.add("STALE_FINANCIAL_SNAPSHOT")
    if authorization.financial_snapshot_sequence != current_financial_snapshot_sequence:
        blockers.add("STALE_FINANCIAL_SEQUENCE")
    if authorization.valuation_policy_digest != _hex64(
        current_valuation_policy_digest, "current_valuation_policy_digest"
    ):
        blockers.add("STALE_VALUATION_POLICY")
    if authorization.requirement_registry_digest != _hex64(
        current_requirement_registry_digest, "current_requirement_registry_digest"
    ):
        blockers.add("STALE_REQUIREMENT_REGISTRY")
    if not authorization.is_valid_at(now):
        blockers.add("AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID")
    return not blockers, tuple(sorted(blockers))
