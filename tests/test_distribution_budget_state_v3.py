from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from sinergy_financial_os.distribution_budget_state_v2 import build_distribution_budget_state_v2
from sinergy_financial_os.distribution_budget_state_v3 import DistributionBudgetStateV3Error, build_distribution_budget_state_v3
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, FlowType, ReportingAccountSpec, ReportingLedger, ReportingLine
from sinergy_financial_os.statement_replay_v1 import StatementReplayV1

H="1"*64
T=datetime(2026,8,28,10,0,tzinfo=UTC)


def statement():
    return StatementReplayV1(replay_id="statement",affected_period_id="period-1",original_period_close_digest="10"*32,original_accounting_close_digest="11"*32,original_financial_snapshot_digest="12"*32,opening_period_close_digest=None,opening_accounting_close_digest=None,account_registry_artifact_digest="13"*32,account_registry_digest="14"*32,valuation_policy_artifact_digest="15"*32,valuation_policy_digest="16"*32,restated_period_view_digest="17"*32,overlay_digests=("18"*32,),excluded_reporting_entry_digests=("19"*32,),opening_sequence=0,closing_sequence=2,original_event_count=2,retained_event_count=1,excluded_event_count=1,replayed_ledger_digest="20"*32,replayed_last_entry_digest="21"*32,hard_external_assets=Decimal("100"),liquid_haircut_assets=Decimal("100"),economic_haircut_assets=Decimal("100"),external_liabilities=Decimal("0"),hard_nav=Decimal("100"),liquid_nav=Decimal("100"),economic_nav=Decimal("100"),realized_external_revenue=Decimal("35"),realized_external_pnl=Decimal("30"),generated_at=T)


def base(st):
    hs=(DistributionLiquidityHeadroomV1(1,Decimal("50"),Decimal("10"),Decimal("1.2"),Decimal("5"),Decimal("38"),Decimal("35"),Decimal("35")),DistributionLiquidityHeadroomV1(4,Decimal("75"),Decimal("30"),Decimal("1.2"),Decimal("5"),Decimal("39"),Decimal("40"),Decimal("39")),DistributionLiquidityHeadroomV1(8,Decimal("90"),Decimal("60"),Decimal("1.2"),Decimal("5"),Decimal("18"),Decimal("25"),Decimal("18")))
    return DistributionCapacityReplayV1(replay_id="cap",affected_period_id="period-1",statement_replay_digest=st.digest,liquidity_replay_digest="22"*32,liquidity_resources_digest="23"*32,liquidity_policy_digest="24"*32,original_financial_snapshot_digest="25"*32,required_retention=Decimal("5"),loss_carryforward=Decimal("0"),required_hard_nav_buffer=Decimal("20"),restated_realized_external_pnl=Decimal("30"),restated_hard_nav=Decimal("100"),realized_profit_budget=Decimal("25"),solvency_headroom=Decimal("80"),accounting_distribution_capacity=Decimal("25"),liquidity_distribution_capacity=Decimal("18"),final_distribution_capacity=Decimal("18"),horizon_headrooms=hs,blockers=(),status="CAPACITY_AVAILABLE",generated_at=T)


