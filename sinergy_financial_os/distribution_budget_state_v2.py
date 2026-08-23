from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_budget_state_v1 import (
    DistributionBudgetStateV1Error,
    _distribution_amount,
    _reversal_amount,
    build_distribution_budget_state_v1,
)
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingEntry, ReportingLedger
from .statement_replay_v1 import StatementReplayV1

SCHEMA="distribution.budget-state/v2"
ZERO=Decimal("0")
HEX=frozenset("0123456789abcdef")

class DistributionBudgetStateV2Error(AccountingInvariantError):pass

def _text(v:Any,n:str)->str:
    if not isinstance(v,str) or not v.strip():raise DistributionBudgetStateV2Error(f"{n} is required")
    return v.strip()
def _hex(v:Any,n:str)->str:
    x=_text(v,n).lower()
    if len(x)!=64 or any(c not in HEX for c in x):raise DistributionBudgetStateV2Error(f"{n} must be hex64")
    return x
def _utc(v:datetime,n:str)->datetime:
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None:raise DistributionBudgetStateV2Error(f"{n} must be timezone-aware")
    return v.astimezone(UTC)
def _amount(v:Any,n:str)->Decimal:
    x=finite_decimal(v,n)
    if x<ZERO:raise DistributionBudgetStateV2Error(f"{n} must be non-negative")
    return x

def _external_line(ledger:ReportingLedger,entry:ReportingEntry,account_class:AccountClass):
    return [(ledger.account(line.account_id),line) for line in entry.lines if ledger.account(line.account_id).account_class==account_class and ledger.account(line.account_id).consolidation_class==ConsolidationClass.EXTERNAL]

def _settlement_fee_amount(ledger:ReportingLedger,entry:ReportingEntry)->Decimal:
    if entry.flow_type!=FlowType.EXTERNAL_EXPENSE:raise DistributionBudgetStateV2Error("distribution settlement fee must be EXTERNAL_EXPENSE")
    if entry.metadata.get("economic_class")!="OWNER_DISTRIBUTION_SETTLEMENT_FEE":raise DistributionBudgetStateV2Error("settlement fee economic class mismatch")
    if entry.metadata.get("pnl_treatment")!="REALIZED_EXTERNAL_EXPENSE":raise DistributionBudgetStateV2Error("settlement fee P&L treatment mismatch")
    if entry.metadata.get("fee_treatment")!="EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT":raise DistributionBudgetStateV2Error("settlement fee treatment mismatch")
    if len(entry.lines)!=2:raise DistributionBudgetStateV2Error("settlement fee requires two lines")
    assets=_external_line(ledger,entry,AccountClass.ASSET);expenses=_external_line(ledger,entry,AccountClass.EXPENSE)
    if len(assets)!=1 or len(expenses)!=1:raise DistributionBudgetStateV2Error("settlement fee requires one external asset and one external expense")
    _,a=assets[0];_,e=expenses[0]
    if a.debit!=ZERO or a.credit<=ZERO or e.credit!=ZERO or e.debit<=ZERO or a.credit!=e.debit:raise DistributionBudgetStateV2Error("settlement fee debit/credit mismatch")
    return a.credit

