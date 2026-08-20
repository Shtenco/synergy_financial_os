from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .distribution_authorization_v1 import (
    DistributionAuthorizationV1,
    DistributionAuthorizationV1Error,
    verify_distribution_authorization_context_v1,
)
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .distribution_plan_v1 import DistributionBeneficiaryV1, DistributionPlanV1, DistributionPlanV1Error
from .liquidity_replay_v1 import LiquidityReplayV1
from .numeric import canonical_decimal_text


def _decimal(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be canonical decimal text")
    result = Decimal(value)
    if not result.is_finite() or canonical_decimal_text(result) != value:
        raise ValueError(f"{field_name} is not canonical decimal text")
    if positive and result <= 0:
        raise ValueError(f"{field_name} must be strictly positive")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field_name} is not canonical UTC text")
    return parsed


def verify_distribution_plan_payload_v1(payload: Mapping[str, Any]) -> DistributionPlanV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.plan/v1":
            raise DistributionPlanV1Error("unsupported distribution plan schema")
        raw_beneficiaries = payload.get("beneficiaries")
        if not isinstance(raw_beneficiaries, list):
            raise DistributionPlanV1Error("beneficiaries must be array")
        beneficiaries = tuple(
            DistributionBeneficiaryV1(
                beneficiary_id=item.get("beneficiary_id"),
                destination_id=item.get("destination_id"),
                amount=_decimal(item.get("amount"), "beneficiary amount", positive=True),
                payment_idempotency_key=item.get("payment_idempotency_key"),
            )
            for item in raw_beneficiaries
        )
        plan = DistributionPlanV1(
            plan_id=payload.get("plan_id"),
            distribution_capacity_replay_digest=payload.get("distribution_capacity_replay_digest"),
            liquidity_replay_digest=payload.get("liquidity_replay_digest"),
            affected_period_id=payload.get("affected_period_id"),
            distribution_currency=payload.get("distribution_currency"),
            source_account_id=payload.get("source_account_id"),
            beneficiaries=beneficiaries,
            capacity_limit=_decimal(payload.get("capacity_limit"), "capacity_limit", positive=True),
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            usage_policy=payload.get("usage_policy"),
            authority=payload.get("authority"),
            authorization_authority=payload.get("authorization_authority"),
            execution_authority=payload.get("execution_authority"),
        )
        if payload.get("beneficiary_set_digest") != plan.beneficiary_set_digest:
            raise DistributionPlanV1Error("beneficiary_set_digest mismatch")
        if _decimal(payload.get("total_amount"), "total_amount", positive=True) != plan.total_amount:
            raise DistributionPlanV1Error("total_amount mismatch")
        if plan.to_dict() != dict(payload):
            raise DistributionPlanV1Error("distribution plan payload is not canonical or digest mismatch")
        return plan
    except (ValueError, TypeError) as exc:
        if isinstance(exc, DistributionPlanV1Error):
            raise
        raise DistributionPlanV1Error(str(exc)) from exc


def verify_distribution_plan_context_v1(
    plan: DistributionPlanV1,
    capacity: DistributionCapacityReplayV1,
    liquidity_replay: LiquidityReplayV1,
) -> bool:
    if capacity.status != "CAPACITY_AVAILABLE":
        raise DistributionPlanV1Error("current distribution capacity is not available")
    if plan.distribution_capacity_replay_digest != capacity.digest:
        raise DistributionPlanV1Error("DistributionPlan / current capacity digest mismatch")
    if plan.capacity_limit != capacity.final_distribution_capacity:
        raise DistributionPlanV1Error("DistributionPlan capacity limit differs from current capacity")
    if plan.total_amount > capacity.final_distribution_capacity:
        raise DistributionPlanV1Error("DistributionPlan total exceeds current capacity")
    if plan.liquidity_replay_digest != liquidity_replay.digest:
        raise DistributionPlanV1Error("DistributionPlan / current LiquidityReplay mismatch")
    if plan.distribution_currency != liquidity_replay.reporting_currency:
        raise DistributionPlanV1Error("DistributionPlan currency mismatch")
    if plan.affected_period_id != capacity.affected_period_id or plan.affected_period_id != liquidity_replay.affected_period_id:
        raise DistributionPlanV1Error("DistributionPlan affected period mismatch")
    if plan.generated_at < capacity.generated_at:
        raise DistributionPlanV1Error("DistributionPlan predates capacity replay")
    return True


def verify_distribution_authorization_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionAuthorizationV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.authorization/v1":
            raise DistributionAuthorizationV1Error("unsupported distribution authorization schema")
        authorization = DistributionAuthorizationV1(
            authorization_id=payload.get("authorization_id"),
            decision=payload.get("decision"),
            decision_authority=payload.get("decision_authority"),
            distribution_plan_digest=payload.get("distribution_plan_digest"),
            distribution_capacity_replay_digest=payload.get("distribution_capacity_replay_digest"),
            liquidity_replay_digest=payload.get("liquidity_replay_digest"),
            affected_period_id=payload.get("affected_period_id"),
            distribution_currency=payload.get("distribution_currency"),
            source_account_id=payload.get("source_account_id"),
            beneficiary_set_digest=payload.get("beneficiary_set_digest"),
            approved_total_amount=_decimal(payload.get("approved_total_amount"), "approved_total_amount"),
            requirement_registry_digest=payload.get("requirement_registry_digest"),
            approver_policy_digest=payload.get("approver_policy_digest"),
            decision_evidence_digest=payload.get("decision_evidence_digest"),
            decided_at=_time(payload.get("decided_at"), "decided_at"),
            expires_at=_time(payload.get("expires_at"), "expires_at"),
            usage_policy=payload.get("usage_policy"),
            notes_digest=payload.get("notes_digest"),
            execution_authority=payload.get("execution_authority"),
            ai_authority=payload.get("ai_authority"),
        )
        if authorization.to_dict() != dict(payload):
            raise DistributionAuthorizationV1Error("distribution authorization payload is not canonical or digest mismatch")
        return authorization
    except (ValueError, TypeError) as exc:
        if isinstance(exc, DistributionAuthorizationV1Error):
            raise
        raise DistributionAuthorizationV1Error(str(exc)) from exc


def verify_distribution_authorization_bundle_v1(
    authorization: DistributionAuthorizationV1,
    *,
    current_plan: DistributionPlanV1,
    current_capacity_replay: DistributionCapacityReplayV1,
    current_liquidity_replay: LiquidityReplayV1,
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[bool, tuple[str, ...]]:
    blockers: set[str] = set()
    try:
        verify_distribution_plan_context_v1(current_plan, current_capacity_replay, current_liquidity_replay)
    except DistributionPlanV1Error:
        blockers.add("CURRENT_PLAN_CONTEXT_INVALID")
    valid, auth_blockers = verify_distribution_authorization_context_v1(
        authorization,
        current_plan=current_plan,
        current_capacity_replay=current_capacity_replay,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=now,
    )
    blockers.update(auth_blockers)
    if authorization.liquidity_replay_digest != current_liquidity_replay.digest:
        blockers.add("STALE_LIQUIDITY_REPLAY")
    if authorization.affected_period_id != current_plan.affected_period_id:
        blockers.add("AFFECTED_PERIOD_MISMATCH")
    if authorization.distribution_currency != current_liquidity_replay.reporting_currency:
        blockers.add("DISTRIBUTION_CURRENCY_MISMATCH")
    return valid and not blockers, tuple(sorted(blockers))
