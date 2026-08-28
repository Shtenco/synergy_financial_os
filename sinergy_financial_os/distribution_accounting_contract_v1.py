from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .distribution_accounting_v1 import DistributionAccountingDecisionV1, DistributionAccountingV1Error
from .numeric import canonical_decimal_text


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionAccountingV1Error("settled_total_amount must be canonical decimal text")
    result = Decimal(value)
    if not result.is_finite() or result < 0 or canonical_decimal_text(result) != value:
        raise DistributionAccountingV1Error("settled_total_amount is not canonical non-negative decimal")
    return result


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DistributionAccountingV1Error("decided_at must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise DistributionAccountingV1Error("decided_at is not canonical UTC text")
    return parsed


def verify_distribution_accounting_decision_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionAccountingDecisionV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.accounting-decision/v1":
        raise DistributionAccountingV1Error("unsupported distribution accounting decision schema")
    decision = DistributionAccountingDecisionV1(
        decision_id=payload.get("decision_id"),
        distribution_plan_digest=payload.get("distribution_plan_digest"),
        distribution_authorization_digest=payload.get("distribution_authorization_digest"),
        distribution_execution_ticket_digest=payload.get("distribution_execution_ticket_digest"),
        distribution_attempt_digest=payload.get("distribution_attempt_digest"),
        distribution_utilization_digest=payload.get("distribution_utilization_digest"),
        settled_receipt_set_digest=payload.get("settled_receipt_set_digest"),
        affected_period_id=payload.get("affected_period_id"),
        operational_source_account_id=payload.get("operational_source_account_id"),
        reporting_cash_account_id=payload.get("reporting_cash_account_id"),
        distribution_equity_account_id=payload.get("distribution_equity_account_id"),
        source_account_mapping_evidence_digest=payload.get("source_account_mapping_evidence_digest"),
        reporting_currency=payload.get("reporting_currency"),
        settled_total_amount=_decimal(payload.get("settled_total_amount")),
        status=payload.get("status"),
        blockers=tuple(payload.get("blockers") or ()),
        decided_at=_time(payload.get("decided_at")),
        accounting_flow_type=payload.get("accounting_flow_type"),
        economic_class=payload.get("economic_class"),
        pnl_treatment=payload.get("pnl_treatment"),
        ledger_posting_authority=payload.get("ledger_posting_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
    )
    if decision.to_dict() != dict(payload):
        raise DistributionAccountingV1Error("distribution accounting decision payload is not canonical or digest mismatch")
    return decision
