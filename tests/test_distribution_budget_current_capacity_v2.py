from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sinergy_financial_os.accounting_close_v2 import build_accounting_close_v2
from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.distribution_available_capacity_v2 import (
    DistributionAvailableCapacityV2Error,
    build_distribution_available_capacity_v2,
)
from sinergy_financial_os.distribution_budget_current_capacity_contract_v2 import (
    verify_distribution_available_capacity_context_v2,
    verify_distribution_available_capacity_payload_v2,
    verify_distribution_budget_state_context_v1,
    verify_distribution_budget_state_payload_v1,
    verify_liquidity_current_resources_payload_v1,
)
from sinergy_financial_os.distribution_budget_state_v1 import build_distribution_budget_state_v1
from sinergy_financial_os.distribution_capacity_replay_v1 import (
    DistributionCapacityReplayV1,
    DistributionLiquidityHeadroomV1,
)
from sinergy_financial_os.ledger_event_v2 import export_reporting_entry_as_ledger_event_v2
from sinergy_financial_os.liquidity_current_resources_v1 import (
    LiquidityCurrentResourceHorizonV1,
    build_liquidity_current_resources_v1,
)
from sinergy_financial_os.liquidity_policy_v1 import LiquidityPolicyHorizonV1, LiquidityPolicyV1
from sinergy_financial_os.maturity_translation_v1 import build_maturity_translation_artifact_v1
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule


REQ = "ab" * 32


def _base_capacity(as_of: datetime) -> DistributionCapacityReplayV1:
    return DistributionCapacityReplayV1(
        replay_id="historical-capacity-1",
        affected_period_id="period-profit-1",
        statement_replay_digest="10" * 32,
        liquidity_replay_digest="11" * 32,
        liquidity_resources_digest="12" * 32,
        liquidity_policy_digest="13" * 32,
        original_financial_snapshot_digest="14" * 32,
        required_retention=Decimal("5"),
        loss_carryforward=Decimal("0"),
        required_hard_nav_buffer=Decimal("20"),
        restated_realized_external_pnl=Decimal("30"),
        restated_hard_nav=Decimal("100"),
        realized_profit_budget=Decimal("25"),
        solvency_headroom=Decimal("80"),
        accounting_distribution_capacity=Decimal("25"),
        liquidity_distribution_capacity=Decimal("18"),
        final_distribution_capacity=Decimal("18"),
        horizon_headrooms=(
            DistributionLiquidityHeadroomV1(1, Decimal("50"), Decimal("10"), Decimal("1.2"), Decimal("5"), Decimal("38"), Decimal("35"), Decimal("35")),
            DistributionLiquidityHeadroomV1(4, Decimal("75"), Decimal("30"), Decimal("1.2"), Decimal("5"), Decimal("39"), Decimal("40"), Decimal("39")),
            DistributionLiquidityHeadroomV1(8, Decimal("90"), Decimal("60"), Decimal("1.2"), Decimal("5"), Decimal("18"), Decimal("25"), Decimal("18")),
        ),
        blockers=(),
        status="CAPACITY_AVAILABLE",
        generated_at=as_of - timedelta(days=2),
    )


def _ledger() -> tuple[ReportingLedger, object]:
    ledger = ReportingLedger("USD")
    ledger.register_account(
        ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH")
    )
    ledger.register_account(
        ReportingAccountSpec("owner_equity", "Owner equity", AccountClass.EQUITY, ConsolidationClass.EXTERNAL, "MEMO_ONLY")
    )
    ledger.post(
        event_id="capital-100",
        reference="capital-ref-100",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("100")), ReportingLine("owner_equity", credit=Decimal("100"))),
        evidence_digest="21" * 32,
        metadata={"economic_class": "OWNER_CAPITAL"},
    )
    distribution = ledger.post(
        event_id="distribution-10",
        reference="distribution-utilization-10",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("owner_equity", debit=Decimal("10")), ReportingLine("cash", credit=Decimal("10"))),
        evidence_digest="22" * 32,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION",
            "capital_direction": "OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "affected_period_id": "period-profit-1",
        },
    )
    return ledger, distribution


def _maturity_snapshot(as_of: datetime) -> dict:
    cumulative = {1: 0, 2: 0, 3: 0, 4: 20, 5: 20, 6: 20, 7: 20, 8: 50}
    buckets = []
    previous = 0
    for week in range(1, 9):
        current = cumulative[week]
        scheduled = current - previous
        buckets.append(
            {
                "week": week,
                "scheduled_unlock": str(scheduled),
                "cumulative_unlock": str(current),
                "scheduled_noncallable_unlock": str(scheduled),
                "cumulative_noncallable_unlock": str(current),
                "duration_eligible_principal": "0",
            }
        )
        previous = current
    payload = {
        "schema": "maturity.snapshot/v1",
        "as_of": as_of.isoformat(),
        "as_of_week": 0,
        "currency": "USD",
        "total_open_principal": "60",
        "immediately_callable_principal": "10",
        "buckets": buckets,
        "metadata": {
            "horizon_weeks": 8,
            "liquidity_outflow_rule": "immediately_callable_principal + cumulative_noncallable_unlock",
        },
    }
    payload["digest"] = canonical_json_digest(payload)
    return payload


