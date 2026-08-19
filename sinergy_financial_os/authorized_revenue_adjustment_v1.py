from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2, LedgerInclusionProofV2
from .accounting_period_chain_v1 import AccountingPeriodChainProofV1
from .accounting_period_v1 import AccountingPeriodCloseV1, AccountingPeriodV1
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingLedger,
    ReportingLine,
)
from .revenue_adjustment_v1 import (
    RevenueAdjustmentAuthorizationV1,
    verify_revenue_adjustment_context_v1,
)
from .revenue_recognition_v2 import RevenueRecognitionDecisionV2


ZERO = Decimal("0")


class AuthorizedRevenueAdjustmentV1Error(AccountingInvariantError):
    pass


@dataclass(frozen=True)
class RevenueAdjustmentAccountsV1:
    external_asset_account: str
    revenue_account: str
    original_tax_liability_account: str
    refund_reserve_liability_account: str
    tax_recoverable_asset_account: str | None = None
    tax_expense_account: str | None = None
    external_fee_expense_account: str | None = None

    def __post_init__(self) -> None:
        required = (
            "external_asset_account",
            "revenue_account",
            "original_tax_liability_account",
            "refund_reserve_liability_account",
        )
        values: list[str] = []
        for name in required:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise AuthorizedRevenueAdjustmentV1Error(f"{name} is required")
            normalized = value.strip()
            object.__setattr__(self, name, normalized)
            values.append(normalized)
        for name in (
            "tax_recoverable_asset_account",
            "tax_expense_account",
            "external_fee_expense_account",
        ):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise AuthorizedRevenueAdjustmentV1Error(f"{name} must be non-empty when supplied")
                normalized = value.strip()
                object.__setattr__(self, name, normalized)
                values.append(normalized)
        if len(values) != len(set(values)):
            raise AuthorizedRevenueAdjustmentV1Error("adjustment accounts must be distinct")


def _assert_account(
    ledger: ReportingLedger,
    account_id: str,
    account_class: AccountClass,
) -> None:
    spec = ledger.account(account_id)
    if spec.consolidation_class != ConsolidationClass.EXTERNAL:
        raise AuthorizedRevenueAdjustmentV1Error(
            f"{account_id} must be EXTERNAL consolidated account"
        )
    if spec.account_class != account_class:
        raise AuthorizedRevenueAdjustmentV1Error(
            f"{account_id} must be {account_class.value}"
        )


def _line_amount(
    event: Mapping[str, Any],
    account: str,
    side: str,
    *,
    expected: Decimal,
) -> Decimal:
    matches = [line for line in event["lines"] if line.get("account") == account]
    if expected == ZERO:
        if matches:
            raise AuthorizedRevenueAdjustmentV1Error(
                f"original LedgerEvent unexpectedly contains zero-valued component account {account}"
            )
        return ZERO
    if len(matches) != 1:
        raise AuthorizedRevenueAdjustmentV1Error(
            f"original LedgerEvent must contain exactly one line for {account}"
        )
    value = finite_decimal(matches[0][side], f"original {account}.{side}")
    opposite_name = "credit" if side == "debit" else "debit"
    opposite = finite_decimal(matches[0][opposite_name], f"original {account}.{opposite_name}")
    if value <= ZERO or opposite != ZERO or value != expected:
        raise AuthorizedRevenueAdjustmentV1Error(
            f"original LedgerEvent component mismatch for {account}"
        )
    return value


def _verify_original_posting_shape(
    event: Mapping[str, Any],
    recognition: RevenueRecognitionDecisionV2,
    accounts: RevenueAdjustmentAccountsV1,
) -> None:
    gross = _line_amount(
        event,
        accounts.external_asset_account,
        "debit",
        expected=recognition.gross_reporting_amount,
    )
    revenue = _line_amount(
        event,
        accounts.revenue_account,
        "credit",
        expected=recognition.recognized_reporting_amount,
    )
    tax = _line_amount(
        event,
        accounts.original_tax_liability_account,
        "credit",
        expected=recognition.tax_reporting_amount,
    )
    reserve = _line_amount(
        event,
        accounts.refund_reserve_liability_account,
        "credit",
        expected=recognition.refund_reserve_reporting_amount,
    )
    if gross != revenue + tax + reserve:
        raise AuthorizedRevenueAdjustmentV1Error(
            "original recognized components do not sum to gross"
        )


