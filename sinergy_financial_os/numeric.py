from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import AccountingInvariantError


ZERO = Decimal("0")


def finite_decimal(value: Any, field_name: str = "value") -> Decimal:
    """Convert to Decimal and reject NaN/Infinity/non-numeric values fail-closed."""

    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AccountingInvariantError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise AccountingInvariantError(f"{field_name} must be finite")
    return result


def canonical_decimal_text(value: Any, field_name: str = "value") -> str:
    """Return one non-exponent textual representation for a finite Decimal.

    This does not round. It removes only representation-only trailing
    fractional zeros and normalizes every signed/quantized zero to ``0``.

    Examples:
      ``0.20 -> 0.2``
      ``1.000 -> 1``
      ``-0.00 -> 0``
      ``0.0010 -> 0.001``
    """

    number = finite_decimal(value, field_name)
    if number == ZERO:
        return "0"
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text
