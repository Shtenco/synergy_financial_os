from decimal import Decimal

import pytest

from sinergy_financial_os.external_profit_bus_accounting_v1 import (
    AccountingAction,
    ExternalProfitBusAccountingV1,
    ExternalProfitBusPayload,
    ExternalProfitClassification,
)

D = Decimal


def realized_payload(**changes) -> ExternalProfitBusPayload:
    values = {
        "evidence_id": "hybrid-001",
        "source": "HYBRID_CLASSIC_DEX_ARBITRAGE",
        "settlement_asset": "USDT",
        "classification": ExternalProfitClassification.REALIZED_EXTERNAL_PNL,
        "canonical_external_pnl": D("7.1"),
        "external_cash_delta": D("12"),
        "settlement_realized": True,
        "independent_external_counterparty": True,
        "flash_principal_repaid": True,
        "provider_references": ("bank:1", "cex:2", "dex:3"),
        "route_digest": "a" * 64,
        "internal_mint_quantity": D("0"),
        "internal_mark_delta": D("0"),
    }
    values.update(changes)
    return ExternalProfitBusPayload(**values)


def test_positive_hybrid_external_pnl_creates_one_realized_pnl_instruction() -> None:
    decision = ExternalProfitBusAccountingV1().decide(realized_payload())
    assert decision.action == AccountingAction.POST_REALIZED_EXTERNAL_PNL
    assert decision.recognized_external_pnl == D("7.1")
    assert len(decision.instructions) == 1
    posting = decision.instructions[0]
    assert posting.amount == D("7.1")
    assert posting.flow_type == "EXTERNAL_REVENUE"
    assert posting.pnl_treatment == "REALIZED_EXTERNAL_PNL"


def test_internal_mint_and_mark_are_provenance_only() -> None:
    decision = ExternalProfitBusAccountingV1().decide(
        realized_payload(
            internal_mint_quantity=D("1000000000"),
            internal_mark_delta=D("999999999"),
        )
    )
    assert decision.recognized_external_pnl == D("7.1")
    assert any("mint" in reason for reason in decision.reasons)
    assert any("mark" in reason for reason in decision.reasons)


def test_internal_mark_classification_cannot_carry_profit() -> None:
    payload = realized_payload(
        classification=ExternalProfitClassification.INTERNAL_MARK_NOT_EXTERNAL_VALUE,
        canonical_external_pnl=D("1000000"),
    )
    with pytest.raises(ValueError, match="non-P&L classification"):
        ExternalProfitBusAccountingV1().decide(payload)


def test_capital_reallocation_has_no_pnl_posting() -> None:
    payload = realized_payload(
        classification=ExternalProfitClassification.CAPITAL_REALLOCATION_PNL_ZERO,
        canonical_external_pnl=D("0"),
        external_cash_delta=D("0"),
        independent_external_counterparty=False,
        provider_references=(),
        route_digest=None,
    )
    decision = ExternalProfitBusAccountingV1().decide(payload)
    assert decision.action == AccountingAction.NO_PNL_POSTING
    assert decision.recognized_external_pnl == D("0")
    assert decision.instructions == ()


def test_issuance_inflow_requires_accounting_classification() -> None:
    payload = realized_payload(
        classification=(
            ExternalProfitClassification.EXTERNAL_INFLOW_REQUIRES_ACCOUNTING_CLASSIFICATION
        ),
        canonical_external_pnl=D("0"),
        external_cash_delta=D("500"),
        independent_external_counterparty=False,
        internal_mint_quantity=D("100000"),
    )
    decision = ExternalProfitBusAccountingV1().decide(payload)
    assert decision.action == AccountingAction.REQUIRE_HUMAN_ACCOUNTING_CLASSIFICATION
    assert decision.recognized_external_pnl == D("0")
    assert decision.instructions == ()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("settlement_realized", False, "external settlement"),
        ("independent_external_counterparty", False, "independent external counterparty"),
        ("flash_principal_repaid", False, "flash principal"),
        ("provider_references", (), "provider/venue references"),
        ("route_digest", None, "route/evidence digest"),
    ],
)
def test_realized_pnl_missing_external_evidence_fails_closed(
    field: str, value, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        ExternalProfitBusAccountingV1().decide(realized_payload(**{field: value}))


def test_recognized_pnl_cannot_exceed_external_cash_delta() -> None:
    with pytest.raises(ValueError, match="cannot exceed external cash delta"):
        ExternalProfitBusAccountingV1().decide(
            realized_payload(canonical_external_pnl=D("13"), external_cash_delta=D("12"))
        )


def test_internal_source_cannot_masquerade_as_realized_profit() -> None:
    with pytest.raises(ValueError, match="source is not eligible"):
        ExternalProfitBusAccountingV1().decide(
            realized_payload(source="INTERNAL_MINT")
        )


def test_input_digest_changes_when_evidence_changes() -> None:
    engine = ExternalProfitBusAccountingV1()
    first = engine.decide(realized_payload())
    second = engine.decide(realized_payload(provider_references=("bank:changed",)))
    assert first.input_digest != second.input_digest
    assert first.digest != second.digest
