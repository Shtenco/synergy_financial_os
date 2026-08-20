from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1, DistributionExecutionTicketV1Error
from .numeric import canonical_decimal_text


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionExecutionTicketV1Error("total_amount must be canonical decimal text")
    result = Decimal(value)
    if not result.is_finite() or result <= 0 or canonical_decimal_text(result) != value:
        raise DistributionExecutionTicketV1Error("total_amount is not canonical positive decimal")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DistributionExecutionTicketV1Error(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise DistributionExecutionTicketV1Error(f"{field_name} is not canonical UTC text")
    return parsed


def verify_distribution_execution_ticket_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionExecutionTicketV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.execution-ticket/v1":
        raise DistributionExecutionTicketV1Error("unsupported distribution execution ticket schema")
    ticket = DistributionExecutionTicketV1(
        ticket_id=payload.get("ticket_id"),
        distribution_authorization_digest=payload.get("distribution_authorization_digest"),
        distribution_plan_digest=payload.get("distribution_plan_digest"),
        distribution_capacity_replay_digest=payload.get("distribution_capacity_replay_digest"),
        liquidity_replay_digest=payload.get("liquidity_replay_digest"),
        affected_period_id=payload.get("affected_period_id"),
        distribution_currency=payload.get("distribution_currency"),
        source_account_id=payload.get("source_account_id"),
        beneficiary_set_digest=payload.get("beneficiary_set_digest"),
        total_amount=_decimal(payload.get("total_amount")),
        requirement_registry_digest=payload.get("requirement_registry_digest"),
        approver_policy_digest=payload.get("approver_policy_digest"),
        verified_at=_time(payload.get("verified_at"), "verified_at"),
        expires_at=_time(payload.get("expires_at"), "expires_at"),
        authority=payload.get("authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
        usage_policy=payload.get("usage_policy"),
    )
    if ticket.to_dict() != dict(payload):
        raise DistributionExecutionTicketV1Error("execution ticket payload is not canonical or digest mismatch")
    return ticket
