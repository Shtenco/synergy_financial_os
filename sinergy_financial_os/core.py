from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


ZERO = Decimal("0")


class AccountingInvariantError(ValueError):
    """Raised when a hard SINERGY accounting invariant is violated."""


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class FinancialState:
    """Minimal canonical balance-sheet state in one reporting currency.

    Values are Decimal-based to avoid binary-float drift in accounting logic.
    This class deliberately does not accept own-token market capitalization or
    internal AMM marks as hard assets.
    """

    hard_external_assets: Decimal
    liquid_haircut_assets: Decimal
    economic_haircut_assets: Decimal
    external_liabilities: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "hard_external_assets",
            "liquid_haircut_assets",
            "economic_haircut_assets",
            "external_liabilities",
        ):
            value = _d(getattr(self, field_name))
            if value < ZERO:
                raise AccountingInvariantError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, value)

        if self.liquid_haircut_assets < self.hard_external_assets:
            raise AccountingInvariantError(
                "liquid_haircut_assets must be >= hard_external_assets"
            )
        if self.economic_haircut_assets < self.liquid_haircut_assets:
            raise AccountingInvariantError(
                "economic_haircut_assets must be >= liquid_haircut_assets"
            )

    @property
    def hard_nav(self) -> Decimal:
        return self.hard_external_assets - self.external_liabilities

    @property
    def liquid_nav(self) -> Decimal:
        return self.liquid_haircut_assets - self.external_liabilities

    @property
    def economic_nav(self) -> Decimal:
        return self.economic_haircut_assets - self.external_liabilities


def hard_nav_surplus_after_capital(
    previous_hard_nav: Decimal | int | str,
    current_hard_nav: Decimal | int | str,
    net_new_capital: Decimal | int | str,
) -> Decimal:
    """Return the signed HardNAV change after removing net new capital.

    This metric is diagnostic, **not distributable profit**. HardNAV can rise
    when previously owned non-hard assets become hard assets, for example when
    performing-loan principal is repaid into cash. Principal hardening is not
    revenue and must not be distributed merely because this value is positive.
    """

    return _d(current_hard_nav) - _d(previous_hard_nav) - _d(net_new_capital)


def distributable_profit(
    realized_external_pnl: Decimal | int | str,
    required_retention: Decimal | int | str = ZERO,
    loss_carryforward: Decimal | int | str = ZERO,
) -> Decimal:
    """Return the realized P&L budget potentially available for distribution.

    The input must come from explicit, externally evidenced P&L classification
    (revenue/expense/loss accounts), not from gross HardNAV movement. Required
    retention and prior realized loss carryforward reduce the budget.

    Final authorization should additionally pass `distribution_capacity`, which
    applies the current solvency/HardNAV buffer.
    """

    pnl = _d(realized_external_pnl)
    retention = _d(required_retention)
    losses = _d(loss_carryforward)
    if retention < ZERO or losses < ZERO:
        raise AccountingInvariantError(
            "required_retention and loss_carryforward must be non-negative"
        )
    return max(ZERO, pnl - retention - losses)


def distribution_capacity(
    realized_profit_budget: Decimal | int | str,
    hard_nav: Decimal | int | str,
    required_hard_nav_buffer: Decimal | int | str = ZERO,
) -> Decimal:
    """Bound a realized-profit budget by the current HardNAV solvency buffer."""

    budget = _d(realized_profit_budget)
    nav = _d(hard_nav)
    buffer = _d(required_hard_nav_buffer)
    if budget < ZERO or buffer < ZERO:
        raise AccountingInvariantError(
            "realized_profit_budget and required_hard_nav_buffer must be non-negative"
        )
    solvency_headroom = max(ZERO, nav - buffer)
    return min(budget, solvency_headroom)


def ensure_balanced_journal(
    debits: Iterable[Decimal | int | str],
    credits: Iterable[Decimal | int | str],
) -> None:
    """Fail closed unless total debits equal total credits exactly."""

    debit_total = sum((_d(v) for v in debits), ZERO)
    credit_total = sum((_d(v) for v in credits), ZERO)
    if debit_total != credit_total:
        raise AccountingInvariantError(
            f"unbalanced journal: debits={debit_total} credits={credit_total}"
        )


def ensure_maturity_match(
    loan_maturity_weeks: int,
    funding_maturity_weeks: int,
) -> None:
    """Enforce the canonical strict duration rule.

    Replacement-liquidity facilities, if introduced later, must be modeled as
    explicit funding objects rather than silently bypassing this reference rule.
    """

    if loan_maturity_weeks < 1 or funding_maturity_weeks < 1:
        raise AccountingInvariantError("maturities must be positive")
    if loan_maturity_weeks >= funding_maturity_weeks:
        raise AccountingInvariantError(
            "loan_maturity must be strictly shorter than funding_maturity"
        )


def debt_capacity_gap(
    debt_capacity: Decimal | int | str,
    debt_outstanding: Decimal | int | str,
) -> Decimal:
    """Positive value means remaining debt capacity; negative means over-capacity."""

    return _d(debt_capacity) - _d(debt_outstanding)


def coverage_deficit(
    debt_capacity: Decimal | int | str,
    debt_outstanding: Decimal | int | str,
) -> Decimal:
    """Positive value means uncovered debt above the permitted capacity."""

    return max(ZERO, _d(debt_outstanding) - _d(debt_capacity))


def liquidity_coverage_ratio(
    liquid_resources: Decimal | int | str,
    expected_net_outflows: Decimal | int | str,
) -> Decimal | None:
    """Return LCR for one declared horizon.

    `None` means the denominator is zero and the ratio is not numerically
    defined. Callers may treat that state as no outflow pressure, but must not
    serialize an invented finite or infinite ratio.
    """

    resources = _d(liquid_resources)
    outflows = _d(expected_net_outflows)
    if resources < ZERO or outflows < ZERO:
        raise AccountingInvariantError("liquid resources and outflows must be non-negative")
    if outflows == ZERO:
        return None
    return resources / outflows


def liquidity_surplus(
    liquid_resources: Decimal | int | str,
    expected_net_outflows: Decimal | int | str,
) -> Decimal:
    resources = _d(liquid_resources)
    outflows = _d(expected_net_outflows)
    if resources < ZERO or outflows < ZERO:
        raise AccountingInvariantError("liquid resources and outflows must be non-negative")
    return resources - outflows


def ensure_lcr_floor(
    liquid_resources: Decimal | int | str,
    expected_net_outflows: Decimal | int | str,
    minimum_ratio: Decimal | int | str,
) -> None:
    """Fail closed when a non-zero-outflow horizon breaches its LCR floor."""

    floor = _d(minimum_ratio)
    if floor < ZERO:
        raise AccountingInvariantError("minimum_ratio must be non-negative")
    ratio = liquidity_coverage_ratio(liquid_resources, expected_net_outflows)
    if ratio is not None and ratio < floor:
        raise AccountingInvariantError(f"LCR floor breached: ratio={ratio} floor={floor}")
