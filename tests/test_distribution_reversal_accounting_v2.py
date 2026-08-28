from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_authorization_v3 import DistributionAuthorizationV3
from sinergy_financial_os.distribution_execution_ticket_v3 import DistributionExecutionTicketV3
from sinergy_financial_os.distribution_fee_accounting_v2 import DistributionFeeAccountingAccountsV2
from sinergy_financial_os.distribution_fee_accounting_v3 import post_distribution_fee_accounting_v3
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1
from sinergy_financial_os.distribution_plan_v3 import DistributionPlanV3
from sinergy_financial_os.distribution_reversal_accounting_v2 import (
    DistributionReversalAccountingV2Error,
    evaluate_distribution_reversal_accounting_v2,
    post_distribution_reversal_accounting_v2,
)
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, FlowType, ReportingAccountSpec, ReportingLedger, ReportingLine
from sinergy_financial_os.reporting_metrics import realized_external_pnl_since

H="1"*64
REQ="2"*64
POLICY="3"*64
DECISION="4"*64


def digest(body:dict,field="digest"):
    item=dict(body);item[field]=canonical_json_digest(item);return item


def setup_cycle():
    beneficiary=DistributionBeneficiaryV1("a","bank-a",Decimal("10"),"dist-a-v3")
    plan=DistributionPlanV3(plan_id="plan",distribution_available_capacity_schema="distribution.available-capacity/v3",distribution_available_capacity_digest=H,affected_period_id="2026-Q3",distribution_currency="USD",source_account_id="treasury-usd",beneficiaries=(beneficiary,),capacity_limit=Decimal("11"),external_fee_budget=Decimal("1"),generated_at=datetime(2026,8,28,8,0,tzinfo=UTC))
    auth=DistributionAuthorizationV3(authorization_id="auth",decision="APPROVED",decision_authority="MULTISIG_GOVERNANCE",distribution_plan_digest=plan.digest,distribution_available_capacity_schema="distribution.available-capacity/v3",distribution_available_capacity_digest=H,affected_period_id=plan.affected_period_id,distribution_currency="USD",source_account_id=plan.source_account_id,beneficiary_set_digest=plan.beneficiary_set_digest,approved_principal_amount=Decimal("10"),approved_external_fee_budget=Decimal("1"),approved_total_outflow_ceiling=Decimal("11"),requirement_registry_digest=REQ,approver_policy_digest=POLICY,decision_evidence_digest=DECISION,decided_at=datetime(2026,8,28,8,5,tzinfo=UTC),expires_at=datetime(2026,8,28,10,0,tzinfo=UTC))
    ticket=DistributionExecutionTicketV3(ticket_id="ticket",distribution_authorization_digest=auth.digest,distribution_plan_digest=plan.digest,distribution_available_capacity_schema="distribution.available-capacity/v3",distribution_available_capacity_digest=H,affected_period_id=plan.affected_period_id,distribution_currency="USD",source_account_id=plan.source_account_id,beneficiary_set_digest=plan.beneficiary_set_digest,principal_total=Decimal("10"),external_fee_budget=Decimal("1"),total_authorized_outflow_ceiling=Decimal("11"),requirement_registry_digest=REQ,approver_policy_digest=POLICY,verified_at=datetime(2026,8,28,8,10,tzinfo=UTC),expires_at=datetime(2026,8,28,9,50,tzinfo=UTC))
    binding={"beneficiary_id":"a","destination_id":"bank-a","principal_amount":"10","payment_idempotency_key":"dist-a-v3","intent_id":"intent-a","intent_binding_digest":"5"*64}
    attempt=digest({"schema":"distribution.batch-attempt/v3","attempt_id":"attempt","distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_schema":"distribution.available-capacity/v3","distribution_available_capacity_digest":H,"beneficiary_set_digest":plan.beneficiary_set_digest,"source_account_id":plan.source_account_id,"distribution_currency":"USD","planned_principal_total":"10","authorized_external_fee_budget":"1","authorized_total_outflow_ceiling":"11","intent_bindings":[binding],"created_at":"2026-08-28T08:15:00Z","status":"AUTHORIZATION_CONSUMED_FOR_FEE_AWARE_ATTEMPT_V3","authorization_consumption":"CONSUMED","authority":"METAPAY_DISTRIBUTION_HANDOFF_V3","execution_authority":"EXISTING_METAPAY_STATE_MACHINE","accounting_authority":"NONE","profit_recognition":"NOT_PERFORMED"})
    receipt=digest({"schema":"distribution.settlement-receipt/v3","settlement_id":"settlement-a","intent_id":"intent-a","distribution_attempt_digest":attempt["digest"],"distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_schema":"distribution.available-capacity/v3","distribution_available_capacity_digest":H,"beneficiary_set_digest":plan.beneficiary_set_digest,"beneficiary_id":"a","payment_idempotency_key":"dist-a-v3","payer_id":plan.source_account_id,"payee_id":"bank-a","asset":"USD","planned_principal_amount":"10","settled_principal_amount":"10","authorized_external_fee_budget":"1","payer_borne_external_fee":"0.7","payer_cash_outflow":"10.7","authorized_total_outflow_ceiling":"11","external_fee_evidence_digest":"8"*64,"fee_treatment":"EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT","status":"SETTLED","finality_time":"2026-08-28T08:20:00Z","reconciled":True,"external_references":["settlement-ref"],"settlement_evidence_digest":"9"*64,"authority":"SETTLEMENT_EVIDENCE_ONLY","settlement_authority":"Shtenco/synergy_pay_system","accounting_authority":"Shtenco/synergy_financial_os","profit_recognition":"NOT_PERFORMED","authorization_consumption":"CONSUMED_BY_BATCH_ATTEMPT","execution_authority":"NONE"},"receipt_digest")
    util=digest({"schema":"distribution.utilization/v3","utilization_id":"util","distribution_attempt_digest":attempt["digest"],"distribution_execution_ticket_digest":ticket.digest,"distribution_authorization_digest":auth.digest,"distribution_plan_digest":plan.digest,"distribution_available_capacity_schema":"distribution.available-capacity/v3","distribution_available_capacity_digest":H,"beneficiary_set_digest":plan.beneficiary_set_digest,"planned_principal_total":"10","settled_principal_total":"10","authorized_external_fee_budget":"1","actual_external_fee_total":"0.7","unused_external_fee_budget":"0.3","authorized_total_outflow_ceiling":"11","actual_payer_cash_outflow":"10.7","receipt_digests":[receipt["receipt_digest"]],"settled_beneficiary_ids":["a"],"failed_beneficiary_ids":[],"status":"FULLY_SETTLED","finalized_at":"2026-08-28T08:25:00Z","authorization_consumption":"CONSUMED","authority":"METAPAY_DISTRIBUTION_UTILIZATION_V3","accounting_authority":"REFERENCE_ONLY","profit_recognition":"NOT_PERFORMED","unused_fee_budget_treatment":"UNUTILIZED_AUTHORIZED_CAPACITY_NOT_PROFIT","execution_authority":"NONE"})
    ledger=ReportingLedger("USD")
    ledger.register_account(ReportingAccountSpec("cash","cash",AccountClass.ASSET,ConsolidationClass.EXTERNAL,"CASH"));ledger.register_account(ReportingAccountSpec("equity","equity",AccountClass.EQUITY,ConsolidationClass.EXTERNAL,"EQUITY"));ledger.register_account(ReportingAccountSpec("fee","fee",AccountClass.EXPENSE,ConsolidationClass.EXTERNAL,"EXPENSE"))
    ledger.post(event_id="fund",reference="fund",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("cash",debit=Decimal("20")),ReportingLine("equity",credit=Decimal("20"))),evidence_digest=H)
    accounts=DistributionFeeAccountingAccountsV2("cash","equity","fee","7"*64)
    original_decision,_=post_distribution_fee_accounting_v3(ledger,decision_id="original",principal_event_id="payout",fee_event_id="settlement-fee",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=(receipt,),accounts=accounts,decided_at=datetime(2026,8,28,8,30,tzinfo=UTC))
    return plan,auth,ticket,attempt,util,receipt,ledger,accounts,original_decision


