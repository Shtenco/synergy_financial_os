from decimal import Decimal

import pytest

from sinergy_financial_os.external_profit_import_v1 import (
    ExternalProfitImportEnvelopeV1,
    ExternalProfitImporterV1,
    ExternalProfitImportError,
    ImportDisposition,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLedger,
)

D = Decimal
HEX_A = "a" * 64
HEX_B = "b" * 64


def make_ledger(currency: str = "USDT") -> ReportingLedger:
    ledger = ReportingLedger(currency)
    ledger.register_account(
        ReportingAccountSpec(
            account_id="cash.external",
            name="External cash",
            account_class=AccountClass.ASSET,
            consolidation_class=ConsolidationClass.EXTERNAL,
            valuation_class="CASH",
        )
    )
    ledger.register_account(
        ReportingAccountSpec(
            account_id="revenue.arbitrage",
            name="Realized external arbitrage revenue",
            account_class=AccountClass.REVENUE,
            consolidation_class=ConsolidationClass.EXTERNAL,
            valuation_class="NOMINAL",
        )
    )
    ledger.register_account(
        ReportingAccountSpec(
            account_id="memo.internal",
            name="Internal memo",
            account_class=AccountClass.REVENUE,
            consolidation_class=ConsolidationClass.MEMO,
            valuation_class="MEMO",
        )
    )
    return ledger


def envelope(
    *,
    classification: str = "REALIZED_EXTERNAL_PNL",
    pnl: str = "10.3",
    cash_delta: str = "14.8",
    admissible: bool = True,
    settlement_asset: str = "USDT",
    metadata: dict[str, str] | None = None,
) -> ExternalProfitImportEnvelopeV1:
    return ExternalProfitImportEnvelopeV1(
        evidence_id="hybrid-001",
        source="HYBRID_CLASSIC_DEX_ARBITRAGE",
        classification=classification,
        settlement_asset=settlement_asset,
        canonical_external_pnl=D(pnl),
        external_cash_delta=D(cash_delta),
        admissible_for_financial_os_pnl=admissible,
        evidence_digest=HEX_A,
        route_digest=HEX_B,
        provider_references=("classic:fixture", "cex:fixture", "dex:fixture"),
        source_repository="Shtenco/synergy_pay_system",
        metadata=metadata or {},
    )


def test_realized_external_profit_posts_double_entry() -> None:
    ledger = make_ledger()
    item = envelope()
    entry = ExternalProfitImporterV1().post_realized_pnl(
        ledger,
        item,
        event_id="external-pnl-001",
        reference="hybrid-001",
        external_cash_account_id="cash.external",
        external_profit_revenue_account_id="revenue.arbitrage",
    )
    assert entry.flow_type.value == "EXTERNAL_REVENUE"
    assert entry.evidence_digest == HEX_A
    assert entry.metadata["route_digest"] == HEX_B
    assert ledger.balance("cash.external") == D("10.3")
    assert ledger.balance("revenue.arbitrage") == D("10.3")
    ledger.assert_balanced()


def test_huge_internal_mark_metadata_cannot_inflate_posted_amount() -> None:
    ledger = make_ledger()
    item = envelope(
        metadata={
            "internal_mint_quantity": "1000000000000000000",
            "internal_mark_delta": "999999999999999999999",
        }
    )
    ExternalProfitImporterV1().post_realized_pnl(
        ledger,
        item,
        event_id="external-pnl-002",
        reference="hybrid-002",
        external_cash_account_id="cash.external",
        external_profit_revenue_account_id="revenue.arbitrage",
    )
    assert ledger.balance("revenue.arbitrage") == D("10.3")


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        ("EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION", ImportDisposition.CLASSIFICATION_REQUIRED),
        ("CAPITAL_REALLOCATION_PNL_ZERO", ImportDisposition.NO_PNL),
        ("INTERNAL_MARK_NOT_EXTERNAL_VALUE", ImportDisposition.NO_PNL),
        ("NOT_REALIZED", ImportDisposition.NO_PNL),
        ("NON_POSITIVE_EXTERNAL_PNL", ImportDisposition.NO_PNL),
        ("INADMISSIBLE", ImportDisposition.REJECTED),
    ],
)
def test_non_realized_or_unclassified_items_cannot_post(
    classification: str, expected: ImportDisposition
) -> None:
    importer = ExternalProfitImporterV1()
    item = envelope(classification=classification, pnl="0", cash_delta="500", admissible=False)
    assert importer.classify(item).disposition == expected
    with pytest.raises(ExternalProfitImportError, match="not postable"):
        importer.post_realized_pnl(
            make_ledger(),
            item,
            event_id="blocked",
            reference=f"blocked-{classification}",
            external_cash_account_id="cash.external",
            external_profit_revenue_account_id="revenue.arbitrage",
        )


def test_pnl_cannot_exceed_external_cash_delta() -> None:
    decision = ExternalProfitImporterV1().classify(envelope(pnl="20", cash_delta="10"))
    assert decision.disposition == ImportDisposition.REJECTED


def test_usd_and_usdt_are_not_implicitly_converted() -> None:
    with pytest.raises(ExternalProfitImportError, match="USD/USDT cannot be conflated"):
        ExternalProfitImporterV1().post_realized_pnl(
            make_ledger("USDT"),
            envelope(settlement_asset="USD"),
            event_id="usd-not-usdt",
            reference="usd-not-usdt",
            external_cash_account_id="cash.external",
            external_profit_revenue_account_id="revenue.arbitrage",
        )


def test_evidence_and_route_digests_are_mandatory_hex64() -> None:
    with pytest.raises(ExternalProfitImportError, match="evidence_digest must be hex64"):
        ExternalProfitImportEnvelopeV1(
            evidence_id="bad-evidence",
            source="DEX_ARBITRAGE",
            classification="REALIZED_EXTERNAL_PNL",
            settlement_asset="USDT",
            canonical_external_pnl=D("1"),
            external_cash_delta=D("1"),
            admissible_for_financial_os_pnl=True,
            evidence_digest="missing",
            route_digest=HEX_B,
            provider_references=("dex:fixture",),
            source_repository="Shtenco/ai_financial_system",
        )


def test_target_accounts_must_be_external_asset_and_external_revenue() -> None:
    ledger = make_ledger()
    with pytest.raises(ExternalProfitImportError, match="EXTERNAL REVENUE"):
        ExternalProfitImporterV1().post_realized_pnl(
            ledger,
            envelope(),
            event_id="bad-account",
            reference="bad-account",
            external_cash_account_id="cash.external",
            external_profit_revenue_account_id="memo.internal",
        )


def test_existing_ledger_duplicate_reference_protection_remains_active() -> None:
    importer = ExternalProfitImporterV1()
    ledger = make_ledger()
    item = envelope()
    importer.post_realized_pnl(
        ledger,
        item,
        event_id="once",
        reference="same-ref",
        external_cash_account_id="cash.external",
        external_profit_revenue_account_id="revenue.arbitrage",
    )
    with pytest.raises(Exception, match="duplicate reference"):
        importer.post_realized_pnl(
            ledger,
            item,
            event_id="twice",
            reference="same-ref",
            external_cash_account_id="cash.external",
            external_profit_revenue_account_id="revenue.arbitrage",
        )
