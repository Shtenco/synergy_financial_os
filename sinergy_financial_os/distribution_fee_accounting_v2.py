from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_authorization_v2 import DistributionAuthorizationV2
from .distribution_execution_ticket_v2 import DistributionExecutionTicketV2
from .distribution_plan_v2 import DistributionPlanV2
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingLedger, ReportingLine

ZERO=Decimal("0")
HEX=frozenset("0123456789abcdef")
TERMINAL=frozenset({"SETTLED","FAILED","REVERSED"})
UTIL_STATUSES=frozenset({"FULLY_SETTLED","PARTIALLY_SETTLED_REQUIRES_NEW_PLAN","FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION"})
FEE_TREATMENT="EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT"
UNUSED_FEE_TREATMENT="UNUTILIZED_AUTHORIZED_CAPACITY_NOT_PROFIT"

class DistributionFeeAccountingV2Error(AccountingInvariantError):pass

def _text(v:Any,n:str)->str:
    if not isinstance(v,str) or not v.strip():raise DistributionFeeAccountingV2Error(f"{n} is required")
    return v.strip()
def _hex(v:Any,n:str)->str:
    x=_text(v,n).lower()
    if len(x)!=64 or any(c not in HEX for c in x):raise DistributionFeeAccountingV2Error(f"{n} must be hex64")
    return x
def _dec(v:Any,n:str,*,nonnegative=False)->Decimal:
    if not isinstance(v,str) or not v:raise DistributionFeeAccountingV2Error(f"{n} must be canonical decimal text")
    x=finite_decimal(v,n)
    if canonical_decimal_text(x)!=v:raise DistributionFeeAccountingV2Error(f"{n} non-canonical")
    if nonnegative and x<ZERO:raise DistributionFeeAccountingV2Error(f"{n} negative")
    return x
def _parse_time(v:Any,n:str)->datetime:
    x=_text(v,n)
    if not x.endswith("Z"):raise DistributionFeeAccountingV2Error(f"{n} must be UTC Z")
    t=datetime.fromisoformat(x.replace("Z","+00:00")).astimezone(UTC)
    if t.isoformat().replace("+00:00","Z")!=x:raise DistributionFeeAccountingV2Error(f"{n} non-canonical")
    return t
def _digest(payload:Mapping[str,Any],field="digest"):
    supplied=_hex(payload.get(field),field);body=dict(payload);body.pop(field,None)
    if canonical_json_digest(body)!=supplied:raise DistributionFeeAccountingV2Error(f"{field} mismatch")
    return supplied

@dataclass(frozen=True)
class DistributionFeeAccountingAccountsV2:
    external_cash_account:str
    distribution_equity_account:str
    settlement_fee_expense_account:str
    source_account_mapping_evidence_digest:str
    def __post_init__(self):
        for n in ("external_cash_account","distribution_equity_account","settlement_fee_expense_account"):object.__setattr__(self,n,_text(getattr(self,n),n))
        if len({self.external_cash_account,self.distribution_equity_account,self.settlement_fee_expense_account})!=3:raise DistributionFeeAccountingV2Error("cash/equity/fee accounts must be distinct")
        object.__setattr__(self,"source_account_mapping_evidence_digest",_hex(self.source_account_mapping_evidence_digest,"source_account_mapping_evidence_digest"))