def reversal(receipt,*,refund="0.5",processing="0.1"):
    body={"schema":"distribution.settlement-reversal/v2","reversal_id":"rev-a","original_distribution_receipt_digest":receipt["receipt_digest"],"original_settlement_id":receipt["settlement_id"],"distribution_attempt_digest":receipt["distribution_attempt_digest"],"distribution_execution_ticket_digest":receipt["distribution_execution_ticket_digest"],"distribution_authorization_digest":receipt["distribution_authorization_digest"],"distribution_plan_digest":receipt["distribution_plan_digest"],"distribution_available_capacity_schema":"distribution.available-capacity/v3","distribution_available_capacity_digest":receipt["distribution_available_capacity_digest"],"beneficiary_set_digest":receipt["beneficiary_set_digest"],"beneficiary_id":"a","payment_idempotency_key":"dist-a-v3","payer_id":"treasury-usd","payee_id":"bank-a","asset":"USD","returned_principal_amount":"10","original_payer_borne_external_fee":"0.7","refunded_original_fee":refund,"reversal_processing_fee":processing,"gross_cash_return":str(Decimal("10")+Decimal(refund)),"fee_refund_evidence_digest":"a"*64 if Decimal(refund)>0 else None,"reversal_fee_evidence_digest":"b"*64 if Decimal(processing)>0 else None,"fee_refund_treatment":"REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE","reversal_fee_treatment":"NEW_EXTERNAL_COST_SEPARATE_FROM_RETURNED_PRINCIPAL_AND_FEE_REFUND","status":"REVERSED_CONFIRMED","observed_at":"2026-08-28T09:00:00Z","external_references":["reversal-ref"],"reversal_evidence_digest":"c"*64,"authority":"SETTLEMENT_REVERSAL_EVIDENCE_ONLY","settlement_authority":"Shtenco/synergy_pay_system","accounting_authority":"Shtenco/synergy_financial_os","authorization_consumption":"REMAINS_CONSUMED","profit_recognition":"NOT_PERFORMED","execution_authority":"NONE"}
    return digest(body)


