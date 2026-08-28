from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .liquidity_replay_v1 import LiquidityReplayV1
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "distribution.plan/v1"
ZERO = Decimal("0")
USAGE_POLICY = "SINGLE_EXACT_BATCH"
HEX = frozenset("0123456789abcdef")


class DistributionPlanV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionPlanV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionPlanV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionPlanV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionBeneficiaryV1:
    beneficiary_id: str
    destination_id: str
    amount: Decimal
    payment_idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "beneficiary_id", _text(self.beneficiary_id, "beneficiary_id"))
        object.__setattr__(self, "destination_id", _text(self.destination_id, "destination_id"))
        object.__setattr__(
            self,
            "payment_idempotency_key",
            _text(self.payment_idempotency_key, "payment_idempotency_key"),
        )
        amount = finite_decimal(self.amount, "beneficiary amount")
        if amount <= ZERO:
            raise DistributionPlanV1Error("beneficiary amount must be strictly positive")
        object.__setattr__(self, "amount", amount)

    def to_dict(self) -> dict[str, Any]:
        return {
            "beneficiary_id": self.beneficiary_id,
            "destination_id": self.destination_id,
            "amount": canonical_decimal_text(self.amount),
            "payment_idempotency_key": self.payment_idempotency_key,
        }


@dataclass(frozen=True)
class DistributionPlanV1:
    plan_id: str
    distribution_capacity_replay_digest: str
    liquidity_replay_digest: str
    affected_period_id: str
    distribution_currency: str
    source_account_id: str
    beneficiaries: tuple[DistributionBeneficiaryV1, ...]
    capacity_limit: Decimal
    generated_at: datetime
    usage_policy: str = USAGE_POLICY
    authority: str = "FINANCIAL_OS_DISTRIBUTION_PLAN"
    authorization_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.usage_policy != USAGE_POLICY:
            raise DistributionPlanV1Error("v1 supports only SINGLE_EXACT_BATCH")
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_PLAN":
            raise DistributionPlanV1Error("distribution plan authority must remain Financial OS")
        if self.authorization_authority != "NONE" or self.execution_authority != "NONE":
            raise DistributionPlanV1Error("distribution plan cannot authorize or execute")
        object.__setattr__(self, "plan_id", _text(self.plan_id, "plan_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "distribution_currency", _text(self.distribution_currency, "distribution_currency").upper())
        object.__setattr__(self, "source_account_id", _text(self.source_account_id, "source_account_id"))
        object.__setattr__(
            self,
            "distribution_capacity_replay_digest",
            _hex64(self.distribution_capacity_replay_digest, "distribution_capacity_replay_digest"),
        )
        object.__setattr__(self, "liquidity_replay_digest", _hex64(self.liquidity_replay_digest, "liquidity_replay_digest"))
        capacity = finite_decimal(self.capacity_limit, "capacity_limit")
        if capacity <= ZERO:
            raise DistributionPlanV1Error("capacity_limit must be strictly positive")
        object.__setattr__(self, "capacity_limit", capacity)
        values = tuple(sorted(self.beneficiaries, key=lambda item: item.beneficiary_id))
        if not values or any(not isinstance(item, DistributionBeneficiaryV1) for item in values):
            raise DistributionPlanV1Error("distribution plan requires beneficiaries")
        beneficiary_ids = [item.beneficiary_id for item in values]
        idempotency_keys = [item.payment_idempotency_key for item in values]
        if len(set(beneficiary_ids)) != len(values):
            raise DistributionPlanV1Error("beneficiary_id must be unique within batch")
        if len(set(idempotency_keys)) != len(values):
            raise DistributionPlanV1Error("payment idempotency keys must be unique within batch")
        object.__setattr__(self, "beneficiaries", values)
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))
        if self.total_amount > self.capacity_limit:
            raise DistributionPlanV1Error("distribution plan total exceeds capacity limit")

    @property
    def total_amount(self) -> Decimal:
        return sum((item.amount for item in self.beneficiaries), ZERO)

    @property
    def beneficiary_set_digest(self) -> str:
        return canonical_json_digest([item.to_dict() for item in self.beneficiaries])

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "plan_id": self.plan_id,
            "distribution_capacity_replay_digest": self.distribution_capacity_replay_digest,
            "liquidity_replay_digest": self.liquidity_replay_digest,
            "affected_period_id": self.affected_period_id,
            "distribution_currency": self.distribution_currency,
            "source_account_id": self.source_account_id,
            "beneficiaries": [item.to_dict() for item in self.beneficiaries],
            "beneficiary_set_digest": self.beneficiary_set_digest,
            "total_amount": canonical_decimal_text(self.total_amount),
            "capacity_limit": canonical_decimal_text(self.capacity_limit),
            "usage_policy": self.usage_policy,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_plan_v1(
    *,
    plan_id: str,
    distribution_capacity_replay: DistributionCapacityReplayV1,
    liquidity_replay: LiquidityReplayV1,
    source_account_id: str,
    beneficiaries: Iterable[DistributionBeneficiaryV1],
    generated_at: datetime,
) -> DistributionPlanV1:
    if distribution_capacity_replay.status != "CAPACITY_AVAILABLE":
        raise DistributionPlanV1Error("distribution plan requires CAPACITY_AVAILABLE")
    if distribution_capacity_replay.final_distribution_capacity <= ZERO:
        raise DistributionPlanV1Error("distribution capacity must be positive")
    if distribution_capacity_replay.liquidity_replay_digest != liquidity_replay.digest:
        raise DistributionPlanV1Error("distribution capacity / LiquidityReplay mismatch")
    if distribution_capacity_replay.affected_period_id != liquidity_replay.affected_period_id:
        raise DistributionPlanV1Error("distribution capacity affected period mismatch")
    generated = _utc(generated_at, "generated_at")
    if generated < distribution_capacity_replay.generated_at:
        raise DistributionPlanV1Error("distribution plan cannot predate capacity replay")
    return DistributionPlanV1(
        plan_id=plan_id,
        distribution_capacity_replay_digest=distribution_capacity_replay.digest,
        liquidity_replay_digest=liquidity_replay.digest,
        affected_period_id=distribution_capacity_replay.affected_period_id,
        distribution_currency=liquidity_replay.reporting_currency,
        source_account_id=source_account_id,
        beneficiaries=tuple(beneficiaries),
        capacity_limit=distribution_capacity_replay.final_distribution_capacity,
        generated_at=generated,
    )
