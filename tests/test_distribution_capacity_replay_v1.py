from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_capacity_contract_v1 import (
    verify_distribution_capacity_replay_payload_v1,
    verify_liquidity_policy_payload_v1,
)
from sinergy_financial_os.distribution_capacity_replay_v1 import (
    DistributionCapacityReplayV1Error,
    build_distribution_capacity_replay_v1,
)
from sinergy_financial_os.liquidity_policy_v1 import LiquidityPolicyHorizonV1, LiquidityPolicyV1
from sinergy_financial_os.liquidity_replay_v1 import LiquidityReplayHorizonV1, LiquidityReplayV1
from sinergy_financial_os.liquidity_resources_v1 import LiquidityResourceHorizonV1, LiquidityResourcesV1
from sinergy_financial_os.statement_replay_v1 import StatementReplayV1

ROOT = Path(__file__).resolve().parents[1]
POLICY_SCHEMA = json.loads((ROOT / "schemas/liquidity_policy_v1.schema.json").read_text(encoding="utf-8"))
CAPACITY_SCHEMA = json.loads((ROOT / "schemas/distribution_capacity_replay_v1.schema.json").read_text(encoding="utf-8"))


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 20, hour, minute, tzinfo=UTC)


def context(*, invariant_failures=()):
    snapshot = {
        "schema":"financial.snapshot/v2",
        "sequence":2,
        "as_of":"2026-08-20T02:00:00+00:00",
        "reporting_currency":"USD",
        "ledger_digest":"10"*32,
        "ledger_last_entry_digest":"11"*32,
        "account_registry_digest":"12"*32,
        "valuation_policy_digest":"13"*32,
        "required_retention":"5",
        "loss_carryforward":"0",
        "required_hard_nav_buffer":"20",
        "invariant_failures":list(invariant_failures),
    }
    snapshot["digest"] = canonical_json_digest(snapshot)
    statement = StatementReplayV1(
        replay_id="statement-capacity", affected_period_id="period-1",
        original_period_close_digest="14"*32, original_accounting_close_digest="15"*32,
        original_financial_snapshot_digest=snapshot["digest"], opening_period_close_digest="16"*32,
        opening_accounting_close_digest="17"*32, account_registry_artifact_digest="18"*32,
        account_registry_digest="12"*32, valuation_policy_artifact_digest="19"*32,
        valuation_policy_digest="13"*32, restated_period_view_digest="1a"*32,
        overlay_digests=("1b"*32,), excluded_reporting_entry_digests=("1c"*32,),
        opening_sequence=1, closing_sequence=2, original_event_count=2, retained_event_count=1,
        excluded_event_count=1, replayed_ledger_digest="1d"*32, replayed_last_entry_digest="1e"*32,
        hard_external_assets=Decimal("100"), liquid_haircut_assets=Decimal("100"),
        economic_haircut_assets=Decimal("100"), external_liabilities=Decimal("0"),
        hard_nav=Decimal("100"), liquid_nav=Decimal("100"), economic_nav=Decimal("100"),
        realized_external_revenue=Decimal("30"), realized_external_pnl=Decimal("30"), generated_at=dt(3)
    )
    policy = LiquidityPolicyV1(
        policy_id="distribution-liquidity-policy-v1", reporting_currency="USD", as_of=dt(2),
        horizons=(
            LiquidityPolicyHorizonV1(1, Decimal("1.2"), Decimal("5")),
            LiquidityPolicyHorizonV1(4, Decimal("1.2"), Decimal("5")),
            LiquidityPolicyHorizonV1(8, Decimal("1.2"), Decimal("5")),
        ), generated_at=dt(2,30)
    )
    resources = LiquidityResourcesV1(
        measurement_id="resources-capacity", statement_replay_digest=statement.digest,
        affected_period_id=statement.affected_period_id, as_of=dt(2), reporting_currency="USD",
        account_registry_digest=statement.account_registry_digest, valuation_policy_digest=statement.valuation_policy_digest,
        liquidity_policy_digest=policy.digest,
        horizons=(
            LiquidityResourceHorizonV1(1, Decimal("50"), "21"*32),
            LiquidityResourceHorizonV1(4, Decimal("75"), "22"*32),
            LiquidityResourceHorizonV1(8, Decimal("90"), "23"*32),
        ), generated_at=dt(3,5)
    )
    liquidity = LiquidityReplayV1(
        replay_id="liquidity-capacity", statement_replay_digest=statement.digest,
        original_financial_snapshot_digest=snapshot["digest"], liquidity_resources_digest=resources.digest,
        maturity_snapshot_digests=("24"*32,), maturity_translation_digests=("25"*32,),
        affected_period_id=statement.affected_period_id, as_of=dt(2), reporting_currency="USD",
        restated_liquid_haircut_assets=statement.liquid_haircut_assets,
        horizons=(
            LiquidityReplayHorizonV1(1, Decimal("50"), Decimal("10"), Decimal("5"), Decimal("40")),
            LiquidityReplayHorizonV1(4, Decimal("75"), Decimal("30"), Decimal("2.5"), Decimal("45")),
            LiquidityReplayHorizonV1(8, Decimal("90"), Decimal("60"), Decimal("1.5"), Decimal("30")),
        ), generated_at=dt(3,10)
    )
    return snapshot, statement, policy, resources, liquidity