def verify_attempt_v2(payload:Mapping[str,Any],*,plan:DistributionPlanV2,authorization:DistributionAuthorizationV2,ticket:DistributionExecutionTicketV2)->dict[str,Any]:
    if not isinstance(payload,Mapping) or payload.get("schema")!="distribution.batch-attempt/v2":raise DistributionFeeAccountingV2Error("unsupported attempt schema")
    x=dict(payload);_digest(x)
    expected={"distribution_plan_digest":plan.digest,"distribution_authorization_digest":authorization.digest,"distribution_execution_ticket_digest":ticket.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest,"source_account_id":plan.source_account_id,"distribution_currency":plan.distribution_currency,"planned_principal_total":canonical_decimal_text(plan.principal_total),"authorized_external_fee_budget":canonical_decimal_text(plan.external_fee_budget),"authorized_total_outflow_ceiling":canonical_decimal_text(plan.total_authorized_outflow_ceiling)}
    for k,v in expected.items():
        if x.get(k)!=v:raise DistributionFeeAccountingV2Error(f"attempt mismatch: {k}")
    if x.get("status")!="AUTHORIZATION_CONSUMED_FOR_FEE_BUDGETED_ATTEMPT" or x.get("authorization_consumption")!="CONSUMED" or x.get("authority")!="METAPAY_DISTRIBUTION_HANDOFF_V2" or x.get("accounting_authority")!="NONE" or x.get("profit_recognition")!="NOT_PERFORMED":raise DistributionFeeAccountingV2Error("attempt authority/state mismatch")
    bindings=x.get("intent_bindings")
    if not isinstance(bindings,list) or len(bindings)!=len(plan.beneficiaries):raise DistributionFeeAccountingV2Error("attempt must bind every beneficiary")
    by={b.beneficiary_id:b for b in plan.beneficiaries};seen=set()
    for raw in bindings:
        bid=_text(raw.get("beneficiary_id"),"beneficiary_id")
        if bid in seen or bid not in by:raise DistributionFeeAccountingV2Error("attempt beneficiary duplicate/unknown")
        seen.add(bid);b=by[bid]
        if raw.get("destination_id")!=b.destination_id or raw.get("principal_amount")!=canonical_decimal_text(b.amount) or raw.get("payment_idempotency_key")!=b.payment_idempotency_key:raise DistributionFeeAccountingV2Error("attempt changed beneficiary principal/destination/idempotency")
        _text(raw.get("intent_id"),"intent_id");_hex(raw.get("intent_binding_digest"),"intent_binding_digest")
    return x


def verify_receipt_v2(payload:Mapping[str,Any],*,plan:DistributionPlanV2,authorization:DistributionAuthorizationV2,ticket:DistributionExecutionTicketV2,attempt:Mapping[str,Any])->dict[str,Any]:
    if not isinstance(payload,Mapping) or payload.get("schema")!="distribution.settlement-receipt/v2":raise DistributionFeeAccountingV2Error("unsupported receipt schema")
    x=dict(payload);_digest(x,"receipt_digest")
    lineage={"distribution_attempt_digest":attempt["digest"],"distribution_plan_digest":plan.digest,"distribution_authorization_digest":authorization.digest,"distribution_execution_ticket_digest":ticket.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest}
    for k,v in lineage.items():
        if x.get(k)!=v:raise DistributionFeeAccountingV2Error(f"receipt mismatch: {k}")
    bid=_text(x.get("beneficiary_id"),"beneficiary_id");matches=[b for b in plan.beneficiaries if b.beneficiary_id==bid]
    if len(matches)!=1:raise DistributionFeeAccountingV2Error("receipt beneficiary unknown")
    b=matches[0]
    if x.get("payer_id")!=plan.source_account_id or x.get("payee_id")!=b.destination_id or x.get("asset")!=plan.distribution_currency or x.get("payment_idempotency_key")!=b.payment_idempotency_key:raise DistributionFeeAccountingV2Error("receipt payer/payee/asset/idempotency mismatch")
    planned=_dec(x.get("planned_principal_amount"),"planned_principal_amount",nonnegative=True);settled=_dec(x.get("settled_principal_amount"),"settled_principal_amount",nonnegative=True);fee=_dec(x.get("payer_borne_external_fee"),"payer_borne_external_fee",nonnegative=True);budget=_dec(x.get("authorized_external_fee_budget"),"authorized_external_fee_budget",nonnegative=True);cash=_dec(x.get("payer_cash_outflow"),"payer_cash_outflow",nonnegative=True);ceiling=_dec(x.get("authorized_total_outflow_ceiling"),"authorized_total_outflow_ceiling",nonnegative=True)
    if planned!=b.amount or budget!=plan.external_fee_budget or ceiling!=plan.total_authorized_outflow_ceiling:raise DistributionFeeAccountingV2Error("receipt changed planned economics")
    status=x.get("status")
    if status not in TERMINAL:raise DistributionFeeAccountingV2Error("receipt non-terminal")
    if settled!=(planned if status=="SETTLED" else ZERO):raise DistributionFeeAccountingV2Error("settled principal/status mismatch")
    if fee>budget or cash!=settled+fee or cash>ceiling:raise DistributionFeeAccountingV2Error("receipt fee/cash ceiling mismatch")
    if x.get("fee_treatment")!=FEE_TREATMENT or x.get("authority")!="SETTLEMENT_EVIDENCE_ONLY" or x.get("accounting_authority")!="Shtenco/synergy_financial_os" or x.get("profit_recognition")!="NOT_PERFORMED" or x.get("execution_authority")!="NONE":raise DistributionFeeAccountingV2Error("receipt authority/treatment mismatch")
    if fee>ZERO:_hex(x.get("external_fee_evidence_digest"),"external_fee_evidence_digest")
    elif x.get("external_fee_evidence_digest") is not None:raise DistributionFeeAccountingV2Error("zero fee cannot carry fee evidence")
    _hex(x.get("settlement_evidence_digest"),"settlement_evidence_digest");_parse_time(x.get("finality_time"),"finality_time")
    return x


