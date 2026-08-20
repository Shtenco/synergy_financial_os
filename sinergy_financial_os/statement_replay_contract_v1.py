from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .numeric import canonical_decimal_text
from .statement_replay_v1 import SCHEMA, StatementReplayV1, StatementReplayV1Error


_DECIMAL_FIELDS = (
    "hard_external_assets",
    "liquid_haircut_assets",
    "economic_haircut_assets",
    "external_liabilities",
    "hard_nav",
    "liquid_nav",
    "economic_nav",
    "realized_external_revenue",
    "realized_external_pnl",
)


def _require_mapping(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise StatementReplayV1Error("statement replay payload must be object")
    return payload


def _canonical_decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise StatementReplayV1Error(f"{field_name} must be canonical decimal string")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise StatementReplayV1Error(f"{field_name} is invalid decimal") from exc
    if not result.is_finite() or canonical_decimal_text(result) != value:
        raise StatementReplayV1Error(f"{field_name} is not canonical decimal text")
    return result


def _canonical_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise StatementReplayV1Error("generated_at must use canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StatementReplayV1Error("generated_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StatementReplayV1Error("generated_at must be timezone-aware")
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise StatementReplayV1Error("generated_at is not canonical UTC text")
    return parsed


def verify_statement_replay_payload_v1(payload: Mapping[str, Any]) -> StatementReplayV1:
    data = dict(_require_mapping(payload))
    if data.get("schema") != SCHEMA:
        raise StatementReplayV1Error("unsupported statement replay schema")
    decimals = {name: _canonical_decimal(data.get(name), name) for name in _DECIMAL_FIELDS}
    generated_at = _canonical_time(data.get("generated_at"))
    replay = StatementReplayV1(
        replay_id=data.get("replay_id"),
        affected_period_id=data.get("affected_period_id"),
        original_period_close_digest=data.get("original_period_close_digest"),
        original_accounting_close_digest=data.get("original_accounting_close_digest"),
        original_financial_snapshot_digest=data.get("original_financial_snapshot_digest"),
        opening_period_close_digest=data.get("opening_period_close_digest"),
        opening_accounting_close_digest=data.get("opening_accounting_close_digest"),
        account_registry_artifact_digest=data.get("account_registry_artifact_digest"),
        account_registry_digest=data.get("account_registry_digest"),
        valuation_policy_artifact_digest=data.get("valuation_policy_artifact_digest"),
        valuation_policy_digest=data.get("valuation_policy_digest"),
        restated_period_view_digest=data.get("restated_period_view_digest"),
        overlay_digests=tuple(data.get("overlay_digests") or ()),
        excluded_reporting_entry_digests=tuple(data.get("excluded_reporting_entry_digests") or ()),
        opening_sequence=data.get("opening_sequence"),
        closing_sequence=data.get("closing_sequence"),
        original_event_count=data.get("original_event_count"),
        retained_event_count=data.get("retained_event_count"),
        excluded_event_count=data.get("excluded_event_count"),
        replayed_ledger_digest=data.get("replayed_ledger_digest"),
        replayed_last_entry_digest=data.get("replayed_last_entry_digest"),
        hard_external_assets=decimals["hard_external_assets"],
        liquid_haircut_assets=decimals["liquid_haircut_assets"],
        economic_haircut_assets=decimals["economic_haircut_assets"],
        external_liabilities=decimals["external_liabilities"],
        hard_nav=decimals["hard_nav"],
        liquid_nav=decimals["liquid_nav"],
        economic_nav=decimals["economic_nav"],
        realized_external_revenue=decimals["realized_external_revenue"],
        realized_external_pnl=decimals["realized_external_pnl"],
        generated_at=generated_at,
        liquidity_metrics=data.get("liquidity_metrics"),
        distribution_metrics=data.get("distribution_metrics"),
        authority=data.get("authority"),
        ledger_mutation_authority=data.get("ledger_mutation_authority"),
        execution_authority=data.get("execution_authority"),
    )
    if replay.to_dict() != data:
        raise StatementReplayV1Error("statement replay payload is not canonical or digest mismatch")
    return replay
