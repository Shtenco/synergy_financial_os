from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .canonical_json import MAX_SAFE_JSON_INTEGER
from .liquidity_replay_v1 import LiquidityReplayHorizonV1, LiquidityReplayV1, LiquidityReplayV1Error
from .liquidity_resources_v1 import LiquidityResourceHorizonV1, LiquidityResourcesV1, LiquidityResourcesV1Error
from .maturity_translation_v1 import MaturityTranslationArtifactV1, MaturityTranslationV1Error
from .numeric import canonical_decimal_text


def _canonical_decimal(value: Any, field_name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be canonical decimal string")
    result = Decimal(value)
    if not result.is_finite() or canonical_decimal_text(result) != value:
        raise ValueError(f"{field_name} is not canonical decimal text")
    if nonnegative and result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field_name} is not canonical UTC text")
    return parsed


def verify_liquidity_resources_payload_v1(payload: Mapping[str, Any]) -> LiquidityResourcesV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "liquidity.resources/v1":
            raise LiquidityResourcesV1Error("unsupported liquidity resources schema")
        raw_horizons = payload.get("horizons")
        if not isinstance(raw_horizons, list):
            raise LiquidityResourcesV1Error("horizons must be array")
        horizons = tuple(
            LiquidityResourceHorizonV1(
                item.get("horizon_weeks"),
                _canonical_decimal(item.get("liquid_resources"), "liquid_resources", nonnegative=True),
                item.get("measurement_evidence_digest"),
            )
            for item in raw_horizons
        )
        result = LiquidityResourcesV1(
            measurement_id=payload.get("measurement_id"),
            statement_replay_digest=payload.get("statement_replay_digest"),
            affected_period_id=payload.get("affected_period_id"),
            as_of=_time(payload.get("as_of"), "as_of"),
            reporting_currency=payload.get("reporting_currency"),
            account_registry_digest=payload.get("account_registry_digest"),
            valuation_policy_digest=payload.get("valuation_policy_digest"),
            liquidity_policy_digest=payload.get("liquidity_policy_digest"),
            horizons=horizons,
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            authority=payload.get("authority"),
            accounting_authority=payload.get("accounting_authority"),
            execution_authority=payload.get("execution_authority"),
        )
        if result.to_dict() != dict(payload):
            raise LiquidityResourcesV1Error("liquidity resources payload is not canonical or digest mismatch")
        return result
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LiquidityResourcesV1Error):
            raise
        raise LiquidityResourcesV1Error(str(exc)) from exc


def verify_maturity_translation_payload_v1(payload: Mapping[str, Any]) -> MaturityTranslationArtifactV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "maturity.translation/v1":
            raise MaturityTranslationV1Error("unsupported maturity translation schema")
        result = MaturityTranslationArtifactV1(
            maturity_snapshot_digest=payload.get("maturity_snapshot_digest"),
            source_currency=payload.get("source_currency"),
            reporting_currency=payload.get("reporting_currency"),
            reporting_units_per_source_unit=_canonical_decimal(
                payload.get("reporting_units_per_source_unit"), "reporting_units_per_source_unit", nonnegative=True
            ),
            as_of=_time(payload.get("as_of"), "as_of"),
            translation_evidence_digest=payload.get("translation_evidence_digest"),
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            authority=payload.get("authority"),
            accounting_authority=payload.get("accounting_authority"),
            execution_authority=payload.get("execution_authority"),
        )
        if result.to_dict() != dict(payload):
            raise MaturityTranslationV1Error("maturity translation payload is not canonical or digest mismatch")
        return result
    except (ValueError, TypeError) as exc:
        if isinstance(exc, MaturityTranslationV1Error):
            raise
        raise MaturityTranslationV1Error(str(exc)) from exc


def verify_liquidity_replay_payload_v1(payload: Mapping[str, Any]) -> LiquidityReplayV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "liquidity.replay/v1":
            raise LiquidityReplayV1Error("unsupported liquidity replay schema")
        raw_horizons = payload.get("horizons")
        if not isinstance(raw_horizons, list):
            raise LiquidityReplayV1Error("horizons must be array")
        horizons = []
        for item in raw_horizons:
            week = item.get("horizon_weeks")
            if isinstance(week, bool) or not isinstance(week, int) or week > MAX_SAFE_JSON_INTEGER:
                raise LiquidityReplayV1Error("invalid horizon_weeks")
            lcr_raw = item.get("lcr")
            horizons.append(
                LiquidityReplayHorizonV1(
                    week,
                    _canonical_decimal(item.get("liquid_resources"), "liquid_resources", nonnegative=True),
                    _canonical_decimal(item.get("expected_net_outflows"), "expected_net_outflows", nonnegative=True),
                    None if lcr_raw is None else _canonical_decimal(lcr_raw, "lcr", nonnegative=True),
                    _canonical_decimal(item.get("liquidity_surplus"), "liquidity_surplus"),
                )
            )
        result = LiquidityReplayV1(
            replay_id=payload.get("replay_id"),
            statement_replay_digest=payload.get("statement_replay_digest"),
            original_financial_snapshot_digest=payload.get("original_financial_snapshot_digest"),
            liquidity_resources_digest=payload.get("liquidity_resources_digest"),
            maturity_snapshot_digests=tuple(payload.get("maturity_snapshot_digests") or ()),
            maturity_translation_digests=tuple(payload.get("maturity_translation_digests") or ()),
            affected_period_id=payload.get("affected_period_id"),
            as_of=_time(payload.get("as_of"), "as_of"),
            reporting_currency=payload.get("reporting_currency"),
            restated_liquid_haircut_assets=_canonical_decimal(
                payload.get("restated_liquid_haircut_assets"), "restated_liquid_haircut_assets", nonnegative=True
            ),
            horizons=tuple(horizons),
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            authority=payload.get("authority"),
            accounting_authority=payload.get("accounting_authority"),
            distribution_authority=payload.get("distribution_authority"),
            execution_authority=payload.get("execution_authority"),
        )
        if result.to_dict() != dict(payload):
            raise LiquidityReplayV1Error("liquidity replay payload is not canonical or digest mismatch")
        return result
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LiquidityReplayV1Error):
            raise
        raise LiquidityReplayV1Error(str(exc)) from exc
