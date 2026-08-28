from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .core import AccountingInvariantError
from .reporting import ReportingEntry, ReportingLedger


SCHEMA = "ledger.event/v1"
EVIDENCE_CLASSES = frozenset(
    {"INTERNAL", "BANK", "PSP", "CEX_FILL", "DEX_RECEIPT", "BLOCKCHAIN_FINALITY", "CBDC", "MERCHANT", "PROJECT", "AUDITED", "OTHER"}
)


class LedgerEventExportV1Error(AccountingInvariantError):
    pass


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LedgerEventExportV1Error("effective_at must be timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

def _decimal_text(value) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

def ledger_event_v1_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()

def export_reporting_entry_as_ledger_event_v1(
    entry: ReportingEntry,
    ledger: ReportingLedger,
    *,
    effective_at: datetime,
    evidence_class: str,
) -> dict[str, Any]:
    if not isinstance(entry, ReportingEntry):
        raise LedgerEventExportV1Error("entry must be ReportingEntry")
    evidence = evidence_class.upper().strip()
    if evidence not in EVIDENCE_CLASSES:
        raise LedgerEventExportV1Error(f"unsupported evidence_class: {evidence}")
    if entry.evidence_digest is None:
        raise LedgerEventExportV1Error("external ledger event requires evidence_digest")
    lines = [
        {
            "account": line.account_id,
            "currency": ledger.reporting_currency,
            "debit": _decimal_text(line.debit),
            "credit": _decimal_text(line.credit),
        }
        for line in entry.lines
    ]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "event_id": entry.event_id,
        "sequence": entry.sequence,
        "event_type": entry.flow_type.value,
        "effective_at": _utc_text(effective_at),
        "lines": lines,
        "evidence_class": evidence,
        "external_reference": entry.reference,
        "evidence_digest": entry.evidence_digest,
        "metadata": dict(sorted(entry.metadata.items())),
    }
    return payload