def verify_utilization_v2(payload:Mapping[str,Any],*,plan:DistributionPlanV2,authorization:DistributionAuthorizationV2,ticket:DistributionExecutionTicketV2,attempt:Mapping[str,Any],receipts:Sequence[Mapping[str,Any]])->tuple[dict[str,Any],tuple[dict[str,Any],...]]:
    if not isinstance(payload,Mapping) or payload.get("schema")!="distribution.utilization/v2":raise DistributionFeeAccountingV2Error("unsupported utilization schema")
    u=dict(payload);_digest(u)
    lineage={"distribution_attempt_digest":attempt["digest"],"distribution_plan_digest":plan.digest,"distribution_authorization_digest":authorization.digest,"distribution_execution_ticket_digest":ticket.digest,"distribution_available_capacity_digest":plan.distribution_available_capacity_digest,"beneficiary_set_digest":plan.beneficiary_set_digest}
    for k,v in lineage.items():
        if u.get(k)!=v:raise DistributionFeeAccountingV2Error(f"utilization mismatch: {k}")
    verified=tuple(verify_receipt_v2(r,plan=plan,authorization=authorization,ticket=ticket,attempt=attempt) for r in receipts)
    if len(verified)!=len(plan.beneficiaries):raise DistributionFeeAccountingV2Error("one receipt per beneficiary required")
    if tuple(u.get("receipt_digests") or ())!=tuple(sorted(r["receipt_digest"] for r in verified)):raise DistributionFeeAccountingV2Error("utilization receipt set mismatch")
    settled=sum((_dec(r["settled_principal_amount"],"settled",nonnegative=True) for r in verified),ZERO);fee=sum((_dec(r["payer_borne_external_fee"],"fee",nonnegative=True) for r in verified),ZERO);cash=settled+fee
    if u.get("planned_principal_total")!=canonical_decimal_text(plan.principal_total) or u.get("settled_principal_total")!=canonical_decimal_text(settled) or u.get("authorized_external_fee_budget")!=canonical_decimal_text(plan.external_fee_budget) or u.get("actual_external_fee_total")!=canonical_decimal_text(fee) or u.get("unused_external_fee_budget")!=canonical_decimal_text(plan.external_fee_budget-fee) or u.get("authorized_total_outflow_ceiling")!=canonical_decimal_text(plan.total_authorized_outflow_ceiling) or u.get("actual_payer_cash_outflow")!=canonical_decimal_text(cash):raise DistributionFeeAccountingV2Error("utilization principal/fee/cash formula mismatch")
    if fee>plan.external_fee_budget or cash>plan.total_authorized_outflow_ceiling:raise DistributionFeeAccountingV2Error("utilization exceeds authorized fee/outflow ceiling")
    if u.get("status") not in UTIL_STATUSES or u.get("authorization_consumption")!="CONSUMED" or u.get("accounting_authority")!="REFERENCE_ONLY" or u.get("profit_recognition")!="NOT_PERFORMED" or u.get("unused_fee_budget_treatment")!=UNUSED_FEE_TREATMENT or u.get("execution_authority")!="NONE":raise DistributionFeeAccountingV2Error("utilization authority/status mismatch")
    return u,verified

