from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FinancialState,
    LiquidityHorizonState,
    ReportingLine,
    ValuationRule,
    distributable_profit,
    liquidity_coverage_ratio,
)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", Decimal("NaN")])
def test_core_rejects_non_finite_decimals(bad) -> None:
    with pytest.raises(AccountingInvariantError):
        distributable_profit(bad)
    with pytest.raises(AccountingInvariantError):
        liquidity_coverage_ratio(bad, "1")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_financial_state_rejects_non_finite_values(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        FinancialState(bad, "1", "1", "0")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_reporting_line_rejects_non_finite_amounts(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        ReportingLine("asset:cash", debit=bad)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_valuation_rule_rejects_non_finite_factors(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule("TEST", "0", "0", bad, "MODEL")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_liquidity_horizon_rejects_non_finite_values(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        LiquidityHorizonState(1, bad, "1")
