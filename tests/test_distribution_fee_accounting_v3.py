from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_authorization_v3 import DistributionAuthorizationV3
from sinergy_financial_os.distribution_execution_ticket_v3 import DistributionExecutionTicketV3
from sinergy_financial_os.distribution_fee_accounting_v2 import DistributionFeeAccountingAccountsV2
from sinergy_financial_os.distribution_fee_accounting_v3 import (
    DistributionFeeAccountingV3Error,
    evaluate_distribution_fee_accounting_v3,
    post_distribution_fee_accounting_v3,
)
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1
from sinergy_financial_os.distribution_plan_v3 import DistributionPlanV3
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.reporting_metrics import realized_external_pnl_since

H = "1" * 64
REQ = "2" * 64
POLICY = "3" * 64
DECISION = "4" * 64
T0 = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)


def digest_payload(body: dict, field: str = "digest") -> dict:
    item = dict(body)
    item[field] = canonical_json_digest(item)
    return item


def financial_objects():
    beneficiaries = (
        DistributionBeneficiaryV1("a", "bank-a", Decimal("10"), "dist-a-v3"),
        DistributionBeneficiaryV1("b", "bank-b", Decimal("8"), "dist-b-v3"),
    )
    plan = DistributionPlanV3(
        plan_id="plan-v3",
        distribution_available_capacity_schema="distribution.available-capacity/v3",
        distribution_available_capacity_digest=H,
        affected_period_id="2026-Q3",
        distribution_currency="USD",
        source_account_id="treasury-usd",
        beneficiaries=beneficiaries,
        capacity_limit=Decimal("20"),
        external_fee_budget=Decimal("2"),
        generated_at=datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
    )
    auth = DistributionAuthorizationV3(
        authorization_id="auth-v3",
        decision="APPROVED",
        decision_authority="MULTISIG_GOVERNANCE",
        distribution_plan_digest=plan.digest,
        distribution_available_capacity_schema="distribution.available-capacity/v3",
        distribution_available_capacity_digest=H,
        affected_period_id=plan.affected_period_id,
        distribution_currency=plan.distribution_currency,
        source_account_id=plan.source_account_id,
        beneficiary_set_digest=plan.beneficiary_set_digest,
        approved_principal_amount=Decimal("18"),
        approved_external_fee_budget=Decimal("2"),
        approved_total_outflow_ceiling=Decimal("20"),
        requirement_registry_digest=REQ,
        approver_policy_digest=POLICY,
        decision_evidence_digest=DECISION,
        decided_at=datetime(2026, 8, 24, 9, 40, tzinfo=UTC),
        expires_at=datetime(2026, 8, 24, 11, 0, tzinfo=UTC),
    )
    ticket = DistributionExecutionTicketV3(
        ticket_id="ticket-v3",
        distribution_authorization_digest=auth.digest,
        distribution_plan_digest=plan.digest,
        distribution_available_capacity_schema="distribution.available-capacity/v3",
        distribution_available_capacity_digest=H,
        affected_period_id=plan.affected_period_id,
        distribution_currency=plan.distribution_currency,
        source_account_id=plan.source_account_id,
        beneficiary_set_digest=plan.beneficiary_set_digest,
        principal_total=Decimal("18"),
        external_fee_budget=Decimal("2"),
        total_authorized_outflow_ceiling=Decimal("20"),
        requirement_registry_digest=REQ,
        approver_policy_digest=POLICY,
        verified_at=datetime(2026, 8, 24, 9, 50, tzinfo=UTC),
        expires_at=datetime(2026, 8, 24, 10, 40, tzinfo=UTC),
    )
    return plan, auth, ticket


