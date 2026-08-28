from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from sinergy_financial_os.account_registry_v1 import build_account_registry_v1
from sinergy_financial_os.canonical_json import canonical_json_digest
from sinergy_financial_os.liquidity_replay_v1 import LiquidityReplayV1Error, build_liquidity_replay_v1
from sinergy_financial_os.liquidity_resources_v1 import (
    LiquidityResourceHorizonV1,
    LiquidityResourcesV1Error,
    build_liquidity_resources_v1,
)
from sinergy_financial_os.maturity_translation_v1 import (
    MaturityTranslationV1Error,
    build_maturity_translation_artifact_v1,
)
from sinergy_financial_os.reporting import AccountClass, ConsolidationClass, ReportingAccountSpec, ReportingLedger
from sinergy_financial_os.statement_replay_v1 import StatementReplayV1
from sinergy_financial_os.valuation import ValuationPolicy, ValuationRule
from sinergy_financial_os.valuation_policy_artifact_v1 import build_valuation_policy_artifact_v1

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_SCHEMA = json.loads((ROOT / "schemas/liquidity_resources_v1.schema.json").read_text(encoding="utf-8"))
TRANSLATION_SCHEMA = json.loads((ROOT / "schemas/maturity_translation_v1.schema.json").read_text(encoding="utf-8"))
REPLAY_SCHEMA = json.loads((ROOT / "schemas/liquidity_replay_v1.schema.json").read_text(encoding="utf-8"))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def maturity_snapshot(*, as_of: str = "2026-08-20T02:00:00+00:00", currency: str = "USD") -> dict:
    noncallable = {1: 0, 2: 0, 3: 0, 4: 20, 5: 20, 6: 20, 7: 20, 8: 50}
    contractual = {1: 0, 2: 0, 3: 0, 4: 30, 5: 30, 6: 30, 7: 30, 8: 60}
    buckets = []
    prev_n = prev_c = 0
    for week in range(1, 9):
        n = noncallable[week]
        c = contractual[week]
        buckets.append({
            "week": week,
            "scheduled_unlock": str(c - prev_c),
            "cumulative_unlock": str(c),
            "scheduled_noncallable_unlock": str(n - prev_n),
            "cumulative_noncallable_unlock": str(n),
            "duration_eligible_principal": "0",
        })
        prev_n, prev_c = n, c
    payload = {
        "schema": "maturity.snapshot/v1",
        "as_of": as_of,
        "as_of_week": 0,
        "currency": currency,
        "total_open_principal": "60",
        "immediately_callable_principal": "10",
        "buckets": buckets,
        "metadata": {
            "horizon_weeks": 8,
            "liquidity_outflow_rule": "immediately_callable_principal + cumulative_noncallable_unlock",
        },
    }
    payload["digest"] = canonical_json_digest(payload)
    return payload


def context():
    spec = ReportingAccountSpec("cash", "External cash", AccountClass.ASSET, ConsolidationClass.EXTERNAL, "CASH")
    ledger = ReportingLedger("USD")
    ledger.register_account(spec)
    registry = build_account_registry_v1((spec,), reporting_currency="USD", generated_at=dt("2026-08-20T02:01:00Z"), expected_ledger=ledger)
    policy = ValuationPolicy(
        "liq-policy-v1", "USD", dt("2026-08-20T01:59:00Z"),
        (ValuationRule("CASH", Decimal("1"), Decimal("1"), Decimal("1"), "BANK_BALANCE"),),
    )
    valuation_artifact = build_valuation_policy_artifact_v1(policy, generated_at=dt("2026-08-20T02:01:00Z"))
    maturity = maturity_snapshot()
    snapshot = {
        "schema": "financial.snapshot/v2",
        "sequence": 1,
        "as_of": "2026-08-20T02:00:00+00:00",
        "reporting_currency": "USD",
        "ledger_digest": "10" * 32,
        "ledger_last_entry_digest": "11" * 32,
        "account_registry_digest": registry.account_registry_digest,
        "valuation_policy_digest": policy.digest,
        "maturity_snapshot_refs": [maturity["digest"]],
    }
    snapshot["digest"] = canonical_json_digest(snapshot)
    statement = StatementReplayV1(
        replay_id="statement-liquidity-input",
        affected_period_id="period-1",
        original_period_close_digest="12" * 32,
        original_accounting_close_digest="13" * 32,
        original_financial_snapshot_digest=snapshot["digest"],
        opening_period_close_digest="14" * 32,
        opening_accounting_close_digest="15" * 32,
        account_registry_artifact_digest=registry.digest,
        account_registry_digest=registry.account_registry_digest,
        valuation_policy_artifact_digest=valuation_artifact.digest,
        valuation_policy_digest=policy.digest,
        restated_period_view_digest="16" * 32,
        overlay_digests=("17" * 32,),
        excluded_reporting_entry_digests=("18" * 32,),
        opening_sequence=1,
        closing_sequence=2,
        original_event_count=2,
        retained_event_count=1,
        excluded_event_count=1,
        replayed_ledger_digest="19" * 32,
        replayed_last_entry_digest="1a" * 32,
        hard_external_assets=Decimal("100"),
        liquid_haircut_assets=Decimal("100"),
        economic_haircut_assets=Decimal("100"),
        external_liabilities=Decimal("0"),
        hard_nav=Decimal("100"),
        liquid_nav=Decimal("100"),
        economic_nav=Decimal("100"),
        realized_external_revenue=Decimal("0"),
        realized_external_pnl=Decimal("0"),
        generated_at=dt("2026-08-20T02:02:00Z"),
    )
    resources = build_liquidity_resources_v1(
        measurement_id="liquidity-resources-001",
        statement_replay=statement,
        original_financial_snapshot=snapshot,
        account_registry=registry,
        valuation_policy_artifact=valuation_artifact,
        liquidity_policy_digest="20" * 32,
        horizons=(
            LiquidityResourceHorizonV1(1, Decimal("50"), "21" * 32),
            LiquidityResourceHorizonV1(4, Decimal("75"), "22" * 32),
            LiquidityResourceHorizonV1(8, Decimal("90"), "23" * 32),
        ),
        generated_at=dt("2026-08-20T02:03:00Z"),
    )
    translation = build_maturity_translation_artifact_v1(
        maturity,
        reporting_currency="USD",
        reporting_units_per_source_unit="1",
        translation_evidence_digest=None,
        generated_at=dt("2026-08-20T02:03:00Z"),
    )
    return registry, valuation_artifact, maturity, snapshot, statement, resources, translation


