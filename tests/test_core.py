from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FinancialState,
    coverage_deficit,
    debt_capacity_gap,
    distributable_profit,
    ensure_balanced_journal,
    ensure_maturity_match,
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


def test_new_capital_is_not_distributable_profit() -> None:
    assert distributable_profit("100", "150", "50") == Decimal("0")
    assert distributable_profit("100", "160", "50") == Decimal("10")


def test_distribution_capacity_floors_at_zero_without_hiding_nav_loss() -> None:
    assert distributable_profit("100", "80", "0") == Decimal("0")


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