def _prior_adjustment_usage(
    ledger: ReportingLedger,
    original_reporting_entry_digest: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, bool]:
    revenue = ZERO
    reserve = ZERO
    tax = ZERO
    customer = ZERO
    full_reversal_seen = False
    for entry in ledger.entries_since(0):
        metadata = entry.metadata
        if metadata.get("original_reporting_entry_digest") != original_reporting_entry_digest:
            continue
        economic_class = metadata.get("economic_class")
        if economic_class == "REVENUE_REVERSAL":
            full_reversal_seen = True
            continue
        if economic_class != "REVENUE_POST_CLOSE_ADJUSTMENT":
            continue
        revenue += finite_decimal(metadata.get("revenue_reduction_amount", "0"), "prior revenue reduction")
        reserve += finite_decimal(metadata.get("refund_reserve_release_amount", "0"), "prior reserve release")
        tax += finite_decimal(metadata.get("tax_adjustment_amount", "0"), "prior tax adjustment")
        customer += finite_decimal(metadata.get("customer_refund_amount", "0"), "prior customer refund")
    return revenue, reserve, tax, customer, full_reversal_seen


def _require_optional_account(
    ledger: ReportingLedger,
    account_id: str | None,
    account_class: AccountClass,
    field_name: str,
) -> str:
    if account_id is None:
        raise AuthorizedRevenueAdjustmentV1Error(f"{field_name} is required for selected treatment")
    _assert_account(ledger, account_id, account_class)
    return account_id


