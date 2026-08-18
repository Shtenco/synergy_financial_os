from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Mapping

from .core import AccountingInvariantError
from .reporting import ReportingEntry, ReportingLedger


SCHEMA = "ledger.event/v2"
HEX64 = re.compile(r"^[a-fA-F0-9]{64}$")
EVIDENCE_CLASSES = frozenset(
    {
        "INTERNAL",
        "BANK",
        "PSP",
        "CEX_FILL",
        "DEX_RECEIPT",
        "BLOCKCHAIN_FINALITY",
        "CBDC",
        "MERCHANT",
        "PROJECT",
        "AUDITED",
        "OTHER",
    }
)


class LedgerEventV2Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerEventV2Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if not HEX64.fullmatch(result):
        raise LedgerEventV2Error(f"{field_name} must be a 64-character hex digest")
    return result


def _utc_text(value: datetime, field_name: str = "effective_at") -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LedgerEventV2Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reconstructed_reporting_entry(payload: Mapping[str, Any]) -> dict[str, Any]:
    lines = payload.get("lines")
    if not isinstance(lines, list) or len(lines) < 2:
        raise LedgerEventV2Error("ledger event requires at least two lines")
    reporting_currency = _text(payload.get("reporting_currency"), "reporting_currency").upper()
    entry_lines: list[dict[str, str]] = []
    for index, raw in enumerate(lines):
        if not isinstance(raw, Mapping):
            raise LedgerEventV2Error(f"lines[{index}] must be an object")
        if raw.get("currency") != reporting_currency:
            raise LedgerEventV2Error("all ledger-event lines must use reporting_currency")
        account = _text(raw.get("account"), f"lines[{index}].account")
        debit = _text(raw.get("debit"), f"lines[{index}].debit")
        credit = _text(raw.get("credit"), f"lines[{index}].credit")
        entry_lines.append({"account_id": account, "debit": debit, "credit": credit})
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise LedgerEventV2Error("metadata must be an object")
    return {
        "sequence": payload.get("sequence"),
        "event_id": _text(payload.get("event_id"), "event_id"),
        "reference": _text(payload.get("external_reference"), "external_reference"),
        "flow_type": _text(payload.get("event_type"), "event_type"),
        "lines": entry_lines,
        "previous_entry_digest": _hex64(
            payload.get("previous_reporting_entry_digest"),
            "previous_reporting_entry_digest",
        ),
        "evidence_digest": _hex64(payload.get("evidence_digest"), "evidence_digest"),
        "metadata": dict(sorted((str(k), str(v)) for k, v in metadata.items())),
    }


def verify_ledger_event_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise LedgerEventV2Error("ledger event must be an object")
    event = dict(payload)
    if event.get("schema") != SCHEMA:
        raise LedgerEventV2Error("unsupported ledger event schema")
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise LedgerEventV2Error("sequence must be a positive integer")
    evidence_class = _text(event.get("evidence_class"), "evidence_class").upper()
    if evidence_class not in EVIDENCE_CLASSES:
        raise LedgerEventV2Error("unsupported evidence_class")
    _utc_text(datetime.fromisoformat(_text(event.get("effective_at"), "effective_at").replace("Z", "+00:00")))
    supplied_entry_digest = _hex64(
        event.get("reporting_entry_digest"), "reporting_entry_digest"
    )
    reconstructed = _reconstructed_reporting_entry(event)
    expected_entry_digest = _canonical_digest(reconstructed)
    if supplied_entry_digest != expected_entry_digest:
        raise LedgerEventV2Error(
            f"reporting entry digest mismatch: expected={expected_entry_digest} got={supplied_entry_digest}"
        )
    return event


def ledger_event_v2_digest(payload: Mapping[str, Any]) -> str:
    verified = verify_ledger_event_v2(payload)
    return _canonical_digest(verified)


def export_reporting_entry_as_ledger_event_v2(
    entry: ReportingEntry,
    ledger: ReportingLedger,
    *,
    effective_at: datetime,
    evidence_class: str,
) -> dict[str, Any]:
    if not isinstance(entry, ReportingEntry):
        raise LedgerEventV2Error("entry must be ReportingEntry")
    if not isinstance(ledger, ReportingLedger):
        raise LedgerEventV2Error("ledger must be ReportingLedger")
    evidence = _text(evidence_class, "evidence_class").upper()
    if evidence not in EVIDENCE_CLASSES:
        raise LedgerEventV2Error(f"unsupported evidence_class: {evidence}")
    if entry.evidence_digest is None:
        raise LedgerEventV2Error("external ledger event requires evidence_digest")

    canonical_entry = entry.canonical_dict()
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "event_id": entry.event_id,
        "sequence": entry.sequence,
        "event_type": entry.flow_type.value,
        "effective_at": _utc_text(effective_at),
        "reporting_currency": ledger.reporting_currency,
        "lines": [
            {
                "account": line["account_id"],
                "currency": ledger.reporting_currency,
                "debit": line["debit"],
                "credit": line["credit"],
            }
            for line in canonical_entry["lines"]
        ],
        "evidence_class": evidence,
        "external_reference": entry.reference,
        "evidence_digest": entry.evidence_digest,
        "metadata": dict(sorted(entry.metadata.items())),
        "previous_reporting_entry_digest": entry.previous_entry_digest,
        "reporting_entry_digest": entry.digest,
    }
    verify_ledger_event_v2(payload)
    return payload