@dataclass(frozen=True)
class DistributionFeeAccountingDecisionV2:
    decision_id:str
    distribution_plan_digest:str
    distribution_authorization_digest:str
    distribution_execution_ticket_digest:str
    distribution_attempt_digest:str
    distribution_utilization_digest:str
    receipt_set_digest:str
    affected_period_id:str
    reporting_currency:str
    settled_principal_total:Decimal
    actual_external_fee_total:Decimal
    actual_payer_cash_outflow:Decimal
    status:str
    blockers:tuple[str,...]
    decided_at:datetime
    authority:str="FINANCIAL_OS_DISTRIBUTION_FEE_ACCOUNTING_V2"
    principal_economic_class:str="OWNER_DISTRIBUTION"
    principal_pnl_treatment:str="EXCLUDED_FROM_REALIZED_PNL"
    fee_economic_class:str="OWNER_DISTRIBUTION_SETTLEMENT_FEE"
    fee_pnl_treatment:str="REALIZED_EXTERNAL_EXPENSE"
    execution_authority:str="NONE"
    ai_authority:str="NONE"
    def to_dict(self,*,include_digest=True):
        p={"schema":"distribution.fee-accounting-decision/v2","decision_id":self.decision_id,"distribution_plan_digest":self.distribution_plan_digest,"distribution_authorization_digest":self.distribution_authorization_digest,"distribution_execution_ticket_digest":self.distribution_execution_ticket_digest,"distribution_attempt_digest":self.distribution_attempt_digest,"distribution_utilization_digest":self.distribution_utilization_digest,"receipt_set_digest":self.receipt_set_digest,"affected_period_id":self.affected_period_id,"reporting_currency":self.reporting_currency,"settled_principal_total":canonical_decimal_text(self.settled_principal_total),"actual_external_fee_total":canonical_decimal_text(self.actual_external_fee_total),"actual_payer_cash_outflow":canonical_decimal_text(self.actual_payer_cash_outflow),"status":self.status,"blockers":list(self.blockers),"decided_at":self.decided_at.astimezone(UTC).isoformat().replace("+00:00","Z"),"authority":self.authority,"principal_economic_class":self.principal_economic_class,"principal_pnl_treatment":self.principal_pnl_treatment,"fee_economic_class":self.fee_economic_class,"fee_pnl_treatment":self.fee_pnl_treatment,"execution_authority":self.execution_authority,"ai_authority":self.ai_authority}
        if include_digest:p["digest"]=canonical_json_digest(p)
        return p
    @property
    def digest(self):return canonical_json_digest(self.to_dict(include_digest=False))


