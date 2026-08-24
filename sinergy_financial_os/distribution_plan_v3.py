from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_available_capacity_v3 import DistributionAvailableCapacityV3, SCHEMA as CAPACITY_SCHEMA
from .distribution_plan_v1 import DistributionBeneficiaryV1
from .numeric import canonical_decimal_text, finite_decimal

SCHEMA = "distribution.plan/v3"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
USAGE_POLICY = "SINGLE_EXACT_BATCH"
FEE_POLICY = "PAYER_BORNE_SEPARATE_FROM_PRINCIPAL_UP_TO_BUDGET"
CAPACITY_POLICY = "FEE_AWARE_BUDGET_STATE_V2_AVAILABLE_CAPACITY_V3_ONLY"


class DistributionPlanV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionPlanV3Error(f"{name} is required")
    return value.strip()


def _hex64(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if len(value) != 64 or any(ch not in HEX for ch in value):
        raise DistributionPlanV3Error(f"{name} must be hex64")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionPlanV3Error(f"{name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionPlanV3:
    plan_id: str
    distribution_available_capacity_schema: str
    distribution_available_capacity_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiaries: tuple[DistributionBeneficiaryV1, ...]
    capacity_limit: Decimal
    external_fee_budget: Decimal
    generated_at: datetime
    usage_policy: str = USAGE_POLICY
    fee_policy: str = FEE_POLICY
    capacity_policy: str = CAPACITY_POLICY
    authority: str = "FINANCIAL_OS_DISTRIBUTION_PLAN_V3"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.distribution_available_capacity_schema != CAPACITY_SCHEMA:
            raise DistributionPlanV3Error("v3 plan requires distribution.available-capacity/v3")
        if self.usage_policy != USAGE_POLICY or self.fee_policy != FEE_POLICY or self.capacity_policy != CAPACITY_POLICY:
            raise DistributionPlanV3Error("unsupported v3 plan policy")
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_PLAN_V3":
            raise DistributionPlanV3Error("plan authority mismatch")
        if any(value != "NONE" for value in (
            self.authorization_authority,
            self.payment_authority,
            self.execution_authority,
            self.ai_authority,
        )):
            raise DistributionPlanV3Error("plan cannot authorize, pay, execute or delegate to AI")
        object.__setattr__(self, "plan_id", _text(self.plan_id, "plan_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        object.__setattr__(self, "distribution_available_capacity_digest", _hex64(self.distribution_available_capacity_digest, "distribution_available_capacity_digest"))
        cap = finite_decimal(self.capacity_limit, "capacity_limit")
        fee = finite_decimal(self.external_fee_budget, "external_fee_budget")
        if cap <= ZERO or fee < ZERO:
            raise DistributionPlanV3Error("capacity must be positive and fee budget non-negative")
        object.__setattr__(self, "capacity_limit", cap)
        object.__setattr__(self, "external_fee_budget", fee)
        beneficiaries = tuple(sorted(self.beneficiaries, key=lambda item: item.beneficiary_id))
        if not beneficiaries or any(not isinstance(item, DistributionBeneficiaryV1) for item in beneficiaries):
            raise DistributionPlanV3Error("plan requires DistributionBeneficiaryV1 entries")
        if len({item.beneficiary_id for item in beneficiaries}) != len(beneficiaries):
            raise DistributionPlanV3Error("beneficiary ids must be unique")
        if len({item.payment_idempotency_key for item in beneficiaries}) != len(beneficiaries):
            raise DistributionPlanV3Error("payment idempotency keys must be unique")
        object.__setattr__(self, "beneficiaries", beneficiaries)
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))
        if self.total_authorized_outflow_ceiling > self.capacity_limit:
            raise DistributionPlanV3Error("principal + external fee budget exceeds fee-aware current capacity")

    @property
    def principal_total(self) -> Decimal:
        return sum((item.amount for item in self.beneficiaries), ZERO)

    @property
    def total_authorized_outflow_ceiling(self) -> Decimal:
        return self.principal_total + self.external_fee_budget

    @property
    def beneficiary_set_digest(self) -> str:
        return canonical_json_digest([item.to_dict() for item in self.beneficiaries])

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "plan_id": self.plan_id,
            "distribution_available_capacity_schema": self.distribution_available_capacity_schema,
            "distribution_available_capacity_digest": self.distribution_available_capacity_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiaries": [item.to_dict() for item in self.beneficiaries],
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "principal_total": canonical_decimal_text(self.principal_total),
            "external_fee_budget": canonical_decimal_text(self.external_fee_budget),
            "total_authorized_outflow_ceiling": canonical_decimal_text(self.total_authorized_outflow_ceiling),
            "capacity_limit": canonical_decimal_text(self.capacity_limit),
            "usage_policy": self.usage_policy,
            "fee_policy": self.fee_policy,
            "capacity_policy": self.capacity_policy,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_plan_v3(
    *,
    plan_id: str,
    available_capacity: DistributionAvailableCapacityV3,
    source_account_id: str,
    beneficiaries: Iterable[DistributionBeneficiaryV1],
    external_fee_budget: Decimal,
    generated_at: datetime,
) -> DistributionPlanV3:
    if not isinstance(available_capacity, DistributionAvailableCapacityV3):
        raise DistributionPlanV3Error("v3 plan requires DistributionAvailableCapacityV3")
    if available_capacity.status != "CAPACITY_AVAILABLE" or available_capacity.final_available_capacity <= ZERO:
        raise DistributionPlanV3Error("v3 plan requires current CAPACITY_AVAILABLE")
    generated = _utc(generated_at, "generated_at")
    if generated < available_capacity.generated_at:
        raise DistributionPlanV3Error("plan cannot predate current available capacity")
    return DistributionPlanV3(
        plan_id=plan_id,
        distribution_available_capacity_schema=CAPACITY_SCHEMA,
        distribution_available_capacity_digest=available_capacity.digest,
        affected_period_id=available_capacity.affected_period_id,
        distribution_currency=available_capacity.reporting_currency,
        source_account_id=source_account_id,
        beneficiaries=tuple(beneficiaries),
        capacity_limit=available_capacity.final_available_capacity,
        external_fee_budget=external_fee_budget,
        generated_at=generated,
    )


def verify_distribution_plan_context_v3(
    plan: DistributionPlanV3,
    *,
    current_available_capacity: DistributionAvailableCapacityV3,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    if not isinstance(current_available_capacity, DistributionAvailableCapacityV3):
        blockers.add("AVAILABLE_CAPACITY_GENERATION_MISMATCH")
        return False, tuple(sorted(blockers))
    if plan.distribution_available_capacity_schema != CAPACITY_SCHEMA:
        blockers.add("AVAILABLE_CAPACITY_SCHEMA_MISMATCH")
    if plan.distribution_available_capacity_digest != current_available_capacity.digest:
        blockers.add("STALE_DISTRIBUTION_AVAILABLE_CAPACITY")
    if current_available_capacity.status != "CAPACITY_AVAILABLE":
        blockers.add("CAPACITY_NO_LONGER_AVAILABLE")
    if plan.affected_period_id != current_available_capacity.affected_period_id:
        blockers.add("AFFECTED_PERIOD_MISMATCH")
    if plan.distribution_currency != current_available_capacity.reporting_currency:
        blockers.add("DISTRIBUTION_CURRENCY_MISMATCH")
    if plan.total_authorized_outflow_ceiling > current_available_capacity.final_available_capacity:
        blockers.add("PRINCIPAL_PLUS_FEE_BUDGET_EXCEEDS_CURRENT_CAPACITY")
    return not blockers, tuple(sorted(blockers))
