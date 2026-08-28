from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_available_capacity_v2 import build_distribution_available_capacity_v2
from .distribution_budget_state_v3 import DistributionBudgetStateV3
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from .liquidity_current_resources_v1 import LiquidityCurrentResourcesV1
from .liquidity_policy_v1 import LiquidityPolicyV1
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .numeric import canonical_decimal_text, finite_decimal

SCHEMA="distribution.available-capacity/v4"
BUDGET_STATE_SCHEMA="distribution.budget-state/v3"
ZERO=Decimal("0")
HEX=frozenset("0123456789abcdef")
HORIZONS=(1,4,8)

class DistributionAvailableCapacityV4Error(AccountingInvariantError):pass

def _text(v:Any,n:str)->str:
    if not isinstance(v,str) or not v.strip():raise DistributionAvailableCapacityV4Error(f"{n} is required")
    return v.strip()
def _hex(v:Any,n:str)->str:
    x=_text(v,n).lower()
    if len(x)!=64 or any(c not in HEX for c in x):raise DistributionAvailableCapacityV4Error(f"{n} must be hex64")
    return x
def _amount(v:Any,n:str,*,allow_negative=False)->Decimal:
    x=finite_decimal(v,n)
    if not allow_negative and x<ZERO:raise DistributionAvailableCapacityV4Error(f"{n} must be non-negative")
    return x
def _utc(v:datetime,n:str)->datetime:
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None:raise DistributionAvailableCapacityV4Error(f"{n} must be timezone-aware")
    return v.astimezone(UTC)

