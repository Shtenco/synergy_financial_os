from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .distribution_available_capacity_v2 import (
    DistributionAvailableCapacityV2,
    DistributionAvailableCapacityV2Error,
    build_distribution_available_capacity_v2,
)
from .distribution_budget_state_v1 import (
    DistributionBudgetStateV1,
    DistributionBudgetStateV1Error,
    build_distribution_budget_state_v1,
)
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from .liquidity_current_resources_v1 import (
    LiquidityCurrentResourceHorizonV1,
    LiquidityCurrentResourcesV1,
    LiquidityCurrentResourcesV1Error,
    build_liquidity_current_resources_v1,
)
from .liquidity_policy_v1 import LiquidityPolicyV1
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import ReportingLedger
from .accounting_close_v2 import AccountingCloseV2


ZERO = Decimal("0")


def _decimal(value: Any, field_name: str, *, nonnegative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be canonical decimal text")
    result = finite_decimal(value, field_name)
    if canonical_decimal_text(result) != value:
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


def verify_distribution_budget_state_payload_v1(payload: Mapping[str, Any]) -> DistributionBudgetStateV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.budget-state/v1":
        raise DistributionBudgetStateV1Error("unsupported distribution budget state schema")
    state = DistributionBudgetStateV1(
        state_id=payload.get("state_id"),
        affected_period_id=payload.get("affected_period_id"),
        base_distribution_capacity_replay_digest=payload.get("base_distribution_capacity_replay_digest"),
        base_statement_replay_digest=payload.get("base_statement_replay_digest"),
        reporting_currency=payload.get("reporting_currency"),
        ledger_sequence=payload.get("ledger_sequence"),
        ledger_digest=payload.get("ledger_digest"),
        gross_period_profit_budget=_decimal(payload.get("gross_period_profit_budget"), "gross_period_profit_budget", nonnegative=True),
        canonical_distribution_outflows=_decimal(payload.get("canonical_distribution_outflows"), "canonical_distribution_outflows", nonnegative=True),
        canonical_distribution_reversals=_decimal(payload.get("canonical_distribution_reversals"), "canonical_distribution_reversals", nonnegative=True),
        net_consumed_distribution_budget=_decimal(payload.get("net_consumed_distribution_budget"), "net_consumed_distribution_budget", nonnegative=True),
        remaining_period_profit_budget=_decimal(payload.get("remaining_period_profit_budget"), "remaining_period_profit_budget", nonnegative=True),
        distribution_entry_digests=tuple(payload.get("distribution_entry_digests") or ()),
        reversal_entry_digests=tuple(payload.get("reversal_entry_digests") or ()),
        blockers=tuple(payload.get("blockers") or ()),
        status=payload.get("status"),
        generated_at=_time(payload.get("generated_at"), "generated_at"),
        authority=payload.get("authority"),
        authorization_authority=payload.get("authorization_authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
    )
    if state.to_dict() != dict(payload):
        raise DistributionBudgetStateV1Error("distribution budget state payload is not canonical or digest mismatch")
    return state


def verify_distribution_budget_state_context_v1(
    state: DistributionBudgetStateV1,
    *,
    base_capacity: DistributionCapacityReplayV1,
    ledger: ReportingLedger,
) -> bool:
    rebuilt = build_distribution_budget_state_v1(
        state_id=state.state_id,
        base_capacity=base_capacity,
        ledger=ledger,
        generated_at=state.generated_at,
    )
    if rebuilt.digest != state.digest:
        raise DistributionBudgetStateV1Error("distribution budget state differs from canonical ledger derivation")
    return True


def verify_liquidity_current_resources_payload_v1(payload: Mapping[str, Any]) -> LiquidityCurrentResourcesV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != "liquidity.current-resources/v1":
        raise LiquidityCurrentResourcesV1Error("unsupported current liquidity resources schema")
    raw_horizons = payload.get("horizons")
    if not isinstance(raw_horizons, list):
        raise LiquidityCurrentResourcesV1Error("current liquidity horizons must be array")
    horizons = []
    for item in raw_horizons:
        if not isinstance(item, Mapping):
            raise LiquidityCurrentResourcesV1Error("current liquidity horizon must be object")
        horizons.append(
            LiquidityCurrentResourceHorizonV1(
                horizon_weeks=item.get("horizon_weeks"),
                liquid_resources=_decimal(item.get("liquid_resources"), "liquid_resources", nonnegative=True),
                measurement_evidence_digest=item.get("measurement_evidence_digest"),
            )
        )
    resource = LiquidityCurrentResourcesV1(
        resource_id=payload.get("resource_id"),
        financial_snapshot_digest=payload.get("financial_snapshot_digest"),
        accounting_close_digest=payload.get("accounting_close_digest"),
        snapshot_sequence=payload.get("snapshot_sequence"),
        snapshot_ledger_digest=payload.get("snapshot_ledger_digest"),
        reporting_currency=payload.get("reporting_currency"),
        as_of=_time(payload.get("as_of"), "as_of"),
        liquidity_policy_digest=payload.get("liquidity_policy_digest"),
        liquid_haircut_asset_ceiling=_decimal(payload.get("liquid_haircut_asset_ceiling"), "liquid_haircut_asset_ceiling", nonnegative=True),
        horizons=tuple(horizons),
        generated_at=_time(payload.get("generated_at"), "generated_at"),
        authority=payload.get("authority"),
        authorization_authority=payload.get("authorization_authority"),
        execution_authority=payload.get("execution_authority"),
    )
    if resource.to_dict() != dict(payload):
        raise LiquidityCurrentResourcesV1Error("current liquidity resources payload is not canonical or digest mismatch")
    return resource


def verify_distribution_available_capacity_payload_v2(payload: Mapping[str, Any]) -> DistributionAvailableCapacityV2:
    if not isinstance(payload, Mapping) or payload.get("schema") != "distribution.available-capacity/v2":
        raise DistributionAvailableCapacityV2Error("unsupported distribution available capacity schema")
    raw_headrooms = payload.get("horizon_headrooms")
    if not isinstance(raw_headrooms, list):
        raise DistributionAvailableCapacityV2Error("available capacity horizon_headrooms must be array")
    headrooms = []
    for item in raw_headrooms:
        if not isinstance(item, Mapping):
            raise DistributionAvailableCapacityV2Error("available capacity headroom must be object")
        headrooms.append(
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
        )
    capacity = DistributionAvailableCapacityV2(
        capacity_id=payload.get("capacity_id"),
        affected_period_id=payload.get("affected_period_id"),
        base_distribution_capacity_replay_digest=payload.get("base_distribution_capacity_replay_digest"),
        distribution_budget_state_digest=payload.get("distribution_budget_state_digest"),
        current_financial_snapshot_digest=payload.get("current_financial_snapshot_digest"),
        current_accounting_close_digest=payload.get("current_accounting_close_digest"),
        current_liquidity_resources_digest=payload.get("current_liquidity_resources_digest"),
        liquidity_policy_digest=payload.get("liquidity_policy_digest"),
        maturity_snapshot_digests=tuple(payload.get("maturity_snapshot_digests") or ()),
        maturity_translation_digests=tuple(payload.get("maturity_translation_digests") or ()),
        reporting_currency=payload.get("reporting_currency"),
        current_snapshot_sequence=payload.get("current_snapshot_sequence"),
        current_snapshot_ledger_digest=payload.get("current_snapshot_ledger_digest"),
        remaining_period_profit_budget=_decimal(payload.get("remaining_period_profit_budget"), "remaining_period_profit_budget", nonnegative=True),
        current_hard_nav=_decimal(payload.get("current_hard_nav"), "current_hard_nav"),
        current_required_hard_nav_buffer=_decimal(payload.get("current_required_hard_nav_buffer"), "current_required_hard_nav_buffer", nonnegative=True),
        current_solvency_headroom=_decimal(payload.get("current_solvency_headroom"), "current_solvency_headroom", nonnegative=True),
        current_liquidity_distribution_capacity=_decimal(payload.get("current_liquidity_distribution_capacity"), "current_liquidity_distribution_capacity", nonnegative=True),
        final_available_capacity=_decimal(payload.get("final_available_capacity"), "final_available_capacity", nonnegative=True),
        horizon_headrooms=tuple(headrooms),
        blockers=tuple(payload.get("blockers") or ()),
        status=payload.get("status"),
        generated_at=_time(payload.get("generated_at"), "generated_at"),
        authority=payload.get("authority"),
        authorization_authority=payload.get("authorization_authority"),
        payment_authority=payload.get("payment_authority"),
        execution_authority=payload.get("execution_authority"),
        ai_authority=payload.get("ai_authority"),
    )
    if capacity.to_dict() != dict(payload):
        raise DistributionAvailableCapacityV2Error("distribution available capacity payload is not canonical or digest mismatch")
    return capacity


def verify_distribution_available_capacity_context_v2(
    capacity: DistributionAvailableCapacityV2,
    *,
    base_capacity: DistributionCapacityReplayV1,
    budget_state: DistributionBudgetStateV1,
    current_financial_snapshot: Mapping[str, Any],
    current_accounting_close: AccountingCloseV2,
    current_sealed_ledger_events: Sequence[Mapping[str, Any]],
    current_liquidity_resources: LiquidityCurrentResourcesV1,
    liquidity_policy: LiquidityPolicyV1,
    maturity_snapshots: Sequence[Mapping[str, Any]],
    maturity_translations: Sequence[MaturityTranslationArtifactV1],
) -> bool:
    rebuilt = build_distribution_available_capacity_v2(
        capacity_id=capacity.capacity_id,
        base_capacity=base_capacity,
        budget_state=budget_state,
        current_financial_snapshot=current_financial_snapshot,
        current_accounting_close=current_accounting_close,
        current_sealed_ledger_events=current_sealed_ledger_events,
        current_liquidity_resources=current_liquidity_resources,
        liquidity_policy=liquidity_policy,
        maturity_snapshots=maturity_snapshots,
        maturity_translations=maturity_translations,
        generated_at=capacity.generated_at,
    )
    if rebuilt.digest != capacity.digest:
        raise DistributionAvailableCapacityV2Error("available capacity differs from canonical current-state derivation")
    return True
