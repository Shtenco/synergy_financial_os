from __future__ import annotations

import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.authorized_revenue_posting_v2 import post_external_revenue_from_evidence_v2
from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.economic_cycle_trace_v4 import CycleReferenceV4, EconomicCycleTraceV4, verify_complete_trace_artifacts_v4
from sinergy_financial_os.ledger_event_export_v1 import export_reporting_entry_as_ledger_event_v1, ledger_event_v1_digest
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, ReportingAccountSpec, ReportingLedger
from sinergy_financial_os.revenue_posting_v2 import RevenuePostingAccountsV2, RevenuePostingV2Error
from sinergy_financial_os.revenue_recognition_v2 import RevenueRecognitionRequestV2, evaluate_revenue_recognition_v2

ROOT=Path(__file__).resolve().parents[1]
AUTH=ROOT/'fixtures/conformance/capital_authorization_v2_canonical.json'
FUNDING=ROOT/'fixtures/conformance/settlement_receipt_v2_funding.json'
REVENUE=ROOT/'fixtures/conformance/settlement_receipt_v2_revenue.json'
RECOGNITION=ROOT/'fixtures/conformance/revenue_recognition_v2_canonical.json'
LEDGER_EVENT=ROOT/'fixtures/conformance/ledger_event_v1_recognized_revenue.json'
TRACE=ROOT/'fixtures/conformance/economic_cycle_trace_v4_complete.json'
TRACE_SCHEMA=ROOT/'schemas/economic_cycle_trace_v4.schema.json'

def load(path): return json.loads(path.read_text(encoding='utf-8'))
def dt(v): return datetime.fromisoformat(v.replace('Z','+00:00'))

def authorization():
    p=load(AUTH)
    return CapitalAuthorizationV2(
        authorization_id=p['authorization_id'],project_id=p['project_id'],decision=p['decision'],decision_authority=p['decision_authority'],funding_asset=p['funding_asset'],approved_amount=Decimal(p['approved_amount']),funding_source_id=p['funding_source_id'],funding_destination_id=p['funding_destination_id'],payment_idempotency_key=p['payment_idempotency_key'],payment_purpose=p['payment_purpose'],usage_policy=p['usage_policy'],screening_digest=p['screening_digest'],financial_snapshot_digest=p['financial_snapshot_digest'],financial_snapshot_sequence=p['financial_snapshot_sequence'],valuation_policy_digest=p['valuation_policy_digest'],requirement_registry_digest=p['requirement_registry_digest'],decision_evidence_digest=p['decision_evidence_digest'],approver_policy_digest=p['approver_policy_digest'],notes_digest=p['notes_digest'],decided_at=dt(p['decided_at']),expires_at=dt(p['expires_at']),execution_authority=p['execution_authority'],ai_authority=p['ai_authority'])

def request(**changes):
    values=dict(recognition_id='revrec-001',project_id='project-001',project_evidence_digest='66'*32,counterparty_id='external-customer-001',counterparty_relation='EXTERNAL_NON_RELATED',counterparty_evidence_digest='11'*32,revenue_destination_id='project-001-revenue-account',contract_digest='22'*32,invoice_digest='33'*32,invoice_reporting_amount=Decimal('125'),delivery_evidence_digest='44'*32,performance_state='SATISFIED',dispute_state='CLEAR',reporting_currency='USDC',fx_rate_to_reporting=Decimal('1'),tax_reporting_amount=Decimal('5'),refund_reserve_reporting_amount=Decimal('2'),accounting_policy_digest='55'*32,recognized_at=dt('2026-08-19T10:30:00Z'))
    values.update(changes);return RevenueRecognitionRequestV2(**values)

def ledger():
    l=ReportingLedger('USDC')
    l.register_account(ReportingAccountSpec('cash','External cash',AccountClass.ASSET,ConsolidationClass.EXTERNAL,'CASH'))
    l.register_account(ReportingAccountSpec('revenue','External revenue',AccountClass.REVENUE,ConsolidationClass.EXTERNAL,'REVENUE'))
    l.register_account(ReportingAccountSpec('tax','Tax payable',AccountClass.LIABILITY,ConsolidationClass.EXTERNAL,'LIABILITY',immediate_liability=True))
    l.register_account(ReportingAccountSpec('refund','Refund reserve',AccountClass.LIABILITY,ConsolidationClass.EXTERNAL,'LIABILITY',immediate_liability=True))
    return l

