from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .distribution_reversal_accounting_v1 import (
    DistributionReversalAccountingDecisionV1,
    DistributionReversalAccountingV1Error,
)
from .numeric import canonical_decimal_text


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionReversalAccountingV1Error("reversal_amount must be canonical decimal text")
    result = Decimal(value)
    if not result.is_finite() or result <= 0 or canonical_decimal_text(result) != value:
        raise DistributionReversalAccountingV1Error("reversal_amount is not canonical positive decimal")
    return result


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DistributionReversalAccountingV1Error("decided_at must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise DistributionReversalAccountingV1Error("decided_at is not canonical UTC text")
    return parsed


def verify_distribution_reversal_accounting_decision_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionReversalAccountingDecisionV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.reversal-accounting-decision/v1":
        raise DistributionReversalAccountingV1Error("unsupported distribution reversal accounting decision schema")
    decision = DistributionReversalAccountingDecisionV1(
        decision_id=payload.get("decision_id"),
        original_distribution_accounting_decision_digest=payload.get("original_distribution_accounting_decision_digest"),
        original_distribution_reporting_entry_digest=payload.get("original_distribution_reporting_entry_digest"),
        original_distribution_utilization_digest=payload.get("original_distribution_utilization_digest"),
        original_distribution_receipt_digest=payload.get("original_distribution_receipt_digest"),
        distribution_settlement_reversal_digest=payload.get("distribution_settlement_reversal_digest"),
        beneficiary_id=payload.get("beneficiary_id"),
        reporting_cash_account_id=payload.get("reporting_cash_account_id"),
        distribution_equity_account_id=payload.get("distribution_equity_account_id"),
        source_account_mapping_evidence_digest=payload.get("source_account_mapping_evidence_digest"),
        reporting_currency=payload.get("reporting_currency"),
        reversal_amount=_decimal(payload.get("reversal_amount")),
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
        raise DistributionReversalAccountingV1Error("distribution reversal accounting decision payload is not canonical or digest mismatch")
    return decision
