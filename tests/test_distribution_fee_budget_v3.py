from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_authorization_v2 import (
    DistributionAuthorizationV2Error,
    build_distribution_authorization_v2,
)
from sinergy_financial_os.distribution_available_capacity_v2 import DistributionAvailableCapacityV2
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionLiquidityHeadroomV1
from sinergy_financial_os.distribution_execution_ticket_v2 import (
    DistributionExecutionTicketV2Error,
    build_distribution_execution_ticket_v2,
)
from sinergy_financial_os.distribution_fee_budget_contract_v3 import (
    reject_legacy_distribution_schema_for_fee_authority,
    verify_distribution_fee_budget_bundle_v3,
    verify_distribution_plan_payload_v2,
)
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1
from sinergy_financial_os.distribution_plan_v2 import DistributionPlanV2Error, build_distribution_plan_v2

H = "1" * 64
REQ = "2" * 64
POLICY = "3" * 64
DECISION = "4" * 64
T0 = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


def headroom(weeks: int) -> DistributionLiquidityHeadroomV1:
    return DistributionLiquidityHeadroomV1(
        horizon_weeks=weeks,
        pre_distribution_resources=Decimal("20"),
        expected_net_outflows=Decimal("5"),
        minimum_lcr=Decimal("1"),
        minimum_liquidity_surplus=Decimal("3"),
        lcr_headroom=Decimal("15"),
        surplus_headroom=Decimal("12"),
        horizon_distribution_capacity=Decimal("12"),
    )


def capacity(*, capacity_id: str = "capacity-12") -> DistributionAvailableCapacityV2:
    return DistributionAvailableCapacityV2(
        capacity_id=capacity_id,
        affected_period_id="2026-Q3",
        base_distribution_capacity_replay_digest=H,
        distribution_budget_state_digest=H,
        current_financial_snapshot_digest=H,
        current_accounting_close_digest=H,
        current_liquidity_resources_digest=H,
        liquidity_policy_digest=H,
        maturity_snapshot_digests=(H,),
        maturity_translation_digests=("5" * 64,),
        reporting_currency="USDC",
        current_snapshot_sequence=10,
        current_snapshot_ledger_digest=H,
        remaining_period_profit_budget=Decimal("12"),
        current_hard_nav=Decimal("100"),
        current_required_hard_nav_buffer=Decimal("80"),
        current_solvency_headroom=Decimal("20"),
        current_liquidity_distribution_capacity=Decimal("12"),
        final_available_capacity=Decimal("12"),
        horizon_headrooms=(headroom(1), headroom(4), headroom(8)),
        blockers=(),
        status="CAPACITY_AVAILABLE",
        generated_at=T0,
    )


def beneficiary(amount: str = "10") -> DistributionBeneficiaryV1:
    return DistributionBeneficiaryV1(
        beneficiary_id="owner-a",
        destination_id="wallet-a",
        amount=Decimal(amount),
        payment_idempotency_key="dist-owner-a-2026q3-v2",
    )


def bundle(*, fee: str = "2"):
    cap = capacity()
    plan = build_distribution_plan_v2(
        plan_id="plan-v2",
        available_capacity=cap,
        source_account_id="external-usdc",
        beneficiaries=(beneficiary(),),
        external_fee_budget=Decimal(fee),
        generated_at=T0 + timedelta(minutes=1),
    )
    auth = build_distribution_authorization_v2(
        authorization_id="auth-v2",
        decision="APPROVED",
        decision_authority="MULTISIG_GOVERNANCE",
        plan=plan,
        available_capacity=cap,
        requirement_registry_digest=REQ,
        approver_policy_digest=POLICY,
        decision_evidence_digest=DECISION,
        decided_at=T0 + timedelta(minutes=2),
        expires_at=T0 + timedelta(hours=1),
    )
    ticket = build_distribution_execution_ticket_v2(
        ticket_id="ticket-v2",
        authorization=auth,
        plan=plan,
        available_capacity=cap,
        current_requirement_registry_digest=REQ,
        current_approver_policy_digest=POLICY,
        verified_at=T0 + timedelta(minutes=3),
        expires_at=T0 + timedelta(minutes=30),
    )
    return cap, plan, auth, ticket


def canonical_bundle_payloads():
    cap, plan, auth, ticket = bundle()
    return cap.to_dict(), plan.to_dict(), auth.to_dict(), ticket.to_dict()


def test_capacity_12_principal_10_fee_2_is_valid():
    cap, plan, auth, ticket = bundle()
    assert plan.principal_total == Decimal("10")
    assert plan.external_fee_budget == Decimal("2")
    assert plan.total_authorized_outflow_ceiling == Decimal("12")
    assert auth.approved_total_outflow_ceiling == Decimal("12")
    assert ticket.total_authorized_outflow_ceiling == Decimal("12")


def test_capacity_12_principal_10_fee_3_fails_closed():
    with pytest.raises(DistributionPlanV2Error):
        bundle(fee="3")


def test_zero_fee_budget_is_valid_and_does_not_change_principal():
    cap = capacity()
    plan = build_distribution_plan_v2(
        plan_id="zero-fee", available_capacity=cap, source_account_id="external-usdc",
        beneficiaries=(beneficiary(),), external_fee_budget=Decimal("0"), generated_at=T0 + timedelta(minutes=1),
    )
    assert plan.principal_total == Decimal("10")
    assert plan.total_authorized_outflow_ceiling == Decimal("10")