def evaluate_distribution_fee_accounting_v2(*,decision_id:str,ledger:ReportingLedger,plan:DistributionPlanV2,authorization:DistributionAuthorizationV2,ticket:DistributionExecutionTicketV2,attempt_payload:Mapping[str,Any],utilization_payload:Mapping[str,Any],receipt_payloads:Sequence[Mapping[str,Any]],accounts:DistributionFeeAccountingAccountsV2,decided_at:datetime)->DistributionFeeAccountingDecisionV2:
    if ledger.reporting_currency!=plan.distribution_currency:raise DistributionFeeAccountingV2Error("ledger/reporting currency mismatch")
    if authorization.distribution_plan_digest!=plan.digest or ticket.distribution_plan_digest!=plan.digest or ticket.distribution_authorization_digest!=authorization.digest:raise DistributionFeeAccountingV2Error("Financial OS plan/auth/ticket context mismatch")
    attempt=verify_attempt_v2(attempt_payload,plan=plan,authorization=authorization,ticket=ticket);u,receipts=verify_utilization_v2(utilization_payload,plan=plan,authorization=authorization,ticket=ticket,attempt=attempt,receipts=receipt_payloads)
    cash_spec=ledger.account(accounts.external_cash_account);equity_spec=ledger.account(accounts.distribution_equity_account);fee_spec=ledger.account(accounts.settlement_fee_expense_account)
    if cash_spec.account_class!=AccountClass.ASSET or cash_spec.consolidation_class!=ConsolidationClass.EXTERNAL:raise DistributionFeeAccountingV2Error("cash account must be EXTERNAL ASSET")
    if equity_spec.account_class!=AccountClass.EQUITY or equity_spec.consolidation_class!=ConsolidationClass.EXTERNAL:raise DistributionFeeAccountingV2Error("distribution account must be EXTERNAL EQUITY")
    if fee_spec.account_class!=AccountClass.EXPENSE or fee_spec.consolidation_class!=ConsolidationClass.EXTERNAL:raise DistributionFeeAccountingV2Error("settlement fee account must be EXTERNAL EXPENSE")
    principal=_dec(u["settled_principal_total"],"settled principal",nonnegative=True);fee=_dec(u["actual_external_fee_total"],"actual fee",nonnegative=True);cash=principal+fee;blockers=[]
    if cash==ZERO:blockers.append("NO_SETTLED_PRINCIPAL_OR_EXTERNAL_FEE")
    if ledger.balance(accounts.external_cash_account)<cash:blockers.append("INSUFFICIENT_REPORTED_CASH_BALANCE")
    if principal>ZERO and ledger.balance(accounts.distribution_equity_account)<principal:blockers.append("INSUFFICIENT_DISTRIBUTION_EQUITY_BALANCE")
    latest=max(_parse_time(r["finality_time"],"receipt.finality_time") for r in receipts);when=decided_at.astimezone(UTC)
    if when<latest:raise DistributionFeeAccountingV2Error("decision predates settlement evidence")
    return DistributionFeeAccountingDecisionV2(decision_id=_text(decision_id,"decision_id"),distribution_plan_digest=plan.digest,distribution_authorization_digest=authorization.digest,distribution_execution_ticket_digest=ticket.digest,distribution_attempt_digest=attempt["digest"],distribution_utilization_digest=u["digest"],receipt_set_digest=canonical_json_digest(sorted(r["receipt_digest"] for r in receipts)),affected_period_id=plan.affected_period_id,reporting_currency=ledger.reporting_currency,settled_principal_total=principal,actual_external_fee_total=fee,actual_payer_cash_outflow=cash,status="POSTABLE" if cash>ZERO and not blockers else "NO_ACTION",blockers=tuple(sorted(blockers)),decided_at=when)


def post_distribution_fee_accounting_v2(ledger:ReportingLedger,*,decision_id:str,principal_event_id:str,fee_event_id:str,plan:DistributionPlanV2,authorization:DistributionAuthorizationV2,ticket:DistributionExecutionTicketV2,attempt_payload:Mapping[str,Any],utilization_payload:Mapping[str,Any],receipt_payloads:Sequence[Mapping[str,Any]],accounts:DistributionFeeAccountingAccountsV2,decided_at:datetime):
    decision=evaluate_distribution_fee_accounting_v2(decision_id=decision_id,ledger=ledger,plan=plan,authorization=authorization,ticket=ticket,attempt_payload=attempt_payload,utilization_payload=utilization_payload,receipt_payloads=receipt_payloads,accounts=accounts,decided_at=decided_at)
    if decision.status!="POSTABLE":raise DistributionFeeAccountingV2Error("accounting evidence not postable: "+",".join(decision.blockers))
    entries=[];u_digest=utilization_payload["digest"]
    if decision.settled_principal_total>ZERO:
        amount=decision.settled_principal_total
        entries.append(ledger.post(event_id=principal_event_id,reference=f"{u_digest}:principal",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine(accounts.distribution_equity_account,debit=amount),ReportingLine(accounts.external_cash_account,credit=amount)),evidence_digest=decision.digest,metadata={"economic_class":"OWNER_DISTRIBUTION","capital_direction":"OUTFLOW","pnl_treatment":"EXCLUDED_FROM_REALIZED_PNL","distribution_fee_accounting_decision_digest":decision.digest,"distribution_utilization_digest":u_digest,"affected_period_id":plan.affected_period_id}))
    if decision.actual_external_fee_total>ZERO:
        fee=decision.actual_external_fee_total
        entries.append(ledger.post(event_id=fee_event_id,reference=f"{u_digest}:external-fee",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine(accounts.settlement_fee_expense_account,debit=fee),ReportingLine(accounts.external_cash_account,credit=fee)),evidence_digest=decision.digest,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE","fee_treatment":FEE_TREATMENT,"distribution_fee_accounting_decision_digest":decision.digest,"distribution_utilization_digest":u_digest,"affected_period_id":plan.affected_period_id}))
    return decision,tuple(entries)
