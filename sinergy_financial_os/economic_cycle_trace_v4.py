from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .capital_authorization_v2 import CapitalAuthorizationV2
from .core import AccountingInvariantError
from .ledger_event_export_v1 import ledger_event_v1_digest
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2
from .settlement_receipt_v2 import (
    verify_funding_receipt_against_authorization_v2,
    verify_revenue_receipt_lineage_v2,
    verify_settlement_receipt_v2_integrity,
)

SCHEMA = "economic.cycle-trace/v4"
HEX = frozenset("0123456789abcdef")
PHASE_CONTRACTS_V4 = (
    ("FUNDING_STATE", "maturity.snapshot/v1", "Shtenco/synergy_matrix_sota"),
    ("PROJECT_PROPOSAL", "project.proposal/v2", "Shtenco/synergy_eurasian"),
    ("PROJECT_SCREENING", "project.screening/v1", "Shtenco/synergy_financial_os"),
    ("CAPITAL_AUTHORIZATION", "capital.authorization/v2", "Shtenco/synergy_financial_os"),
    ("FUNDING_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("PROJECT_EVIDENCE", "project.evidence/v1", "Shtenco/synergy_eurasian"),
    ("REVENUE_SETTLEMENT", "settlement.receipt/v2", "Shtenco/synergy_pay_system"),
    ("REVENUE_RECOGNITION", "revenue.recognition/v2", "Shtenco/synergy_financial_os"),
    ("LEDGER_EVENT", "ledger.event/v1", "Shtenco/synergy_financial_os"),
    ("ACCOUNTING_SNAPSHOT", "financial.snapshot/v2", "Shtenco/synergy_financial_os"),
    ("TRUST_COMMITMENT", "commitment.envelope/v3", "Shtenco/synergy_ai_blockchain"),
)
INDEX = {p: i for i, (p, _, _) in enumerate(PHASE_CONTRACTS_V4)}
SCHEMA_BY_PHASE = {p: s for p, s, _ in PHASE_CONTRACTS_V4}
SOURCE_BY_PHASE = {p: r for p, _, r in PHASE_CONTRACTS_V4}
PROJECT_PHASES = frozenset({"PROJECT_PROPOSAL","PROJECT_SCREENING","CAPITAL_AUTHORIZATION","PROJECT_EVIDENCE","REVENUE_RECOGNITION"})

class EconomicCycleTraceV4Error(AccountingInvariantError):
    pass

def _text(v: Any, n: str) -> str:
    if not isinstance(v, str) or not v.strip(): raise EconomicCycleTraceV4Error(f"{n} is required")
    return v.strip()
def _hex(v: Any, n: str) -> str:
    x=_text(v,n).lower()
    if len(x)!=64 or any(c not in HEX for c in x): raise EconomicCycleTraceV4Error(f"{n} must be hex64")
    return x
def _time(v: datetime,n:str)->datetime:
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None: raise EconomicCycleTraceV4Error(f"{n} must be timezone-aware")
    return v.astimezone(UTC)
def _time_text(v: str,n:str)->datetime:
    if not isinstance(v,str) or not v.endswith('Z'): raise EconomicCycleTraceV4Error(f"{n} must be UTC Z")
    try:return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(UTC)
    except ValueError as exc: raise EconomicCycleTraceV4Error(f"{n} invalid") from exc
def _digest(p: Mapping[str,Any])->str:
    return hashlib.sha256(json.dumps(dict(p),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class CycleReferenceV4:
    phase:str; schema_id:str; digest:str; source_repository:str; subject_id:str; observed_at:datetime
    def __post_init__(self)->None:
        p=_text(self.phase,'phase').upper()
        if p not in INDEX: raise EconomicCycleTraceV4Error(f"unsupported phase {p}")
        if self.schema_id!=SCHEMA_BY_PHASE[p] or self.source_repository!=SOURCE_BY_PHASE[p]: raise EconomicCycleTraceV4Error(f"{p} schema/source mismatch")
        object.__setattr__(self,'phase',p);object.__setattr__(self,'digest',_hex(self.digest,'digest'));object.__setattr__(self,'subject_id',_text(self.subject_id,'subject_id'));object.__setattr__(self,'observed_at',_time(self.observed_at,'observed_at'))
    def to_dict(self)->dict[str,str]:
        return {'phase':self.phase,'schema_id':self.schema_id,'digest':self.digest,'source_repository':self.source_repository,'subject_id':self.subject_id,'observed_at':self.observed_at.isoformat().replace('+00:00','Z')}

@dataclass(frozen=True)
class EconomicCycleTraceV4:
    cycle_id:str; household_or_funding_subject:str; project_id:str; references:tuple[CycleReferenceV4,...]
    authority:str='PROVENANCE_ONLY'; profit_recognition:str='REFERENCE_ONLY'; execution_authority:str='NONE'
    def __post_init__(self)->None:
        cycle=_text(self.cycle_id,'cycle_id');funding=_text(self.household_or_funding_subject,'household_or_funding_subject');project=_text(self.project_id,'project_id')
        if self.authority!='PROVENANCE_ONLY' or self.profit_recognition!='REFERENCE_ONLY' or self.execution_authority!='NONE': raise EconomicCycleTraceV4Error('trace authority boundary violated')
        refs=tuple(self.references)
        if not refs or any(not isinstance(r,CycleReferenceV4) for r in refs): raise EconomicCycleTraceV4Error('references required')
        phases=[r.phase for r in refs]; expected=[p for p,_,_ in PHASE_CONTRACTS_V4[:len(refs)]]
        if phases!=expected or len(phases)!=len(set(phases)): raise EconomicCycleTraceV4Error('trace must be strict unique causal prefix')
        times=[r.observed_at for r in refs]
        if times!=sorted(times): raise EconomicCycleTraceV4Error('trace time cannot move backwards')
        if refs[0].subject_id!=funding: raise EconomicCycleTraceV4Error('funding subject mismatch')
        for r in refs:
            if r.phase in PROJECT_PHASES and r.subject_id!=project: raise EconomicCycleTraceV4Error(f"{r.phase} project mismatch")
        object.__setattr__(self,'cycle_id',cycle);object.__setattr__(self,'household_or_funding_subject',funding);object.__setattr__(self,'project_id',project);object.__setattr__(self,'references',refs)
    @property
    def complete(self)->bool:return len(self.references)==len(PHASE_CONTRACTS_V4)
    @property
    def status(self)->str:return 'TRACE_COMPLETE' if self.complete else 'TRACE_PARTIAL'
    @property
    def missing_phases(self)->tuple[str,...]:return tuple(p for p,_,_ in PHASE_CONTRACTS_V4[len(self.references):])
    def reference(self,phase:str)->CycleReferenceV4:
        p=phase.upper().strip()
        for r in self.references:
            if r.phase==p:return r
        raise EconomicCycleTraceV4Error(f"missing phase {p}")
    def to_dict(self,*,include_digest:bool=True)->dict[str,Any]:
        p={'schema':SCHEMA,'cycle_id':self.cycle_id,'household_or_funding_subject':self.household_or_funding_subject,'project_id':self.project_id,'status':self.status,'complete':self.complete,'missing_phases':list(self.missing_phases),'references':[r.to_dict() for r in self.references],'authority':self.authority,'profit_recognition':self.profit_recognition,'execution_authority':self.execution_authority}
        if include_digest:p['digest']=_digest(p)
        return p
    @property
    def digest(self)->str:return _digest(self.to_dict(include_digest=False))

@dataclass(frozen=True)
class CycleArtifactReviewV4:
    status:str; blockers:tuple[str,...]; trace_digest:str; recognized_reporting_amount:str|None=None; accounting_reference_only:bool=True; execution_authority:str='NONE'
    @property
    def verified(self)->bool:return self.status=='CAUSAL_ACCOUNTING_GRAPH_VERIFIED'

def verify_complete_trace_artifacts_v4(trace:EconomicCycleTraceV4,*,authorization:CapitalAuthorizationV2,funding_receipt:Mapping[str,Any],revenue_receipt:Mapping[str,Any],project_evidence_digest:str,recognition:RevenueRecognitionDecisionV2,ledger_event:Mapping[str,Any])->CycleArtifactReviewV4:
    blockers:set[str]=set()
    if not trace.complete:return CycleArtifactReviewV4('CAUSAL_ACCOUNTING_GRAPH_BLOCKED',('TRACE_NOT_COMPLETE',),trace.digest)
    evidence=_hex(project_evidence_digest,'project_evidence_digest')
    funding=verify_settlement_receipt_v2_integrity(funding_receipt);revenue=verify_settlement_receipt_v2_integrity(revenue_receipt)
    blockers.update(verify_funding_receipt_against_authorization_v2(funding,authorization).blockers)
    blockers.update(verify_revenue_receipt_lineage_v2(revenue,authorization,expected_project_evidence_digest=evidence).blockers)
    if recognition.decision!='RECOGNIZED' or not recognition.ledger_posting_allowed: blockers.add('REVENUE_NOT_RECOGNIZED')
    if recognition.project_id!=trace.project_id: blockers.add('RECOGNITION_PROJECT_MISMATCH')
    if recognition.settlement_receipt_digest!=revenue['receipt_digest']: blockers.add('RECOGNITION_RECEIPT_LINK_MISMATCH')
    if recognition.capital_authorization_digest!=authorization.digest: blockers.add('RECOGNITION_AUTHORIZATION_LINK_MISMATCH')
    if recognition.project_evidence_digest!=evidence: blockers.add('RECOGNITION_PROJECT_EVIDENCE_LINK_MISMATCH')
    if ledger_event.get('schema')!='ledger.event/v1' or ledger_event.get('event_type')!='EXTERNAL_REVENUE': blockers.add('LEDGER_EVENT_TYPE_MISMATCH')
    if ledger_event.get('evidence_digest')!=recognition.digest: blockers.add('LEDGER_RECOGNITION_EVIDENCE_MISMATCH')
    event_digest=ledger_event_v1_digest(dict(ledger_event))
    links=(('PROJECT_SCREENING',authorization.screening_digest),('CAPITAL_AUTHORIZATION',authorization.digest),('FUNDING_SETTLEMENT',funding['receipt_digest']),('PROJECT_EVIDENCE',evidence),('REVENUE_SETTLEMENT',revenue['receipt_digest']),('REVENUE_RECOGNITION',recognition.digest),('LEDGER_EVENT',event_digest))
    for phase,digest in links:
        if trace.reference(phase).digest!=digest:blockers.add(f'{phase}_REFERENCE_MISMATCH')
    if trace.reference('FUNDING_SETTLEMENT').observed_at!=_time_text(funding['finality_time'],'funding.finality_time'): blockers.add('FUNDING_FINALITY_TIME_MISMATCH')
    if trace.reference('REVENUE_SETTLEMENT').observed_at!=_time_text(revenue['finality_time'],'revenue.finality_time'): blockers.add('REVENUE_FINALITY_TIME_MISMATCH')
    if trace.reference('REVENUE_RECOGNITION').observed_at!=recognition.recognized_at: blockers.add('RECOGNITION_TIME_MISMATCH')
    if trace.reference('LEDGER_EVENT').observed_at!=_time_text(ledger_event.get('effective_at'),'ledger_event.effective_at'): blockers.add('LEDGER_EVENT_TIME_MISMATCH')
    return CycleArtifactReviewV4('CAUSAL_ACCOUNTING_GRAPH_BLOCKED' if blockers else 'CAUSAL_ACCOUNTING_GRAPH_VERIFIED',tuple(sorted(blockers)),trace.digest,str(recognition.recognized_reporting_amount) if not blockers else None,True,'NONE')

def make_reference_v4(phase:str,*,digest:str,subject_id:str,observed_at:datetime)->CycleReferenceV4:
    p=phase.upper().strip()
    return CycleReferenceV4(p,SCHEMA_BY_PHASE[p],digest,SOURCE_BY_PHASE[p],subject_id,observed_at)

def build_trace_v4(cycle_id:str,household_or_funding_subject:str,project_id:str,references:Iterable[CycleReferenceV4])->EconomicCycleTraceV4:
    return EconomicCycleTraceV4(cycle_id,household_or_funding_subject,project_id,tuple(references))
