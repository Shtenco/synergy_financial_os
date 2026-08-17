from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .core import AccountingInvariantError


ZERO = Decimal("0")
ONE = Decimal("1")
ZERO_VALUE_CLASSES = frozenset({"OWN_ISSUED_INSTRUMENT", "INTERNAL_CLAIM", "MEMO_ONLY"})


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class ValuationTiers:
    hard: Decimal
    liquid: Decimal
    economic: Decimal


@dataclass(frozen=True)
class ValuationRule:
    valuation_class: str
    hard_factor: Decimal
    liquid_factor: Decimal
    economic_factor: Decimal
    price_source_class: str
    requires_external_enforceability: bool = False
    requires_intragroup_elimination: bool = False

    def __post_init__(self) -> None:
        valuation_class = self.valuation_class.upper().strip()
        source_class = self.price_source_class.upper().strip()
        if not valuation_class:
            raise AccountingInvariantError("valuation_class is required")
        if not source_class:
            raise AccountingInvariantError("price_source_class is required")

        hard = _d(self.hard_factor)
        liquid = _d(self.liquid_factor)
        economic = _d(self.economic_factor)
        if not ZERO <= hard <= liquid <= economic <= ONE:
            raise AccountingInvariantError(
                "valuation factors must satisfy 0 <= hard <= liquid <= economic <= 1"
            )
        if valuation_class in ZERO_VALUE_CLASSES and any(
            factor != ZERO for factor in (hard, liquid, economic)
        ):
            raise AccountingInvariantError(
                f"{valuation_class} must have zero consolidated valuation factors"
            )

        object.__setattr__(self, "valuation_class", valuation_class)
        object.__setattr__(self, "price_source_class", source_class)
        object.__setattr__(self, "hard_factor", hard)
        object.__setattr__(self, "liquid_factor", liquid)
        object.__setattr__(self, "economic_factor", economic)

    def apply(self, positive_value: Decimal | int | str) -> ValuationTiers:
        amount = _d(positive_value)
        if amount < ZERO:
            raise AccountingInvariantError("asset value must be non-negative")
        return ValuationTiers(
            hard=amount * self.hard_factor,
            liquid=amount * self.liquid_factor,
            economic=amount * self.economic_factor,
        )
