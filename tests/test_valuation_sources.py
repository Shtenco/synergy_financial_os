import pytest

from sinergy_financial_os import AccountingInvariantError, ValuationRule


ALLOWED = {
    "PAR",
    "BANK_BALANCE",
    "AUDITED_NAV",
    "EXECUTABLE_MARKET",
    "ORACLE",
    "MODEL",
    "NONE",
}


def test_all_canonical_price_source_classes_are_accepted() -> None:
    for source in ALLOWED:
        rule = ValuationRule(
            valuation_class="TEST_ASSET",
            hard_factor="0",
            liquid_factor="0",
            economic_factor="0",
            price_source_class=source.lower(),
        )
        assert rule.price_source_class == source


def test_unknown_price_source_class_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            valuation_class="TEST_ASSET",
            hard_factor="0",
            liquid_factor="0",
            economic_factor="0",
            price_source_class="TRUST_ME_BRO_PRICE",
        )


def test_empty_price_source_class_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            valuation_class="TEST_ASSET",
            hard_factor="0",
            liquid_factor="0",
            economic_factor="0",
            price_source_class=" ",
        )
