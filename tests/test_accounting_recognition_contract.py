from datetime import datetime, timezone
from uuid import UUID
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"contracts"/"accounting_recognition_v1.py"
spec=importlib.util.spec_from_file_location("accounting_recognition_v1",PATH)
mod=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_balanced_recognition_is_accepted():
    payload=mod.accounting_recognition_payload(
        source_settlement_event_id=UUID("66666666-6666-4666-8666-666666666666"),
        recognition_id=UUID("77777777-7777-4777-8777-777777777777"),
        classification="ASSET_TRANSFER",
        entries=[
            {"account":"asset:broker","side":"DEBIT","asset":"USD","amount":"750"},
            {"account":"clearing:trades","side":"CREDIT","asset":"USD","amount":"750"},
        ],
        recognized_at=datetime(2026,9,28,18,2,tzinfo=timezone.utc),
        accounting_period="2026-09-28",
        hardnav_delta="0",
        policy_refs=["fos:v1"],
        settlement_payload={
            "status":"SETTLED",
            "reconciled":True,
            "reconciliation_breaks":[],
        },
    )
    assert payload["classification"]=="ASSET_TRANSFER"


def test_unbalanced_recognition_fails_closed():
    with pytest.raises(ValueError):
        mod.accounting_recognition_payload(
            source_settlement_event_id="66666666-6666-4666-8666-666666666666",
            recognition_id="77777777-7777-4777-8777-777777777777",
            classification="REVENUE",
            entries=[{"account":"cash","side":"DEBIT","asset":"USD","amount":"1"}],
            recognized_at=datetime.now(timezone.utc),
            accounting_period="2026-09",
            hardnav_delta="1",
        )


def test_unreconciled_settlement_cannot_be_recognized():
    with pytest.raises(ValueError):
        mod.accounting_recognition_payload(
            source_settlement_event_id="66666666-6666-4666-8666-666666666666",
            recognition_id="77777777-7777-4777-8777-777777777777",
            classification="TRADING_PNL",
            entries=[],
            recognized_at=datetime.now(timezone.utc),
            accounting_period="2026-09",
            hardnav_delta="1",
            settlement_payload={
                "status":"SETTLED",
                "reconciled":False,
                "reconciliation_breaks":["missing_external:fill-1"],
            },
        )
