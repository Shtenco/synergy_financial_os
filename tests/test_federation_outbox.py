import hashlib
from datetime import UTC, datetime

import pytest

from synergy_financial_os.contracts import (
    FinancialCommitmentArtifact,
    ReconciledTradingResult,
)
from synergy_financial_os.federation_outbox import AccountingTransactionalOutbox


NOW = "2026-09-06T11:10:00Z"
RESULT_WIRE = b'{"signed":"reconciled-result"}'
RESULT_HASH = hashlib.sha256(RESULT_WIRE).hexdigest()
CLOSE_WIRE = b'{"signed":"financial-close"}'
CLOSE_HASH = hashlib.sha256(CLOSE_WIRE).hexdigest()


def result() -> ReconciledTradingResult:
    return ReconciledTradingResult(
        execution_intent_id="intent-1",
        settlement_contract_id="settlement-1",
        realized_pnl=400.0,
        hardnav_delta=400.0,
        reconciliation_status="MATCHED",
    )


def close_artifact() -> FinancialCommitmentArtifact:
    return FinancialCommitmentArtifact(
        close_id="close-1",
        snapshot_hash="a" * 64,
        merkle_root="b" * 64,
        hardnav=1_250_400.0,
        liquid_nav=900_400.0,
        liabilities=250_000.0,
        accounting_period_end=datetime(2026, 9, 6, 11, 10, tzinfo=UTC),
    )


def test_reconciliation_and_event_commit_atomically(tmp_path):
    store = AccountingTransactionalOutbox(tmp_path / "financial.db")
    assert store.record_reconciliation_and_event(
        contract_id="reconciliation-1",
        result=result(),
        event_id="result-event-1",
        event_bytes=RESULT_WIRE,
        expected_event_hash=RESULT_HASH,
        now=NOW,
    )
    assert store.counts() == (1, 0, 1)
    assert store.pending()[0].fact_type == "ReconciledTradingResult"
    store.close()


def test_crash_between_reconciliation_and_outbox_rolls_back_both(tmp_path):
    store = AccountingTransactionalOutbox(tmp_path / "rollback-result.db")
    with pytest.raises(RuntimeError, match="injected crash"):
        store.record_reconciliation_and_event(
            contract_id="reconciliation-crash",
            result=result(),
            event_id="result-event-crash",
            event_bytes=RESULT_WIRE,
            expected_event_hash=RESULT_HASH,
            now=NOW,
            fail_after_domain_write=True,
        )
    assert store.counts() == (0, 0, 0)
    store.close()


def test_financial_close_and_chain_event_commit_atomically(tmp_path):
    store = AccountingTransactionalOutbox(tmp_path / "close.db")
    assert store.record_close_and_event(
        contract_id="financial-artifact-1",
        artifact=close_artifact(),
        event_id="close-event-1",
        event_bytes=CLOSE_WIRE,
        expected_event_hash=CLOSE_HASH,
        now=NOW,
    )
    assert store.counts() == (0, 1, 1)
    pending = store.pending()
    assert pending[0].fact_type == "FinancialCommitmentArtifact"
    assert pending[0].event_bytes == CLOSE_WIRE
    store.close()


def test_crash_between_close_and_chain_outbox_rolls_back_both(tmp_path):
    store = AccountingTransactionalOutbox(tmp_path / "rollback-close.db")
    with pytest.raises(RuntimeError, match="injected crash"):
        store.record_close_and_event(
            contract_id="financial-artifact-crash",
            artifact=close_artifact(),
            event_id="close-event-crash",
            event_bytes=CLOSE_WIRE,
            expected_event_hash=CLOSE_HASH,
            now=NOW,
            fail_after_domain_write=True,
        )
    assert store.counts() == (0, 0, 0)
    store.close()


def test_exact_reconciliation_retry_is_idempotent(tmp_path):
    store = AccountingTransactionalOutbox(tmp_path / "idempotent.db")
    kwargs = dict(
        contract_id="reconciliation-1",
        result=result(),
        event_id="result-event-1",
        event_bytes=RESULT_WIRE,
        expected_event_hash=RESULT_HASH,
        now=NOW,
    )
    assert store.record_reconciliation_and_event(**kwargs)
    assert not store.record_reconciliation_and_event(**kwargs)
    assert store.counts() == (1, 0, 1)
    store.close()
