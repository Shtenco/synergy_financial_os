from __future__ import annotations

from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_available_capacity_v3 import (
    DistributionAvailableCapacityV3Error,
    build_distribution_available_capacity_v3,
    verify_distribution_available_capacity_v3_payload,
)

H = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def _payload() -> dict:
    payload = {
        "schema": "distribution.available-capacity/v3",
        "capacity_id": "cap-v3",
        "affected_period_id": "2026-M08",
        "base_distribution_capacity_replay_digest": H,
        "distribution_budget_state_schema": "distribution.budget-state/v2",
        "distribution_budget_state_digest": B,
        "current_financial_snapshot_digest": C,
        "current_accounting_close_digest": D,
        "current_liquidity_resources_digest": E,
        "liquidity_policy_digest": F,
        "maturity_snapshot_digests": [H],
        "maturity_translation_digests": [B],
        "reporting_currency": "USD",
        "current_snapshot_sequence": 42,
        "current_snapshot_ledger_digest": C,
        "gross_period_profit_budget": "25",
        "post_close_settlement_fee_expenses": "1.5",
        "fee_adjusted_period_profit_budget": "23.5",
        "canonical_distribution_outflows": "10",
        "canonical_distribution_reversals": "0",
        "net_consumed_distribution_budget": "10",
        "remaining_period_profit_budget": "13.5",
        "current_hard_nav": "90",
        "current_required_hard_nav_buffer": "20",
        "current_solvency_headroom": "70",
        "current_liquidity_distribution_capacity": "8",
        "final_available_capacity": "8",
        "horizon_headrooms": [{"horizon_weeks": 1}, {"horizon_weeks": 4}, {"horizon_weeks": 8}],
        "blockers": [],
        "status": "CAPACITY_AVAILABLE",
        "generated_at": "2026-08-24T12:00:00Z",
        "authority": "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V3",
        "authorization_authority": "NONE",
        "payment_authority": "NONE",
        "execution_authority": "NONE",
        "ai_authority": "NONE",
    }
    payload["digest"] = canonical_json_digest(payload)
    return payload


def test_fee_aware_capacity_payload_formula() -> None:
    payload = _payload()
    assert verify_distribution_available_capacity_v3_payload(payload)
    assert Decimal(payload["fee_adjusted_period_profit_budget"]) == Decimal("23.5")
    assert Decimal(payload["remaining_period_profit_budget"]) == Decimal("13.5")
    assert Decimal(payload["final_available_capacity"]) == Decimal("8")


def test_fresh_hash_cannot_hide_fee_budget_tamper() -> None:
    payload = _payload()
    payload["post_close_settlement_fee_expenses"] = "0.5"
    payload.pop("digest")
    payload["digest"] = canonical_json_digest(payload)
    assert not verify_distribution_available_capacity_v3_payload(payload)


def test_fresh_hash_cannot_inflate_final_capacity() -> None:
    payload = _payload()
    payload["final_available_capacity"] = "13.5"
    payload.pop("digest")
    payload["digest"] = canonical_json_digest(payload)
    assert not verify_distribution_available_capacity_v3_payload(payload)


def test_v3_builder_rejects_legacy_budget_state_before_any_other_input() -> None:
    with pytest.raises(DistributionAvailableCapacityV3Error, match="requires DistributionBudgetStateV2"):
        build_distribution_available_capacity_v3(
            capacity_id="cap-v3",
            base_capacity=None,  # type: ignore[arg-type]
            budget_state=object(),  # type: ignore[arg-type]
            current_financial_snapshot={},
            current_accounting_close=None,  # type: ignore[arg-type]
            current_sealed_ledger_events=(),
            current_liquidity_resources=None,  # type: ignore[arg-type]
            liquidity_policy=None,  # type: ignore[arg-type]
            maturity_snapshots=(),
            maturity_translations=(),
            generated_at=None,  # type: ignore[arg-type]
        )
