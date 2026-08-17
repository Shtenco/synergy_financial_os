from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from .canonical_json import MAX_SAFE_JSON_INTEGER, canonical_json_digest
from .core import (
    AccountingInvariantError,
    distributable_profit,
    distribution_capacity,
    hard_nav_surplus_after_capital,
    liquidity_coverage_ratio,
    liquidity_surplus,
)
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import ReportingLedger
from .reporting_metrics import (
    net_new_capital_since,
    realized_external_pnl_since,
    realized_external_revenue_since,
)
from .valuation import ValuationPolicy


ZERO = Decimal("0")
POLICY_MODES = frozenset({"GROWTH", "NORMAL", "DEFENSE", "EMERGENCY"})
REQUIRED_LIQUIDITY_HORIZONS = (1, 4, 8)
SIGNED_DECIMAL_FIELDS = (
    "hard_nav",
    "liquid_nav",
    "economic_nav",
    "net_new_capital",
    "realized_external_pnl",
    "hard_nav_surplus_after_capital",
)
NONNEGATIVE_DECIMAL_FIELDS = (
    "hard_external_assets",
    "external_liabilities",
    "immediate_external_liabilities",
    "realized_external_revenue",
    "required_retention",
    "loss_carryforward",
    "period_profit_budget",
    "required_hard_nav_buffer",
    "distribution_capacity",
)


def _d(value: Decimal | int | str, field_name: str = "value") -> Decimal:
    return finite_decimal(value, field_name)


def _decimal_text(value: Decimal, field_name: str = "value") -> str:
    return canonical_decimal_text(value, field_name)


def _canonical_digest(payload: Any) -> str:
    return canonical_json_digest(payload)


def _require_hex64(value: str, field_name: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise AccountingInvariantError(f"{field_name} must be a 64-character hex digest")
    return normalized


def _require_safe_nonnegative_integer(value: int, field_name: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > MAX_SAFE_JSON_INTEGER
    ):
        raise AccountingInvariantError(
            f"{field_name} must be a non-negative cross-language safe integer"
        )
    return value


@dataclass(frozen=True)
class LiquidityHorizonState:
    horizon_weeks: int
    liquid_resources: Decimal
    expected_net_outflows: Decimal

    def __post_init__(self) -> None:
        if self.horizon_weeks not in REQUIRED_LIQUIDITY_HORIZONS:
            raise AccountingInvariantError("liquidity horizon must be 1, 4 or 8 weeks")
        resources = _d(self.liquid_resources, "liquid_resources")
        outflows = _d(self.expected_net_outflows, "expected_net_outflows")
        if resources < ZERO or outflows < ZERO:
            raise AccountingInvariantError(
                "liquid_resources and expected_net_outflows must be non-negative"
            )
        object.__setattr__(self, "liquid_resources", resources)
        object.__setattr__(self, "expected_net_outflows", outflows)

    @property
    def lcr(self) -> Decimal | None:
        return liquidity_coverage_ratio(self.liquid_resources, self.expected_net_outflows)

    @property
    def surplus(self) -> Decimal:
        return liquidity_surplus(self.liquid_resources, self.expected_net_outflows)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "horizon_weeks": self.horizon_weeks,
            "liquid_resources": _decimal_text(self.liquid_resources, "liquid_resources"),
            "expected_net_outflows": _decimal_text(
                self.expected_net_outflows,
                "expected_net_outflows",
            ),
            "lcr": None if self.lcr is None else _decimal_text(self.lcr, "lcr"),
            "liquidity_surplus": _decimal_text(self.surplus, "liquidity_surplus"),
        }


