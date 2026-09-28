import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"contracts"/"research_inputs_v1.py"
spec=importlib.util.spec_from_file_location("research_inputs_v1",PATH)
mod=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

def test_bridge_health_and_scenario_remain_noncanonical():
    b=mod.consume_bridge_health({"observation_id":"b","health_factor_bps":18000,"status":"HEALTHY","accounting_authority":False})
    s=mod.consume_scenario_evidence({
        "scenario_id":"s","status":"STRESS","evidence_digest":"1"*64,
        "accounting_authority":False,"settlement_authority":False,"capital_authorization":False
    })
    assert b["canonical_accounting"] is False
    assert s["canonical_accounting"] is False
