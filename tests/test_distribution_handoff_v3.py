from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os.distribution_authorization_v3 import (
    DistributionAuthorizationV3Error,
    build_distribution_authorization_v3,
    verify_distribution_authorization_context_v3,
)
from sinergy_financial_os.distribution_available_capacity_v3 import DistributionAvailableCapacityV3
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionLiquidityHeadroomV1
from sinergy_financial_os.distribution_execution_ticket_v3 import (
    DistributionExecutionTicketV3Error,
    build_distribution_execution_ticket_v3,
    verify_distribution_execution_ticket_context_v3,
)
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1
from sinergy_financial_os.distribution_plan_v3 import (
    DistributionPlanV3Error,
    build_distribution_plan_v3,
    verify_distribution_plan_context_v3,
)

H = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
NOW = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)


def _headroom(horizon: int, resources: str, outflows: str) -> DistributionLiquidityHeadroomV1:
    r = Decimal(resources)
    o = Decimal(outflows)
    lcr = Decimal("1.2")
    surplus = Decimal("5")
    lcr_headroom = r - lcr * o if o else r
    surplus_headroom = r - o - surplus
    capacity = max(Decimal("0"), min(r, lcr_headroom, surplus_headroom))
    return DistributionLiquidityHeadroomV1(
        horizon_weeks=horizon,
        pre_distribution_resources=r,
        expected_net_outflows=o,
        minimum_lcr=lcr,
        minimum_liquidity_surplus=surplus,
        lcr_headroom=lcr_headroom,
        surplus_headroom=surplus_headroom,
        horizon_distribution_capacity=capacity,
    )


def _capacity() -> DistributionAvailableCapacityV3:
    return DistributionAvailableCapacityV3(
        capacity_id="cap-v3",
        affected_period_id="2026-M08",
        base_distribution_capacity_replay_digest=H,
        distribution_budget_state_schema="distribution.budget-state/v2",
        distribution_budget_state_digest=B,
        current_financial_snapshot_digest=C,
        current_accounting_close_digest=D,
        current_liquidity_resources_digest=E,
        liquidity_policy_digest=F,
        maturity_snapshot_digests=(H,),
        maturity_translation_digests=(B,),
        reporting_currency="USD",
        current_snapshot_sequence=42,
        current_snapshot_ledger_digest=C,
        gross_period_profit_budget=Decimal("25"),
        post_close_settlement_fee_expenses=Decimal("1.5"),
        fee_adjusted_period_profit_budget=Decimal("23.5"),
        canonical_distribution_outflows=Decimal("10"),
        canonical_distribution_reversals=Decimal("0"),
        net_consumed_distribution_budget=Decimal("10"),
        remaining_period_profit_budget=Decimal("13.5"),
        current_hard_nav=Decimal("90"),
        current_required_hard_nav_buffer=Decimal("20"),
        current_solvency_headroom=Decimal("70"),
        current_liquidity_distribution_capacity=Decimal("8"),
        final_available_capacity=Decimal("8"),
        horizon_headrooms=(
            _headroom(1, "50", "10"),
            _headroom(4, "65", "30"),
            _headroom(8, "80", "60"),
        ),
        blockers=(),
        status="CAPACITY_AVAILABLE",
        generated_at=NOW,
    )


def _beneficiaries() -> tuple[DistributionBeneficiaryV1, ...]:
    return (
        DistributionBeneficiaryV1("alice", "dest-alice", Decimal("4"), "pay-alice-1"),
        DistributionBeneficiaryV1("bob", "dest-bob", Decimal("2"), "pay-bob-1"),
    )


def test_fee_aware_v3_plan_auth_ticket_chain() -> None:
    capacity = _capacity()
    plan = build_distribution_plan_v3(
        plan_id="plan-v3",
        available_capacity=capacity,
        source_account_id="cash-usd",
        beneficiaries=_beneficiaries(),
        external_fee_budget=Decimal("2"),
        generated_at=NOW + timedelta(seconds=1),
    )
    assert plan.principal_total == Decimal("6")
    assert plan.total_authorized_outflow_ceiling == Decimal("8")
    ok, blockers = verify_distribution_plan_context_v3(plan, current_available_capacity=capacity)
    assert ok and not blockers

    auth = build_distribution_authorization_v3(
        authorization_id="auth-v3",
        decision="APPROVED",
        decision_authority="MULTISIG_GOVERNANCE",
        plan=plan,
        available_capacity=capacity,
        requirement_registry_digest=D,
        approver_policy_digest=E,
        decision_evidence_digest=F,
        decided_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=10),
    )
    ok, blockers = verify_distribution_authorization_context_v3(
        auth,
        current_plan=plan,
        current_available_capacity=capacity,
        current_requirement_registry_digest=D,
        current_approver_policy_digest=E,
        now=NOW + timedelta(seconds=3),
    )
    assert ok and not blockers
    assert auth.ai_authority == "NONE"

    ticket = build_distribution_execution_ticket_v3(
        ticket_id="ticket-v3",
        authorization=auth,
        plan=plan,
        available_capacity=capacity,
        current_requirement_registry_digest=D,
        current_approver_policy_digest=E,
        verified_at=NOW + timedelta(seconds=3),
        expires_at=NOW + timedelta(minutes=5),
    )
    ok, blockers = verify_distribution_execution_ticket_context_v3(
        ticket,
        authorization=auth,
        plan=plan,
        available_capacity=capacity,
        current_requirement_registry_digest=D,
        current_approver_policy_digest=E,
        now=NOW + timedelta(minutes=1),
    )
    assert ok and not blockers
    assert ticket.payment_authority == "METAPAY_ONLY"
    assert ticket.execution_authority == "NONE"


def test_principal_plus_fee_cannot_exceed_fee_aware_capacity() -> None:
    capacity = _capacity()
    with pytest.raises(DistributionPlanV3Error, match="exceeds fee-aware current capacity"):
        build_distribution_plan_v3(
            plan_id="too-large",
            available_capacity=capacity,
            source_account_id="cash-usd",
            beneficiaries=(DistributionBeneficiaryV1("alice", "dest", Decimal("7"), "p1"),),
            external_fee_budget=Decimal("2"),
            generated_at=NOW + timedelta(seconds=1),
        )


def test_v3_handoff_rejects_legacy_generation_objects() -> None:
    with pytest.raises(DistributionPlanV3Error, match="requires DistributionAvailableCapacityV3"):
        build_distribution_plan_v3(
            plan_id="legacy",
            available_capacity=object(),  # type: ignore[arg-type]
            source_account_id="cash",
            beneficiaries=_beneficiaries(),
            external_fee_budget=Decimal("0"),
            generated_at=NOW,
        )
    with pytest.raises(DistributionAuthorizationV3Error, match="requires Plan v3 and AvailableCapacity v3"):
        build_distribution_authorization_v3(
            authorization_id="legacy",
            decision="APPROVED",
            decision_authority="HUMAN_COMMITTEE",
            plan=object(),  # type: ignore[arg-type]
            available_capacity=object(),  # type: ignore[arg-type]
            requirement_registry_digest=D,
            approver_policy_digest=E,
            decision_evidence_digest=F,
            decided_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(DistributionExecutionTicketV3Error, match="requires Authorization v3"):
        build_distribution_execution_ticket_v3(
            ticket_id="legacy",
            authorization=object(),  # type: ignore[arg-type]
            plan=object(),  # type: ignore[arg-type]
            available_capacity=object(),  # type: ignore[arg-type]
            current_requirement_registry_digest=D,
            current_approver_policy_digest=E,
            verified_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