def accounts(): return RevenuePostingAccountsV2('cash','revenue','tax','refund')

def trace_from_fixture():
    p=load(TRACE)
    refs=tuple(CycleReferenceV4(r['phase'],r['schema_id'],r['digest'],r['source_repository'],r['subject_id'],dt(r['observed_at'])) for r in p['references'])
    t=EconomicCycleTraceV4(p['cycle_id'],p['household_or_funding_subject'],p['project_id'],refs,authority=p['authority'],profit_recognition=p['profit_recognition'],execution_authority=p['execution_authority'])
    assert t.digest==p['digest'];return t

def test_recognition_posting_ledger_event_and_trace_v4_are_one_exact_chain():
    auth=authorization(); req=request(); revenue=load(REVENUE); funding=load(FUNDING)
    decision=evaluate_revenue_recognition_v2(revenue,auth,req)
    assert decision.to_dict()==load(RECOGNITION)
    l=ledger(); posted_decision,entry=post_external_revenue_from_evidence_v2(l,receipt_payload=revenue,authorization=auth,recognition_request=req,accounts=accounts(),event_id='revenue-event-001')
    assert posted_decision.digest==decision.digest
    event=export_reporting_entry_as_ledger_event_v1(entry,l,effective_at=req.recognized_at,evidence_class='PROJECT')
    assert event==load(LEDGER_EVENT)
    assert ledger_event_v1_digest(event)=='1dcf75a6084615c4a8c3dcdcf04a820ee25311900a7a4f5ade858e6711263771'
    trace=trace_from_fixture();jsonschema.Draft202012Validator(load(TRACE_SCHEMA)).validate(trace.to_dict())
    review=verify_complete_trace_artifacts_v4(trace,authorization=auth,funding_receipt=funding,revenue_receipt=revenue,project_evidence_digest='66'*32,recognition=decision,ledger_event=event)
    assert review.verified is True
    assert review.blockers==()
    assert review.recognized_reporting_amount=='118'
    assert review.accounting_reference_only is True
    assert review.execution_authority=='NONE'

def test_canonical_posting_recomputes_evidence_and_rejects_deferred_revenue():
    with pytest.raises(RevenuePostingV2Error):
        post_external_revenue_from_evidence_v2(ledger(),receipt_payload=load(REVENUE),authorization=authorization(),recognition_request=request(performance_state='PARTIAL'),accounts=accounts(),event_id='should-not-post')

def test_rehashed_ledger_event_and_repointed_trace_cannot_break_recognition_link():
    auth=authorization();decision=evaluate_revenue_recognition_v2(load(REVENUE),auth,request())
    event=copy.deepcopy(load(LEDGER_EVENT));event['evidence_digest']='99'*32
    fake_event_digest=ledger_event_v1_digest(event)
    p=load(TRACE)
    for ref in p['references']:
        if ref['phase']=='LEDGER_EVENT': ref['digest']=fake_event_digest
    p.pop('digest',None)
    import hashlib
    p['digest']=hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    refs=tuple(CycleReferenceV4(r['phase'],r['schema_id'],r['digest'],r['source_repository'],r['subject_id'],dt(r['observed_at'])) for r in p['references'])
    trace=EconomicCycleTraceV4(p['cycle_id'],p['household_or_funding_subject'],p['project_id'],refs,authority=p['authority'],profit_recognition=p['profit_recognition'],execution_authority=p['execution_authority'])
    review=verify_complete_trace_artifacts_v4(trace,authorization=auth,funding_receipt=load(FUNDING),revenue_receipt=load(REVENUE),project_evidence_digest='66'*32,recognition=decision,ledger_event=event)
    assert review.verified is False
    assert 'LEDGER_RECOGNITION_EVIDENCE_MISMATCH' in review.blockers
