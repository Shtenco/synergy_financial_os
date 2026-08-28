from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

from sinergy_financial_os.accounting_period_v1 import AccountingPeriodV1
from sinergy_financial_os.revenue_reversal_v1 import RevenueReversalAuthorizationV1

ROOT=Path(__file__).resolve().parents[1]

def load(path): return json.loads(path.read_text(encoding='utf-8'))
def dt(v): return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(UTC)

def test_period_and_reversal_contracts_conform_to_json_schema():
 period=AccountingPeriodV1('period-x',dt('2026-08-19T00:00:00Z'),dt('2026-08-19T01:00:00Z'),'SINERGY_CONSOLIDATED','USDC','55'*32,'77'*32)
 auth=RevenueReversalAuthorizationV1('rev-x','period-y','project-x','REFUND','11'*32,'22'*32,'33'*32,'44'*32,'55'*32,'66'*32,'77'*32,'88'*32,'MULTISIG_GOVERNANCE',dt('2026-08-19T01:10:00Z'),dt('2026-08-19T01:20:00Z'))
 for name,payload in (
  ('accounting_period_v1.schema.json',period.to_dict()),
  ('revenue_reversal_authorization_v1.schema.json',auth.to_dict()),
 ):
  schema=load(ROOT/'schemas'/name);jsonschema.Draft202012Validator.check_schema(schema);jsonschema.Draft202012Validator(schema).validate(payload)

def test_schema_registry_v9_is_append_only_over_v8():
 r=load(ROOT/'config/schema_registry_v9.json')
 assert r['schema']=='sinergy.schema-registry/v9';assert r['base_registry']=='config/schema_registry_v8.json';assert r['evolution_policy']=='APPEND_ONLY_OVERLAY';assert r['supersessions']==[]
 ids={x['schema_id'] for x in r['additions']}
 assert {'accounting.period/v1','accounting.period-close/v1','revenue.reversal-authorization/v1'}<=ids
