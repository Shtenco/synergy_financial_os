from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import verify_financial_snapshot_v2_payload
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError, liquidity_coverage_ratio, liquidity_surplus
from .liquidity_resources_v1 import HORIZONS, LiquidityResourcesV1
from .maturity_bridge import translate_maturity_outflows, verify_maturity_snapshot_digest
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .numeric import canonical_decimal_text, finite_decimal
from .statement_replay_v1 import StatementReplayV1


SCHEMA = "liquidity.replay/v1"
HEX = frozenset("0123456789abcdef")
ZERO = Decimal("0")


class LiquidityReplayV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiquidityReplayV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise LiquidityReplayV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiquidityReplayV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _parse_utc(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LiquidityReplayV1Error(f"{field_name} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiquidityReplayV1Error(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class LiquidityReplayHorizonV1:
    horizon_weeks: int
    liquid_resources: Decimal
    expected_net_outflows: Decimal
    lcr: Decimal | None
    liquidity_surplus: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.horizon_weeks, bool) or self.horizon_weeks not in HORIZONS:
            raise LiquidityReplayV1Error("liquidity replay horizon must be 1, 4 or 8 weeks")
        resources = finite_decimal(self.liquid_resources, "liquid_resources")
        outflows = finite_decimal(self.expected_net_outflows, "expected_net_outflows")
        surplus = finite_decimal(self.liquidity_surplus, "liquidity_surplus")
        if resources < ZERO or outflows < ZERO:
            raise LiquidityReplayV1Error("liquidity resources/outflows must be non-negative")
        expected_lcr = liquidity_coverage_ratio(resources, outflows)
        expected_surplus = liquidity_surplus(resources, outflows)
        if self.lcr is None:
            if expected_lcr is not None:
                raise LiquidityReplayV1Error("lcr cannot be null when outflows are non-zero")
        else:
            lcr = finite_decimal(self.lcr, "lcr")
            if lcr < ZERO or expected_lcr != lcr:
                raise LiquidityReplayV1Error("lcr mismatch")
            object.__setattr__(self, "lcr", lcr)
        if surplus != expected_surplus:
            raise LiquidityReplayV1Error("liquidity surplus mismatch")
        object.__setattr__(self, "liquid_resources", resources)
        object.__setattr__(self, "expected_net_outflows", outflows)
        object.__setattr__(self, "liquidity_surplus", surplus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "liquid_resources": canonical_decimal_text(self.liquid_resources),
            "expected_net_outflows": canonical_decimal_text(self.expected_net_outflows),
            "lcr": None if self.lcr is None else canonical_decimal_text(self.lcr),
            "liquidity_surplus": canonical_decimal_text(self.liquidity_surplus),
        }


@dataclass(frozen=True)
class LiquidityReplayV1:
    replay_id: str
    statement_replay_digest: str
    original_financial_snapshot_digest: str
    liquidity_resources_digest: str
    maturity_snapshot_digests: tuple[str, ...]
    maturity_translation_digests: tuple[str, ...]
    affected_period_id: str
    as_of: datetime
    reporting_currency: str
    restated_liquid_haircut_assets: Decimal
    horizons: tuple[LiquidityReplayHorizonV1, ...]
    generated_at: datetime
    authority: str = "FINANCIAL_OS_LIQUIDITY_REPLAY"
    accounting_authority: str = "REFERENCE_ONLY"
    distribution_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_LIQUIDITY_REPLAY":
            raise LiquidityReplayV1Error("liquidity replay authority must remain Financial OS")
        if self.accounting_authority != "REFERENCE_ONLY":
            raise LiquidityReplayV1Error("liquidity replay is reference-only")
        if self.distribution_authority != "NONE" or self.execution_authority != "NONE":
            raise LiquidityReplayV1Error("liquidity replay cannot authorize distribution or execute")
        object.__setattr__(self, "replay_id", _text(self.replay_id, "replay_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in ("statement_replay_digest", "original_financial_snapshot_digest", "liquidity_resources_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        maturity = tuple(sorted(_hex64(item, "maturity_snapshot_digest") for item in self.maturity_snapshot_digests))
        translations = tuple(sorted(_hex64(item, "maturity_translation_digest") for item in self.maturity_translation_digests))
        if not maturity or len(maturity) != len(set(maturity)):
            raise LiquidityReplayV1Error("liquidity replay requires unique maturity snapshots")
        if len(translations) != len(maturity) or len(translations) != len(set(translations)):
            raise LiquidityReplayV1Error("liquidity replay requires one unique translation per maturity snapshot")
        object.__setattr__(self, "maturity_snapshot_digests", maturity)
        object.__setattr__(self, "maturity_translation_digests", translations)
        assets = finite_decimal(self.restated_liquid_haircut_assets, "restated_liquid_haircut_assets")
        if assets < ZERO:
            raise LiquidityReplayV1Error("restated liquid haircut assets must be non-negative")
        object.__setattr__(self, "restated_liquid_haircut_assets", assets)
        horizons = tuple(sorted(self.horizons, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in horizons) != HORIZONS:
            raise LiquidityReplayV1Error("liquidity replay requires exactly 1w, 4w and 8w horizons")
        object.__setattr__(self, "horizons", horizons)
        as_of = _utc(self.as_of, "as_of")
        generated = _utc(self.generated_at, "generated_at")
        if generated < as_of:
            raise LiquidityReplayV1Error("liquidity replay cannot be generated before as_of")
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "generated_at", generated)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "replay_id": self.replay_id,
            "statement_replay_digest": self.statement_replay_digest,
            "original_financial_snapshot_digest": self.original_financial_snapshot_digest,
            "liquidity_resources_digest": self.liquidity_resources_digest,
            "maturity_snapshot_digests": list(self.maturity_snapshot_digests),
            "maturity_translation_digests": list(self.maturity_translation_digests),
            "affected_period_id": self.affected_period_id,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "reporting_currency": self.reporting_currency,
            "restated_liquid_haircut_assets": canonical_decimal_text(self.restated_liquid_haircut_assets),
            "horizons": [item.to_dict() for item in self.horizons],
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "accounting_authority": self.accounting_authority,
            "distribution_authority": self.distribution_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_liquidity_replay_v1(
    *,
    replay_id: str,
    statement_replay: StatementReplayV1,
    original_financial_snapshot: Mapping[str, Any],
    liquidity_resources: LiquidityResourcesV1,
    maturity_inputs: Sequence[tuple[Mapping[str, Any], MaturityTranslationArtifactV1]],
    generated_at: datetime,
) -> LiquidityReplayV1:
    snapshot = verify_financial_snapshot_v2_payload(original_financial_snapshot)
    if snapshot["digest"] != statement_replay.original_financial_snapshot_digest:
        raise LiquidityReplayV1Error("statement replay / FinancialSnapshot mismatch")
    if liquidity_resources.statement_replay_digest != statement_replay.digest:
        raise LiquidityReplayV1Error("liquidity resources / statement replay mismatch")
    if liquidity_resources.affected_period_id != statement_replay.affected_period_id:
        raise LiquidityReplayV1Error("liquidity resources affected period mismatch")
    snapshot_as_of = _parse_utc(snapshot["as_of"], "FinancialSnapshot.as_of")
    if liquidity_resources.as_of != snapshot_as_of:
        raise LiquidityReplayV1Error("liquidity resources as_of must equal FinancialSnapshot as_of in v1")
    if liquidity_resources.reporting_currency != snapshot.get("reporting_currency"):
        raise LiquidityReplayV1Error("liquidity resources reporting currency mismatch")
    if liquidity_resources.account_registry_digest != statement_replay.account_registry_digest:
        raise LiquidityReplayV1Error("liquidity resources account registry mismatch")
    if liquidity_resources.valuation_policy_digest != statement_replay.valuation_policy_digest:
        raise LiquidityReplayV1Error("liquidity resources valuation policy mismatch")
    for horizon in liquidity_resources.horizons:
        if horizon.liquid_resources > statement_replay.liquid_haircut_assets:
            raise LiquidityReplayV1Error("liquidity resource exceeds restated liquid haircut assets")

    if not maturity_inputs:
        raise LiquidityReplayV1Error("liquidity replay requires at least one maturity snapshot")
    maturity_digests: list[str] = []
    translation_digests: list[str] = []
    outflows = {horizon: ZERO for horizon in HORIZONS}
    for index, pair in enumerate(maturity_inputs):
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise LiquidityReplayV1Error(f"maturity_inputs[{index}] must be (snapshot, translation)")
        maturity_snapshot, translation_artifact = pair
        if not isinstance(translation_artifact, MaturityTranslationArtifactV1):
            raise LiquidityReplayV1Error("maturity input translation must be MaturityTranslationArtifactV1")
        maturity_digest = verify_maturity_snapshot_digest(maturity_snapshot)
        if translation_artifact.maturity_snapshot_digest != maturity_digest:
            raise LiquidityReplayV1Error("maturity translation / snapshot digest mismatch")
        if translation_artifact.reporting_currency != liquidity_resources.reporting_currency:
            raise LiquidityReplayV1Error("maturity translation reporting currency mismatch")
        maturity_as_of = _parse_utc(maturity_snapshot.get("as_of"), "maturity snapshot as_of")
        if translation_artifact.as_of != maturity_as_of:
            raise LiquidityReplayV1Error("maturity translation as_of mismatch")
        if maturity_as_of != snapshot_as_of:
            raise LiquidityReplayV1Error("v1 requires maturity snapshot as_of == FinancialSnapshot as_of")
        translated = translate_maturity_outflows(maturity_snapshot, translation_artifact.to_translation())
        for horizon in HORIZONS:
            outflows[horizon] += translated[horizon]
        maturity_digests.append(maturity_digest)
        translation_digests.append(translation_artifact.digest)

    referenced = tuple(sorted(snapshot.get("maturity_snapshot_refs") or ()))
    supplied = tuple(sorted(maturity_digests))
    if supplied != referenced:
        raise LiquidityReplayV1Error("supplied maturity snapshots must exactly match FinancialSnapshot refs")

    resources = liquidity_resources.resources_by_horizon()
    horizon_results = tuple(
        LiquidityReplayHorizonV1(
            horizon_weeks=horizon,
            liquid_resources=resources[horizon],
            expected_net_outflows=outflows[horizon],
            lcr=liquidity_coverage_ratio(resources[horizon], outflows[horizon]),
            liquidity_surplus=liquidity_surplus(resources[horizon], outflows[horizon]),
        )
        for horizon in HORIZONS
    )
    latest_input_time = max(
        [liquidity_resources.generated_at]
        + [translation.generated_at for _, translation in maturity_inputs]
    )
    generated = _utc(generated_at, "generated_at")
    if generated < latest_input_time:
        raise LiquidityReplayV1Error("liquidity replay cannot predate its input artifacts")
    return LiquidityReplayV1(
        replay_id=replay_id,
        statement_replay_digest=statement_replay.digest,
        original_financial_snapshot_digest=snapshot["digest"],
        liquidity_resources_digest=liquidity_resources.digest,
        maturity_snapshot_digests=tuple(maturity_digests),
        maturity_translation_digests=tuple(translation_digests),
        affected_period_id=statement_replay.affected_period_id,
        as_of=snapshot_as_of,
        reporting_currency=liquidity_resources.reporting_currency,
        restated_liquid_haircut_assets=statement_replay.liquid_haircut_assets,
        horizons=horizon_results,
        generated_at=generated,
    )
