from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_digest
from .distribution_accounting_v1 import (
    DistributionAccountingAccountsV1,
    DistributionAccountingDecisionV1,
    DistributionAccountingV1Error,
    evaluate_distribution_accounting_v1,
)
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from .distribution_plan_v1 import DistributionPlanV1
from .numeric import canonical_decimal_text
from .reporting import ReportingLedger


def _verify_attempt_intent_bindings_independently(
    attempt_payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
) -> None:
    bindings = attempt_payload.get("intent_bindings")
    if not isinstance(bindings, list) or len(bindings) != len(plan.beneficiaries):
        raise DistributionAccountingV1Error("attempt intent binding cardinality mismatch")
    by_beneficiary = {item.beneficiary_id: item for item in plan.beneficiaries}
    source = plan.source_account_id
    currency = plan.distribution_currency
    seen: set[str] = set()
    for raw in bindings:
        if not isinstance(raw, Mapping):
            raise DistributionAccountingV1Error("attempt intent binding must be object")
        beneficiary_id = raw.get("beneficiary_id")
        if not isinstance(beneficiary_id, str) or beneficiary_id not in by_beneficiary or beneficiary_id in seen:
            raise DistributionAccountingV1Error("attempt contains unknown/duplicate beneficiary binding")
        seen.add(beneficiary_id)
        beneficiary = by_beneficiary[beneficiary_id]
        amount_text = canonical_decimal_text(beneficiary.amount)
        if raw.get("destination_id") != beneficiary.destination_id:
            raise DistributionAccountingV1Error("attempt intent destination mismatch")
        if raw.get("amount") != amount_text:
            raise DistributionAccountingV1Error("attempt intent amount mismatch")
        if raw.get("payment_idempotency_key") != beneficiary.payment_idempotency_key:
            raise DistributionAccountingV1Error("attempt intent idempotency mismatch")
        intent_id = raw.get("intent_id")
        if not isinstance(intent_id, str) or not intent_id:
            raise DistributionAccountingV1Error("attempt intent_id is required")
        binding = {
            "intent_id": intent_id,
            "idempotency_key": beneficiary.payment_idempotency_key,
            "payer_id": source,
            "payee_id": beneficiary.destination_id,
            "source_asset": currency,
            "target_asset": currency,
            "amount": amount_text,
            "purpose": "authorized_distribution",
            "beneficiary_id": beneficiary_id,
            "distribution_plan_digest": plan.digest,
            "distribution_authorization_digest": authorization.digest,
            "distribution_execution_ticket_digest": ticket.digest,
        }
        if raw.get("intent_binding_digest") != canonical_json_digest(binding):
            raise DistributionAccountingV1Error("attempt intent_binding_digest mismatch")


def evaluate_distribution_accounting_canonical_v1(
    *,
    decision_id: str,
    ledger: ReportingLedger,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    receipt_payloads: Sequence[Mapping[str, Any]],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
) -> DistributionAccountingDecisionV1:
    _verify_attempt_intent_bindings_independently(
        attempt_payload,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
    )
    return evaluate_distribution_accounting_v1(
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
