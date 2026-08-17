from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountClass,
    AccountingInvariantError,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    ValuationPolicy,
    ValuationRule,
)
from sinergy_financial_os.snapshot import (
    LiquidityHorizonState,
    capture_financial_snapshot_v2,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
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
            "Performing credit",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "PERFORMING_CREDIT",
        ),
        ReportingAccountSpec(
            "liability:deposit",
            "Demand liability",
            AccountClass.LIABILITY,
            ConsolidationClass.EXTERNAL,
            "EXTERNAL_LIABILITY",
            immediate_liability=True,
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
        ReportingAccountSpec(
            "expense:external",
            "External expense",
            AccountClass.EXPENSE,
            ConsolidationClass.EXTERNAL,
            "EXPENSE_ACCOUNT",
        ),
    ):
        ledger.register_account(spec)
    return ledger


def _policy(as_of: datetime = NOW) -> ValuationPolicy:
    return ValuationPolicy(
        "usd-policy-v1",
        "USD",
        as_of,
        (
            ValuationRule(
                "HARD_EXTERNAL_ASSET",
                "1",
                "1",
                "1",
                "BANK_BALANCE",
            ),
            ValuationRule(
                "PERFORMING_CREDIT",
                "0",
                "0",
                "0.8",
                "AUDITED_NAV",
            ),
        ),
    )


def _liquidity() -> tuple[LiquidityHorizonState, ...]:
    return (
        LiquidityHorizonState(1, "80", "40"),
        LiquidityHorizonState(4, "90", "60"),
        LiquidityHorizonState(8, "100", "0"),
    )


def _seed_first_period(ledger: ReportingLedger) -> None:
    ledger.post(
        event_id="capital",
        reference="capital-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("equity:capital", credit="100"),
        ),
    )
    ledger.post(
        event_id="loan",
        reference="loan-ref",
        flow_type=FlowType.CREDIT_ORIGINATION,
        evidence_digest="cd" * 32,
        lines=(
            ReportingLine("asset:credit", debit="40"),
            ReportingLine("asset:cash", credit="40"),
        ),
    )
    ledger.post(
        event_id="interest",
        reference="interest-ref",
        flow_type=FlowType.EXTERNAL_REVENUE,
        evidence_digest="ef" * 32,
        lines=(
            ReportingLine("asset:cash", debit="5"),
            ReportingLine("revenue:external", credit="5"),
        ),
    )


def test_snapshot_binds_ledger_valuation_policy_and_realized_pnl() -> None:
    ledger = _ledger()
    _seed_first_period(ledger)

    snapshot = capture_financial_snapshot_v2(
        ledger,
        _policy(),
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=_liquidity(),
        required_retention="2",
        required_hard_nav_buffer="50",
        maturity_snapshot_refs=("11" * 32,),
    )

    assert snapshot.sequence == 3
    assert snapshot.period_start_sequence == 0
    assert snapshot.hard_external_assets == Decimal("65")
    assert snapshot.hard_nav == Decimal("65")
    assert snapshot.economic_nav == Decimal("97.0")
    assert snapshot.net_new_capital == Decimal("100")
    assert snapshot.realized_external_revenue == Decimal("5")
    assert snapshot.realized_external_pnl == Decimal("5")
    assert snapshot.hard_nav_surplus_after_capital == Decimal("-35")
    assert snapshot.period_profit_budget == Decimal("3")
    assert snapshot.distribution_capacity == Decimal("3")
    assert snapshot.liquidity_horizons[0].lcr == Decimal("2")
    assert snapshot.liquidity_horizons[2].lcr is None
    assert snapshot.ledger_digest == ledger.digest
    assert snapshot.valuation_policy_digest == _policy().digest
    assert snapshot.to_dict()["digest"] == snapshot.digest


