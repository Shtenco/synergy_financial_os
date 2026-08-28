from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FinancialState,
    coverage_deficit,
    debt_capacity_gap,
    distributable_profit,
    distribution_capacity,
    ensure_balanced_journal,
    ensure_lcr_floor,
    ensure_maturity_match,
    hard_nav_surplus_after_capital,
    liquidity_coverage_ratio,
    liquidity_surplus,
)


def test_nav_layers_follow_asset_haircut_order() -> None:
    state = FinancialState(
        hard_external_assets=Decimal("100"),
        liquid_haircut_assets=Decimal("120"),
        economic_haircut_assets=Decimal("150"),
        external_liabilities=Decimal("40"),
    )
    assert state.hard_nav == Decimal("60")
    assert state.liquid_nav == Decimal("80")
    assert state.economic_nav == Decimal("110")


def test_state_rejects_invalid_nav_asset_order() -> None:
    with pytest.raises(AccountingInvariantError):
        FinancialState(
            hard_external_assets=Decimal("100"),
            liquid_haircut_assets=Decimal("90"),
            economic_haircut_assets=Decimal("110"),
            external_liabilities=Decimal("10"),
        )


def test_hard_nav_surplus_after_capital_is_diagnostic_not_profit() -> None:
    assert hard_nav_surplus_after_capital("100", "150", "50") == Decimal("0")
    assert hard_nav_surplus_after_capital("100", "160", "50") == Decimal("10")
    assert hard_nav_surplus_after_capital("100", "80", "0") == Decimal("-20")


def test_distributable_profit_comes_from_realized_external_pnl() -> None:
    assert distributable_profit("10") == Decimal("10")
    assert distributable_profit("10", required_retention="3") == Decimal("7")
    assert distributable_profit("10", required_retention="3", loss_carryforward="8") == Decimal("0")
    assert distributable_profit("-5") == Decimal("0")


def test_distribution_capacity_is_bounded_by_hard_nav_buffer() -> None:
    assert distribution_capacity("10", hard_nav="30", required_hard_nav_buffer="15") == Decimal("10")
    assert distribution_capacity("20", hard_nav="30", required_hard_nav_buffer="15") == Decimal("15")
    assert distribution_capacity("20", hard_nav="10", required_hard_nav_buffer="15") == Decimal("0")


def test_profit_budget_inputs_reject_negative_retention_or_budget() -> None:
    with pytest.raises(AccountingInvariantError):
        distributable_profit("10", required_retention="-1")
    with pytest.raises(AccountingInvariantError):
        distribution_capacity("-1", hard_nav="10")


def test_balanced_journal_passes() -> None:
    ensure_balanced_journal(["100", "25.50"], ["125.50"])


def test_unbalanced_journal_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        ensure_balanced_journal(["100"], ["99.99"])


def test_maturity_must_be_strictly_shorter() -> None:
    ensure_maturity_match(12, 13)
    with pytest.raises(AccountingInvariantError):
        ensure_maturity_match(12, 12)
    with pytest.raises(AccountingInvariantError):
        ensure_maturity_match(13, 12)


def test_debt_capacity_gap_sign_is_unambiguous() -> None:
    assert debt_capacity_gap("100", "70") == Decimal("30")
    assert debt_capacity_gap("100", "120") == Decimal("-20")


def test_coverage_deficit_is_only_positive_when_outstanding_exceeds_capacity() -> None:
    assert coverage_deficit("100", "70") == Decimal("0")
    assert coverage_deficit("100", "120") == Decimal("20")


def test_liquidity_coverage_ratio_uses_explicit_horizon_outflows() -> None:
    assert liquidity_coverage_ratio("150", "100") == Decimal("1.5")
    assert liquidity_surplus("150", "100") == Decimal("50")


def test_zero_outflow_lcr_is_undefined_not_fake_infinity() -> None:
    assert liquidity_coverage_ratio("150", "0") is None
    ensure_lcr_floor("0", "0", "1")


def test_lcr_floor_fails_closed_when_nonzero_outflows_are_undercovered() -> None:
    ensure_lcr_floor("120", "100", "1.1")
    with pytest.raises(AccountingInvariantError):
        ensure_lcr_floor("100", "100", "1.1")


def test_lcr_inputs_cannot_be_negative() -> None:
    with pytest.raises(AccountingInvariantError):
        liquidity_coverage_ratio("-1", "10")
