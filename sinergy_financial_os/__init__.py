"""Dependency-light canonical reference primitives for SINERGY Financial OS."""

from .core import (
    AccountingInvariantError,
    FinancialState,
    coverage_deficit,
    debt_capacity_gap,
    distributable_profit,
    ensure_balanced_journal,
    ensure_maturity_match,
)
from .ledger import AppendOnlyJournal, JournalEntry, JournalLine

__all__ = [
    "AccountingInvariantError",
    "AppendOnlyJournal",
    "FinancialState",
    "JournalEntry",
    "JournalLine",
    "coverage_deficit",
    "debt_capacity_gap",
    "distributable_profit",
    "ensure_balanced_journal",
    "ensure_maturity_match",
]
