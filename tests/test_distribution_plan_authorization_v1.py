from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.distribution_authorization_v1 import (
    DistributionAuthorizationV1Error,
    build_distribution_authorization_v1,
)
from sinergy_financial_os.distribution_capacity_replay_v1 import (
    DistributionCapacityReplayV1,
    DistributionLiquidityHeadroomV1,
)
from sinergy_financial_os.distribution_plan_authorization_contract_v1 import (
    verify_distribution_authorization_bundle_v1,
    verify_distribution_authorization_payload_v1,
    verify_distribution_plan_payload_v1,
)
from sinergy_financial_os.distribution_plan_v1 import (
    DistributionBeneficiaryV1,
    DistributionPlanV1Error,
    build_distribution_plan_v1,
)
from sinergy_financial_os.liquidity_replay_v1 import LiquidityReplayHorizonV1, LiquidityReplayV1

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = json.loads((ROOT / "schemas/distribution_plan_v1.schema.json").read_text(encoding="utf-8"))
AUTH_SCHEMA = json.loads((ROOT / "schemas/distribution_authorization_v1.schema.json").read_text(encoding="utf-8"))
REQ = "91" * 32
APPROVER = "92" * 32


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 20, hour, minute, tzinfo=UTC)


def liquidity() -> LiquidityReplayV1:
    return LiquidityReplayV1(
        replay_id="liq-for-distribution", statement_replay_digest="10"*32,
        original_financial_snapshot_digest="11"*32, liquidity_resources_digest="12"*32,
        maturity_snapshot_digests=("13"*32,), maturity_translation_digests=("14"*32,),
        affected_period_id="period-1", as_of=dt(2), reporting_currency="USD",
        restated_liquid_haircut_assets=Decimal("100"),
        horizons=(
            LiquidityReplayHorizonV1(1, Decimal("50"), Decimal("10"), Decimal("5"), Decimal("40")),
            LiquidityReplayHorizonV1(4, Decimal("75"), Decimal("30"), Decimal("2.5"), Decimal("45")),
            LiquidityReplayHorizonV1(8, Decimal("90"), Decimal("60"), Decimal("1.5"), Decimal("30")),
        ), generated_at=dt(3)
    )


def capacity(liq: LiquidityReplayV1, *, final: Decimal = Decimal("18")) -> DistributionCapacityReplayV1:
    if final == Decimal("18"):
        h8_min_surplus = Decimal("5")
        h8_surplus_headroom = Decimal("25")
    elif final == Decimal("17"):
        h8_min_surplus = Decimal("13")
        h8_surplus_headroom = Decimal("17")
    else:
        raise ValueError("test fixture supports only 18 or 17")
    return DistributionCapacityReplayV1(
        replay_id="capacity-for-distribution", affected_period_id="period-1",
        statement_replay_digest=liq.statement_replay_digest, liquidity_replay_digest=liq.digest,
        liquidity_resources_digest=liq.liquidity_resources_digest, liquidity_policy_digest="20"*32,
        original_financial_snapshot_digest=liq.original_financial_snapshot_digest,
        required_retention=Decimal("5"), loss_carryforward=Decimal("0"), required_hard_nav_buffer=Decimal("20"),
        restated_realized_external_pnl=Decimal("30"), restated_hard_nav=Decimal("100"),
        realized_profit_budget=Decimal("25"), solvency_headroom=Decimal("80"),
        accounting_distribution_capacity=Decimal("25"), liquidity_distribution_capacity=final,
        final_distribution_capacity=final,
        horizon_headrooms=(
            DistributionLiquidityHeadroomV1(1, Decimal("50"), Decimal("10"), Decimal("1.2"), Decimal("5"), Decimal("38"), Decimal("35"), Decimal("35")),
            DistributionLiquidityHeadroomV1(4, Decimal("75"), Decimal("30"), Decimal("1.2"), Decimal("5"), Decimal("39"), Decimal("40"), Decimal("39")),
            DistributionLiquidityHeadroomV1(8, Decimal("90"), Decimal("60"), Decimal("1.2"), h8_min_surplus, Decimal("18"), h8_surplus_headroom, final),
        ), blockers=(), status="CAPACITY_AVAILABLE", generated_at=dt(3,20)
    )


def plan_and_auth():
    liq = liquidity()
    cap = capacity(liq)
    plan = build_distribution_plan_v1(
        plan_id="distribution-plan-001", distribution_capacity_replay=cap, liquidity_replay=liq,
        source_account_id="treasury-usd",
        beneficiaries=(
            DistributionBeneficiaryV1("beneficiary-a", "bank-a", Decimal("10"), "dist-001-a"),
            DistributionBeneficiaryV1("beneficiary-b", "bank-b", Decimal("8"), "dist-001-b"),
        ), generated_at=dt(3,30)
    )
    auth = build_distribution_authorization_v1(
        authorization_id="distribution-auth-001", decision="APPROVED", decision_authority="MULTISIG_GOVERNANCE",
        distribution_plan=plan, distribution_capacity_replay=cap, requirement_registry_digest=REQ,
        approver_policy_digest=APPROVER, decision_evidence_digest="93"*32,
        decided_at=dt(3,40), expires_at=dt(4,40)
    )
    return liq, cap, plan, auth


