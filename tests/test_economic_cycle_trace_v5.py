from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema

from sinergy_financial_os.capital_authorization_v2 import CapitalAuthorizationV2
from sinergy_financial_os.economic_cycle_trace_v5 import (
    CycleReferenceV5,
    EconomicCycleTraceV5,
    verify_complete_trace_artifacts_v5,
)
from sinergy_financial_os.revenue_recognition_v2 import RevenueRecognitionDecisionV2

ROOT=Path(__file__).resolve().parents[1]
AUTH=ROOT/'fixtures/conformance/capital_authorization_v2_canonical.json'
FUNDING=ROOT/'fixtures/conformance/settlement_receipt_v2_funding.json'
REVENUE=ROOT/'fixtures/conformance/settlement_receipt_v2_revenue.json'
RECOG=ROOT/'fixtures/conformance/revenue_recognition_v2_canonical.json'
EVENT=ROOT/'fixtures/conformance/ledger_event_v1_recognized_revenue.json'
TRACE=ROOT/'fixtures/conformance/economic_cycle_trace_v5_complete.json'
SCHEMA=ROOT/'schemas/economic_cycle_trace_v5.schema.json'

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def dt(v): return datetime.fromisoformat(v.replace('Z','+00:00'))
def auth():
 p=load(AUTH);return CapitalAuthorizationV2(authorization_id=p['authorization_id'],project_id=p['project_id'],decision=p['decision'],decision_authority=p['decision_authority'],funding_asset=p['funding_asset'],approved_amount=Decimal(p['approved_amount']),funding_source_id=p['funding_source_id'],funding_destination_id=p['funding_destination_id'],payment_idempotency_key=p['payment_idempotency_key'],payment_purpose=p['payment_purpose'],usage_policy=p['usage_policy'],screening_digest=p['screening_digest'],financial_snapshot_digest=p['financial_snapshot_digest'],financial_snapshot_sequence=p['financial_snapshot_sequence'],valuation_policy_digest=p['valuation_policy_digest'],requirement_registry_digest=p['requirement_registry_digest'],decision_evidence_digest=p['decision_evidence_digest'],approver_policy_digest=p['approver_policy_digest'],notes_digest=p['notes_digest'],decided_at=dt(p['decided_at']),expires_at=dt(p['expires_at']),execution_authority=p['execution_authority'],ai_authority=p['ai_authority'])
def recognition():
 p=load(RECOG);return RevenueRecognitionDecisionV2(recognition_id=p['recognition_id'],project_id=p['project_id'],decision=p['decision'],settlement_receipt_digest=p['settlement_receipt_digest'],capital_authorization_digest=p['capital_authorization_digest'],project_evidence_digest=p['project_evidence_digest'],counterparty_id=p['counterparty_id'],counterparty_relation=p['counterparty_relation'],counterparty_evidence_digest=p['counterparty_evidence_digest'],revenue_destination_id=p['revenue_destination_id'],contract_digest=p['contract_digest'],invoice_digest=p['invoice_digest'],invoice_reporting_amount=Decimal(p['invoice_reporting_amount']),delivery_evidence_digest=p['delivery_evidence_digest'],accounting_policy_digest=p['accounting_policy_digest'],settlement_asset=p['settlement_asset'],settlement_amount=Decimal(p['settlement_amount']),reporting_currency=p['reporting_currency'],fx_rate_to_reporting=Decimal(p['fx_rate_to_reporting']),gross_reporting_amount=Decimal(p['gross_reporting_amount']),tax_reporting_amount=Decimal(p['tax_reporting_amount']),refund_reserve_reporting_amount=Decimal(p['refund_reserve_reporting_amount']),recognized_reporting_amount=Decimal(p['recognized_reporting_amount']),performance_state=p['performance_state'],dispute_state=p['dispute_state'],recognized_at=dt(p['recognized_at']),blockers=tuple(p['blockers']),fx_evidence_digest=p['fx_evidence_digest'],accounting_authority=p['accounting_authority'],ledger_posting_authority=p['ledger_posting_authority'],ai_authority=p['ai_authority'])
def trace(payload=None):
 p=payload or load(TRACE);refs=tuple(CycleReferenceV5(r['phase'],r['schema_id'],r['digest'],r['source_repository'],r['subject_id'],dt(r['observed_at'])) for r in p['references']);return EconomicCycleTraceV5(p['cycle_id'],p['household_or_funding_subject'],p['project_id'],refs,authority=p['authority'],profit_recognition=p['profit_recognition'],execution_authority=p['execution_authority'],trust_finalization=p['trust_finalization'])

def test_v5_is_non_circular_and_exact():
 p=load(TRACE);t=trace(p);jsonschema.Draft202012Validator(load(SCHEMA)).validate(p)
 assert t.digest==p['digest']=='0182bbf05b7dc11690adf899bd6e3b353df47b3e2146c3629669693167dacfca'
 assert 'TRUST_COMMITMENT' not in [r.phase for r in t.references]
 assert t.trust_finalization=='EXTERNAL_COMMITMENT_REQUIRED'

def test_v5_verifies_accounting_graph_before_external_commitment():
 review=verify_complete_trace_artifacts_v5(trace(),authorization=auth(),funding_receipt=load(FUNDING),revenue_receipt=load(REVENUE),project_evidence_digest='66'*32,recognition=recognition(),ledger_event=load(EVENT))
 assert review.verified is True and review.blockers==()
 assert review.external_commitment_required is True and review.execution_authority=='NONE'

def test_rehashed_trace_cannot_hide_wrong_ledger_evidence_link():
 event=copy.deepcopy(load(EVENT));event['evidence_digest']='99'*32
 p=copy.deepcopy(load(TRACE));event_digest=hashlib.sha256(json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 next(r for r in p['references'] if r['phase']=='LEDGER_EVENT')['digest']=event_digest;p.pop('digest',None);p['digest']=hashlib.sha256(json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 review=verify_complete_trace_artifacts_v5(trace(p),authorization=auth(),funding_receipt=load(FUNDING),revenue_receipt=load(REVENUE),project_evidence_digest='66'*32,recognition=recognition(),ledger_event=event)
 assert review.verified is False and 'LEDGER_RECOGNITION_EVIDENCE_MISMATCH' in review.blockers
