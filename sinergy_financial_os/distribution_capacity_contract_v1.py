from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .core import distributable_profit, distribution_capacity
from .distribution_capacity_replay_v1 import (
    DistributionCapacityReplayV1,
    DistributionCapacityReplayV1Error,
    DistributionLiquidityHeadroomV1,
)
from .liquidity_policy_v1 import LiquidityPolicyHorizonV1, LiquidityPolicyV1, LiquidityPolicyV1Error
from .numeric import canonical_decimal_text


ZERO = Decimal("0")


def _decimal(value: Any, field_name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be canonical decimal text")
    result = Decimal(value)
    if not result.is_finite() or canonical_decimal_text(result) != value:
        raise ValueError(f"{field_name} is not canonical decimal text")
    if nonnegative and result < ZERO:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _time(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must use canonical UTC Z time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field_name} is not canonical UTC text")
    return parsed


def verify_liquidity_policy_payload_v1(payload: Mapping[str, Any]) -> LiquidityPolicyV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "liquidity.policy/v1":
            raise LiquidityPolicyV1Error("unsupported liquidity policy schema")
        raw = payload.get("horizons")
        if not isinstance(raw, list):
            raise LiquidityPolicyV1Error("liquidity policy horizons must be array")
        horizons = tuple(
            LiquidityPolicyHorizonV1(
                item.get("horizon_weeks"),
                _decimal(item.get("minimum_lcr"), "minimum_lcr", nonnegative=True),
                _decimal(item.get("minimum_liquidity_surplus"), "minimum_liquidity_surplus", nonnegative=True),
            )
            for item in raw
        )
        policy = LiquidityPolicyV1(
            policy_id=payload.get("policy_id"),
            reporting_currency=payload.get("reporting_currency"),
            as_of=_time(payload.get("as_of"), "as_of"),
            horizons=horizons,
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            distribution_outflow_treatment=payload.get("distribution_outflow_treatment"),
            authority=payload.get("authority"),
            authorization_authority=payload.get("authorization_authority"),
            execution_authority=payload.get("execution_authority"),
        )
        if policy.to_dict() != dict(payload):
            raise LiquidityPolicyV1Error("liquidity policy payload is not canonical or digest mismatch")
        return policy
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LiquidityPolicyV1Error):
            raise
        raise LiquidityPolicyV1Error(str(exc)) from exc


