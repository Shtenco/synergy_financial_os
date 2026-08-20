from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_available_capacity_v2 import (
    DistributionAvailableCapacityV2,
    DistributionAvailableCapacityV2Error,
)
from sinergy_financial_os.distribution_budget_current_capacity_contract_v2 import (
    verify_distribution_available_capacity_payload_v2,
    verify_distribution_budget_state_payload_v1,
    verify_liquidity_current_resources_payload_v1,
)
from sinergy_financial_os.distribution_budget_state_v1 import DistributionBudgetStateV1
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionLiquidityHeadroomV1
from sinergy_financial_os.liquidity_current_resources_v1 import (
    LiquidityCurrentResourceHorizonV1,
    LiquidityCurrentResourcesV1,
)


ROOT = Path(__file__).resolve().parents[1]
BUDGET_SCHEMA = json.loads((ROOT / "schemas/distribution_budget_state_v1.schema.json").read_text(encoding="utf-8"))
RESOURCE_SCHEMA = json.loads((ROOT / "schemas/liquidity_current_resources_v1.schema.json").read_text(encoding="utf-8"))
CAPACITY_SCHEMA = json.loads((ROOT / "schemas/distribution_available_capacity_v2.schema.json").read_text(encoding="utf-8"))


def _time() -> datetime:
    return datetime(2026, 8, 21, 1, 0, tzinfo=UTC)


def _budget() -> DistributionBudgetStateV1:
    return DistributionBudgetStateV1(
        state_id="budget-contract",
        affected_period_id="period-profit-1",
        base_distribution_capacity_replay_digest="10" * 32,
        base_statement_replay_digest="11" * 32,
        reporting_currency="USD",
        ledger_sequence=2,
        ledger_digest="12" * 32,
        gross_period_profit_budget=Decimal("25"),
        canonical_distribution_outflows=Decimal("10"),
        canonical_distribution_reversals=Decimal("0"),
        net_consumed_distribution_budget=Decimal("10"),
        remaining_period_profit_budget=Decimal("15"),
        distribution_entry_digests=("13" * 32,),
        reversal_entry_digests=(),
        blockers=(),
        status="BUDGET_AVAILABLE",
        generated_at=_time(),
    )


def _resources() -> LiquidityCurrentResourcesV1:
    return LiquidityCurrentResourcesV1(
        resource_id="resources-contract",
        financial_snapshot_digest="20" * 32,
        accounting_close_digest="21" * 32,
        snapshot_sequence=2,
        snapshot_ledger_digest="12" * 32,
        reporting_currency="USD",
        as_of=_time(),
        liquidity_policy_digest="22" * 32,
        liquid_haircut_asset_ceiling=Decimal("90"),
        horizons=(
            LiquidityCurrentResourceHorizonV1(1, Decimal("40"), "23" * 32),
            LiquidityCurrentResourceHorizonV1(4, Decimal("65"), "24" * 32),
            LiquidityCurrentResourceHorizonV1(8, Decimal("80"), "25" * 32),
        ),
        generated_at=_time(),
    )


def _capacity() -> DistributionAvailableCapacityV2:
    return DistributionAvailableCapacityV2(
        capacity_id="capacity-contract",
        affected_period_id="period-profit-1",
        base_distribution_capacity_replay_digest="10" * 32,
        distribution_budget_state_digest=_budget().digest,
        current_financial_snapshot_digest="20" * 32,
        current_accounting_close_digest="21" * 32,
        current_liquidity_resources_digest=_resources().digest,
        liquidity_policy_digest="22" * 32,
        maturity_snapshot_digests=("30" * 32,),
        maturity_translation_digests=("31" * 32,),
        reporting_currency="USD",
        current_snapshot_sequence=2,
        current_snapshot_ledger_digest="12" * 32,
        remaining_period_profit_budget=Decimal("15"),
        current_hard_nav=Decimal("90"),
        current_required_hard_nav_buffer=Decimal("20"),
        current_solvency_headroom=Decimal("70"),
        current_liquidity_distribution_capacity=Decimal("8"),
        final_available_capacity=Decimal("8"),
        horizon_headrooms=(
            DistributionLiquidityHeadroomV1(1, Decimal("40"), Decimal("10"), Decimal("1.2"), Decimal("5"), Decimal("28"), Decimal("25"), Decimal("25")),
            DistributionLiquidityHeadroomV1(4, Decimal("65"), Decimal("30"), Decimal("1.2"), Decimal("5"), Decimal("29"), Decimal("30"), Decimal("29")),
            DistributionLiquidityHeadroomV1(8, Decimal("80"), Decimal("60"), Decimal("1.2"), Decimal("5"), Decimal("8"), Decimal("15"), Decimal("8")),
        ),
        blockers=(),
        status="CAPACITY_AVAILABLE",
        generated_at=_time(),
    )


def test_new_v22_artifacts_round_trip_through_schema_and_runtime_verifiers() -> None:
    budget = _budget().to_dict()
    resources = _resources().to_dict()
    capacity = _capacity().to_dict()
    jsonschema.Draft202012Validator(BUDGET_SCHEMA).validate(budget)
    jsonschema.Draft202012Validator(RESOURCE_SCHEMA).validate(resources)
    jsonschema.Draft202012Validator(CAPACITY_SCHEMA).validate(capacity)
    assert verify_distribution_budget_state_payload_v1(budget).digest == budget["digest"]
    assert verify_liquidity_current_resources_payload_v1(resources).digest == resources["digest"]
    assert verify_distribution_available_capacity_payload_v2(capacity).digest == capacity["digest"]


def test_fresh_outer_hash_cannot_legalize_wrong_final_available_capacity() -> None:
    payload = _capacity().to_dict()
    payload["final_available_capacity"] = "15"
    body = dict(payload)
    body.pop("digest")
    payload["digest"] = canonical_json_digest(body)
    jsonschema.Draft202012Validator(CAPACITY_SCHEMA).validate(payload)
    with pytest.raises(DistributionAvailableCapacityV2Error, match="final available distribution capacity mismatch"):
        verify_distribution_available_capacity_payload_v2(payload)


def test_resource_schema_shape_does_not_override_runtime_horizon_semantics() -> None:
    payload = _resources().to_dict()
    payload["horizons"] = [payload["horizons"][0], payload["horizons"][0], payload["horizons"][0]]
    body = dict(payload)
    body.pop("digest")
    payload["digest"] = canonical_json_digest(body)
    jsonschema.Draft202012Validator(RESOURCE_SCHEMA).validate(payload)
    with pytest.raises(Exception, match="exactly 1w, 4w and 8w"):
        verify_liquidity_current_resources_payload_v1(payload)
