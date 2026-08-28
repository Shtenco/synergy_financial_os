from decimal import Decimal

import pytest

from sinergy_financial_os import (
    AccountClass,
    AccountingInvariantError,
    ConsolidationClass,
    FlowType,
    ReportingAccountSpec,
    ReportingLedger,
    ReportingLine,
    ValuationRule,
)


EVIDENCE_A = "aa" * 32
EVIDENCE_B = "bb" * 32
EVIDENCE_C = "cc" * 32


def _register_standard_accounts(ledger: ReportingLedger) -> None:
    specs = [
        ReportingAccountSpec(
            "asset:cash",
            "External cash",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "HARD_EXTERNAL_ASSET",
        ),
        ReportingAccountSpec(
            "asset:credit",
            "Performing credit",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "PERFORMING_CREDIT",
        ),
        ReportingAccountSpec(
            "asset:intragroup",
            "Intra-group claim",
            AccountClass.ASSET,
            ConsolidationClass.INTRA_GROUP,
            "INTERNAL_CLAIM",
        ),
        ReportingAccountSpec(
            "asset:own-token",
            "Treasury-held own instrument",
            AccountClass.ASSET,
            ConsolidationClass.EXTERNAL,
            "OWN_ISSUED_INSTRUMENT",
        ),
        ReportingAccountSpec(
            "liability:deposit",
            "External deposit liability",
            AccountClass.LIABILITY,
            ConsolidationClass.EXTERNAL,
            "EXTERNAL_LIABILITY",
            immediate_liability=True,
        ),
        ReportingAccountSpec(
            "liability:intragroup",
            "Intra-group liability",
            AccountClass.LIABILITY,
            ConsolidationClass.INTRA_GROUP,
            "INTERNAL_CLAIM",
        ),
        ReportingAccountSpec(
            "equity:capital",
            "Contributed capital",
            AccountClass.EQUITY,
            ConsolidationClass.EXTERNAL,
            "EQUITY_ACCOUNT",
        ),
        ReportingAccountSpec(
            "revenue:external",
            "External revenue",
            AccountClass.REVENUE,
            ConsolidationClass.EXTERNAL,
            "REVENUE_ACCOUNT",
        ),
        ReportingAccountSpec(
            "expense:external",
            "External expense",
            AccountClass.EXPENSE,
            ConsolidationClass.EXTERNAL,
            "EXPENSE_ACCOUNT",
        ),
    ]
    for spec in specs:
        ledger.register_account(spec)


def _valuation_policy() -> dict[str, ValuationRule]:
    return {
        "HARD_EXTERNAL_ASSET": ValuationRule(
            "HARD_EXTERNAL_ASSET", "1", "1", "1", "BANK_BALANCE"
        ),
        "PERFORMING_CREDIT": ValuationRule(
            "PERFORMING_CREDIT", "0", "0", "0.8", "AUDITED_NAV"
        ),
        "OWN_ISSUED_INSTRUMENT": ValuationRule(
            "OWN_ISSUED_INSTRUMENT", "0", "0", "0", "EXECUTABLE_MARKET"
        ),
    }


def _capital_entry(ledger: ReportingLedger, amount: str = "100"):
    return ledger.post(
        event_id="capital-1",
        reference="bank-capital-1",
        flow_type=FlowType.EXTERNAL_CAPITAL,
        evidence_digest=EVIDENCE_A,
        lines=(
            ReportingLine("asset:cash", debit=amount),
            ReportingLine("equity:capital", credit=amount),
        ),
    )


def test_chart_freezes_after_first_entry() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger)

    with pytest.raises(AccountingInvariantError):
        ledger.register_account(
            ReportingAccountSpec(
                "asset:late",
                "Late account",
                AccountClass.ASSET,
                ConsolidationClass.EXTERNAL,
                "HARD_EXTERNAL_ASSET",
            )
        )


def test_every_non_internal_flow_requires_evidence() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)

    for flow_type in FlowType:
        if flow_type == FlowType.INTERNAL:
            continue
        with pytest.raises(AccountingInvariantError):
            ledger.post(
                event_id=f"event-{flow_type.value}",
                reference=f"ref-{flow_type.value}",
                flow_type=flow_type,
                lines=(
                    ReportingLine("asset:cash", debit="1"),
                    ReportingLine("equity:capital", credit="1"),
                ),
            )


def test_internal_reclassification_does_not_require_external_evidence() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    entry = ledger.post(
        event_id="internal-1",
        reference="internal-1",
        flow_type=FlowType.INTERNAL,
        lines=(
            ReportingLine("asset:intragroup", debit="10"),
            ReportingLine("equity:capital", credit="10"),
        ),
    )
    assert entry.evidence_digest is None