def test_fee_cannot_be_hidden_by_reducing_beneficiary_principal():
    cap_payload, plan_payload, auth_payload, ticket_payload = canonical_bundle_payloads()
    plan_payload = copy.deepcopy(plan_payload)
    plan_payload["beneficiaries"][0]["amount"] = "9"
    plan_payload["principal_total"] = "9"
    plan_payload["external_fee_budget"] = "3"
    plan_payload["total_authorized_outflow_ceiling"] = "12"
    plan_payload["beneficiary_set_digest"] = canonical_json_digest(plan_payload["beneficiaries"])
    body = dict(plan_payload); body.pop("digest")
    plan_payload["digest"] = canonical_json_digest(body)
    with pytest.raises((DistributionAuthorizationV2Error, DistributionExecutionTicketV2Error)):
        verify_distribution_fee_budget_bundle_v3(
            available_capacity_payload=cap_payload, plan_payload=plan_payload,
            authorization_payload=auth_payload, ticket_payload=ticket_payload,
            current_requirement_registry_digest=REQ, current_approver_policy_digest=POLICY,
            now=T0 + timedelta(minutes=4),
        )


def test_authorization_cannot_expand_fee_budget_even_with_fresh_outer_digest():
    cap_payload, plan_payload, auth_payload, ticket_payload = canonical_bundle_payloads()
    auth_payload = copy.deepcopy(auth_payload)
    auth_payload["approved_external_fee_budget"] = "3"
    auth_payload["approved_total_outflow_ceiling"] = "13"
    body = dict(auth_payload); body.pop("digest")
    auth_payload["digest"] = canonical_json_digest(body)
    with pytest.raises(DistributionAuthorizationV2Error):
        verify_distribution_fee_budget_bundle_v3(
            available_capacity_payload=cap_payload, plan_payload=plan_payload,
            authorization_payload=auth_payload, ticket_payload=ticket_payload,
            current_requirement_registry_digest=REQ, current_approver_policy_digest=POLICY,
            now=T0 + timedelta(minutes=4),
        )


def test_stale_available_capacity_invalidates_existing_plan_auth_ticket():
    cap_payload, plan_payload, auth_payload, ticket_payload = canonical_bundle_payloads()
    stale = capacity(capacity_id="new-current-capacity").to_dict()
    with pytest.raises(DistributionPlanV2Error):
        verify_distribution_fee_budget_bundle_v3(
            available_capacity_payload=stale, plan_payload=plan_payload,
            authorization_payload=auth_payload, ticket_payload=ticket_payload,
            current_requirement_registry_digest=REQ, current_approver_policy_digest=POLICY,
            now=T0 + timedelta(minutes=4),
        )


def test_legacy_v1_objects_have_zero_fee_authority():
    for schema in ("distribution.plan/v1", "distribution.authorization/v1", "distribution.execution-ticket/v1"):
        with pytest.raises(ValueError, match="no payer-borne external-fee authority"):
            reject_legacy_distribution_schema_for_fee_authority({"schema": schema})


def test_plan_payload_cannot_grant_payment_authority():
    _, plan, _, _ = bundle()
    payload = plan.to_dict(); payload["payment_authority"] = "METAPAY"
    body = dict(payload); body.pop("digest")
    payload["digest"] = canonical_json_digest(body)
    with pytest.raises(DistributionPlanV2Error):
        verify_distribution_plan_payload_v2(payload)


def test_ai_cannot_authorize_fee_budget():
    cap, plan, _, _ = bundle()
    with pytest.raises(DistributionAuthorizationV2Error):
        from sinergy_financial_os.distribution_authorization_v2 import DistributionAuthorizationV2
        DistributionAuthorizationV2(
            authorization_id="bad-ai", decision="APPROVED", decision_authority="MULTISIG_GOVERNANCE",
            distribution_plan_digest=plan.digest, distribution_available_capacity_digest=cap.digest,
            affected_period_id=plan.affected_period_id, distribution_currency=plan.distribution_currency,
            source_account_id=plan.source_account_id, beneficiary_set_digest=plan.beneficiary_set_digest,
            approved_principal_amount=Decimal("10"), approved_external_fee_budget=Decimal("2"),
            approved_total_outflow_ceiling=Decimal("12"), requirement_registry_digest=REQ,
            approver_policy_digest=POLICY, decision_evidence_digest=DECISION,
            decided_at=T0 + timedelta(minutes=2), expires_at=T0 + timedelta(hours=1), ai_authority="NEXUS",
        )


def test_ticket_cannot_outlive_authorization():
    cap, plan, auth, _ = bundle()
    with pytest.raises(DistributionExecutionTicketV2Error):
        build_distribution_execution_ticket_v2(
            ticket_id="too-long", authorization=auth, plan=plan, available_capacity=cap,
            current_requirement_registry_digest=REQ, current_approver_policy_digest=POLICY,
            verified_at=T0 + timedelta(minutes=3), expires_at=T0 + timedelta(hours=2),
        )
