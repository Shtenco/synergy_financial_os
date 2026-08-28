from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical_json import canonical_json_digest
from .core import AccountingInvariantError
from .distribution_budget_state_v2 import build_distribution_budget_state_v2, _settlement_fee_amount
from .distribution_capacity_replay_v1 import DistributionCapacityReplayV1
from .numeric import canonical_decimal_text, finite_decimal
from .reporting import AccountClass, ConsolidationClass, FlowType, ReportingEntry, ReportingLedger
from .statement_replay_v1 import StatementReplayV1

SCHEMA = "distribution.budget-state/v3"
ZERO = Decimal("0")
HEX = frozenset("0123456789abcdef")
FEE_REFUND_TREATMENT = "REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE"
REVERSAL_FEE_TREATMENT = "NEW_EXTERNAL_COST_SEPARATE_FROM_RETURNED_PRINCIPAL_AND_FEE_REFUND"


class DistributionBudgetStateV3Error(AccountingInvariantError):
    pass


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DistributionBudgetStateV3Error(f"{name} is required")
    return value.strip()


def _hex(value: Any, name: str) -> str:
    result = _text(value, name).lower()
    if len(result) != 64 or any(ch not in HEX for ch in result):
        raise DistributionBudgetStateV3Error(f"{name} must be hex64")
    return result


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DistributionBudgetStateV3Error(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _amount(value: Any, name: str) -> Decimal:
    result = finite_decimal(value, name)
    if result < ZERO:
        raise DistributionBudgetStateV3Error(f"{name} must be non-negative")
    return result


def _external_lines(ledger: ReportingLedger, entry: ReportingEntry, account_class: AccountClass):
    return [(ledger.account(line.account_id), line) for line in entry.lines if ledger.account(line.account_id).account_class == account_class and ledger.account(line.account_id).consolidation_class == ConsolidationClass.EXTERNAL]


def _fee_refund_amount(ledger: ReportingLedger, entry: ReportingEntry) -> tuple[Decimal, str, str]:
    if entry.flow_type != FlowType.EXTERNAL_EXPENSE:
        raise DistributionBudgetStateV3Error("settlement fee refund must use EXTERNAL_EXPENSE reversal semantics")
    if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND":
        raise DistributionBudgetStateV3Error("settlement fee refund economic class mismatch")
    if entry.metadata.get("pnl_treatment") != "REALIZED_EXTERNAL_EXPENSE_REVERSAL":
        raise DistributionBudgetStateV3Error("settlement fee refund P&L treatment mismatch")
    if entry.metadata.get("fee_refund_treatment") != FEE_REFUND_TREATMENT:
        raise DistributionBudgetStateV3Error("settlement fee refund treatment mismatch")
    if len(entry.lines) != 2:
        raise DistributionBudgetStateV3Error("settlement fee refund requires two lines")
    assets = _external_lines(ledger, entry, AccountClass.ASSET)
    expenses = _external_lines(ledger, entry, AccountClass.EXPENSE)
    if len(assets) != 1 or len(expenses) != 1:
        raise DistributionBudgetStateV3Error("settlement fee refund requires one external asset and one external expense")
    _, asset = assets[0]; _, expense = expenses[0]
    if asset.credit != ZERO or asset.debit <= ZERO or expense.debit != ZERO or expense.credit <= ZERO or asset.debit != expense.credit:
        raise DistributionBudgetStateV3Error("settlement fee refund debit/credit mismatch")
    original_fee = _hex(entry.metadata.get("original_fee_reporting_entry_digest"), "original_fee_reporting_entry_digest")
    original_receipt = _hex(entry.metadata.get("original_distribution_receipt_digest"), "original_distribution_receipt_digest")
    _hex(entry.metadata.get("distribution_reversal_accounting_decision_digest"), "distribution_reversal_accounting_decision_digest")
    return asset.debit, original_fee, original_receipt


def _reversal_processing_fee_amount(ledger: ReportingLedger, entry: ReportingEntry) -> Decimal:
    if entry.flow_type != FlowType.EXTERNAL_EXPENSE:
        raise DistributionBudgetStateV3Error("reversal processing fee must be EXTERNAL_EXPENSE")
    if entry.metadata.get("economic_class") != "OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE":
        raise DistributionBudgetStateV3Error("reversal processing fee economic class mismatch")
    if entry.metadata.get("pnl_treatment") != "REALIZED_EXTERNAL_EXPENSE":
        raise DistributionBudgetStateV3Error("reversal processing fee P&L treatment mismatch")
    if entry.metadata.get("fee_treatment") != REVERSAL_FEE_TREATMENT:
        raise DistributionBudgetStateV3Error("reversal processing fee treatment mismatch")
    if len(entry.lines) != 2:
        raise DistributionBudgetStateV3Error("reversal processing fee requires two lines")
    assets = _external_lines(ledger, entry, AccountClass.ASSET)
    expenses = _external_lines(ledger, entry, AccountClass.EXPENSE)
    if len(assets) != 1 or len(expenses) != 1:
        raise DistributionBudgetStateV3Error("reversal processing fee requires one external asset and one external expense")
    _, asset = assets[0]; _, expense = expenses[0]
    if asset.debit != ZERO or asset.credit <= ZERO or expense.credit != ZERO or expense.debit <= ZERO or asset.credit != expense.debit:
        raise DistributionBudgetStateV3Error("reversal processing fee debit/credit mismatch")
    _hex(entry.metadata.get("original_distribution_receipt_digest"), "original_distribution_receipt_digest")
    _hex(entry.metadata.get("distribution_reversal_accounting_decision_digest"), "distribution_reversal_accounting_decision_digest")
    return asset.credit


@dataclass(frozen=True)
class DistributionBudgetStateV3:
    state_id: str
    previous_budget_state_digest: str
    affected_period_id: str
    base_distribution_capacity_replay_digest: str
    base_statement_replay_digest: str
    base_statement_closing_sequence: int
    reporting_currency: str
    ledger_sequence: int
    ledger_digest: str
    gross_period_profit_budget: Decimal
    post_close_settlement_fee_expenses: Decimal
    post_close_settlement_fee_refunds: Decimal
    post_close_reversal_processing_fees: Decimal
    net_post_close_distribution_fee_cost: Decimal
    fee_adjusted_period_profit_budget: Decimal
    canonical_distribution_outflows: Decimal
    canonical_distribution_reversals: Decimal
    net_consumed_distribution_budget: Decimal
    remaining_period_profit_budget: Decimal
    settlement_fee_entry_digests: tuple[str, ...]
    settlement_fee_refund_entry_digests: tuple[str, ...]
    reversal_processing_fee_entry_digests: tuple[str, ...]
    distribution_entry_digests: tuple[str, ...]
    reversal_entry_digests: tuple[str, ...]
    blockers: tuple[str, ...]
    status: str
    generated_at: datetime
    authority: str = "FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE_V3"
    authorization_authority: str = "NONE"
    payment_authority: str = "NONE"
    execution_authority: str = "NONE"
    ai_authority: str = "NONE"

    def __post_init__(self) -> None:
        if self.authority != "FINANCIAL_OS_DISTRIBUTION_BUDGET_STATE_V3" or any(value != "NONE" for value in (self.authorization_authority, self.payment_authority, self.execution_authority, self.ai_authority)):
            raise DistributionBudgetStateV3Error("budget state authority escalation")
        object.__setattr__(self, "state_id", _text(self.state_id, "state_id")); object.__setattr__(self, "affected_period_id", _text(self.affected_period_id, "affected_period_id")); object.__setattr__(self, "reporting_currency", _text(self.reporting_currency, "reporting_currency").upper())
        for name in ("previous_budget_state_digest","base_distribution_capacity_replay_digest","base_statement_replay_digest","ledger_digest"):
            object.__setattr__(self, name, _hex(getattr(self, name), name))
        if isinstance(self.base_statement_closing_sequence, bool) or not isinstance(self.base_statement_closing_sequence, int) or self.base_statement_closing_sequence < 0:
            raise DistributionBudgetStateV3Error("base_statement_closing_sequence invalid")
        if isinstance(self.ledger_sequence, bool) or not isinstance(self.ledger_sequence, int) or self.ledger_sequence < self.base_statement_closing_sequence:
            raise DistributionBudgetStateV3Error("ledger_sequence invalid")
        for name in ("gross_period_profit_budget","post_close_settlement_fee_expenses","post_close_settlement_fee_refunds","post_close_reversal_processing_fees","net_post_close_distribution_fee_cost","fee_adjusted_period_profit_budget","canonical_distribution_outflows","canonical_distribution_reversals","net_consumed_distribution_budget","remaining_period_profit_budget"):
            object.__setattr__(self, name, _amount(getattr(self, name), name))
        if self.post_close_settlement_fee_refunds > self.post_close_settlement_fee_expenses:
            raise DistributionBudgetStateV3Error("fee refunds cannot exceed referenced post-close settlement fees")
        expected_net_fee = self.post_close_settlement_fee_expenses - self.post_close_settlement_fee_refunds + self.post_close_reversal_processing_fees
        if self.net_post_close_distribution_fee_cost != expected_net_fee:
            raise DistributionBudgetStateV3Error("net post-close distribution fee cost mismatch")
        expected_adjusted = min(self.gross_period_profit_budget, max(ZERO, self.gross_period_profit_budget - expected_net_fee))
        if self.fee_adjusted_period_profit_budget != expected_adjusted:
            raise DistributionBudgetStateV3Error("fee-adjusted period profit budget mismatch")
        if self.canonical_distribution_reversals > self.canonical_distribution_outflows:
            raise DistributionBudgetStateV3Error("reversals exceed distributions")
        if self.net_consumed_distribution_budget != self.canonical_distribution_outflows - self.canonical_distribution_reversals:
            raise DistributionBudgetStateV3Error("net consumed distribution mismatch")
        expected_remaining = max(ZERO, expected_adjusted - self.net_consumed_distribution_budget)
        if self.remaining_period_profit_budget != expected_remaining:
            raise DistributionBudgetStateV3Error("remaining period profit budget mismatch")
        for field in ("settlement_fee_entry_digests","settlement_fee_refund_entry_digests","reversal_processing_fee_entry_digests","distribution_entry_digests","reversal_entry_digests"):
            values = tuple(_hex(item, field) for item in getattr(self, field))
            if len(values) != len(set(values)):
                raise DistributionBudgetStateV3Error(f"{field} must be unique")
            object.__setattr__(self, field, values)
        blockers = tuple(sorted({_text(item, "blocker") for item in self.blockers})); object.__setattr__(self, "blockers", blockers)
        expected_status = "BUDGET_AVAILABLE" if self.remaining_period_profit_budget > ZERO and not blockers else "NO_ACTION"
        if self.status != expected_status:
            raise DistributionBudgetStateV3Error("budget status mismatch")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = {
            "schema": SCHEMA, "state_id": self.state_id, "previous_budget_state_digest": self.previous_budget_state_digest,
            "affected_period_id": self.affected_period_id, "base_distribution_capacity_replay_digest": self.base_distribution_capacity_replay_digest,
            "base_statement_replay_digest": self.base_statement_replay_digest, "base_statement_closing_sequence": self.base_statement_closing_sequence,
            "reporting_currency": self.reporting_currency, "ledger_sequence": self.ledger_sequence, "ledger_digest": self.ledger_digest,
            "gross_period_profit_budget": canonical_decimal_text(self.gross_period_profit_budget),
            "post_close_settlement_fee_expenses": canonical_decimal_text(self.post_close_settlement_fee_expenses),
            "post_close_settlement_fee_refunds": canonical_decimal_text(self.post_close_settlement_fee_refunds),
            "post_close_reversal_processing_fees": canonical_decimal_text(self.post_close_reversal_processing_fees),
            "net_post_close_distribution_fee_cost": canonical_decimal_text(self.net_post_close_distribution_fee_cost),
            "fee_adjusted_period_profit_budget": canonical_decimal_text(self.fee_adjusted_period_profit_budget),
            "canonical_distribution_outflows": canonical_decimal_text(self.canonical_distribution_outflows),
            "canonical_distribution_reversals": canonical_decimal_text(self.canonical_distribution_reversals),
            "net_consumed_distribution_budget": canonical_decimal_text(self.net_consumed_distribution_budget),
            "remaining_period_profit_budget": canonical_decimal_text(self.remaining_period_profit_budget),
            "settlement_fee_entry_digests": list(self.settlement_fee_entry_digests),
            "settlement_fee_refund_entry_digests": list(self.settlement_fee_refund_entry_digests),
            "reversal_processing_fee_entry_digests": list(self.reversal_processing_fee_entry_digests),
            "distribution_entry_digests": list(self.distribution_entry_digests), "reversal_entry_digests": list(self.reversal_entry_digests),
            "blockers": list(self.blockers), "status": self.status, "generated_at": self.generated_at.isoformat().replace("+00:00","Z"),
            "authority": self.authority, "authorization_authority": self.authorization_authority, "payment_authority": self.payment_authority,
            "execution_authority": self.execution_authority, "ai_authority": self.ai_authority,
        }
        if include_digest: payload["digest"] = canonical_json_digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return canonical_json_digest(self.to_dict(include_digest=False))


def build_distribution_budget_state_v3(*, state_id: str, base_capacity: DistributionCapacityReplayV1, base_statement_replay: StatementReplayV1, ledger: ReportingLedger, generated_at: datetime) -> DistributionBudgetStateV3:
    if base_statement_replay.digest != base_capacity.statement_replay_digest:
        raise DistributionBudgetStateV3Error("base StatementReplay / DistributionCapacityReplay mismatch")
    previous = build_distribution_budget_state_v2(state_id=f"{state_id}:v2-lineage", base_capacity=base_capacity, base_statement_replay=base_statement_replay, ledger=ledger, generated_at=generated_at)
    affected = base_capacity.affected_period_id
    fee_entries: dict[str, tuple[ReportingEntry, Decimal]] = {}
    for entry in ledger.entries_since(base_statement_replay.closing_sequence):
        if entry.metadata.get("economic_class") == "OWNER_DISTRIBUTION_SETTLEMENT_FEE" and entry.metadata.get("affected_period_id") == affected:
            fee_entries[entry.digest] = (entry, _settlement_fee_amount(ledger, entry))
    if set(fee_entries) != set(previous.settlement_fee_entry_digests):
        raise DistributionBudgetStateV3Error("v2/v3 post-close settlement fee set mismatch")

    refunds: list[tuple[ReportingEntry, Decimal, str, str]] = []
    refund_by_fee: dict[str, Decimal] = {}
    seen_refund_receipts: set[str] = set()
    processing_fees: list[tuple[ReportingEntry, Decimal]] = []
    for entry in ledger.entries_since(base_statement_replay.closing_sequence):
        if entry.metadata.get("affected_period_id") != affected:
            continue
        economic_class = entry.metadata.get("economic_class")
        if economic_class == "OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND":
            amount, original_fee_digest, original_receipt_digest = _fee_refund_amount(ledger, entry)
            if original_fee_digest not in fee_entries:
                raise DistributionBudgetStateV3Error("fee refund must reference a canonical post-close settlement fee for the same affected period")
            if original_receipt_digest in seen_refund_receipts:
                raise DistributionBudgetStateV3Error("same original distribution receipt has multiple fee-refund postings")
            seen_refund_receipts.add(original_receipt_digest)
            refund_by_fee[original_fee_digest] = refund_by_fee.get(original_fee_digest, ZERO) + amount
            refunds.append((entry, amount, original_fee_digest, original_receipt_digest))
        elif economic_class == "OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE":
            processing_fees.append((entry, _reversal_processing_fee_amount(ledger, entry)))
    for fee_digest, refunded in refund_by_fee.items():
        original_amount = fee_entries[fee_digest][1]
        if refunded > original_amount:
            raise DistributionBudgetStateV3Error("cumulative fee refunds exceed canonical original post-close settlement fee")

    fee_total = sum((amount for _, amount in fee_entries.values()), ZERO)
    refund_total = sum((amount for _, amount, _, _ in refunds), ZERO)
    processing_total = sum((amount for _, amount in processing_fees), ZERO)
    net_fee_cost = fee_total - refund_total + processing_total
    if net_fee_cost < ZERO:
        raise DistributionBudgetStateV3Error("net post-close distribution fee cost cannot be negative")
    gross = base_capacity.realized_profit_budget
    adjusted = min(gross, max(ZERO, gross - net_fee_cost))
    net_distribution = previous.net_consumed_distribution_budget
    remaining = max(ZERO, adjusted - net_distribution)
    blockers: list[str] = []
    if net_distribution > adjusted:
        blockers.append("DISTRIBUTED_ABOVE_NET_FEE_ADJUSTED_PERIOD_BUDGET")
    if net_fee_cost > gross:
        blockers.append("NET_POST_CLOSE_DISTRIBUTION_FEES_EXCEED_GROSS_PERIOD_PROFIT_BUDGET")
    if remaining <= ZERO:
        blockers.append("NO_REMAINING_PERIOD_BUDGET")
    return DistributionBudgetStateV3(
        state_id=state_id, previous_budget_state_digest=previous.digest, affected_period_id=affected,
        base_distribution_capacity_replay_digest=base_capacity.digest, base_statement_replay_digest=base_statement_replay.digest,
        base_statement_closing_sequence=base_statement_replay.closing_sequence, reporting_currency=ledger.reporting_currency,
        ledger_sequence=ledger.sequence, ledger_digest=ledger.digest, gross_period_profit_budget=gross,
        post_close_settlement_fee_expenses=fee_total, post_close_settlement_fee_refunds=refund_total,
        post_close_reversal_processing_fees=processing_total, net_post_close_distribution_fee_cost=net_fee_cost,
        fee_adjusted_period_profit_budget=adjusted, canonical_distribution_outflows=previous.canonical_distribution_outflows,
        canonical_distribution_reversals=previous.canonical_distribution_reversals, net_consumed_distribution_budget=net_distribution,
        remaining_period_profit_budget=remaining, settlement_fee_entry_digests=tuple(sorted(fee_entries)),
        settlement_fee_refund_entry_digests=tuple(entry.digest for entry, _, _, _ in refunds),
        reversal_processing_fee_entry_digests=tuple(entry.digest for entry, _ in processing_fees),
        distribution_entry_digests=previous.distribution_entry_digests, reversal_entry_digests=previous.reversal_entry_digests,
        blockers=tuple(blockers), status="BUDGET_AVAILABLE" if remaining > ZERO and not blockers else "NO_ACTION", generated_at=generated_at,
    )