def test_liquidity_replay_reproduces_lcr_from_separate_resource_and_outflow_evidence():
    _, _, maturity, snapshot, statement, resources, translation = context()
    result = build_liquidity_replay_v1(
        replay_id="liquidity-replay-001",
        statement_replay=statement,
        original_financial_snapshot=snapshot,
        liquidity_resources=resources,
        maturity_inputs=((maturity, translation),),
        generated_at=dt("2026-08-20T02:04:00Z"),
    )
    assert [item.expected_net_outflows for item in result.horizons] == [Decimal("10"), Decimal("30"), Decimal("60")]
    assert [item.lcr for item in result.horizons] == [Decimal("5"), Decimal("2.5"), Decimal("1.5")]
    assert [item.liquidity_surplus for item in result.horizons] == [Decimal("40"), Decimal("45"), Decimal("30")]
    jsonschema.Draft202012Validator(RESOURCE_SCHEMA).validate(resources.to_dict())
    jsonschema.Draft202012Validator(TRANSLATION_SCHEMA).validate(translation.to_dict())
    jsonschema.Draft202012Validator(REPLAY_SCHEMA).validate(result.to_dict())


def test_resource_measurement_cannot_exceed_restated_liquid_assets():
    registry, valuation_artifact, _, snapshot, statement, _, _ = context()
    with pytest.raises(LiquidityResourcesV1Error, match="exceed"):
        build_liquidity_resources_v1(
            measurement_id="too-large", statement_replay=statement, original_financial_snapshot=snapshot,
            account_registry=registry, valuation_policy_artifact=valuation_artifact, liquidity_policy_digest="20"*32,
            horizons=(
                LiquidityResourceHorizonV1(1, Decimal("50"), "21"*32),
                LiquidityResourceHorizonV1(4, Decimal("75"), "22"*32),
                LiquidityResourceHorizonV1(8, Decimal("101"), "23"*32),
            ), generated_at=dt("2026-08-20T02:03:00Z")
        )


def test_cross_currency_translation_requires_evidence():
    maturity = maturity_snapshot(currency="KZT")
    with pytest.raises(MaturityTranslationV1Error, match="evidence"):
        build_maturity_translation_artifact_v1(
            maturity, reporting_currency="USD", reporting_units_per_source_unit="0.002",
            translation_evidence_digest=None, generated_at=dt("2026-08-20T02:03:00Z")
        )


def test_unreferenced_or_stale_maturity_input_fails_closed():
    _, _, maturity, snapshot, statement, resources, _ = context()
    other = maturity_snapshot(as_of="2026-08-20T01:59:00+00:00")
    other_translation = build_maturity_translation_artifact_v1(
        other, reporting_currency="USD", reporting_units_per_source_unit="1", translation_evidence_digest=None,
        generated_at=dt("2026-08-20T02:03:00Z")
    )
    with pytest.raises(LiquidityReplayV1Error, match="as_of"):
        build_liquidity_replay_v1(
            replay_id="stale", statement_replay=statement, original_financial_snapshot=snapshot,
            liquidity_resources=resources, maturity_inputs=((other, other_translation),),
            generated_at=dt("2026-08-20T02:04:00Z")
        )