@dataclass(frozen=True)
class FinancialSnapshotV2:
    sequence: int
    as_of: datetime
    accounting_perimeter: str
    reporting_currency: str
    ledger_digest: str
    ledger_last_entry_digest: str
    account_registry_digest: str
    valuation_policy_id: str
    valuation_policy_digest: str
    valuation_policy_as_of: datetime
    period_start_sequence: int
    previous_snapshot_digest: str | None
    hard_external_assets: Decimal
    external_liabilities: Decimal
    immediate_external_liabilities: Decimal
    hard_nav: Decimal
    liquid_nav: Decimal
    economic_nav: Decimal
    hard_coverage: Decimal | None
    net_new_capital: Decimal
    realized_external_revenue: Decimal
    realized_external_pnl: Decimal
    hard_nav_surplus_after_capital: Decimal
    required_retention: Decimal
    loss_carryforward: Decimal
    period_profit_budget: Decimal
    required_hard_nav_buffer: Decimal
    distribution_capacity: Decimal
    liquidity_horizons: tuple[LiquidityHorizonState, ...]
    maturity_snapshot_refs: tuple[str, ...]
    policy_mode: str
    invariant_failures: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_safe_nonnegative_integer(self.sequence, "sequence")
        _require_safe_nonnegative_integer(self.period_start_sequence, "period_start_sequence")
        if self.period_start_sequence > self.sequence:
            raise AccountingInvariantError("period_start_sequence cannot exceed sequence")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise AccountingInvariantError("snapshot as_of must be timezone-aware")
        if self.valuation_policy_as_of.tzinfo is None or self.valuation_policy_as_of.utcoffset() is None:
            raise AccountingInvariantError("valuation_policy_as_of must be timezone-aware")
        if self.valuation_policy_as_of > self.as_of:
            raise AccountingInvariantError("valuation policy cannot be from the future")

        perimeter = self.accounting_perimeter.strip()
        currency = self.reporting_currency.upper().strip()
        policy_id = self.valuation_policy_id.strip()
        mode = self.policy_mode.upper().strip()
        if not perimeter or not currency or not policy_id:
            raise AccountingInvariantError(
                "accounting_perimeter, reporting_currency and valuation_policy_id are required"
            )
        if mode not in POLICY_MODES:
            raise AccountingInvariantError(f"invalid policy_mode: {mode}")

        object.__setattr__(self, "accounting_perimeter", perimeter)
        object.__setattr__(self, "reporting_currency", currency)
        object.__setattr__(self, "valuation_policy_id", policy_id)
        object.__setattr__(self, "policy_mode", mode)
        object.__setattr__(self, "ledger_digest", _require_hex64(self.ledger_digest, "ledger_digest"))
        object.__setattr__(
            self,
            "ledger_last_entry_digest",
            _require_hex64(self.ledger_last_entry_digest, "ledger_last_entry_digest"),
        )
        object.__setattr__(
            self,
            "account_registry_digest",
            _require_hex64(self.account_registry_digest, "account_registry_digest"),
        )
        object.__setattr__(
            self,
            "valuation_policy_digest",
            _require_hex64(self.valuation_policy_digest, "valuation_policy_digest"),
        )
        if self.previous_snapshot_digest is not None:
            object.__setattr__(
                self,
                "previous_snapshot_digest",
                _require_hex64(self.previous_snapshot_digest, "previous_snapshot_digest"),
            )

        for field_name in SIGNED_DECIMAL_FIELDS:
            object.__setattr__(
                self,
                field_name,
                _d(getattr(self, field_name), field_name),
            )
        for field_name in NONNEGATIVE_DECIMAL_FIELDS:
            value = _d(getattr(self, field_name), field_name)
            if value < ZERO:
                raise AccountingInvariantError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, value)
        if self.hard_coverage is not None:
            hard_coverage = _d(self.hard_coverage, "hard_coverage")
            if hard_coverage < ZERO:
                raise AccountingInvariantError("hard_coverage must be non-negative")
            object.__setattr__(self, "hard_coverage", hard_coverage)

        if self.immediate_external_liabilities > self.external_liabilities:
            raise AccountingInvariantError(
                "immediate_external_liabilities cannot exceed external_liabilities"
            )
        expected_hard_nav = self.hard_external_assets - self.external_liabilities
        if self.hard_nav != expected_hard_nav:
            raise AccountingInvariantError(
                f"hard_nav mismatch: expected {expected_hard_nav}, got {self.hard_nav}"
            )
        if not self.hard_nav <= self.liquid_nav <= self.economic_nav:
            raise AccountingInvariantError("NAV tiers must satisfy hard_nav <= liquid_nav <= economic_nav")

        if self.external_liabilities == ZERO:
            if self.hard_coverage is not None:
                raise AccountingInvariantError(
                    "hard_coverage must be null when external_liabilities is zero"
                )
        else:
            expected_coverage = self.hard_external_assets / self.external_liabilities
            if self.hard_coverage != expected_coverage:
                raise AccountingInvariantError(
                    f"hard_coverage mismatch: expected {expected_coverage}, got {self.hard_coverage}"
                )

        expected_profit_budget = distributable_profit(
            self.realized_external_pnl,
            required_retention=self.required_retention,
            loss_carryforward=self.loss_carryforward,
        )
        if self.period_profit_budget != expected_profit_budget:
            raise AccountingInvariantError(
                "period_profit_budget does not match realized P&L retention/loss policy"
            )
        expected_distribution_capacity = distribution_capacity(
            self.period_profit_budget,
            hard_nav=self.hard_nav,
            required_hard_nav_buffer=self.required_hard_nav_buffer,
        )
        if self.distribution_capacity != expected_distribution_capacity:
            raise AccountingInvariantError(
                "distribution_capacity does not match profit budget and HardNAV solvency headroom"
            )

        horizons = tuple(sorted(self.liquidity_horizons, key=lambda item: item.horizon_weeks))
        if tuple(item.horizon_weeks for item in horizons) != REQUIRED_LIQUIDITY_HORIZONS:
            raise AccountingInvariantError("snapshot requires exactly 1w, 4w and 8w liquidity horizons")
        object.__setattr__(self, "liquidity_horizons", horizons)

        refs = tuple(
            sorted(
                {
                    _require_hex64(ref, "maturity_snapshot_ref")
                    for ref in self.maturity_snapshot_refs
                }
            )
        )
        object.__setattr__(self, "maturity_snapshot_refs", refs)
        failures = tuple(sorted({item.strip() for item in self.invariant_failures if item.strip()}))
        object.__setattr__(self, "invariant_failures", failures)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "financial.snapshot/v2",
            "sequence": self.sequence,
            "as_of": self.as_of.isoformat(),
            "accounting_perimeter": self.accounting_perimeter,
            "reporting_currency": self.reporting_currency,
            "ledger_digest": self.ledger_digest,
            "ledger_last_entry_digest": self.ledger_last_entry_digest,
            "account_registry_digest": self.account_registry_digest,
            "valuation_policy_id": self.valuation_policy_id,
            "valuation_policy_digest": self.valuation_policy_digest,
            "valuation_policy_as_of": self.valuation_policy_as_of.isoformat(),
            "period_start_sequence": self.period_start_sequence,
            "previous_snapshot_digest": self.previous_snapshot_digest,
            "hard_external_assets": _decimal_text(self.hard_external_assets, "hard_external_assets"),
            "external_liabilities": _decimal_text(self.external_liabilities, "external_liabilities"),
            "immediate_external_liabilities": _decimal_text(
                self.immediate_external_liabilities,
                "immediate_external_liabilities",
            ),
            "hard_nav": _decimal_text(self.hard_nav, "hard_nav"),
            "liquid_nav": _decimal_text(self.liquid_nav, "liquid_nav"),
            "economic_nav": _decimal_text(self.economic_nav, "economic_nav"),
            "hard_coverage": (
                None
                if self.hard_coverage is None
                else _decimal_text(self.hard_coverage, "hard_coverage")
            ),
            "net_new_capital": _decimal_text(self.net_new_capital, "net_new_capital"),
            "realized_external_revenue": _decimal_text(
                self.realized_external_revenue,
                "realized_external_revenue",
            ),
            "realized_external_pnl": _decimal_text(
                self.realized_external_pnl,
                "realized_external_pnl",
            ),
            "hard_nav_surplus_after_capital": _decimal_text(
                self.hard_nav_surplus_after_capital,
                "hard_nav_surplus_after_capital",
            ),
            "required_retention": _decimal_text(self.required_retention, "required_retention"),
            "loss_carryforward": _decimal_text(self.loss_carryforward, "loss_carryforward"),
            "period_profit_budget": _decimal_text(self.period_profit_budget, "period_profit_budget"),
            "required_hard_nav_buffer": _decimal_text(
                self.required_hard_nav_buffer,
                "required_hard_nav_buffer",
            ),
            "distribution_capacity": _decimal_text(
                self.distribution_capacity,
                "distribution_capacity",
            ),
            "liquidity_horizons": [item.canonical_dict() for item in self.liquidity_horizons],
            "maturity_snapshot_refs": list(self.maturity_snapshot_refs),
            "policy_mode": self.policy_mode,
            "invariant_failures": list(self.invariant_failures),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.canonical_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical_dict()
        payload["digest"] = self.digest
        return payload