def verify_distribution_capacity_replay_payload_v1(
    payload: Mapping[str, Any],
) -> DistributionCapacityReplayV1:
    try:
        if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.capacity-replay/v1":
            raise DistributionCapacityReplayV1Error("unsupported distribution capacity replay schema")
        raw_headrooms = payload.get("horizon_headrooms")
        if not isinstance(raw_headrooms, list):
            raise DistributionCapacityReplayV1Error("horizon_headrooms must be array")
        headrooms = tuple(
            DistributionLiquidityHeadroomV1(
                horizon_weeks=item.get("horizon_weeks"),
                pre_distribution_resources=_decimal(item.get("pre_distribution_resources"), "pre_distribution_resources", nonnegative=True),
                expected_net_outflows=_decimal(item.get("expected_net_outflows"), "expected_net_outflows", nonnegative=True),
                minimum_lcr=_decimal(item.get("minimum_lcr"), "minimum_lcr", nonnegative=True),
                minimum_liquidity_surplus=_decimal(item.get("minimum_liquidity_surplus"), "minimum_liquidity_surplus", nonnegative=True),
                lcr_headroom=_decimal(item.get("lcr_headroom"), "lcr_headroom"),
                surplus_headroom=_decimal(item.get("surplus_headroom"), "surplus_headroom"),
                horizon_distribution_capacity=_decimal(item.get("horizon_distribution_capacity"), "horizon_distribution_capacity", nonnegative=True),
            )
            for item in raw_headrooms
        )
        replay = DistributionCapacityReplayV1(
            replay_id=payload.get("replay_id"),
            affected_period_id=payload.get("affected_period_id"),
            statement_replay_digest=payload.get("statement_replay_digest"),
            liquidity_replay_digest=payload.get("liquidity_replay_digest"),
            liquidity_resources_digest=payload.get("liquidity_resources_digest"),
            liquidity_policy_digest=payload.get("liquidity_policy_digest"),
            original_financial_snapshot_digest=payload.get("original_financial_snapshot_digest"),
            required_retention=_decimal(payload.get("required_retention"), "required_retention", nonnegative=True),
            loss_carryforward=_decimal(payload.get("loss_carryforward"), "loss_carryforward", nonnegative=True),
            required_hard_nav_buffer=_decimal(payload.get("required_hard_nav_buffer"), "required_hard_nav_buffer", nonnegative=True),
            restated_realized_external_pnl=_decimal(payload.get("restated_realized_external_pnl"), "restated_realized_external_pnl"),
            restated_hard_nav=_decimal(payload.get("restated_hard_nav"), "restated_hard_nav"),
            realized_profit_budget=_decimal(payload.get("realized_profit_budget"), "realized_profit_budget", nonnegative=True),
            solvency_headroom=_decimal(payload.get("solvency_headroom"), "solvency_headroom", nonnegative=True),
            accounting_distribution_capacity=_decimal(payload.get("accounting_distribution_capacity"), "accounting_distribution_capacity", nonnegative=True),
            liquidity_distribution_capacity=_decimal(payload.get("liquidity_distribution_capacity"), "liquidity_distribution_capacity", nonnegative=True),
            final_distribution_capacity=_decimal(payload.get("final_distribution_capacity"), "final_distribution_capacity", nonnegative=True),
            horizon_headrooms=headrooms,
            blockers=tuple(payload.get("blockers") or ()),
            status=payload.get("status"),
            generated_at=_time(payload.get("generated_at"), "generated_at"),
            authority=payload.get("authority"),
            authorization_authority=payload.get("authorization_authority"),
            payment_authority=payload.get("payment_authority"),
            execution_authority=payload.get("execution_authority"),
        )

        expected_profit = distributable_profit(
            replay.restated_realized_external_pnl,
            replay.required_retention,
            replay.loss_carryforward,
        )
        expected_solvency = max(ZERO, replay.restated_hard_nav - replay.required_hard_nav_buffer)
        expected_accounting = distribution_capacity(
            expected_profit,
            replay.restated_hard_nav,
            replay.required_hard_nav_buffer,
        )
        expected_liquidity = min(item.horizon_distribution_capacity for item in replay.horizon_headrooms)
        if replay.realized_profit_budget != expected_profit:
            raise DistributionCapacityReplayV1Error("realized profit budget formula mismatch")
        if replay.solvency_headroom != expected_solvency:
            raise DistributionCapacityReplayV1Error("solvency headroom formula mismatch")
        if replay.accounting_distribution_capacity != expected_accounting:
            raise DistributionCapacityReplayV1Error("accounting capacity formula mismatch")
        if replay.liquidity_distribution_capacity != expected_liquidity:
            raise DistributionCapacityReplayV1Error("liquidity capacity formula mismatch")
        expected_final = ZERO if replay.blockers else min(expected_accounting, expected_liquidity)
        if replay.final_distribution_capacity != expected_final:
            raise DistributionCapacityReplayV1Error("final distribution capacity formula mismatch")
        expected_status = "CAPACITY_AVAILABLE" if expected_final > ZERO and not replay.blockers else "NO_ACTION"
        if replay.status != expected_status:
            raise DistributionCapacityReplayV1Error("capacity status formula mismatch")
        if replay.to_dict() != dict(payload):
            raise DistributionCapacityReplayV1Error("capacity replay payload is not canonical or digest mismatch")
        return replay
    except (ValueError, TypeError) as exc:
        if isinstance(exc, DistributionCapacityReplayV1Error):
            raise
        raise DistributionCapacityReplayV1Error(str(exc)) from exc
