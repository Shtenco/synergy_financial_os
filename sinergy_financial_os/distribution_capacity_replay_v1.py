from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from .accounting_close_v2 import verify_financial_snapshot_v2_payload
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError, distributable_profit, distribution_capacity
from .liquidity_policy_v1 import LiquidityPolicyV1
from .liquidity_replay_v1 import LiquidityReplayV1
from .liquidity_resources_v1 import LiquidityResourcesV1
from .numeric import canonical_decimal_text, finite_decimal
from .statement_replay_v1 import StatementReplayV1


SCHEMA = "distribution.capacity-replay/v1"
HORIZONS = (1, 4, 8)
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class DistributionCapacityReplayV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionCapacityReplayV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionCapacityReplayV1Error(f"{field_name} must be hex64")
    return result


def _d(value: Any, field_name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise DistributionCapacityReplayV1Error(f"{field_name} must be canonical decimal string")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
        raise DistributionCapacityReplayV1Error(f"{field_name} is not canonical decimal text")
    if nonnegative and result < ZERO:
        raise DistributionCapacityReplayV1Error(f"{field_name} must be non-negative")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionCapacityReplayV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class DistributionLiquidityHeadroomV1:
    horizon_weeks: int
    pre_distribution_resources: Decimal
    expected_net_outflows: Decimal
    minimum_lcr: Decimal
    minimum_liquidity_surplus: Decimal
    lcr_headroom: Decimal
    surplus_headroom: Decimal
    horizon_distribution_capacity: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.horizon_weeks, bool) or self.horizon_weeks not in HORIZONS:
            raise DistributionCapacityReplayV1Error("distribution headroom horizon must be 1, 4 or 8 weeks")
        values = {}
        for name in (
            "pre_distribution_resources",
            "expected_net_outflows",
            "minimum_lcr",
            "minimum_liquidity_surplus",
            "lcr_headroom",
            "surplus_headroom",
            "horizon_distribution_capacity",
        ):
            value = finite_decimal(getattr(self, name), name)
            if name not in {"lcr_headroom", "surplus_headroom"} and value < ZERO:
                raise DistributionCapacityReplayV1Error(f"{name} must be non-negative")
            values[name] = value
            object.__setattr__(self, name, value)
        resources = values["pre_distribution_resources"]
        outflows = values["expected_net_outflows"]
        minimum_lcr = values["minimum_lcr"]
        minimum_surplus = values["minimum_liquidity_surplus"]
        expected_lcr_headroom = resources if outflows == ZERO else resources - minimum_lcr * outflows
        expected_surplus_headroom = resources - outflows - minimum_surplus
        expected_capacity = max(ZERO, min(resources, expected_lcr_headroom, expected_surplus_headroom))
        if self.lcr_headroom != expected_lcr_headroom:
            raise DistributionCapacityReplayV1Error("LCR distribution headroom mismatch")
        if self.surplus_headroom != expected_surplus_headroom:
            raise DistributionCapacityReplayV1Error("liquidity-surplus distribution headroom mismatch")
        if self.horizon_distribution_capacity != expected_capacity:
            raise DistributionCapacityReplayV1Error("horizon distribution capacity mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "pre_distribution_resources": canonical_decimal_text(self.pre_distribution_resources),
            "expected_net_outflows": canonical_decimal_text(self.expected_net_outflows),
            "minimum_lcr": canonical_decimal_text(self.minimum_lcr),
            "minimum_liquidity_surplus": canonical_decimal_text(self.minimum_liquidity_surplus),
            "lcr_headroom": canonical_decimal_text(self.lcr_headroom),
            "surplus_headroom": canonical_decimal_text(self.surplus_headroom),
            "horizon_distribution_capacity": canonical_decimal_text(self.horizon_distribution_capacity),
        }


