from datetime import UTC, datetime

import pytest

from sinergy_financial_os import AccountingInvariantError, ValuationPolicy, ValuationRule


def _rule(name: str = "HARD_EXTERNAL_ASSET") -> ValuationRule:
    return ValuationRule(
        name,
        "1" if name == "HARD_EXTERNAL_ASSET" else "0",
        "1" if name == "HARD_EXTERNAL_ASSET" else "0.8",
        "1" if name == "HARD_EXTERNAL_ASSET" else "0.9",
        "BANK_BALANCE" if name == "HARD_EXTERNAL_ASSET" else "AUDITED_NAV",
    )


def test_policy_digest_is_deterministic_and_rule_order_independent() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    first = ValuationPolicy(
        "policy-v1",
        "KZT",
        now,
        (_rule("PERFORMING_CREDIT"), _rule()),
    )
    second = ValuationPolicy(
        "policy-v1",
        "kzt",
        now,
        (_rule(), _rule("PERFORMING_CREDIT")),
    )
    assert first.digest == second.digest
    assert first.rule_map.keys() == second.rule_map.keys()
    assert len(first.digest) == 64


def test_policy_digest_changes_when_haircut_changes() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    first = ValuationPolicy("policy-v1", "KZT", now, (_rule("PERFORMING_CREDIT"),))
    changed = ValuationPolicy(
        "policy-v1",
        "KZT",
        now,
        (
            ValuationRule(
                "PERFORMING_CREDIT",
                "0",
                "0.7",
                "0.85",
                "AUDITED_NAV",
            ),
        ),
    )
    assert first.digest != changed.digest


def test_policy_canonical_dict_normalizes_equivalent_factor_text() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    policy = ValuationPolicy(
        "policy-v1",
        "usd",
        now,
        (
            ValuationRule(
                "PERFORMING_CREDIT",
                "0.00",
                "0.8000",
                "0.900",
                "AUDITED_NAV",
            ),
        ),
    )
    rule = policy.canonical_dict()["rules"][0]
    assert rule["hard_factor"] == "0"
    assert rule["liquid_factor"] == "0.8"
    assert rule["economic_factor"] == "0.9"
    assert policy.reporting_currency == "USD"


def test_policy_rejects_duplicate_valuation_classes() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationPolicy(
            "policy-v1",
            "KZT",
            datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
            (_rule(), _rule()),
        )


def test_policy_requires_timezone_aware_as_of() -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationPolicy(
            "policy-v1",
            "KZT",
            datetime(2026, 8, 17, 12, 0),
            (_rule(),),
        )


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_rule_rejects_nonfinite_factors(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        ValuationRule(
            "PERFORMING_CREDIT",
            "0",
            bad,
            "1",
            "AUDITED_NAV",
        )


def test_rule_rejects_unknown_price_source_class() -> None:
    with pytest.raises(AccountingInvariantError, match="price_source_class"):
        ValuationRule(
            "PERFORMING_CREDIT",
            "0",
            "0.8",
            "0.9",
            "MANUAL_MAGIC_PRICE",
        )


def test_rule_rejects_unsafe_or_boolean_staleness() -> None:
    for bad in (True, 9_007_199_254_740_992):
        with pytest.raises(AccountingInvariantError, match="safe integer"):
            ValuationRule(
                "PERFORMING_CREDIT",
                "0",
                "0.8",
                "0.9",
                "AUDITED_NAV",
                max_staleness_seconds=bad,
            )
