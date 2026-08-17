from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from .core import AccountingInvariantError
from .reporting import (
    AccountClass,
    ConsolidationClass,
    FlowType,
    ReportingEntry,
    ReportingLedger,
)
from .valuation import ValuationRule


ZERO = Decimal("0")
REALIZED_PNL_FLOWS = frozenset(
    {FlowType.EXTERNAL_REVENUE, FlowType.EXTERNAL_EXPENSE, FlowType.CREDIT_LOSS}
)


def hard_nav_effect(
    ledger: ReportingLedger,
    entry: ReportingEntry,
    valuation_policy: Mapping[str, ValuationRule],
) -> Decimal:
    """Return the signed HardNAV effect of one reporting entry.

    This is intentionally net, not a sum of asset debits. It prevents a sale or
    asset swap from being mislabeled as revenue merely because a large cash
    debit appears on the entry.

    HardNAV effect is:

    - hard-valued external asset debits minus credits;
    - plus external-liability debits minus credits;
    - zero contribution from intra-group, memo, equity, revenue and expense
      accounts directly. Revenue/expense accounts explain the balancing side;
      economic value is recognized through external asset/liability movement.
    """

    effect = ZERO
    for line in entry.lines:
        spec = ledger.account(line.account_id)
        if spec.consolidation_class != ConsolidationClass.EXTERNAL:
            continue

        if spec.account_class == AccountClass.ASSET:
            try:
                rule = valuation_policy[spec.valuation_class]
            except KeyError as exc:
                raise AccountingInvariantError(
                    f"missing valuation rule for {spec.valuation_class}"
                ) from exc
            if rule.valuation_class != spec.valuation_class:
                raise AccountingInvariantError(
                    "valuation policy key/class mismatch for "
                    f"{spec.account_id}: {spec.valuation_class} != {rule.valuation_class}"
                )
            effect += rule.apply(line.debit).hard
            effect -= rule.apply(line.credit).hard

        elif spec.account_class == AccountClass.LIABILITY:
            effect += line.debit
            effect -= line.credit

    return effect


def entry_pnl_effect(ledger: ReportingLedger, entry: ReportingEntry) -> Decimal:
    """Return signed external P&L represented by revenue/expense account lines.

    Revenue normal credits increase P&L. Expense normal debits decrease P&L.
    Intra-group or memo P&L accounts are ignored for consolidated external P&L.
    Principal and asset/liability movements do not enter this function directly.
    """

    effect = ZERO
    for line in entry.lines:
        spec = ledger.account(line.account_id)
        if spec.consolidation_class != ConsolidationClass.EXTERNAL:
            continue
        if spec.account_class == AccountClass.REVENUE:
            effect += line.credit - line.debit
        elif spec.account_class == AccountClass.EXPENSE:
            effect += line.credit - line.debit
    return effect


def net_new_capital_since(
    ledger: ReportingLedger,
    sequence: int,
    valuation_policy: Mapping[str, ValuationRule],
) -> Decimal:
    """Signed HardNAV contribution of entries explicitly classified as capital."""

    total = ZERO
    for entry in ledger.entries_since(sequence):
        if entry.flow_type == FlowType.EXTERNAL_CAPITAL:
            total += hard_nav_effect(ledger, entry, valuation_policy)
    return total


def realized_external_revenue_since(
    ledger: ReportingLedger,
    sequence: int,
) -> Decimal:
    """Reporting-currency revenue from externally evidenced revenue entries.

    The value is taken from explicit consolidated revenue-account lines rather
    than gross asset movement. Principal repayment and settlement notional are
    excluded by flow type.
    """

    total = ZERO
    for entry in ledger.entries_since(sequence):
        if entry.flow_type == FlowType.EXTERNAL_REVENUE:
            total += entry_pnl_effect(ledger, entry)
    return total


def realized_external_pnl_since(
    ledger: ReportingLedger,
    sequence: int,
) -> Decimal:
    """Signed realized P&L from revenue, expense and credit-loss flow classes."""

    total = ZERO
    for entry in ledger.entries_since(sequence):
        if entry.flow_type in REALIZED_PNL_FLOWS:
            total += entry_pnl_effect(ledger, entry)
    return total