@dataclass(frozen=True)
class DistributionAvailableCapacityV4:
    capacity_id:str
    affected_period_id:str
    base_distribution_capacity_replay_digest:str
    distribution_budget_state_schema:str
    distribution_budget_state_digest:str
    current_financial_snapshot_digest:str
    current_accounting_close_digest:str
    current_liquidity_resources_digest:str
    liquidity_policy_digest:str
    maturity_snapshot_digests:tuple[str,...]
    maturity_translation_digests:tuple[str,...]
    reporting_currency:str
    current_snapshot_sequence:int
    current_snapshot_ledger_digest:str
    gross_period_profit_budget:Decimal
    post_close_settlement_fee_expenses:Decimal
    post_close_settlement_fee_refunds:Decimal
    post_close_reversal_processing_fees:Decimal
    net_post_close_distribution_fee_cost:Decimal
    fee_adjusted_period_profit_budget:Decimal
    canonical_distribution_outflows:Decimal
    canonical_distribution_reversals:Decimal
    net_consumed_distribution_budget:Decimal
    remaining_period_profit_budget:Decimal
    current_hard_nav:Decimal
    current_required_hard_nav_buffer:Decimal
    current_solvency_headroom:Decimal
    current_liquidity_distribution_capacity:Decimal
    final_available_capacity:Decimal
    horizon_headrooms:tuple[DistributionLiquidityHeadroomV1,...]
    blockers:tuple[str,...]
    status:str
    generated_at:datetime
    authority:str="FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V4"
    authorization_authority:str="NONE"
    payment_authority:str="NONE"
    execution_authority:str="NONE"
    ai_authority:str="NONE"
    def __post_init__(self):
        if self.distribution_budget_state_schema!=BUDGET_STATE_SCHEMA:raise DistributionAvailableCapacityV4Error("v4 requires distribution.budget-state/v3")
        if self.authority!="FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V4" or any(x!="NONE" for x in (self.authorization_authority,self.payment_authority,self.execution_authority,self.ai_authority)):raise DistributionAvailableCapacityV4Error("capacity authority escalation")
        object.__setattr__(self,"capacity_id",_text(self.capacity_id,"capacity_id"));object.__setattr__(self,"affected_period_id",_text(self.affected_period_id,"affected_period_id"));object.__setattr__(self,"reporting_currency",_text(self.reporting_currency,"reporting_currency").upper())
        for n in ("base_distribution_capacity_replay_digest","distribution_budget_state_digest","current_financial_snapshot_digest","current_accounting_close_digest","current_liquidity_resources_digest","liquidity_policy_digest","current_snapshot_ledger_digest"):object.__setattr__(self,n,_hex(getattr(self,n),n))
        if isinstance(self.current_snapshot_sequence,bool) or not isinstance(self.current_snapshot_sequence,int) or self.current_snapshot_sequence<1:raise DistributionAvailableCapacityV4Error("current_snapshot_sequence invalid")
        for n in ("gross_period_profit_budget","post_close_settlement_fee_expenses","post_close_settlement_fee_refunds","post_close_reversal_processing_fees","net_post_close_distribution_fee_cost","fee_adjusted_period_profit_budget","canonical_distribution_outflows","canonical_distribution_reversals","net_consumed_distribution_budget","remaining_period_profit_budget","current_required_hard_nav_buffer","current_solvency_headroom","current_liquidity_distribution_capacity","final_available_capacity"):object.__setattr__(self,n,_amount(getattr(self,n),n))
        object.__setattr__(self,"current_hard_nav",_amount(self.current_hard_nav,"current_hard_nav",allow_negative=True))
        if self.post_close_settlement_fee_refunds>self.post_close_settlement_fee_expenses:raise DistributionAvailableCapacityV4Error("fee refunds exceed post-close settlement fees")
        net_fee=self.post_close_settlement_fee_expenses-self.post_close_settlement_fee_refunds+self.post_close_reversal_processing_fees
        if self.net_post_close_distribution_fee_cost!=net_fee:raise DistributionAvailableCapacityV4Error("net fee cost mismatch")
        adjusted=min(self.gross_period_profit_budget,max(ZERO,self.gross_period_profit_budget-net_fee))
        if self.fee_adjusted_period_profit_budget!=adjusted:raise DistributionAvailableCapacityV4Error("fee-adjusted budget mismatch")
        if self.canonical_distribution_reversals>self.canonical_distribution_outflows:raise DistributionAvailableCapacityV4Error("reversals exceed outflows")
        if self.net_consumed_distribution_budget!=self.canonical_distribution_outflows-self.canonical_distribution_reversals:raise DistributionAvailableCapacityV4Error("net consumed distribution mismatch")
        if self.remaining_period_profit_budget!=max(ZERO,adjusted-self.net_consumed_distribution_budget):raise DistributionAvailableCapacityV4Error("remaining budget mismatch")
        if self.current_solvency_headroom!=max(ZERO,self.current_hard_nav-self.current_required_hard_nav_buffer):raise DistributionAvailableCapacityV4Error("solvency headroom mismatch")
        hs=tuple(sorted(self.horizon_headrooms,key=lambda x:x.horizon_weeks));object.__setattr__(self,"horizon_headrooms",hs)
        if tuple(x.horizon_weeks for x in hs)!=HORIZONS:raise DistributionAvailableCapacityV4Error("requires exact 1w/4w/8w headrooms")
        if self.current_liquidity_distribution_capacity!=min(x.horizon_distribution_capacity for x in hs):raise DistributionAvailableCapacityV4Error("liquidity capacity mismatch")
        blockers=tuple(sorted({_text(x,"blocker") for x in self.blockers}));object.__setattr__(self,"blockers",blockers)
        final=ZERO if blockers else min(self.remaining_period_profit_budget,self.current_solvency_headroom,self.current_liquidity_distribution_capacity)
        if self.final_available_capacity!=final:raise DistributionAvailableCapacityV4Error("final available capacity mismatch")
        if self.status!=("CAPACITY_AVAILABLE" if final>ZERO and not blockers else "NO_ACTION"):raise DistributionAvailableCapacityV4Error("capacity status mismatch")
        snaps=tuple(sorted(_hex(x,"maturity_snapshot_digest") for x in self.maturity_snapshot_digests));trans=tuple(sorted(_hex(x,"maturity_translation_digest") for x in self.maturity_translation_digests))
        if not snaps or len(snaps)!=len(set(snaps)) or len(trans)!=len(set(trans)) or len(trans)!=len(snaps):raise DistributionAvailableCapacityV4Error("maturity evidence set invalid")
        object.__setattr__(self,"maturity_snapshot_digests",snaps);object.__setattr__(self,"maturity_translation_digests",trans);object.__setattr__(self,"generated_at",_utc(self.generated_at,"generated_at"))
    def to_dict(self,*,include_digest=True):
        p={"schema":SCHEMA,"capacity_id":self.capacity_id,"affected_period_id":self.affected_period_id,"base_distribution_capacity_replay_digest":self.base_distribution_capacity_replay_digest,"distribution_budget_state_schema":self.distribution_budget_state_schema,"distribution_budget_state_digest":self.distribution_budget_state_digest,"current_financial_snapshot_digest":self.current_financial_snapshot_digest,"current_accounting_close_digest":self.current_accounting_close_digest,"current_liquidity_resources_digest":self.current_liquidity_resources_digest,"liquidity_policy_digest":self.liquidity_policy_digest,"maturity_snapshot_digests":list(self.maturity_snapshot_digests),"maturity_translation_digests":list(self.maturity_translation_digests),"reporting_currency":self.reporting_currency,"current_snapshot_sequence":self.current_snapshot_sequence,"current_snapshot_ledger_digest":self.current_snapshot_ledger_digest,"gross_period_profit_budget":canonical_decimal_text(self.gross_period_profit_budget),"post_close_settlement_fee_expenses":canonical_decimal_text(self.post_close_settlement_fee_expenses),"post_close_settlement_fee_refunds":canonical_decimal_text(self.post_close_settlement_fee_refunds),"post_close_reversal_processing_fees":canonical_decimal_text(self.post_close_reversal_processing_fees),"net_post_close_distribution_fee_cost":canonical_decimal_text(self.net_post_close_distribution_fee_cost),"fee_adjusted_period_profit_budget":canonical_decimal_text(self.fee_adjusted_period_profit_budget),"canonical_distribution_outflows":canonical_decimal_text(self.canonical_distribution_outflows),"canonical_distribution_reversals":canonical_decimal_text(self.canonical_distribution_reversals),"net_consumed_distribution_budget":canonical_decimal_text(self.net_consumed_distribution_budget),"remaining_period_profit_budget":canonical_decimal_text(self.remaining_period_profit_budget),"current_hard_nav":canonical_decimal_text(self.current_hard_nav),"current_required_hard_nav_buffer":canonical_decimal_text(self.current_required_hard_nav_buffer),"current_solvency_headroom":canonical_decimal_text(self.current_solvency_headroom),"current_liquidity_distribution_capacity":canonical_decimal_text(self.current_liquidity_distribution_capacity),"final_available_capacity":canonical_decimal_text(self.final_available_capacity),"horizon_headrooms":[x.to_dict() for x in self.horizon_headrooms],"blockers":list(self.blockers),"status":self.status,"generated_at":self.generated_at.isoformat().replace("+00:00","Z"),"authority":self.authority,"authorization_authority":self.authorization_authority,"payment_authority":self.payment_authority,"execution_authority":self.execution_authority,"ai_authority":self.ai_authority}
        if include_digest:p["digest"]=canonical_json_digest(p)
        return p
    @property
    def digest(self):return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_available_capacity_v4(*,capacity_id:str,base_capacity:DistributionCapacityReplayV1,budget_state:DistributionBudgetStateV3,current_financial_snapshot:Mapping[str,Any],current_accounting_close:AccountingCloseV2,current_sealed_ledger_events:Sequence[Mapping[str,Any]],current_liquidity_resources:LiquidityCurrentResourcesV1,liquidity_policy:LiquidityPolicyV1,maturity_snapshots:Sequence[Mapping[str,Any]],maturity_translations:Sequence[MaturityTranslationArtifactV1],generated_at:datetime)->DistributionAvailableCapacityV4:
    if not isinstance(budget_state,DistributionBudgetStateV3):raise DistributionAvailableCapacityV4Error("v4 path requires DistributionBudgetStateV3")
    kernel=build_distribution_available_capacity_v2(capacity_id=f"{capacity_id}:v2-math-kernel",base_capacity=base_capacity,budget_state=budget_state,current_financial_snapshot=current_financial_snapshot,current_accounting_close=current_accounting_close,current_sealed_ledger_events=current_sealed_ledger_events,current_liquidity_resources=current_liquidity_resources,liquidity_policy=liquidity_policy,maturity_snapshots=maturity_snapshots,maturity_translations=maturity_translations,generated_at=generated_at)
    if kernel.distribution_budget_state_digest!=budget_state.digest:raise DistributionAvailableCapacityV4Error("capacity kernel did not bind exact BudgetState v3")
    return DistributionAvailableCapacityV4(capacity_id=capacity_id,affected_period_id=kernel.affected_period_id,base_distribution_capacity_replay_digest=kernel.base_distribution_capacity_replay_digest,distribution_budget_state_schema=BUDGET_STATE_SCHEMA,distribution_budget_state_digest=budget_state.digest,current_financial_snapshot_digest=kernel.current_financial_snapshot_digest,current_accounting_close_digest=kernel.current_accounting_close_digest,current_liquidity_resources_digest=kernel.current_liquidity_resources_digest,liquidity_policy_digest=kernel.liquidity_policy_digest,maturity_snapshot_digests=kernel.maturity_snapshot_digests,maturity_translation_digests=kernel.maturity_translation_digests,reporting_currency=kernel.reporting_currency,current_snapshot_sequence=kernel.current_snapshot_sequence,current_snapshot_ledger_digest=kernel.current_snapshot_ledger_digest,gross_period_profit_budget=budget_state.gross_period_profit_budget,post_close_settlement_fee_expenses=budget_state.post_close_settlement_fee_expenses,post_close_settlement_fee_refunds=budget_state.post_close_settlement_fee_refunds,post_close_reversal_processing_fees=budget_state.post_close_reversal_processing_fees,net_post_close_distribution_fee_cost=budget_state.net_post_close_distribution_fee_cost,fee_adjusted_period_profit_budget=budget_state.fee_adjusted_period_profit_budget,canonical_distribution_outflows=budget_state.canonical_distribution_outflows,canonical_distribution_reversals=budget_state.canonical_distribution_reversals,net_consumed_distribution_budget=budget_state.net_consumed_distribution_budget,remaining_period_profit_budget=budget_state.remaining_period_profit_budget,current_hard_nav=kernel.current_hard_nav,current_required_hard_nav_buffer=kernel.current_required_hard_nav_buffer,current_solvency_headroom=kernel.current_solvency_headroom,current_liquidity_distribution_capacity=kernel.current_liquidity_distribution_capacity,final_available_capacity=kernel.final_available_capacity,horizon_headrooms=kernel.horizon_headrooms,blockers=kernel.blockers,status=kernel.status,generated_at=kernel.generated_at)


