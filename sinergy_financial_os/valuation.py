from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from .canonical_json import MAX_SAFE_JSON_INTEGER, canonical_json_digest
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal


ZERO = Decimal("0")
ONE = Decimal("1")
ZERO_VALUE_CLASSES = frozenset({"OWN_ISSUED_INSTRUMENT", "INTERNAL_CLAIM", "MEMO_ONLY"})
PRICE_SOURCE_CLASSES = frozenset(
    {"PAR", "BANK_BALANCE", "AUDITED_NAV", "EXECUTABLE_MARKET", "ORACLE", "MODEL", "NONE"}
)


def _d(value: Decimal | int | str, field_name: str = "value") -> Decimal:
    return finite_decimal(value, field_name)


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
    max_staleness_seconds: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        valuation_class = self.valuation_class.upper().strip()
        source_class = self.price_source_class.upper().strip()
        if not valuation_class:
            raise AccountingInvariantError("valuation_class is required")
        if source_class not in PRICE_SOURCE_CLASSES:
            raise AccountingInvariantError(
                f"unsupported price_source_class: {source_class or '<empty>'}"
            )

        hard = _d(self.hard_factor, "hard_factor")
        liquid = _d(self.liquid_factor, "liquid_factor")
        economic = _d(self.economic_factor, "economic_factor")
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

        staleness = self.max_staleness_seconds
        if staleness is not None:
            if (
                not isinstance(staleness, int)
                or isinstance(staleness, bool)
                or staleness < 0
                or staleness > MAX_SAFE_JSON_INTEGER
            ):
                raise AccountingInvariantError(
                    "max_staleness_seconds must be a non-negative cross-language safe integer"
                )

        notes = None if self.notes is None else self.notes.strip() or None

        object.__setattr__(self, "valuation_class", valuation_class)
        object.__setattr__(self, "price_source_class", source_class)
        object.__setattr__(self, "hard_factor", hard)
        object.__setattr__(self, "liquid_factor", liquid)
        object.__setattr__(self, "economic_factor", economic)
        object.__setattr__(self, "notes", notes)

    def apply(self, positive_value: Decimal | int | str) -> ValuationTiers:
        amount = _d(positive_value, "asset value")
        if amount < ZERO:
            raise AccountingInvariantError("asset value must be non-negative")
        return ValuationTiers(
            hard=amount * self.hard_factor,
            liquid=amount * self.liquid_factor,
            economic=amount * self.economic_factor,
        )

    def canonical_dict(self) -> dict[str, object]:
        return {
            "valuation_class": self.valuation_class,
            "hard_factor": canonical_decimal_text(self.hard_factor, "hard_factor"),
            "liquid_factor": canonical_decimal_text(self.liquid_factor, "liquid_factor"),
            "economic_factor": canonical_decimal_text(self.economic_factor, "economic_factor"),
            "price_source_class": self.price_source_class,
            "max_staleness_seconds": self.max_staleness_seconds,
            "requires_external_enforceability": self.requires_external_enforceability,
            "requires_intragroup_elimination": self.requires_intragroup_elimination,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ValuationPolicy:
    policy_id: str
    reporting_currency: str
    as_of: datetime
    rules: tuple[ValuationRule, ...]

    def __post_init__(self) -> None:
        policy_id = self.policy_id.strip()
        currency = self.reporting_currency.upper().strip()
        if not policy_id:
            raise AccountingInvariantError("valuation policy_id is required")
        if not currency:
            raise AccountingInvariantError("valuation reporting_currency is required")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise AccountingInvariantError("valuation policy as_of must be timezone-aware")
        if not self.rules:
            raise AccountingInvariantError("valuation policy requires at least one rule")

        ordered_rules = tuple(sorted(self.rules, key=lambda rule: rule.valuation_class))
        classes = [rule.valuation_class for rule in ordered_rules]
        if len(classes) != len(set(classes)):
            raise AccountingInvariantError("valuation policy contains duplicate valuation classes")

        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "reporting_currency", currency)
        object.__setattr__(self, "rules", ordered_rules)

    @property
    def rule_map(self) -> Mapping[str, ValuationRule]:
        return {rule.valuation_class: rule for rule in self.rules}

    def canonical_dict(self) -> dict[str, object]:
        return {
            "schema": "valuation-policy/v1",
            "policy_id": self.policy_id,
            "reporting_currency": self.reporting_currency,
            "as_of": self.as_of.isoformat(),
            "rules": [rule.canonical_dict() for rule in self.rules],
        }

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.canonical_dict())
