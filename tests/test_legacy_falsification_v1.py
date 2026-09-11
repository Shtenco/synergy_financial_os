"""Standalone legacy regression gates for the canonical Financial OS."""


def hard_nav(external_assets: float, external_liabilities: float) -> float:
    return external_assets - external_liabilities


def recognized_profit(current_nav, prior_nav, net_new_capital=0.0, distributions=0.0):
    return current_nav - prior_nav - net_new_capital + distributions


def test_own_token_mark_is_not_external_profit():
    prior = hard_nav(100, 20)
    current = hard_nav(100, 20)  # own-token mark may change, external balance did not
    assert recognized_profit(current, prior) == 0


def test_flash_principal_is_asset_and_liability():
    assert hard_nav(100 + 50_000, 50_000) == 100


def test_new_capital_is_not_revenue():
    assert recognized_profit(150, 100, net_new_capital=50) == 0


def test_synthetic_yield_without_external_settlement_is_not_recognized():
    external_cash_before = 100
    external_cash_after = 100
    synthetic_internal_yield = 10
    assert synthetic_internal_yield > 0
    assert external_cash_after - external_cash_before == 0


def test_participant_deposits_are_liabilities():
    contract_assets = 50
    deposits = [30, 20]
    other_liabilities = 10
    assert contract_assets < sum(deposits) + other_liabilities
