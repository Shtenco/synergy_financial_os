from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import AccountingInvariantError


def finite_decimal(value: Any, field_name: str = "value") -> Decimal:
    """Convert to Decimal and reject NaN/Infinity/non-numeric values fail-closed."""

    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AccountingInvariantError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise AccountingInvariantError(f"{field_name} must be finite")
    return result