def metapay_payloads(*, fees=("0.7", "1.2"), statuses=("SETTLED", "SETTLED")):
    plan, auth, ticket = financial_objects()
    bindings = []
    for index, beneficiary in enumerate(plan.beneficiaries):
        bindings.append({
            "beneficiary_id": beneficiary.beneficiary_id,
            "destination_id": beneficiary.destination_id,
            "principal_amount": str(beneficiary.amount),
            "payment_idempotency_key": beneficiary.payment_idempotency_key,
            "intent_id": f"intent-v3-{index}",
            "intent_binding_digest": str(index + 5) * 64,
        })
    attempt = digest_payload({
        "schema": "distribution.batch-attempt/v3",
        "attempt_id": "attempt-v3",
        "distribution_execution_ticket_digest": ticket.digest,
        "distribution_authorization_digest": auth.digest,
        "distribution_plan_digest": plan.digest,
        "distribution_available_capacity_schema": "distribution.available-capacity/v3",
        "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
        "beneficiary_set_digest": plan.beneficiary_set_digest,
        "source_account_id": plan.source_account_id,
        "distribution_currency": plan.distribution_currency,
        "planned_principal_total": "18",
        "authorized_external_fee_budget": "2",
        "authorized_total_outflow_ceiling": "20",
        "intent_bindings": bindings,
        "created_at": "2026-08-24T10:00:00Z",
        "status": "AUTHORIZATION_CONSUMED_FOR_FEE_AWARE_ATTEMPT_V3",
        "authorization_consumption": "CONSUMED",
        "authority": "METAPAY_DISTRIBUTION_HANDOFF_V3",
        "execution_authority": "EXISTING_METAPAY_STATE_MACHINE",
        "accounting_authority": "NONE",
        "profit_recognition": "NOT_PERFORMED",
    })
    receipts = []
    settled_ids = []
    failed_ids = []
    settled_total = Decimal("0")
    fee_total = Decimal("0")
    for index, (beneficiary, fee_text, status) in enumerate(zip(plan.beneficiaries, fees, statuses)):
        fee = Decimal(fee_text)
        settled = beneficiary.amount if status == "SETTLED" else Decimal("0")
        cash = settled + fee
        if status == "SETTLED":
            settled_ids.append(beneficiary.beneficiary_id)
            settled_total += settled
        else:
            failed_ids.append(beneficiary.beneficiary_id)
        fee_total += fee
        body = {
            "schema": "distribution.settlement-receipt/v3",
            "settlement_id": f"settlement-v3-{index}",
            "intent_id": f"intent-v3-{index}",
            "distribution_attempt_digest": attempt["digest"],
            "distribution_execution_ticket_digest": ticket.digest,
            "distribution_authorization_digest": auth.digest,
            "distribution_plan_digest": plan.digest,
            "distribution_available_capacity_schema": "distribution.available-capacity/v3",
            "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
            "beneficiary_set_digest": plan.beneficiary_set_digest,
            "beneficiary_id": beneficiary.beneficiary_id,
            "payment_idempotency_key": beneficiary.payment_idempotency_key,
            "payer_id": plan.source_account_id,
            "payee_id": beneficiary.destination_id,
            "asset": plan.distribution_currency,
            "planned_principal_amount": str(beneficiary.amount),
            "settled_principal_amount": str(settled),
            "authorized_external_fee_budget": "2",
            "payer_borne_external_fee": fee_text,
            "payer_cash_outflow": str(cash),
            "authorized_total_outflow_ceiling": "20",
            "external_fee_evidence_digest": ("8" * 64 if fee > 0 else None),
            "fee_treatment": "EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT",
            "status": status,
            "finality_time": f"2026-08-24T10:0{5 + index}:00Z",
            "reconciled": status == "SETTLED",
            "external_references": [f"ref-v3-{index}"],
            "settlement_evidence_digest": "9" * 64,
            "authority": "SETTLEMENT_EVIDENCE_ONLY",
            "settlement_authority": "Shtenco/synergy_pay_system",
            "accounting_authority": "Shtenco/synergy_financial_os",
            "profit_recognition": "NOT_PERFORMED",
            "authorization_consumption": "CONSUMED_BY_BATCH_ATTEMPT",
            "execution_authority": "NONE",
        }
        receipts.append(digest_payload(body, "receipt_digest"))
    if len(settled_ids) == 2:
        utilization_status = "FULLY_SETTLED"
    elif settled_ids:
        utilization_status = "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN"
    else:
        utilization_status = "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION"
    utilization = digest_payload({
        "schema": "distribution.utilization/v3",
        "utilization_id": "util-v3",
        "distribution_attempt_digest": attempt["digest"],
        "distribution_execution_ticket_digest": ticket.digest,
        "distribution_authorization_digest": auth.digest,
        "distribution_plan_digest": plan.digest,
        "distribution_available_capacity_schema": "distribution.available-capacity/v3",
        "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
        "beneficiary_set_digest": plan.beneficiary_set_digest,
        "planned_principal_total": "18",
        "settled_principal_total": str(settled_total),
        "authorized_external_fee_budget": "2",
        "actual_external_fee_total": str(fee_total),
        "unused_external_fee_budget": str(Decimal("2") - fee_total),
        "authorized_total_outflow_ceiling": "20",
        "actual_payer_cash_outflow": str(settled_total + fee_total),
        "receipt_digests": sorted(receipt["receipt_digest"] for receipt in receipts),
        "settled_beneficiary_ids": sorted(settled_ids),
        "failed_beneficiary_ids": sorted(failed_ids),
        "status": utilization_status,
        "finalized_at": "2026-08-24T10:10:00Z",
        "authorization_consumption": "CONSUMED",
        "authority": "METAPAY_DISTRIBUTION_UTILIZATION_V3",
        "accounting_authority": "REFERENCE_ONLY",
        "profit_recognition": "NOT_PERFORMED",
        "unused_fee_budget_treatment": "UNUTILIZED_AUTHORIZED_CAPACITY_NOT_PROFIT",
        "execution_authority": "NONE",
    })
    return plan, auth, ticket, attempt, utilization, tuple(receipts)


