from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_authorization_v2 import DistributionAuthorizationV2
from sinergy_financial_os.distribution_execution_ticket_v2 import DistributionExecutionTicketV2
from sinergy_financial_os.distribution_fee_accounting_v2 import (
    DistributionFeeAccountingAccountsV2,
    DistributionFeeAccountingV2Error,
    evaluate_distribution_fee_accounting_v2,
    post_distribution_fee_accounting_v2,
)
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1
from sinergy_financial_os.distribution_plan_v2 import DistributionPlanV2
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, FlowType, ReportingAccountSpec, ReportingLedger, ReportingLine
from sinergy_financial_os.reporting_metrics import realized_external_pnl_since

H="1"*64
REQ="2"*64
POLICY="3"*64
DECISION="4"*64
T0=datetime(2026,8,23,10,0,tzinfo=UTC)

def digest_payload(body:dict,field="digest"):
    x=dict(body);x[field]=canonical_json_digest(x);return x

def financial_objects():
    beneficiaries=(DistributionBeneficiaryV1("a","bank-a",Decimal("10"),"dist-a-v2"),DistributionBeneficiaryV1("b","bank-b",Decimal("8"),"dist-b-v2"))
    plan=DistributionPlanV2(plan_id="plan",distribution_available_capacity_digest=H,affected_period_id="2026-Q3",distribution_currency="USD",source_account_id="treasury-usd",beneficiaries=beneficiaries,capacity_limit=Decimal("20"),external_fee_budget=Decimal("2"),generated_at=datetime(2026,8,23,9,30,tzinfo=UTC))
    auth=DistributionAuthorizationV2(authorization_id="auth",decision="APPROVED",decision_authority="MULTISIG_GOVERNANCE",distribution_plan_digest=plan.digest,distribution_available_capacity_digest=H,affected_period_id=plan.affected_period_id,distribution_currency=plan.distribution_currency,source_account_id=plan.source_account_id,beneficiary_set_digest=plan.beneficiary_set_digest,approved_principal_amount=Decimal("18"),approved_external_fee_budget=Decimal("2"),approved_total_outflow_ceiling=Decimal("20"),requirement_registry_digest=REQ,approver_policy_digest=POLICY,decision_evidence_digest=DECISION,decided_at=datetime(2026,8,23,9,40,tzinfo=UTC),expires_at=datetime(2026,8,23,11,0,tzinfo=UTC))
    ticket=DistributionExecutionTicketV2(ticket_id="ticket",distribution_authorization_digest=auth.digest,distribution_plan_digest=plan.digest,distribution_available_capacity_digest=H,affected_period_id=plan.affected_period_id,distribution_currency=plan.distribution_currency,source_account_id=plan.source_account_id,beneficiary_set_digest=plan.beneficiary_set_digest,principal_total=Decimal("18"),external_fee_budget=Decimal("2"),total_authorized_outflow_ceiling=Decimal("20"),requirement_registry_digest=REQ,approver_policy_digest=POLICY,verified_at=datetime(2026,8,23,9,50,tzinfo=UTC),expires_at=datetime(2026,8,23,10,40,tzinfo=UTC))
    return plan,auth,ticket

