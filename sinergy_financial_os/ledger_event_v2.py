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
DECIMAL = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
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


def _safe_sequence(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > MAX_SAFE_JSON_INTEGER
    ):
        raise LedgerEventV2Error("sequence must be a positive cross-language safe integer")
    return value


def _utc_text(value: datetime, field_name: str = "effective_at") -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LedgerEventV2Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_canonical_utc(value: Any, field_name: str) -> datetime:
    text = _text(value, field_name)
    if not text.endswith("Z"):
        raise LedgerEventV2Error(f"{field_name} must use canonical UTC Z time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LedgerEventV2Error(f"{field_name} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerEventV2Error(f"{field_name} must be timezone-aware")
    if _utc_text(parsed, field_name) != text:
        raise LedgerEventV2Error(f"{field_name} is not canonical UTC text")
    return parsed.astimezone(UTC)


def _decimal(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if not DECIMAL.fullmatch(result):
        raise LedgerEventV2Error(f"{field_name} must be canonical non-negative decimal text")
    return result


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


def _metadata(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise LedgerEventV2Error("metadata must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise LedgerEventV2Error("metadata keys must be non-empty strings")
        if not isinstance(item, str):
            raise LedgerEventV2Error("metadata values must be strings")
        result[key] = item
    return dict(sorted(result.items()))


def _reconstructed_reporting_entry(payload: Mapping[str, Any]) -> dict[str, Any]:
    lines = payload.get("lines")
    if not isinstance(lines, list) or len(lines) < 2:
        raise LedgerEventV2Error("ledger event requires at least two lines")
    reporting_currency = _text(payload.get("reporting_currency"), "reporting_currency").upper()
    entry_lines: list[dict[str, str]] = []
    debit_total_positive = False
    credit_total_positive = False
    for index, raw in enumerate(lines):
        if not isinstance(raw, Mapping):
            raise LedgerEventV2Error(f"lines[{index}] must be an object")
        if raw.get("currency") != reporting_currency:
            raise LedgerEventV2Error("all ledger-event lines must use reporting_currency")
        account = _text(raw.get("account"), f"lines[{index}].account")
        debit = _decimal(raw.get("debit"), f"lines[{index}].debit")
        credit = _decimal(raw.get("credit"), f"lines[{index}].credit")
        debit_positive = debit != "0"
        credit_positive = credit != "0"
        if debit_positive == credit_positive:
            raise LedgerEventV2Error("each line must contain exactly one positive debit or credit")
        debit_total_positive |= debit_positive
        credit_total_positive |= credit_positive
        entry_lines.append({"account_id": account, "debit": debit, "credit": credit})
    if not debit_total_positive or not credit_total_positive:
        raise LedgerEventV2Error("ledger event must contain both debit and credit sides")
    return {
        "sequence": _safe_sequence(payload.get("sequence")),
        "event_id": _text(payload.get("event_id"), "event_id"),
        "reference": _text(payload.get("external_reference"), "external_reference"),
        "flow_type": _text(payload.get("event_type"), "event_type"),
        "lines": entry_lines,
        "previous_entry_digest": _hex64(
            payload.get("previous_reporting_entry_digest"),
            "previous_reporting_entry_digest",
        ),
        "evidence_digest": _hex64(payload.get("evidence_digest"), "evidence_digest"),
        "metadata": _metadata(payload.get("metadata")),
    }


def verify_ledger_event_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise LedgerEventV2Error("ledger event must be an object")
    event = dict(payload)
    if event.get("schema") != SCHEMA:
        raise LedgerEventV2Error("unsupported ledger event schema")
    _safe_sequence(event.get("sequence"))
    evidence_class = _text(event.get("evidence_class"), "evidence_class").upper()
    if evidence_class not in EVIDENCE_CLASSES:
        raise LedgerEventV2Error("unsupported evidence_class")
    _parse_canonical_utc(event.get("effective_at"), "effective_at")
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