def ledger() -> ReportingLedger:
    result = ReportingLedger("USD")
    result.register_account(ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    result.register_account(ReportingAccountSpec("equity", "Distribution equity", AccountClass.EQUITY, ConsolidationClass.EXTERNAL, "EQUITY"))
    result.register_account(ReportingAccountSpec("fee-expense", "Settlement fees", AccountClass.EXPENSE, ConsolidationClass.EXTERNAL, "EXPENSE"))
    result.post(
        event_id="fund",
        reference="funding",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("30")), ReportingLine("equity", credit=Decimal("30"))),
        evidence_digest=H,
    )
    return result


def accounts() -> DistributionFeeAccountingAccountsV2:
    return DistributionFeeAccountingAccountsV2("cash", "equity", "fee-expense", "7" * 64)


def test_v3_principal_and_fee_post_separately_only_fee_hits_pnl():
    plan, auth, ticket, attempt, utilization, receipts = metapay_payloads()
    reporting = ledger()
    start = reporting.sequence
    decision, entries = post_distribution_fee_accounting_v3(
        reporting,
        decision_id="decision-v3",
        principal_event_id="principal-v3",
        fee_event_id="fee-v3",
        plan=plan,
        authorization=auth,
        ticket=ticket,
        attempt_payload=attempt,
        utilization_payload=utilization,
        receipt_payloads=receipts,
        accounts=accounts(),
        decided_at=T0.replace(minute=20),
    )
    assert decision.distribution_available_capacity_schema == "distribution.available-capacity/v3"
    assert decision.settled_principal_total == Decimal("18")
    assert decision.actual_external_fee_total == Decimal("1.9")
    assert [entry.flow_type for entry in entries] == [FlowType.EXTERNAL_CAPITAL, FlowType.EXTERNAL_EXPENSE]
    assert realized_external_pnl_since(reporting, start) == Decimal("-1.9")
    assert reporting.balance("cash") == Decimal("10.1")
    assert reporting.balance("equity") == Decimal("12")
    assert reporting.balance("fee-expense") == Decimal("1.9")


