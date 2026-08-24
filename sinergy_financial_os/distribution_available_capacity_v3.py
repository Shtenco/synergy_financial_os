from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_available_capacity_v2 import build_distribution_available_capacity_v2
from .distribution_budget_state_v2 import DistributionBudgetStateV2
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from .liquidity_current_resources_v1 import LiquidityCurrentResourcesV1
from .liquidity_policy_v1 import LiquidityPolicyV1
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .numeric import canonical_decimal_text, finite_decimal

SCHEMA = "distribution.available-capacity/v3"
BUDGET_STATE_SCHEMA = "distribution.budget-state/v2"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
HORIZONS = (1, 4, 8)


class DistributionAvailableCapacityV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionAvailableCapacityV3Error(f"{name} is required")
    return value.strip()


def _hex64(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if len(value) != 64 or any(ch not in HEX for ch in value):
        raise DistributionAvailableCapacityV3Error(f"{name} must be hex64")
    return value


def _amount(value: Any, name: str, *, allow_negative: bool = False) -> Decimal:
    result = finite_decimal(value, name)
    if not allow_negative and result < ZERO:
        raise DistributionAvailableCapacityV3Error(f"{name} must be non-negative")
    return result


@dataclass(frozen=True)
class DistributionAvailableCapacityV3:
    capacity_id: str
    affected_period_id: str
    base_distribution_capacity_replay_digest: str
    distribution_budget_state_schema: str
    distribution_budget_state_digest: str
    current_financial_snapshot_digest: str
    current_accounting_close_digest: str
    current_liquidity_resources_digest: str
    liquidity_policy_digest: str
    maturity_snapshot_digests: tuple[str, ...]
    maturity_translation_digests: tuple[str, ...]
    reporting_currency: str
    current_snapshot_sequence: int
    current_snapshot_ledger_digest: str
    gross_period_profit_budget: Decimal
    post_close_settlement_fee_expenses: Decimal
    fee_adjusted_period_profit_budget: Decimal
    canonical_distribution_outflows: Decimal
    canonical_distribution_reversals: Decimal
    net_consumed_distribution_budget: Decimal
    remaining_period_profit_budget: Decimal
    current_hard_nav: Decimal
    current_required_hard_nav_buffer: Decimal
    current_solvency_headroom: Decimal
    current_liquidity_distribution_capacity: Decimal
    final_available_capacity: Decimal
    horizon_headrooms: tuple[DistributionLiquidityHeadroomV1, ...]
    blockers: tuple[str, ...]
    status: str
    generated_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V3"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.distribution_budget_state_schema != BUDGET_STATE_SCHEMA:
            raise DistributionAvailableCapacityV3Error("v3 requires distribution.budget-state/v2")
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V3":
            raise DistributionAvailableCapacityV3Error("available capacity authority mismatch")
        if any(value != "NONE" for value in (
            self.authorization_authority,
            self.payment_authority,
            self.execution_authority,
            self.ai_authority,
        )):
            raise DistributionAvailableCapacityV3Error("available capacity cannot authorize, pay, execute or delegate to AI")
        object.__setattr__(self, "capacity_id", _text(self.capacity_id, "capacity_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in (
            "base_distribution_capacity_replay_digest",
            "distribution_budget_state_digest",
            "current_financial_snapshot_digest",
            "current_accounting_close_digest",
            "current_liquidity_resources_digest",
            "liquidity_policy_digest",
            "current_snapshot_ledger_digest",
        ):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if isinstance(self.current_snapshot_sequence, bool) or not isinstance(self.current_snapshot_sequence, int) or self.current_snapshot_sequence < 1:
            raise DistributionAvailableCapacityV3Error("current_snapshot_sequence must be a positive integer")
        for name in (
            "gross_period_profit_budget",
            "post_close_settlement_fee_expenses",
            "fee_adjusted_period_profit_budget",
            "canonical_distribution_outflows",
            "canonical_distribution_reversals",
            "net_consumed_distribution_budget",
            "remaining_period_profit_budget",
            "current_required_hard_nav_buffer",
            "current_solvency_headroom",
            "current_liquidity_distribution_capacity",
            "final_available_capacity",
        ):
            object.__setattr__(self, name, _amount(getattr(self, name), name))
        object.__setattr__(self, "current_hard_nav", _amount(self.current_hard_nav, "current_hard_nav", allow_negative=True))
        if self.canonical_distribution_reversals > self.canonical_distribution_outflows:
            raise DistributionAvailableCapacityV3Error("distribution reversals exceed outflows")
        if self.net_consumed_distribution_budget != self.canonical_distribution_outflows - self.canonical_distribution_reversals:
            raise DistributionAvailableCapacityV3Error("net consumed distribution budget mismatch")
        expected_adjusted = max(ZERO, self.gross_period_profit_budget - self.post_close_settlement_fee_expenses)
        if self.fee_adjusted_period_profit_budget != expected_adjusted:
            raise DistributionAvailableCapacityV3Error("fee-adjusted profit budget mismatch")
        expected_remaining = max(ZERO, expected_adjusted - self.net_consumed_distribution_budget)
        if self.remaining_period_profit_budget != expected_remaining:
            raise DistributionAvailableCapacityV3Error("remaining period profit budget mismatch")
        if self.current_solvency_headroom != max(ZERO, self.current_hard_nav - self.current_required_hard_nav_buffer):
            raise DistributionAvailableCapacityV3Error("current solvency headroom mismatch")
        headrooms = tuple(sorted(self.horizon_headrooms, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in headrooms) != HORIZONS:
            raise DistributionAvailableCapacityV3Error("v3 requires exactly 1w/4w/8w liquidity headrooms")
        object.__setattr__(self, "horizon_headrooms", headrooms)
        expected_liquidity = min(item.horizon_distribution_capacity for item in headrooms)
        if self.current_liquidity_distribution_capacity != expected_liquidity:
            raise DistributionAvailableCapacityV3Error("current liquidity distribution capacity mismatch")
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected_final = ZERO if blockers else min(
            self.remaining_period_profit_budget,
            self.current_solvency_headroom,
            self.current_liquidity_distribution_capacity,
        )
        if self.final_available_capacity != expected_final:
            raise DistributionAvailableCapacityV3Error("final available capacity mismatch")
        expected_status = "CAPACITY_AVAILABLE" if expected_final > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionAvailableCapacityV3Error("available capacity status mismatch")
        snapshots = tuple(sorted(_hex64(item, "maturity_snapshot_digest") for item in self.maturity_snapshot_digests))
        translations = tuple(sorted(_hex64(item, "maturity_translation_digest") for item in self.maturity_translation_digests))
        if not snapshots or len(snapshots) != len(set(snapshots)):
            raise DistributionAvailableCapacityV3Error("maturity snapshot digests must be non-empty and unique")
        if len(translations) != len(set(translations)) or len(translations) != len(snapshots):
            raise DistributionAvailableCapacityV3Error("maturity translation cardinality mismatch")
        object.__setattr__(self, "maturity_snapshot_digests", snapshots)
        object.__setattr__(self, "maturity_translation_digests", translations)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA,
            "capacity_id": self.capacity_id,
            "affected_period_id": self.affected_period_id,
            "base_distribution_capacity_replay_digest": self.base_distribution_capacity_replay_digest,
            "distribution_budget_state_schema": self.distribution_budget_state_schema,
            "distribution_budget_state_digest": self.distribution_budget_state_digest,
            "current_financial_snapshot_digest": self.current_financial_snapshot_digest,
            "current_accounting_close_digest": self.current_accounting_close_digest,
            "current_liquidity_resources_digest": self.current_liquidity_resources_digest,
            "liquidity_policy_digest": self.liquidity_policy_digest,
            "maturity_snapshot_digests": list(self.maturity_snapshot_digests),
            "maturity_translation_digests": list(self.maturity_translation_digests),
            "reporting_currency": self.reporting_currency,
            "current_snapshot_sequence": self.current_snapshot_sequence,
            "current_snapshot_ledger_digest": self.current_snapshot_ledger_digest,
            "gross_period_profit_budget": canonical_decimal_text(self.gross_period_profit_budget),
            "post_close_settlement_fee_expenses": canonical_decimal_text(self.post_close_settlement_fee_expenses),
            "fee_adjusted_period_profit_budget": canonical_decimal_text(self.fee_adjusted_period_profit_budget),
            "canonical_distribution_outflows": canonical_decimal_text(self.canonical_distribution_outflows),
            "canonical_distribution_reversals": canonical_decimal_text(self.canonical_distribution_reversals),
            "net_consumed_distribution_budget": canonical_decimal_text(self.net_consumed_distribution_budget),
            "remaining_period_profit_budget": canonical_decimal_text(self.remaining_period_profit_budget),
            "current_hard_nav": canonical_decimal_text(self.current_hard_nav),
            "current_required_hard_nav_buffer": canonical_decimal_text(self.current_required_hard_nav_buffer),
            "current_solvency_headroom": canonical_decimal_text(self.current_solvency_headroom),
            "current_liquidity_distribution_capacity": canonical_decimal_text(self.current_liquidity_distribution_capacity),
            "final_available_capacity": canonical_decimal_text(self.final_available_capacity),
            "horizon_headrooms": [item.to_dict() for item in self.horizon_headrooms],
            "blockers": list(self.blockers),
            "status": self.status,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
            "ai_authority": self.ai_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_available_capacity_v3(
    *,
    capacity_id: str,
    base_capacity: DistributionCapacityReplayV1,
    budget_state: DistributionBudgetStateV2,
    current_financial_snapshot: Mapping[str, Any],
    current_accounting_close: AccountingCloseV2,
    current_sealed_ledger_events: Sequence[Mapping[str, Any]],
    current_liquidity_resources: LiquidityCurrentResourcesV1,
    liquidity_policy: LiquidityPolicyV1,
    maturity_snapshots: Sequence[Mapping[str, Any]],
    maturity_translations: Sequence[MaturityTranslationArtifactV1],
    generated_at: datetime,
) -> DistributionAvailableCapacityV3:
    if not isinstance(budget_state, DistributionBudgetStateV2):
        raise DistributionAvailableCapacityV3Error("v3 path requires DistributionBudgetStateV2; v1 is not accepted")
    legacy_calculation = build_distribution_available_capacity_v2(
        capacity_id=f"{capacity_id}:v2-math-kernel",
        base_capacity=base_capacity,
        budget_state=budget_state,  # runtime-compatible field superset; v3 pins the schema explicitly below
        current_financial_snapshot=current_financial_snapshot,
        current_accounting_close=current_accounting_close,
        current_sealed_ledger_events=current_sealed_ledger_events,
        current_liquidity_resources=current_liquidity_resources,
        liquidity_policy=liquidity_policy,
        maturity_snapshots=maturity_snapshots,
        maturity_translations=maturity_translations,
        generated_at=generated_at,
    )
    if legacy_calculation.distribution_budget_state_digest != budget_state.digest:
        raise DistributionAvailableCapacityV3Error("v2 calculation kernel did not bind the exact v2 budget state")
    return DistributionAvailableCapacityV3(
        capacity_id=capacity_id,
        affected_period_id=legacy_calculation.affected_period_id,
        base_distribution_capacity_replay_digest=legacy_calculation.base_distribution_capacity_replay_digest,
        distribution_budget_state_schema=BUDGET_STATE_SCHEMA,
        distribution_budget_state_digest=budget_state.digest,
        current_financial_snapshot_digest=legacy_calculation.current_financial_snapshot_digest,
        current_accounting_close_digest=legacy_calculation.current_accounting_close_digest,
        current_liquidity_resources_digest=legacy_calculation.current_liquidity_resources_digest,
        liquidity_policy_digest=legacy_calculation.liquidity_policy_digest,
        maturity_snapshot_digests=legacy_calculation.maturity_snapshot_digests,
        maturity_translation_digests=legacy_calculation.maturity_translation_digests,
        reporting_currency=legacy_calculation.reporting_currency,
        current_snapshot_sequence=legacy_calculation.current_snapshot_sequence,
        current_snapshot_ledger_digest=legacy_calculation.current_snapshot_ledger_digest,
        gross_period_profit_budget=budget_state.gross_period_profit_budget,
        post_close_settlement_fee_expenses=budget_state.post_close_settlement_fee_expenses,
        fee_adjusted_period_profit_budget=budget_state.fee_adjusted_period_profit_budget,
        canonical_distribution_outflows=budget_state.canonical_distribution_outflows,
        canonical_distribution_reversals=budget_state.canonical_distribution_reversals,
        net_consumed_distribution_budget=budget_state.net_consumed_distribution_budget,
        remaining_period_profit_budget=budget_state.remaining_period_profit_budget,
        current_hard_nav=legacy_calculation.current_hard_nav,
        current_required_hard_nav_buffer=legacy_calculation.current_required_hard_nav_buffer,
        current_solvency_headroom=legacy_calculation.current_solvency_headroom,
        current_liquidity_distribution_capacity=legacy_calculation.current_liquidity_distribution_capacity,
        final_available_capacity=legacy_calculation.final_available_capacity,
        horizon_headrooms=legacy_calculation.horizon_headrooms,
        blockers=legacy_calculation.blockers,
        status=legacy_calculation.status,
        generated_at=legacy_calculation.generated_at,
    )


def verify_distribution_available_capacity_v3_payload(payload: Mapping[str, Any]) -> bool:
    if payload.get("schema") != SCHEMA or payload.get("distribution_budget_state_schema") != BUDGET_STATE_SCHEMA:
        return False
    candidate = dict(payload)
    supplied_digest = candidate.pop("digest", None)
    if supplied_digest != canonical_json_digest(candidate):
        return False
    if candidate.get("authority") != "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V3":
        return False
    if any(candidate.get(name) != "NONE" for name in (
        "authorization_authority", "payment_authority", "execution_authority", "ai_authority"
    )):
        return False
    try:
        gross = _amount(candidate["gross_period_profit_budget"], "gross_period_profit_budget")
        fee = _amount(candidate["post_close_settlement_fee_expenses"], "post_close_settlement_fee_expenses")
        adjusted = _amount(candidate["fee_adjusted_period_profit_budget"], "fee_adjusted_period_profit_budget")
        outflows = _amount(candidate["canonical_distribution_outflows"], "canonical_distribution_outflows")
        reversals = _amount(candidate["canonical_distribution_reversals"], "canonical_distribution_reversals")
        net = _amount(candidate["net_consumed_distribution_budget"], "net_consumed_distribution_budget")
        remaining = _amount(candidate["remaining_period_profit_budget"], "remaining_period_profit_budget")
        hard_nav = _amount(candidate["current_hard_nav"], "current_hard_nav", allow_negative=True)
        buffer = _amount(candidate["current_required_hard_nav_buffer"], "current_required_hard_nav_buffer")
        solvency = _amount(candidate["current_solvency_headroom"], "current_solvency_headroom")
        liquidity = _amount(candidate["current_liquidity_distribution_capacity"], "current_liquidity_distribution_capacity")
        final = _amount(candidate["final_available_capacity"], "final_available_capacity")
    except (KeyError, AccountingInvariantError, ValueError, TypeError):
        return False
    if reversals > outflows or net != outflows - reversals:
        return False
    if adjusted != max(ZERO, gross - fee):
        return False
    if remaining != max(ZERO, adjusted - net):
        return False
    if solvency != max(ZERO, hard_nav - buffer):
        return False
    blockers = candidate.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
        return False
    expected_final = ZERO if blockers else min(remaining, solvency, liquidity)
    if final != expected_final:
        return False
    return candidate.get("status") == ("CAPACITY_AVAILABLE" if final > ZERO and not blockers else "NO_ACTION")
