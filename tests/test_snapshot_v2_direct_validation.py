from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FinancialSnapshotV2,
    LiquidityHorizonState,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
HEX_A = "aa" * 32
HEX_B = "bb" * 32
HEX_C = "cc" * 32
HEX_D = "dd" * 32


def _snapshot() -> FinancialSnapshotV2:
    return FinancialSnapshotV2(
        sequence=10,
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        reporting_currency="USD",
        ledger_digest=HEX_A,
        ledger_last_entry_digest=HEX_B,
        account_registry_digest=HEX_C,
        valuation_policy_id="policy-v1",
        valuation_policy_digest=HEX_D,
        valuation_policy_as_of=NOW,
        period_start_sequence=5,
        previous_snapshot_digest=HEX_A,
        hard_external_assets=Decimal("120"),
        external_liabilities=Decimal("20"),
        immediate_external_liabilities=Decimal("10"),
        hard_nav=Decimal("100"),
        liquid_nav=Decimal("110"),
        economic_nav=Decimal("130"),
        hard_coverage=Decimal("6"),
        net_new_capital=Decimal("0"),
        realized_external_revenue=Decimal("12"),
        realized_external_pnl=Decimal("10"),
        hard_nav_surplus_after_capital=Decimal("10"),
        required_retention=Decimal("2"),
        loss_carryforward=Decimal("1"),
        period_profit_budget=Decimal("7"),
        required_hard_nav_buffer=Decimal("95"),
        distribution_capacity=Decimal("5"),
        liquidity_horizons=(
            LiquidityHorizonState(1, "50", "10"),
            LiquidityHorizonState(4, "60", "20"),
            LiquidityHorizonState(8, "70", "0"),
        ),
        maturity_snapshot_refs=(HEX_B,),
        policy_mode="NORMAL",
        invariant_failures=(),
    )


def test_direct_snapshot_normalizes_decimal_string_inputs() -> None:
    snapshot = replace(
        _snapshot(),
        hard_external_assets="120",
        external_liabilities="20",
        hard_nav="100",
        hard_coverage="6",
    )
    assert snapshot.hard_external_assets == Decimal("120")
    assert snapshot.hard_nav == Decimal("100")
    assert snapshot.hard_coverage == Decimal("6")


def test_direct_snapshot_rejects_hard_nav_mismatch() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), hard_nav="101")


def test_direct_snapshot_rejects_nav_order_violation() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), liquid_nav="90")


def test_direct_snapshot_rejects_hard_coverage_mismatch() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), hard_coverage="5")


def test_direct_snapshot_rejects_immediate_liability_above_total_liability() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), immediate_external_liabilities="21")


def test_direct_snapshot_rejects_profit_budget_not_matching_pnl_policy() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), period_profit_budget="8")


def test_direct_snapshot_rejects_distribution_above_solvency_headroom() -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), distribution_capacity="6")


def test_direct_snapshot_requires_null_coverage_when_no_external_liabilities() -> None:
    no_liabilities = replace(
        _snapshot(),
        external_liabilities="0",
        immediate_external_liabilities="0",
        hard_nav="120",
        liquid_nav="130",
        economic_nav="150",
        hard_coverage=None,
        required_hard_nav_buffer="115",
        distribution_capacity="5",
    )
    assert no_liabilities.hard_coverage is None

    with pytest.raises(AccountingInvariantError):
        replace(no_liabilities, hard_coverage="1")


def test_direct_snapshot_rejects_negative_nonnegative_fields() -> None:
    for field_name in (
        "hard_external_assets",
        "external_liabilities",
        "immediate_external_liabilities",
        "realized_external_revenue",
        "required_retention",
        "loss_carryforward",
        "period_profit_budget",
        "required_hard_nav_buffer",
        "distribution_capacity",
    ):
        with pytest.raises(AccountingInvariantError):
            replace(_snapshot(), **{field_name: "-1"})
