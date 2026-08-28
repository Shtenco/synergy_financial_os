from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .accounting_close_v2 import AccountingCloseV2, verify_accounting_close_v2, verify_financial_snapshot_v2_payload
from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_budget_state_v1 import DistributionBudgetStateV1
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from .liquidity_current_resources_v1 import LiquidityCurrentResourcesV1
from .liquidity_policy_v1 import LiquidityPolicyV1
from .maturity_bridge import translate_maturity_outflows, verify_maturity_snapshot_digest
from .maturity_translation_v1 import MaturityTranslationArtifactV1
from .numeric import canonical_decimal_text, finite_decimal


SCHEMA = "distribution.available-capacity/v2"
HORIZONS = (1, 4, 8)
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class DistributionAvailableCapacityV2Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionAvailableCapacityV2Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionAvailableCapacityV2Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionAvailableCapacityV2Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _snapshot_time(snapshot: Mapping[str, Any]) -> datetime:
    text = _text(snapshot.get("as_of"), "snapshot.as_of")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DistributionAvailableCapacityV2Error("snapshot.as_of is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DistributionAvailableCapacityV2Error("snapshot.as_of must be timezone-aware")
    return parsed.astimezone(UTC)


def _snapshot_liquidity(snapshot: Mapping[str, Any]) -> dict[int, tuple[Decimal, Decimal]]:
    raw = snapshot.get("liquidity_horizons")
    if not isinstance(raw, list) or len(raw) != 3:
        raise DistributionAvailableCapacityV2Error("current FinancialSnapshot requires 1w/4w/8w liquidity horizons")
    result: dict[int, tuple[Decimal, Decimal]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise DistributionAvailableCapacityV2Error("snapshot liquidity horizon must be object")
        horizon = item.get("horizon_weeks")
        if isinstance(horizon, bool) or horizon not in HORIZONS or horizon in result:
            raise DistributionAvailableCapacityV2Error("snapshot liquidity horizons must be unique 1w/4w/8w")
        resources = finite_decimal(item.get("liquid_resources"), "snapshot liquid_resources")
        outflows = finite_decimal(item.get("expected_net_outflows"), "snapshot expected_net_outflows")
        if resources < ZERO or outflows < ZERO:
            raise DistributionAvailableCapacityV2Error("snapshot liquidity values must be non-negative")
        result[horizon] = (resources, outflows)
    if tuple(sorted(result)) != HORIZONS:
        raise DistributionAvailableCapacityV2Error("snapshot liquidity horizons incomplete")
    return result


@dataclass(frozen=True)
class DistributionAvailableCapacityV2:
    capacity_id: str
    affected_period_id: str
    base_distribution_capacity_replay_digest: str
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
    authority: str = "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V2"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_AVAILABLE_CAPACITY_V2":
            raise DistributionAvailableCapacityV2Error("available capacity authority mismatch")
        if any(value != "NONE" for value in (self.authorization_authority, self.payment_authority, self.execution_authority, self.ai_authority)):
            raise DistributionAvailableCapacityV2Error("available capacity cannot authorize, pay, execute or delegate to AI")
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
            raise DistributionAvailableCapacityV2Error("current_snapshot_sequence must be positive integer")
        for name in (
            "remaining_period_profit_budget",
            "current_required_hard_nav_buffer",
            "current_solvency_headroom",
            "current_liquidity_distribution_capacity",
            "final_available_capacity",
        ):
            value = finite_decimal(getattr(self, name), name)
            if value < ZERO:
                raise DistributionAvailableCapacityV2Error(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        hard_nav = finite_decimal(self.current_hard_nav, "current_hard_nav")
        object.__setattr__(self, "current_hard_nav", hard_nav)
        if self.current_solvency_headroom != max(ZERO, hard_nav - self.current_required_hard_nav_buffer):
            raise DistributionAvailableCapacityV2Error("current solvency headroom mismatch")
        horizons = tuple(sorted(self.horizon_headrooms, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in horizons) != HORIZONS:
            raise DistributionAvailableCapacityV2Error("available capacity requires exactly 1w/4w/8w headrooms")
        object.__setattr__(self, "horizon_headrooms", horizons)
        expected_liquidity = min(item.horizon_distribution_capacity for item in horizons)
        if self.current_liquidity_distribution_capacity != expected_liquidity:
            raise DistributionAvailableCapacityV2Error("current liquidity distribution capacity mismatch")
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected_final = ZERO if blockers else min(
            self.remaining_period_profit_budget,
            self.current_solvency_headroom,
            self.current_liquidity_distribution_capacity,
        )
        if self.final_available_capacity != expected_final:
            raise DistributionAvailableCapacityV2Error("final available distribution capacity mismatch")
        expected_status = "CAPACITY_AVAILABLE" if expected_final > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionAvailableCapacityV2Error("available capacity status mismatch")
        snapshots = tuple(_hex64(item, "maturity_snapshot_digest") for item in self.maturity_snapshot_digests)
        translations = tuple(_hex64(item, "maturity_translation_digest") for item in self.maturity_translation_digests)
        if not snapshots or len(snapshots) != len(set(snapshots)):
            raise DistributionAvailableCapacityV2Error("maturity snapshot digests must be unique and non-empty")
        if len(translations) != len(set(translations)) or len(translations) != len(snapshots):
            raise DistributionAvailableCapacityV2Error("maturity translation digest cardinality mismatch")
        object.__setattr__(self, "maturity_snapshot_digests", tuple(sorted(snapshots)))
        object.__setattr__(self, "maturity_translation_digests", tuple(sorted(translations)))
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "capacity_id": self.capacity_id,
            "affected_period_id": self.affected_period_id,
            "base_distribution_capacity_replay_digest": self.base_distribution_capacity_replay_digest,
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


def build_distribution_available_capacity_v2(
    *,
    capacity_id: str,
    base_capacity: DistributionCapacityReplayV1,
    budget_state: DistributionBudgetStateV1,
    current_financial_snapshot: Mapping[str, Any],
    current_accounting_close: AccountingCloseV2,
    current_sealed_ledger_events: Sequence[Mapping[str, Any]],
    current_liquidity_resources: LiquidityCurrentResourcesV1,
    liquidity_policy: LiquidityPolicyV1,
    maturity_snapshots: Sequence[Mapping[str, Any]],
    maturity_translations: Sequence[MaturityTranslationArtifactV1],
    generated_at: datetime,
) -> DistributionAvailableCapacityV2:
    snapshot = verify_financial_snapshot_v2_payload(current_financial_snapshot)
    verify_accounting_close_v2(current_sealed_ledger_events, snapshot, current_accounting_close)
    if current_accounting_close.financial_snapshot_digest != snapshot["digest"]:
        raise DistributionAvailableCapacityV2Error("current AccountingClose / FinancialSnapshot mismatch")
    if budget_state.base_distribution_capacity_replay_digest != base_capacity.digest:
        raise DistributionAvailableCapacityV2Error("budget state / base capacity mismatch")
    if budget_state.affected_period_id != base_capacity.affected_period_id:
        raise DistributionAvailableCapacityV2Error("budget state affected period mismatch")
    if budget_state.ledger_sequence != snapshot["sequence"] or budget_state.ledger_digest != snapshot["ledger_digest"]:
        raise DistributionAvailableCapacityV2Error("budget state is stale relative to current closed ledger")
    if current_liquidity_resources.financial_snapshot_digest != snapshot["digest"]:
        raise DistributionAvailableCapacityV2Error("current liquidity resources / FinancialSnapshot mismatch")
    if current_liquidity_resources.accounting_close_digest != current_accounting_close.digest:
        raise DistributionAvailableCapacityV2Error("current liquidity resources / AccountingClose mismatch")
    if current_liquidity_resources.snapshot_sequence != snapshot["sequence"] or current_liquidity_resources.snapshot_ledger_digest != snapshot["ledger_digest"]:
        raise DistributionAvailableCapacityV2Error("current liquidity resources ledger binding mismatch")
    currency = _text(snapshot.get("reporting_currency"), "snapshot.reporting_currency").upper()
    if budget_state.reporting_currency != currency or current_liquidity_resources.reporting_currency != currency:
        raise DistributionAvailableCapacityV2Error("distribution budget/current liquidity reporting currency mismatch")
    if liquidity_policy.reporting_currency != currency:
        raise DistributionAvailableCapacityV2Error("LiquidityPolicy reporting currency mismatch")
    if current_liquidity_resources.liquidity_policy_digest != liquidity_policy.digest:
        raise DistributionAvailableCapacityV2Error("current liquidity resources / LiquidityPolicy mismatch")
    as_of = _snapshot_time(snapshot)
    if current_liquidity_resources.as_of != as_of:
        raise DistributionAvailableCapacityV2Error("current liquidity resources as_of mismatch")
    if liquidity_policy.as_of > as_of:
        raise DistributionAvailableCapacityV2Error("LiquidityPolicy cannot be from the future")

    expected_refs = snapshot.get("maturity_snapshot_refs")
    if not isinstance(expected_refs, list) or not expected_refs:
        raise DistributionAvailableCapacityV2Error("current capacity requires non-empty maturity_snapshot_refs")
    supplied_snapshots: dict[str, Mapping[str, Any]] = {}
    for item in maturity_snapshots:
        digest = verify_maturity_snapshot_digest(item)
        if digest in supplied_snapshots:
            raise DistributionAvailableCapacityV2Error("duplicate maturity snapshot digest")
        supplied_snapshots[digest] = item
    if set(supplied_snapshots) != set(expected_refs):
        raise DistributionAvailableCapacityV2Error("supplied maturity snapshot set differs from current FinancialSnapshot refs")

    translation_by_snapshot: dict[str, MaturityTranslationArtifactV1] = {}
    for artifact in maturity_translations:
        if artifact.maturity_snapshot_digest in translation_by_snapshot:
            raise DistributionAvailableCapacityV2Error("duplicate maturity translation for snapshot")
        if artifact.reporting_currency != currency:
            raise DistributionAvailableCapacityV2Error("maturity translation reporting currency mismatch")
        if artifact.as_of != as_of:
            raise DistributionAvailableCapacityV2Error("v2 requires maturity translation as_of == current snapshot as_of")
        translation_by_snapshot[artifact.maturity_snapshot_digest] = artifact
    if set(translation_by_snapshot) != set(supplied_snapshots):
        raise DistributionAvailableCapacityV2Error("each current maturity snapshot requires exactly one translation")

    total_outflows = {horizon: ZERO for horizon in HORIZONS}
    for digest, maturity_snapshot in supplied_snapshots.items():
        raw_as_of = _text(maturity_snapshot.get("as_of"), "maturity snapshot as_of")
        maturity_as_of = datetime.fromisoformat(raw_as_of.replace("Z", "+00:00")).astimezone(UTC)
        if maturity_as_of != as_of:
            raise DistributionAvailableCapacityV2Error("v2 requires maturity snapshot as_of == current snapshot as_of")
        translated = translate_maturity_outflows(maturity_snapshot, translation_by_snapshot[digest].to_translation())
        for horizon in HORIZONS:
            total_outflows[horizon] += translated[horizon]

    snapshot_liquidity = _snapshot_liquidity(snapshot)
    resources = current_liquidity_resources.resources_by_horizon()
    for horizon in HORIZONS:
        snapshot_resources, snapshot_outflows = snapshot_liquidity[horizon]
        if resources[horizon] != snapshot_resources:
            raise DistributionAvailableCapacityV2Error("current resource evidence differs from closed snapshot liquidity resources")
        if total_outflows[horizon] != snapshot_outflows:
            raise DistributionAvailableCapacityV2Error("reconstructed maturity outflows differ from closed snapshot liquidity outflows")

    hard_nav = finite_decimal(snapshot.get("hard_nav"), "snapshot.hard_nav")
    hard_buffer = finite_decimal(snapshot.get("required_hard_nav_buffer"), "snapshot.required_hard_nav_buffer")
    if hard_buffer < ZERO:
        raise DistributionAvailableCapacityV2Error("current required HardNAV buffer must be non-negative")
    solvency_headroom = max(ZERO, hard_nav - hard_buffer)
    policy_by_horizon = liquidity_policy.by_horizon()
    headrooms: list[DistributionLiquidityHeadroomV1] = []
    for horizon in HORIZONS:
        resource = resources[horizon]
        outflow = total_outflows[horizon]
        rule = policy_by_horizon[horizon]
        lcr_headroom = resource if outflow == ZERO else resource - rule.minimum_lcr * outflow
        surplus_headroom = resource - outflow - rule.minimum_liquidity_surplus
        capacity = max(ZERO, min(resource, lcr_headroom, surplus_headroom))
        headrooms.append(
            DistributionLiquidityHeadroomV1(
                horizon_weeks=horizon,
                pre_distribution_resources=resource,
                expected_net_outflows=outflow,
                minimum_lcr=rule.minimum_lcr,
                minimum_liquidity_surplus=rule.minimum_liquidity_surplus,
                lcr_headroom=lcr_headroom,
                surplus_headroom=surplus_headroom,
                horizon_distribution_capacity=capacity,
            )
        )
    liquidity_capacity = min(item.horizon_distribution_capacity for item in headrooms)

    blockers = list(budget_state.blockers)
    invariant_failures = snapshot.get("invariant_failures")
    if not isinstance(invariant_failures, list) or any(not isinstance(item, str) for item in invariant_failures):
        raise DistributionAvailableCapacityV2Error("current snapshot invariant_failures must be string array")
    if invariant_failures:
        blockers.append("CURRENT_SNAPSHOT_INVARIANT_FAILURES")
    if budget_state.remaining_period_profit_budget <= ZERO:
        blockers.append("NO_REMAINING_PERIOD_BUDGET")
    if solvency_headroom <= ZERO:
        blockers.append("NO_CURRENT_HARDNAV_SOLVENCY_HEADROOM")
    if liquidity_capacity <= ZERO:
        blockers.append("NO_CURRENT_LIQUIDITY_DISTRIBUTION_HEADROOM")
    blockers = sorted(set(blockers))
    final = ZERO if blockers else min(budget_state.remaining_period_profit_budget, solvency_headroom, liquidity_capacity)
    generated = _utc(generated_at, "generated_at")
    latest = max(current_liquidity_resources.generated_at, liquidity_policy.generated_at, budget_state.generated_at)
    if generated < latest:
        raise DistributionAvailableCapacityV2Error("available capacity cannot predate its input artifacts")
    return DistributionAvailableCapacityV2(
        capacity_id=capacity_id,
        affected_period_id=base_capacity.affected_period_id,
        base_distribution_capacity_replay_digest=base_capacity.digest,
        distribution_budget_state_digest=budget_state.digest,
        current_financial_snapshot_digest=snapshot["digest"],
        current_accounting_close_digest=current_accounting_close.digest,
        current_liquidity_resources_digest=current_liquidity_resources.digest,
        liquidity_policy_digest=liquidity_policy.digest,
        maturity_snapshot_digests=tuple(supplied_snapshots),
        maturity_translation_digests=tuple(artifact.digest for artifact in maturity_translations),
        reporting_currency=currency,
        current_snapshot_sequence=snapshot["sequence"],
        current_snapshot_ledger_digest=snapshot["ledger_digest"],
        remaining_period_profit_budget=budget_state.remaining_period_profit_budget,
        current_hard_nav=hard_nav,
        current_required_hard_nav_buffer=hard_buffer,
        current_solvency_headroom=solvency_headroom,
        current_liquidity_distribution_capacity=liquidity_capacity,
        final_available_capacity=final,
        horizon_headrooms=tuple(headrooms),
        blockers=tuple(blockers),
        status="CAPACITY_AVAILABLE" if final > ZERO and not blockers else "NO_ACTION",
        generated_at=generated,
    )
