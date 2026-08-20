from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from .distribution_plan_v1 import DistributionPlanV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, ReportingLedger


SCHEMA = "distribution.accounting-decision/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
TERMINAL_STATUSES = frozenset({"SETTLED", "FAILED", "REVERSED"})
UTILIZATION_STATUSES = frozenset({
    "FULLY_SETTLED",
    "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN",
    "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION",
})


class DistributionAccountingV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionAccountingV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionAccountingV1Error(f"{field_name} must be hex64")
    return result


def _decimal_text(value: Any, field_name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionAccountingV1Error(f"{field_name} must be canonical decimal text")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
        raise DistributionAccountingV1Error(f"{field_name} is not canonical decimal text")
    if nonnegative and result < ZERO:
        raise DistributionAccountingV1Error(f"{field_name} must be non-negative")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionAccountingV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise DistributionAccountingV1Error(f"{field_name} must use canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DistributionAccountingV1Error(f"{field_name} is invalid") from exc
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise DistributionAccountingV1Error(f"{field_name} is not canonical UTC text")
    return parsed.astimezone(UTC)


def _verify_digest(payload: Mapping[str, Any], field_name: str = "digest") -> str:
    supplied = _hex64(payload.get(field_name), field_name)
    body = dict(payload)
    body.pop(field_name, None)
    if canonical_json_digest(body) != supplied:
        raise DistributionAccountingV1Error(f"{field_name} mismatch")
    return supplied


def verify_distribution_batch_attempt_for_accounting_v1(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.batch-attempt/v1":
        raise DistributionAccountingV1Error("unsupported distribution batch-attempt schema")
    attempt = dict(payload)
    _verify_digest(attempt)
    if attempt.get("distribution_plan_digest") != plan.digest:
        raise DistributionAccountingV1Error("batch attempt / DistributionPlan mismatch")
    if attempt.get("distribution_authorization_digest") != authorization.digest:
        raise DistributionAccountingV1Error("batch attempt / DistributionAuthorization mismatch")
    if attempt.get("distribution_execution_ticket_digest") != ticket.digest:
        raise DistributionAccountingV1Error("batch attempt / ExecutionTicket mismatch")
    if attempt.get("beneficiary_set_digest") != plan.beneficiary_set_digest:
        raise DistributionAccountingV1Error("batch attempt beneficiary-set mismatch")
    if attempt.get("source_account_id") != plan.source_account_id:
        raise DistributionAccountingV1Error("batch attempt source-account mismatch")
    if attempt.get("distribution_currency") != plan.distribution_currency:
        raise DistributionAccountingV1Error("batch attempt currency mismatch")
    if attempt.get("total_amount") != canonical_decimal_text(plan.total_amount):
        raise DistributionAccountingV1Error("batch attempt total mismatch")
    if attempt.get("authorization_consumption") != "CONSUMED":
        raise DistributionAccountingV1Error("batch attempt must consume authorization")
    if attempt.get("status") != "AUTHORIZATION_CONSUMED_FOR_ATTEMPT":
        raise DistributionAccountingV1Error("unexpected batch attempt status")
    if attempt.get("authority") != "METAPAY_DISTRIBUTION_HANDOFF":
        raise DistributionAccountingV1Error("unexpected batch attempt authority")
    if attempt.get("accounting_authority") != "NONE":
        raise DistributionAccountingV1Error("MetaPay batch attempt cannot claim accounting authority")
    bindings = attempt.get("intent_bindings")
    if not isinstance(bindings, list) or len(bindings) != len(plan.beneficiaries):
        raise DistributionAccountingV1Error("batch attempt must bind every beneficiary exactly once")
    by_beneficiary = {item.beneficiary_id: item for item in plan.beneficiaries}
    seen: set[str] = set()
    for raw in bindings:
        if not isinstance(raw, Mapping):
            raise DistributionAccountingV1Error("batch intent binding must be object")
        beneficiary_id = _text(raw.get("beneficiary_id"), "beneficiary_id")
        if beneficiary_id in seen or beneficiary_id not in by_beneficiary:
            raise DistributionAccountingV1Error("batch intent beneficiary duplicate/unknown")
        seen.add(beneficiary_id)
        expected = by_beneficiary[beneficiary_id]
        if raw.get("destination_id") != expected.destination_id:
            raise DistributionAccountingV1Error("batch intent destination mismatch")
        if raw.get("amount") != canonical_decimal_text(expected.amount):
            raise DistributionAccountingV1Error("batch intent amount mismatch")
        if raw.get("payment_idempotency_key") != expected.payment_idempotency_key:
            raise DistributionAccountingV1Error("batch intent idempotency mismatch")
        _text(raw.get("intent_id"), "intent_id")
        _hex64(raw.get("intent_binding_digest"), "intent_binding_digest")
    return attempt


def verify_distribution_settlement_receipt_for_accounting_v1(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.settlement-receipt/v1":
        raise DistributionAccountingV1Error("unsupported distribution settlement receipt schema")
    receipt = dict(payload)
    _verify_digest(receipt, "receipt_digest")
    if receipt.get("distribution_attempt_digest") != attempt.get("digest"):
        raise DistributionAccountingV1Error("distribution receipt / attempt mismatch")
    if receipt.get("distribution_plan_digest") != plan.digest:
        raise DistributionAccountingV1Error("distribution receipt / plan mismatch")
    if receipt.get("distribution_authorization_digest") != authorization.digest:
        raise DistributionAccountingV1Error("distribution receipt / authorization mismatch")
    if receipt.get("distribution_execution_ticket_digest") != ticket.digest:
        raise DistributionAccountingV1Error("distribution receipt / ticket mismatch")
    if receipt.get("beneficiary_set_digest") != plan.beneficiary_set_digest:
        raise DistributionAccountingV1Error("distribution receipt beneficiary-set mismatch")
    beneficiary_id = _text(receipt.get("beneficiary_id"), "beneficiary_id")
    matches = [item for item in plan.beneficiaries if item.beneficiary_id == beneficiary_id]
    if len(matches) != 1:
        raise DistributionAccountingV1Error("distribution receipt beneficiary not in plan")
    beneficiary = matches[0]
    if receipt.get("payer_id") != plan.source_account_id:
        raise DistributionAccountingV1Error("distribution receipt payer/source mismatch")
    if receipt.get("payee_id") != beneficiary.destination_id:
        raise DistributionAccountingV1Error("distribution receipt payee mismatch")
    if receipt.get("asset") != plan.distribution_currency:
        raise DistributionAccountingV1Error("distribution receipt asset mismatch")
    if receipt.get("amount") != canonical_decimal_text(beneficiary.amount):
        raise DistributionAccountingV1Error("distribution receipt amount mismatch")
    if receipt.get("payment_idempotency_key") != beneficiary.payment_idempotency_key:
        raise DistributionAccountingV1Error("distribution receipt idempotency mismatch")
    if receipt.get("payer_borne_external_fee") != "0":
        raise DistributionAccountingV1Error("v1 accounting refuses payer-borne distribution fees")
    status = receipt.get("status")
    if status not in TERMINAL_STATUSES:
        raise DistributionAccountingV1Error("distribution receipt must be terminal")
    if status == "SETTLED" and receipt.get("reconciled") is not True:
        raise DistributionAccountingV1Error("SETTLED distribution receipt must be reconciled")
    if receipt.get("authority") != "SETTLEMENT_EVIDENCE_ONLY":
        raise DistributionAccountingV1Error("distribution receipt authority mismatch")
    if receipt.get("accounting_authority") != "Shtenco/synergy_financial_os":
        raise DistributionAccountingV1Error("distribution receipt accounting authority mismatch")
    if receipt.get("profit_recognition") != "NOT_PERFORMED":
        raise DistributionAccountingV1Error("distribution receipt cannot recognize profit")
    _hex64(receipt.get("settlement_evidence_digest"), "settlement_evidence_digest")
    _parse_utc(receipt.get("finality_time"), "finality_time")
    return receipt


def verify_distribution_utilization_for_accounting_v1(
    payload: Mapping[str, Any],
    *,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.utilization/v1":
        raise DistributionAccountingV1Error("unsupported distribution utilization schema")
    utilization = dict(payload)
    _verify_digest(utilization)
    if utilization.get("distribution_attempt_digest") != attempt.get("digest"):
        raise DistributionAccountingV1Error("utilization / attempt mismatch")
    if utilization.get("distribution_plan_digest") != plan.digest:
        raise DistributionAccountingV1Error("utilization / plan mismatch")
    if utilization.get("distribution_authorization_digest") != authorization.digest:
        raise DistributionAccountingV1Error("utilization / authorization mismatch")
    if utilization.get("distribution_execution_ticket_digest") != ticket.digest:
        raise DistributionAccountingV1Error("utilization / ticket mismatch")
    if utilization.get("beneficiary_set_digest") != plan.beneficiary_set_digest:
        raise DistributionAccountingV1Error("utilization beneficiary-set mismatch")
    if utilization.get("authorization_consumption") != "CONSUMED":
        raise DistributionAccountingV1Error("utilization must preserve consumed authorization")
    if utilization.get("authority") != "METAPAY_DISTRIBUTION_UTILIZATION":
        raise DistributionAccountingV1Error("utilization authority mismatch")
    if utilization.get("accounting_authority") != "REFERENCE_ONLY":
        raise DistributionAccountingV1Error("utilization cannot claim Financial OS accounting authority")
    status = utilization.get("status")
    if status not in UTILIZATION_STATUSES:
        raise DistributionAccountingV1Error("unsupported utilization status")
    verified_receipts = tuple(
        verify_distribution_settlement_receipt_for_accounting_v1(
            item,
            plan=plan,
            authorization=authorization,
            ticket=ticket,
            attempt=attempt,
        )
        for item in receipts
    )
    if len(verified_receipts) != len(plan.beneficiaries):
        raise DistributionAccountingV1Error("accounting requires one terminal receipt per planned beneficiary")
    receipt_digests = tuple(sorted(item["receipt_digest"] for item in verified_receipts))
    if tuple(utilization.get("receipt_digests") or ()) != receipt_digests:
        raise DistributionAccountingV1Error("utilization receipt digest set mismatch")
    settled = tuple(sorted(item["beneficiary_id"] for item in verified_receipts if item["status"] == "SETTLED"))
    failed = tuple(sorted(item["beneficiary_id"] for item in verified_receipts if item["status"] != "SETTLED"))
    if tuple(utilization.get("settled_beneficiary_ids") or ()) != settled:
        raise DistributionAccountingV1Error("utilization settled beneficiary set mismatch")
    if tuple(utilization.get("failed_beneficiary_ids") or ()) != failed:
        raise DistributionAccountingV1Error("utilization failed beneficiary set mismatch")
    settled_total = sum(
        (_decimal_text(item["amount"], "receipt amount", nonnegative=True) for item in verified_receipts if item["status"] == "SETTLED"),
        ZERO,
    )
    if utilization.get("settled_total_amount") != canonical_decimal_text(settled_total):
        raise DistributionAccountingV1Error("utilization settled total mismatch")
    if utilization.get("planned_total_amount") != canonical_decimal_text(plan.total_amount):
        raise DistributionAccountingV1Error("utilization planned total mismatch")
    if status == "FULLY_SETTLED" and settled_total != plan.total_amount:
        raise DistributionAccountingV1Error("FULLY_SETTLED utilization does not settle exact plan total")
    if status == "PARTIALLY_SETTLED_REQUIRES_NEW_PLAN" and not (ZERO < settled_total < plan.total_amount):
        raise DistributionAccountingV1Error("partial utilization amount semantics mismatch")
    if status == "FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION" and settled_total != ZERO:
        raise DistributionAccountingV1Error("failed utilization cannot contain settled amount")
    final_time = _parse_utc(utilization.get("finalized_at"), "utilization.finalized_at")
    latest_receipt = max(_parse_utc(item["finality_time"], "receipt.finality_time") for item in verified_receipts)
    if final_time < latest_receipt:
        raise DistributionAccountingV1Error("utilization predates latest settlement receipt")
    return utilization, verified_receipts


@dataclass(frozen=True)
class DistributionAccountingAccountsV1:
    external_cash_account: str
    distribution_equity_account: str
    source_account_mapping_evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "external_cash_account", _text(self.external_cash_account, "external_cash_account"))
        object.__setattr__(self, "distribution_equity_account", _text(self.distribution_equity_account, "distribution_equity_account"))
        if self.external_cash_account == self.distribution_equity_account:
            raise DistributionAccountingV1Error("distribution cash/equity accounts must be distinct")
        object.__setattr__(
            self,
            "source_account_mapping_evidence_digest",
            _hex64(self.source_account_mapping_evidence_digest, "source_account_mapping_evidence_digest"),
        )


@dataclass(frozen=True)
class DistributionAccountingDecisionV1:
    decision_id: str
    distribution_plan_digest: str
    distribution_authorization_digest: str
    distribution_execution_ticket_digest: str
    distribution_attempt_digest: str
    distribution_utilization_digest: str
    settled_receipt_set_digest: str
    affected_period_id: str
    operational_source_account_id: str
    reporting_cash_account_id: str
    distribution_equity_account_id: str
    source_account_mapping_evidence_digest: str
    reporting_currency: str
    settled_total_amount: Decimal
    status: str
    blockers: tuple[str, ...]
    decided_at: datetime
    accounting_flow_type: str = "EXTERNAL_CAPITAL"
    economic_class: str = "OWNER_DISTRIBUTION"
    pnl_treatment: str = "EXCLUDED_FROM_REALIZED_PNL"
    ledger_posting_authority: str = "SEPARATE_CANONICAL_POSTING"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.accounting_flow_type != "EXTERNAL_CAPITAL" or self.economic_class != "OWNER_DISTRIBUTION":
            raise DistributionAccountingV1Error("distribution accounting classification mismatch")
        if self.pnl_treatment != "EXCLUDED_FROM_REALIZED_PNL":
            raise DistributionAccountingV1Error("owner distribution must remain outside realized P&L")
        if self.ledger_posting_authority != "SEPARATE_CANONICAL_POSTING":
            raise DistributionAccountingV1Error("accounting decision cannot mutate ledger directly")
        if self.execution_authority != "NONE" or self.ai_authority != "NONE":
            raise DistributionAccountingV1Error("accounting decision cannot execute and AI cannot authorize")
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "operational_source_account_id", _text(self.operational_source_account_id, "operational_source_account_id"))
        object.__setattr__(self, "reporting_cash_account_id", _text(self.reporting_cash_account_id, "reporting_cash_account_id"))
        object.__setattr__(self, "distribution_equity_account_id", _text(self.distribution_equity_account_id, "distribution_equity_account_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in (
            "distribution_plan_digest",
            "distribution_authorization_digest",
            "distribution_execution_ticket_digest",
            "distribution_attempt_digest",
            "distribution_utilization_digest",
            "settled_receipt_set_digest",
            "source_account_mapping_evidence_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        settled = finite_decimal(self.settled_total_amount, "settled_total_amount")
        if settled < ZERO:
            raise DistributionAccountingV1Error("settled_total_amount must be non-negative")
        object.__setattr__(self, "settled_total_amount", settled)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected = "POSTABLE" if settled > ZERO and not blockers else "NO_ACTION"
        if self.status != expected:
            raise DistributionAccountingV1Error("distribution accounting decision status mismatch")
        object.__setattr__(self, "decided_at", _utc(self.decided_at, "decided_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "decision_id": self.decision_id,
            "distribution_plan_digest": self.distribution_plan_digest,
            "distribution_authorization_digest": self.distribution_authorization_digest,
            "distribution_execution_ticket_digest": self.distribution_execution_ticket_digest,
            "distribution_attempt_digest": self.distribution_attempt_digest,
            "distribution_utilization_digest": self.distribution_utilization_digest,
            "settled_receipt_set_digest": self.settled_receipt_set_digest,
            "affected_period_id": self.affected_period_id,
            "operational_source_account_id": self.operational_source_account_id,
            "reporting_cash_account_id": self.reporting_cash_account_id,
            "distribution_equity_account_id": self.distribution_equity_account_id,
            "source_account_mapping_evidence_digest": self.source_account_mapping_evidence_digest,
            "reporting_currency": self.reporting_currency,
            "settled_total_amount": canonical_decimal_text(self.settled_total_amount),
            "status": self.status,
            "blockers": list(self.blockers),
            "decided_at": self.decided_at.isoformat().replace("+00:00", "Z"),
            "accounting_flow_type": self.accounting_flow_type,
            "economic_class": self.economic_class,
            "pnl_treatment": self.pnl_treatment,
            "ledger_posting_authority": self.ledger_posting_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def evaluate_distribution_accounting_v1(
    *,
    decision_id: str,
    ledger: ReportingLedger,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    receipt_payloads: Sequence[Mapping[str, Any]],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
) -> DistributionAccountingDecisionV1:
    if ledger.reporting_currency != plan.distribution_currency:
        raise DistributionAccountingV1Error("v1 requires ledger/reporting currency == distribution currency")
    if authorization.distribution_plan_digest != plan.digest or ticket.distribution_plan_digest != plan.digest:
        raise DistributionAccountingV1Error("Financial OS distribution context is internally inconsistent")
    if ticket.distribution_authorization_digest != authorization.digest:
        raise DistributionAccountingV1Error("ExecutionTicket / DistributionAuthorization mismatch")
    attempt = verify_distribution_batch_attempt_for_accounting_v1(
        attempt_payload,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
    )
    utilization, receipts = verify_distribution_utilization_for_accounting_v1(
        utilization_payload,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt=attempt,
        receipts=receipt_payloads,
    )
    cash_spec = ledger.account(accounts.external_cash_account)
    equity_spec = ledger.account(accounts.distribution_equity_account)
    if cash_spec.account_class != AccountClass.ASSET or cash_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionAccountingV1Error("distribution cash account must be EXTERNAL ASSET")
    if equity_spec.account_class != AccountClass.EQUITY or equity_spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise DistributionAccountingV1Error("distribution equity account must be EXTERNAL EQUITY")
    settled_total = _decimal_text(utilization["settled_total_amount"], "settled_total_amount", nonnegative=True)
    blockers: list[str] = []
    if settled_total == ZERO:
        blockers.append("NO_SETTLED_DISTRIBUTION")
    if settled_total > ZERO and ledger.balance(accounts.external_cash_account) < settled_total:
        blockers.append("INSUFFICIENT_REPORTED_CASH_BALANCE")
    if settled_total > ZERO and ledger.balance(accounts.distribution_equity_account) < settled_total:
        blockers.append("INSUFFICIENT_DISTRIBUTION_EQUITY_BALANCE")
    latest_receipt_time = max(_parse_utc(item["finality_time"], "receipt.finality_time") for item in receipts)
    decision_time = _utc(decided_at, "decided_at")
    if decision_time < latest_receipt_time:
        raise DistributionAccountingV1Error("accounting decision cannot predate settlement evidence")
    receipt_set_digest = canonical_json_digest(sorted(item["receipt_digest"] for item in receipts))
    return DistributionAccountingDecisionV1(
        decision_id=decision_id,
        distribution_plan_digest=plan.digest,
        distribution_authorization_digest=authorization.digest,
        distribution_execution_ticket_digest=ticket.digest,
        distribution_attempt_digest=attempt["digest"],
        distribution_utilization_digest=utilization["digest"],
        settled_receipt_set_digest=receipt_set_digest,
        affected_period_id=plan.affected_period_id,
        operational_source_account_id=plan.source_account_id,
        reporting_cash_account_id=accounts.external_cash_account,
        distribution_equity_account_id=accounts.distribution_equity_account,
        source_account_mapping_evidence_digest=accounts.source_account_mapping_evidence_digest,
        reporting_currency=ledger.reporting_currency,
        settled_total_amount=settled_total,
        status="POSTABLE" if settled_total > ZERO and not blockers else "NO_ACTION",
        blockers=tuple(blockers),
        decided_at=decision_time,
    )
