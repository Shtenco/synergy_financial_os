from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_accounting_v1 import (
    DistributionAccountingAccountsV1,
    DistributionAccountingDecisionV1,
    DistributionAccountingV1Error,
    verify_distribution_batch_attempt_for_accounting_v1,
    verify_distribution_utilization_for_accounting_v1,
)
from .distribution_authorization_v1 import DistributionAuthorizationV1
from .distribution_execution_ticket_v1 import DistributionExecutionTicketV1
from .distribution_plan_v1 import DistributionPlanV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import FlowType, ReportingEntry, ReportingLedger, ReportingLine


SCHEMA = "distribution.reversal-accounting-decision/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class DistributionReversalAccountingV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionReversalAccountingV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionReversalAccountingV1Error(f"{field_name} must be hex64")
    return result


def _decimal(value: Any, field_name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise DistributionReversalAccountingV1Error(f"{field_name} must be canonical decimal text")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
        raise DistributionReversalAccountingV1Error(f"{field_name} is not canonical decimal text")
    if positive and result <= ZERO:
        raise DistributionReversalAccountingV1Error(f"{field_name} must be strictly positive")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionReversalAccountingV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise DistributionReversalAccountingV1Error(f"{field_name} must use canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DistributionReversalAccountingV1Error(f"{field_name} is invalid") from exc
    if parsed.isoformat().replace("+00:00", "Z") != text:
        raise DistributionReversalAccountingV1Error(f"{field_name} is not canonical UTC text")
    return parsed.astimezone(UTC)


def _verify_reversal_payload(
    payload: Mapping[str, Any],
    *,
    original_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.settlement-reversal/v1":
        raise DistributionReversalAccountingV1Error("unsupported distribution settlement reversal schema")
    reversal = dict(payload)
    supplied = _hex64(reversal.get("digest"), "reversal.digest")
    body = dict(reversal); body.pop("digest", None)
    if canonical_json_digest(body) != supplied:
        raise DistributionReversalAccountingV1Error("distribution settlement reversal digest mismatch")
    if reversal.get("original_distribution_receipt_digest") != original_receipt.get("receipt_digest"):
        raise DistributionReversalAccountingV1Error("reversal / original receipt digest mismatch")
    for field in (
        "distribution_attempt_digest",
        "distribution_execution_ticket_digest",
        "distribution_authorization_digest",
        "distribution_plan_digest",
        "beneficiary_set_digest",
        "beneficiary_id",
        "payment_idempotency_key",
        "payer_id",
        "payee_id",
        "asset",
        "amount",
    ):
        if reversal.get(field) != original_receipt.get(field):
            raise DistributionReversalAccountingV1Error(f"reversal / original receipt {field} mismatch")
    if original_receipt.get("status") != "SETTLED" or original_receipt.get("reconciled") is not True:
        raise DistributionReversalAccountingV1Error("reversal requires original SETTLED reconciled receipt")
    if reversal.get("payer_borne_reversal_fee") != "0":
        raise DistributionReversalAccountingV1Error("v1 accounting refuses payer-borne reversal fee")
    if reversal.get("status") != "REVERSED_CONFIRMED":
        raise DistributionReversalAccountingV1Error("unexpected distribution reversal status")
    if reversal.get("authority") != "SETTLEMENT_REVERSAL_EVIDENCE_ONLY":
        raise DistributionReversalAccountingV1Error("unexpected distribution reversal authority")
    if reversal.get("accounting_authority") != "Shtenco/synergy_financial_os":
        raise DistributionReversalAccountingV1Error("distribution reversal accounting authority mismatch")
    if reversal.get("authorization_consumption") != "REMAINS_CONSUMED":
        raise DistributionReversalAccountingV1Error("reversal must not revive consumed authorization")
    if reversal.get("profit_recognition") != "NOT_PERFORMED" or reversal.get("execution_authority") != "NONE":
        raise DistributionReversalAccountingV1Error("reversal settlement evidence cannot recognize P&L or execute")
    observed = _parse_utc(reversal.get("observed_at"), "reversal.observed_at")
    original_time = _parse_utc(original_receipt.get("finality_time"), "original receipt finality_time")
    if observed <= original_time:
        raise DistributionReversalAccountingV1Error("reversal must occur after original settlement finality")
    _hex64(reversal.get("reversal_evidence_digest"), "reversal_evidence_digest")
    _decimal(reversal.get("amount"), "reversal amount", positive=True)
    return reversal


def _find_original_distribution_entry(
    ledger: ReportingLedger,
    *,
    original_decision: DistributionAccountingDecisionV1,
    utilization_digest: str,
) -> ReportingEntry:
    matches = [
        entry
        for entry in ledger.entries_since(0)
        if entry.reference == utilization_digest
        and entry.flow_type == FlowType.EXTERNAL_CAPITAL
        and entry.evidence_digest == original_decision.digest
        and entry.metadata.get("economic_class") == "OWNER_DISTRIBUTION"
    ]
    if len(matches) != 1:
        raise DistributionReversalAccountingV1Error(
            "original owner distribution must exist exactly once in ReportingLedger"
        )
    entry = matches[0]
    amount = original_decision.settled_total_amount
    cash_lines = [line for line in entry.lines if line.account_id == original_decision.reporting_cash_account_id]
    equity_lines = [line for line in entry.lines if line.account_id == original_decision.distribution_equity_account_id]
    if len(cash_lines) != 1 or len(equity_lines) != 1:
        raise DistributionReversalAccountingV1Error("original payout account lines mismatch")
    if cash_lines[0].credit != amount or cash_lines[0].debit != ZERO:
        raise DistributionReversalAccountingV1Error("original payout cash line mismatch")
    if equity_lines[0].debit != amount or equity_lines[0].credit != ZERO:
        raise DistributionReversalAccountingV1Error("original payout equity line mismatch")
    if len(entry.lines) != 2:
        raise DistributionReversalAccountingV1Error("original payout must use canonical two-line posting")
    return entry


@dataclass(frozen=True)
class DistributionReversalAccountingDecisionV1:
    decision_id: str
    original_distribution_accounting_decision_digest: str
    original_distribution_reporting_entry_digest: str
    original_distribution_utilization_digest: str
    original_distribution_receipt_digest: str
    distribution_settlement_reversal_digest: str
    beneficiary_id: str
    reporting_cash_account_id: str
    distribution_equity_account_id: str
    source_account_mapping_evidence_digest: str
    reporting_currency: str
    reversal_amount: Decimal
    status: str
    blockers: tuple[str, ...]
    decided_at: datetime
    accounting_flow_type: str = "EXTERNAL_CAPITAL"
    economic_class: str = "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL"
    pnl_treatment: str = "EXCLUDED_FROM_REALIZED_PNL"
    ledger_posting_authority: str = "SEPARATE_CANONICAL_POSTING"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.accounting_flow_type != "EXTERNAL_CAPITAL":
            raise DistributionReversalAccountingV1Error("reversal must remain capital flow")
        if self.economic_class != "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL":
            raise DistributionReversalAccountingV1Error("reversal economic class mismatch")
        if self.pnl_treatment != "EXCLUDED_FROM_REALIZED_PNL":
            raise DistributionReversalAccountingV1Error("distribution reversal cannot enter realized P&L")
        if self.ledger_posting_authority != "SEPARATE_CANONICAL_POSTING" or self.execution_authority != "NONE" or self.ai_authority != "NONE":
            raise DistributionReversalAccountingV1Error("distribution reversal authority boundary mismatch")
        object.__setattr__(self, "decision_id", _text(self.decision_id, "decision_id"))
        object.__setattr__(self, "beneficiary_id", _text(self.beneficiary_id, "beneficiary_id"))
        object.__setattr__(self, "reporting_cash_account_id", _text(self.reporting_cash_account_id, "reporting_cash_account_id"))
        object.__setattr__(self, "distribution_equity_account_id", _text(self.distribution_equity_account_id, "distribution_equity_account_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in (
            "original_distribution_accounting_decision_digest",
            "original_distribution_reporting_entry_digest",
            "original_distribution_utilization_digest",
            "original_distribution_receipt_digest",
            "distribution_settlement_reversal_digest",
            "source_account_mapping_evidence_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        amount = finite_decimal(self.reversal_amount, "reversal_amount")
        if amount <= ZERO:
            raise DistributionReversalAccountingV1Error("reversal amount must be strictly positive")
        object.__setattr__(self, "reversal_amount", amount)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected = "POSTABLE" if not blockers else "NO_ACTION"
        if self.status != expected:
            raise DistributionReversalAccountingV1Error("distribution reversal accounting status mismatch")
        object.__setattr__(self, "decided_at", _utc(self.decided_at, "decided_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "decision_id": self.decision_id,
            "original_distribution_accounting_decision_digest": self.original_distribution_accounting_decision_digest,
            "original_distribution_reporting_entry_digest": self.original_distribution_reporting_entry_digest,
            "original_distribution_utilization_digest": self.original_distribution_utilization_digest,
            "original_distribution_receipt_digest": self.original_distribution_receipt_digest,
            "distribution_settlement_reversal_digest": self.distribution_settlement_reversal_digest,
            "beneficiary_id": self.beneficiary_id,
            "reporting_cash_account_id": self.reporting_cash_account_id,
            "distribution_equity_account_id": self.distribution_equity_account_id,
            "source_account_mapping_evidence_digest": self.source_account_mapping_evidence_digest,
            "reporting_currency": self.reporting_currency,
            "reversal_amount": canonical_decimal_text(self.reversal_amount),
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


def evaluate_distribution_reversal_accounting_v1(
    *,
    decision_id: str,
    ledger: ReportingLedger,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    original_receipt_payloads: Sequence[Mapping[str, Any]],
    original_accounting_decision: DistributionAccountingDecisionV1,
    settlement_reversal_payload: Mapping[str, Any],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
) -> DistributionReversalAccountingDecisionV1:
    attempt = verify_distribution_batch_attempt_for_accounting_v1(
        attempt_payload, plan=plan, authorization=authorization, ticket=ticket
    )
    utilization, receipts = verify_distribution_utilization_for_accounting_v1(
        utilization_payload,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt=attempt,
        receipts=original_receipt_payloads,
    )
    if original_accounting_decision.status != "POSTABLE":
        raise DistributionReversalAccountingV1Error("original distribution accounting decision was not POSTABLE")
    expected_receipt_set = canonical_json_digest(sorted(item["receipt_digest"] for item in receipts))
    checks = (
        (original_accounting_decision.distribution_plan_digest, plan.digest, "original decision plan"),
        (original_accounting_decision.distribution_authorization_digest, authorization.digest, "original decision authorization"),
        (original_accounting_decision.distribution_execution_ticket_digest, ticket.digest, "original decision ticket"),
        (original_accounting_decision.distribution_attempt_digest, attempt["digest"], "original decision attempt"),
        (original_accounting_decision.distribution_utilization_digest, utilization["digest"], "original decision utilization"),
        (original_accounting_decision.settled_receipt_set_digest, expected_receipt_set, "original decision receipt set"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise DistributionReversalAccountingV1Error(f"{label} mismatch")
    if original_accounting_decision.reporting_cash_account_id != accounts.external_cash_account:
        raise DistributionReversalAccountingV1Error("reversal cash account differs from original distribution")
    if original_accounting_decision.distribution_equity_account_id != accounts.distribution_equity_account:
        raise DistributionReversalAccountingV1Error("reversal equity account differs from original distribution")
    if original_accounting_decision.source_account_mapping_evidence_digest != accounts.source_account_mapping_evidence_digest:
        raise DistributionReversalAccountingV1Error("reversal account mapping evidence differs from original distribution")
    original_entry = _find_original_distribution_entry(
        ledger,
        original_decision=original_accounting_decision,
        utilization_digest=utilization["digest"],
    )
    reversal_receipt_digest = settlement_reversal_payload.get("original_distribution_receipt_digest")
    matches = [item for item in receipts if item["receipt_digest"] == reversal_receipt_digest]
    if len(matches) != 1:
        raise DistributionReversalAccountingV1Error("reversal original receipt is not uniquely present in distribution evidence")
    original_receipt = matches[0]
    if original_receipt["status"] != "SETTLED":
        raise DistributionReversalAccountingV1Error("only an originally SETTLED beneficiary can be reversed")
    reversal = _verify_reversal_payload(settlement_reversal_payload, original_receipt=original_receipt)
    prior = [
        entry
        for entry in ledger.entries_since(0)
        if entry.metadata.get("economic_class") == "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL"
        and entry.metadata.get("original_distribution_receipt_digest") == original_receipt["receipt_digest"]
    ]
    blockers: list[str] = []
    if prior:
        blockers.append("ORIGINAL_DISTRIBUTION_RECEIPT_ALREADY_REVERSED_IN_LEDGER")
    decision_time = _utc(decided_at, "decided_at")
    reversal_time = _parse_utc(reversal["observed_at"], "reversal.observed_at")
    if decision_time < reversal_time:
        raise DistributionReversalAccountingV1Error("reversal accounting decision cannot predate reversal evidence")
    return DistributionReversalAccountingDecisionV1(
        decision_id=decision_id,
        original_distribution_accounting_decision_digest=original_accounting_decision.digest,
        original_distribution_reporting_entry_digest=original_entry.digest,
        original_distribution_utilization_digest=utilization["digest"],
        original_distribution_receipt_digest=original_receipt["receipt_digest"],
        distribution_settlement_reversal_digest=reversal["digest"],
        beneficiary_id=original_receipt["beneficiary_id"],
        reporting_cash_account_id=accounts.external_cash_account,
        distribution_equity_account_id=accounts.distribution_equity_account,
        source_account_mapping_evidence_digest=accounts.source_account_mapping_evidence_digest,
        reporting_currency=ledger.reporting_currency,
        reversal_amount=_decimal(reversal["amount"], "reversal amount", positive=True),
        status="POSTABLE" if not blockers else "NO_ACTION",
        blockers=tuple(blockers),
        decided_at=decision_time,
    )


def post_distribution_settlement_reversal_v1(
    ledger: ReportingLedger,
    *,
    decision_id: str,
    event_id: str,
    plan: DistributionPlanV1,
    authorization: DistributionAuthorizationV1,
    ticket: DistributionExecutionTicketV1,
    attempt_payload: Mapping[str, Any],
    utilization_payload: Mapping[str, Any],
    original_receipt_payloads: Sequence[Mapping[str, Any]],
    original_accounting_decision: DistributionAccountingDecisionV1,
    settlement_reversal_payload: Mapping[str, Any],
    accounts: DistributionAccountingAccountsV1,
    decided_at: datetime,
):
    decision = evaluate_distribution_reversal_accounting_v1(
        decision_id=decision_id,
        ledger=ledger,
        plan=plan,
        authorization=authorization,
        ticket=ticket,
        attempt_payload=attempt_payload,
        utilization_payload=utilization_payload,
        original_receipt_payloads=original_receipt_payloads,
        original_accounting_decision=original_accounting_decision,
        settlement_reversal_payload=settlement_reversal_payload,
        accounts=accounts,
        decided_at=decided_at,
    )
    if decision.status != "POSTABLE":
        raise DistributionReversalAccountingV1Error(
            "distribution settlement reversal is not postable: " + ",".join(decision.blockers)
        )
    amount = decision.reversal_amount
    entry = ledger.post(
        event_id=event_id,
        reference=settlement_reversal_payload["digest"],
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(
            ReportingLine(accounts.external_cash_account, debit=amount),
            ReportingLine(accounts.distribution_equity_account, credit=amount),
        ),
        evidence_digest=decision.digest,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL",
            "capital_direction": "INFLOW_REVERSAL_OF_PRIOR_OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "distribution_reversal_accounting_decision_digest": decision.digest,
            "original_distribution_accounting_decision_digest": original_accounting_decision.digest,
            "original_distribution_reporting_entry_digest": decision.original_distribution_reporting_entry_digest,
            "original_distribution_utilization_digest": decision.original_distribution_utilization_digest,
            "original_distribution_receipt_digest": decision.original_distribution_receipt_digest,
            "distribution_settlement_reversal_digest": decision.distribution_settlement_reversal_digest,
            "beneficiary_id": decision.beneficiary_id,
            "source_account_mapping_evidence_digest": accounts.source_account_mapping_evidence_digest,
        },
    )
    return decision, entry
