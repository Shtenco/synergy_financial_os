from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_authorization_v3 import DistributionAuthorizationV3
from .distribution_execution_ticket_v3 import DistributionExecutionTicketV3
from .distribution_fee_accounting_v2 import DistributionFeeAccountingAccountsV2
from .distribution_fee_accounting_v3 import (
    CAPACITY_SCHEMA,
    DistributionFeeAccountingDecisionV3,
    verify_attempt_v3,
    verify_utilization_v3,
)
from .distribution_plan_v3 import DistributionPlanV3
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingEntry, ReportingLedger, ReportingLine

SCHEMA = "distribution.reversal-accounting-decision/v2"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
FEE_REFUND_TREATMENT = "REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE"
REVERSAL_FEE_TREATMENT = "NEW_EXTERNAL_COST_SEPARATE_FROM_RETURNED_PRINCIPAL_AND_FEE_REFUND"


class DistributionReversalAccountingV2Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionReversalAccountingV2Error(f"{name} is required")
    return value.strip()


def _hex(value: Any, name: str) -> str:
    result = _text(value, name).lower()
    if len(result) != 64 or any(ch not in HEX for ch in result):
        raise DistributionReversalAccountingV2Error(f"{name} must be hex64")
    return result


def _dec(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionReversalAccountingV2Error(f"{name} must be canonical decimal text")
    result = finite_decimal(value, name)
    if canonical_decimal_text(result) != value:
        raise DistributionReversalAccountingV2Error(f"{name} is not canonical decimal text")
    if positive and result <= ZERO:
        raise DistributionReversalAccountingV2Error(f"{name} must be strictly positive")
    if result < ZERO:
        raise DistributionReversalAccountingV2Error(f"{name} cannot be negative")
    return result


def _time(value: Any, name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise DistributionReversalAccountingV2Error(f"{name} must be timezone-aware")
        return value.astimezone(UTC)
    text = _text(value, name)
    if not text.endswith("Z"):
        raise DistributionReversalAccountingV2Error(f"{name} must be canonical UTC Z text")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise DistributionReversalAccountingV2Error(f"{name} is not canonical UTC text")
    return parsed


def _verify_digest(payload: Mapping[str, Any], field: str = "digest") -> str:
    supplied = _hex(payload.get(field), field)
    body = dict(payload); body.pop(field, None)
    if canonical_json_digest(body) != supplied:
        raise DistributionReversalAccountingV2Error(f"{field} mismatch")
    return supplied


def _verify_reversal_v2(payload: Mapping[str, Any], *, original_receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.settlement-reversal/v2":
        raise DistributionReversalAccountingV2Error("fee-aware reversal accounting requires settlement-reversal/v2")
    reversal = dict(payload)
    _verify_digest(reversal)
    if original_receipt.get("schema") != "distribution.settlement-receipt/v3" or original_receipt.get("status") != "SETTLED" or original_receipt.get("reconciled") is not True:
        raise DistributionReversalAccountingV2Error("original receipt must be reconciled SETTLED v3")
    expected = {
        "original_distribution_receipt_digest": original_receipt["receipt_digest"],
        "original_settlement_id": original_receipt["settlement_id"],
        "distribution_attempt_digest": original_receipt["distribution_attempt_digest"],
        "distribution_execution_ticket_digest": original_receipt["distribution_execution_ticket_digest"],
        "distribution_authorization_digest": original_receipt["distribution_authorization_digest"],
        "distribution_plan_digest": original_receipt["distribution_plan_digest"],
        "distribution_available_capacity_schema": CAPACITY_SCHEMA,
        "distribution_available_capacity_digest": original_receipt["distribution_available_capacity_digest"],
        "beneficiary_set_digest": original_receipt["beneficiary_set_digest"],
        "beneficiary_id": original_receipt["beneficiary_id"],
        "payment_idempotency_key": original_receipt["payment_idempotency_key"],
        "payer_id": original_receipt["payer_id"],
        "payee_id": original_receipt["payee_id"],
        "asset": original_receipt["asset"],
        "returned_principal_amount": original_receipt["settled_principal_amount"],
        "original_payer_borne_external_fee": original_receipt["payer_borne_external_fee"],
    }
    for field, value in expected.items():
        if reversal.get(field) != value:
            raise DistributionReversalAccountingV2Error(f"reversal mismatch: {field}")
    returned = _dec(reversal.get("returned_principal_amount"), "returned_principal_amount", positive=True)
    original_fee = _dec(reversal.get("original_payer_borne_external_fee"), "original_payer_borne_external_fee")
    refund = _dec(reversal.get("refunded_original_fee"), "refunded_original_fee")
    processing = _dec(reversal.get("reversal_processing_fee"), "reversal_processing_fee")
    gross = _dec(reversal.get("gross_cash_return"), "gross_cash_return", positive=True)
    if refund > original_fee or gross != returned + refund:
        raise DistributionReversalAccountingV2Error("reversal principal/refund formula mismatch")
    if refund > ZERO:
        _hex(reversal.get("fee_refund_evidence_digest"), "fee_refund_evidence_digest")
    elif reversal.get("fee_refund_evidence_digest") is not None:
        raise DistributionReversalAccountingV2Error("zero refund cannot carry refund evidence")
    if processing > ZERO:
        _hex(reversal.get("reversal_fee_evidence_digest"), "reversal_fee_evidence_digest")
    elif reversal.get("reversal_fee_evidence_digest") is not None:
        raise DistributionReversalAccountingV2Error("zero processing fee cannot carry fee evidence")
    if reversal.get("fee_refund_treatment") != FEE_REFUND_TREATMENT or reversal.get("reversal_fee_treatment") != REVERSAL_FEE_TREATMENT:
        raise DistributionReversalAccountingV2Error("reversal fee treatment mismatch")
    if reversal.get("status") != "REVERSED_CONFIRMED":
        raise DistributionReversalAccountingV2Error("unexpected reversal status")
    if _time(reversal.get("observed_at"), "observed_at") <= _time(original_receipt.get("finality_time"), "original finality_time"):
        raise DistributionReversalAccountingV2Error("reversal time-travel")
    _hex(reversal.get("reversal_evidence_digest"), "reversal_evidence_digest")
    if reversal.get("authority") != "SETTLEMENT_REVERSAL_EVIDENCE_ONLY" or reversal.get("settlement_authority") != "Shtenco/synergy_pay_system" or reversal.get("accounting_authority") != "Shtenco/synergy_financial_os":
        raise DistributionReversalAccountingV2Error("reversal authority boundary mismatch")
    if reversal.get("authorization_consumption") != "REMAINS_CONSUMED":
        raise DistributionReversalAccountingV2Error("reversal must not revive authorization")
    if reversal.get("profit_recognition") != "NOT_PERFORMED" or reversal.get("execution_authority") != "NONE":
        raise DistributionReversalAccountingV2Error("MetaPay reversal cannot recognize P&L or execute")
    return reversal


def _find_original_principal_entry(ledger: ReportingLedger, *, decision: DistributionFeeAccountingDecisionV3) -> ReportingEntry:
    matches = [entry for entry in ledger.entries_since(0) if entry.reference == f"{decision.distribution_utilization_digest}:principal:v3" and entry.flow_type == FlowType.EXTERNAL_CAPITAL and entry.evidence_digest == decision.digest and entry.metadata.get("economic_class") == "OWNER_DISTRIBUTION"]
    if len(matches) != 1:
        raise DistributionReversalAccountingV2Error("original v3 principal posting must exist exactly once")
    entry = matches[0]
    if len(entry.lines) != 2:
        raise DistributionReversalAccountingV2Error("original principal posting must have two lines")
    return entry


def _find_original_fee_entry(ledger: ReportingLedger, *, decision: DistributionFeeAccountingDecisionV3, accounts: DistributionFeeAccountingAccountsV2) -> ReportingEntry | None:
    matches = [entry for entry in ledger.entries_since(0) if entry.reference == f"{decision.distribution_utilization_digest}:external-fee:v3" and entry.flow_type == FlowType.EXTERNAL_EXPENSE and entry.evidence_digest == decision.digest and entry.metadata.get("economic_class") == "OWNER_DISTRIBUTION_SETTLEMENT_FEE"]
    if decision.actual_external_fee_total == ZERO:
        if matches:
            raise DistributionReversalAccountingV2Error("zero original fee must not have fee posting")
        return None
    if len(matches) != 1:
        raise DistributionReversalAccountingV2Error("original v3 fee posting must exist exactly once")
    entry = matches[0]
    fee_lines = [line for line in entry.lines if line.account_id == accounts.settlement_fee_expense_account]
    cash_lines = [line for line in entry.lines if line.account_id == accounts.external_cash_account]
    if len(entry.lines) != 2 or len(fee_lines) != 1 or len(cash_lines) != 1:
        raise DistributionReversalAccountingV2Error("original fee posting account lines mismatch")
    amount = decision.actual_external_fee_total
    if fee_lines[0].debit != amount or fee_lines[0].credit != ZERO or cash_lines[0].credit != amount or cash_lines[0].debit != ZERO:
        raise DistributionReversalAccountingV2Error("original fee posting amount mismatch")
    return entry


@dataclass(frozen=True)
class DistributionReversalAccountingDecisionV2:
    decision_id: str
    original_distribution_fee_accounting_decision_digest: str
    original_principal_reporting_entry_digest: str
    original_fee_reporting_entry_digest: str | None
    original_distribution_utilization_digest: str
    original_distribution_receipt_digest: str
    distribution_settlement_reversal_digest: str
    distribution_available_capacity_schema: str
    distribution_available_capacity_digest: str
    beneficiary_id: str
    reporting_currency: str
    returned_principal_amount: Decimal
    refunded_original_fee: Decimal
    reversal_processing_fee: Decimal
    gross_cash_return: Decimal
    net_cash_effect: Decimal
    realized_pnl_effect: Decimal
    status: str
    blockers: tuple[str, ...]
    decided_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_REVERSAL_ACCOUNTING_V2"
    principal_economic_class: str = "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL"
    principal_pnl_treatment: str = "EXCLUDED_FROM_REALIZED_PNL"
    fee_refund_economic_class: str = "OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND"
    fee_refund_pnl_treatment: str = "REALIZED_EXTERNAL_EXPENSE_REVERSAL"
    reversal_fee_economic_class: str = "OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE"
    reversal_fee_pnl_treatment: str = "REALIZED_EXTERNAL_EXPENSE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_REVERSAL_ACCOUNTING_V2" or self.execution_authority != "NONE" or self.ai_authority != "NONE":
            raise DistributionReversalAccountingV2Error("reversal accounting authority mismatch")
        if self.distribution_available_capacity_schema != CAPACITY_SCHEMA:
            raise DistributionReversalAccountingV2Error("reversal accounting requires AvailableCapacity v3 lineage")
        if self.principal_economic_class != "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL" or self.principal_pnl_treatment != "EXCLUDED_FROM_REALIZED_PNL":
            raise DistributionReversalAccountingV2Error("principal reversal semantics drift")
        if self.fee_refund_economic_class != "OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND" or self.fee_refund_pnl_treatment != "REALIZED_EXTERNAL_EXPENSE_REVERSAL":
            raise DistributionReversalAccountingV2Error("fee refund semantics drift")
        if self.reversal_fee_economic_class != "OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE" or self.reversal_fee_pnl_treatment != "REALIZED_EXTERNAL_EXPENSE":
            raise DistributionReversalAccountingV2Error("reversal processing fee semantics drift")
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id"))
        object.__setattr__(self, "beneficiary_id", _text(self.beneficiary_id, "beneficiary_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in ("original_distribution_fee_accounting_decision_digest","original_principal_reporting_entry_digest","original_distribution_utilization_digest","original_distribution_receipt_digest","distribution_settlement_reversal_digest","distribution_available_capacity_digest"):
            object.__setattr__(self, name, _hex(getattr(self, name), name))
        if self.original_fee_reporting_entry_digest is not None:
            object.__setattr__(self, "original_fee_reporting_entry_digest", _hex(self.original_fee_reporting_entry_digest, "original_fee_reporting_entry_digest"))
        for name in ("returned_principal_amount","refunded_original_fee","reversal_processing_fee","gross_cash_return"):
            value = finite_decimal(getattr(self, name), name)
            if value < ZERO or (name in {"returned_principal_amount","gross_cash_return"} and value <= ZERO):
                raise DistributionReversalAccountingV2Error(f"{name} invalid")
            object.__setattr__(self, name, value)
        net = finite_decimal(self.net_cash_effect, "net_cash_effect")
        pnl = finite_decimal(self.realized_pnl_effect, "realized_pnl_effect")
        object.__setattr__(self, "net_cash_effect", net); object.__setattr__(self, "realized_pnl_effect", pnl)
        if self.gross_cash_return != self.returned_principal_amount + self.refunded_original_fee:
            raise DistributionReversalAccountingV2Error("gross cash return formula mismatch")
        if self.net_cash_effect != self.gross_cash_return - self.reversal_processing_fee:
            raise DistributionReversalAccountingV2Error("net cash effect formula mismatch")
        if self.realized_pnl_effect != self.refunded_original_fee - self.reversal_processing_fee:
            raise DistributionReversalAccountingV2Error("realized P&L reversal formula mismatch")
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        if self.status != ("POSTABLE" if not blockers else "NO_ACTION"):
            raise DistributionReversalAccountingV2Error("reversal accounting status mismatch")
        object.__setattr__(self, "decided_at", _time(self.decided_at, "decided_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "decision_id": self.decision_id,
            "original_distribution_fee_accounting_decision_digest": self.original_distribution_fee_accounting_decision_digest,
            "original_principal_reporting_entry_digest": self.original_principal_reporting_entry_digest,
            "original_fee_reporting_entry_digest": self.original_fee_reporting_entry_digest,
            "original_distribution_utilization_digest": self.original_distribution_utilization_digest,
            "original_distribution_receipt_digest": self.original_distribution_receipt_digest,
            "distribution_settlement_reversal_digest": self.distribution_settlement_reversal_digest,
            "distribution_available_capacity_schema": self.distribution_available_capacity_schema,
            "distribution_available_capacity_digest": self.distribution_available_capacity_digest,
            "beneficiary_id": self.beneficiary_id,
            "reporting_currency": self.reporting_currency,
            "returned_principal_amount": canonical_decimal_text(self.returned_principal_amount),
            "refunded_original_fee": canonical_decimal_text(self.refunded_original_fee),
            "reversal_processing_fee": canonical_decimal_text(self.reversal_processing_fee),
            "gross_cash_return": canonical_decimal_text(self.gross_cash_return),
            "net_cash_effect": canonical_decimal_text(self.net_cash_effect),
            "realized_pnl_effect": canonical_decimal_text(self.realized_pnl_effect),
            "status": self.status,
            "blockers": list(self.blockers),
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "principal_economic_class": self.principal_economic_class,
            "principal_pnl_treatment": self.principal_pnl_treatment,
            "fee_refund_economic_class": self.fee_refund_economic_class,
            "fee_refund_pnl_treatment": self.fee_refund_pnl_treatment,
            "reversal_fee_economic_class": self.reversal_fee_economic_class,
            "reversal_fee_pnl_treatment": self.reversal_fee_pnl_treatment,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def evaluate_distribution_reversal_accounting_v2(
    *, decision_id: str, ledger: ReportingLedger, plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3, ticket: DistributionExecutionTicketV3,
    attempt_payload: Mapping[str, Any], utilization_payload: Mapping[str, Any],
    original_receipt_payloads: Sequence[Mapping[str, Any]],
    original_accounting_decision: DistributionFeeAccountingDecisionV3,
    settlement_reversal_payload: Mapping[str, Any], accounts: DistributionFeeAccountingAccountsV2,
    decided_at: datetime,
) -> DistributionReversalAccountingDecisionV2:
    attempt = verify_attempt_v3(attempt_payload, plan=plan, authorization=authorization, ticket=ticket)
    utilization, receipts = verify_utilization_v3(utilization_payload, plan=plan, authorization=authorization, ticket=ticket, attempt=attempt, receipts=original_receipt_payloads)
    if original_accounting_decision.status != "POSTABLE":
        raise DistributionReversalAccountingV2Error("original fee accounting decision was not POSTABLE")
    checks = (
        (original_accounting_decision.distribution_plan_digest, plan.digest, "plan"),
        (original_accounting_decision.distribution_authorization_digest, authorization.digest, "authorization"),
        (original_accounting_decision.distribution_execution_ticket_digest, ticket.digest, "ticket"),
        (original_accounting_decision.distribution_available_capacity_schema, CAPACITY_SCHEMA, "capacity schema"),
        (original_accounting_decision.distribution_available_capacity_digest, plan.distribution_available_capacity_digest, "capacity digest"),
        (original_accounting_decision.distribution_attempt_digest, attempt["digest"], "attempt"),
        (original_accounting_decision.distribution_utilization_digest, utilization["digest"], "utilization"),
        (original_accounting_decision.receipt_set_digest, canonical_json_digest(sorted(item["receipt_digest"] for item in receipts)), "receipt set"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise DistributionReversalAccountingV2Error(f"original accounting decision {label} mismatch")
    if original_accounting_decision.settled_principal_total != finite_decimal(utilization["settled_principal_total"], "settled principal") or original_accounting_decision.actual_external_fee_total != finite_decimal(utilization["actual_external_fee_total"], "actual fee"):
        raise DistributionReversalAccountingV2Error("original accounting decision economics mismatch")
    if ledger.reporting_currency != plan.distribution_currency:
        raise DistributionReversalAccountingV2Error("ledger/reporting currency mismatch")
    cash_spec = ledger.account(accounts.external_cash_account); equity_spec = ledger.account(accounts.distribution_equity_account); fee_spec = ledger.account(accounts.settlement_fee_expense_account)
    if cash_spec.account_class != AccountClass.ASSET or cash_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionReversalAccountingV2Error("cash account must be EXTERNAL ASSET")
    if equity_spec.account_class != AccountClass.EQUITY or equity_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionReversalAccountingV2Error("distribution account must be EXTERNAL EQUITY")
    if fee_spec.account_class != AccountClass.EXPENSE or fee_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionReversalAccountingV2Error("settlement fee account must be EXTERNAL EXPENSE")
    principal_entry = _find_original_principal_entry(ledger, decision=original_accounting_decision)
    fee_entry = _find_original_fee_entry(ledger, decision=original_accounting_decision, accounts=accounts)
    receipt_digest = settlement_reversal_payload.get("original_distribution_receipt_digest")
    matching = [receipt for receipt in receipts if receipt["receipt_digest"] == receipt_digest]
    if len(matching) != 1:
        raise DistributionReversalAccountingV2Error("reversal original receipt not uniquely present in v3 receipt set")
    original_receipt = matching[0]
    reversal = _verify_reversal_v2(settlement_reversal_payload, original_receipt=original_receipt)
    refund = _dec(reversal["refunded_original_fee"], "refunded_original_fee")
    if refund > ZERO and fee_entry is None:
        raise DistributionReversalAccountingV2Error("original fee refund requires canonical original fee posting")
    prior = [entry for entry in ledger.entries_since(0) if entry.metadata.get("original_distribution_receipt_digest") == original_receipt["receipt_digest"] and entry.metadata.get("economic_class") in {"OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL","OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND","OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE"}]
    blockers: list[str] = []
    if prior:
        blockers.append("ORIGINAL_DISTRIBUTION_RECEIPT_ALREADY_REVERSED_IN_LEDGER")
    when = _time(decided_at, "decided_at")
    if when < _time(reversal["observed_at"], "reversal.observed_at"):
        raise DistributionReversalAccountingV2Error("accounting decision predates reversal evidence")
    returned = _dec(reversal["returned_principal_amount"], "returned_principal_amount", positive=True)
    processing = _dec(reversal["reversal_processing_fee"], "reversal_processing_fee")
    gross = returned + refund
    return DistributionReversalAccountingDecisionV2(
        decision_id=decision_id,
        original_distribution_fee_accounting_decision_digest=original_accounting_decision.digest,
        original_principal_reporting_entry_digest=principal_entry.digest,
        original_fee_reporting_entry_digest=fee_entry.digest if fee_entry is not None else None,
        original_distribution_utilization_digest=utilization["digest"],
        original_distribution_receipt_digest=original_receipt["receipt_digest"],
        distribution_settlement_reversal_digest=reversal["digest"],
        distribution_available_capacity_schema=CAPACITY_SCHEMA,
        distribution_available_capacity_digest=plan.distribution_available_capacity_digest,
        beneficiary_id=original_receipt["beneficiary_id"], reporting_currency=ledger.reporting_currency,
        returned_principal_amount=returned, refunded_original_fee=refund, reversal_processing_fee=processing,
        gross_cash_return=gross, net_cash_effect=gross-processing, realized_pnl_effect=refund-processing,
        status="POSTABLE" if not blockers else "NO_ACTION", blockers=tuple(blockers), decided_at=when,
    )


def post_distribution_reversal_accounting_v2(
    ledger: ReportingLedger, *, decision_id: str, principal_event_id: str,
    fee_refund_event_id: str, reversal_fee_event_id: str,
    plan: DistributionPlanV3, authorization: DistributionAuthorizationV3, ticket: DistributionExecutionTicketV3,
    attempt_payload: Mapping[str, Any], utilization_payload: Mapping[str, Any], original_receipt_payloads: Sequence[Mapping[str, Any]],
    original_accounting_decision: DistributionFeeAccountingDecisionV3, settlement_reversal_payload: Mapping[str, Any],
    accounts: DistributionFeeAccountingAccountsV2, decided_at: datetime,
) -> tuple[DistributionReversalAccountingDecisionV2, tuple[ReportingEntry, ...]]:
    decision = evaluate_distribution_reversal_accounting_v2(
        decision_id=decision_id, ledger=ledger, plan=plan, authorization=authorization, ticket=ticket,
        attempt_payload=attempt_payload, utilization_payload=utilization_payload,
        original_receipt_payloads=original_receipt_payloads, original_accounting_decision=original_accounting_decision,
        settlement_reversal_payload=settlement_reversal_payload, accounts=accounts, decided_at=decided_at,
    )
    if decision.status != "POSTABLE":
        raise DistributionReversalAccountingV2Error("distribution reversal accounting not postable: " + ",".join(decision.blockers))
    reversal_digest = settlement_reversal_payload["digest"]
    common = {
        "distribution_reversal_accounting_decision_digest": decision.digest,
        "original_distribution_fee_accounting_decision_digest": original_accounting_decision.digest,
        "original_distribution_utilization_digest": decision.original_distribution_utilization_digest,
        "original_distribution_receipt_digest": decision.original_distribution_receipt_digest,
        "distribution_settlement_reversal_digest": decision.distribution_settlement_reversal_digest,
        "distribution_available_capacity_schema": CAPACITY_SCHEMA,
        "distribution_available_capacity_digest": decision.distribution_available_capacity_digest,
        "beneficiary_id": decision.beneficiary_id,
        "affected_period_id": plan.affected_period_id,
    }
    entries: list[ReportingEntry] = []
    amount = decision.returned_principal_amount
    entries.append(ledger.post(
        event_id=principal_event_id, reference=f"{reversal_digest}:principal-return:v2", flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine(accounts.external_cash_account, debit=amount), ReportingLine(accounts.distribution_equity_account, credit=amount)),
        evidence_digest=decision.digest,
        metadata={**common, "economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL", "capital_direction":"INFLOW_REVERSAL_OF_PRIOR_OUTFLOW", "pnl_treatment":"EXCLUDED_FROM_REALIZED_PNL", "original_distribution_reporting_entry_digest":decision.original_principal_reporting_entry_digest},
    ))
    if decision.refunded_original_fee > ZERO:
        refund = decision.refunded_original_fee
        entries.append(ledger.post(
            event_id=fee_refund_event_id, reference=f"{reversal_digest}:original-fee-refund:v2", flow_type=FlowType.EXTERNAL_EXPENSE,
            lines=(ReportingLine(accounts.external_cash_account, debit=refund), ReportingLine(accounts.settlement_fee_expense_account, credit=refund)),
            evidence_digest=decision.digest,
            metadata={**common, "economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND", "pnl_treatment":"REALIZED_EXTERNAL_EXPENSE_REVERSAL", "fee_refund_treatment":FEE_REFUND_TREATMENT, "original_fee_reporting_entry_digest":decision.original_fee_reporting_entry_digest},
        ))
    if decision.reversal_processing_fee > ZERO:
        fee = decision.reversal_processing_fee
        entries.append(ledger.post(
            event_id=reversal_fee_event_id, reference=f"{reversal_digest}:processing-fee:v2", flow_type=FlowType.EXTERNAL_EXPENSE,
            lines=(ReportingLine(accounts.settlement_fee_expense_account, debit=fee), ReportingLine(accounts.external_cash_account, credit=fee)),
            evidence_digest=decision.digest,
            metadata={**common, "economic_class":"OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE", "pnl_treatment":"REALIZED_EXTERNAL_EXPENSE", "fee_treatment":REVERSAL_FEE_TREATMENT},
        ))
    return decision, tuple(entries)
