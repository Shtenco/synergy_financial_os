import sinergy_financial_os as financial_os


PUBLIC_BOUNDARY_SYMBOLS = {
    "AIPolicyProposalReview",
    "FeeTranslation",
    "FinancialSnapshotV2",
    "LiquidityHorizonState",
    "MaturityTranslation",
    "ProjectMoneyTranslation",
    "ProjectScreeningPolicy",
    "ProjectScreeningResult",
    "TranslatedSettlementFee",
    "ValuationPolicy",
    "automatic_fee_pnl",
    "capture_financial_snapshot_v2",
    "contractual_outflows_by_horizon",
    "liquidity_horizon_states_from_maturity",
    "project_proposal_v2_digest",
    "requirement_ids_from_registry",
    "requirement_registry_digest",
    "review_ai_policy_proposal",
    "screen_project_for_financial_review",
    "screen_project_v2_for_financial_review",
    "translate_maturity_outflows",
    "translate_settlement_fees",
    "verify_maturity_snapshot_digest",
    "verify_project_evidence_bundle",
    "verify_settlement_receipt_for_accounting",
}


def test_package_root_exposes_current_federation_boundary_api() -> None:
    missing = sorted(name for name in PUBLIC_BOUNDARY_SYMBOLS if not hasattr(financial_os, name))
    assert missing == []


def test_package_all_contains_current_federation_boundary_api() -> None:
    exported = set(financial_os.__all__)
    assert PUBLIC_BOUNDARY_SYMBOLS <= exported


def test_public_api_does_not_expose_execution_or_authorization_shortcuts() -> None:
    for forbidden in (
        "approve_project",
        "authorize_project",
        "execute_ai_policy",
        "fund_project",
        "mint_from_ai",
    ):
        assert not hasattr(financial_os, forbidden)
