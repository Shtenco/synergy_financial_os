from __future__ import annotations

from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_available_capacity_v4 import (
    DistributionAvailableCapacityV4Error,
    build_distribution_available_capacity_v4,
    verify_distribution_available_capacity_v4_payload,
)

H="a"*64;B="b"*64;C="c"*64;D="d"*64;E="e"*64;F="f"*64


def payload():
    item={"schema":"distribution.available-capacity/v4","capacity_id":"cap-v4","affected_period_id":"2026-M08","base_distribution_capacity_replay_digest":H,"distribution_budget_state_schema":"distribution.budget-state/v3","distribution_budget_state_digest":B,"current_financial_snapshot_digest":C,"current_accounting_close_digest":D,"current_liquidity_resources_digest":E,"liquidity_policy_digest":F,"maturity_snapshot_digests":[H],"maturity_translation_digests":[B],"reporting_currency":"USD","current_snapshot_sequence":51,"current_snapshot_ledger_digest":C,"gross_period_profit_budget":"25","post_close_settlement_fee_expenses":"1.5","post_close_settlement_fee_refunds":"0.5","post_close_reversal_processing_fees":"0.1","net_post_close_distribution_fee_cost":"1.1","fee_adjusted_period_profit_budget":"23.9","canonical_distribution_outflows":"10","canonical_distribution_reversals":"10","net_consumed_distribution_budget":"0","remaining_period_profit_budget":"23.9","current_hard_nav":"90","current_required_hard_nav_buffer":"20","current_solvency_headroom":"70","current_liquidity_distribution_capacity":"8","final_available_capacity":"8","horizon_headrooms":[{"horizon_weeks":1},{"horizon_weeks":4},{"horizon_weeks":8}],"blockers":[],"status":"CAPACITY_AVAILABLE","generated_at":"2026-08-28T10:00:00Z","authority":"FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V4","authorization_authority":"NONE","payment_authority":"NONE","execution_authority":"NONE","ai_authority":"NONE"}
    item["digest"]=canonical_json_digest(item);return item


def test_v4_exposes_refund_restored_budget_and_current_capacity():
    item=payload();assert verify_distribution_available_capacity_v4_payload(item)
    assert Decimal(item["net_post_close_distribution_fee_cost"])==Decimal("1.1")
    assert Decimal(item["remaining_period_profit_budget"])==Decimal("23.9")
    assert Decimal(item["final_available_capacity"])==Decimal("8")


def test_fresh_hash_cannot_turn_fee_refund_into_extra_profit():
    item=payload();item["post_close_settlement_fee_refunds"]="1.6";item["net_post_close_distribution_fee_cost"]="0";item["fee_adjusted_period_profit_budget"]="25";item.pop("digest");item["digest"]=canonical_json_digest(item)
    assert not verify_distribution_available_capacity_v4_payload(item)


def test_fresh_hash_cannot_inflate_final_capacity():
    item=payload();item["final_available_capacity"]="23.9";item.pop("digest");item["digest"]=canonical_json_digest(item)
    assert not verify_distribution_available_capacity_v4_payload(item)


def test_v4_builder_rejects_non_v3_budget_state_before_other_inputs():
    with pytest.raises(DistributionAvailableCapacityV4Error,match="requires DistributionBudgetStateV3"):
        build_distribution_available_capacity_v4(capacity_id="x",base_capacity=None,budget_state=object(),current_financial_snapshot={},current_accounting_close=None,current_sealed_ledger_events=(),current_liquidity_resources=None,liquidity_policy=None,maturity_snapshots=(),maturity_translations=(),generated_at=None)  # type: ignore[arg-type]