def _closed_context(ledger: ReportingLedger, *, as_of: datetime, resources: tuple[str, str, str]):
    maturity = _maturity_snapshot(as_of)
    liquidity_policy = LiquidityPolicyV1(
        policy_id="liquidity-policy-current",
        reporting_currency="USD",
        as_of=as_of,
        horizons=(
            LiquidityPolicyHorizonV1(1, Decimal("1.2"), Decimal("5")),
            LiquidityPolicyHorizonV1(4, Decimal("1.2"), Decimal("5")),
            LiquidityPolicyHorizonV1(8, Decimal("1.2"), Decimal("5")),
        ),
        generated_at=as_of,
    )
    valuation = ValuationPolicy(
        policy_id="valuation-current",
        reporting_currency="USD",
        as_of=as_of - timedelta(days=1),
        rules=(ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )
    horizons = (
        LiquidityHorizonState(1, Decimal(resources[0]), Decimal("10")),
        LiquidityHorizonState(4, Decimal(resources[1]), Decimal("30")),
        LiquidityHorizonState(8, Decimal(resources[2]), Decimal("60")),
    )
    snapshot = capture_financial_snapshot_v2(
        ledger,
        valuation,
        as_of=as_of,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons,
        required_hard_nav_buffer=Decimal("20"),
        maturity_snapshot_refs=(maturity["digest"],),
    ).to_dict()
    events = tuple(
        export_reporting_entry_as_ledger_event_v2(
            entry,
            ledger,
            effective_at=as_of - timedelta(minutes=5),
            evidence_class="OTHER",
        )
        for entry in ledger.entries_since(0)
    )
    close = build_accounting_close_v2(
        events,
        snapshot,
        close_id=f"close-{ledger.sequence}-{as_of.isoformat()}",
        closed_at=as_of + timedelta(minutes=1),
        requirement_registry_digest=REQ,
    )
    translation = build_maturity_translation_artifact_v1(
        maturity,
        reporting_currency="USD",
        reporting_units_per_source_unit=Decimal("1"),
        translation_evidence_digest=None,
        generated_at=as_of + timedelta(minutes=2),
    )
    current_resources = build_liquidity_current_resources_v1(
        resource_id=f"resources-{ledger.sequence}",
        financial_snapshot=snapshot,
        accounting_close=close,
        sealed_ledger_events=events,
        liquidity_policy=liquidity_policy,
        horizons=(
            LiquidityCurrentResourceHorizonV1(1, Decimal(resources[0]), "31" * 32),
            LiquidityCurrentResourceHorizonV1(4, Decimal(resources[1]), "32" * 32),
            LiquidityCurrentResourceHorizonV1(8, Decimal(resources[2]), "33" * 32),
        ),
        generated_at=as_of + timedelta(minutes=3),
    )
    return snapshot, events, close, maturity, translation, current_resources, liquidity_policy


def test_budget_state_deducts_only_canonical_posted_distribution_and_reversal_restores_it() -> None:
    as_of = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    ledger, distribution = _ledger()
    base = _base_capacity(as_of)
    before = build_distribution_budget_state_v1(
        state_id="budget-before-reversal", base_capacity=base, ledger=ledger, generated_at=as_of
    )
    assert before.gross_period_profit_budget == Decimal("25")
    assert before.canonical_distribution_outflows == Decimal("10")
    assert before.canonical_distribution_reversals == Decimal("0")
    assert before.remaining_period_profit_budget == Decimal("15")
    assert verify_distribution_budget_state_payload_v1(before.to_dict()).digest == before.digest
    assert verify_distribution_budget_state_context_v1(before, base_capacity=base, ledger=ledger)

    ledger.post(
        event_id="distribution-reversal-4",
        reference="distribution-reversal-ref-4",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("4")), ReportingLine("owner_equity", credit=Decimal("4"))),
        evidence_digest="23" * 32,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL",
            "capital_direction": "INFLOW_REVERSAL_OF_PRIOR_OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "original_distribution_reporting_entry_digest": distribution.digest,
            "original_distribution_receipt_digest": "24" * 32,
        },
    )
    after = build_distribution_budget_state_v1(
        state_id="budget-after-reversal", base_capacity=base, ledger=ledger, generated_at=as_of + timedelta(minutes=1)
    )
    assert after.canonical_distribution_outflows == Decimal("10")
    assert after.canonical_distribution_reversals == Decimal("4")
    assert after.net_consumed_distribution_budget == Decimal("6")
    assert after.remaining_period_profit_budget == Decimal("19")


