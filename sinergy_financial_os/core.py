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


def distributable_profit(
    previous_hard_nav: Decimal | int | str,
    current_hard_nav: Decimal | int | str,
    net_new_capital: Decimal | int | str,
) -> Decimal:
    """Return realized distributable profit under the canonical HardNAV rule.

    New participant/sponsor capital is removed from the period NAV change.
    Negative results floor at zero for *distribution capacity*; economic losses
    remain visible in the underlying NAV series and must not be erased.
    """

    raw = _d(current_hard_nav) - _d(previous_hard_nav) - _d(net_new_capital)
    return max(ZERO, raw)


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