def test_v3_failed_settlement_fee_only_is_external_expense():
    plan, auth, ticket, attempt, utilization, receipts = metapay_payloads(fees=("0.3", "0.2"), statuses=("FAILED", "FAILED"))
    reporting = ledger()
    start = reporting.sequence
    decision, entries = post_distribution_fee_accounting_v3(
        reporting,
        decision_id="fee-only-v3",
        principal_event_id="unused-principal-v3",
        fee_event_id="failed-fee-v3",
        plan=plan,
        authorization=auth,
        ticket=ticket,
        attempt_payload=attempt,
        utilization_payload=utilization,
        receipt_payloads=receipts,
        accounts=accounts(),
        decided_at=T0.replace(minute=20),
    )
    assert decision.settled_principal_total == 0
    assert decision.actual_external_fee_total == Decimal("0.5")
    assert len(entries) == 1 and entries[0].flow_type == FlowType.EXTERNAL_EXPENSE
    assert reporting.balance("equity") == Decimal("30")
    assert realized_external_pnl_since(reporting, start) == Decimal("-0.5")


def test_v3_unused_fee_budget_is_never_posted():
    plan, auth, ticket, attempt, utilization, receipts = metapay_payloads()
    reporting = ledger()
    start = reporting.sequence
    decision, _ = post_distribution_fee_accounting_v3(
        reporting,
        decision_id="unused-v3",
        principal_event_id="p-v3",
        fee_event_id="f-v3",
        plan=plan,
        authorization=auth,
        ticket=ticket,
        attempt_payload=attempt,
        utilization_payload=utilization,
        receipt_payloads=receipts,
        accounts=accounts(),
        decided_at=T0.replace(minute=20),
    )
    assert Decimal(utilization["unused_external_fee_budget"]) == Decimal("0.1")
    assert decision.actual_external_fee_total == Decimal("1.9")
    assert realized_external_pnl_since(reporting, start) == Decimal("-1.9")


def test_v3_rejects_v2_attempt_generation_even_with_fresh_digest():
    plan, auth, ticket, attempt, utilization, receipts = metapay_payloads()
    bad = dict(attempt)
    bad["schema"] = "distribution.batch-attempt/v2"
    bad.pop("digest")
    bad["digest"] = canonical_json_digest(bad)
    with pytest.raises(DistributionFeeAccountingV3Error, match="v3 required"):
        evaluate_distribution_fee_accounting_v3(
            decision_id="downgrade",
            ledger=ledger(),
            plan=plan,
            authorization=auth,
            ticket=ticket,
            attempt_payload=bad,
            utilization_payload=utilization,
            receipt_payloads=receipts,
            accounts=accounts(),
            decided_at=T0.replace(minute=20),
        )


def test_v3_receipt_cannot_hide_fee_inside_reduced_principal():
    plan, auth, ticket, attempt, utilization, receipts = metapay_payloads()
    bad_receipts = list(receipts)
    bad_receipts[0] = dict(bad_receipts[0])
    bad_receipts[0]["planned_principal_amount"] = "9"
    body = dict(bad_receipts[0])
    body.pop("receipt_digest")
    bad_receipts[0]["receipt_digest"] = canonical_json_digest(body)
    with pytest.raises(DistributionFeeAccountingV3Error, match="planned economics"):
        evaluate_distribution_fee_accounting_v3(
            decision_id="bad-principal",
            ledger=ledger(),
            plan=plan,
            authorization=auth,
            ticket=ticket,
            attempt_payload=attempt,
            utilization_payload=utilization,
            receipt_payloads=bad_receipts,
            accounts=accounts(),
            decided_at=T0.replace(minute=20),
        )
