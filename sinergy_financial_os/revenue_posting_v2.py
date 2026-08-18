from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .core import AccountingInvariantError
from .reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingEntry,
    ReportingLedger,
    ReportingLine,
)
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2


ZERO = Decimal("0")


class RevenuePostingV2Error(AccountingInvariantError):
    pass


@dataclass(frozen=True)
class RevenuePostingAccountsV2:
    cash_or_receivable_account_id: str
    revenue_account_id: str
    tax_liability_account_id: str
    refund_reserve_liability_account_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "cash_or_receivable_account_id",
            "revenue_account_id",
            "tax_liability_account_id",
            "refund_reserve_liability_account_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise RevenuePostingV2Error(f"{field_name} is required")
            object.__setattr__(self, field_name, value.strip())


def _require_account(
    ledger: ReportingLedger,
    account_id: str,
    account_class: AccountClass,
) -> None:
    spec = ledger.account(account_id)
    if spec.account_class != account_class:
        raise RevenuePostingV2Error(
            f"{account_id} must be {account_class.value}, got {spec.account_class.value}"
        )
    if spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise RevenuePostingV2Error(
            f"{account_id} must be EXTERNAL for canonical external revenue posting"
        )


def post_recognized_external_revenue_v2(
    ledger: ReportingLedger,
    decision: RevenueRecognitionDecisionV2,
    accounts: RevenuePostingAccountsV2,
    *,
    event_id: str,
) -> ReportingEntry:
    """Post only a separately recognized external-revenue decision.

    Receipt/lineage evidence alone cannot call this adapter. The decision remains
    the evidence root and the adapter preserves tax/refund amounts as liabilities.
    """

    if not isinstance(decision, RevenueRecognitionDecisionV2):
        raise RevenuePostingV2Error("decision must be RevenueRecognitionDecisionV2")
    if decision.decision != "RECOGNIZED" or not decision.ledger_posting_allowed:
        raise RevenuePostingV2Error(
            "only RECOGNIZED RevenueRecognition v2 decisions may post external revenue"
        )
    if decision.recognized_reporting_amount <= ZERO:
        raise RevenuePostingV2Error("recognized amount must be positive")
    if ledger.reporting_currency != decision.reporting_currency:
        raise RevenuePostingV2Error(
            "ReportingLedger currency must match recognition reporting_currency"
        )
    if (
        decision.recognized_reporting_amount
        + decision.tax_reporting_amount
        + decision.refund_reserve_reporting_amount
        != decision.gross_reporting_amount
    ):
        raise RevenuePostingV2Error("recognition components must sum to gross reporting amount")

    _require_account(
        ledger, accounts.cash_or_receivable_account_id, AccountClass.ASSET
    )
    _require_account(ledger, accounts.revenue_account_id, AccountClass.REVENUE)
    _require_account(
        ledger, accounts.tax_liability_account_id, AccountClass.LIABILITY
    )
    _require_account(
        ledger, accounts.refund_reserve_liability_account_id, AccountClass.LIABILITY
    )

    lines: list[ReportingLine] = [
        ReportingLine(
            account_id=accounts.cash_or_receivable_account_id,
            debit=decision.gross_reporting_amount,
        ),
        ReportingLine(
            account_id=accounts.revenue_account_id,
            credit=decision.recognized_reporting_amount,
        ),
    ]
    if decision.tax_reporting_amount > ZERO:
        lines.append(
            ReportingLine(
                account_id=accounts.tax_liability_account_id,
                credit=decision.tax_reporting_amount,
            )
        )
    if decision.refund_reserve_reporting_amount > ZERO:
        lines.append(
            ReportingLine(
                account_id=accounts.refund_reserve_liability_account_id,
                credit=decision.refund_reserve_reporting_amount,
            )
        )

    return ledger.post(
        event_id=event_id,
        reference=decision.recognition_id,
        flow_type=FlowType.EXTERNAL_REVENUE,
        lines=lines,
        evidence_digest=decision.digest,
        metadata={
            "project_id": decision.project_id,
            "settlement_receipt_digest": decision.settlement_receipt_digest,
            "capital_authorization_digest": decision.capital_authorization_digest,
            "project_evidence_digest": decision.project_evidence_digest,
            "accounting_policy_digest": decision.accounting_policy_digest,
            "revenue_recognition_schema": "revenue.recognition/v2",
        },
    )
