from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Iterable
from uuid import UUID


CONTRACT_ID = "synergy.accounting.recognition/v1"
AUTHORITY = "canonical_accounting"
CLASSIFICATIONS = {
    "REVENUE","EXPENSE","ASSET_TRANSFER","LIABILITY_CHANGE",
    "TRADING_PNL","CAPITAL_FLOW","NON_RECOGNIZED",
}


def _check_double_entry(entries: list[dict]) -> None:
    debits: dict[str, Decimal] = defaultdict(Decimal)
    credits: dict[str, Decimal] = defaultdict(Decimal)
    for entry in entries:
        asset = str(entry["asset"]).upper()
        amount = Decimal(str(entry["amount"]))
        if amount < 0:
            raise ValueError("entry amount must be non-negative")
        side = str(entry["side"]).upper()
        if side == "DEBIT":
            debits[asset] += amount
        elif side == "CREDIT":
            credits[asset] += amount
        else:
            raise ValueError("side must be DEBIT or CREDIT")
    if debits != credits:
        raise ValueError(f"unbalanced double entry: debits={dict(debits)} credits={dict(credits)}")


def accounting_recognition_payload(
    *,
    source_settlement_event_id: UUID | str,
    recognition_id: UUID | str,
    classification: str,
    entries: Iterable[dict],
    recognized_at: datetime,
    accounting_period: str,
    hardnav_delta: Decimal | str,
    liquidnav_delta: Decimal | str = "0",
    economicnav_delta: Decimal | str = "0",
    policy_refs: Iterable[str] = (),
) -> dict:
    cls = classification.upper()
    if cls not in CLASSIFICATIONS:
        raise ValueError("unknown accounting classification")
    normalized = [
        {
            "account": str(e["account"]),
            "side": str(e["side"]).upper(),
            "asset": str(e["asset"]).upper(),
            "amount": str(Decimal(str(e["amount"]))),
        }
        for e in entries
    ]
    _check_double_entry(normalized)
    return {
        "source_settlement_event_id": str(source_settlement_event_id),
        "recognition_id": str(recognition_id),
        "classification": cls,
        "entries": normalized,
        "recognized_at": recognized_at.isoformat(),
        "accounting_period": accounting_period,
        "hardnav_delta": str(Decimal(str(hardnav_delta))),
        "liquidnav_delta": str(Decimal(str(liquidnav_delta))),
        "economicnav_delta": str(Decimal(str(economicnav_delta))),
        "policy_refs": list(policy_refs),
    }
