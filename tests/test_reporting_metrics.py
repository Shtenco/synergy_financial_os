from decimal import Decimal

from sinergy_financial_os import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    ValuationRule,
    hard_nav_effect,
    net_new_capital_since,
    realized_external_revenue_since,
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
            "asset:market",
            "Hard-valued market asset",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "HARD_EXTERNAL_ASSET",
        ),
        ReportingAccountSpec(
            "asset:credit",
            "Performing credit",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "PERFORMING_CREDIT",
        ),
        ReportingAccountSpec(
            "liability:synt",
            "External monetary liability",
            AccountClass.LIABILITY,
            ConsolidationClass.EXTERNAL,
            "EXTERNAL_LIABILITY",
        ),
        ReportingAccountSpec(
            "equity:capital",
            "Capital",
            AccountClass.EQUITY,
            ConsolidationClass.EXTERNAL,
            "EQUITY_ACCOUNT",
        ),
        ReportingAccountSpec(
            "revenue:external",
            "External revenue",
            AccountClass.REVENUE,
            ConsolidationClass.EXTERNAL,
            "REVENUE_ACCOUNT",
        ),
    ):
        ledger.register_account(spec)
    return ledger


def _policy() -> dict[str, ValuationRule]:
    return {
        "HARD_EXTERNAL_ASSET": ValuationRule(
            "HARD_EXTERNAL_ASSET", "1", "1", "1", "BANK_BALANCE"
        ),
        "PERFORMING_CREDIT": ValuationRule(
            "PERFORMING_CREDIT", "0", "0", "0.8", "AUDITED_NAV"
        ),
    }


def test_capital_injection_has_positive_hard_nav_effect_and_is_net_new_capital() -> None:
    ledger = _ledger()
    entry = ledger.post(
        event_id="capital-1",
        reference="capital-bank-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    assert hard_nav_effect(ledger, entry, _policy()) == Decimal("100")
    assert net_new_capital_since(ledger, 0, _policy()) == Decimal("100")
    assert realized_external_revenue_since(ledger, 0, _policy()) == Decimal("0")


def test_liability_issuance_has_zero_hard_nav_effect() -> None:
    ledger = _ledger()
    entry = ledger.post(
        event_id="liability-1",
        reference="liability-ref",
        flow_type=FlowType.LIABILITY_ISSUANCE,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="50"),
            ReportingLine("liability:synt", credit="50"),
        ),
    )
    assert hard_nav_effect(ledger, entry, _policy()) == Decimal("0")


def test_asset_sale_counts_only_net_hard_nav_gain_not_gross_cash_debit() -> None:
    ledger = _ledger()
    ledger.post(
        event_id="seed-market",
        reference="seed-market-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:market", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    revenue_entry = ledger.post(
        event_id="sale-profit",
        reference="external-sale-ref",
        flow_type=FlowType.EXTERNAL_REVENUE,
        evidence_digest="cd" * 32,
        lines=(
            ReportingLine("asset:cash", debit="110"),
            ReportingLine("asset:market", credit="100"),
            ReportingLine("revenue:external", credit="10"),
        ),
    )

    assert hard_nav_effect(ledger, revenue_entry, _policy()) == Decimal("10")
    assert realized_external_revenue_since(ledger, 1, _policy()) == Decimal("10")


def test_credit_principal_repayment_is_not_revenue() -> None:
    ledger = _ledger()
    ledger.post(
        event_id="seed-cash",
        reference="seed-cash-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    ledger.post(
        event_id="loan-1",
        reference="loan-origination-ref",
        flow_type=FlowType.CREDIT_ORIGINATION,
        evidence_digest="ef" * 32,
        lines=(
            ReportingLine("asset:credit", debit="40"),
            ReportingLine("asset:cash", credit="40"),
        ),
    )
    repayment = ledger.post(
        event_id="repay-1",
        reference="loan-repayment-ref",
        flow_type=FlowType.CREDIT_REPAYMENT,
        evidence_digest="12" * 32,
        lines=(
            ReportingLine("asset:cash", debit="40"),
            ReportingLine("asset:credit", credit="40"),
        ),
    )

    assert hard_nav_effect(ledger, repayment, _policy()) == Decimal("40")
    assert realized_external_revenue_since(ledger, 0, _policy()) == Decimal("0")


def test_revenue_paid_by_extinguishing_external_liability_can_raise_hard_nav() -> None:
    ledger = _ledger()
    ledger.post(
        event_id="issue-synt",
        reference="issue-synt-ref",
        flow_type=FlowType.LIABILITY_ISSUANCE,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="50"),
            ReportingLine("liability:synt", credit="50"),
        ),
    )
    revenue = ledger.post(
        event_id="fee-in-synt",
        reference="fee-in-synt-ref",
        flow_type=FlowType.EXTERNAL_REVENUE,
        evidence_digest="34" * 32,
        lines=(
            ReportingLine("liability:synt", debit="5"),
            ReportingLine("revenue:external", credit="5"),
        ),
    )

    assert hard_nav_effect(ledger, revenue, _policy()) == Decimal("5")
    assert realized_external_revenue_since(ledger, 1, _policy()) == Decimal("5")
