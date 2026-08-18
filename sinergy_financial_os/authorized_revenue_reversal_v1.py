from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .accounting_close_v2 import AccountingCloseV2, LedgerInclusionProofV2
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingLedger,
    ReportingLine,
)
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2
from .revenue_reversal_v1 import (
    RevenueReversalAuthorizationV1,
    verify_revenue_reversal_context_v1,
)


ZERO = Decimal("0")


class AuthorizedRevenueReversalV1Error(AccountingInvariantError):
    pass


@dataclass(frozen=True)
class RevenueReversalAccountsV1:
    external_asset_account: str
    revenue_account: str
    tax_liability_account: str
    refund_reserve_liability_account: str

    def __post_init__(self) -> None:
        for name in (
            "external_asset_account",
            "revenue_account",
            "tax_liability_account",
            "refund_reserve_liability_account",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise AuthorizedRevenueReversalV1Error(f"{name} is required")
            object.__setattr__(self, name, value.strip())
        if len(set((self.external_asset_account, self.revenue_account, self.tax_liability_account, self.refund_reserve_liability_account))) != 4:
            raise AuthorizedRevenueReversalV1Error("reversal accounts must be distinct")


def _assert_account_classes(
    ledger: ReportingLedger, accounts: RevenueReversalAccountsV1
) -> None:
    expected = {
        accounts.external_asset_account: AccountClass.ASSET,
        accounts.revenue_account: AccountClass.REVENUE,
        accounts.tax_liability_account: AccountClass.LIABILITY,
        accounts.refund_reserve_liability_account: AccountClass.LIABILITY,
    }
    for account_id, account_class in expected.items():
        spec = ledger.account(account_id)
        if spec.consolidation_class != ConsolidationClass.EXTERNAL:
            raise AuthorizedRevenueReversalV1Error(
                f"{account_id} must be EXTERNAL consolidated account"
            )
        if spec.account_class != account_class:
            raise AuthorizedRevenueReversalV1Error(
                f"{account_id} must be {account_class.value}"
            )


def _line_amount(
    event: Mapping[str, Any], account: str, side: str
) -> Decimal:
    matches = [line for line in event["lines"] if line.get("account") == account]
    if len(matches) != 1:
        raise AuthorizedRevenueReversalV1Error(
            f"original LedgerEvent must contain exactly one line for {account}"
        )
    value = Decimal(matches[0][side])
    opposite = Decimal(matches[0]["credit" if side == "debit" else "debit"])
    if value <= ZERO or opposite != ZERO:
        raise AuthorizedRevenueReversalV1Error(
            f"original LedgerEvent {account} side does not match canonical revenue posting"
        )
    return value


def _verify_original_posting_shape(
    event: Mapping[str, Any],
    recognition: RevenueRecognitionDecisionV2,
    accounts: RevenueReversalAccountsV1,
) -> None:
    gross = _line_amount(event, accounts.external_asset_account, "debit")
    revenue = _line_amount(event, accounts.revenue_account, "credit")
    tax = _line_amount(event, accounts.tax_liability_account, "credit")
    refund = _line_amount(event, accounts.refund_reserve_liability_account, "credit")
    if gross != recognition.gross_reporting_amount:
        raise AuthorizedRevenueReversalV1Error("original gross asset debit mismatch")
    if revenue != recognition.recognized_reporting_amount:
        raise AuthorizedRevenueReversalV1Error("original recognized revenue credit mismatch")
    if tax != recognition.tax_reporting_amount:
        raise AuthorizedRevenueReversalV1Error("original tax liability credit mismatch")
    if refund != recognition.refund_reserve_reporting_amount:
        raise AuthorizedRevenueReversalV1Error("original refund reserve credit mismatch")
    if gross != revenue + tax + refund:
        raise AuthorizedRevenueReversalV1Error("original recognized components do not sum to gross")


def post_authorized_revenue_reversal_v1(
    ledger: ReportingLedger,
    authorization: RevenueReversalAuthorizationV1,
    target_period: AccountingPeriodV1,
    original_period_close: AccountingPeriodCloseV1,
    original_accounting_close: AccountingCloseV2,
    original_recognition: RevenueRecognitionDecisionV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
    accounts: RevenueReversalAccountsV1,
    *,
    event_id: str,
) :
    """Re-evaluate the closed-period evidence and post one new full reversal.

    The original entry/close are never mutated. V1 refuses partial reversals and
    refuses to synthesize tax/refund receivables when original component balances
    are no longer available.
    """

    verify_revenue_reversal_context_v1(
        authorization,
        target_period,
        original_period_close,
        original_accounting_close,
        original_recognition,
        original_ledger_event,
        original_inclusion_proof,
    )
    _assert_account_classes(ledger, accounts)
    _verify_original_posting_shape(
        original_ledger_event, original_recognition, accounts
    )
    if ledger.reporting_currency != original_recognition.reporting_currency:
        raise AuthorizedRevenueReversalV1Error("ledger reporting currency mismatch")

    gross = original_recognition.gross_reporting_amount
    revenue = original_recognition.recognized_reporting_amount
    tax = original_recognition.tax_reporting_amount
    refund = original_recognition.refund_reserve_reporting_amount

    required_balances = {
        accounts.external_asset_account: gross,
        accounts.revenue_account: revenue,
        accounts.tax_liability_account: tax,
        accounts.refund_reserve_liability_account: refund,
    }
    for account_id, required in required_balances.items():
        if required > ZERO and ledger.balance(account_id) < required:
            raise AuthorizedRevenueReversalV1Error(
                f"FULL_ONLY reversal unavailable: {account_id} balance is below original component"
            )

    lines = [ReportingLine(accounts.external_asset_account, credit=gross)]
    if revenue > ZERO:
        lines.append(ReportingLine(accounts.revenue_account, debit=revenue))
    if tax > ZERO:
        lines.append(ReportingLine(accounts.tax_liability_account, debit=tax))
    if refund > ZERO:
        lines.append(ReportingLine(accounts.refund_reserve_liability_account, debit=refund))

    metadata = {
        "economic_class": "REVENUE_REVERSAL",
        "reversal_reason": authorization.reason,
        "reversal_scope": authorization.adjustment_scope,
        "reversal_authorization_digest": authorization.digest,
        "target_period_id": target_period.period_id,
        "project_id": authorization.project_id,
        "original_period_close_digest": authorization.original_period_close_digest,
        "original_accounting_close_digest": authorization.original_accounting_close_digest,
        "original_revenue_recognition_digest": authorization.original_revenue_recognition_digest,
        "original_ledger_event_digest": authorization.original_ledger_event_digest,
        "original_reporting_entry_digest": authorization.original_reporting_entry_digest,
        "external_evidence_digest": authorization.external_evidence_digest,
        "decision_evidence_digest": authorization.decision_evidence_digest,
        "accounting_policy_digest": authorization.accounting_policy_digest,
    }
    return ledger.post(
        event_id=event_id,
        reference=authorization.authorization_id,
        flow_type=FlowType.EXTERNAL_EXPENSE,
        lines=tuple(lines),
        evidence_digest=authorization.digest,
        metadata=metadata,
    )
