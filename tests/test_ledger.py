import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    AppendOnlyJournal,
    JournalEntry,
    JournalLine,
)


def balanced_entry(event_id: str, sequence: int) -> JournalEntry:
    return JournalEntry(
        event_id=event_id,
        sequence=sequence,
        event_type="test",
        lines=(
            JournalLine("asset:cash", "USD", debit="100"),
            JournalLine("liability:deposit", "USD", credit="100"),
        ),
    )


def test_balanced_entry_is_accepted() -> None:
    balanced_entry("e1", 1)


def test_line_cannot_debit_and_credit_at_once() -> None:
    with pytest.raises(AccountingInvariantError):
        JournalLine("asset:cash", "USD", debit="1", credit="1")


def test_currency_must_balance_independently() -> None:
    with pytest.raises(AccountingInvariantError):
        JournalEntry(
            event_id="e1",
            sequence=1,
            event_type="bad_fx",
            lines=(
                JournalLine("asset:usd", "USD", debit="100"),
                JournalLine("asset:kzt", "KZT", credit="100"),
            ),
        )


def test_multi_currency_entry_can_balance_each_currency_separately() -> None:
    JournalEntry(
        event_id="e1",
        sequence=1,
        event_type="multi_currency",
        lines=(
            JournalLine("asset:usd", "USD", debit="100"),
            JournalLine("liability:usd", "USD", credit="100"),
            JournalLine("asset:kzt", "KZT", debit="50000"),
            JournalLine("liability:kzt", "KZT", credit="50000"),
        ),
    )


def test_journal_sequence_is_contiguous_and_event_ids_are_unique() -> None:
    journal = AppendOnlyJournal()
    journal.append(balanced_entry("e1", 1))
    journal.append(balanced_entry("e2", 2))
    assert journal.last_sequence == 2

    with pytest.raises(AccountingInvariantError):
        journal.append(balanced_entry("e2", 3))

    with pytest.raises(AccountingInvariantError):
        journal.append(balanced_entry("e3", 4))