@dataclass(frozen=True)
class DistributionBudgetStateV2:
    state_id:str
    previous_budget_state_digest:str
    affected_period_id:str
    base_distribution_capacity_replay_digest:str
    base_statement_replay_digest:str
    base_statement_closing_sequence:int
    reporting_currency:str
    ledger_sequence:int
    ledger_digest:str
    gross_period_profit_budget:Decimal
    post_close_settlement_fee_expenses:Decimal
    fee_adjusted_period_profit_budget:Decimal
    canonical_distribution_outflows:Decimal
    canonical_distribution_reversals:Decimal
    net_consumed_distribution_budget:Decimal
    remaining_period_profit_budget:Decimal
    settlement_fee_entry_digests:tuple[str,...]
    distribution_entry_digests:tuple[str,...]
    reversal_entry_digests:tuple[str,...]
    blockers:tuple[str,...]
    status:str
    generated_at:datetime
    authority:str="FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE_V2"
    authorization_authority:str="NONE"
    payment_authority:str="NONE"
    execution_authority:str="NONE"
    ai_authority:str="NONE"
    def __post_init__(self):
        if self.authority!="FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE_V2" or any(x!="NONE" for x in (self.authorization_authority,self.payment_authority,self.execution_authority,self.ai_authority)):raise DistributionBudgetStateV2Error("budget state authority escalation")
        object.__setattr__(self,"state_id",_text(self.state_id,"state_id"));object.__setattr__(self,"affected_period_id",_text(self.affected_period_id,"affected_period_id"));object.__setattr__(self,"reporting_currency",_text(self.reporting_currency,"reporting_currency").upper())
        for n in ("previous_budget_state_digest","base_distribution_capacity_replay_digest","base_statement_replay_digest","ledger_digest"):object.__setattr__(self,n,_hex(getattr(self,n),n))
        if isinstance(self.base_statement_closing_sequence,bool) or not isinstance(self.base_statement_closing_sequence,int) or self.base_statement_closing_sequence<0:raise DistributionBudgetStateV2Error("base_statement_closing_sequence invalid")
        if isinstance(self.ledger_sequence,bool) or not isinstance(self.ledger_sequence,int) or self.ledger_sequence<self.base_statement_closing_sequence:raise DistributionBudgetStateV2Error("ledger_sequence invalid")
        for n in ("gross_period_profit_budget","post_close_settlement_fee_expenses","fee_adjusted_period_profit_budget","canonical_distribution_outflows","canonical_distribution_reversals","net_consumed_distribution_budget","remaining_period_profit_budget"):object.__setattr__(self,n,_amount(getattr(self,n),n))
        if self.canonical_distribution_reversals>self.canonical_distribution_outflows:raise DistributionBudgetStateV2Error("reversals exceed distributions")
        if self.net_consumed_distribution_budget!=self.canonical_distribution_outflows-self.canonical_distribution_reversals:raise DistributionBudgetStateV2Error("net consumed distribution mismatch")
        expected_adjusted=max(ZERO,self.gross_period_profit_budget-self.post_close_settlement_fee_expenses)
        if self.fee_adjusted_period_profit_budget!=expected_adjusted:raise DistributionBudgetStateV2Error("fee-adjusted period profit budget mismatch")
        expected_remaining=max(ZERO,expected_adjusted-self.net_consumed_distribution_budget)
        if self.remaining_period_profit_budget!=expected_remaining:raise DistributionBudgetStateV2Error("remaining period profit budget mismatch")
        for field in ("settlement_fee_entry_digests","distribution_entry_digests","reversal_entry_digests"):
            vals=tuple(_hex(x,field) for x in getattr(self,field))
            if len(vals)!=len(set(vals)):raise DistributionBudgetStateV2Error(f"{field} must be unique")
            object.__setattr__(self,field,vals)
        blockers=tuple(sorted({_text(x,"blocker") for x in self.blockers}));object.__setattr__(self,"blockers",blockers)
        expected_status="BUDGET_AVAILABLE" if self.remaining_period_profit_budget>ZERO and not blockers else "NO_ACTION"
        if self.status!=expected_status:raise DistributionBudgetStateV2Error("budget status mismatch")
        object.__setattr__(self,"generated_at",_utc(self.generated_at,"generated_at"))
    def to_dict(self,*,include_digest=True):
        p={"schema":SCHEMA,"state_id":self.state_id,"previous_budget_state_digest":self.previous_budget_state_digest,"affected_period_id":self.affected_period_id,"base_distribution_capacity_replay_digest":self.base_distribution_capacity_replay_digest,"base_statement_replay_digest":self.base_statement_replay_digest,"base_statement_closing_sequence":self.base_statement_closing_sequence,"reporting_currency":self.reporting_currency,"ledger_sequence":self.ledger_sequence,"ledger_digest":self.ledger_digest,"gross_period_profit_budget":canonical_decimal_text(self.gross_period_profit_budget),"post_close_settlement_fee_expenses":canonical_decimal_text(self.post_close_settlement_fee_expenses),"fee_adjusted_period_profit_budget":canonical_decimal_text(self.fee_adjusted_period_profit_budget),"canonical_distribution_outflows":canonical_decimal_text(self.canonical_distribution_outflows),"canonical_distribution_reversals":canonical_decimal_text(self.canonical_distribution_reversals),"net_consumed_distribution_budget":canonical_decimal_text(self.net_consumed_distribution_budget),"remaining_period_profit_budget":canonical_decimal_text(self.remaining_period_profit_budget),"settlement_fee_entry_digests":list(self.settlement_fee_entry_digests),"distribution_entry_digests":list(self.distribution_entry_digests),"reversal_entry_digests":list(self.reversal_entry_digests),"blockers":list(self.blockers),"status":self.status,"generated_at":self.generated_at.isoformat().replace("+00:00","Z"),"authority":self.authority,"authorization_authority":self.authorization_authority,"payment_authority":self.payment_authority,"execution_authority":self.execution_authority,"ai_authority":self.ai_authority}
        if include_digest:p["digest"]=canonical_json_digest(p)
        return p
    @property
    def digest(self):return canonical_json_digest(self.to_dict(include_digest=False))

