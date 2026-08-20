from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os.distribution_available_capacity_v2 import DistributionAvailableCapacityV2
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionLiquidityHeadroomV1
from sinergy_financial_os.distribution_capacity_reservation_contract_v1 import (
    mark_distribution_reservation_accounted_canonical_v1,
    verify_commitment_state_context_v1,
    verify_commitment_state_transition_v1,
    verify_distribution_capacity_reservation_payload_v1,
    verify_distribution_commitment_state_payload_v1,
    verify_reservation_chain_v1,
)
from sinergy_financial_os.distribution_capacity_reservation_v1 import (
    DistributionCapacityReservationV1Error,
    DistributionCommitmentBookV1,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)


def dt(minute: int = 0) -> datetime:
    return datetime(2026, 8, 21, 2, minute, tzinfo=UTC)


def capacity(
    amount: str = "8",
    *,
    sequence: int = 1,
    ledger_digest: str = "11" * 32,
    snapshot_digest: str = "12" * 32,
    blockers: tuple[str, ...] = (),
) -> DistributionAvailableCapacityV2:
    final = Decimal("0") if blockers else Decimal(amount)
    remaining_budget = Decimal("0") if "NO_REMAINING_PERIOD_BUDGET" in blockers else Decimal("15")
    return DistributionAvailableCapacityV2(
        capacity_id=f"capacity-{sequence}-{amount}-{'blocked' if blockers else 'open'}",
        affected_period_id="period-profit-1",
        base_distribution_capacity_replay_digest="13" * 32,
        distribution_budget_state_digest="14" * 32,
        current_financial_snapshot_digest=snapshot_digest,
        current_accounting_close_digest="15" * 32,
        current_liquidity_resources_digest="16" * 32,
        liquidity_policy_digest="17" * 32,
        maturity_snapshot_digests=("18" * 32,),
        maturity_translation_digests=("19" * 32,),
        reporting_currency="USD",
        current_snapshot_sequence=sequence,
        current_snapshot_ledger_digest=ledger_digest,
        remaining_period_profit_budget=remaining_budget,
        current_hard_nav=Decimal("90"),
        current_required_hard_nav_buffer=Decimal("20"),
        current_solvency_headroom=Decimal("70"),
        current_liquidity_distribution_capacity=Decimal("8"),
        final_available_capacity=final,
        horizon_headrooms=(
            DistributionLiquidityHeadroomV1(1, Decimal("40"), Decimal("10"), Decimal("1.2"), Decimal("5"), Decimal("28"), Decimal("25"), Decimal("25")),
            DistributionLiquidityHeadroomV1(4, Decimal("65"), Decimal("30"), Decimal("1.2"), Decimal("5"), Decimal("29"), Decimal("30"), Decimal("29")),
            DistributionLiquidityHeadroomV1(8, Decimal("80"), Decimal("60"), Decimal("1.2"), Decimal("5"), Decimal("8"), Decimal("15"), Decimal("8")),
        ),
        blockers=blockers,
        status="NO_ACTION" if blockers else "CAPACITY_AVAILABLE",
        generated_at=dt(),
    )