def ledger_with_cycle():
    l=ReportingLedger("USD")
    l.register_account(ReportingAccountSpec("cash","Cash",AccountClass.ASSET,ConsolidationClass.EXTERNAL,"CASH"));l.register_account(ReportingAccountSpec("equity","Equity",AccountClass.EQUITY,ConsolidationClass.EXTERNAL,"EQUITY"));l.register_account(ReportingAccountSpec("fee","Fee",AccountClass.EXPENSE,ConsolidationClass.EXTERNAL,"EXPENSE"))
    l.post(event_id="capital",reference="capital",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("cash",debit=Decimal("100")),ReportingLine("equity",credit=Decimal("100"))),evidence_digest=H,metadata={"economic_class":"OWNER_CAPITAL"})
    pre=l.post(event_id="pre-close-fee",reference="pre-close-fee",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("fee",debit=Decimal("0.5")),ReportingLine("cash",credit=Decimal("0.5"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE","fee_treatment":"EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT","affected_period_id":"period-1"})
    dist=l.post(event_id="distribution",reference="distribution",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("equity",debit=Decimal("10")),ReportingLine("cash",credit=Decimal("10"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION","capital_direction":"OUTFLOW","pnl_treatment":"EXCLUDED_FROM_REALIZED_PNL","affected_period_id":"period-1"})
    fee=l.post(event_id="post-close-fee",reference="post-close-fee",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("fee",debit=Decimal("1.5")),ReportingLine("cash",credit=Decimal("1.5"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE","fee_treatment":"EXTERNAL_COST_SEPARATE_FROM_PRINCIPAL_NOT_PROFIT","affected_period_id":"period-1"})
    l.post(event_id="principal-return",reference="principal-return",flow_type=FlowType.EXTERNAL_CAPITAL,lines=(ReportingLine("cash",debit=Decimal("10")),ReportingLine("equity",credit=Decimal("10"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_REVERSAL","capital_direction":"INFLOW_REVERSAL_OF_PRIOR_OUTFLOW","pnl_treatment":"EXCLUDED_FROM_REALIZED_PNL","original_distribution_reporting_entry_digest":dist.digest,"original_distribution_receipt_digest":"31"*32,"affected_period_id":"period-1"})
    l.post(event_id="fee-refund",reference="fee-refund",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("cash",debit=Decimal("0.5")),ReportingLine("fee",credit=Decimal("0.5"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE_REVERSAL","fee_refund_treatment":"REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE","original_fee_reporting_entry_digest":fee.digest,"original_distribution_receipt_digest":"31"*32,"distribution_reversal_accounting_decision_digest":"32"*32,"affected_period_id":"period-1"})
    l.post(event_id="reversal-fee",reference="reversal-fee",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("fee",debit=Decimal("0.1")),ReportingLine("cash",credit=Decimal("0.1"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_REVERSAL_PROCESSING_FEE","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE","fee_treatment":"NEW_EXTERNAL_COST_SEPARATE_FROM_RETURNED_PRINCIPAL_AND_FEE_REFUND","original_distribution_receipt_digest":"31"*32,"distribution_reversal_accounting_decision_digest":"32"*32,"affected_period_id":"period-1"})
    return l,pre,fee


def test_fee_refund_restores_entitlement_but_processing_fee_reduces_it():
    st=statement();cap=base(st);l,_,_=ledger_with_cycle()
    state=build_distribution_budget_state_v3(state_id="v3",base_capacity=cap,base_statement_replay=st,ledger=l,generated_at=T)
    assert state.previous_budget_state_digest==build_distribution_budget_state_v2(state_id="v3:v2-lineage",base_capacity=cap,base_statement_replay=st,ledger=l,generated_at=T).digest
    assert state.gross_period_profit_budget==Decimal("25")
    assert state.post_close_settlement_fee_expenses==Decimal("1.5")
    assert state.post_close_settlement_fee_refunds==Decimal("0.5")
    assert state.post_close_reversal_processing_fees==Decimal("0.1")
    assert state.net_post_close_distribution_fee_cost==Decimal("1.1")
    assert state.fee_adjusted_period_profit_budget==Decimal("23.9")
    assert state.canonical_distribution_outflows==Decimal("10")
    assert state.canonical_distribution_reversals==Decimal("10")
    assert state.net_consumed_distribution_budget==Decimal("0")
    assert state.remaining_period_profit_budget==Decimal("23.9")


def test_refund_cannot_reference_preclose_fee():
    st=statement();cap=base(st);l,pre,_=ledger_with_cycle()
    l.post(event_id="bad-preclose-refund",reference="bad",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("cash",debit=Decimal("0.1")),ReportingLine("fee",credit=Decimal("0.1"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE_REVERSAL","fee_refund_treatment":"REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE","original_fee_reporting_entry_digest":pre.digest,"original_distribution_receipt_digest":"41"*32,"distribution_reversal_accounting_decision_digest":"42"*32,"affected_period_id":"period-1"})
    with pytest.raises(DistributionBudgetStateV3Error,match="post-close settlement fee"):
        build_distribution_budget_state_v3(state_id="bad",base_capacity=cap,base_statement_replay=st,ledger=l,generated_at=T)


def test_cumulative_refund_cannot_exceed_original_postclose_fee():
    st=statement();cap=base(st);l,_,fee=ledger_with_cycle()
    l.post(event_id="excess-refund",reference="excess",flow_type=FlowType.EXTERNAL_EXPENSE,lines=(ReportingLine("cash",debit=Decimal("1.1")),ReportingLine("fee",credit=Decimal("1.1"))),evidence_digest=H,metadata={"economic_class":"OWNER_DISTRIBUTION_SETTLEMENT_FEE_REFUND","pnl_treatment":"REALIZED_EXTERNAL_EXPENSE_REVERSAL","fee_refund_treatment":"REFUND_OF_ORIGINAL_SETTLEMENT_EXTERNAL_EXPENSE","original_fee_reporting_entry_digest":fee.digest,"original_distribution_receipt_digest":"51"*32,"distribution_reversal_accounting_decision_digest":"52"*32,"affected_period_id":"period-1"})
    with pytest.raises(DistributionBudgetStateV3Error,match="cumulative fee refunds"):
        build_distribution_budget_state_v3(state_id="excess",base_capacity=cap,base_statement_replay=st,ledger=l,generated_at=T)


def test_refund_never_lifts_fee_adjusted_entitlement_above_original_gross_budget():
    st=statement();cap=base(st);l,_,_=ledger_with_cycle();state=build_distribution_budget_state_v3(state_id="cap",base_capacity=cap,base_statement_replay=st,ledger=l,generated_at=T)
    assert state.fee_adjusted_period_profit_budget<=state.gross_period_profit_budget