def build_distribution_budget_state_v2(*,state_id:str,base_capacity:DistributionCapacityReplayV1,base_statement_replay:StatementReplayV1,ledger:ReportingLedger,generated_at:datetime)->DistributionBudgetStateV2:
    if base_statement_replay.digest!=base_capacity.statement_replay_digest:raise DistributionBudgetStateV2Error("base StatementReplay / DistributionCapacityReplay mismatch")
    previous=build_distribution_budget_state_v1(state_id=f"{state_id}:v1-lineage",base_capacity=base_capacity,ledger=ledger,generated_at=generated_at)
    affected=base_capacity.affected_period_id
    distributions=[];by_digest={}
    for entry in ledger.entries_since(0):
        if entry.metadata.get("economic_class")=="OWNER_DISTRIBUTION" and entry.metadata.get("affected_period_id")==affected:
            amount=_distribution_amount(ledger,entry);distributions.append((entry,amount));by_digest[entry.digest]=(entry,amount)
    reversals=[];reversed_by={}
    for entry in ledger.entries_since(0):
        if entry.metadata.get("economic_class")!="OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL":continue
        original_digest=entry.metadata.get("original_distribution_reporting_entry_digest")
        try:original_digest=_hex(original_digest,"original_distribution_reporting_entry_digest")
        except DistributionBudgetStateV2Error:raise
        original=by_digest.get(original_digest)
        if original is None:
            candidates=[x for x in ledger.entries_since(0) if x.digest==original_digest]
            if len(candidates)!=1:raise DistributionBudgetStateV2Error("reversal original missing/non-unique")
            original_entry=candidates[0]
            if original_entry.metadata.get("economic_class")!="OWNER_DISTRIBUTION":raise DistributionBudgetStateV2Error("reversal original not owner distribution")
            if original_entry.metadata.get("affected_period_id")!=affected:continue
            amount=_distribution_amount(ledger,original_entry);original=(original_entry,amount);by_digest[original_digest]=original
            if all(e.digest!=original_entry.digest for e,_ in distributions):distributions.append(original)
        amount=_reversal_amount(ledger,entry);cumulative=reversed_by.get(original_digest,ZERO)+amount
        if cumulative>original[1]:raise DistributionBudgetStateV2Error("cumulative reversal exceeds original distribution")
        reversed_by[original_digest]=cumulative;reversals.append((entry,amount))
    fees=[]
    for entry in ledger.entries_since(base_statement_replay.closing_sequence):
        if entry.metadata.get("economic_class")!="OWNER_DISTRIBUTION_SETTLEMENT_FEE":continue
        if entry.metadata.get("affected_period_id")!=affected:continue
        fees.append((entry,_settlement_fee_amount(ledger,entry)))
    distributions.sort(key=lambda x:x[0].sequence);reversals.sort(key=lambda x:x[0].sequence);fees.sort(key=lambda x:x[0].sequence)
    outflows=sum((a for _,a in distributions),ZERO);rev=sum((a for _,a in reversals),ZERO);net=outflows-rev;fee_total=sum((a for _,a in fees),ZERO);gross=base_capacity.realized_profit_budget;adjusted=max(ZERO,gross-fee_total);remaining=max(ZERO,adjusted-net);blockers=[]
    if net>adjusted:blockers.append("DISTRIBUTED_ABOVE_FEE_ADJUSTED_PERIOD_BUDGET")
    if fee_total>gross:blockers.append("POST_CLOSE_FEES_EXCEED_GROSS_PERIOD_PROFIT_BUDGET")
    if remaining<=ZERO:blockers.append("NO_REMAINING_PERIOD_BUDGET")
    return DistributionBudgetStateV2(state_id=state_id,previous_budget_state_digest=previous.digest,affected_period_id=affected,base_distribution_capacity_replay_digest=base_capacity.digest,base_statement_replay_digest=base_statement_replay.digest,base_statement_closing_sequence=base_statement_replay.closing_sequence,reporting_currency=ledger.reporting_currency,ledger_sequence=ledger.sequence,ledger_digest=ledger.digest,gross_period_profit_budget=gross,post_close_settlement_fee_expenses=fee_total,fee_adjusted_period_profit_budget=adjusted,canonical_distribution_outflows=outflows,canonical_distribution_reversals=rev,net_consumed_distribution_budget=net,remaining_period_profit_budget=remaining,settlement_fee_entry_digests=tuple(e.digest for e,_ in fees),distribution_entry_digests=tuple(e.digest for e,_ in distributions),reversal_entry_digests=tuple(e.digest for e,_ in reversals),blockers=tuple(blockers),status="BUDGET_AVAILABLE" if remaining>ZERO and not blockers else "NO_ACTION",generated_at=generated_at)
