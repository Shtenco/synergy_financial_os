import pytest

from sinergy_financial_os import (
    AccountClass,
    AccountingInvariantError,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)


EVIDENCE = "ab" * 32


def _ledger() -> ReportingLedger:
    ledger = ReportingLedger("USD")
    for spec in (
        ReportingAccountSpec(
            "asset:cash",
            "Cash",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "HARD_EXTERNAL_ASSET",
        ),
        ReportingAccountSpec(
            "asset:credit",
            "Credit principal",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "PERFORMING_CREDIT",
        ),
        ReportingAccountSpec(
            "revenue:external",
            "External revenue",
            AccountClass.REVENUE,
            ConsolidationClass.EXTERNAL,
            "REVENUE_ACCOUNT",
        ),
        ReportingAccountSpec(
            "expense:external",
            "External expense",
            AccountClass.EXPENSE,
            ConsolidationClass.EXTERNAL,
            "EXPENSE_ACCOUNT",
        ),
        ReportingAccountSpec(
            "equity:capital",
            "Capital",
            AccountClass.EQUITY,
            ConsolidationClass.EXTERNAL,
            "EQUITY_ACCOUNT",
        ),
    ):
        ledger.register_account(spec)
    return ledger


def test_credit_repayment_cannot_hide_interest_in_principal_flow() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="mixed-repayment",
            reference="bank-repayment-ref",
            flow_type=FlowType.CREDIT_REPAYMENT,
            evidence_digest=EVIDENCE,
            lines=(
                ReportingLine("asset:cash", debit="45"),
                ReportingLine("asset:credit", credit="40"),
                ReportingLine("revenue:external", credit="5"),
            ),
        )


def test_principal_and_interest_can_share_evidence_but_use_separate_entries() -> None:
    ledger = _ledger()
    ledger.post(
        event_id="seed",
        reference="seed-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest="cd" * 32,
        lines=(
            ReportingLine("asset:credit", debit="40"),
            ReportingLine("equity:capital", credit="40"),
        ),
    )
    ledger.post(
        event_id="principal",
        reference="repayment-principal-ref",
        flow_type=FlowType.CREDIT_REPAYMENT,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="40"),
            ReportingLine("asset:credit", credit="40"),
        ),
    )
    ledger.post(
        event_id="interest",
        reference="repayment-interest-ref",
        flow_type=FlowType.EXTERNAL_REVENUE,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="5"),
            ReportingLine("revenue:external", credit="5"),
        ),
    )
    assert ledger.sequence == 3


def test_external_revenue_requires_positive_pnl_line() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="fake-revenue",
            reference="fake-revenue-ref",
            flow_type=FlowType.EXTERNAL_REVENUE,
            evidence_digest=EVIDENCE,
            lines=(
                ReportingLine("asset:cash", debit="10"),
                ReportingLine("equity:capital", credit="10"),
            ),
        )


def test_external_expense_requires_negative_pnl_line() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="fake-expense",
            reference="fake-expense-ref",
            flow_type=FlowType.EXTERNAL_EXPENSE,
            evidence_digest=EVIDENCE,
            lines=(
                ReportingLine("asset:cash", debit="10"),
                ReportingLine("equity:capital", credit="10"),
            ),
        )


def test_credit_loss_requires_negative_pnl_line() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="fake-loss",
            reference="fake-loss-ref",
            flow_type=FlowType.CREDIT_LOSS,
            evidence_digest=EVIDENCE,
            lines=(
                ReportingLine("asset:cash", debit="10"),
                ReportingLine("equity:capital", credit="10"),
            ),
        )
