from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_available_capacity_v3 import DistributionAvailableCapacityV3, SCHEMA as CAPACITY_SCHEMA
from .distribution_plan_v3 import DistributionPlanV3, verify_distribution_plan_context_v3
from .numeric import canonical_decimal_text, finite_decimal

SCHEMA = "distribution.authorization/v3"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
DECISIONS = frozenset({"APPROVED", "REJECTED"})
AUTHORITIES = frozenset({"HUMAN_COMMITTEE", "MULTISIG_GOVERNANCE"})
HANDOFF_POLICY = "FEE_AWARE_AVAILABLE_CAPACITY_V3_EXACT_BATCH"


class DistributionAuthorizationV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionAuthorizationV3Error(f"{name} is required")
    return value.strip()


def _hex64(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if len(value) != 64 or any(ch not in HEX for ch in value):
        raise DistributionAuthorizationV3Error(f"{name} must be hex64")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionAuthorizationV3Error(f"{name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionAuthorizationV3:
    authorization_id: str
    decision: str
    decision_authority: str
    distribution_plan_digest: str
    distribution_available_capacity_schema: str
    distribution_available_capacity_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiary_set_digest: str
    approved_principal_amount: Decimal
    approved_external_fee_budget: Decimal
    approved_total_outflow_ceiling: Decimal
    requirement_registry_digest: str
    approver_policy_digest: str
    decision_evidence_digest: str
    decided_at: datetime
    expires_at: datetime
    handoff_policy: str = HANDOFF_POLICY
    execution_authority: str = "SEPARATE_METAPAY_FEE_AWARE_BATCH_HANDOFF_V3"
    payment_authority: str = "METAPAY_ONLY_AFTER_EXECUTION_TICKET_V3"
    ai_authority: str = "NONE"
    usage_policy: str = "SINGLE_EXACT_BATCH"
    fee_policy: str = "PAYER_BORNE_SEPARATE_FROM_PRINCIPAL_UP_TO_BUDGET"

    def __post_init__(self) -> None:
        decision = _text(self.decision, "decision").upper()
        authority = _text(self.decision_authority, "decision_authority").upper()
        if decision not in DECISIONS or authority not in AUTHORITIES:
            raise DistributionAuthorizationV3Error("unsupported decision/authority")
        if self.distribution_available_capacity_schema != CAPACITY_SCHEMA:
            raise DistributionAuthorizationV3Error("v3 authorization requires distribution.available-capacity/v3")
        if self.handoff_policy != HANDOFF_POLICY:
            raise DistributionAuthorizationV3Error("unsupported v3 handoff policy")
        if self.execution_authority != "SEPARATE_METAPAY_FEE_AWARE_BATCH_HANDOFF_V3":
            raise DistributionAuthorizationV3Error("authorization execution boundary mismatch")
        if self.payment_authority != "METAPAY_ONLY_AFTER_EXECUTION_TICKET_V3":
            raise DistributionAuthorizationV3Error("authorization payment boundary mismatch")
        if self.ai_authority != "NONE":
            raise DistributionAuthorizationV3Error("AI cannot authorize distributions")
        if self.usage_policy != "SINGLE_EXACT_BATCH" or self.fee_policy != "PAYER_BORNE_SEPARATE_FROM_PRINCIPAL_UP_TO_BUDGET":
            raise DistributionAuthorizationV3Error("unsupported usage/fee policy")
        principal = finite_decimal(self.approved_principal_amount, "approved_principal_amount")
        fee = finite_decimal(self.approved_external_fee_budget, "approved_external_fee_budget")
        ceiling = finite_decimal(self.approved_total_outflow_ceiling, "approved_total_outflow_ceiling")
        if min(principal, fee, ceiling) < ZERO or ceiling != principal + fee:
            raise DistributionAuthorizationV3Error("approved ceiling must equal principal + fee budget")
        if decision == "APPROVED" and principal <= ZERO:
            raise DistributionAuthorizationV3Error("APPROVED requires positive principal")
        if decision == "REJECTED" and any(value != ZERO for value in (principal, fee, ceiling)):
            raise DistributionAuthorizationV3Error("REJECTED must approve zero economics")
        decided = _utc(self.decided_at, "decided_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= decided:
            raise DistributionAuthorizationV3Error("expires_at must be after decided_at")
        object.__setattr__(self, "authorization_id", _text(self.authorization_id, "authorization_id"))
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "decision_authority", authority)
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        for name in (
            "distribution_plan_digest",
            "distribution_available_capacity_digest",
            "beneficiary_set_digest",
            "requirement_registry_digest",
            "approver_policy_digest",
            "decision_evidence_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        object.__setattr__(self, "approved_principal_amount", principal)
        object.__setattr__(self, "approved_external_fee_budget", fee)
        object.__setattr__(self, "approved_total_outflow_ceiling", ceiling)
        object.__setattr__(self, "decided_at", decided)
        object.__setattr__(self, "expires_at", expires)

    def is_valid_at(self, now: datetime) -> bool:
        current = _utc(now, "now")
        return self.decision == "APPROVED" and self.decided_at <= current < self.expires_at

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "authorization_id": self.authorization_id,
            "decision": self.decision,
            "decision_authority": self.decision_authority,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_available_capacity_schema": self.distribution_available_capacity_schema,
            "distribution_available_capacity_digest": self.distribution_available_capacity_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "approved_principal_amount": canonical_decimal_text(self.approved_principal_amount),
            "approved_external_fee_budget": canonical_decimal_text(self.approved_external_fee_budget),
            "approved_total_outflow_ceiling": canonical_decimal_text(self.approved_total_outflow_ceiling),
            "requirement_registry_digest": self.requirement_registry_digest,
            "approver_policy_digest": self.approver_policy_digest,
            "decision_evidence_digest": self.decision_evidence_digest,
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "handoff_policy": self.handoff_policy,
            "execution_authority": self.execution_authority,
            "payment_authority": self.payment_authority,
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


def build_distribution_authorization_v3(
    *,
    authorization_id: str,
    decision: str,
    decision_authority: str,
    plan: DistributionPlanV3,
    available_capacity: DistributionAvailableCapacityV3,
    requirement_registry_digest: str,
    approver_policy_digest: str,
    decision_evidence_digest: str,
    decided_at: datetime,
    expires_at: datetime,
) -> DistributionAuthorizationV3:
    if not isinstance(plan, DistributionPlanV3) or not isinstance(available_capacity, DistributionAvailableCapacityV3):
        raise DistributionAuthorizationV3Error("v3 authorization requires Plan v3 and AvailableCapacity v3")
    normalized = _text(decision, "decision").upper()
    valid, blockers = verify_distribution_plan_context_v3(plan, current_available_capacity=available_capacity)
    if normalized == "APPROVED" and not valid:
        raise DistributionAuthorizationV3Error("cannot approve stale/over-capacity v3 plan: " + ",".join(blockers))
    decided = _utc(decided_at, "decided_at")
    if decided < plan.generated_at or decided < available_capacity.generated_at:
        raise DistributionAuthorizationV3Error("authorization cannot predate plan/capacity")
    principal = plan.principal_total if normalized == "APPROVED" else ZERO
    fee = plan.external_fee_budget if normalized == "APPROVED" else ZERO
    return DistributionAuthorizationV3(
        authorization_id=authorization_id,
        decision=normalized,
        decision_authority=decision_authority,
        distribution_plan_digest=plan.digest,
        distribution_available_capacity_schema=CAPACITY_SCHEMA,
        distribution_available_capacity_digest=available_capacity.digest,
        affected_period_id=plan.affected_period_id,
        distribution_currency=plan.distribution_currency,
        source_account_id=plan.source_account_id,
        beneficiary_set_digest=plan.beneficiary_set_digest,
        approved_principal_amount=principal,
        approved_external_fee_budget=fee,
        approved_total_outflow_ceiling=principal + fee,
        requirement_registry_digest=requirement_registry_digest,
        approver_policy_digest=approver_policy_digest,
        decision_evidence_digest=decision_evidence_digest,
        decided_at=decided,
        expires_at=expires_at,
    )


def verify_distribution_authorization_context_v3(
    authorization: DistributionAuthorizationV3,
    *,
    current_plan: DistributionPlanV3,
    current_available_capacity: DistributionAvailableCapacityV3,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    if not isinstance(current_plan, DistributionPlanV3) or not isinstance(current_available_capacity, DistributionAvailableCapacityV3):
        blockers.add("V3_GENERATION_MISMATCH")
        return False, tuple(sorted(blockers))
    valid_plan, plan_blockers = verify_distribution_plan_context_v3(current_plan, current_available_capacity=current_available_capacity)
    blockers.update(plan_blockers)
    if authorization.decision != "APPROVED":
        blockers.add("NOT_APPROVED")
    if authorization.distribution_plan_digest != current_plan.digest:
        blockers.add("STALE_DISTRIBUTION_PLAN")
    if authorization.distribution_available_capacity_schema != CAPACITY_SCHEMA:
        blockers.add("AVAILABLE_CAPACITY_SCHEMA_MISMATCH")
    if authorization.distribution_available_capacity_digest != current_available_capacity.digest:
        blockers.add("STALE_DISTRIBUTION_AVAILABLE_CAPACITY")
    if authorization.beneficiary_set_digest != current_plan.beneficiary_set_digest:
        blockers.add("BENEFICIARY_SET_MISMATCH")
    if authorization.approved_principal_amount != current_plan.principal_total:
        blockers.add("AUTHORIZED_PRINCIPAL_MISMATCH")
    if authorization.approved_external_fee_budget != current_plan.external_fee_budget:
        blockers.add("AUTHORIZED_FEE_BUDGET_MISMATCH")
    if authorization.approved_total_outflow_ceiling != current_plan.total_authorized_outflow_ceiling:
        blockers.add("AUTHORIZED_OUTFLOW_CEILING_MISMATCH")
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
    return valid_plan and not blockers, tuple(sorted(blockers))
