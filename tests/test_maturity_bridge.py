import hashlib
import json
from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    MaturityTranslation,
    contractual_outflows_by_horizon,
    liquidity_horizon_states_from_maturity,
    translate_maturity_outflows,
    verify_maturity_snapshot_digest,
)


def _digest(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(currency: str = "KZT") -> dict:
    cumulative = {
        1: Decimal("0"),
        2: Decimal("0"),
        3: Decimal("0"),
        4: Decimal("200"),
        5: Decimal("200"),
        6: Decimal("200"),
        7: Decimal("200"),
        8: Decimal("500"),
    }
    total_cumulative = {
        1: Decimal("0"),
        2: Decimal("0"),
        3: Decimal("0"),
        4: Decimal("300"),
        5: Decimal("300"),
        6: Decimal("300"),
        7: Decimal("300"),
        8: Decimal("600"),
    }
    buckets = []
    previous_noncallable = Decimal("0")
    previous_total = Decimal("0")
    for week in range(1, 9):
        noncallable = cumulative[week]
        total = total_cumulative[week]
        buckets.append(
            {
                "week": week,
                "scheduled_unlock": format(total - previous_total, "f"),
                "cumulative_unlock": format(total, "f"),
                "scheduled_noncallable_unlock": format(
                    noncallable - previous_noncallable, "f"
                ),
                "cumulative_noncallable_unlock": format(noncallable, "f"),
                "duration_eligible_principal": "0",
            }
        )
        previous_noncallable = noncallable
        previous_total = total

    payload = {
        "schema": "maturity.snapshot/v1",
        "as_of": "2026-08-17T12:00:00+00:00",
        "as_of_week": 0,
        "currency": currency,
        "total_open_principal": "600",
        "immediately_callable_principal": "100",
        "buckets": buckets,
        "metadata": {
            "horizon_weeks": 8,
            "liquidity_outflow_rule": (
                "immediately_callable_principal + cumulative_noncallable_unlock"
            ),
        },
    }
    payload["digest"] = _digest(payload)
    return payload


def test_verified_maturity_outflow_does_not_double_count_callable_principal() -> None:
    snapshot = _snapshot()
    assert verify_maturity_snapshot_digest(snapshot) == snapshot["digest"]
    outflows = contractual_outflows_by_horizon(snapshot)
    assert outflows == {
        1: Decimal("100"),
        4: Decimal("300"),
        8: Decimal("600"),
    }
    assert outflows[4] != Decimal("400")


def test_tampered_maturity_snapshot_is_rejected() -> None:
    snapshot = _snapshot()
    snapshot["immediately_callable_principal"] = "101"
    with pytest.raises(AccountingInvariantError):
        verify_maturity_snapshot_digest(snapshot)


def test_same_currency_translation_requires_exact_rate_one() -> None:
    snapshot = _snapshot("USD")
    translation = MaturityTranslation("USD", "USD", "1")
    assert translate_maturity_outflows(snapshot, translation)[4] == Decimal("300")

    with pytest.raises(AccountingInvariantError):
        MaturityTranslation("USD", "USD", "0.99")


def test_cross_currency_translation_requires_evidence_digest() -> None:
    with pytest.raises(AccountingInvariantError):
        MaturityTranslation("KZT", "USD", "0.002")

    translation = MaturityTranslation(
        "KZT",
        "USD",
        "0.002",
        translation_evidence_digest="ab" * 32,
    )
    translated = translate_maturity_outflows(_snapshot("KZT"), translation)
    assert translated[1] == Decimal("0.200")
    assert translated[4] == Decimal("0.600")
    assert translated[8] == Decimal("1.200")


def test_liquidity_horizon_states_combine_translated_outflows_with_asset_side() -> None:
    states = liquidity_horizon_states_from_maturity(
        _snapshot("USD"),
        MaturityTranslation("USD", "USD", "1"),
        {1: "200", 4: "450", 8: "900"},
    )
    assert [state.horizon_weeks for state in states] == [1, 4, 8]
    assert states[0].expected_net_outflows == Decimal("100")
    assert states[0].lcr == Decimal("2")
    assert states[1].expected_net_outflows == Decimal("300")
    assert states[1].lcr == Decimal("1.5")
    assert states[2].expected_net_outflows == Decimal("600")
    assert states[2].lcr == Decimal("1.5")


def test_missing_liquid_resource_horizon_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        liquidity_horizon_states_from_maturity(
            _snapshot("USD"),
            MaturityTranslation("USD", "USD", "1"),
            {1: "200", 4: "450"},
        )
