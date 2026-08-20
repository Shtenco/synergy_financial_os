from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "liquidity.policy/v1"
HORIZONS = (1, 4, 8)
ZERO = Decimal("0")


class LiquidityPolicyV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiquidityPolicyV1Error(f"{field_name} is required")
    return value.strip()


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiquidityPolicyV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class LiquidityPolicyHorizonV1:
    horizon_weeks: int
    minimum_lcr: Decimal
    minimum_liquidity_surplus: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.horizon_weeks, bool) or self.horizon_weeks not in HORIZONS:
            raise LiquidityPolicyV1Error("liquidity policy horizon must be 1, 4 or 8 weeks")
        lcr = finite_decimal(self.minimum_lcr, "minimum_lcr")
        surplus = finite_decimal(self.minimum_liquidity_surplus, "minimum_liquidity_surplus")
        if lcr < ZERO or surplus < ZERO:
            raise LiquidityPolicyV1Error("liquidity policy floors must be non-negative")
        object.__setattr__(self, "minimum_lcr", lcr)
        object.__setattr__(self, "minimum_liquidity_surplus", surplus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "minimum_lcr": canonical_decimal_text(self.minimum_lcr),
            "minimum_liquidity_surplus": canonical_decimal_text(self.minimum_liquidity_surplus),
        }


@dataclass(frozen=True)
class LiquidityPolicyV1:
    policy_id: str
    reporting_currency: str
    as_of: datetime
    horizons: tuple[LiquidityPolicyHorizonV1, ...]
    generated_at: datetime
    distribution_outflow_treatment: str = "IMMEDIATE_RESOURCE_REDUCTION_ALL_HORIZONS"
    authority: str = "FINANCIAL_OS_LIQUIDITY_POLICY"
    authorization_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.distribution_outflow_treatment != "IMMEDIATE_RESOURCE_REDUCTION_ALL_HORIZONS":
            raise LiquidityPolicyV1Error("unsupported distribution outflow treatment")
        if self.authority != "FINANCIAL_OS_LIQUIDITY_POLICY":
            raise LiquidityPolicyV1Error("liquidity policy authority must remain Financial OS")
        if self.authorization_authority != "NONE" or self.execution_authority != "NONE":
            raise LiquidityPolicyV1Error("liquidity policy cannot authorize or execute distributions")
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        values = tuple(sorted(self.horizons, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in values) != HORIZONS:
            raise LiquidityPolicyV1Error("liquidity policy requires exactly 1w, 4w and 8w horizons")
        object.__setattr__(self, "horizons", values)
        as_of = _utc(self.as_of, "as_of")
        generated = _utc(self.generated_at, "generated_at")
        if generated < as_of:
            raise LiquidityPolicyV1Error("liquidity policy cannot be generated before as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "generated_at", generated)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "policy_id": self.policy_id,
            "reporting_currency": self.reporting_currency,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "horizons": [item.to_dict() for item in self.horizons],
            "distribution_outflow_treatment": self.distribution_outflow_treatment,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))

    def by_horizon(self) -> dict[int, LiquidityPolicyHorizonV1]:
        return {item.horizon_weeks: item for item in self.horizons}
