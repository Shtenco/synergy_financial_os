from copy import deepcopy
from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FeeTranslation,
    automatic_fee_pnl,
    translate_settlement_fees,
    verify_settlement_receipt_for_accounting,
)


EVIDENCE = "ab" * 32


def _receipt() -> dict:
    return {
        "schema": "settlement.receipt/v1",
        "settlement_id": "settlement-1",
        "intent_id": "intent-1",
        "providers": ["bank-a", "dex-b"],
        "source_asset": "KZT",
        "source_amount": "1000000",
        "target_asset": "CNY",
        "target_amount": "14200",
        "fees": [
            {
                "asset": "USD",
                "amount": "1",
                "kind": "customer_service_fee",
                "economic_role": "PROTOCOL_REVENUE",
                "provider_ref": None,
            },
            {
                "asset": "KZT",
                "amount": "200",
                "kind": "bank_execution_fee",
                "economic_role": "PROVIDER_COST",
                "provider_ref": "bank-a",
            },
            {
                "asset": "KZT",
                "amount": "50",
                "kind": "network_cost",
                "economic_role": "NETWORK_COST",
                "provider_ref": None,
            },
            {
                "asset": "KZT",
                "amount": "25",
                "kind": "tax_withheld",
                "economic_role": "TAX",
                "provider_ref": None,
            },
        ],
        "status": "SETTLED",
        "finality_time": "2026-08-17T12:00:00+05:00",
        "external_evidence_classes": ["BANK", "DEX_RECEIPT"],
        "external_references": ["bank-ref", "chain-ref"],
        "evidence_digest": EVIDENCE,
        "reconciled": True,
        "route_id": "route-1",
        "metadata": {},
    }


def test_only_final_reconciled_evidence_bound_settlement_is_accounting_eligible() -> None:
    digest = verify_settlement_receipt_for_accounting(_receipt())
    assert len(digest) == 64

    pending = _receipt()
    pending["status"] = "PENDING"
    with pytest.raises(AccountingInvariantError):
        verify_settlement_receipt_for_accounting(pending)

    unreconciled = _receipt()
    unreconciled["reconciled"] = False
    with pytest.raises(AccountingInvariantError):
        verify_settlement_receipt_for_accounting(unreconciled)

    no_evidence = _receipt()
    no_evidence["evidence_digest"] = None
    with pytest.raises(AccountingInvariantError):
        verify_settlement_receipt_for_accounting(no_evidence)


def test_fee_translation_requires_explicit_fx_evidence_for_foreign_asset() -> None:
    with pytest.raises(AccountingInvariantError):
        FeeTranslation("KZT", "USD", "0.002")

    translation = FeeTranslation(
        "KZT",
        "USD",
        "0.002",
        translation_evidence_digest="cd" * 32,
    )
    assert translation.reporting_units_per_source_unit == Decimal("0.002")


def test_translated_fee_pnl_distinguishes_revenue_cost_and_tax() -> None:
    fees = translate_settlement_fees(
        _receipt(),
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
        Decimal("1"),
        Decimal("0.400"),
        Decimal("0.100"),
        Decimal("0.050"),
    ]
    assert [fee.automatic_pnl_effect for fee in fees] == [
        Decimal("1"),
        Decimal("-0.400"),
        Decimal("-0.100"),
        Decimal("0.000"),
    ]
    assert automatic_fee_pnl(fees) == Decimal("0.500")


def test_tax_and_other_are_not_auto_classified_as_expense_or_revenue() -> None:
    receipt = _receipt()
    receipt["fees"] = [
        {
            "asset": "USD",
            "amount": "5",
            "kind": "tax",
            "economic_role": "TAX",
            "provider_ref": None,
        },
        {
            "asset": "USD",
            "amount": "7",
            "kind": "manual_review",
            "economic_role": "OTHER",
            "provider_ref": None,
        },
    ]
    fees = translate_settlement_fees(receipt, reporting_currency="USD")
    assert automatic_fee_pnl(fees) == Decimal("0")


def test_missing_foreign_fee_translation_fails_closed() -> None:
    with pytest.raises(AccountingInvariantError):
        translate_settlement_fees(_receipt(), reporting_currency="USD")


def test_payment_notional_does_not_change_fee_pnl() -> None:
    translation = {
        "KZT": FeeTranslation(
            "KZT",
            "USD",
            "0.002",
            translation_evidence_digest="cd" * 32,
        )
    }
    base = _receipt()
    large = deepcopy(base)
    large["source_amount"] = "999999999999"
    large["target_amount"] = "8888888888"

    assert automatic_fee_pnl(
        translate_settlement_fees(base, reporting_currency="USD", translations=translation)
    ) == automatic_fee_pnl(
        translate_settlement_fees(large, reporting_currency="USD", translations=translation)
    )


def test_same_currency_fee_translation_rate_must_be_exactly_one() -> None:
    with pytest.raises(AccountingInvariantError):
        FeeTranslation("USD", "USD", "0.999")
