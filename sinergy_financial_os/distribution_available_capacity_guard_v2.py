from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2, verify_financial_snapshot_v2_payload
from .core import distributable_profit
from .distribution_available_capacity_v2 import (
    DistributionAvailableCapacityV2,
    DistributionAvailableCapacityV2Error,
    build_distribution_available_capacity_v2,
)
from .distribution_budget_current_capacity_contract_v2 import verify_distribution_budget_state_context_v1
from .distribution_budget_state_v1 import DistributionBudgetStateV1
from .distribution_capacity_contract_v1 import verify_distribution_capacity_replay_payload_v1
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .liquidity_current_resources_v1 import LiquidityCurrentResourcesV1
from .liquidity_policy_v1 import LiquidityPolicyV1
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .reporting import ReportingLedger
from .statement_replay_v1 import StatementReplayV1


ZERO = Decimal("0")


def build_distribution_available_capacity_canonical_v2(
    *,
    capacity_id: str,
    base_capacity: DistributionCapacityReplayV1,
    statement_replay: StatementReplayV1,
    original_financial_snapshot: Mapping[str, Any],
    budget_state: DistributionBudgetStateV1,
    current_reporting_ledger: ReportingLedger,
    current_financial_snapshot: Mapping[str, Any],
    current_accounting_close: AccountingCloseV2,
    current_sealed_ledger_events: Sequence[Mapping[str, Any]],
    current_liquidity_resources: LiquidityCurrentResourcesV1,
    liquidity_policy: LiquidityPolicyV1,
    maturity_snapshots: Sequence[Mapping[str, Any]],
    maturity_translations: Sequence[MaturityTranslationArtifactV1],
    generated_at: datetime,
) -> DistributionAvailableCapacityV2:
    """Canonical v2 gate: historical entitlement + current closed solvency/liquidity.

    The raw v2 builder is a pure derivation helper. This gate additionally
    rebinds the gross period-profit budget to the original StatementReplay and
    snapshot policy inputs, re-derives BudgetState from the current canonical
    ReportingLedger, and requires that ledger to be exactly the one sealed by
    the current FinancialSnapshot.
    """

    verify_distribution_capacity_replay_payload_v1(base_capacity.to_dict())
    original_snapshot = verify_financial_snapshot_v2_payload(original_financial_snapshot)
    current_snapshot = verify_financial_snapshot_v2_payload(current_financial_snapshot)

    if base_capacity.statement_replay_digest != statement_replay.digest:
        raise DistributionAvailableCapacityV2Error("base capacity / StatementReplay mismatch")
    if base_capacity.affected_period_id != statement_replay.affected_period_id:
        raise DistributionAvailableCapacityV2Error("base capacity / StatementReplay affected period mismatch")
    if base_capacity.original_financial_snapshot_digest != original_snapshot["digest"]:
        raise DistributionAvailableCapacityV2Error("base capacity / original FinancialSnapshot mismatch")
    if statement_replay.original_financial_snapshot_digest != original_snapshot["digest"]:
        raise DistributionAvailableCapacityV2Error("StatementReplay / original FinancialSnapshot mismatch")

    retention = Decimal(original_snapshot["required_retention"])
    loss_cf = Decimal(original_snapshot["loss_carryforward"])
    hard_buffer = Decimal(original_snapshot["required_hard_nav_buffer"])
    if retention < ZERO or loss_cf < ZERO or hard_buffer < ZERO:
        raise DistributionAvailableCapacityV2Error("original distribution policy inputs must be non-negative")
    expected_gross = distributable_profit(statement_replay.realized_external_pnl, retention, loss_cf)
    if base_capacity.realized_profit_budget != expected_gross:
        raise DistributionAvailableCapacityV2Error("base gross period profit budget is not reproduced by original statement/policy")
    if (
        base_capacity.required_retention != retention
        or base_capacity.loss_carryforward != loss_cf
        or base_capacity.required_hard_nav_buffer != hard_buffer
    ):
        raise DistributionAvailableCapacityV2Error("base capacity original policy inputs mismatch")

    if current_reporting_ledger.reporting_currency != current_snapshot["reporting_currency"]:
        raise DistributionAvailableCapacityV2Error("current ReportingLedger / snapshot currency mismatch")
    if current_reporting_ledger.sequence != current_snapshot["sequence"]:
        raise DistributionAvailableCapacityV2Error("current ReportingLedger / snapshot sequence mismatch")
    if current_reporting_ledger.digest != current_snapshot["ledger_digest"]:
        raise DistributionAvailableCapacityV2Error("current ReportingLedger is not the ledger sealed by current snapshot")

    verify_distribution_budget_state_context_v1(
        budget_state,
        base_capacity=base_capacity,
        ledger=current_reporting_ledger,
    )
    if budget_state.gross_period_profit_budget != expected_gross:
        raise DistributionAvailableCapacityV2Error("budget state gross period budget mismatch")

    result = build_distribution_available_capacity_v2(
        capacity_id=capacity_id,
        base_capacity=base_capacity,
        budget_state=budget_state,
        current_financial_snapshot=current_financial_snapshot,
        current_accounting_close=current_accounting_close,
        current_sealed_ledger_events=current_sealed_ledger_events,
        current_liquidity_resources=current_liquidity_resources,
        liquidity_policy=liquidity_policy,
        maturity_snapshots=maturity_snapshots,
        maturity_translations=maturity_translations,
        generated_at=generated_at,
    )
    latest_input_time = max(
        current_accounting_close.closed_at,
        current_liquidity_resources.generated_at,
        liquidity_policy.generated_at,
        budget_state.generated_at,
        *(item.generated_at for item in maturity_translations),
    )
    if result.generated_at < latest_input_time:
        raise DistributionAvailableCapacityV2Error("available capacity predates a current-state input artifact")
    return result
