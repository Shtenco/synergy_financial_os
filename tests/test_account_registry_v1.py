from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.account_registry_v1 import (
    AccountRegistryV1Error,
    build_account_registry_v1,
    verify_account_registry_against_snapshot_v1,
    verify_account_registry_payload_v1,
)
from sinergy_financial_os.reporting import (
    AccountClass,
    ConsolidationClass,
    ReportingAccountSpec,
    ReportingLine,
    FlowType,
)
from sinergy_financial_os.snapshot import LiquidityHorizonState, capture_financial_snapshot_v2
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/account_registry_v1.schema.json"


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def specs():
    return (
        ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH"),
        ReportingAccountSpec("revenue", "External revenue", AccountClass.REVENUE, ConsolidationClass.EXTERNAL, "REVENUE"),
        ReportingAccountSpec("tax", "Tax payable", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True),
        ReportingAccountSpec("refund", "Refund reserve", AccountClass.LIABILITY, ConsolidationClass.EXTERNAL, "LIABILITY", immediate_liability=True),
    )


def policy():
    return ValuationPolicy(
        "policy-v1", "USDC", dt("2026-08-19T10:00:00Z"),
        (ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )


def horizons(amount):
    return (
        LiquidityHorizonState(1, amount, Decimal("0")),
        LiquidityHorizonState(4, amount, Decimal("0")),
        LiquidityHorizonState(8, amount, Decimal("0")),
    )


def test_account_registry_round_trip_preserves_existing_reporting_ledger_digest():
    provisional = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-19T10:01:00Z")
    )
    ledger = provisional.instantiate_empty_reporting_ledger()
    registry = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-19T10:01:00Z"), expected_ledger=ledger
    )
    assert registry.account_registry_digest == ledger.account_registry_digest
    payload = registry.to_dict()
    assert verify_account_registry_payload_v1(payload) == registry
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)


def test_account_registry_digest_is_exact_snapshot_binding_not_a_new_hash_meaning():
    registry = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-19T10:01:00Z")
    )
    ledger = registry.instantiate_empty_reporting_ledger()
    ledger.post(
        event_id="capital-001", reference="capital-evidence-001", flow_type=FlowType.EXTERNAL_CAPITAL,
        lines=(ReportingLine("cash", debit=Decimal("100")), ReportingLine("refund", credit=Decimal("100"))),
        evidence_digest="11" * 32,
    )
    snapshot = capture_financial_snapshot_v2(
        ledger, policy(), as_of=dt("2026-08-19T11:00:00Z"), accounting_perimeter="SINERGY_CONSOLIDATED",
        liquidity_horizons=horizons(Decimal("100")), required_hard_nav_buffer=Decimal("0"), policy_mode="NORMAL"
    )
    assert snapshot.account_registry_digest == registry.account_registry_digest
    assert verify_account_registry_against_snapshot_v1(registry, snapshot.to_dict()) is True


def test_tampered_account_semantics_cannot_preserve_inner_registry_digest():
    registry = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-19T10:01:00Z")
    )
    payload = registry.to_dict()
    bad = copy.deepcopy(payload)
    bad["accounts"][0]["name"] = "Different account meaning"
    # Attacker can recompute an outer artifact digest, but cannot keep the old
    # ReportingLedger-compatible account_registry_digest for changed account bytes.
    bad.pop("digest")
    import hashlib
    bad["digest"] = hashlib.sha256(
        json.dumps(bad, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    with pytest.raises(AccountRegistryV1Error, match="account_registry_digest mismatch"):
        verify_account_registry_payload_v1(bad)


def test_runtime_rejects_normal_side_mismatch_and_schema_rejects_non_boolean_immediate_flag():
    payload = build_account_registry_v1(
        specs(), reporting_currency="USDC", generated_at=dt("2026-08-19T10:01:00Z")
    ).to_dict()
    bad = copy.deepcopy(payload)
    bad["accounts"][0]["normal_side"] = "CREDIT"
    with pytest.raises(AccountRegistryV1Error, match="normal_side mismatch"):
        verify_account_registry_payload_v1(bad)
    bad = copy.deepcopy(payload)
    bad["accounts"][0]["immediate_liability"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(bad)
