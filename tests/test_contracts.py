from datetime import datetime, timezone

import pytest

from synergy_financial_os import (
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
