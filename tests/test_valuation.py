from decimal import Decimal

import pytest

from sinergy_financial_os import AccountingInvariantError, ValuationRule


def test_tiered_valuation_preserves_hard_liquid_economic_order() -> None:
    rule = ValuationRule(
        valuation_class="LIQUID_MARKET_ASSET",
        hard_factor="0",
        liquid_factor="0.80",
        economic_factor="0.90",
        price_source_class="EXECUTABLE_MARKET",
    )
    valued = rule.apply("100")
    assert valued.hard == Decimal("0")
    assert valued.liquid == Decimal("80.00")
    assert valued.economic == Decimal("90.00")


def test_invalid_factor_order_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            valuation_class="BAD",
            hard_factor="0.9",
            liquid_factor="0.8",
            economic_factor="1",
            price_source_class="MODEL",
        )


def test_own_issued_instrument_must_have_zero_consolidated_value() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            valuation_class="OWN_ISSUED_INSTRUMENT",
            hard_factor="0",
            liquid_factor="0",
            economic_factor="0.1",
            price_source_class="EXECUTABLE_MARKET",
        )

    rule = ValuationRule(
        valuation_class="OWN_ISSUED_INSTRUMENT",
        hard_factor="0",
        liquid_factor="0",
        economic_factor="0",
        price_source_class="EXECUTABLE_MARKET",
    )
    assert rule.apply("1000000").economic == Decimal("0")


def test_internal_claim_must_be_eliminated_in_consolidated_reference() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            valuation_class="INTERNAL_CLAIM",
            hard_factor="0",
            liquid_factor="0",
            economic_factor="1",
            price_source_class="PAR",
            requires_intragroup_elimination=True,
        )


def test_negative_asset_value_is_rejected() -> None:
    rule = ValuationRule(
        valuation_class="HARD_EXTERNAL_ASSET",
        hard_factor="1",
        liquid_factor="1",
        economic_factor="1",
        price_source_class="BANK_BALANCE",
        requires_external_enforceability=True,
    )
    with pytest.raises(AccountingInvariantError):
        rule.apply("-1")
