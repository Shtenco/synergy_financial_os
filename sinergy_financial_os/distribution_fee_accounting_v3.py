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
from .distribution_plan_v3 import DistributionPlanV3
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingLedger, ReportingLine

ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
CAPACITY_SCHEMA = "distribution.available-capacity/v3"
TERMINAL = frozenset({"SETTLED", "FAILED", "REVERSED"})
UTIL_STATUSES = frozenset({
    "FULLY_SETTLED",
    "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN",
    "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION",
})
FEE_TREATMENT = "EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT"
UNUSED_FEE_TREATMENT = "UNUTILIZED_AUTHORIZED_CAPACITY_NOT_PROFIT"


class DistributionFeeAccountingV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionFeeAccountingV3Error(f"{name} is required")
    return value.strip()


def _hex(value: Any, name: str) -> str:
    result = _text(value, name).lower()
    if len(result) != 64 or any(ch not in HEX for ch in result):
        raise DistributionFeeAccountingV3Error(f"{name} must be hex64")
    return result


def _dec(value: Any, name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionFeeAccountingV3Error(f"{name} must be canonical decimal text")
    result = finite_decimal(value, name)
    if canonical_decimal_text(result) != value:
        raise DistributionFeeAccountingV3Error(f"{name} non-canonical")
    if nonnegative and result < ZERO:
        raise DistributionFeeAccountingV3Error(f"{name} negative")
    return result


def _parse_time(value: Any, name: str) -> datetime:
    text = _text(value, name)
    if not text.endswith("Z"):
        raise DistributionFeeAccountingV3Error(f"{name} must be UTC Z")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise DistributionFeeAccountingV3Error(f"{name} non-canonical")
    return parsed


def _verify_digest(payload: Mapping[str, Any], field: str = "digest") -> str:
    supplied = _hex(payload.get(field), field)
    body = dict(payload)
    body.pop(field, None)
    if canonical_json_digest(body) != supplied:
        raise DistributionFeeAccountingV3Error(f"{field} mismatch")
    return supplied


def _require_v3_financial_context(
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
) -> None:
    if not isinstance(plan, DistributionPlanV3) or not isinstance(authorization, DistributionAuthorizationV3) or not isinstance(ticket, DistributionExecutionTicketV3):
        raise DistributionFeeAccountingV3Error("accounting v3 requires Financial OS Plan/Auth/Ticket v3")
    if plan.distribution_available_capacity_schema != CAPACITY_SCHEMA:
        raise DistributionFeeAccountingV3Error("plan does not bind AvailableCapacity v3")
    if authorization.distribution_available_capacity_schema != CAPACITY_SCHEMA or ticket.distribution_available_capacity_schema != CAPACITY_SCHEMA:
        raise DistributionFeeAccountingV3Error("authorization/ticket capacity schema mismatch")
    if authorization.distribution_plan_digest != plan.digest:
        raise DistributionFeeAccountingV3Error("authorization / plan context mismatch")
    if authorization.distribution_available_capacity_digest != plan.distribution_available_capacity_digest:
        raise DistributionFeeAccountingV3Error("authorization / capacity context mismatch")
    if ticket.distribution_plan_digest != plan.digest or ticket.distribution_authorization_digest != authorization.digest:
        raise DistributionFeeAccountingV3Error("ticket / plan/auth context mismatch")
    if ticket.distribution_available_capacity_digest != plan.distribution_available_capacity_digest:
        raise DistributionFeeAccountingV3Error("ticket / capacity context mismatch")


def verify_attempt_v3(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
) -> dict[str, Any]:
    _require_v3_financial_context(plan, authorization, ticket)
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.batch-attempt/v3":
        raise DistributionFeeAccountingV3Error("unsupported attempt schema; v3 required")
    item = dict(payload)
    _verify_digest(item)
    expected = {
        "distribution_plan_digest": plan.digest,
        "distribution_authorization_digest": authorization.digest,
        "distribution_execution_ticket_digest": ticket.digest,
        "distribution_available_capacity_schema": CAPACITY_SCHEMA,
        "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
        "beneficiary_set_digest": plan.beneficiary_set_digest,
        "source_account_id": plan.source_account_id,
        "distribution_currency": plan.distribution_currency,
        "planned_principal_total": canonical_decimal_text(plan.principal_total),
        "authorized_external_fee_budget": canonical_decimal_text(plan.external_fee_budget),
        "authorized_total_outflow_ceiling": canonical_decimal_text(plan.total_authorized_outflow_ceiling),
    }
    for key, value in expected.items():
        if item.get(key) != value:
            raise DistributionFeeAccountingV3Error(f"attempt mismatch: {key}")
    if item.get("status") != "AUTHORIZATION_CONSUMED_FOR_FEE_AWARE_ATTEMPT_V3":
        raise DistributionFeeAccountingV3Error("attempt state mismatch")
    if item.get("authorization_consumption") != "CONSUMED":
        raise DistributionFeeAccountingV3Error("authorization must remain consumed")
    if item.get("authority") != "METAPAY_DISTRIBUTION_HANDOFF_V3" or item.get("execution_authority") != "EXISTING_METAPAY_STATE_MACHINE":
        raise DistributionFeeAccountingV3Error("attempt execution authority mismatch")
    if item.get("accounting_authority") != "NONE" or item.get("profit_recognition") != "NOT_PERFORMED":
        raise DistributionFeeAccountingV3Error("MetaPay attempt cannot account or recognize profit")
    bindings = item.get("intent_bindings")
    if not isinstance(bindings, list) or len(bindings) != len(plan.beneficiaries):
        raise DistributionFeeAccountingV3Error("attempt must bind every beneficiary")
    by_id = {beneficiary.beneficiary_id: beneficiary for beneficiary in plan.beneficiaries}
    seen: set[str] = set()
    principal_total = ZERO
    for raw in bindings:
        if not isinstance(raw, Mapping):
            raise DistributionFeeAccountingV3Error("attempt binding must be object")
        bid = _text(raw.get("beneficiary_id"), "beneficiary_id")
        if bid in seen or bid not in by_id:
            raise DistributionFeeAccountingV3Error("attempt beneficiary duplicate/unknown")
        seen.add(bid)
        beneficiary = by_id[bid]
        amount = _dec(raw.get("principal_amount"), "principal_amount", nonnegative=True)
        if amount != beneficiary.amount or amount <= ZERO:
            raise DistributionFeeAccountingV3Error("attempt changed beneficiary principal")
        if raw.get("destination_id") != beneficiary.destination_id or raw.get("payment_idempotency_key") != beneficiary.payment_idempotency_key:
            raise DistributionFeeAccountingV3Error("attempt changed beneficiary destination/idempotency")
        _text(raw.get("intent_id"), "intent_id")
        _hex(raw.get("intent_binding_digest"), "intent_binding_digest")
        principal_total += amount
    if principal_total != plan.principal_total:
        raise DistributionFeeAccountingV3Error("attempt principal total mismatch")
    return item


def verify_receipt_v3(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
    attempt: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.settlement-receipt/v3":
        raise DistributionFeeAccountingV3Error("unsupported receipt schema; v3 required")
    item = dict(payload)
    _verify_digest(item, "receipt_digest")
    lineage = {
        "distribution_attempt_digest": attempt["digest"],
        "distribution_plan_digest": plan.digest,
        "distribution_authorization_digest": authorization.digest,
        "distribution_execution_ticket_digest": ticket.digest,
        "distribution_available_capacity_schema": CAPACITY_SCHEMA,
        "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
        "beneficiary_set_digest": plan.beneficiary_set_digest,
    }
    for key, value in lineage.items():
        if item.get(key) != value:
            raise DistributionFeeAccountingV3Error(f"receipt mismatch: {key}")
    bid = _text(item.get("beneficiary_id"), "beneficiary_id")
    matches = [beneficiary for beneficiary in plan.beneficiaries if beneficiary.beneficiary_id == bid]
    if len(matches) != 1:
        raise DistributionFeeAccountingV3Error("receipt beneficiary unknown")
    beneficiary = matches[0]
    if item.get("payer_id") != plan.source_account_id or item.get("payee_id") != beneficiary.destination_id:
        raise DistributionFeeAccountingV3Error("receipt payer/payee mismatch")
    if item.get("asset") != plan.distribution_currency or item.get("payment_idempotency_key") != beneficiary.payment_idempotency_key:
        raise DistributionFeeAccountingV3Error("receipt asset/idempotency mismatch")
    planned = _dec(item.get("planned_principal_amount"), "planned_principal_amount", nonnegative=True)
    settled = _dec(item.get("settled_principal_amount"), "settled_principal_amount", nonnegative=True)
    fee = _dec(item.get("payer_borne_external_fee"), "payer_borne_external_fee", nonnegative=True)
    fee_budget = _dec(item.get("authorized_external_fee_budget"), "authorized_external_fee_budget", nonnegative=True)
    cash = _dec(item.get("payer_cash_outflow"), "payer_cash_outflow", nonnegative=True)
    ceiling = _dec(item.get("authorized_total_outflow_ceiling"), "authorized_total_outflow_ceiling", nonnegative=True)
    if planned != beneficiary.amount or fee_budget != plan.external_fee_budget or ceiling != plan.total_authorized_outflow_ceiling:
        raise DistributionFeeAccountingV3Error("receipt changed planned economics")
    status = item.get("status")
    if status not in TERMINAL:
        raise DistributionFeeAccountingV3Error("receipt non-terminal")
    if settled != (planned if status == "SETTLED" else ZERO):
        raise DistributionFeeAccountingV3Error("settled principal/status mismatch")
    if fee > fee_budget or cash != settled + fee or cash > ceiling:
        raise DistributionFeeAccountingV3Error("receipt fee/cash ceiling mismatch")
    if item.get("fee_treatment") != FEE_TREATMENT:
        raise DistributionFeeAccountingV3Error("receipt fee treatment mismatch")
    if item.get("authority") != "SETTLEMENT_EVIDENCE_ONLY" or item.get("settlement_authority") != "Shtenco/synergy_pay_system":
        raise DistributionFeeAccountingV3Error("receipt settlement authority mismatch")
    if item.get("accounting_authority") != "Shtenco/synergy_financial_os" or item.get("profit_recognition") != "NOT_PERFORMED" or item.get("execution_authority") != "NONE":
        raise DistributionFeeAccountingV3Error("receipt accounting/execution boundary mismatch")
    if item.get("authorization_consumption") != "CONSUMED_BY_BATCH_ATTEMPT":
        raise DistributionFeeAccountingV3Error("receipt cannot unconsume authorization")
    if fee > ZERO:
        _hex(item.get("external_fee_evidence_digest"), "external_fee_evidence_digest")
    elif item.get("external_fee_evidence_digest") is not None:
        raise DistributionFeeAccountingV3Error("zero fee cannot carry fee evidence")
    _hex(item.get("settlement_evidence_digest"), "settlement_evidence_digest")
    _parse_time(item.get("finality_time"), "finality_time")
    return item


def verify_utilization_v3(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
    attempt: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.utilization/v3":
        raise DistributionFeeAccountingV3Error("unsupported utilization schema; v3 required")
    utilization = dict(payload)
    _verify_digest(utilization)
    lineage = {
        "distribution_attempt_digest": attempt["digest"],
        "distribution_plan_digest": plan.digest,
        "distribution_authorization_digest": authorization.digest,
        "distribution_execution_ticket_digest": ticket.digest,
        "distribution_available_capacity_schema": CAPACITY_SCHEMA,
        "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
        "beneficiary_set_digest": plan.beneficiary_set_digest,
    }
    for key, value in lineage.items():
        if utilization.get(key) != value:
            raise DistributionFeeAccountingV3Error(f"utilization mismatch: {key}")
    verified_receipts = tuple(
        verify_receipt_v3(raw, plan=plan, authorization=authorization, ticket=ticket, attempt=attempt)
        for raw in receipts
    )
    if len(verified_receipts) != len(plan.beneficiaries):
        raise DistributionFeeAccountingV3Error("one receipt per beneficiary required")
    receipt_set = tuple(sorted(receipt["receipt_digest"] for receipt in verified_receipts))
    if tuple(utilization.get("receipt_digests") or ()) != receipt_set:
        raise DistributionFeeAccountingV3Error("utilization receipt set mismatch")
    settled = sum((_dec(receipt["settled_principal_amount"], "settled", nonnegative=True) for receipt in verified_receipts), ZERO)
    fee = sum((_dec(receipt["payer_borne_external_fee"], "fee", nonnegative=True) for receipt in verified_receipts), ZERO)
    cash = settled + fee
    expected = {
        "planned_principal_total": canonical_decimal_text(plan.principal_total),
        "settled_principal_total": canonical_decimal_text(settled),
        "authorized_external_fee_budget": canonical_decimal_text(plan.external_fee_budget),
        "actual_external_fee_total": canonical_decimal_text(fee),
        "unused_external_fee_budget": canonical_decimal_text(plan.external_fee_budget - fee),
        "authorized_total_outflow_ceiling": canonical_decimal_text(plan.total_authorized_outflow_ceiling),
        "actual_payer_cash_outflow": canonical_decimal_text(cash),
    }
    for key, value in expected.items():
        if utilization.get(key) != value:
            raise DistributionFeeAccountingV3Error(f"utilization economics mismatch: {key}")
    if fee > plan.external_fee_budget or cash > plan.total_authorized_outflow_ceiling:
        raise DistributionFeeAccountingV3Error("utilization exceeds authorized fee/outflow ceiling")
    if utilization.get("status") not in UTIL_STATUSES:
        raise DistributionFeeAccountingV3Error("utilization status mismatch")
    if utilization.get("authorization_consumption") != "CONSUMED" or utilization.get("authority") != "METAPAY_DISTRIBUTION_UTILIZATION_V3":
        raise DistributionFeeAccountingV3Error("utilization authorization/authority mismatch")
    if utilization.get("accounting_authority") != "REFERENCE_ONLY" or utilization.get("profit_recognition") != "NOT_PERFORMED":
        raise DistributionFeeAccountingV3Error("MetaPay utilization cannot account or recognize profit")
    if utilization.get("unused_fee_budget_treatment") != UNUSED_FEE_TREATMENT or utilization.get("execution_authority") != "NONE":
        raise DistributionFeeAccountingV3Error("utilization fee/execution treatment mismatch")
    return utilization, verified_receipts


@dataclass(frozen=True)
class DistributionFeeAccountingDecisionV3:
    decision_id: str
    distribution_plan_digest: str
    distribution_authorization_digest: str
    distribution_execution_ticket_digest: str
    distribution_available_capacity_schema: str
    distribution_available_capacity_digest: str
    distribution_attempt_digest: str
    distribution_utilization_digest: str
    receipt_set_digest: str
    affected_period_id: str
    reporting_currency: str
    settled_principal_total: Decimal
    actual_external_fee_total: Decimal
    actual_payer_cash_outflow: Decimal
    status: str
    blockers: tuple[str, ...]
    decided_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_FEE_ACCOUNTING_V3"
    principal_economic_class: str = "OWNER_DISTRIBUTION"
    principal_pnl_treatment: str = "EXCLUDED_FROM_REALIZED_PNL"
    fee_economic_class: str = "OWNER_DISTRIBUTION_SETTLEMENT_FEE"
    fee_pnl_treatment: str = "REALIZED_EXTERNAL_EXPENSE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": "distribution.fee-accounting-decision/v3",
            "decision_id": self.decision_id,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_authorization_digest": self.distribution_authorization_digest,
            "distribution_execution_ticket_digest": self.distribution_execution_ticket_digest,
            "distribution_available_capacity_schema": self.distribution_available_capacity_schema,
            "distribution_available_capacity_digest": self.distribution_available_capacity_digest,
            "distribution_attempt_digest": self.distribution_attempt_digest,
            "distribution_utilization_digest": self.distribution_utilization_digest,
            "receipt_set_digest": self.receipt_set_digest,
            "affected_period_id": self.affected_period_id,
            "reporting_currency": self.reporting_currency,
            "settled_principal_total": canonical_decimal_text(self.settled_principal_total),
            "actual_external_fee_total": canonical_decimal_text(self.actual_external_fee_total),
            "actual_payer_cash_outflow": canonical_decimal_text(self.actual_payer_cash_outflow),
            "status": self.status,
            "blockers": list(self.blockers),
            "decided_at": self.decided_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "principal_economic_class": self.principal_economic_class,
            "principal_pnl_treatment": self.principal_pnl_treatment,
            "fee_economic_class": self.fee_economic_class,
            "fee_pnl_treatment": self.fee_pnl_treatment,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def evaluate_distribution_fee_accounting_v3(
    *,
    decision_id: str,
    ledger: ReportingLedger,
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    receipt_payloads: Sequence[Mapping[str, Any]],
    accounts: DistributionFeeAccountingAccountsV2,
    decided_at: datetime,
) -> DistributionFeeAccountingDecisionV3:
    _require_v3_financial_context(plan, authorization, ticket)
    if ledger.reporting_currency != plan.distribution_currency:
        raise DistributionFeeAccountingV3Error("ledger/reporting currency mismatch")
    attempt = verify_attempt_v3(attempt_payload, plan=plan, authorization=authorization, ticket=ticket)
    utilization, receipts = verify_utilization_v3(
        utilization_payload,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt=attempt,
        receipts=receipt_payloads,
    )
    cash_spec = ledger.account(accounts.external_cash_account)
    equity_spec = ledger.account(accounts.distribution_equity_account)
    fee_spec = ledger.account(accounts.settlement_fee_expense_account)
    if cash_spec.account_class != AccountClass.ASSET or cash_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionFeeAccountingV3Error("cash account must be EXTERNAL ASSET")
    if equity_spec.account_class != AccountClass.EQUITY or equity_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionFeeAccountingV3Error("distribution account must be EXTERNAL EQUITY")
    if fee_spec.account_class != AccountClass.EXPENSE or fee_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionFeeAccountingV3Error("settlement fee account must be EXTERNAL EXPENSE")
    principal = _dec(utilization["settled_principal_total"], "settled principal", nonnegative=True)
    fee = _dec(utilization["actual_external_fee_total"], "actual fee", nonnegative=True)
    cash = principal + fee
    blockers: list[str] = []
    if cash <= ZERO:
        blockers.append("NO_EXTERNAL_CASH_EFFECT")
    latest = max(_parse_time(receipt["finality_time"], "receipt.finality_time") for receipt in receipts)
    when = decided_at.astimezone(UTC)
    if when < latest:
        raise DistributionFeeAccountingV3Error("decision predates settlement evidence")
    return DistributionFeeAccountingDecisionV3(
        decision_id=_text(decision_id, "decision_id"),
        distribution_plan_digest=plan.digest,
        distribution_authorization_digest=authorization.digest,
        distribution_execution_ticket_digest=ticket.digest,
        distribution_available_capacity_schema=CAPACITY_SCHEMA,
        distribution_available_capacity_digest=plan.distribution_available_capacity_digest,
        distribution_attempt_digest=attempt["digest"],
        distribution_utilization_digest=utilization["digest"],
        receipt_set_digest=canonical_json_digest(sorted(receipt["receipt_digest"] for receipt in receipts)),
        affected_period_id=plan.affected_period_id,
        reporting_currency=ledger.reporting_currency,
        settled_principal_total=principal,
        actual_external_fee_total=fee,
        actual_payer_cash_outflow=cash,
        status="POSTABLE" if cash > ZERO and not blockers else "NO_ACTION",
        blockers=tuple(sorted(blockers)),
        decided_at=when,
    )


def post_distribution_fee_accounting_v3(
    ledger: ReportingLedger,
    *,
    decision_id: str,
    principal_event_id: str,
    fee_event_id: str,
    plan: DistributionPlanV3,
    authorization: DistributionAuthorizationV3,
    ticket: DistributionExecutionTicketV3,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    receipt_payloads: Sequence[Mapping[str, Any]],
    accounts: DistributionFeeAccountingAccountsV2,
    decided_at: datetime,
) -> tuple[DistributionFeeAccountingDecisionV3, tuple[Any, ...]]:
    decision = evaluate_distribution_fee_accounting_v3(
        decision_id=decision_id,
        ledger=ledger,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt_payload=attempt_payload,
        utilization_payload=utilization_payload,
        receipt_payloads=receipt_payloads,
        accounts=accounts,
        decided_at=decided_at,
    )
    if decision.status != "POSTABLE":
        raise DistributionFeeAccountingV3Error("accounting evidence not postable: " + ",".join(decision.blockers))
    entries = []
    utilization_digest = utilization_payload["digest"]
    if decision.settled_principal_total > ZERO:
        amount = decision.settled_principal_total
        entries.append(ledger.post(
            event_id=principal_event_id,
            reference=f"{utilization_digest}:principal:v3",
            flow_type=FlowType.EXTERNAL_CAPITAL,
            lines=(
                ReportingLine(accounts.distribution_equity_account, debit=amount),
                ReportingLine(accounts.external_cash_account, credit=amount),
            ),
            evidence_digest=decision.digest,
            metadata={
                "economic_class": "OWNER_DISTRIBUTION",
                "capital_direction": "OUTFLOW",
                "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
                "distribution_fee_accounting_decision_digest": decision.digest,
                "distribution_utilization_digest": utilization_digest,
                "distribution_available_capacity_schema": CAPACITY_SCHEMA,
                "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
                "affected_period_id": plan.affected_period_id,
            },
        ))
    if decision.actual_external_fee_total > ZERO:
        fee = decision.actual_external_fee_total
        entries.append(ledger.post(
            event_id=fee_event_id,
            reference=f"{utilization_digest}:external-fee:v3",
            flow_type=FlowType.EXTERNAL_EXPENSE,
            lines=(
                ReportingLine(accounts.settlement_fee_expense_account, debit=fee),
                ReportingLine(accounts.external_cash_account, credit=fee),
            ),
            evidence_digest=decision.digest,
            metadata={
                "economic_class": "OWNER_DISTRIBUTION_SETTLEMENT_FEE",
                "pnl_treatment": "REALIZED_EXTERNAL_EXPENSE",
                "fee_treatment": FEE_TREATMENT,
                "distribution_fee_accounting_decision_digest": decision.digest,
                "distribution_utilization_digest": utilization_digest,
                "distribution_available_capacity_schema": CAPACITY_SCHEMA,
                "distribution_available_capacity_digest": plan.distribution_available_capacity_digest,
                "affected_period_id": plan.affected_period_id,
            },
        ))
    return decision, tuple(entries)