@dataclass(frozen=True)
class DistributionCapacityReplayV1:
    replay_id: str
    affected_period_id: str
    statement_replay_digest: str
    liquidity_replay_digest: str
    liquidity_resources_digest: str
    liquidity_policy_digest: str
    original_financial_snapshot_digest: str
    required_retention: Decimal
    loss_carryforward: Decimal
    required_hard_nav_buffer: Decimal
    restated_realized_external_pnl: Decimal
    restated_hard_nav: Decimal
    realized_profit_budget: Decimal
    solvency_headroom: Decimal
    accounting_distribution_capacity: Decimal
    liquidity_distribution_capacity: Decimal
    final_distribution_capacity: Decimal
    horizon_headrooms: tuple[DistributionLiquidityHeadroomV1, ...]
    blockers: tuple[str, ...]
    status: str
    generated_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_CAPACITY_REPLAY"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_CAPACITY_REPLAY":
            raise DistributionCapacityReplayV1Error("capacity replay authority must remain Financial OS")
        if any(
            value != "NONE"
            for value in (self.authorization_authority, self.payment_authority, self.execution_authority)
        ):
            raise DistributionCapacityReplayV1Error("capacity replay cannot authorize, pay or execute")
        object.__setattr__(self, "replay_id", _text(self.replay_id, "replay_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        for name in (
            "statement_replay_digest",
            "liquidity_replay_digest",
            "liquidity_resources_digest",
            "liquidity_policy_digest",
            "original_financial_snapshot_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        for name in (
            "required_retention",
            "loss_carryforward",
            "required_hard_nav_buffer",
            "realized_profit_budget",
            "solvency_headroom",
            "accounting_distribution_capacity",
            "liquidity_distribution_capacity",
            "final_distribution_capacity",
        ):
            value = finite_decimal(getattr(self, name), name)
            if value < ZERO:
                raise DistributionCapacityReplayV1Error(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        for name in ("restated_realized_external_pnl", "restated_hard_nav"):
            value = finite_decimal(getattr(self, name), name)
            object.__setattr__(self, name, value)
        horizons = tuple(sorted(self.horizon_headrooms, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in horizons) != HORIZONS:
            raise DistributionCapacityReplayV1Error("capacity replay requires exactly 1w, 4w and 8w headrooms")
        object.__setattr__(self, "horizon_headrooms", horizons)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected_status = "CAPACITY_AVAILABLE" if self.final_distribution_capacity > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionCapacityReplayV1Error("capacity replay status mismatch")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "replay_id": self.replay_id,
            "affected_period_id": self.affected_period_id,
            "statement_replay_digest": self.statement_replay_digest,
            "liquidity_replay_digest": self.liquidity_replay_digest,
            "liquidity_resources_digest": self.liquidity_resources_digest,
            "liquidity_policy_digest": self.liquidity_policy_digest,
            "original_financial_snapshot_digest": self.original_financial_snapshot_digest,
            "required_retention": canonical_decimal_text(self.required_retention),
            "loss_carryforward": canonical_decimal_text(self.loss_carryforward),
            "required_hard_nav_buffer": canonical_decimal_text(self.required_hard_nav_buffer),
            "restated_realized_external_pnl": canonical_decimal_text(self.restated_realized_external_pnl),
            "restated_hard_nav": canonical_decimal_text(self.restated_hard_nav),
            "realized_profit_budget": canonical_decimal_text(self.realized_profit_budget),
            "solvency_headroom": canonical_decimal_text(self.solvency_headroom),
            "accounting_distribution_capacity": canonical_decimal_text(self.accounting_distribution_capacity),
            "liquidity_distribution_capacity": canonical_decimal_text(self.liquidity_distribution_capacity),
            "final_distribution_capacity": canonical_decimal_text(self.final_distribution_capacity),
            "horizon_headrooms": [item.to_dict() for item in self.horizon_headrooms],
            "blockers": list(self.blockers),
            "status": self.status,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_capacity_replay_v1(
    *,
    replay_id: str,
    statement_replay: StatementReplayV1,
    liquidity_replay: LiquidityReplayV1,
    liquidity_resources: LiquidityResourcesV1,
    liquidity_policy: LiquidityPolicyV1,
    original_financial_snapshot: Mapping[str, Any],
    generated_at: datetime,
) -> DistributionCapacityReplayV1:
    snapshot = verify_financial_snapshot_v2_payload(original_financial_snapshot)
    if snapshot["digest"] != statement_replay.original_financial_snapshot_digest:
        raise DistributionCapacityReplayV1Error("StatementReplay / original FinancialSnapshot mismatch")
    if liquidity_replay.statement_replay_digest != statement_replay.digest:
        raise DistributionCapacityReplayV1Error("LiquidityReplay / StatementReplay mismatch")
    if liquidity_replay.liquidity_resources_digest != liquidity_resources.digest:
        raise DistributionCapacityReplayV1Error("LiquidityReplay / LiquidityResources mismatch")
    if liquidity_resources.statement_replay_digest != statement_replay.digest:
        raise DistributionCapacityReplayV1Error("LiquidityResources / StatementReplay mismatch")
    if liquidity_resources.liquidity_policy_digest != liquidity_policy.digest:
        raise DistributionCapacityReplayV1Error("LiquidityResources / LiquidityPolicy digest mismatch")
    if liquidity_policy.reporting_currency != liquidity_replay.reporting_currency:
        raise DistributionCapacityReplayV1Error("LiquidityPolicy reporting currency mismatch")
    if liquidity_policy.as_of > liquidity_replay.as_of:
        raise DistributionCapacityReplayV1Error("LiquidityPolicy cannot be from the future")
    if liquidity_replay.affected_period_id != statement_replay.affected_period_id:
        raise DistributionCapacityReplayV1Error("affected period mismatch")

    retention = _d(snapshot.get("required_retention"), "required_retention", nonnegative=True)
    loss_cf = _d(snapshot.get("loss_carryforward"), "loss_carryforward", nonnegative=True)
    hard_buffer = _d(snapshot.get("required_hard_nav_buffer"), "required_hard_nav_buffer", nonnegative=True)
    profit_budget = distributable_profit(statement_replay.realized_external_pnl, retention, loss_cf)
    solvency_headroom = max(ZERO, statement_replay.hard_nav - hard_buffer)
    accounting_capacity = distribution_capacity(profit_budget, statement_replay.hard_nav, hard_buffer)

    policy_by_horizon = liquidity_policy.by_horizon()
    liquidity_by_horizon = {item.horizon_weeks: item for item in liquidity_replay.horizons}
    headrooms = []
    for horizon in HORIZONS:
        state = liquidity_by_horizon[horizon]
        rule = policy_by_horizon[horizon]
        resources = state.liquid_resources
        outflows = state.expected_net_outflows
        lcr_headroom = resources if outflows == ZERO else resources - rule.minimum_lcr * outflows
        surplus_headroom = resources - outflows - rule.minimum_liquidity_surplus
        capacity = max(ZERO, min(resources, lcr_headroom, surplus_headroom))
        headrooms.append(
            DistributionLiquidityHeadroomV1(
                horizon_weeks=horizon,
                pre_distribution_resources=resources,
                expected_net_outflows=outflows,
                minimum_lcr=rule.minimum_lcr,
                minimum_liquidity_surplus=rule.minimum_liquidity_surplus,
                lcr_headroom=lcr_headroom,
                surplus_headroom=surplus_headroom,
                horizon_distribution_capacity=capacity,
            )
        )
    liquidity_capacity = min(item.horizon_distribution_capacity for item in headrooms)

    blockers: list[str] = []
    original_failures = snapshot.get("invariant_failures") or []
    if not isinstance(original_failures, list) or any(not isinstance(item, str) for item in original_failures):
        raise DistributionCapacityReplayV1Error("FinancialSnapshot invariant_failures must be string array")
    if original_failures:
        blockers.append("ORIGINAL_SNAPSHOT_INVARIANT_FAILURES_REQUIRE_REEVALUATION")
    if profit_budget <= ZERO:
        blockers.append("NO_REALIZED_PROFIT_BUDGET")
    if solvency_headroom <= ZERO:
        blockers.append("NO_HARDNAV_SOLVENCY_HEADROOM")
    if liquidity_capacity <= ZERO:
        blockers.append("NO_LIQUIDITY_DISTRIBUTION_HEADROOM")

    final_capacity = ZERO if blockers else min(accounting_capacity, liquidity_capacity)
    generated = _utc(generated_at, "generated_at")
    latest_input_time = max(statement_replay.generated_at, liquidity_replay.generated_at, liquidity_resources.generated_at, liquidity_policy.generated_at)
    if generated < latest_input_time:
        raise DistributionCapacityReplayV1Error("capacity replay cannot predate input artifacts")
    return DistributionCapacityReplayV1(
        replay_id=replay_id,
        affected_period_id=statement_replay.affected_period_id,
        statement_replay_digest=statement_replay.digest,
        liquidity_replay_digest=liquidity_replay.digest,
        liquidity_resources_digest=liquidity_resources.digest,
        liquidity_policy_digest=liquidity_policy.digest,
        original_financial_snapshot_digest=snapshot["digest"],
        required_retention=retention,
        loss_carryforward=loss_cf,
        required_hard_nav_buffer=hard_buffer,
        restated_realized_external_pnl=statement_replay.realized_external_pnl,
        restated_hard_nav=statement_replay.hard_nav,
        realized_profit_budget=profit_budget,
        solvency_headroom=solvency_headroom,
        accounting_distribution_capacity=accounting_capacity,
        liquidity_distribution_capacity=liquidity_capacity,
        final_distribution_capacity=final_capacity,
        horizon_headrooms=tuple(headrooms),
        blockers=tuple(blockers),
        status="CAPACITY_AVAILABLE" if final_capacity > ZERO and not blockers else "NO_ACTION",
        generated_at=generated,
    )
