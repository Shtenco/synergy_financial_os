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

__all__ = [
    "AccountingInvariantError",
    "FinancialState",
    "coverage_deficit",
    "debt_capacity_gap",
    "distributable_profit",
    "ensure_balanced_journal",
    "ensure_maturity_match",
]