def verify_distribution_available_capacity_v4_payload(payload:Mapping[str,Any])->bool:
    if not isinstance(payload,Mapping) or payload.get("schema")!=SCHEMA or payload.get("distribution_budget_state_schema")!=BUDGET_STATE_SCHEMA:return False
    item=dict(payload);supplied=item.pop("digest",None)
    if supplied!=canonical_json_digest(item):return False
    if item.get("authority")!="FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V4" or any(item.get(n)!="NONE" for n in ("authorization_authority","payment_authority","execution_authority","ai_authority")):return False
    try:
        gross=_amount(item["gross_period_profit_budget"],"gross");expense=_amount(item["post_close_settlement_fee_expenses"],"expense");refund=_amount(item["post_close_settlement_fee_refunds"],"refund");processing=_amount(item["post_close_reversal_processing_fees"],"processing");netfee=_amount(item["net_post_close_distribution_fee_cost"],"netfee");adjusted=_amount(item["fee_adjusted_period_profit_budget"],"adjusted");outflows=_amount(item["canonical_distribution_outflows"],"outflows");reversals=_amount(item["canonical_distribution_reversals"],"reversals");net=_amount(item["net_consumed_distribution_budget"],"net");remaining=_amount(item["remaining_period_profit_budget"],"remaining");hard=_amount(item["current_hard_nav"],"hard",allow_negative=True);buffer=_amount(item["current_required_hard_nav_buffer"],"buffer");solvency=_amount(item["current_solvency_headroom"],"solvency");liquidity=_amount(item["current_liquidity_distribution_capacity"],"liquidity");final=_amount(item["final_available_capacity"],"final")
    except (KeyError,ValueError,TypeError,DistributionAvailableCapacityV4Error):return False
    if refund>expense or netfee!=expense-refund+processing:return False
    if adjusted!=min(gross,max(ZERO,gross-netfee)) or reversals>outflows or net!=outflows-reversals or remaining!=max(ZERO,adjusted-net):return False
    if solvency!=max(ZERO,hard-buffer):return False
    blockers=item.get("blockers");
    if not isinstance(blockers,list) or any(not isinstance(x,str) for x in blockers):return False
    expected=ZERO if blockers else min(remaining,solvency,liquidity)
    if final!=expected or item.get("status")!=("CAPACITY_AVAILABLE" if expected>ZERO and not blockers else "NO_ACTION"):return False
    return True
