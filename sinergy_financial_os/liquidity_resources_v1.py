from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .account_registry_v1 import AccountRegistryV1
from .accounting_close_v2 import verify_financial_snapshot_v2_payload
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .numeric import canonical_decimal_text, finite_decimal
from .statement_replay_v1 import StatementReplayV1
from .valuation_policy_artifact_v1 import ValuationPolicyArtifactV1


SCHEMA = "liquidity.resources/v1"
HORIZONS = (1, 4, 8)
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class LiquidityResourcesV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiquidityResourcesV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise LiquidityResourcesV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiquidityResourcesV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _d(value: Decimal | int | str, field_name: str) -> Decimal:
    result = finite_decimal(value, field_name)
    if result < ZERO:
        raise LiquidityResourcesV1Error(f"{field_name} must be non-negative")
    return result


@dataclass(frozen=True)
class LiquidityResourceHorizonV1:
    horizon_weeks: int
    liquid_resources: Decimal
    measurement_evidence_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.horizon_weeks, bool) or self.horizon_weeks not in HORIZONS:
            raise LiquidityResourcesV1Error("liquidity resource horizon must be 1, 4 or 8 weeks")
        object.__setattr__(
            self,
            "liquid_resources",
            _d(self.liquid_resources, f"{self.horizon_weeks}w liquid_resources"),
        )
        object.__setattr__(
            self,
            "measurement_evidence_digest",
            _hex64(self.measurement_evidence_digest, "measurement_evidence_digest"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "liquid_resources": canonical_decimal_text(self.liquid_resources),
            "measurement_evidence_digest": self.measurement_evidence_digest,
        }


@dataclass(frozen=True)
class LiquidityResourcesV1:
    measurement_id: str
    statement_replay_digest: str
    affected_period_id: str
    as_of: datetime
    reporting_currency: str
    account_registry_digest: str
    valuation_policy_digest: str
    liquidity_policy_digest: str
    horizons: tuple[LiquidityResourceHorizonV1, ...]
    generated_at: datetime
    authority: str = "FINANCIAL_OS_LIQUIDITY_MEASUREMENT"
    accounting_authority: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_LIQUIDITY_MEASUREMENT":
            raise LiquidityResourcesV1Error("liquidity measurement authority must remain Financial OS")
        if self.accounting_authority != "REFERENCE_ONLY" or self.execution_authority != "NONE":
            raise LiquidityResourcesV1Error("liquidity resources cannot mutate accounting or execute")
        object.__setattr__(self, "measurement_id", _text(self.measurement_id, "measurement_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in (
            "statement_replay_digest",
            "account_registry_digest",
            "valuation_policy_digest",
            "liquidity_policy_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        values = tuple(sorted(self.horizons, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in values) != HORIZONS:
            raise LiquidityResourcesV1Error("liquidity resources require exactly 1w, 4w and 8w horizons")
        if not all(isinstance(item, LiquidityResourceHorizonV1) for item in values):
            raise LiquidityResourcesV1Error("invalid liquidity resource horizon")
        resources = tuple(item.liquid_resources for item in values)
        if not resources[0] <= resources[1] <= resources[2]:
            raise LiquidityResourcesV1Error("liquid resources must be non-decreasing across longer horizons")
        object.__setattr__(self, "horizons", values)
        as_of = _utc(self.as_of, "as_of")
        generated = _utc(self.generated_at, "generated_at")
        if generated < as_of:
            raise LiquidityResourcesV1Error("liquidity resources cannot be generated before as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "generated_at", generated)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "measurement_id": self.measurement_id,
            "statement_replay_digest": self.statement_replay_digest,
            "affected_period_id": self.affected_period_id,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "reporting_currency": self.reporting_currency,
            "account_registry_digest": self.account_registry_digest,
            "valuation_policy_digest": self.valuation_policy_digest,
            "liquidity_policy_digest": self.liquidity_policy_digest,
            "horizons": [item.to_dict() for item in self.horizons],
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "accounting_authority": self.accounting_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))

    def resources_by_horizon(self) -> dict[int, Decimal]:
        return {item.horizon_weeks: item.liquid_resources for item in self.horizons}


def build_liquidity_resources_v1(
    *,
    measurement_id: str,
    statement_replay: StatementReplayV1,
    original_financial_snapshot: Mapping[str, Any],
    account_registry: AccountRegistryV1,
    valuation_policy_artifact: ValuationPolicyArtifactV1,
    liquidity_policy_digest: str,
    horizons: Iterable[LiquidityResourceHorizonV1],
    generated_at: datetime,
) -> LiquidityResourcesV1:
    snapshot = verify_financial_snapshot_v2_payload(original_financial_snapshot)
    if snapshot["digest"] != statement_replay.original_financial_snapshot_digest:
        raise LiquidityResourcesV1Error("statement replay / FinancialSnapshot digest mismatch")
    if statement_replay.account_registry_digest != account_registry.account_registry_digest:
        raise LiquidityResourcesV1Error("statement replay / AccountRegistry digest mismatch")
    if statement_replay.valuation_policy_digest != valuation_policy_artifact.policy.digest:
        raise LiquidityResourcesV1Error("statement replay / valuation policy digest mismatch")
    if snapshot.get("reporting_currency") != account_registry.reporting_currency:
        raise LiquidityResourcesV1Error("FinancialSnapshot / AccountRegistry currency mismatch")
    if snapshot.get("account_registry_digest") != account_registry.account_registry_digest:
        raise LiquidityResourcesV1Error("FinancialSnapshot / AccountRegistry digest mismatch")
    if snapshot.get("valuation_policy_digest") != valuation_policy_artifact.policy.digest:
        raise LiquidityResourcesV1Error("FinancialSnapshot / valuation policy digest mismatch")
    if statement_replay.affected_period_id == "":
        raise LiquidityResourcesV1Error("statement replay affected period is required")
    try:
        as_of = datetime.fromisoformat(str(snapshot["as_of"]).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise LiquidityResourcesV1Error("FinancialSnapshot as_of is invalid") from exc
    result = LiquidityResourcesV1(
        measurement_id=measurement_id,
        statement_replay_digest=statement_replay.digest,
        affected_period_id=statement_replay.affected_period_id,
        as_of=as_of,
        reporting_currency=account_registry.reporting_currency,
        account_registry_digest=account_registry.account_registry_digest,
        valuation_policy_digest=valuation_policy_artifact.policy.digest,
        liquidity_policy_digest=liquidity_policy_digest,
        horizons=tuple(horizons),
        generated_at=generated_at,
    )
    for item in result.horizons:
        if item.liquid_resources > statement_replay.liquid_haircut_assets:
            raise LiquidityResourcesV1Error(
                f"{item.horizon_weeks}w resources exceed restated liquid haircut assets"
            )
    return result