def test_principal_refund_and_processing_fee_post_as_three_flows():
    plan,auth,ticket,attempt,util,receipt,ledger,accounts,original=setup_cycle();start=ledger.sequence
    decision,entries=post_distribution_reversal_accounting_v2(ledger,decision_id="reverse",principal_event_id="principal-return",fee_refund_event_id="fee-refund",reversal_fee_event_id="reversal-fee",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=reversal(receipt),accounts=accounts,decided_at=datetime(2026,8,28,9,5,tzinfo=UTC))
    assert decision.returned_principal_amount==Decimal("10")
    assert decision.refunded_original_fee==Decimal("0.5")
    assert decision.reversal_processing_fee==Decimal("0.1")
    assert decision.net_cash_effect==Decimal("10.4")
    assert decision.realized_pnl_effect==Decimal("0.4")
    assert [entry.flow_type for entry in entries]==[FlowType.EXTERNAL_CAPITAL,FlowType.EXTERNAL_EXPENSE,FlowType.EXTERNAL_EXPENSE]
    assert ledger.balance("cash")==Decimal("19.7")
    assert ledger.balance("equity")==Decimal("20")
    assert ledger.balance("fee")==Decimal("0.3")
    assert realized_external_pnl_since(ledger,start)==Decimal("0.4")


def test_double_reversal_is_no_action_and_cannot_post_twice():
    plan,auth,ticket,attempt,util,receipt,ledger,accounts,original=setup_cycle();payload=reversal(receipt)
    post_distribution_reversal_accounting_v2(ledger,decision_id="one",principal_event_id="return-one",fee_refund_event_id="refund-one",reversal_fee_event_id="fee-one",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=payload,accounts=accounts,decided_at=datetime(2026,8,28,9,5,tzinfo=UTC))
    decision=evaluate_distribution_reversal_accounting_v2(decision_id="two",ledger=ledger,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=payload,accounts=accounts,decided_at=datetime(2026,8,28,9,6,tzinfo=UTC))
    assert decision.status=="NO_ACTION"
    with pytest.raises(DistributionReversalAccountingV2Error,match="not postable"):
        post_distribution_reversal_accounting_v2(ledger,decision_id="two",principal_event_id="return-two",fee_refund_event_id="refund-two",reversal_fee_event_id="fee-two",plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=payload,accounts=accounts,decided_at=datetime(2026,8,28,9,6,tzinfo=UTC))


def test_fresh_hash_cannot_over_refund_original_fee():
    plan,auth,ticket,attempt,util,receipt,ledger,accounts,original=setup_cycle();bad=reversal(receipt,refund="0.8",processing="0")
    with pytest.raises(DistributionReversalAccountingV2Error,match="formula"):
        evaluate_distribution_reversal_accounting_v2(decision_id="bad",ledger=ledger,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=bad,accounts=accounts,decided_at=datetime(2026,8,28,9,5,tzinfo=UTC))


def test_fresh_hash_cannot_revive_authorization():
    plan,auth,ticket,attempt,util,receipt,ledger,accounts,original=setup_cycle();bad=reversal(receipt);bad["authorization_consumption"]="UNCONSUMED";body=dict(bad);body.pop("digest");bad["digest"]=canonical_json_digest(body)
    with pytest.raises(DistributionReversalAccountingV2Error,match="revive"):
        evaluate_distribution_reversal_accounting_v2(decision_id="bad-auth",ledger=ledger,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original,settlement_reversal_payload=bad,accounts=accounts,decided_at=datetime(2026,8,28,9,5,tzinfo=UTC))