def test_principal_repayment_can_raise_hard_nav_without_creating_profit_budget() -> None:
    ledger = _ledger()
    _seed_first_period(ledger)
    first = capture_financial_snapshot_v2(
        ledger,
        _policy(),
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=_liquidity(),
    )

    ledger.post(
        event_id="principal-repay",
        reference="principal-repay-ref",
        flow_type=FlowType.CREDIT_REPAYMENT,
        evidence_digest="12" * 32,
        lines=(
            ReportingLine("asset:cash", debit="40"),
            ReportingLine("asset:credit", credit="40"),
        ),
    )
    second = capture_financial_snapshot_v2(
        ledger,
        _policy(),
        as_of=NOW + timedelta(hours=1),
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=_liquidity(),
        previous_snapshot=first,
    )

    assert second.previous_snapshot_digest == first.digest
    assert second.period_start_sequence == first.sequence
    assert second.hard_nav - first.hard_nav == Decimal("40")
    assert second.hard_nav_surplus_after_capital == Decimal("40")
    assert second.realized_external_pnl == Decimal("0")
    assert second.period_profit_budget == Decimal("0")
    assert second.distribution_capacity == Decimal("0")


def test_external_liability_is_in_snapshot_coverage_and_immediate_liability() -> None:
    ledger = _ledger()
    ledger.post(
        event_id="deposit",
        reference="deposit-ref",
        flow_type=FlowType.LIABILITY_ISSUANCE,
        evidence_digest=EVIDENCE,
        lines=(
            ReportingLine("asset:cash", debit="100"),
            ReportingLine("liability:deposit", credit="100"),
        ),
    )
    snapshot = capture_financial_snapshot_v2(
        ledger,
        _policy(),
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=_liquidity(),
    )
    assert snapshot.hard_external_assets == Decimal("100")
    assert snapshot.external_liabilities == Decimal("100")
    assert snapshot.immediate_external_liabilities == Decimal("100")
    assert snapshot.hard_nav == Decimal("0")
    assert snapshot.hard_coverage == Decimal("1")


def test_snapshot_rejects_policy_currency_mismatch() -> None:
    ledger = _ledger()
    bad_policy = ValuationPolicy(
        "kzt-policy",
        "KZT",
        NOW,
        (
            ValuationRule(
                "HARD_EXTERNAL_ASSET", "1", "1", "1", "BANK_BALANCE"
            ),
        ),
    )
    with pytest.raises(AccountingInvariantError):
        capture_financial_snapshot_v2(
            ledger,
            bad_policy,
            as_of=NOW,
            accounting_perimeter="SINERGY_CONSOLIDATED",
            liquidity_horizons=_liquidity(),
        )


def test_snapshot_rejects_future_valuation_policy() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        capture_financial_snapshot_v2(
            ledger,
            _policy(NOW + timedelta(seconds=1)),
            as_of=NOW,
            accounting_perimeter="SINERGY_CONSOLIDATED",
            liquidity_horizons=_liquidity(),
        )


def test_snapshot_requires_exactly_1_4_8_week_liquidity_horizons() -> None:
    ledger = _ledger()
    with pytest.raises(AccountingInvariantError):
        capture_financial_snapshot_v2(
            ledger,
            _policy(),
            as_of=NOW,
            accounting_perimeter="SINERGY_CONSOLIDATED",
            liquidity_horizons=(
                LiquidityHorizonState(1, "10", "5"),
                LiquidityHorizonState(4, "10", "5"),
            ),
        )


def test_snapshot_chain_cannot_change_accounting_perimeter_silently() -> None:
    ledger = _ledger()
    _seed_first_period(ledger)
    first = capture_financial_snapshot_v2(
        ledger,
        _policy(),
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=_liquidity(),
    )
    with pytest.raises(AccountingInvariantError):
        capture_financial_snapshot_v2(
            ledger,
            _policy(),
            as_of=NOW + timedelta(hours=1),
            accounting_perimeter="OTHER_PERIMETER",
            liquidity_horizons=_liquidity(),
            previous_snapshot=first,
        )
