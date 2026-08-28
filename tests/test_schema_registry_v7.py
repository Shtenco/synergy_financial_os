import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V6=ROOT/'config/schema_registry_v6.json';V7=ROOT/'config/schema_registry_v7.json'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def test_v7_is_overlay_and_v6_survives():
 assert V6.exists() and load(V6)['schema']=='sinergy.schema-registry/v6';v7=load(V7);assert v7['schema']=='sinergy.schema-registry/v7';assert v7['base_registry']=='config/schema_registry_v6.json';assert v7['evolution_policy']=='APPEND_ONLY_OVERLAY'
def test_accounting_close_and_inclusion_proof_have_narrow_authority():
 additions={x['schema_id']:x for x in load(V7)['additions']};assert set(additions)=={'accounting.close/v1','ledger.inclusion-proof/v1'};assert additions['accounting.close/v1']['schema_authority']=='Shtenco/synergy_financial_os';assert 'cannot execute transactions or recognize revenue itself' in additions['accounting.close/v1']['authority_note'];assert 'Provenance-only Merkle proof' in additions['ledger.inclusion-proof/v1']['authority_note']