def test_capacity_is_minimum_of_profit_solvency_and_post_distribution_liquidity_headroom():
    snapshot, statement, policy, resources, liquidity = context()
    result = build_distribution_capacity_replay_v1(
        replay_id="distribution-capacity-001", statement_replay=statement, liquidity_replay=liquidity,
        liquidity_resources=resources, liquidity_policy=policy, original_financial_snapshot=snapshot,
        generated_at=dt(3,20)
    )
    assert result.realized_profit_budget == Decimal("25")
    assert result.solvency_headroom == Decimal("80")
    assert result.accounting_distribution_capacity == Decimal("25")
    assert [x.horizon_distribution_capacity for x in result.horizon_headrooms] == [Decimal("35"), Decimal("39.0"), Decimal("18.0")]
    assert result.liquidity_distribution_capacity == Decimal("18.0")
    assert result.final_distribution_capacity == Decimal("18.0")
    assert result.status == "CAPACITY_AVAILABLE"
    assert result.authorization_authority == "NONE"
    jsonschema.Draft202012Validator(POLICY_SCHEMA).validate(policy.to_dict())
    jsonschema.Draft202012Validator(CAPACITY_SCHEMA).validate(result.to_dict())
    assert verify_liquidity_policy_payload_v1(policy.to_dict()).digest == policy.digest
    assert verify_distribution_capacity_replay_payload_v1(result.to_dict()).digest == result.digest


def test_original_snapshot_invariant_failure_forces_no_action_until_separate_reevaluation():
    snapshot, statement, policy, resources, liquidity = context(invariant_failures=("LEGACY_LCR_BLOCKER",))
    result = build_distribution_capacity_replay_v1(
        replay_id="distribution-capacity-blocked", statement_replay=statement, liquidity_replay=liquidity,
        liquidity_resources=resources, liquidity_policy=policy, original_financial_snapshot=snapshot,
        generated_at=dt(3,20)
    )
    assert result.status == "NO_ACTION"
    assert result.final_distribution_capacity == Decimal("0")
    assert "ORIGINAL_SNAPSHOT_INVARIANT_FAILURES_REQUIRE_REEVALUATION" in result.blockers


def test_recomputed_outer_hash_cannot_inflate_final_capacity():
    snapshot, statement, policy, resources, liquidity = context()
    result = build_distribution_capacity_replay_v1(
        replay_id="distribution-capacity-tamper", statement_replay=statement, liquidity_replay=liquidity,
        liquidity_resources=resources, liquidity_policy=policy, original_financial_snapshot=snapshot,
        generated_at=dt(3,20)
    )
    payload = result.to_dict()
    payload["final_distribution_capacity"] = "999"
    body = dict(payload); body.pop("digest")
    payload["digest"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with pytest.raises(DistributionCapacityReplayV1Error, match="final distribution capacity"):
        verify_distribution_capacity_replay_payload_v1(payload)


def test_capacity_refuses_self_consistent_liquidity_with_different_resource_measurements():
    snapshot, statement, policy, resources, liquidity = context()
    forged_resources = LiquidityResourcesV1(
        measurement_id="forged", statement_replay_digest=statement.digest, affected_period_id=statement.affected_period_id,
        as_of=dt(2), reporting_currency="USD", account_registry_digest=statement.account_registry_digest,
        valuation_policy_digest=statement.valuation_policy_digest, liquidity_policy_digest=policy.digest,
        horizons=(
            LiquidityResourceHorizonV1(1, Decimal("49"), "31"*32),
            LiquidityResourceHorizonV1(4, Decimal("75"), "32"*32),
            LiquidityResourceHorizonV1(8, Decimal("90"), "33"*32),
        ), generated_at=dt(3,5)
    )
    with pytest.raises(DistributionCapacityReplayV1Error, match="LiquidityReplay / LiquidityResources"):
        build_distribution_capacity_replay_v1(
            replay_id="mismatch", statement_replay=statement, liquidity_replay=liquidity,
            liquidity_resources=forged_resources, liquidity_policy=policy, original_financial_snapshot=snapshot,
            generated_at=dt(3,20)
        )
