from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .distribution_accounting_v1 import DistributionAccountingAccountsV1, DistributionAccountingDecisionV1
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from .distribution_plan_v1 import DistributionPlanV1
from .distribution_reversal_accounting_v1 import (
    DistributionReversalAccountingV1Error,
    post_distribution_settlement_reversal_v1,
)
from .reporting import ReportingLedger


def post_distribution_settlement_reversal_canonical_v1(
    ledger: ReportingLedger,
    *,
    decision_id: str,
    event_id: str,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    original_receipt_payloads: Sequence[Mapping[str, Any]],
    original_accounting_decision: DistributionAccountingDecisionV1,
    settlement_reversal_payload: Mapping[str, Any],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
):
    if settlement_reversal_payload.get("settlement_authority") != "Shtenco/synergy_pay_system":
        raise DistributionReversalAccountingV1Error(
            "distribution settlement reversal must be issued by MetaPay settlement authority"
        )
    return post_distribution_settlement_reversal_v1(
        ledger,
        decision_id=decision_id,
        event_id=event_id,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt_payload=attempt_payload,
        utilization_payload=utilization_payload,
        original_receipt_payloads=original_receipt_payloads,
        original_accounting_decision=original_accounting_decision,
        settlement_reversal_payload=settlement_reversal_payload,
        accounts=accounts,
        decided_at=decided_at,
    )
