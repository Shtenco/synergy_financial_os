from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_authorization_v3 import DistributionAuthorizationV3, verify_distribution_authorization_context_v3
from .distribution_available_capacity_v3 import DistributionAvailableCapacityV3, SCHEMA as CAPACITY_SCHEMA
from .distribution_plan_v3 import DistributionPlanV3
from .numeric import canonical_decimal_text, finite_decimal

SCHEMA = "distribution.execution-ticket/v3"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
HANDOFF_POLICY = "FEE_AWARE_AVAILABLE_CAPACITY_V3_EXACT_BATCH"


class DistributionExecutionTicketV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionExecutionTicketV3Error(f"{name} is required")
    return value.strip()


def _hex64(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if len(value) != 64 or any(ch not in HEX for ch in value):
        raise DistributionExecutionTicketV3Error(f"{name} must be hex64")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionExecutionTicketV3Error(f"{name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionExecutionTicketV3:
    ticket_id: str
    distribution_authorization_digest: str
    distribution_plan_digest: str
    distribution_available_capacity_schema: str
    distribution_available_capacity_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiary_set_digest: str
    principal_total: Decimal
    external_fee_budget: Decimal
    total_authorized_outflow_ceiling: Decimal
    requirement_registry_digest: str
    approver_policy_digest: str
    verified_at: datetime
    expires_at: datetime
    handoff_policy: str = HANDOFF_POLICY
    authority: str = "FINANCIAL_OS_EXECUTION_HANDOFF_GATE_V3"
    payment_authority: str = "METAPAY_ONLY"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"
    usage_policy: str = "SINGLE_EXACT_BATCH"
    fee_policy: str = "PAYER_BORNE_SEPARATE_FROM_PRINCIPAL_UP_TO_BUDGET"

    def __post_init__(self) -> None:
        if self.distribution_available_capacity_schema != CAPACITY_SCHEMA:
            raise DistributionExecutionTicketV3Error("v3 ticket requires distribution.available-capacity/v3")
        if self.handoff_policy != HANDOFF_POLICY:
            raise DistributionExecutionTicketV3Error("unsupported v3 handoff policy")
        if self.authority != "FINANCIAL_OS_EXECUTION_HANDOFF_GATE_V3":
            raise DistributionExecutionTicketV3Error("ticket authority mismatch")
        if self.payment_authority != "METAPAY_ONLY" or self.execution_authority != "NONE" or self.ai_authority != "NONE":
            raise DistributionExecutionTicketV3Error("ticket can hand off to MetaPay but cannot execute")
        if self.usage_policy != "SINGLE_EXACT_BATCH" or self.fee_policy != "PAYER_BORNE_SEPARATE_FROM_PRINCIPAL_UP_TO_BUDGET":
            raise DistributionExecutionTicketV3Error("unsupported usage/fee policy")
        object.__setattr__(self, "ticket_id", _text(self.ticket_id, "ticket_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        for name in (
            "distribution_authorization_digest",
            "distribution_plan_digest",
            "distribution_available_capacity_digest",
            "beneficiary_set_digest",
            "requirement_registry_digest",
            "approver_policy_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        principal = finite_decimal(self.principal_total, "principal_total")
        fee = finite_decimal(self.external_fee_budget, "external_fee_budget")
        ceiling = finite_decimal(self.total_authorized_outflow_ceiling, "total_authorized_outflow_ceiling")
        if principal <= ZERO or fee < ZERO or ceiling != principal + fee:
            raise DistributionExecutionTicketV3Error("ticket ceiling must equal positive principal + non-negative fee budget")
        object.__setattr__(self, "principal_total", principal)
        object.__setattr__(self, "external_fee_budget", fee)
        object.__setattr__(self, "total_authorized_outflow_ceiling", ceiling)
        verified = _utc(self.verified_at, "verified_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= verified:
            raise DistributionExecutionTicketV3Error("ticket expires_at must be after verified_at")
        object.__setattr__(self, "verified_at", verified)
        object.__setattr__(self, "expires_at", expires)

    def is_valid_at(self, now: datetime) -> bool:
        current = _utc(now, "now")
        return self.verified_at <= current < self.expires_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "ticket_id": self.ticket_id,
            "distribution_authorization_digest": self.distribution_authorization_digest,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_available_capacity_schema": self.distribution_available_capacity_schema,
            "distribution_available_capacity_digest": self.distribution_available_capacity_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "principal_total": canonical_decimal_text(self.principal_total),
            "external_fee_budget": canonical_decimal_text(self.external_fee_budget),
            "total_authorized_outflow_ceiling": canonical_decimal_text(self.total_authorized_outflow_ceiling),
            "requirement_registry_digest": self.requirement_registry_digest,
            "approver_policy_digest": self.approver_policy_digest,
            "verified_at": self.verified_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "handoff_policy": self.handoff_policy,
            "authority": self.authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
            "usage_policy": self.usage_policy,
            "fee_policy": self.fee_policy,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_execution_ticket_v3(
    *,
    ticket_id: str,
    authorization: DistributionAuthorizationV3,
    plan: DistributionPlanV3,
    available_capacity: DistributionAvailableCapacityV3,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    verified_at: datetime,
    expires_at: datetime,
) -> DistributionExecutionTicketV3:
    if not isinstance(authorization, DistributionAuthorizationV3) or not isinstance(plan, DistributionPlanV3) or not isinstance(available_capacity, DistributionAvailableCapacityV3):
        raise DistributionExecutionTicketV3Error("v3 ticket requires Authorization v3, Plan v3 and AvailableCapacity v3")
    verified = _utc(verified_at, "verified_at")
    valid, blockers = verify_distribution_authorization_context_v3(
        authorization,
        current_plan=plan,
        current_available_capacity=available_capacity,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=verified,
    )
    if not valid:
        raise DistributionExecutionTicketV3Error("distribution v3 bundle not handoff-ready: " + ",".join(blockers))
    expires = _utc(expires_at, "expires_at")
    if expires > authorization.expires_at:
        raise DistributionExecutionTicketV3Error("execution ticket cannot outlive authorization")
    return DistributionExecutionTicketV3(
        ticket_id=ticket_id,
        distribution_authorization_digest=authorization.digest,
        distribution_plan_digest=plan.digest,
        distribution_available_capacity_schema=CAPACITY_SCHEMA,
        distribution_available_capacity_digest=available_capacity.digest,
        affected_period_id=plan.affected_period_id,
        distribution_currency=plan.distribution_currency,
        source_account_id=plan.source_account_id,
        beneficiary_set_digest=plan.beneficiary_set_digest,
        principal_total=plan.principal_total,
        external_fee_budget=plan.external_fee_budget,
        total_authorized_outflow_ceiling=plan.total_authorized_outflow_ceiling,
        requirement_registry_digest=authorization.requirement_registry_digest,
        approver_policy_digest=authorization.approver_policy_digest,
        verified_at=verified,
        expires_at=expires,
    )


def verify_distribution_execution_ticket_context_v3(
    ticket: DistributionExecutionTicketV3,
    *,
    authorization: DistributionAuthorizationV3,
    plan: DistributionPlanV3,
    available_capacity: DistributionAvailableCapacityV3,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    if not isinstance(authorization, DistributionAuthorizationV3) or not isinstance(plan, DistributionPlanV3) or not isinstance(available_capacity, DistributionAvailableCapacityV3):
        blockers.add("V3_GENERATION_MISMATCH")
        return False, tuple(sorted(blockers))
    valid, auth_blockers = verify_distribution_authorization_context_v3(
        authorization,
        current_plan=plan,
        current_available_capacity=available_capacity,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=now,
    )
    blockers.update(auth_blockers)
    checks = (
        (ticket.distribution_authorization_digest, authorization.digest, "STALE_AUTHORIZATION"),
        (ticket.distribution_plan_digest, plan.digest, "STALE_PLAN"),
        (ticket.distribution_available_capacity_digest, available_capacity.digest, "STALE_AVAILABLE_CAPACITY"),
        (ticket.beneficiary_set_digest, plan.beneficiary_set_digest, "BENEFICIARY_SET_MISMATCH"),
    )
    for actual, expected, blocker in checks:
        if actual != expected:
            blockers.add(blocker)
    if ticket.distribution_available_capacity_schema != CAPACITY_SCHEMA:
        blockers.add("AVAILABLE_CAPACITY_SCHEMA_MISMATCH")
    if ticket.principal_total != plan.principal_total:
        blockers.add("PRINCIPAL_MISMATCH")
    if ticket.external_fee_budget != plan.external_fee_budget:
        blockers.add("FEE_BUDGET_MISMATCH")
    if ticket.total_authorized_outflow_ceiling != plan.total_authorized_outflow_ceiling:
        blockers.add("OUTFLOW_CEILING_MISMATCH")
    if not ticket.is_valid_at(now):
        blockers.add("EXECUTION_TICKET_EXPIRED_OR_NOT_YET_VALID")
    return valid and not blockers, tuple(sorted(blockers))