def test_two_parallel_plans_cannot_reserve_more_than_one_current_capacity() -> None:
    cap = capacity()
    book = DistributionCommitmentBookV1()
    state0 = book.refresh_capacity(cap, generated_at=dt())
    reservation_a, state1 = book.reserve(
        reservation_id="reservation-a",
        plan_digest="21" * 32,
        plan_amount=Decimal("5"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=cap,
        created_at=dt(1),
        expires_at=dt(20),
    )
    assert state1.outstanding_commitments == Decimal("5")
    assert state1.remaining_authorizable_capacity == Decimal("3")
    with pytest.raises(DistributionCapacityReservationV1Error, match="insufficient unreserved"):
        book.reserve(
            reservation_id="reservation-b-too-large",
            plan_digest="22" * 32,
            plan_amount=Decimal("4"),
            affected_period_id="period-profit-1",
            distribution_currency="USD",
            capacity=cap,
            created_at=dt(2),
            expires_at=dt(20),
        )
    reservation_b, state2 = book.reserve(
        reservation_id="reservation-b",
        plan_digest="23" * 32,
        plan_amount=Decimal("3"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=cap,
        created_at=dt(3),
        expires_at=dt(20),
    )
    assert state2.outstanding_commitments == Decimal("8")
    assert state2.remaining_authorizable_capacity == Decimal("0")
    assert state2.status == "NO_ACTION"
    assert verify_commitment_state_transition_v1(state0, state1)
    assert verify_commitment_state_transition_v1(state1, state2)
    assert verify_commitment_state_context_v1(
        state2, capacity=cap, latest_reservations=(reservation_a, reservation_b)
    )
    assert verify_distribution_capacity_reservation_payload_v1(reservation_a.to_dict()).digest == reservation_a.digest
    assert verify_distribution_commitment_state_payload_v1(state2.to_dict()).digest == state2.digest


def test_partial_settlement_releases_failed_remainder_but_keeps_settled_amount_outstanding_until_accounting() -> None:
    cap = capacity()
    book = DistributionCommitmentBookV1()
    r1, _ = book.reserve(
        reservation_id="reservation-partial",
        plan_digest="31" * 32,
        plan_amount=Decimal("8"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=cap,
        created_at=dt(1),
        expires_at=dt(20),
    )
    r2, _ = book.mark_attempted(
        r1.reservation_id, attempt_digest="32" * 32, capacity=cap, attempted_at=dt(2)
    )
    r3, state3 = book.apply_terminal_utilization(
        r1.reservation_id,
        utilization_digest="33" * 32,
        utilization_status="PARTIALLY_SETTLED_REQUIRES_NEW_PLAN",
        planned_total_amount=Decimal("8"),
        settled_total_amount=Decimal("3"),
        capacity=cap,
        finalized_at=dt(3),
    )
    assert r3.status == "SETTLED_PENDING_ACCOUNTING"
    assert r3.settled_amount == Decimal("3")
    assert r3.outstanding_amount == Decimal("3")
    assert state3.remaining_authorizable_capacity == Decimal("5")
    assert verify_reservation_chain_v1((r1, r2, r3))


def test_accounted_transition_requires_refreshed_ledger_and_real_owner_distribution_entry() -> None:
    old_cap = capacity(sequence=1, ledger_digest="41" * 32)
    book = DistributionCommitmentBookV1()
    r1, _ = book.reserve(
        reservation_id="reservation-accounting",
        plan_digest="42" * 32,
        plan_amount=Decimal("3"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=old_cap,
        created_at=dt(1),
        expires_at=dt(20),
    )
    r2, _ = book.mark_attempted(r1.reservation_id, attempt_digest="43" * 32, capacity=old_cap, attempted_at=dt(2))
    r3, _ = book.apply_terminal_utilization(
        r1.reservation_id,
        utilization_digest="44" * 32,
        utilization_status="FULLY_SETTLED",
        planned_total_amount=Decimal("3"),
        settled_total_amount=Decimal("3"),
        capacity=old_cap,
        finalized_at=dt(3),
    )
    with pytest.raises(DistributionCapacityReservationV1Error, match="refreshed closed ledger"):
        book.mark_accounted(
            r1.reservation_id,
            accounting_entry_digest="45" * 32,
            accounted_amount=Decimal("3"),
            refreshed_capacity=old_cap,
            accounted_at=dt(4),
        )

    ledger = ReportingLedger("USD")
    ledger.register_account(ReportingAccountSpec("cash", "Cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"))
    ledger.register_account(ReportingAccountSpec("equity", "Equity", AccountClass.EQUITY, ConsolidationClass.EXTERNAL, "MEMO_ONLY"))
    ledger.post(
        event_id="capital",
        reference="capital-ref",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("100")), ReportingLine("equity", credit=Decimal("100"))),
        evidence_digest="46" * 32,
    )
    payout = ledger.post(
        event_id="payout",
        reference="utilization-44",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("equity", debit=Decimal("3")), ReportingLine("cash", credit=Decimal("3"))),
        evidence_digest="47" * 32,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION",
            "capital_direction": "OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "affected_period_id": "period-profit-1",
            "distribution_plan_digest": r1.plan_digest,
            "distribution_utilization_digest": r3.utilization_digest,
        },
    )
    refreshed = capacity(
        amount="5",
        sequence=ledger.sequence,
        ledger_digest=ledger.digest,
        snapshot_digest="48" * 32,
    )
    r4, state4 = mark_distribution_reservation_accounted_canonical_v1(
        book,
        r1.reservation_id,
        accounting_entry_digest=payout.digest,
        refreshed_capacity=refreshed,
        current_reporting_ledger=ledger,
        accounted_at=dt(5),
    )
    assert r4.status == "ACCOUNTED"
    assert r4.outstanding_amount == Decimal("0")
    assert state4.outstanding_commitments == Decimal("0")
    assert state4.remaining_authorizable_capacity == Decimal("5")
    assert verify_reservation_chain_v1((r1, r2, r3, r4))


def test_capacity_drop_below_outstanding_commitments_blocks_new_attempts() -> None:
    cap8 = capacity("8")
    cap4 = capacity("4", sequence=2, ledger_digest="51" * 32, snapshot_digest="52" * 32)
    book = DistributionCommitmentBookV1()
    reservation, _ = book.reserve(
        reservation_id="reservation-stress",
        plan_digest="53" * 32,
        plan_amount=Decimal("6"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=cap8,
        created_at=dt(1),
        expires_at=dt(20),
    )
    stressed = book.refresh_capacity(cap4, generated_at=dt(2))
    assert stressed.status == "NO_ACTION"
    assert "OUTSTANDING_COMMITMENTS_EXCEED_CURRENT_CAPACITY" in stressed.blockers
    with pytest.raises(DistributionCapacityReservationV1Error, match="blocks attempt"):
        book.mark_attempted(
            reservation.reservation_id,
            attempt_digest="54" * 32,
            capacity=cap4,
            attempted_at=dt(3),
        )


def test_failed_terminal_attempt_releases_full_reservation_but_authorization_must_be_new() -> None:
    cap = capacity()
    book = DistributionCommitmentBookV1()
    r1, _ = book.reserve(
        reservation_id="reservation-failed",
        plan_digest="61" * 32,
        plan_amount=Decimal("8"),
        affected_period_id="period-profit-1",
        distribution_currency="USD",
        capacity=cap,
        created_at=dt(1),
        expires_at=dt(20),
    )
    r2, _ = book.mark_attempted(r1.reservation_id, attempt_digest="62" * 32, capacity=cap, attempted_at=dt(2))
    r3, state3 = book.apply_terminal_utilization(
        r1.reservation_id,
        utilization_digest="63" * 32,
        utilization_status="FAILED_NO_SETTLEMENT_REQUIRES_NEW_AUTHORIZATION",
        planned_total_amount=Decimal("8"),
        settled_total_amount=Decimal("0"),
        capacity=cap,
        finalized_at=dt(3),
    )
    assert r3.status == "RELEASED_TERMINAL_FAILED"
    assert r3.outstanding_amount == Decimal("0")
    assert state3.remaining_authorizable_capacity == Decimal("8")
    assert verify_reservation_chain_v1((r1, r2, r3))
