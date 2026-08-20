from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .distribution_accounting_guard_v1 import evaluate_distribution_accounting_canonical_v1
from .distribution_accounting_v1 import (
    DistributionAccountingAccountsV1,
    DistributionAccountingDecisionV1,
    DistributionAccountingV1Error,
)
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from .distribution_plan_v1 import DistributionPlanV1
from .reporting import FlowType, ReportingLedger, ReportingLine


def post_settled_owner_distribution_v1(
    ledger: ReportingLedger,
    *,
    decision_id: str,
    event_id: str,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    receipt_payloads: Sequence[Mapping[str, Any]],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
):
    """Canonical settlement->accounting path for actual owner distributions.

    Raw MetaPay evidence is re-evaluated immediately before ledger mutation. A
    caller-supplied DistributionAccountingDecision alone cannot use this path.
    """

    decision: DistributionAccountingDecisionV1 = evaluate_distribution_accounting_canonical_v1(
        decision_id=decision_id,
        ledger=ledger,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt_payload=attempt_payload,
        utilization_payload=utilization_payload,
        receipt_payloads=receipt_payloads,
        accounts=accounts,
        decided_at=decided_at,
    )
    if decision.status != "POSTABLE" or decision.settled_total_amount <= 0:
        raise DistributionAccountingV1Error(
            "distribution accounting evidence is not postable: " + ",".join(decision.blockers)
        )
    amount = decision.settled_total_amount
    entry = ledger.post(
        event_id=event_id,
        reference=utilization_payload["digest"],
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(
            ReportingLine(accounts.distribution_equity_account, debit=amount),
            ReportingLine(accounts.external_cash_account, credit=amount),
        ),
        evidence_digest=decision.digest,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION",
            "capital_direction": "OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "distribution_accounting_decision_digest": decision.digest,
            "distribution_utilization_digest": utilization_payload["digest"],
            "settled_receipt_set_digest": decision.settled_receipt_set_digest,
            "distribution_plan_digest": plan.digest,
            "distribution_authorization_digest": authorization.digest,
            "distribution_execution_ticket_digest": ticket.digest,
            "distribution_attempt_digest": attempt_payload["digest"],
            "affected_period_id": plan.affected_period_id,
            "operational_source_account_id": plan.source_account_id,
            "source_account_mapping_evidence_digest": accounts.source_account_mapping_evidence_digest,
        },
    )
    return decision, entry
