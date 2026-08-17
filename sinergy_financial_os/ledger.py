from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .core import AccountingInvariantError


ZERO = Decimal("0")


def _d(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class JournalLine:
    account: str
    currency: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    def __post_init__(self) -> None:
        if not self.account:
            raise AccountingInvariantError("account is required")
        if not self.currency:
            raise AccountingInvariantError("currency is required")
        debit = _d(self.debit)
        credit = _d(self.credit)
        if debit < ZERO or credit < ZERO:
            raise AccountingInvariantError("debit and credit must be non-negative")
        if debit > ZERO and credit > ZERO:
            raise AccountingInvariantError("a journal line cannot debit and credit simultaneously")
        if debit == ZERO and credit == ZERO:
            raise AccountingInvariantError("a journal line must contain a debit or credit")
        object.__setattr__(self, "debit", debit)
        object.__setattr__(self, "credit", credit)


@dataclass(frozen=True)
class JournalEntry:
    event_id: str
    sequence: int
    event_type: str
    lines: tuple[JournalLine, ...]

    def __post_init__(self) -> None:
        if not self.event_id:
            raise AccountingInvariantError("event_id is required")
        if self.sequence < 1:
            raise AccountingInvariantError("sequence must be >= 1")
        if not self.event_type:
            raise AccountingInvariantError("event_type is required")
        if len(self.lines) < 2:
            raise AccountingInvariantError("journal entry requires at least two lines")
        self.ensure_balanced_by_currency()

    def ensure_balanced_by_currency(self) -> None:
        totals: dict[str, tuple[Decimal, Decimal]] = {}
        for line in self.lines:
            debit_total, credit_total = totals.get(line.currency, (ZERO, ZERO))
            totals[line.currency] = (
                debit_total + line.debit,
                credit_total + line.credit,
            )
        for currency, (debits, credits) in totals.items():
            if debits != credits:
                raise AccountingInvariantError(
                    f"unbalanced journal for {currency}: debits={debits} credits={credits}"
                )


@dataclass
class AppendOnlyJournal:
    """Minimal append-only event journal.

    This object validates identity, ordering and per-currency conservation. It
    intentionally does not infer account types or profit classification; those
    belong to a versioned chart of accounts / accounting policy layer.
    """

    entries: list[JournalEntry] = field(default_factory=list)
    _event_ids: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        original = list(self.entries)
        self.entries = []
        for entry in original:
            self.append(entry)

    @property
    def last_sequence(self) -> int:
        return self.entries[-1].sequence if self.entries else 0

    def append(self, entry: JournalEntry) -> None:
        if entry.event_id in self._event_ids:
            raise AccountingInvariantError(f"duplicate event_id: {entry.event_id}")
        expected = self.last_sequence + 1
        if entry.sequence != expected:
            raise AccountingInvariantError(
                f"non-contiguous sequence: expected={expected} got={entry.sequence}"
            )
        self.entries.append(entry)
        self._event_ids.add(entry.event_id)
