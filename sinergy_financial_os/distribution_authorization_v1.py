from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .distribution_plan_v1 import DistributionPlanV1
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "distribution.authorization/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
DECISIONS = frozenset({"APPROVED", "REJECTED"})
AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})
USAGE_POLICY = "SINGLE_EXACT_BATCH"


class DistributionAuthorizationV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionAuthorizationV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionAuthorizationV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionAuthorizationV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionAuthorizationV1:
    authorization_id: str
    decision: str
    decision_authority: str
    distribution_plan_digest: str
    distribution_capacity_replay_digest: str
    liquidity_replay_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiary_set_digest: str
    approved_total_amount: Decimal
    requirement_registry_digest: str
    approver_policy_digest: str
    decision_evidence_digest: str
    decided_at: datetime
    expires_at: datetime
    usage_policy: str = USAGE_POLICY
    notes_digest: str | None = None
    execution_authority: str = "SEPARATE_METAPAY_BATCH_HANDOFF"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        decision = _text(self.decision, "decision").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        if decision not in DECISIONS:
            raise DistributionAuthorizationV1Error("unsupported distribution decision")
        if authority not in AUTHORITIES:
            raise DistributionAuthorizationV1Error("distribution authorization requires human committee or multisig governance")
        if self.usage_policy != USAGE_POLICY:
            raise DistributionAuthorizationV1Error("v1 supports only one exact batch")
        if self.execution_authority != "SEPARATE_METAPAY_BATCH_HANDOFF":
            raise DistributionAuthorizationV1Error("distribution authorization cannot execute payments")
        if self.ai_authority != "NONE":
            raise DistributionAuthorizationV1Error("AI cannot authorize distributions")
        amount = finite_decimal(self.approved_total_amount, "approved_total_amount")
        if amount < ZERO:
            raise DistributionAuthorizationV1Error("approved_total_amount must be non-negative")
        if decision == "APPROVED" and amount <= ZERO:
            raise DistributionAuthorizationV1Error("APPROVED distribution requires positive amount")
        if decision == "REJECTED" and amount != ZERO:
            raise DistributionAuthorizationV1Error("REJECTED distribution must approve zero amount")
        decided = _utc(self.decided_at, "decided_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= decided:
            raise DistributionAuthorizationV1Error("expires_at must be later than decided_at")
        object.__setattr__(self, "authorization_id", _text(self.authorization_id, "authorization_id"))
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        object.__setattr__(self, "approved_total_amount", amount)
        for name in (
            "distribution_plan_digest",
            "distribution_capacity_replay_digest",
            "liquidity_replay_digest",
            "beneficiary_set_digest",
            "requirement_registry_digest",
            "approver_policy_digest",
            "decision_evidence_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if self.notes_digest is not None:
            object.__setattr__(self, "notes_digest", _hex64(self.notes_digest, "notes_digest", nullable=True))
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "expires_at", expires)

    def is_valid_at(self, now: datetime) -> bool:
        current = _utc(now, "now")
        return self.decision == "APPROVED" and self.decided_at <= current < self.expires_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "decision": self.decision,
            "decision_authority": self.decision_authority,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_capacity_replay_digest": self.distribution_capacity_replay_digest,
            "liquidity_replay_digest": self.liquidity_replay_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "approved_total_amount": canonical_decimal_text(self.approved_total_amount),
            "requirement_registry_digest": self.requirement_registry_digest,
            "approver_policy_digest": self.approver_policy_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "usage_policy": self.usage_policy,
            "notes_digest": self.notes_digest,
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_authorization_v1(
    *,
    authorization_id: str,
    decision: str,
    decision_authority: str,
    distribution_plan: DistributionPlanV1,
    distribution_capacity_replay: DistributionCapacityReplayV1,
    requirement_registry_digest: str,
    approver_policy_digest: str,
    decision_evidence_digest: str,
    decided_at: datetime,
    expires_at: datetime,
    notes_digest: str | None = None,
) -> DistributionAuthorizationV1:
    normalized_decision = _text(decision, "decision").upper()
    if distribution_plan.distribution_capacity_replay_digest != distribution_capacity_replay.digest:
        raise DistributionAuthorizationV1Error("DistributionPlan / capacity replay mismatch")
    if distribution_plan.affected_period_id != distribution_capacity_replay.affected_period_id:
        raise DistributionAuthorizationV1Error("DistributionPlan affected period mismatch")
    if distribution_capacity_replay.status != "CAPACITY_AVAILABLE" and normalized_decision == "APPROVED":
        raise DistributionAuthorizationV1Error("cannot approve distribution without CAPACITY_AVAILABLE")
    if distribution_plan.total_amount > distribution_capacity_replay.final_distribution_capacity:
        raise DistributionAuthorizationV1Error("DistributionPlan exceeds current capacity")
    decided = _utc(decided_at, "decided_at")
    if decided < distribution_plan.generated_at or decided < distribution_capacity_replay.generated_at:
        raise DistributionAuthorizationV1Error("distribution authorization cannot predate plan/capacity")
    amount = distribution_plan.total_amount if normalized_decision == "APPROVED" else ZERO
    return DistributionAuthorizationV1(
        authorization_id=authorization_id,
        decision=normalized_decision,
        decision_authority=decision_authority,
        distribution_plan_digest=distribution_plan.digest,
        distribution_capacity_replay_digest=distribution_capacity_replay.digest,
        liquidity_replay_digest=distribution_plan.liquidity_replay_digest,
        affected_period_id=distribution_plan.affected_period_id,
        distribution_currency=distribution_plan.distribution_currency,
        source_account_id=distribution_plan.source_account_id,
        beneficiary_set_digest=distribution_plan.beneficiary_set_digest,
        approved_total_amount=amount,
        requirement_registry_digest=requirement_registry_digest,
        approver_policy_digest=approver_policy_digest,
        decision_evidence_digest=decision_evidence_digest,
        decided_at=decided,
        expires_at=expires_at,
        notes_digest=notes_digest,
    )


def verify_distribution_authorization_context_v1(
    authorization: DistributionAuthorizationV1,
    *,
    current_plan: DistributionPlanV1,
    current_capacity_replay: DistributionCapacityReplayV1,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    if authorization.decision != "APPROVED":
        blockers.add("NOT_APPROVED")
    if authorization.distribution_plan_digest != current_plan.digest:
        blockers.add("STALE_DISTRIBUTION_PLAN")
    if authorization.distribution_capacity_replay_digest != current_capacity_replay.digest:
        blockers.add("STALE_DISTRIBUTION_CAPACITY")
    if current_plan.distribution_capacity_replay_digest != current_capacity_replay.digest:
        blockers.add("PLAN_CAPACITY_MISMATCH")
    if current_capacity_replay.status != "CAPACITY_AVAILABLE":
        blockers.add("CAPACITY_NO_LONGER_AVAILABLE")
    if current_plan.total_amount > current_capacity_replay.final_distribution_capacity:
        blockers.add("PLAN_EXCEEDS_CURRENT_CAPACITY")
    if authorization.approved_total_amount != current_plan.total_amount:
        blockers.add("AUTHORIZED_AMOUNT_PLAN_MISMATCH")
    if authorization.beneficiary_set_digest != current_plan.beneficiary_set_digest:
        blockers.add("BENEFICIARY_SET_MISMATCH")
    if authorization.source_account_id != current_plan.source_account_id:
        blockers.add("SOURCE_ACCOUNT_MISMATCH")
    if authorization.distribution_currency != current_plan.distribution_currency:
        blockers.add("DISTRIBUTION_CURRENCY_MISMATCH")
    if authorization.requirement_registry_digest != _hex64(current_requirement_registry_digest, "current_requirement_registry_digest"):
        blockers.add("STALE_REQUIREMENT_REGISTRY")
    if authorization.approver_policy_digest != _hex64(current_approver_policy_digest, "current_approver_policy_digest"):
        blockers.add("STALE_APPROVER_POLICY")
    if not authorization.is_valid_at(now):
        blockers.add("AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID")
    return not blockers, tuple(sorted(blockers))
