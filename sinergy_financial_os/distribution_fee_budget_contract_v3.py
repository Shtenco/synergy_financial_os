from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .distribution_authorization_v2 import (
    DistributionAuthorizationV2,
    DistributionAuthorizationV2Error,
    verify_distribution_authorization_context_v2,
)
from .distribution_available_capacity_v2 import DistributionAvailableCapacityV2
from .distribution_budget_current_capacity_contract_v2 import verify_distribution_available_capacity_payload_v2
from .distribution_execution_ticket_v2 import (
    DistributionExecutionTicketV2,
    DistributionExecutionTicketV2Error,
    verify_distribution_execution_ticket_context_v2,
)
from .distribution_plan_v1 import DistributionBeneficiaryV1
from .distribution_plan_v2 import DistributionPlanV2, DistributionPlanV2Error, verify_distribution_plan_context_v2
from .numeric import canonical_decimal_text, finite_decimal

ZERO = Decimal("0")


def _decimal(value: Any, field_name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be canonical decimal text")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
        raise ValueError(f"{field_name} is not canonical decimal text")
    if positive and result <= ZERO:
        raise ValueError(f"{field_name} must be positive")
    if nonnegative and result < ZERO:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field_name} is not canonical UTC text")
    return parsed


def _beneficiaries(raw: Any) -> tuple[DistributionBeneficiaryV1, ...]:
    if not isinstance(raw, list) or not raw:
        raise DistributionPlanV2Error("beneficiaries must be non-empty array")
    values = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise DistributionPlanV2Error("beneficiary must be object")
        values.append(
            DistributionBeneficiaryV1(
                beneficiary_id=item.get("beneficiary_id"),
                destination_id=item.get("destination_id"),
                amount=_decimal(item.get("amount"), "beneficiary.amount", positive=True),
                payment_idempotency_key=item.get("payment_idempotency_key"),
            )
        )
    return tuple(values)


