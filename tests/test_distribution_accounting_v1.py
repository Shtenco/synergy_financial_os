from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_accounting_contract_v1 import verify_distribution_accounting_decision_payload_v1
from sinergy_financial_os.distribution_accounting_v1 import (
    DistributionAccountingAccountsV1,
    DistributionAccountingV1Error,
    evaluate_distribution_accounting_v1,
)
from sinergy_financial_os.distribution_accounting_guard_v1 import evaluate_distribution_accounting_canonical_v1
from sinergy_financial_os.distribution_authorization_v1 import DistributionAuthorizationV1
from sinergy_financial_os.distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1, DistributionPlanV1
from sinergy_financial_os.distribution_posting_v1 import post_settled_owner_distribution_v1
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.reporting_metrics import net_new_capital_since, realized_external_pnl_since
from sinergy_financial_os.valuation import ValuationRule

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/distribution_accounting_decision_v1.schema.json').read_text(encoding='utf-8'))


def dt(h,m=0): return datetime(2026,8,20,h,m,tzinfo=UTC)


def ledger():
 x=ReportingLedger('USD')
 x.register_account(ReportingAccountSpec('cash','External cash',AccountClass.ASSET,ConsolidationClass.EXTERNAL,'CASH'))
 x.register_account(ReportingAccountSpec('equity','Owner equity',AccountClass.EQUITY,ConsolidationClass.EXTERNAL,'EQUITY'))
 x.post(event_id='capital-001',reference='capital-ref-001',flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine('cash',debit=Decimal('100')),ReportingLine('equity',credit=Decimal('100'))),evidence_digest='01'*32,metadata={'economic_class':'OWNER_CAPITAL_CONTRIBUTION'})
 return x


def financial_objects():
 beneficiaries=(DistributionBeneficiaryV1('a','bank-a',Decimal('10'),'dist-a-001'),DistributionBeneficiaryV1('b','bank-b',Decimal('8'),'dist-b-001'))
 plan=DistributionPlanV1('plan-001','10'*32,'11'*32,'period-1','USD','treasury-usd',beneficiaries,Decimal('18'),dt(3,30))
 auth=DistributionAuthorizationV1('auth-001','APPROVED','MULTISIG_GOVERNANCE',plan.digest,plan.distribution_capacity_replay_digest,plan.liquidity_replay_digest,plan.affected_period_id,plan.distribution_currency,plan.source_account_id,plan.beneficiary_set_digest,plan.total_amount,'12'*32,'13'*32,'14'*32,dt(3,40),dt(4,40))
 ticket=DistributionExecutionTicketV1('ticket-001',auth.digest,plan.digest,plan.distribution_capacity_replay_digest,plan.liquidity_replay_digest,plan.affected_period_id,plan.distribution_currency,plan.source_account_id,plan.beneficiary_set_digest,plan.total_amount,auth.requirement_registry_digest,auth.approver_policy_digest,dt(3,50),dt(4,20))
 return plan,auth,ticket