def test_current_capacity_uses_remaining_budget_and_current_post_distribution_liquidity() -> None:
    as_of = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    ledger, _ = _ledger()
    base = _base_capacity(as_of)
    budget = build_distribution_budget_state_v1(
        state_id="budget-current", base_capacity=base, ledger=ledger, generated_at=as_of + timedelta(minutes=2)
    )
    snapshot, events, close, maturity, translation, resources, policy = _closed_context(
        ledger, as_of=as_of, resources=("40", "65", "80")
    )
    assert verify_liquidity_current_resources_payload_v1(resources.to_dict()).digest == resources.digest
    capacity = build_distribution_available_capacity_v2(
        capacity_id="available-capacity-current",
        base_capacity=base,
        budget_state=budget,
        current_financial_snapshot=snapshot,
        current_accounting_close=close,
        current_sealed_ledger_events=events,
        current_liquidity_resources=resources,
        liquidity_policy=policy,
        maturity_snapshots=(maturity,),
        maturity_translations=(translation,),
        generated_at=as_of + timedelta(minutes=4),
    )
    assert budget.remaining_period_profit_budget == Decimal("15")
    assert capacity.current_hard_nav == Decimal("90")
    assert capacity.current_solvency_headroom == Decimal("70")
    assert [item.horizon_distribution_capacity for item in capacity.horizon_headrooms] == [
        Decimal("25"), Decimal("29"), Decimal("8")
    ]
    assert capacity.current_liquidity_distribution_capacity == Decimal("8")
    assert capacity.final_available_capacity == Decimal("8")
    assert capacity.status == "CAPACITY_AVAILABLE"
    assert verify_distribution_available_capacity_payload_v2(capacity.to_dict()).digest == capacity.digest
    assert verify_distribution_available_capacity_context_v2(
        capacity,
        base_capacity=base,
        budget_state=budget,
        current_financial_snapshot=snapshot,
        current_accounting_close=close,
        current_sealed_ledger_events=events,
        current_liquidity_resources=resources,
        liquidity_policy=policy,
        maturity_snapshots=(maturity,),
        maturity_translations=(translation,),
    )


def test_old_budget_state_becomes_stale_after_another_canonical_distribution_entry() -> None:
    as_of = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    ledger, _ = _ledger()
    base = _base_capacity(as_of)
    stale_budget = build_distribution_budget_state_v1(
        state_id="budget-before-race", base_capacity=base, ledger=ledger, generated_at=as_of
    )
    ledger.post(
        event_id="distribution-race-1",
        reference="distribution-race-ref-1",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("owner_equity", debit=Decimal("1")), ReportingLine("cash", credit=Decimal("1"))),
        evidence_digest="25" * 32,
        metadata={
            "economic_class": "OWNER_DISTRIBUTION",
            "capital_direction": "OUTFLOW",
            "pnl_treatment": "EXCLUDED_FROM_REALIZED_PNL",
            "affected_period_id": "period-profit-1",
        },
    )
    later = as_of + timedelta(hours=1)
    snapshot, events, close, maturity, translation, resources, policy = _closed_context(
        ledger, as_of=later, resources=("39", "64", "79")
    )
    with pytest.raises(DistributionAvailableCapacityV2Error, match="budget state is stale"):
        build_distribution_available_capacity_v2(
            capacity_id="must-fail-stale-budget",
            base_capacity=base,
            budget_state=stale_budget,
            current_financial_snapshot=snapshot,
            current_accounting_close=close,
            current_sealed_ledger_events=events,
            current_liquidity_resources=resources,
            liquidity_policy=policy,
            maturity_snapshots=(maturity,),
            maturity_translations=(translation,),
            generated_at=later + timedelta(minutes=4),
        )


def test_closed_snapshot_liquidity_must_match_independent_current_resource_evidence() -> None:
    as_of = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    ledger, _ = _ledger()
    base = _base_capacity(as_of)
    budget = build_distribution_budget_state_v1(
        state_id="budget-resource-mismatch", base_capacity=base, ledger=ledger, generated_at=as_of
    )
    snapshot, events, close, maturity, translation, _, policy = _closed_context(
        ledger, as_of=as_of, resources=("40", "65", "80")
    )
    mismatched = build_liquidity_current_resources_v1(
        resource_id="mismatched-resources",
        financial_snapshot=snapshot,
        accounting_close=close,
        sealed_ledger_events=events,
        liquidity_policy=policy,
        horizons=(
            LiquidityCurrentResourceHorizonV1(1, Decimal("39"), "41" * 32),
            LiquidityCurrentResourceHorizonV1(4, Decimal("64"), "42" * 32),
            LiquidityCurrentResourceHorizonV1(8, Decimal("79"), "43" * 32),
        ),
        generated_at=as_of + timedelta(minutes=3),
    )
    with pytest.raises(DistributionAvailableCapacityV2Error, match="resource evidence differs"):
        build_distribution_available_capacity_v2(
            capacity_id="must-fail-resource-mismatch",
            base_capacity=base,
            budget_state=budget,
            current_financial_snapshot=snapshot,
            current_accounting_close=close,
            current_sealed_ledger_events=events,
            current_liquidity_resources=mismatched,
            liquidity_policy=policy,
            maturity_snapshots=(maturity,),
            maturity_translations=(translation,),
            generated_at=as_of + timedelta(minutes=4),
        )
