import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];P=ROOT/"contracts"/"research_inputs_v1.py"
s=importlib.util.spec_from_file_location("r",P);r=importlib.util.module_from_spec(s);assert s and s.loader;s.loader.exec_module(r)

def test_simulation_not_realized_pnl():
    x=r.consume_monetary_simulation({"run_id":"r","packets":1,"modeled_consolidated_hardnav_usd":10,"simulation_only":True,"external_profit_realized":False,"accounting_authority":False,"capital_authorization":False})
    assert x["realized_external_pnl"] is False
    assert x["canonical_accounting"] is False

def test_simulation_cannot_claim_realized_profit():
    with pytest.raises(ValueError):
        r.consume_monetary_simulation({"run_id":"r","packets":1,"modeled_consolidated_hardnav_usd":10,"simulation_only":True,"external_profit_realized":True,"accounting_authority":False,"capital_authorization":False})