def execution_payloads(*, fully_settled=False):
 plan,auth,ticket=financial_objects()
 bindings=[]
 for idx,b in enumerate(plan.beneficiaries, start=1):
  intent_id=f'intent-{idx}'
  binding_body={'intent_id':intent_id,'idempotency_key':b.payment_idempotency_key,'payer_id':plan.source_account_id,'payee_id':b.destination_id,'source_asset':'USD','target_asset':'USD','amount':str(b.amount),'purpose':'authorized_distribution','beneficiary_id':b.beneficiary_id,'distribution_plan_digest':plan.digest,'distribution_authorization_digest':auth.digest,'distribution_execution_ticket_digest':ticket.digest}
  bindings.append({'beneficiary_id':b.beneficiary_id,'destination_id':b.destination_id,'amount':str(b.amount),'payment_idempotency_key':b.payment_idempotency_key,'intent_id':intent_id,'intent_binding_digest':canonical_json_digest(binding_body)})
 attempt={'schema':'distribution.batch-attempt/v1','attempt_id':'attempt-001','distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'source_account_id':plan.source_account_id,'distribution_currency':'USD','total_amount':'18','intent_bindings':bindings,'created_at':'2026-08-20T04:00:00Z','status':'AUTHORIZATION_CONSUMED_FOR_ATTEMPT','authorization_consumption':'CONSUMED','authority':'METAPAY_DISTRIBUTION_HANDOFF','execution_authority':'EXISTING_METAPAY_STATE_MACHINE','accounting_authority':'NONE'}
 attempt['digest']=canonical_json_digest(attempt)
 receipts=[]
 statuses=('SETTLED','SETTLED') if fully_settled else ('SETTLED','FAILED')
 for b,status,minute in zip(plan.beneficiaries,statuses,(5,6)):
  r={'schema':'distribution.settlement-receipt/v1','settlement_id':f'settlement-{b.beneficiary_id}','intent_id':f'intent-{1 if b.beneficiary_id=="a" else 2}','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'beneficiary_id':b.beneficiary_id,'payment_idempotency_key':b.payment_idempotency_key,'payer_id':plan.source_account_id,'payee_id':b.destination_id,'asset':'USD','amount':str(b.amount),'payer_borne_external_fee':'0','status':status,'finality_time':f'2026-08-20T04:0{minute}:00Z','reconciled':status=='SETTLED','external_references':[f'bank-{b.beneficiary_id}'],'settlement_evidence_digest':('21' if b.beneficiary_id=='a' else '22')*32,'authority':'SETTLEMENT_EVIDENCE_ONLY','settlement_authority':'Shtenco/synergy_pay_system','accounting_authority':'Shtenco/synergy_financial_os','profit_recognition':'NOT_PERFORMED','authorization_consumption':'CONSUMED_BY_BATCH_ATTEMPT','execution_authority':'NONE'}
  r['receipt_digest']=canonical_json_digest(r); receipts.append(r)
 settled_ids=tuple(sorted(r['beneficiary_id'] for r in receipts if r['status']=='SETTLED'))
 failed_ids=tuple(sorted(r['beneficiary_id'] for r in receipts if r['status']!='SETTLED'))
 settled_total=sum((Decimal(r['amount']) for r in receipts if r['status']=='SETTLED'),Decimal('0'))
 status='FULLY_SETTLED' if fully_settled else 'PARTIALLY_SETTLED_REQUIRES_NEW_PLAN'
 util={'schema':'distribution.utilization/v1','utilization_id':'util-001','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'planned_total_amount':'18','settled_total_amount':str(settled_total),'receipt_digests':sorted(r['receipt_digest'] for r in receipts),'settled_beneficiary_ids':list(settled_ids),'failed_beneficiary_ids':list(failed_ids),'status':status,'finalized_at':'2026-08-20T04:07:00Z','authorization_consumption':'CONSUMED','authority':'METAPAY_DISTRIBUTION_UTILIZATION','accounting_authority':'REFERENCE_ONLY','execution_authority':'NONE'}
 util['digest']=canonical_json_digest(util)
 return plan,auth,ticket,attempt,tuple(receipts),util


def accounts(): return DistributionAccountingAccountsV1('cash','equity','31'*32)


def test_partial_utilization_posts_only_settled_owner_distribution_without_pnl_loss():
 l=ledger(); plan,auth,ticket,attempt,receipts,util=execution_payloads()
 decision,entry=post_settled_owner_distribution_v1(l,decision_id='accounting-001',event_id='distribution-entry-001',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=receipts,accounts=accounts(),decided_at=dt(4,10))
 assert decision.status=='POSTABLE' and decision.settled_total_amount==Decimal('10')
 assert entry.flow_type==FlowType.EXTERNAL_CAPITAL
 assert l.balance('cash')==Decimal('90') and l.balance('equity')==Decimal('90')
 policy={'CASH':ValuationRule('CASH',Decimal('1'),Decimal('1'),Decimal('1'),'BANK_BALANCE')}
 assert realized_external_pnl_since(l,1)==Decimal('0')
 assert net_new_capital_since(l,1,policy)==Decimal('-10')
 jsonschema.Draft202012Validator(SCHEMA).validate(decision.to_dict())
 assert verify_distribution_accounting_decision_payload_v1(decision.to_dict()).digest==decision.digest
 with pytest.raises(Exception,match='duplicate reference'):
  post_settled_owner_distribution_v1(l,decision_id='accounting-replay',event_id='distribution-entry-002',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=receipts,accounts=accounts(),decided_at=dt(4,11))


def test_full_utilization_posts_exact_18_not_plan_capacity_twice():
 l=ledger(); plan,auth,ticket,attempt,receipts,util=execution_payloads(fully_settled=True)
 decision,entry=post_settled_owner_distribution_v1(l,decision_id='accounting-full',event_id='distribution-entry-full',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=receipts,accounts=accounts(),decided_at=dt(4,10))
 assert decision.settled_total_amount==Decimal('18')
 assert l.balance('cash')==Decimal('82') and l.balance('equity')==Decimal('82')


def test_fresh_hash_tampered_intent_binding_is_rejected_by_financial_os_guard():
 l=ledger(); plan,auth,ticket,attempt,receipts,util=execution_payloads()
 attempt=dict(attempt); attempt['intent_bindings']=[dict(x) for x in attempt['intent_bindings']]
 attempt['intent_bindings'][0]['intent_binding_digest']='ff'*32
 body=dict(attempt); body.pop('digest'); attempt['digest']=canonical_json_digest(body)
 with pytest.raises(DistributionAccountingV1Error,match='intent_binding_digest'):
  evaluate_distribution_accounting_canonical_v1(decision_id='bad',ledger=l,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=receipts,accounts=accounts(),decided_at=dt(4,10))


def test_failed_no_settlement_is_no_action_and_cannot_post():
 l=ledger(); plan,auth,ticket,attempt,receipts,_=execution_payloads()
 failed=[]
 for r in receipts:
  x=dict(r); x['status']='FAILED'; x['reconciled']=False; x.pop('receipt_digest'); x['receipt_digest']=canonical_json_digest(x); failed.append(x)
 util={'schema':'distribution.utilization/v1','utilization_id':'util-failed','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'planned_total_amount':'18','settled_total_amount':'0','receipt_digests':sorted(r['receipt_digest'] for r in failed),'settled_beneficiary_ids':[],'failed_beneficiary_ids':['a','b'],'status':'FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION','finalized_at':'2026-08-20T04:07:00Z','authorization_consumption':'CONSUMED','authority':'METAPAY_DISTRIBUTION_UTILIZATION','accounting_authority':'REFERENCE_ONLY','execution_authority':'NONE'}; util['digest']=canonical_json_digest(util)
 decision=evaluate_distribution_accounting_v1(decision_id='no-action',ledger=l,plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=tuple(failed),accounts=accounts(),decided_at=dt(4,10))
 assert decision.status=='NO_ACTION' and decision.settled_total_amount==Decimal('0')
 with pytest.raises(DistributionAccountingV1Error,match='not postable'):
  post_settled_owner_distribution_v1(l,decision_id='no-action-post',event_id='no-action-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=tuple(failed),accounts=accounts(),decided_at=dt(4,10))
