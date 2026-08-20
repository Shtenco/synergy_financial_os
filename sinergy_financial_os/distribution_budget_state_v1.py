from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingEntry, ReportingLedger


SCHEMA = "distribution.budget-state/v1"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")


class DistributionBudgetStateV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionBudgetStateV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise DistributionBudgetStateV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionBudgetStateV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _amount(value: Any, field_name: str, *, nonnegative: bool = True) -> Decimal:
    result = finite_decimal(value, field_name)
    if nonnegative and result < ZERO:
        raise DistributionBudgetStateV1Error(f"{field_name} must be non-negative")
    return result


def _external_account(ledger: ReportingLedger, entry: ReportingEntry, account_class: AccountClass):
    matches = []
    for line in entry.lines:
        spec = ledger.account(line.account_id)
        if spec.account_class == account_class and spec.consolidation_class == ConsolidationClass.EXTERNAL:
            matches.append((spec, line))
    return matches


def _distribution_amount(ledger: ReportingLedger, entry: ReportingEntry) -> Decimal:
    if entry.flow_type != FlowType.EXTERNAL_CAPITAL:
        raise DistributionBudgetStateV1Error("owner distribution must be EXTERNAL_CAPITAL")
    if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION":
        raise DistributionBudgetStateV1Error("owner distribution economic class mismatch")
    if entry.metadata.get("capital_direction") != "OUTFLOW":
        raise DistributionBudgetStateV1Error("owner distribution capital direction mismatch")
    if entry.metadata.get("pnl_treatment") != "EXCLUDED_FROM_REALIZED_PNL":
        raise DistributionBudgetStateV1Error("owner distribution P&L treatment mismatch")
    if len(entry.lines) != 2:
        raise DistributionBudgetStateV1Error("owner distribution must have exactly two reporting lines")
    assets = _external_account(ledger, entry, AccountClass.ASSET)
    equities = _external_account(ledger, entry, AccountClass.EQUITY)
    if len(assets) != 1 or len(equities) != 1:
        raise DistributionBudgetStateV1Error("owner distribution requires one external asset and one external equity line")
    _, asset_line = assets[0]
    _, equity_line = equities[0]
    if asset_line.debit != ZERO or asset_line.credit <= ZERO:
        raise DistributionBudgetStateV1Error("owner distribution external asset must be credited")
    if equity_line.credit != ZERO or equity_line.debit <= ZERO:
        raise DistributionBudgetStateV1Error("owner distribution external equity must be debited")
    if asset_line.credit != equity_line.debit:
        raise DistributionBudgetStateV1Error("owner distribution amount mismatch")
    return asset_line.credit


def _reversal_amount(ledger: ReportingLedger, entry: ReportingEntry) -> Decimal:
    if entry.flow_type != FlowType.EXTERNAL_CAPITAL:
        raise DistributionBudgetStateV1Error("owner distribution reversal must be EXTERNAL_CAPITAL")
    if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL":
        raise DistributionBudgetStateV1Error("owner distribution reversal economic class mismatch")
    if entry.metadata.get("capital_direction") != "INFLOW_REVERSAL_OF_PRIOR_OUTFLOW":
        raise DistributionBudgetStateV1Error("owner distribution reversal capital direction mismatch")
    if entry.metadata.get("pnl_treatment") != "EXCLUDED_FROM_REALIZED_PNL":
        raise DistributionBudgetStateV1Error("owner distribution reversal P&L treatment mismatch")
    if len(entry.lines) != 2:
        raise DistributionBudgetStateV1Error("owner distribution reversal must have exactly two reporting lines")
    assets = _external_account(ledger, entry, AccountClass.ASSET)
    equities = _external_account(ledger, entry, AccountClass.EQUITY)
    if len(assets) != 1 or len(equities) != 1:
        raise DistributionBudgetStateV1Error("owner distribution reversal requires one external asset and one external equity line")
    _, asset_line = assets[0]
    _, equity_line = equities[0]
    if asset_line.credit != ZERO or asset_line.debit <= ZERO:
        raise DistributionBudgetStateV1Error("owner distribution reversal external asset must be debited")
    if equity_line.debit != ZERO or equity_line.credit <= ZERO:
        raise DistributionBudgetStateV1Error("owner distribution reversal external equity must be credited")
    if asset_line.debit != equity_line.credit:
        raise DistributionBudgetStateV1Error("owner distribution reversal amount mismatch")
    return asset_line.debit


