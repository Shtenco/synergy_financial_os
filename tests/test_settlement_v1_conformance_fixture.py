import json
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FeeTranslation,
    automatic_fee_pnl,
    translate_settlement_fees,
    verify_settlement_receipt_for_accounting,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/settlement_receipt_v1_kzt_cny.json"
EXPECTED_DIGEST = "048f00672fea4b4dd3d3ba6f834d18cca0b9346f0fc93024b62c33fc62c92140"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_financial_os_accepts_shared_metapay_receipt_with_fixed_digest() -> None:
    receipt = _fixture()
    assert verify_settlement_receipt_for_accounting(receipt) == EXPECTED_DIGEST


def test_shared_receipt_fee_translation_classifies_only_explicit_fee_roles() -> None:
    fees = translate_settlement_fees(
        _fixture(),
        reporting_currency="USD",
        translations={
            "KZT": FeeTranslation(
                "KZT",
                "USD",
                "0.002",
                translation_evidence_digest="cd" * 32,
            )
        },
    )
    assert [fee.reporting_amount for fee in fees] == [
        Decimal("0.0030"),
        Decimal("0.25"),
    ]
    assert automatic_fee_pnl(fees) == Decimal("0.2470")


def test_notional_changes_do_not_enter_fee_pnl_path() -> None:
    receipt = _fixture()
    baseline = translate_settlement_fees(
        receipt,
        reporting_currency="USD",
        translations={
            "KZT": FeeTranslation(
                "KZT",
                "USD",
                "0.002",
                translation_evidence_digest="cd" * 32,
            )
        },
    )
    receipt["source_amount"] = "999999999"
    receipt["target_amount"] = "7777777"
    changed = translate_settlement_fees(
        receipt,
        reporting_currency="USD",
        translations={
            "KZT": FeeTranslation(
                "KZT",
                "USD",
                "0.002",
                translation_evidence_digest="cd" * 32,
            )
        },
    )
    assert automatic_fee_pnl(baseline) == automatic_fee_pnl(changed)


def test_noncanonical_fee_amount_is_rejected_even_if_other_facts_are_valid() -> None:
    receipt = _fixture()
    receipt["fees"][0]["amount"] = "1.50"
    with pytest.raises(AccountingInvariantError, match="not canonical decimal text"):
        verify_settlement_receipt_for_accounting(receipt)


def test_naive_finality_time_is_rejected() -> None:
    receipt = _fixture()
    receipt["finality_time"] = "2026-08-17T12:00:00"
    with pytest.raises(AccountingInvariantError, match="timezone-aware"):
        verify_settlement_receipt_for_accounting(receipt)
