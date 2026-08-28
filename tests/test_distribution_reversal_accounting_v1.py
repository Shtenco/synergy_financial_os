from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_accounting_v1 import DistributionAccountingAccountsV1
from sinergy_financial_os.distribution_authorization_v1 import DistributionAuthorizationV1
from sinergy_financial_os.distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1, DistributionPlanV1
from sinergy_financial_os.distribution_posting_v1 import post_settled_owner_distribution_v1
from sinergy_financial_os.distribution_reversal_accounting_contract_v1 import verify_distribution_reversal_accounting_decision_payload_v1
from sinergy_financial_os.distribution_reversal_accounting_guard_v1 import post_distribution_settlement_reversal_canonical_v1
from sinergy_financial_os.distribution_reversal_accounting_v1 import DistributionReversalAccountingV1Error
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, FlowType, ReportingAccountSpec, ReportingLedger, ReportingLine
from sinergy_financial_os.reporting_metrics import net_new_capital_since, realized_external_pnl_since
from sinergy_financial_os.valuation import ValuationRule

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/distribution_reversal_accounting_decision_v1.schema.json').read_text(encoding='utf-8'))

def dt(h,m=0): return datetime(2026,8,20,h,m,tzinfo=UTC)

def ledger():
 x=ReportingLedger('USD')
 x.register_account(ReportingAccountSpec('cash','External cash',AccountClass.ASSET,ConsolidationClass.EXTERNAL,'CASH'))
 x.register_account(ReportingAccountSpec('equity','Owner equity',AccountClass.EQUITY,ConsolidationClass.EXTERNAL,'EQUITY'))
 x.post(event_id='capital',reference='capital-ref',flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine('cash',debit=Decimal('100')),ReportingLine('equity',credit=Decimal('100'))),evidence_digest='01'*32,metadata={'economic_class':'OWNER_CAPITAL_CONTRIBUTION'})
 return x