@dataclass(frozen=True)
class DistributionBudgetStateV1:
    state_id: str
    affected_period_id: str
    base_distribution_capacity_replay_digest: str
    base_statement_replay_digest: str
    reporting_currency: str
    ledger_sequence: int
    ledger_digest: str
    gross_period_profit_budget: Decimal
    canonical_distribution_outflows: Decimal
    canonical_distribution_reversals: Decimal
    net_consumed_distribution_budget: Decimal
    remaining_period_profit_budget: Decimal
    distribution_entry_digests: tuple[str, ...]
    reversal_entry_digests: tuple[str, ...]
    blockers: tuple[str, ...]
    status: str
    generated_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE":
            raise DistributionBudgetStateV1Error("distribution budget state authority mismatch")
        if any(value != "NONE" for value in (self.authorization_authority, self.payment_authority, self.execution_authority)):
            raise DistributionBudgetStateV1Error("distribution budget state cannot authorize, pay or execute")
        object.__setattr__(self, "state_id", _text(self.state_id, "state_id"))
        object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id"))
        object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in ("base_distribution_capacity_replay_digest", "base_statement_replay_digest", "ledger_digest"):
            object.__setattr__(self, name, _hex64(getattr(self, name), name))
        if isinstance(self.ledger_sequence, bool) or not isinstance(self.ledger_sequence, int) or self.ledger_sequence < 0:
            raise DistributionBudgetStateV1Error("ledger_sequence must be non-negative integer")
        for name in (
            "gross_period_profit_budget",
            "canonical_distribution_outflows",
            "canonical_distribution_reversals",
            "net_consumed_distribution_budget",
            "remaining_period_profit_budget",
        ):
            value = _amount(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if self.canonical_distribution_reversals > self.canonical_distribution_outflows:
            raise DistributionBudgetStateV1Error("distribution reversals cannot exceed distribution outflows")
        if self.net_consumed_distribution_budget != self.canonical_distribution_outflows - self.canonical_distribution_reversals:
            raise DistributionBudgetStateV1Error("net consumed distribution budget mismatch")
        expected_remaining = max(ZERO, self.gross_period_profit_budget - self.net_consumed_distribution_budget)
        if self.remaining_period_profit_budget != expected_remaining:
            raise DistributionBudgetStateV1Error("remaining period profit budget mismatch")
        distributions = tuple(_hex64(item, "distribution_entry_digest") for item in self.distribution_entry_digests)
        reversals = tuple(_hex64(item, "reversal_entry_digest") for item in self.reversal_entry_digests)
        if len(distributions) != len(set(distributions)) or len(reversals) != len(set(reversals)):
            raise DistributionBudgetStateV1Error("budget-state entry digests must be unique")
        object.__setattr__(self, "distribution_entry_digests", distributions)
        object.__setattr__(self, "reversal_entry_digests", reversals)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers}))
        object.__setattr__(self, "blockers", blockers)
        expected_status = "BUDGET_AVAILABLE" if self.remaining_period_profit_budget > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionBudgetStateV1Error("distribution budget state status mismatch")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "state_id": self.state_id,
            "affected_period_id": self.affected_period_id,
            "base_distribution_capacity_replay_digest": self.base_distribution_capacity_replay_digest,
            "base_statement_replay_digest": self.base_statement_replay_digest,
            "reporting_currency": self.reporting_currency,
            "ledger_sequence": self.ledger_sequence,
            "ledger_digest": self.ledger_digest,
            "gross_period_profit_budget": canonical_decimal_text(self.gross_period_profit_budget),
            "canonical_distribution_outflows": canonical_decimal_text(self.canonical_distribution_outflows),
            "canonical_distribution_reversals": canonical_decimal_text(self.canonical_distribution_reversals),
            "net_consumed_distribution_budget": canonical_decimal_text(self.net_consumed_distribution_budget),
            "remaining_period_profit_budget": canonical_decimal_text(self.remaining_period_profit_budget),
            "distribution_entry_digests": list(self.distribution_entry_digests),
            "reversal_entry_digests": list(self.reversal_entry_digests),
            "blockers": list(self.blockers),
            "status": self.status,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "authorization_authority": self.authorization_authority,
            "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_budget_state_v1(
    *,
    state_id: str,
    base_capacity: DistributionCapacityReplayV1,
    ledger: ReportingLedger,
    generated_at: datetime,
) -> DistributionBudgetStateV1:
    affected_period_id = base_capacity.affected_period_id
    distribution_entries: list[tuple[ReportingEntry, Decimal]] = []
    by_digest: dict[str, tuple[ReportingEntry, Decimal]] = {}
    for entry in ledger.entries_since(0):
        if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION":
            continue
        if entry.metadata.get("affected_period_id") != affected_period_id:
            continue
        amount = _distribution_amount(ledger, entry)
        distribution_entries.append((entry, amount))
        by_digest[entry.digest] = (entry, amount)

    reversal_entries: list[tuple[ReportingEntry, Decimal]] = []
    reversed_by_original: dict[str, Decimal] = {}
    for entry in ledger.entries_since(0):
        if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL":
            continue
        original_digest = _hex64(
            entry.metadata.get("original_distribution_reporting_entry_digest"),
            "original_distribution_reporting_entry_digest",
        )
        original = by_digest.get(original_digest)
        if original is None:
            # The reversal may belong to another affected period. Resolve against
            # the full ledger and include it only if its original payout belongs here.
            candidates = [item for item in ledger.entries_since(0) if item.digest == original_digest]
            if len(candidates) != 1:
                raise DistributionBudgetStateV1Error("reversal original distribution entry is missing or non-unique")
            original_entry = candidates[0]
            if original_entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION":
                raise DistributionBudgetStateV1Error("reversal does not reference an owner distribution")
            if original_entry.metadata.get("affected_period_id") != affected_period_id:
                continue
            original_amount = _distribution_amount(ledger, original_entry)
            by_digest[original_digest] = (original_entry, original_amount)
            if all(existing.digest != original_entry.digest for existing, _ in distribution_entries):
                distribution_entries.append((original_entry, original_amount))
            original = (original_entry, original_amount)
        reversal_amount = _reversal_amount(ledger, entry)
        cumulative = reversed_by_original.get(original_digest, ZERO) + reversal_amount
        if cumulative > original[1]:
            raise DistributionBudgetStateV1Error("cumulative reversals exceed original distribution posting")
        reversed_by_original[original_digest] = cumulative
        reversal_entries.append((entry, reversal_amount))

    distribution_entries.sort(key=lambda item: item[0].sequence)
    reversal_entries.sort(key=lambda item: item[0].sequence)
    outflows = sum((amount for _, amount in distribution_entries), ZERO)
    reversals = sum((amount for _, amount in reversal_entries), ZERO)
    net_consumed = outflows - reversals
    gross = base_capacity.realized_profit_budget
    remaining = max(ZERO, gross - net_consumed)
    blockers: list[str] = []
    if net_consumed > gross:
        blockers.append("DISTRIBUTED_ABOVE_GROSS_PERIOD_BUDGET")
    if remaining <= ZERO:
        blockers.append("NO_REMAINING_PERIOD_BUDGET")
    return DistributionBudgetStateV1(
        state_id=state_id,
        affected_period_id=affected_period_id,
        base_distribution_capacity_replay_digest=base_capacity.digest,
        base_statement_replay_digest=base_capacity.statement_replay_digest,
        reporting_currency=ledger.reporting_currency,
        ledger_sequence=ledger.sequence,
        ledger_digest=ledger.digest,
        gross_period_profit_budget=gross,
        canonical_distribution_outflows=outflows,
        canonical_distribution_reversals=reversals,
        net_consumed_distribution_budget=net_consumed,
        remaining_period_profit_budget=remaining,
        distribution_entry_digests=tuple(entry.digest for entry, _ in distribution_entries),
        reversal_entry_digests=tuple(entry.digest for entry, _ in reversal_entries),
        blockers=tuple(blockers),
        status="BUDGET_AVAILABLE" if remaining > ZERO and not blockers else "NO_ACTION",
        generated_at=generated_at,
    )
