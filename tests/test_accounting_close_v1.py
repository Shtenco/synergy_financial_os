from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.accounting_close_v1 import (
    AccountingCloseV1Error,
    build_accounting_close_v1,
    build_ledger_inclusion_proof_v1,
    ledger_event_digest,
    merkle_root_v1,
    verify_ledger_inclusion_proof_v1,
)

ROOT=Path(__file__).resolve().parents[1]
EVENT_PATH=ROOT/'fixtures/conformance/ledger_event_v1_recognized_revenue.json'
CLOSE_SCHEMA=ROOT/'schemas/accounting_close_v1.schema.json'
PROOF_SCHEMA=ROOT/'schemas/ledger_inclusion_proof_v1.schema.json'

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def events(count=3):
 base=load(EVENT_PATH);out=[]
 for i in range(count):
  e=copy.deepcopy(base);e['event_id']=f'event-{i+1:03d}';e['sequence']=i+1;e['external_reference']=f'ref-{i+1:03d}';out.append(e)
 return out

def close(ev):
 return build_accounting_close_v1(ev,close_id='close-001',financial_snapshot_digest='08'*32,closed_at=datetime(2026,8,19,11,5,tzinfo=UTC),valuation_policy_digest='cc'*32,requirement_registry_digest='dd'*32)

def test_close_seals_contiguous_ledger_prefix_and_validates_schema():
 ev=events();c=close(ev)
 assert c.event_count==3 and c.first_sequence==1 and c.last_sequence==3
 assert c.ledger_root==merkle_root_v1(ev)
 jsonschema.Draft202012Validator(load(CLOSE_SCHEMA)).validate(c.to_dict())

def test_middle_event_has_valid_merkle_inclusion_proof():
 ev=events();c=close(ev);proof=build_ledger_inclusion_proof_v1(ev,event_index=1,close=c)
 assert proof.event_digest==ledger_event_digest(ev[1])
 assert verify_ledger_inclusion_proof_v1(ev[1],proof,c) is True
 jsonschema.Draft202012Validator(load(PROOF_SCHEMA)).validate(proof.to_dict())

def test_changed_event_cannot_reuse_old_inclusion_proof_even_if_event_hash_is_recomputed():
 ev=events();c=close(ev);proof=build_ledger_inclusion_proof_v1(ev,event_index=1,close=c)
 tampered=copy.deepcopy(ev[1]);tampered['evidence_digest']='99'*32
 assert ledger_event_digest(tampered)!=proof.event_digest
 with pytest.raises(AccountingCloseV1Error,match='event digest mismatch'):
  verify_ledger_inclusion_proof_v1(tampered,proof,c)

def test_new_merkle_root_cannot_claim_old_accounting_close():
 ev=events();c=close(ev);changed=copy.deepcopy(ev);changed[1]['evidence_digest']='99'*32
 assert merkle_root_v1(changed)!=c.ledger_root
 with pytest.raises(AccountingCloseV1Error,match='does not seal supplied ledger events'):
  build_ledger_inclusion_proof_v1(changed,event_index=1,close=c)

def test_noncontiguous_or_duplicate_sequences_are_rejected_before_sealing():
 broken=events();broken[1]['sequence']=3
 with pytest.raises(AccountingCloseV1Error,match='contiguous'):
  close(broken)
 duplicate=events();duplicate[1]['event_id']=duplicate[0]['event_id']
 with pytest.raises(AccountingCloseV1Error,match='unique'):
  close(duplicate)

def test_single_event_tree_has_zero_siblings_and_is_still_provable():
 ev=events(1);c=close(ev);proof=build_ledger_inclusion_proof_v1(ev,event_index=0,close=c)
 assert proof.siblings==()
 assert verify_ledger_inclusion_proof_v1(ev[0],proof,c) is True