def verify_distribution_plan_payload_v2(payload: Mapping[str, Any]) -> DistributionPlanV2:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.plan/v2":
        raise DistributionPlanV2Error("unsupported distribution plan schema; fee-aware handoff requires v2")
    plan = DistributionPlanV2(
        plan_id=payload.get("plan_id"),
        distribution_available_capacity_digest=payload.get("distribution_available_capacity_digest"),
        affected_period_id=payload.get("affected_period_id"),
        distribution_currency=payload.get("distribution_currency"),
        source_account_id=payload.get("source_account_id"),
        beneficiaries=_beneficiaries(payload.get("beneficiaries")),
        capacity_limit=_decimal(payload.get("capacity_limit"), "capacity_limit", positive=True),
        external_fee_budget=_decimal(payload.get("external_fee_budget"), "external_fee_budget", nonnegative=True),
        generated_at=_time(payload.get("generated_at"), "generated_at"),
        usage_policy=payload.get("usage_policy"),
        fee_policy=payload.get("fee_policy"),
        authority=payload.get("authority"),
        authorization_authority=payload.get("authorization_authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
    )
    if plan.to_dict() != dict(payload):
        raise DistributionPlanV2Error("distribution plan payload is non-canonical, formula-tampered or digest-mismatched")
    return plan


def verify_distribution_authorization_payload_v2(payload: Mapping[str, Any]) -> DistributionAuthorizationV2:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.authorization/v2":
        raise DistributionAuthorizationV2Error("unsupported distribution authorization schema; fee-aware handoff requires v2")
    authorization = DistributionAuthorizationV2(
        authorization_id=payload.get("authorization_id"),
        decision=payload.get("decision"),
        decision_authority=payload.get("decision_authority"),
        distribution_plan_digest=payload.get("distribution_plan_digest"),
        distribution_available_capacity_digest=payload.get("distribution_available_capacity_digest"),
        affected_period_id=payload.get("affected_period_id"),
        distribution_currency=payload.get("distribution_currency"),
        source_account_id=payload.get("source_account_id"),
        beneficiary_set_digest=payload.get("beneficiary_set_digest"),
        approved_principal_amount=_decimal(payload.get("approved_principal_amount"), "approved_principal_amount", nonnegative=True),
        approved_external_fee_budget=_decimal(payload.get("approved_external_fee_budget"), "approved_external_fee_budget", nonnegative=True),
        approved_total_outflow_ceiling=_decimal(payload.get("approved_total_outflow_ceiling"), "approved_total_outflow_ceiling", nonnegative=True),
        requirement_registry_digest=payload.get("requirement_registry_digest"),
        approver_policy_digest=payload.get("approver_policy_digest"),
        decision_evidence_digest=payload.get("decision_evidence_digest"),
        decided_at=_time(payload.get("decided_at"), "decided_at"),
        expires_at=_time(payload.get("expires_at"), "expires_at"),
        execution_authority=payload.get("execution_authority"),
        payment_authority=payload.get("payment_authority"),
        ai_authority=payload.get("ai_authority"),
        usage_policy=payload.get("usage_policy"),
        fee_policy=payload.get("fee_policy"),
    )
    if authorization.to_dict() != dict(payload):
        raise DistributionAuthorizationV2Error("distribution authorization payload is non-canonical, formula-tampered or digest-mismatched")
    return authorization


def verify_distribution_execution_ticket_payload_v2(payload: Mapping[str, Any]) -> DistributionExecutionTicketV2:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.execution-ticket/v2":
        raise DistributionExecutionTicketV2Error("unsupported distribution execution-ticket schema; fee-aware handoff requires v2")
    ticket = DistributionExecutionTicketV2(
        ticket_id=payload.get("ticket_id"),
        distribution_authorization_digest=payload.get("distribution_authorization_digest"),
        distribution_plan_digest=payload.get("distribution_plan_digest"),
        distribution_available_capacity_digest=payload.get("distribution_available_capacity_digest"),
        affected_period_id=payload.get("affected_period_id"),
        distribution_currency=payload.get("distribution_currency"),
        source_account_id=payload.get("source_account_id"),
        beneficiary_set_digest=payload.get("beneficiary_set_digest"),
        principal_total=_decimal(payload.get("principal_total"), "principal_total", positive=True),
        external_fee_budget=_decimal(payload.get("external_fee_budget"), "external_fee_budget", nonnegative=True),
        total_authorized_outflow_ceiling=_decimal(payload.get("total_authorized_outflow_ceiling"), "total_authorized_outflow_ceiling", positive=True),
        requirement_registry_digest=payload.get("requirement_registry_digest"),
        approver_policy_digest=payload.get("approver_policy_digest"),
        verified_at=_time(payload.get("verified_at"), "verified_at"),
        expires_at=_time(payload.get("expires_at"), "expires_at"),
        authority=payload.get("authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
        usage_policy=payload.get("usage_policy"),
        fee_policy=payload.get("fee_policy"),
    )
    if ticket.to_dict() != dict(payload):
        raise DistributionExecutionTicketV2Error("distribution execution ticket payload is non-canonical, formula-tampered or digest-mismatched")
    return ticket


def verify_distribution_fee_budget_bundle_v3(
    *,
    available_capacity_payload: Mapping[str, Any],
    plan_payload: Mapping[str, Any],
    authorization_payload: Mapping[str, Any],
    ticket_payload: Mapping[str, Any],
    current_requirement_registry_digest: str,
    current_approver_policy_digest: str,
    now: datetime,
) -> tuple[DistributionAvailableCapacityV2, DistributionPlanV2, DistributionAuthorizationV2, DistributionExecutionTicketV2]:
    capacity = verify_distribution_available_capacity_payload_v2(available_capacity_payload)
    plan = verify_distribution_plan_payload_v2(plan_payload)
    authorization = verify_distribution_authorization_payload_v2(authorization_payload)
    ticket = verify_distribution_execution_ticket_payload_v2(ticket_payload)

    valid_plan, plan_blockers = verify_distribution_plan_context_v2(plan, current_available_capacity=capacity)
    if not valid_plan:
        raise DistributionPlanV2Error("fee-budget plan context invalid: " + ",".join(plan_blockers))
    valid_auth, auth_blockers = verify_distribution_authorization_context_v2(
        authorization,
        current_plan=plan,
        current_available_capacity=capacity,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=now,
    )
    if not valid_auth:
        raise DistributionAuthorizationV2Error("fee-budget authorization context invalid: " + ",".join(auth_blockers))
    valid_ticket, ticket_blockers = verify_distribution_execution_ticket_context_v2(
        ticket,
        authorization=authorization,
        plan=plan,
        available_capacity=capacity,
        current_requirement_registry_digest=current_requirement_registry_digest,
        current_approver_policy_digest=current_approver_policy_digest,
        now=now,
    )
    if not valid_ticket:
        raise DistributionExecutionTicketV2Error("fee-budget execution ticket context invalid: " + ",".join(ticket_blockers))

    principal = sum((item.amount for item in plan.beneficiaries), ZERO)
    if principal != plan.principal_total:
        raise DistributionPlanV2Error("beneficiary principal sum mismatch")
    if plan.total_authorized_outflow_ceiling != principal + plan.external_fee_budget:
        raise DistributionPlanV2Error("plan total outflow ceiling formula mismatch")
    if plan.total_authorized_outflow_ceiling > capacity.final_available_capacity:
        raise DistributionPlanV2Error("plan principal + fee budget exceeds current Financial OS capacity")
    if authorization.approved_principal_amount != principal:
        raise DistributionAuthorizationV2Error("authorization changed beneficiary principal")
    if authorization.approved_external_fee_budget != plan.external_fee_budget:
        raise DistributionAuthorizationV2Error("authorization changed external fee budget")
    if ticket.principal_total != principal or ticket.external_fee_budget != plan.external_fee_budget:
        raise DistributionExecutionTicketV2Error("ticket changed authorized principal/fee budget")
    if ticket.total_authorized_outflow_ceiling != principal + plan.external_fee_budget:
        raise DistributionExecutionTicketV2Error("ticket total outflow ceiling formula mismatch")
    return capacity, plan, authorization, ticket


def reject_legacy_distribution_schema_for_fee_authority(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema in {"distribution.plan/v1", "distribution.authorization/v1", "distribution.execution-ticket/v1"}:
        raise ValueError("legacy distribution v1 artifacts carry no payer-borne external-fee authority")
