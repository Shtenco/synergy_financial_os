from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .distribution_plan_authorization_contract_v1 import verify_distribution_authorization_bundle_v1
from .distribution_plan_v1 import DistributionPlanV1
from .liquidity_replay_v1 import LiquidityReplayV1
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "distribution.execution-ticket/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class DistributionExecutionTicketV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionExecutionTicketV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionExecutionTicketV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionExecutionTicketV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionExecutionTicketV1:
    ticket_id: str
    distribution_authorization_digest: str
    distribution_plan_digest: str
    distribution_capacity_replay_digest: str
    liquidity_replay_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiary_set_digest: str
    total_amount: Decimal
    requirement_registry_digest: str
    approver_policy_digest: str
    verified_at: datetime
    expires_at: datetime
    authority: str = "FINANCIAL_OS_EXECUTION_HANDOFF_GATE"
    payment_authority: str = "METAPAY_ONLY"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"
    usage_policy: str = "SINGLE_EXACT_BATCH"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_EXECUTION_HANDOFF_GATE":
            raise DistributionExecutionTicketV1Error("execution ticket authority must remain Financial OS")
        if self.payment_authority != "METAPAY_ONLY" or self.execution_authority != "NONE":
            raise DistributionExecutionTicketV1Error("ticket delegates payment handoff but cannot execute")
        if self.ai_authority != "NONE":
            raise DistributionExecutionTicketV1Error("AI cannot issue distribution execution tickets")
        if self.usage_policy != "SINGLE_EXACT_BATCH":
            raise DistributionExecutionTicketV1Error("v1 supports only SINGLE_EXACT_BATCH")
        object.__setattr__(self, "ticket_id", _text(self.ticket_id, "ticket_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        for name in (
            "distribution_authorization_digest",
            "distribution_plan_digest",
            "distribution_capacity_replay_digest",
            "liquidity_replay_digest",
            "beneficiary_set_digest",
            "requirement_registry_digest",
            "approver_policy_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        total = finite_decimal(self.total_amount, "total_amount")
        if total <= ZERO:
            raise DistributionExecutionTicketV1Error("execution ticket total must be positive")
        object.__setattr__(self, "total_amount", total)
        verified = _utc(self.verified_at, "verified_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= verified:
            raise DistributionExecutionTicketV1Error("ticket expires_at must be later than verified_at")
        object.__setattr__(self, "verified_at", verified)
        object.__setattr__(self, "expires_at", expires)

    def is_valid_at(self, now: datetime) -> bool:
        current = _utc(now, "now")
        return self.verified_at <= current < self.expires_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "ticket_id": self.ticket_id,
            "distribution_authorization_digest": self.distribution_authorization_digest,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_capacity_replay_digest": self.distribution_capacity_replay_digest,
            "liquidity_replay_digest": self.liquidity_replay_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "total_amount": canonical_decimal_text(self.total_amount),
            "requirement_registry_digest": self.requirement_registry_digest,
            "approver_policy_digest": self.approver_policy_digest,
            "verified_at": self.verified_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
            "usage_policy": self.usage_policy,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_execution_ticket_v1(
    *,
    ticket_id: str,
    authorization: DistributionAuthorizationV1,
    plan: DistributionPlanV1,
    capacity_replay: DistributionCapacityReplayV1,
    liquidity_replay: LiquidityReplayV1,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    verified_at: datetime,
    expires_at: datetime,
) -> DistributionExecutionTicketV1:
    verified = _utc(verified_at, "verified_at")
    valid, blockers = verify_distribution_authorization_bundle_v1(
        authorization,
        current_plan=plan,
        current_capacity_replay=capacity_replay,
        current_liquidity_replay=liquidity_replay,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=verified,
    )
    if not valid:
        raise DistributionExecutionTicketV1Error(
            "distribution authorization bundle is not handoff-ready: " + ",".join(blockers)
        )
    expires = _utc(expires_at, "expires_at")
    if expires > authorization.expires_at:
        raise DistributionExecutionTicketV1Error("execution ticket cannot outlive distribution authorization")
    if plan.total_amount != authorization.approved_total_amount:
        raise DistributionExecutionTicketV1Error("plan total / authorized total mismatch")
    return DistributionExecutionTicketV1(
        ticket_id=ticket_id,
        distribution_authorization_digest=authorization.digest,
        distribution_plan_digest=plan.digest,
        distribution_capacity_replay_digest=capacity_replay.digest,
        liquidity_replay_digest=liquidity_replay.digest,
        affected_period_id=plan.affected_period_id,
        distribution_currency=plan.distribution_currency,
        source_account_id=plan.source_account_id,
        beneficiary_set_digest=plan.beneficiary_set_digest,
        total_amount=plan.total_amount,
        requirement_registry_digest=authorization.requirement_registry_digest,
        approver_policy_digest=authorization.approver_policy_digest,
        verified_at=verified,
        expires_at=expires,
    )


def verify_distribution_execution_ticket_context_v1(
    ticket: DistributionExecutionTicketV1,
    *,
    authorization: DistributionAuthorizationV1,
    plan: DistributionPlanV1,
    capacity_replay: DistributionCapacityReplayV1,
    liquidity_replay: LiquidityReplayV1,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    current = _utc(now, "now")
    valid, auth_blockers = verify_distribution_authorization_bundle_v1(
        authorization,
        current_plan=plan,
        current_capacity_replay=capacity_replay,
        current_liquidity_replay=liquidity_replay,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=current,
    )
    blockers.update(auth_blockers)
    comparisons = (
        (ticket.distribution_authorization_digest, authorization.digest, "STALE_DISTRIBUTION_AUTHORIZATION"),
        (ticket.distribution_plan_digest, plan.digest, "STALE_DISTRIBUTION_PLAN"),
        (ticket.distribution_capacity_replay_digest, capacity_replay.digest, "STALE_DISTRIBUTION_CAPACITY"),
        (ticket.liquidity_replay_digest, liquidity_replay.digest, "STALE_LIQUIDITY_REPLAY"),
        (ticket.beneficiary_set_digest, plan.beneficiary_set_digest, "BENEFICIARY_SET_MISMATCH"),
    )
    for actual, expected, blocker in comparisons:
        if actual != expected:
            blockers.add(blocker)
    if ticket.total_amount != plan.total_amount:
        blockers.add("TOTAL_AMOUNT_MISMATCH")
    if ticket.source_account_id != plan.source_account_id:
        blockers.add("SOURCE_ACCOUNT_MISMATCH")
    if ticket.distribution_currency != plan.distribution_currency:
        blockers.add("DISTRIBUTION_CURRENCY_MISMATCH")
    if ticket.requirement_registry_digest != authorization.requirement_registry_digest:
        blockers.add("REQUIREMENT_REGISTRY_MISMATCH")
    if ticket.approver_policy_digest != authorization.approver_policy_digest:
        blockers.add("APPROVER_POLICY_MISMATCH")
    if not ticket.is_valid_at(current):
        blockers.add("EXECUTION_TICKET_EXPIRED_OR_NOT_YET_VALID")
    return valid and not blockers, tuple(sorted(blockers))