def capture_financial_snapshot_v2(
    ledger: ReportingLedger,
    valuation_policy: ValuationPolicy,
    *,
    as_of: datetime,
    accounting_perimeter: str,
    liquidity_horizons: Iterable[LiquidityHorizonState],
    previous_snapshot: FinancialSnapshotV2 | None = None,
    required_retention: Decimal | int | str = ZERO,
    loss_carryforward: Decimal | int | str = ZERO,
    required_hard_nav_buffer: Decimal | int | str = ZERO,
    maturity_snapshot_refs: Iterable[str] = (),
    policy_mode: str = "NORMAL",
    invariant_failures: Iterable[str] = (),
) -> FinancialSnapshotV2:
    """Capture a deterministic FinancialSnapshot v2 from the reporting ledger.

    Measurement is separated from policy authorization. The caller supplies
    liquidity-horizon inputs and policy status; this function computes the
    accounting state, period P&L/budgets and cryptographic bindings.
    """

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise AccountingInvariantError("snapshot as_of must be timezone-aware")
    if valuation_policy.reporting_currency != ledger.reporting_currency:
        raise AccountingInvariantError(
            "valuation policy reporting currency must match reporting ledger"
        )
    if valuation_policy.as_of > as_of:
        raise AccountingInvariantError("valuation policy cannot be from the future")

    perimeter = accounting_perimeter.strip()
    if not perimeter:
        raise AccountingInvariantError("accounting_perimeter is required")

    if previous_snapshot is None:
        period_start_sequence = 0
        previous_hard_nav = ZERO
        previous_digest = None
    else:
        if previous_snapshot.sequence > ledger.sequence:
            raise AccountingInvariantError("previous snapshot sequence exceeds ledger sequence")
        if previous_snapshot.as_of > as_of:
            raise AccountingInvariantError("previous snapshot cannot be from the future")
        if previous_snapshot.reporting_currency != ledger.reporting_currency:
            raise AccountingInvariantError("reporting currency changed across snapshot chain")
        if previous_snapshot.accounting_perimeter != perimeter:
            raise AccountingInvariantError("accounting perimeter changed across snapshot chain")
        period_start_sequence = previous_snapshot.sequence
        previous_hard_nav = previous_snapshot.hard_nav
        previous_digest = previous_snapshot.digest

    retention = _d(required_retention, "required_retention")
    loss_cf = _d(loss_carryforward, "loss_carryforward")
    hard_buffer = _d(required_hard_nav_buffer, "required_hard_nav_buffer")
    if retention < ZERO or loss_cf < ZERO or hard_buffer < ZERO:
        raise AccountingInvariantError(
            "required_retention, loss_carryforward and required_hard_nav_buffer must be non-negative"
        )

    ledger.assert_balanced()
    state = ledger.financial_state(valuation_policy.rule_map)
    immediate_liabilities = ledger.immediate_external_liabilities()
    net_capital = net_new_capital_since(
        ledger,
        period_start_sequence,
        valuation_policy.rule_map,
    )
    external_revenue = realized_external_revenue_since(ledger, period_start_sequence)
    external_pnl = realized_external_pnl_since(ledger, period_start_sequence)
    diagnostic_surplus = hard_nav_surplus_after_capital(
        previous_hard_nav,
        state.hard_nav,
        net_capital,
    )
    profit_budget = distributable_profit(
        external_pnl,
        required_retention=retention,
        loss_carryforward=loss_cf,
    )
    distributable_capacity = distribution_capacity(
        profit_budget,
        hard_nav=state.hard_nav,
        required_hard_nav_buffer=hard_buffer,
    )
    hard_coverage = (
        None
        if state.external_liabilities == ZERO
        else state.hard_external_assets / state.external_liabilities
    )

    return FinancialSnapshotV2(
        sequence=ledger.sequence,
        as_of=as_of,
        accounting_perimeter=perimeter,
        reporting_currency=ledger.reporting_currency,
        ledger_digest=ledger.digest,
        ledger_last_entry_digest=ledger.last_entry_digest,
        account_registry_digest=ledger.account_registry_digest,
        valuation_policy_id=valuation_policy.policy_id,
        valuation_policy_digest=valuation_policy.digest,
        valuation_policy_as_of=valuation_policy.as_of,
        period_start_sequence=period_start_sequence,
        previous_snapshot_digest=previous_digest,
        hard_external_assets=state.hard_external_assets,
        external_liabilities=state.external_liabilities,
        immediate_external_liabilities=immediate_liabilities,
        hard_nav=state.hard_nav,
        liquid_nav=state.liquid_nav,
        economic_nav=state.economic_nav,
        hard_coverage=hard_coverage,
        net_new_capital=net_capital,
        realized_external_revenue=external_revenue,
        realized_external_pnl=external_pnl,
        hard_nav_surplus_after_capital=diagnostic_surplus,
        required_retention=retention,
        loss_carryforward=loss_cf,
        period_profit_budget=profit_budget,
        required_hard_nav_buffer=hard_buffer,
        distribution_capacity=distributable_capacity,
        liquidity_horizons=tuple(liquidity_horizons),
        maturity_snapshot_refs=tuple(maturity_snapshot_refs),
        policy_mode=policy_mode,
        invariant_failures=tuple(invariant_failures),
    )
