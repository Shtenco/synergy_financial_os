from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os.accounting_close_v2 import (
    build_accounting_close_v2,
    build_ledger_inclusion_proof_v2,
    verify_accounting_close_v2,
)
from sinergy_financial_os.accounting_period_v1 import (
    AccountingPeriodV1,
    build_period_close_v1,
)
from sinergy_financial_os.authorized_revenue_reversal_v1 import (
    AuthorizedRevenueReversalV1Error,
    RevenueReversalAccountsV1,
    post_authorized_revenue_reversal_v1,
)
from sinergy_financial_os.ledger_event_v2 import (
    export_reporting_entry_as_ledger_event_v2,
    ledger_event_v2_digest,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.revenue_posting_v2 import (
    RevenuePostingAccountsV2,
    post_recognized_external_revenue_v2,
)
from sinergy_financial_os.revenue_recognition_v2 import RevenueRecognitionDecisionV2
from sinergy_financial_os.revenue_reversal_v1 import (
    RevenueReversalAuthorizationV1,
    RevenueReversalV1Error,
    verify_revenue_reversal_context_v1,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule

ROOT=Path(__file__).resolve().parents[1]
RECOGNITION=ROOT/'fixtures/conformance/revenue_recognition_v2_canonical.json'
REQ='77'*32
POLICY='55'*32

def dt(v): return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(UTC)
def load(p): return json.loads(p.read_text(encoding='utf-8'))

def recognition():
 p=load(RECOGNITION)
 return RevenueRecognitionDecisionV2(
  recognition_id=p['recognition_id'],project_id=p['project_id'],decision=p['decision'],settlement_receipt_digest=p['settlement_receipt_digest'],capital_authorization_digest=p['capital_authorization_digest'],project_evidence_digest=p['project_evidence_digest'],counterparty_id=p['counterparty_id'],counterparty_relation=p['counterparty_relation'],counterparty_evidence_digest=p['counterparty_evidence_digest'],revenue_destination_id=p['revenue_destination_id'],contract_digest=p['contract_digest'],invoice_digest=p['invoice_digest'],invoice_reporting_amount=Decimal(p['invoice_reporting_amount']),delivery_evidence_digest=p['delivery_evidence_digest'],accounting_policy_digest=p['accounting_policy_digest'],settlement_asset=p['settlement_asset'],settlement_amount=Decimal(p['settlement_amount']),reporting_currency=p['reporting_currency'],fx_rate_to_reporting=Decimal(p['fx_rate_to_reporting']),gross_reporting_amount=Decimal(p['gross_reporting_amount']),tax_reporting_amount=Decimal(p['tax_reporting_amount']),refund_reserve_reporting_amount=Decimal(p['refund_reserve_reporting_amount']),recognized_reporting_amount=Decimal(p['recognized_reporting_amount']),performance_state=p['performance_state'],dispute_state=p['dispute_state'],recognized_at=dt(p['recognized_at']),blockers=tuple(p['blockers']),fx_evidence_digest=p['fx_evidence_digest'],accounting_authority=p['accounting_authority'],ledger_posting_authority=p['ledger_posting_authority'],ai_authority=p['ai_authority'])

def book():
 x=ReportingLedger('USDC')
 x.register_account(ReportingAccountSpec('cash','External cash',AccountClass.ASSET,ConsolidationClass.EXTERNAL,'CASH'))
 x.register_account(ReportingAccountSpec('revenue','External revenue',AccountClass.REVENUE,ConsolidationClass.EXTERNAL,'REVENUE'))
 x.register_account(ReportingAccountSpec('tax','Tax payable',AccountClass.LIABILITY,ConsolidationClass.EXTERNAL,'LIABILITY',immediate_liability=True))
 x.register_account(ReportingAccountSpec('refund','Refund reserve',AccountClass.LIABILITY,ConsolidationClass.EXTERNAL,'LIABILITY',immediate_liability=True))
 return x

def policy(): return ValuationPolicy('cycle-policy-v1','USDC',dt('2026-08-19T10:29:00Z'),(ValuationRule('CASH',Decimal('1'),Decimal('1'),Decimal('1'),'BANK_BALANCE'),))
def horizons(amount): return (LiquidityHorizonState(1,amount,Decimal('0')),LiquidityHorizonState(4,amount,Decimal('0')),LiquidityHorizonState(8,amount,Decimal('0')))

def original_closed_period():
 ledger=book();rec=recognition();entry=post_recognized_external_revenue_v2(ledger,rec,RevenuePostingAccountsV2('cash','revenue','tax','refund'),event_id='revenue-event-001');event=export_reporting_entry_as_ledger_event_v2(entry,ledger,effective_at=rec.recognized_at,evidence_class='PROJECT')
 snap=capture_financial_snapshot_v2(ledger,policy(),as_of=dt('2026-08-19T11:00:00Z'),accounting_perimeter='SINERGY_CONSOLIDATED',liquidity_horizons=horizons(Decimal('125')),required_hard_nav_buffer=Decimal('0'),policy_mode='NORMAL')
 close=build_accounting_close_v2([event],snap.to_dict(),close_id='close-period-n',closed_at=dt('2026-08-19T11:01:00Z'),requirement_registry_digest=REQ)
 proof=build_ledger_inclusion_proof_v2([event],snap.to_dict(),event_index=0,close=close)
 period=AccountingPeriodV1('period-n',dt('2026-08-19T00:00:00Z'),dt('2026-08-19T11:00:00Z'),'SINERGY_CONSOLIDATED','USDC',POLICY,REQ)
 period_close=build_period_close_v1(period,close,financial_snapshot=snap.to_dict(),sealed_ledger_events=[event],closed_at=dt('2026-08-19T11:02:00Z'))
 return ledger,rec,entry,event,snap,close,proof,period,period_close

def successor_and_auth(ctx):
 ledger,rec,entry,event,snap,close,proof,period,period_close=ctx
 successor=AccountingPeriodV1('period-n-plus-1',dt('2026-08-19T11:00:00Z'),dt('2026-08-19T13:00:00Z'),'SINERGY_CONSOLIDATED','USDC',POLICY,REQ,period_close.digest)
 auth=RevenueReversalAuthorizationV1('reversal-auth-001',successor.period_id,rec.project_id,'CHARGEBACK',period_close.digest,close.digest,rec.digest,ledger_event_v2_digest(event),entry.digest,'99'*32,'aa'*32,POLICY,'MULTISIG_GOVERNANCE',dt('2026-08-19T11:20:00Z'),dt('2026-08-19T11:30:00Z'))
 return successor,auth

def reversal_accounts(): return RevenueReversalAccountsV1('cash','revenue','tax','refund')

def test_full_closed_period_chargeback_is_new_entry_and_zeroes_hardnav_without_mutating_close_n():
 ctx=original_closed_period();ledger,rec,original_entry,original_event,snap1,close1,proof1,period1,period_close1=ctx;successor,auth=successor_and_auth(ctx);close1_digest=close1.digest;event1_digest=original_entry.digest
 reversal=post_authorized_revenue_reversal_v1(ledger,auth,successor,period_close1,close1,rec,original_event,proof1,reversal_accounts(),event_id='reversal-event-001')
 assert reversal.sequence==2;assert reversal.flow_type==FlowType.EXTERNAL_EXPENSE;assert reversal.evidence_digest==auth.digest;assert original_entry.digest==event1_digest;assert close1.digest==close1_digest
 assert ledger.balance('cash')==Decimal('0');assert ledger.balance('revenue')==Decimal('0');assert ledger.balance('tax')==Decimal('0');assert ledger.balance('refund')==Decimal('0')
 reversal_event=export_reporting_entry_as_ledger_event_v2(reversal,ledger,effective_at=auth.effective_at,evidence_class='PROJECT')
 snap2=capture_financial_snapshot_v2(ledger,policy(),as_of=dt('2026-08-19T13:00:00Z'),accounting_perimeter='SINERGY_CONSOLIDATED',liquidity_horizons=horizons(Decimal('0')),previous_snapshot=snap1,required_hard_nav_buffer=Decimal('0'),policy_mode='DEFENSE')
 assert snap1.hard_nav==Decimal('118');assert snap2.hard_nav==Decimal('0');assert snap2.realized_external_revenue==Decimal('0');assert snap2.realized_external_pnl==Decimal('-118');assert snap2.period_profit_budget==Decimal('0');assert snap2.distribution_capacity==Decimal('0')
 close2=build_accounting_close_v2([original_event,reversal_event],snap2.to_dict(),close_id='close-period-n-plus-1',closed_at=dt('2026-08-19T13:01:00Z'),requirement_registry_digest=REQ);assert verify_accounting_close_v2([original_event,reversal_event],snap2.to_dict(),close2)
 period_close2=build_period_close_v1(successor,close2,financial_snapshot=snap2.to_dict(),sealed_ledger_events=[original_event,reversal_event],adjustment_authorization_digests=(auth.digest,),closed_at=dt('2026-08-19T13:02:00Z'))
 assert period_close2.previous_period_close_digest==period_close1.digest;assert period_close2.accounting_close_digest==close2.digest;assert period_close2.adjustment_authorization_digests==(auth.digest,);assert period_close1.digest!=period_close2.digest

def test_period_close_refuses_to_claim_adjustment_not_in_sealed_prefix():
 ctx=original_closed_period();ledger,rec,_,event,snap1,close1,proof,_,period_close1=ctx;successor,auth=successor_and_auth(ctx)
 # No reversal is posted. A new close over the old prefix cannot claim the authorization.
 snap2=capture_financial_snapshot_v2(ledger,policy(),as_of=dt('2026-08-19T13:00:00Z'),accounting_perimeter='SINERGY_CONSOLIDATED',liquidity_horizons=horizons(Decimal('125')),previous_snapshot=snap1,required_hard_nav_buffer=Decimal('0'),policy_mode='NORMAL')
 close2=build_accounting_close_v2([event],snap2.to_dict(),close_id='close-without-adjustment',closed_at=dt('2026-08-19T13:01:00Z'),requirement_registry_digest=REQ)
 with pytest.raises(Exception,match='adjustment authorization must appear exactly once'):
  build_period_close_v1(successor,close2,financial_snapshot=snap2.to_dict(),sealed_ledger_events=[event],adjustment_authorization_digests=(auth.digest,),closed_at=dt('2026-08-19T13:02:00Z'))

def test_reversal_replay_is_blocked_after_first_full_reversal():
 ctx=original_closed_period();ledger,rec,_,event,_,close,proof,_,period_close=ctx;successor,auth=successor_and_auth(ctx)
 post_authorized_revenue_reversal_v1(ledger,auth,successor,period_close,close,rec,event,proof,reversal_accounts(),event_id='reversal-event-001')
 with pytest.raises(AuthorizedRevenueReversalV1Error,match='balance is below original component'):
  post_authorized_revenue_reversal_v1(ledger,auth,successor,period_close,close,rec,event,proof,reversal_accounts(),event_id='reversal-event-002')

def test_full_reversal_refuses_to_guess_when_tax_component_was_already_consumed():
 ctx=original_closed_period();ledger,rec,_,event,_,close,proof,_,period_close=ctx;successor,auth=successor_and_auth(ctx)
 ledger.post(event_id='tax-remittance',reference='tax-remittance-001',flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine('tax',debit=Decimal('5')),ReportingLine('cash',credit=Decimal('5'))),evidence_digest='bb'*32,metadata={'economic_class':'TAX_REMITTANCE'})
 with pytest.raises(AuthorizedRevenueReversalV1Error,match='tax balance is below original component'):
  post_authorized_revenue_reversal_v1(ledger,auth,successor,period_close,close,rec,event,proof,reversal_accounts(),event_id='reversal-event-001')

def test_v1_rejects_partial_scope_and_non_successor_period():
 ctx=original_closed_period();_,rec,entry,event,_,close,_,_,period_close=ctx;successor,auth=successor_and_auth(ctx)
 with pytest.raises(RevenueReversalV1Error,match='full reversal only'):
  RevenueReversalAuthorizationV1('partial',successor.period_id,rec.project_id,'REFUND',period_close.digest,close.digest,rec.digest,ledger_event_v2_digest(event),entry.digest,'99'*32,'aa'*32,POLICY,'HUMAN_COMMITTEE',dt('2026-08-19T11:20:00Z'),dt('2026-08-19T11:30:00Z'),adjustment_scope='PARTIAL')
 wrong=AccountingPeriodV1('wrong',dt('2026-08-19T11:00:00Z'),dt('2026-08-19T13:00:00Z'),'SINERGY_CONSOLIDATED','USDC',POLICY,REQ,'cc'*32)
 with pytest.raises(RevenueReversalV1Error,match='directly succeed'):
  verify_revenue_reversal_context_v1(auth,wrong,period_close,close,rec,event,ctx[6])
