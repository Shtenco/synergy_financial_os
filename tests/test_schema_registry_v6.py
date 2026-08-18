import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V5=ROOT/'config/schema_registry_v5.json';V6=ROOT/'config/schema_registry_v6.json'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def test_v6_is_overlay_and_v5_survives():
 assert V5.exists() and load(V5)['schema']=='sinergy.schema-registry/v5';v6=load(V6);assert v6['schema']=='sinergy.schema-registry/v6';assert v6['base_registry']=='config/schema_registry_v5.json';assert v6['evolution_policy']=='APPEND_ONLY_OVERLAY'
def test_trace_v5_supersedes_v4_without_deletion():
 v6=load(V6);assert v6['supersessions'][0]['schema_id']=='economic.cycle-trace/v4';assert v6['supersessions'][0]['superseded_by']=='economic.cycle-trace/v5';item=v6['additions'][0];assert item['schema_id']=='economic.cycle-trace/v5';assert 'separate external trust commitment' in item['authority_note']
