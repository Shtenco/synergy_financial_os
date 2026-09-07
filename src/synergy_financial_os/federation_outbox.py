from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .contracts import FinancialCommitmentArtifact, ReconciledTradingResult


class FinancialOutboxError(ValueError):
    pass


@dataclass(frozen=True)
class PendingFinancialEvent:
    event_id: str
    fact_contract_id: str
    fact_type: str
    event_bytes: bytes
    event_hash: str
    created_at: str


class AccountingTransactionalOutbox:
    """Commit Financial OS accounting truth and signed event atomically."""

    authority = "canonical_accounting"

    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(
            str(path),
            isolation_level=None,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reconciled_trading_results (
                contract_id TEXT PRIMARY KEY,
                execution_intent_id TEXT NOT NULL,
                settlement_contract_id TEXT NOT NULL,
                realized_pnl REAL NOT NULL,
                hardnav_delta REAL NOT NULL,
                reconciliation_status TEXT NOT NULL,
                domain_payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS financial_closes (
                contract_id TEXT PRIMARY KEY,
                close_id TEXT NOT NULL UNIQUE,
                snapshot_hash TEXT NOT NULL,
                merkle_root TEXT NOT NULL,
                hardnav REAL NOT NULL,
                liquid_nav REAL NOT NULL,
                liabilities REAL NOT NULL,
                accounting_period_end TEXT NOT NULL,
                domain_payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS federation_outbox (
                event_id TEXT PRIMARY KEY,
                fact_contract_id TEXT NOT NULL UNIQUE,
                fact_type TEXT NOT NULL,
                event_bytes BLOB NOT NULL,
                event_hash TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('PENDING','PUBLISHED')),
                created_at TEXT NOT NULL,
                published_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_financial_outbox_pending
              ON federation_outbox(state, created_at);
            """
        )

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _payload_hash(payload: dict) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_event_hash(
        self,
        event_bytes: bytes,
        expected_event_hash: str,
    ) -> str:
        actual = self._sha256(event_bytes)
        if actual != expected_event_hash:
            raise FinancialOutboxError(
                "signed event bytes do not match expected event hash"
            )
        return actual

    def _existing_outbox_matches(
        self,
        tx: sqlite3.Connection,
        contract_id: str,
        event_hash: str,
        fact_type: str,
    ) -> bool:
        row = tx.execute(
            """
            SELECT event_hash, fact_type
            FROM federation_outbox
            WHERE fact_contract_id=?
            """,
            (contract_id,),
        ).fetchone()
        if row is None:
            return False
        if row["event_hash"] != event_hash or row["fact_type"] != fact_type:
            raise FinancialOutboxError(
                "accounting fact replay conflicts with durable outbox"
            )
        return True

    def record_reconciliation_and_event(
        self,
        *,
        contract_id: str,
        result: ReconciledTradingResult,
        event_id: str,
        event_bytes: bytes,
        expected_event_hash: str,
        now: str,
        fail_after_domain_write: bool = False,
    ) -> bool:
        event_hash = self._validate_event_hash(
            event_bytes,
            expected_event_hash,
        )
        payload_hash = self._payload_hash(result.as_payload())
        with self.transaction() as tx:
            existing = tx.execute(
                """
                SELECT domain_payload_hash
                FROM reconciled_trading_results
                WHERE contract_id=?
                """,
                (contract_id,),
            ).fetchone()
            if existing is not None:
                if existing["domain_payload_hash"] != payload_hash:
                    raise FinancialOutboxError(
                        "reconciliation contract id reused with conflicting fact"
                    )
                if not self._existing_outbox_matches(
                    tx,
                    contract_id,
                    event_hash,
                    "ReconciledTradingResult",
                ):
                    raise FinancialOutboxError(
                        "reconciliation exists without matching durable outbox"
                    )
                return False

            tx.execute(
                """
                INSERT INTO reconciled_trading_results(
                    contract_id, execution_intent_id, settlement_contract_id,
                    realized_pnl, hardnav_delta, reconciliation_status,
                    domain_payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract_id,
                    result.execution_intent_id,
                    result.settlement_contract_id,
                    result.realized_pnl,
                    result.hardnav_delta,
                    result.reconciliation_status,
                    payload_hash,
                    now,
                ),
            )
            if fail_after_domain_write:
                raise RuntimeError(
                    "injected crash after reconciliation before outbox"
                )
            tx.execute(
                """
                INSERT INTO federation_outbox(
                    event_id, fact_contract_id, fact_type,
                    event_bytes, event_hash, state, created_at, published_at
                ) VALUES (?, ?, 'ReconciledTradingResult', ?, ?, 'PENDING', ?, NULL)
                """,
                (
                    event_id,
                    contract_id,
                    event_bytes,
                    event_hash,
                    now,
                ),
            )
        return True

    def record_close_and_event(
        self,
        *,
        contract_id: str,
        artifact: FinancialCommitmentArtifact,
        event_id: str,
        event_bytes: bytes,
        expected_event_hash: str,
        now: str,
        fail_after_domain_write: bool = False,
    ) -> bool:
        event_hash = self._validate_event_hash(
            event_bytes,
            expected_event_hash,
        )
        payload_hash = self._payload_hash(artifact.as_payload())
        period_end = artifact.accounting_period_end.isoformat().replace(
            "+00:00",
            "Z",
        )
        with self.transaction() as tx:
            existing = tx.execute(
                "SELECT domain_payload_hash FROM financial_closes WHERE contract_id=?",
                (contract_id,),
            ).fetchone()
            if existing is not None:
                if existing["domain_payload_hash"] != payload_hash:
                    raise FinancialOutboxError(
                        "financial close contract id reused with conflicting fact"
                    )
                if not self._existing_outbox_matches(
                    tx,
                    contract_id,
                    event_hash,
                    "FinancialCommitmentArtifact",
                ):
                    raise FinancialOutboxError(
                        "financial close exists without matching durable outbox"
                    )
                return False

            tx.execute(
                """
                INSERT INTO financial_closes(
                    contract_id, close_id, snapshot_hash, merkle_root,
                    hardnav, liquid_nav, liabilities, accounting_period_end,
                    domain_payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract_id,
                    artifact.close_id,
                    artifact.snapshot_hash,
                    artifact.merkle_root,
                    artifact.hardnav,
                    artifact.liquid_nav,
                    artifact.liabilities,
                    period_end,
                    payload_hash,
                    now,
                ),
            )
            if fail_after_domain_write:
                raise RuntimeError(
                    "injected crash after financial close before outbox"
                )
            tx.execute(
                """
                INSERT INTO federation_outbox(
                    event_id, fact_contract_id, fact_type,
                    event_bytes, event_hash, state, created_at, published_at
                ) VALUES (?, ?, 'FinancialCommitmentArtifact', ?, ?, 'PENDING', ?, NULL)
                """,
                (
                    event_id,
                    contract_id,
                    event_bytes,
                    event_hash,
                    now,
                ),
            )
        return True

    def pending(self, limit: int = 100) -> list[PendingFinancialEvent]:
        rows = self.conn.execute(
            """
            SELECT event_id, fact_contract_id, fact_type,
                   event_bytes, event_hash, created_at
            FROM federation_outbox
            WHERE state='PENDING'
            ORDER BY created_at, event_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            PendingFinancialEvent(
                event_id=row["event_id"],
                fact_contract_id=row["fact_contract_id"],
                fact_type=row["fact_type"],
                event_bytes=bytes(row["event_bytes"]),
                event_hash=row["event_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def mark_published(self, event_id: str, published_at: str) -> None:
        with self.transaction() as tx:
            cursor = tx.execute(
                """
                UPDATE federation_outbox
                SET state='PUBLISHED', published_at=?
                WHERE event_id=? AND state='PENDING'
                """,
                (published_at, event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(event_id)

    def counts(self) -> tuple[int, int, int]:
        reconciliations = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM reconciled_trading_results"
            ).fetchone()[0]
        )
        closes = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM financial_closes"
            ).fetchone()[0]
        )
        outbox = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM federation_outbox"
            ).fetchone()[0]
        )
        return reconciliations, closes, outbox