def objects():
 b=DistributionBeneficiaryV1('a','bank-a',Decimal('10'),'dist-a-001')
 plan=DistributionPlanV1('plan','10'*32,'11'*32,'period-1','USD','treasury-usd',(b,),Decimal('10'),dt(3,30))
 auth=DistributionAuthorizationV1('auth','APPROVED','MULTISIG_GOVERNANCE',plan.digest,plan.distribution_capacity_replay_digest,plan.liquidity_replay_digest,plan.affected_period_id,plan.distribution_currency,plan.source_account_id,plan.beneficiary_set_digest,plan.total_amount,'12'*32,'13'*32,'14'*32,dt(3,40),dt(4,40))
 ticket=DistributionExecutionTicketV1('ticket',auth.digest,plan.digest,plan.distribution_capacity_replay_digest,plan.liquidity_replay_digest,plan.affected_period_id,plan.distribution_currency,plan.source_account_id,plan.beneficiary_set_digest,plan.total_amount,auth.requirement_registry_digest,auth.approver_policy_digest,dt(3,50),dt(4,20))
 binding_body={'intent_id':'intent-a','idempotency_key':b.payment_idempotency_key,'payer_id':plan.source_account_id,'payee_id':b.destination_id,'source_asset':'USD','target_asset':'USD','amount':'10','purpose':'authorized_distribution','beneficiary_id':'a','distribution_plan_digest':plan.digest,'distribution_authorization_digest':auth.digest,'distribution_execution_ticket_digest':ticket.digest}
 attempt={'schema':'distribution.batch-attempt/v1','attempt_id':'attempt','distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'source_account_id':plan.source_account_id,'distribution_currency':'USD','total_amount':'10','intent_bindings':[{'beneficiary_id':'a','destination_id':'bank-a','amount':'10','payment_idempotency_key':'dist-a-001','intent_id':'intent-a','intent_binding_digest':canonical_json_digest(binding_body)}],'created_at':'2026-08-20T04:00:00Z','status':'AUTHORIZATION_CONSUMED_FOR_ATTEMPT','authorization_consumption':'CONSUMED','authority':'METAPAY_DISTRIBUTION_HANDOFF','execution_authority':'EXISTING_METAPAY_STATE_MACHINE','accounting_authority':'NONE'}; attempt['digest']=canonical_json_digest(attempt)
 receipt={'schema':'distribution.settlement-receipt/v1','settlement_id':'settlement-a','intent_id':'intent-a','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'beneficiary_id':'a','payment_idempotency_key':'dist-a-001','payer_id':'treasury-usd','payee_id':'bank-a','asset':'USD','amount':'10','payer_borne_external_fee':'0','status':'SETTLED','finality_time':'2026-08-20T04:05:00Z','reconciled':True,'external_references':['bank-a-settled'],'settlement_evidence_digest':'15'*32,'authority':'SETTLEMENT_EVIDENCE_ONLY','settlement_authority':'Shtenco/synergy_pay_system','accounting_authority':'Shtenco/synergy_financial_os','profit_recognition':'NOT_PERFORMED','authorization_consumption':'CONSUMED_BY_BATCH_ATTEMPT','execution_authority':'NONE'}; receipt['receipt_digest']=canonical_json_digest(receipt)
 util={'schema':'distribution.utilization/v1','utilization_id':'util','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'planned_total_amount':'10','settled_total_amount':'10','receipt_digests':[receipt['receipt_digest']],'settled_beneficiary_ids':['a'],'failed_beneficiary_ids':[],'status':'FULLY_SETTLED','finalized_at':'2026-08-20T04:06:00Z','authorization_consumption':'CONSUMED','authority':'METAPAY_DISTRIBUTION_UTILIZATION','accounting_authority':'REFERENCE_ONLY','execution_authority':'NONE'}; util['digest']=canonical_json_digest(util)
 reversal={'schema':'distribution.settlement-reversal/v1','reversal_id':'reversal-a','original_distribution_receipt_digest':receipt['receipt_digest'],'original_settlement_id':'settlement-a','distribution_attempt_digest':attempt['digest'],'distribution_execution_ticket_digest':ticket.digest,'distribution_authorization_digest':auth.digest,'distribution_plan_digest':plan.digest,'beneficiary_set_digest':plan.beneficiary_set_digest,'beneficiary_id':'a','payment_idempotency_key':'dist-a-001','payer_id':'treasury-usd','payee_id':'bank-a','asset':'USD','amount':'10','payer_borne_reversal_fee':'0','status':'REVERSED_CONFIRMED','observed_at':'2026-08-20T05:00:00Z','external_references':['bank-a-reversed'],'reversal_evidence_digest':'16'*32,'authority':'SETTLEMENT_REVERSAL_EVIDENCE_ONLY','settlement_authority':'Shtenco/synergy_pay_system','accounting_authority':'Shtenco/synergy_financial_os','authorization_consumption':'REMAINS_CONSUMED','profit_recognition':'NOT_PERFORMED','execution_authority':'NONE'}; reversal['digest']=canonical_json_digest(reversal)
 return plan,auth,ticket,attempt,receipt,util,reversal

def accounts(): return DistributionAccountingAccountsV1('cash','equity','31'*32)

def test_later_provider_reversal_restores_cash_equity_without_realized_pnl():
 l=ledger(); plan,auth,ticket,attempt,receipt,util,reversal=objects()
 original_decision,original_entry=post_settled_owner_distribution_v1(l,decision_id='dist-accounting',event_id='dist-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=(receipt,),accounts=accounts(),decided_at=dt(4,10))
 assert l.balance('cash')==Decimal('90') and l.balance('equity')==Decimal('90')
 reversal_decision,reversal_entry=post_distribution_settlement_reversal_canonical_v1(l,decision_id='reversal-accounting',event_id='reversal-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original_decision,settlement_reversal_payload=reversal,accounts=accounts(),decided_at=dt(5,5))
 assert reversal_entry.flow_type==FlowType.EXTERNAL_CAPITAL
 assert reversal_decision.reversal_amount==Decimal('10')
 assert l.balance('cash')==Decimal('100') and l.balance('equity')==Decimal('100')
 policy={'CASH':ValuationRule('CASH',Decimal('1'),Decimal('1'),Decimal('1'),'BANK_BALANCE')}
 assert realized_external_pnl_since(l,1)==Decimal('0')
 assert net_new_capital_since(l,1,policy)==Decimal('0')
 jsonschema.Draft202012Validator(SCHEMA).validate(reversal_decision.to_dict())
 assert verify_distribution_reversal_accounting_decision_payload_v1(reversal_decision.to_dict()).digest==reversal_decision.digest

def test_same_original_receipt_cannot_be_reversed_twice_in_financial_ledger():
 l=ledger(); plan,auth,ticket,attempt,receipt,util,reversal=objects()
 original_decision,_=post_settled_owner_distribution_v1(l,decision_id='dist-accounting',event_id='dist-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=(receipt,),accounts=accounts(),decided_at=dt(4,10))
 post_distribution_settlement_reversal_canonical_v1(l,decision_id='r1',event_id='reversal-entry-1',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original_decision,settlement_reversal_payload=reversal,accounts=accounts(),decided_at=dt(5,5))
 second=dict(reversal); second['reversal_id']='reversal-a-2'; second['reversal_evidence_digest']='17'*32; second.pop('digest'); second['digest']=canonical_json_digest(second)
 with pytest.raises(DistributionReversalAccountingV1Error,match='not postable'):
  post_distribution_settlement_reversal_canonical_v1(l,decision_id='r2',event_id='reversal-entry-2',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original_decision,settlement_reversal_payload=second,accounts=accounts(),decided_at=dt(5,6))

def test_reversal_without_prior_canonical_distribution_entry_is_rejected():
 l=ledger(); plan,auth,ticket,attempt,receipt,util,reversal=objects()
 from sinergy_financial_os.distribution_accounting_v1 import DistributionAccountingDecisionV1
 fake=DistributionAccountingDecisionV1('fake',plan.digest,auth.digest,ticket.digest,attempt['digest'],util['digest'],canonical_json_digest([receipt['receipt_digest']]),plan.affected_period_id,plan.source_account_id,'cash','equity','31'*32,'USD',Decimal('10'),'POSTABLE',(),dt(4,10))
 with pytest.raises(DistributionReversalAccountingV1Error,match='must exist exactly once'):
  post_distribution_settlement_reversal_canonical_v1(l,decision_id='no-original',event_id='reversal-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=fake,settlement_reversal_payload=reversal,accounts=accounts(),decided_at=dt(5,5))

def test_wrong_settlement_authority_is_blocked_before_accounting():
 l=ledger(); plan,auth,ticket,attempt,receipt,util,reversal=objects()
 original_decision,_=post_settled_owner_distribution_v1(l,decision_id='dist-accounting',event_id='dist-entry',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,receipt_payloads=(receipt,),accounts=accounts(),decided_at=dt(4,10))
 bad=dict(reversal); bad['settlement_authority']='attacker/repo'; bad.pop('digest'); bad['digest']=canonical_json_digest(bad)
 with pytest.raises(DistributionReversalAccountingV1Error,match='MetaPay settlement authority'):
  post_distribution_settlement_reversal_canonical_v1(l,decision_id='bad-authority',event_id='bad-reversal',plan=plan,authorization=auth,ticket=ticket,attempt_payload=attempt,utilization_payload=util,original_receipt_payloads=(receipt,),original_accounting_decision=original_decision,settlement_reversal_payload=bad,accounts=accounts(),decided_at=dt(5,5))