def test_exact_batch_plan_and_human_authorization_bind_every_beneficiary_byte():
    liq, cap, plan, auth = plan_and_auth()
    assert plan.total_amount == Decimal("18")
    assert plan.capacity_limit == Decimal("18")
    assert auth.approved_total_amount == Decimal("18")
    assert auth.beneficiary_set_digest == plan.beneficiary_set_digest
    assert auth.ai_authority == "NONE"
    assert auth.execution_authority == "SEPARATE_METAPAY_BATCH_HANDOFF"
    jsonschema.Draft202012Validator(PLAN_SCHEMA).validate(plan.to_dict())
    jsonschema.Draft202012Validator(AUTH_SCHEMA).validate(auth.to_dict())
    assert verify_distribution_plan_payload_v1(plan.to_dict()).digest == plan.digest
    assert verify_distribution_authorization_payload_v1(auth.to_dict()).digest == auth.digest
    valid, blockers = verify_distribution_authorization_bundle_v1(
        auth, current_plan=plan, current_capacity_replay=cap, current_liquidity_replay=liq,
        current_requirement_registry_digest=REQ, current_approver_policy_digest=APPROVER, now=dt(4)
    )
    assert valid and blockers == ()


def test_plan_cannot_exceed_capacity():
    liq = liquidity(); cap = capacity(liq)
    with pytest.raises(DistributionPlanV1Error, match="exceeds capacity"):
        build_distribution_plan_v1(
            plan_id="too-large", distribution_capacity_replay=cap, liquidity_replay=liq,
            source_account_id="treasury-usd",
            beneficiaries=(DistributionBeneficiaryV1("beneficiary-a", "bank-a", Decimal("19"), "too-large-a"),),
            generated_at=dt(3,30)
        )


def test_changed_destination_requires_new_authorization_even_with_valid_new_plan_hash():
    liq, cap, original_plan, auth = plan_and_auth()
    changed_plan = build_distribution_plan_v1(
        plan_id=original_plan.plan_id, distribution_capacity_replay=cap, liquidity_replay=liq,
        source_account_id=original_plan.source_account_id,
        beneficiaries=(
            DistributionBeneficiaryV1("beneficiary-a", "attacker-bank", Decimal("10"), "dist-001-a"),
            DistributionBeneficiaryV1("beneficiary-b", "bank-b", Decimal("8"), "dist-001-b"),
        ), generated_at=original_plan.generated_at
    )
    assert changed_plan.digest != original_plan.digest
    valid, blockers = verify_distribution_authorization_bundle_v1(
        auth, current_plan=changed_plan, current_capacity_replay=cap, current_liquidity_replay=liq,
        current_requirement_registry_digest=REQ, current_approver_policy_digest=APPROVER, now=dt(4)
    )
    assert not valid
    assert "STALE_DISTRIBUTION_PLAN" in blockers
    assert "BENEFICIARY_SET_MISMATCH" in blockers


def test_capacity_recalculation_invalidates_old_plan_and_authorization():
    liq, cap, plan, auth = plan_and_auth()
    lower = capacity(liq, final=Decimal("17"))
    valid, blockers = verify_distribution_authorization_bundle_v1(
        auth, current_plan=plan, current_capacity_replay=lower, current_liquidity_replay=liq,
        current_requirement_registry_digest=REQ, current_approver_policy_digest=APPROVER, now=dt(4)
    )
    assert not valid
    assert "CURRENT_PLAN_CONTEXT_INVALID" in blockers
    assert "STALE_DISTRIBUTION_CAPACITY" in blockers


def test_expired_or_ai_authorization_fails_closed():
    liq, cap, plan, auth = plan_and_auth()
    valid, blockers = verify_distribution_authorization_bundle_v1(
        auth, current_plan=plan, current_capacity_replay=cap, current_liquidity_replay=liq,
        current_requirement_registry_digest=REQ, current_approver_policy_digest=APPROVER, now=dt(5)
    )
    assert not valid and "AUTHORIZATION_EXPIRED_OR_NOT_YET_VALID" in blockers
    with pytest.raises(DistributionAuthorizationV1Error, match="AI"):
        __import__("sinergy_financial_os.distribution_authorization_v1", fromlist=["DistributionAuthorizationV1"]).DistributionAuthorizationV1(
            authorization_id="bad-ai", decision="APPROVED", decision_authority="HUMAN_COMMITTEE",
            distribution_plan_digest=plan.digest, distribution_capacity_replay_digest=cap.digest,
            liquidity_replay_digest=liq.digest, affected_period_id=plan.affected_period_id,
            distribution_currency=plan.distribution_currency, source_account_id=plan.source_account_id,
            beneficiary_set_digest=plan.beneficiary_set_digest, approved_total_amount=plan.total_amount,
            requirement_registry_digest=REQ, approver_policy_digest=APPROVER, decision_evidence_digest="93"*32,
            decided_at=dt(3,40), expires_at=dt(4,40), ai_authority="AI"
        )