def post_authorized_revenue_adjustment_v1(
    ledger: ReportingLedger,
    authorization: RevenueAdjustmentAuthorizationV1,
    target_period: AccountingPeriodV1,
    period_chain_proof: AccountingPeriodChainProofV1,
    period_close_chain: Sequence[AccountingPeriodCloseV1],
    original_accounting_close: AccountingCloseV2,
    original_recognition: RevenueRecognitionDecisionV2,
    original_ledger_event: Mapping[str, Any],
    original_inclusion_proof: LedgerInclusionProofV2,
    accounts: RevenueAdjustmentAccountsV1,
    *,
    event_id: str,
):
    """Post one evidence-bound post-close refund/chargeback adjustment.

    V1 supports exact externally observed refund/chargeback cash events with an
    explicit accounting allocation. It never mutates the historical revenue
    entry or any prior PeriodClose. Multiple adjustments are allowed only while
    their cumulative revenue/tax/reserve use stays inside the original recognized
    components. A prior FULL_ONLY reversal consumes the adjustment path entirely.
    """

    verify_revenue_adjustment_context_v1(
        authorization,
        target_period,
        period_chain_proof,
        period_close_chain,
        original_accounting_close,
        original_recognition,
        original_ledger_event,
        original_inclusion_proof,
    )
    if ledger.reporting_currency != original_recognition.reporting_currency:
        raise AuthorizedRevenueAdjustmentV1Error("ledger reporting currency mismatch")

    _assert_account(ledger, accounts.external_asset_account, AccountClass.ASSET)
    _assert_account(ledger, accounts.revenue_account, AccountClass.REVENUE)
    _assert_account(ledger, accounts.original_tax_liability_account, AccountClass.LIABILITY)
    _assert_account(ledger, accounts.refund_reserve_liability_account, AccountClass.LIABILITY)
    _verify_original_posting_shape(original_ledger_event, original_recognition, accounts)

    used_revenue, used_reserve, used_tax, used_customer, full_reversal_seen = _prior_adjustment_usage(
        ledger,
        authorization.original_reporting_entry_digest,
    )
    if full_reversal_seen:
        raise AuthorizedRevenueAdjustmentV1Error(
            "original revenue was already fully reversed"
        )
    if used_revenue + authorization.revenue_reduction_amount > original_recognition.recognized_reporting_amount:
        raise AuthorizedRevenueAdjustmentV1Error("cumulative revenue reduction exceeds original recognized revenue")
    if used_reserve + authorization.refund_reserve_release_amount > original_recognition.refund_reserve_reporting_amount:
        raise AuthorizedRevenueAdjustmentV1Error("cumulative refund reserve release exceeds original reserve")
    if used_tax + authorization.tax_adjustment_amount > original_recognition.tax_reporting_amount:
        raise AuthorizedRevenueAdjustmentV1Error("cumulative tax adjustment exceeds original tax component")
    if used_customer + authorization.customer_refund_amount > original_recognition.gross_reporting_amount:
        raise AuthorizedRevenueAdjustmentV1Error("cumulative customer refunds exceed original gross settlement")

    if ledger.balance(accounts.external_asset_account) < authorization.total_cash_outflow_amount:
        raise AuthorizedRevenueAdjustmentV1Error("external asset balance is below required refund/fee cash outflow")
    if authorization.revenue_reduction_amount > ZERO and ledger.balance(accounts.revenue_account) < authorization.revenue_reduction_amount:
        raise AuthorizedRevenueAdjustmentV1Error("revenue balance is below authorized reduction")
    if authorization.refund_reserve_release_amount > ZERO and ledger.balance(accounts.refund_reserve_liability_account) < authorization.refund_reserve_release_amount:
        raise AuthorizedRevenueAdjustmentV1Error("refund reserve balance is below authorized release")

    lines: list[ReportingLine] = []
    if authorization.revenue_reduction_amount > ZERO:
        lines.append(
            ReportingLine(
                accounts.revenue_account,
                debit=authorization.revenue_reduction_amount,
            )
        )
    if authorization.refund_reserve_release_amount > ZERO:
        lines.append(
            ReportingLine(
                accounts.refund_reserve_liability_account,
                debit=authorization.refund_reserve_release_amount,
            )
        )

    tax_account_used = "NONE"
    if authorization.tax_adjustment_amount > ZERO:
        if authorization.tax_treatment == "LIABILITY_RELEASE":
            if ledger.balance(accounts.original_tax_liability_account) < authorization.tax_adjustment_amount:
                raise AuthorizedRevenueAdjustmentV1Error(
                    "tax liability balance is below authorized liability release"
                )
            tax_account_used = accounts.original_tax_liability_account
            lines.append(
                ReportingLine(
                    accounts.original_tax_liability_account,
                    debit=authorization.tax_adjustment_amount,
                )
            )
        elif authorization.tax_treatment == "RECOVERABLE_RECEIVABLE":
            tax_account_used = _require_optional_account(
                ledger,
                accounts.tax_recoverable_asset_account,
                AccountClass.ASSET,
                "tax_recoverable_asset_account",
            )
            lines.append(
                ReportingLine(
                    tax_account_used,
                    debit=authorization.tax_adjustment_amount,
                )
            )
        elif authorization.tax_treatment == "NONRECOVERABLE_EXPENSE":
            tax_account_used = _require_optional_account(
                ledger,
                accounts.tax_expense_account,
                AccountClass.EXPENSE,
                "tax_expense_account",
            )
            lines.append(
                ReportingLine(
                    tax_account_used,
                    debit=authorization.tax_adjustment_amount,
                )
            )
        else:
            raise AuthorizedRevenueAdjustmentV1Error("invalid non-zero tax treatment")

    fee_account_used = "NONE"
    if authorization.external_fee_expense_amount > ZERO:
        fee_account_used = _require_optional_account(
            ledger,
            accounts.external_fee_expense_account,
            AccountClass.EXPENSE,
            "external_fee_expense_account",
        )
        lines.append(
            ReportingLine(
                fee_account_used,
                debit=authorization.external_fee_expense_amount,
            )
        )

    lines.append(
        ReportingLine(
            accounts.external_asset_account,
            credit=authorization.total_cash_outflow_amount,
        )
    )

    metadata = {
        "economic_class": "REVENUE_POST_CLOSE_ADJUSTMENT",
        "adjustment_reason": authorization.reason,
        "adjustment_authorization_digest": authorization.digest,
        "target_period_id": target_period.period_id,
        "project_id": authorization.project_id,
        "original_period_close_digest": authorization.original_period_close_digest,
        "original_accounting_close_digest": authorization.original_accounting_close_digest,
        "original_revenue_recognition_digest": authorization.original_revenue_recognition_digest,
        "original_ledger_event_digest": authorization.original_ledger_event_digest,
        "original_reporting_entry_digest": authorization.original_reporting_entry_digest,
        "period_chain_proof_digest": authorization.period_chain_proof_digest,
        "customer_refund_amount": canonical_decimal_text(authorization.customer_refund_amount),
        "revenue_reduction_amount": canonical_decimal_text(authorization.revenue_reduction_amount),
        "refund_reserve_release_amount": canonical_decimal_text(authorization.refund_reserve_release_amount),
        "tax_adjustment_amount": canonical_decimal_text(authorization.tax_adjustment_amount),
        "tax_treatment": authorization.tax_treatment,
        "tax_account_used": tax_account_used,
        "external_fee_expense_amount": canonical_decimal_text(authorization.external_fee_expense_amount),
        "fee_account_used": fee_account_used,
        "total_cash_outflow_amount": canonical_decimal_text(authorization.total_cash_outflow_amount),
        "external_refund_evidence_digest": authorization.external_refund_evidence_digest,
        "tax_evidence_digest": authorization.tax_evidence_digest or "NONE",
        "fee_evidence_digest": authorization.fee_evidence_digest or "NONE",
        "decision_evidence_digest": authorization.decision_evidence_digest,
        "accounting_policy_digest": authorization.accounting_policy_digest,
        "requirement_registry_digest": authorization.requirement_registry_digest,
    }
    return ledger.post(
        event_id=event_id,
        reference=authorization.authorization_id,
        flow_type=FlowType.EXTERNAL_EXPENSE,
        lines=tuple(lines),
        evidence_digest=authorization.digest,
        metadata=metadata,
    )
