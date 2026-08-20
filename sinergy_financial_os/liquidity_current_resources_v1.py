from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2, verify_accounting_close_v2, verify_financial_snapshot_v2_payload
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .liquidity_policy_v1 import LiquidityPolicyV1
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "liquidity.current-resources/v1"
HORIZONS = (1, 4, 8)
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class LiquidityCurrentResourcesV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiquidityCurrentResourcesV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise LiquidityCurrentResourcesV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiquidityCurrentResourcesV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _snapshot_time(snapshot: Mapping[str, Any]) -> datetime:
    text = _text(snapshot.get("as_of"), "snapshot.as_of")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiquidityCurrentResourcesV1Error("snapshot.as_of must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class LiquidityCurrentResourceHorizonV1:
    horizon_weeks: int
    liquid_resources: Decimal
    measurement_evidence_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.horizon_weeks, bool) or self.horizon_weeks not in HORIZONS:
            raise LiquidityCurrentResourcesV1Error("current liquidity horizon must be 1, 4 or 8 weeks")
        resources = finite_decimal(self.liquid_resources, "liquid_resources")
        if resources < ZERO:
            raise LiquidityCurrentResourcesV1Error("liquid_resources must be non-negative")
        object.__setattr__(self, "liquid_resources", resources)
        object.__setattr__(self, "measurement_evidence_digest", _hex64(self.measurement_evidence_digest, "measurement_evidence_digest"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "liquid_resources": canonical_decimal_text(self.liquid_resources),
            "measurement_evidence_digest": self.measurement_evidence_digest,
        }


@dataclass(frozen=True)
class LiquidityCurrentResourcesV1:
    resource_id: str
    financial_snapshot_digest: str
    accounting_close_digest: str
    snapshot_sequence: int
    snapshot_ledger_digest: str
    reporting_currency: str
    as_of: datetime
    liquidity_policy_digest: str
    liquid_haircut_asset_ceiling: Decimal
    horizons: tuple[LiquidityCurrentResourceHorizonV1, ...]
    generated_at: datetime
    authority: str = "FINANCIAL_OS_CURRENT_LIQUIDITY_RESOURCES"
    authorization_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_CURRENT_LIQUIDITY_RESOURCES":
            raise LiquidityCurrentResourcesV1Error("current liquidity resources authority mismatch")
        if self.authorization_authority != "NONE" or self.execution_authority != "NONE":
            raise LiquidityCurrentResourcesV1Error("current liquidity resources cannot authorize or execute")
        object.__setattr__(self, "resource_id", _text(self.resource_id, "resource_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in ("financial_snapshot_digest", "accounting_close_digest", "snapshot_ledger_digest", "liquidity_policy_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if isinstance(self.snapshot_sequence, bool) or not isinstance(self.snapshot_sequence, int) or self.snapshot_sequence < 1:
            raise LiquidityCurrentResourcesV1Error("snapshot_sequence must be positive integer")
        ceiling = finite_decimal(self.liquid_haircut_asset_ceiling, "liquid_haircut_asset_ceiling")
        if ceiling < ZERO:
            raise LiquidityCurrentResourcesV1Error("liquid_haircut_asset_ceiling must be non-negative")
        object.__setattr__(self, "liquid_haircut_asset_ceiling", ceiling)
        values = tuple(sorted(self.horizons, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in values) != HORIZONS:
            raise LiquidityCurrentResourcesV1Error("current liquidity resources require exactly 1w, 4w and 8w horizons")
        previous = ZERO
        for index, item in enumerate(values):
            if index and item.liquid_resources < previous:
                raise LiquidityCurrentResourcesV1Error("liquid resources must be non-decreasing across longer horizons")
            if item.liquid_resources > ceiling:
                raise LiquidityCurrentResourcesV1Error("horizon liquid resources exceed closed-snapshot liquid-asset ceiling")
            previous = item.liquid_resources
        object.__setattr__(self, "horizons", values)
        as_of = _utc(self.as_of, "as_of")
        generated = _utc(self.generated_at, "generated_at")
        if generated < as_of:
            raise LiquidityCurrentResourcesV1Error("current liquidity resources cannot be generated before as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "generated_at", generated)

    def resources_by_horizon(self) -> dict[int, Decimal]:
        return {item.horizon_weeks: item.liquid_resources for item in self.horizons}

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "resource_id": self.resource_id,
            "financial_snapshot_digest": self.financial_snapshot_digest,
            "accounting_close_digest": self.accounting_close_digest,
            "snapshot_sequence": self.snapshot_sequence,
            "snapshot_ledger_digest": self.snapshot_ledger_digest,
            "reporting_currency": self.reporting_currency,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "liquidity_policy_digest": self.liquidity_policy_digest,
            "liquid_haircut_asset_ceiling": canonical_decimal_text(self.liquid_haircut_asset_ceiling),
            "horizons": [item.to_dict() for item in self.horizons],
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


def build_liquidity_current_resources_v1(
    *,
    resource_id: str,
    financial_snapshot: Mapping[str, Any],
    accounting_close: AccountingCloseV2,
    sealed_ledger_events: Sequence[Mapping[str, Any]],
    liquidity_policy: LiquidityPolicyV1,
    horizons: tuple[LiquidityCurrentResourceHorizonV1, ...],
    generated_at: datetime,
) -> LiquidityCurrentResourcesV1:
    snapshot = verify_financial_snapshot_v2_payload(financial_snapshot)
    verify_accounting_close_v2(sealed_ledger_events, snapshot, accounting_close)
    if accounting_close.financial_snapshot_digest != snapshot["digest"]:
        raise LiquidityCurrentResourcesV1Error("AccountingClose / FinancialSnapshot mismatch")
    if accounting_close.snapshot_sequence != snapshot["sequence"]:
        raise LiquidityCurrentResourcesV1Error("AccountingClose / snapshot sequence mismatch")
    if accounting_close.snapshot_ledger_digest != snapshot["ledger_digest"]:
        raise LiquidityCurrentResourcesV1Error("AccountingClose / snapshot ledger digest mismatch")
    currency = _text(snapshot.get("reporting_currency"), "snapshot.reporting_currency").upper()
    if liquidity_policy.reporting_currency != currency:
        raise LiquidityCurrentResourcesV1Error("LiquidityPolicy / current snapshot reporting currency mismatch")
    as_of = _snapshot_time(snapshot)
    if liquidity_policy.as_of > as_of:
        raise LiquidityCurrentResourcesV1Error("LiquidityPolicy cannot be from the future")
    liquid_nav = finite_decimal(snapshot.get("liquid_nav"), "snapshot.liquid_nav")
    external_liabilities = finite_decimal(snapshot.get("external_liabilities"), "snapshot.external_liabilities")
    ceiling = liquid_nav + external_liabilities
    if ceiling < ZERO:
        raise LiquidityCurrentResourcesV1Error("closed snapshot implies negative liquid haircut assets")
    return LiquidityCurrentResourcesV1(
        resource_id=resource_id,
        financial_snapshot_digest=snapshot["digest"],
        accounting_close_digest=accounting_close.digest,
        snapshot_sequence=snapshot["sequence"],
        snapshot_ledger_digest=snapshot["ledger_digest"],
        reporting_currency=currency,
        as_of=as_of,
        liquidity_policy_digest=liquidity_policy.digest,
        liquid_haircut_asset_ceiling=ceiling,
        horizons=horizons,
        generated_at=generated_at,
    )
