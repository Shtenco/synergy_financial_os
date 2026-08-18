import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
V4=ROOT/'config/schema_registry_v4.json'
V5=ROOT/'config/schema_registry_v5.json'

def load(p): return json.loads(p.read_text(encoding='utf-8'))

def test_v5_is_append_only_overlay_and_v4_survives():
    assert V4.exists() and load(V4)['schema']=='sinergy.schema-registry/v4'
    v5=load(V5);assert v5['schema']=='sinergy.schema-registry/v5';assert v5['base_registry']=='config/schema_registry_v4.json';assert v5['evolution_policy']=='APPEND_ONLY_OVERLAY'

def test_recognition_v1_is_preserved_but_not_promoted():
    v5=load(V5);note=v5['lineage_notes'][0]
    assert note['artifact']=='sinergy_financial_os/revenue_recognition_v1.py'
    assert note['status']=='PRESERVED_UNPROMOTED_DRAFT'
    assert note['superseded_by']=='revenue.recognition/v2'

def test_v5_promotes_only_strict_revenue_chain_generations():
    additions={x['schema_id']:x for x in load(V5)['additions']}
    assert set(additions)=={'revenue.recognition/v2','economic.cycle-trace/v4','commitment.envelope/v3'}
    assert additions['revenue.recognition/v2']['schema_authority']=='Shtenco/synergy_financial_os'
    assert 'AI cannot recognize revenue' in additions['revenue.recognition/v2']['authority_note']
    assert additions['commitment.envelope/v3']['schema_authority']=='Shtenco/synergy_ai_blockchain'

def test_trace_and_trust_prior_generations_are_superseded_not_deleted():
    mapping={x['schema_id']:x['superseded_by'] for x in load(V5)['supersessions']}
    assert mapping=={'economic.cycle-trace/v3':'economic.cycle-trace/v4','commitment.envelope/v2':'commitment.envelope/v3'}
