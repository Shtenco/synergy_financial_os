from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.distribution_authorization_v1 import build_distribution_authorization_v1
from sinergy_financial_os.distribution_capacity_replay_v1 import DistributionCapacityReplayV1, DistributionLiquidityHeadroomV1
from sinergy_financial_os.distribution_execution_ticket_contract_v1 import verify_distribution_execution_ticket_payload_v1
from sinergy_financial_os.distribution_execution_ticket_v1 import (
    DistributionExecutionTicketV1Error,
    build_distribution_execution_ticket_v1,
    verify_distribution_execution_ticket_context_v1,
)
from sinergy_financial_os.distribution_plan_v1 import DistributionBeneficiaryV1, build_distribution_plan_v1
from sinergy_financial_os.liquidity_replay_v1 import LiquidityReplayHorizonV1, LiquidityReplayV1

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/distribution_execution_ticket_v1.schema.json').read_text(encoding='utf-8'))
REQ='91'*32; APPROVER='92'*32

def dt(h,m=0): return datetime(2026,8,20,h,m,tzinfo=UTC)

def ctx():
 liq=LiquidityReplayV1('liq','10'*32,'11'*32,'12'*32,('13'*32,),('14'*32,),'period-1',dt(2),'USD',Decimal('100'),(
  LiquidityReplayHorizonV1(1,Decimal('50'),Decimal('10'),Decimal('5'),Decimal('40')),
  LiquidityReplayHorizonV1(4,Decimal('75'),Decimal('30'),Decimal('2.5'),Decimal('45')),
  LiquidityReplayHorizonV1(8,Decimal('90'),Decimal('60'),Decimal('1.5'),Decimal('30'))),dt(3))
 cap=DistributionCapacityReplayV1('cap','period-1',liq.statement_replay_digest,liq.digest,liq.liquidity_resources_digest,'20'*32,liq.original_financial_snapshot_digest,Decimal('5'),Decimal('0'),Decimal('20'),Decimal('30'),Decimal('100'),Decimal('25'),Decimal('80'),Decimal('25'),Decimal('18'),Decimal('18'),(
  DistributionLiquidityHeadroomV1(1,Decimal('50'),Decimal('10'),Decimal('1.2'),Decimal('5'),Decimal('38'),Decimal('35'),Decimal('35')),
  DistributionLiquidityHeadroomV1(4,Decimal('75'),Decimal('30'),Decimal('1.2'),Decimal('5'),Decimal('39'),Decimal('40'),Decimal('39')),
  DistributionLiquidityHeadroomV1(8,Decimal('90'),Decimal('60'),Decimal('1.2'),Decimal('5'),Decimal('18'),Decimal('25'),Decimal('18'))),(), 'CAPACITY_AVAILABLE',dt(3,20))
 plan=build_distribution_plan_v1(plan_id='plan',distribution_capacity_replay=cap,liquidity_replay=liq,source_account_id='treasury-usd',beneficiaries=(DistributionBeneficiaryV1('a','bank-a',Decimal('10'),'dist-a-001'),DistributionBeneficiaryV1('b','bank-b',Decimal('8'),'dist-b-001')),generated_at=dt(3,30))
 auth=build_distribution_authorization_v1(authorization_id='auth',decision='APPROVED',decision_authority='MULTISIG_GOVERNANCE',distribution_plan=plan,distribution_capacity_replay=cap,requirement_registry_digest=REQ,approver_policy_digest=APPROVER,decision_evidence_digest='93'*32,decided_at=dt(3,40),expires_at=dt(4,40))
 return liq,cap,plan,auth

def test_ticket_is_fresh_financial_os_gate_but_not_execution():
 liq,cap,plan,auth=ctx()
 ticket=build_distribution_execution_ticket_v1(ticket_id='ticket',authorization=auth,plan=plan,capacity_replay=cap,liquidity_replay=liq,current_requirement_registry_digest=REQ,current_approver_policy_digest=APPROVER,verified_at=dt(3,50),expires_at=dt(4,20))
 assert ticket.payment_authority=='METAPAY_ONLY' and ticket.execution_authority=='NONE'
 jsonschema.Draft202012Validator(SCHEMA).validate(ticket.to_dict())
 assert verify_distribution_execution_ticket_payload_v1(ticket.to_dict()).digest==ticket.digest
 ok,blockers=verify_distribution_execution_ticket_context_v1(ticket,authorization=auth,plan=plan,capacity_replay=cap,liquidity_replay=liq,current_requirement_registry_digest=REQ,current_approver_policy_digest=APPROVER,now=dt(4))
 assert ok and blockers==()

def test_ticket_cannot_outlive_authorization():
 liq,cap,plan,auth=ctx()
 with pytest.raises(DistributionExecutionTicketV1Error,match='outlive'):
  build_distribution_execution_ticket_v1(ticket_id='ticket',authorization=auth,plan=plan,capacity_replay=cap,liquidity_replay=liq,current_requirement_registry_digest=REQ,current_approver_policy_digest=APPROVER,verified_at=dt(3,50),expires_at=dt(5))

def test_destination_change_invalidates_existing_ticket():
 liq,cap,plan,auth=ctx()
 ticket=build_distribution_execution_ticket_v1(ticket_id='ticket',authorization=auth,plan=plan,capacity_replay=cap,liquidity_replay=liq,current_requirement_registry_digest=REQ,current_approver_policy_digest=APPROVER,verified_at=dt(3,50),expires_at=dt(4,20))
 changed=build_distribution_plan_v1(plan_id='plan',distribution_capacity_replay=cap,liquidity_replay=liq,source_account_id='treasury-usd',beneficiaries=(DistributionBeneficiaryV1('a','attacker-bank',Decimal('10'),'dist-a-001'),DistributionBeneficiaryV1('b','bank-b',Decimal('8'),'dist-b-001')),generated_at=dt(3,30))
 ok,blockers=verify_distribution_execution_ticket_context_v1(ticket,authorization=auth,plan=changed,capacity_replay=cap,liquidity_replay=liq,current_requirement_registry_digest=REQ,current_approver_policy_digest=APPROVER,now=dt(4))
 assert not ok
 assert 'STALE_DISTRIBUTION_PLAN' in blockers and 'BENEFICIARY_SET_MISMATCH' in blockers
