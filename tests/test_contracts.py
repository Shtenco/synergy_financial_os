from datetime import datetime, timezone

import pytest

from synergy_financial_os import (
    EligibleAssetGrowthAttestation,
    EmissionReleaseRecognition,
    FinancialCommitmentArtifact,
    FinancialContractError,
    ProjectUnderwritingDecision,
    ReconciledTradingResult,
)


def test_matched_trading_result_must_reconcile_hardnav():
    with pytest.raises(FinancialContractError):
        ReconciledTradingResult(
            execution_intent_id="i1",
            settlement_contract_id="s1",
            realized_pnl=100.0,
            hardnav_delta=90.0,
            reconciliation_status="MATCHED",
        )


def test_rejected_project_has_zero_capacity():
    with pytest.raises(FinancialContractError):
        ProjectUnderwritingDecision(
            project_id="p1",
            decision="REJECT",
            approved_capacity=1.0,
            required_reserves=0.0,
            underwriting_snapshot_ref="snapshot:1",
        )


def test_financial_commitment_requires_real_hashes():
    artifact = FinancialCommitmentArtifact(
        close_id="c1",
        snapshot_hash="a" * 64,
        merkle_root="b" * 64,
        hardnav=1000,
        liquid_nav=800,
        liabilities=100,
        accounting_period_end=datetime.now(timezone.utc),
    )
    assert artifact.as_payload()["snapshot_hash"] == "a" * 64


def test_real_asset_growth_attestation_credits_only_verified_net_hardnav_growth():
    attestation = EligibleAssetGrowthAttestation(
        close_id="close:2",
        close_sequence=2,
        previous_hardnav=1000.0,
        current_hardnav=1080.0,
        previous_liabilities=100.0,
        current_liabilities=120.0,
        eligible_asset_gross_growth=100.0,
        internal_mark_change=50.0,
        flash_principal_inflow=0.0,
        eligible_asset_classes=("EXTERNAL_CASH",),
        evidence_refs=("settlement:bank:123",),
    )

    assert attestation.hardnav_growth == 80.0
    assert attestation.liability_increase == 20.0
    assert attestation.net_eligible_asset_growth == 80.0
    assert attestation.credited_growth == 80.0
    payload = attestation.as_payload()
    assert payload["credited_growth"] == 80.0
    assert payload["internal_mark_change"] == 50.0


def test_internal_mark_only_creates_zero_emission_credit():
    attestation = EligibleAssetGrowthAttestation(
        close_id="close:mark",
        close_sequence=3,
        previous_hardnav=1000.0,
        current_hardnav=1100.0,
        previous_liabilities=100.0,
        current_liabilities=100.0,
        eligible_asset_gross_growth=0.0,
        internal_mark_change=100.0,
        flash_principal_inflow=0.0,
    )
    assert attestation.credited_growth == 0.0


def test_liability_funded_asset_growth_creates_zero_emission_credit():
    attestation = EligibleAssetGrowthAttestation(
        close_id="close:flash",
        close_sequence=4,
        previous_hardnav=1000.0,
        current_hardnav=1000.0,
        previous_liabilities=100.0,
        current_liabilities=200.0,
        eligible_asset_gross_growth=100.0,
        internal_mark_change=0.0,
        flash_principal_inflow=100.0,
        eligible_asset_classes=("EXTERNAL_CASH",),
        evidence_refs=("flash:tx:abc",),
    )
    assert attestation.net_eligible_asset_growth == 0.0
    assert attestation.credited_growth == 0.0


def test_positive_eligible_growth_requires_class_and_evidence():
    with pytest.raises(FinancialContractError):
        EligibleAssetGrowthAttestation(
            close_id="close:no-proof",
            close_sequence=5,
            previous_hardnav=1000.0,
            current_hardnav=1010.0,
            previous_liabilities=100.0,
            current_liabilities=100.0,
            eligible_asset_gross_growth=10.0,
            internal_mark_change=0.0,
            flash_principal_inflow=0.0,
        )


def test_emission_release_is_recognized_without_revenue_or_profit():
    recognition = EmissionReleaseRecognition(
        proposal_id="aicb:proposal:17",
        release_tx_ref="polygon:tx:release-17",
        financial_growth_attestation_ref="financial:close:42",
        productive_growth_attestation_ref="eurasian:close:9",
        released_units=50.0,
        unit_value=1.0,
        accounting_classification="MONETARY_LIABILITY",
    )
    payload = recognition.as_payload()
    assert payload["released_monetary_value"] == 50.0
    assert payload["recognized_revenue"] == 0.0
    assert payload["recognized_profit"] == 0.0


def test_emission_release_cannot_be_booked_as_profit():
    with pytest.raises(FinancialContractError):
        EmissionReleaseRecognition(
            proposal_id="aicb:proposal:17",
            release_tx_ref="polygon:tx:release-17",
            financial_growth_attestation_ref="financial:close:42",
            productive_growth_attestation_ref="eurasian:close:9",
            released_units=50.0,
            unit_value=1.0,
            accounting_classification="MONETARY_LIABILITY",
            recognized_profit=50.0,
        )