def test_duplicate_event_id_and_reference_fail_closed() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger)

    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="capital-1",
            reference="different-reference",
            flow_type=FlowType.INTERNAL,
            lines=(
                ReportingLine("asset:intragroup", debit="1"),
                ReportingLine("equity:capital", credit="1"),
            ),
        )

    with pytest.raises(AccountingInvariantError):
        ledger.post(
            event_id="different-event",
            reference="bank-capital-1",
            flow_type=FlowType.INTERNAL,
            lines=(
                ReportingLine("asset:intragroup", debit="1"),
                ReportingLine("equity:capital", credit="1"),
            ),
        )


def test_entry_hash_chain_links_to_previous_entry() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    first = _capital_entry(ledger)
    second = ledger.post(
        event_id="internal-2",
        reference="internal-2",
        flow_type=FlowType.INTERNAL,
        lines=(
            ReportingLine("asset:intragroup", debit="5"),
            ReportingLine("equity:capital", credit="5"),
        ),
    )
    assert second.previous_entry_digest == first.digest
    assert ledger.last_entry_digest == second.digest


def test_external_liability_reduces_nav_and_immediate_liability_is_reported() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger, "100")
    ledger.post(
        event_id="deposit-1",
        reference="external-deposit-1",
        flow_type=FlowType.LIABILITY_ISSUANCE,
        evidence_digest=EVIDENCE_B,
        lines=(
            ReportingLine("asset:cash", debit="50"),
            ReportingLine("liability:deposit", credit="50"),
        ),
    )

    state = ledger.financial_state(_valuation_policy())
    assert state.hard_external_assets == Decimal("150")
    assert state.external_liabilities == Decimal("50")
    assert state.hard_nav == Decimal("100")
    assert ledger.immediate_external_liabilities() == Decimal("50")


def test_intragroup_and_own_issued_positions_do_not_inflate_consolidated_nav() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger, "100")
    ledger.post(
        event_id="internal-claim",
        reference="internal-claim",
        flow_type=FlowType.INTERNAL,
        lines=(
            ReportingLine("asset:intragroup", debit="1000"),
            ReportingLine("equity:capital", credit="1000"),
        ),
    )
    ledger.post(
        event_id="own-token",
        reference="own-token",
        flow_type=FlowType.INTERNAL,
        lines=(
            ReportingLine("asset:own-token", debit="5000"),
            ReportingLine("equity:capital", credit="5000"),
        ),
    )

    state = ledger.financial_state(_valuation_policy())
    assert state.hard_external_assets == Decimal("100")
    assert state.liquid_haircut_assets == Decimal("100")
    assert state.economic_haircut_assets == Decimal("100")


def test_performing_credit_can_enter_economic_nav_without_becoming_hard_nav() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger, "100")
    ledger.post(
        event_id="credit-origination-1",
        reference="loan-1",
        flow_type=FlowType.CREDIT_ORIGINATION,
        evidence_digest=EVIDENCE_B,
        lines=(
            ReportingLine("asset:credit", debit="40"),
            ReportingLine("asset:cash", credit="40"),
        ),
    )

    state = ledger.financial_state(_valuation_policy())
    assert state.hard_external_assets == Decimal("60")
    assert state.liquid_haircut_assets == Decimal("60")
    assert state.economic_haircut_assets == Decimal("92.0")


def test_missing_or_mismatched_valuation_rule_fails_closed() -> None:
    ledger = ReportingLedger("KZT")
    _register_standard_accounts(ledger)
    _capital_entry(ledger, "100")

    with pytest.raises(AccountingInvariantError):
        ledger.financial_state({})

    with pytest.raises(AccountingInvariantError):
        ledger.financial_state(
            {
                "HARD_EXTERNAL_ASSET": ValuationRule(
                    "SOMETHING_ELSE", "1", "1", "1", "BANK_BALANCE"
                )
            }
        )


def test_trial_balance_and_digest_are_deterministic_for_same_history() -> None:
    def build() -> ReportingLedger:
        ledger = ReportingLedger("KZT")
        _register_standard_accounts(ledger)
        _capital_entry(ledger, "100")
        ledger.post(
            event_id="revenue-1",
            reference="merchant-fee-1",
            flow_type=FlowType.EXTERNAL_REVENUE,
            evidence_digest=EVIDENCE_C,
            lines=(
                ReportingLine("asset:cash", debit="10"),
                ReportingLine("revenue:external", credit="10"),
            ),
        )
        return ledger

    first = build()
    second = build()
    assert first.trial_balance() == (Decimal("110"), Decimal("110"))
    assert first.digest == second.digest
    assert first.last_entry_digest == second.last_entry_digest