def metapay_payloads(*,fees=("0.7","1.2"),statuses=("SETTLED","SETTLED")):
    plan,auth,ticket=financial_objects()
    bindings=[]
    for i,b in enumerate(plan.beneficiaries):
        bindings.append({"beneficiary_id":b.beneficiary_id,"destination_id":b.destination_id,"principal_amount":str(b.amount),"payment_idempotency_key":b.payment_idempotency_key,"intent_id":f"intent-{i}","intent_binding_digest":str(i+5)*64})
    attempt=digest_payload({"schema":"distribution.batch-attempt/v2","attempt_id":"attempt","distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest,"source_account_id":plan.source_account_id,"distribution_currency":plan.distribution_currency,"planned_principal_total":"18","authorized_external_fee_budget":"2","authorized_total_outflow_ceiling":"20","intent_bindings":bindings,"created_at":"2026-08-23T10:00:00Z","status":"AUTHORIZATION_CONSUMED_FOR_FEE_BUDGETED_ATTEMPT","authorization_consumption":"CONSUMED","authority":"METAPAY_DISTRIBUTION_HANDOFF_V2","execution_authority":"EXISTING_METAPAY_STATE_MACHINE","accounting_authority":"NONE","profit_recognition":"NOT_PERFORMED"})
    receipts=[];settled_ids=[];failed_ids=[];settled_total=Decimal("0");fee_total=Decimal("0")
    for i,(b,fee_text,status) in enumerate(zip(plan.beneficiaries,fees,statuses)):
        fee=Decimal(fee_text);settled=b.amount if status=="SETTLED" else Decimal("0");cash=settled+fee
        if status=="SETTLED":settled_ids.append(b.beneficiary_id);settled_total+=settled
        else:failed_ids.append(b.beneficiary_id)
        fee_total+=fee
        body={"schema":"distribution.settlement-receipt/v2","settlement_id":f"settlement-{i}","intent_id":f"intent-{i}","distribution_attempt_digest":attempt["digest"],"distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest,"beneficiary_id":b.beneficiary_id,"payment_idempotency_key":b.payment_idempotency_key,"payer_id":plan.source_account_id,"payee_id":b.destination_id,"asset":plan.distribution_currency,"planned_principal_amount":str(b.amount),"settled_principal_amount":str(settled),"authorized_external_fee_budget":"2","payer_borne_external_fee":fee_text,"payer_cash_outflow":str(cash),"authorized_total_outflow_ceiling":"20","external_fee_evidence_digest":("8"*64 if fee>0 else None),"fee_treatment":"EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT","status":status,"finality_time":f"2026-08-23T10:0{5+i}:00Z","reconciled":status=="SETTLED","external_references":[f"ref-{i}"],"settlement_evidence_digest":"9"*64,"authority":"SETTLEMENT_EVIDENCE_ONLY","settlement_authority":"Shtenco/synergy_pay_system","accounting_authority":"Shtenco/synergy_financial_os","profit_recognition":"NOT_PERFORMED","authorization_consumption":"CONSUMED_BY_BATCH_ATTEMPT","execution_authority":"NONE"}
        receipts.append(digest_payload(body,"receipt_digest"))
    if len(settled_ids)==2:status="FULLY_SETTLED"
    elif settled_ids:status="PARTIALLY_SETTLED_REQUIRES_NEW_PLAN"
    else:status="FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION"
    utilization=digest_payload({"schema":"distribution.utilization/v2","utilization_id":"util","distribution_attempt_digest":attempt["digest"],"distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest,"planned_principal_total":"18","settled_principal_total":str(settled_total),"authorized_external_fee_budget":"2","actual_external_fee_total":str(fee_total),"unused_external_fee_budget":str(Decimal("2")-fee_total),"authorized_total_outflow_ceiling":"20","actual_payer_cash_outflow":str(settled_total+fee_total),"receipt_digests":sorted(r["receipt_digest"] for r in receipts),"settled_beneficiary_ids":sorted(settled_ids),"failed_beneficiary_ids":sorted(failed_ids),"status":status,"finalized_at":"2026-08-23T10:10:00Z","authorization_consumption":"CONSUMED","authority":"METAPAY_DISTRIBUTION_UTILIZATION_V2","accounting_authority":"REFERENCE_ONLY","profit_recognition":"NOT_PERFORMED","unused_fee_budget_treatment":"UNUTILIZED_AUTHORIZED_CAPACITY_NOT_PROFIT","execution_authority":"NONE"})
    return plan,auth,ticket,attempt,utilization,tuple(receipts)

def ledger(*,cash_account_class=AccountClass.ASSET):
    l=ReportingLedger("USD")
    l.register_account(ReportingAccountSpec("cash","External cash",cash_account_class,ConsolidationClass.EXTERNAL,"CASH"))
    l.register_account(ReportingAccountSpec("equity","Distribution equity",AccountClass.EQUITY,ConsolidationClass.EXTERNAL,"EQUITY"))
    l.register_account(ReportingAccountSpec("fee-expense","Settlement fees",AccountClass.EXPENSE,ConsolidationClass.EXTERNAL,"EXPENSE"))
    l.post(event_id="fund",reference="funding",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("cash",debit=Decimal("30")),ReportingLine("equity",credit=Decimal("30"))),evidence_digest=H)
    return l

def accounts():return DistributionFeeAccountingAccountsV2("cash","equity","fee-expense","7"*64)

def test_principal_and_fee_post_separately_and_only_fee_hits_realized_pnl():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads();l=ledger();start=l.sequence
    decision,entries=post_distribution_fee_accounting_v2(l,decision_id="d",principal_event_id="principal",fee_event_id="fee",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=receipts,accounts=accounts(),decided_at=T0.replace(minute=20))
    assert decision.settled_principal_total==Decimal("18")
    assert decision.actual_external_fee_total==Decimal("1.9")
    assert [e.flow_type for e in entries]==[FlowType.EXTERNAL_CAPITAL,FlowType.EXTERNAL_EXPENSE]
    assert realized_external_pnl_since(l,start)==Decimal("-1.9")
    assert l.balance("cash")==Decimal("10.1")
    assert l.balance("equity")==Decimal("12")
    assert l.balance("fee-expense")==Decimal("1.9")

def test_failed_settlement_fee_only_is_postable_external_expense():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads(fees=("0.3","0.2"),statuses=("FAILED","FAILED"));l=ledger();start=l.sequence
    decision,entries=post_distribution_fee_accounting_v2(l,decision_id="fee-only",principal_event_id="unused-principal",fee_event_id="failed-fee",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=receipts,accounts=accounts(),decided_at=T0.replace(minute=20))
    assert decision.settled_principal_total==0 and decision.actual_external_fee_total==Decimal("0.5")
    assert len(entries)==1 and entries[0].flow_type==FlowType.EXTERNAL_EXPENSE
    assert l.balance("equity")==Decimal("30")
    assert realized_external_pnl_since(l,start)==Decimal("-0.5")

def test_unused_fee_budget_is_not_posted_as_profit_or_expense():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads(fees=("0.7","1.2"));l=ledger();start=l.sequence
    decision,entries=post_distribution_fee_accounting_v2(l,decision_id="unused",principal_event_id="p",fee_event_id="f",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=receipts,accounts=accounts(),decided_at=T0.replace(minute=20))
    assert Decimal(u["unused_external_fee_budget"])==Decimal("0.1")
    assert decision.actual_external_fee_total==Decimal("1.9")
    assert realized_external_pnl_since(l,start)==Decimal("-1.9")

def test_receipt_cannot_hide_fee_inside_reduced_principal():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads();bad=list(receipts);bad[0]=dict(bad[0]);bad[0]["planned_principal_amount"]="9";body=dict(bad[0]);body.pop("receipt_digest");bad[0]["receipt_digest"]=canonical_json_digest(body);l=ledger()
    with pytest.raises(DistributionFeeAccountingV2Error,match="planned economics"):
        evaluate_distribution_fee_accounting_v2(decision_id="bad",ledger=l,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=bad,accounts=accounts(),decided_at=T0.replace(minute=20))

def test_aggregate_fee_over_authorized_budget_is_rejected_even_with_fresh_utilization_digest():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads(fees=("1.2","1.2"));l=ledger()
    with pytest.raises(DistributionFeeAccountingV2Error,match="fee/cash|exceeds"):
        evaluate_distribution_fee_accounting_v2(decision_id="too-much",ledger=l,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=receipts,accounts=accounts(),decided_at=T0.replace(minute=20))

def test_fee_account_must_be_external_expense():
    plan,auth,ticket,attempt,u,receipts=metapay_payloads();l=ReportingLedger("USD")
    l.register_account(ReportingAccountSpec("cash","External cash",AccountClass.ASSET,ConsolidationClass.EXTERNAL,"CASH"));l.register_account(ReportingAccountSpec("equity","Distribution equity",AccountClass.EQUITY,ConsolidationClass.EXTERNAL,"EQUITY"));l.register_account(ReportingAccountSpec("fee-expense","Wrong fee",AccountClass.ASSET,ConsolidationClass.EXTERNAL,"CASH"));l.post(event_id="fund",reference="fund",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("cash",debit=Decimal("30")),ReportingLine("equity",credit=Decimal("30"))),evidence_digest=H)
    with pytest.raises(DistributionFeeAccountingV2Error,match="EXTERNAL EXPENSE"):
        evaluate_distribution_fee_accounting_v2(decision_id="bad-account",ledger=l,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=u,receipt_payloads=receipts,accounts=accounts(),decided_at=T0.replace(minute=20))
