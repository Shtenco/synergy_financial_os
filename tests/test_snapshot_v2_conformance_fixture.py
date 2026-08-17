import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    FinancialSnapshotV2,
    LiquidityHorizonState,
)
from sinergy_financial_os.canonical_json import canonical_json_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures/conformance/financial_snapshot_v2_canonical.json"
SCHEMA_PATH = ROOT / "schemas/financial_snapshot_v2.schema.json"
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _snapshot() -> FinancialSnapshotV2:
    return FinancialSnapshotV2(
        sequence=10,
        as_of=NOW,
        accounting_perimeter="SINERGY_CONSOLIDATED",
        reporting_currency="usd",
        ledger_digest="AA" * 32,
        ledger_last_entry_digest="BB" * 32,
        account_registry_digest="CC" * 32,
        valuation_policy_id="policy-v1",
        valuation_policy_digest="DD" * 32,
        valuation_policy_as_of=NOW,
        period_start_sequence=5,
        previous_snapshot_digest="AA" * 32,
        hard_external_assets=Decimal("120.00"),
        external_liabilities=Decimal("20.000"),
        immediate_external_liabilities=Decimal("10.0"),
        hard_nav=Decimal("100.000"),
        liquid_nav=Decimal("110.00"),
        economic_nav=Decimal("130.0"),
        hard_coverage=Decimal("6.000"),
        net_new_capital=Decimal("-0.00"),
        realized_external_revenue=Decimal("12.0"),
        realized_external_pnl=Decimal("10.00"),
        hard_nav_surplus_after_capital=Decimal("10.0"),
        required_retention=Decimal("2.0"),
        loss_carryforward=Decimal("1.00"),
        period_profit_budget=Decimal("7.000"),
        required_hard_nav_buffer=Decimal("95.00"),
        distribution_capacity=Decimal("5.0"),
        liquidity_horizons=(
            LiquidityHorizonState(1, "50.00", "10.0"),
            LiquidityHorizonState(4, "60.000", "20.00"),
            LiquidityHorizonState(8, "70.0", "-0.00"),
        ),
        maturity_snapshot_refs=("BB" * 32,),
        policy_mode="normal",
        invariant_failures=(),
    )


def test_authoritative_snapshot_producer_matches_shared_fixture_byte_semantics() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    snapshot = _snapshot()

    assert snapshot.to_dict() == fixture
    assert snapshot.digest == fixture["digest"]
    assert fixture["digest"] == "f0554b81af1924b9399f7d47a25af1a9d28ebf7373545ba72fea99788648a720"


def test_fixture_digest_is_over_payload_without_digest_field() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = dict(fixture)
    expected = payload.pop("digest")
    assert canonical_json_digest(payload) == expected


def test_snapshot_canonicalizes_equivalent_decimal_representations_uniquely() -> None:
    payload = _snapshot().to_dict()
    assert payload["hard_external_assets"] == "120"
    assert payload["hard_coverage"] == "6"
    assert payload["net_new_capital"] == "0"
    assert payload["liquidity_horizons"][0]["liquid_resources"] == "50"
    assert payload["liquidity_horizons"][1]["lcr"] == "3"
    assert payload["liquidity_horizons"][2]["expected_net_outflows"] == "0"
    assert payload["liquidity_horizons"][2]["lcr"] is None


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_snapshot_rejects_nonfinite_direct_decimal_inputs(bad: str) -> None:
    with pytest.raises(AccountingInvariantError):
        replace(_snapshot(), hard_nav=bad)


@pytest.mark.parametrize("bad_sequence", [True, 9_007_199_254_740_992])
def test_snapshot_rejects_noncanonical_cross_language_sequence_values(bad_sequence) -> None:
    with pytest.raises(AccountingInvariantError, match="safe integer"):
        replace(_snapshot(), sequence=bad_sequence)


def test_snapshot_v2_schema_uses_unique_decimal_text_and_safe_integer_caps() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    signed = re.compile(schema["$defs"]["signed"]["pattern"])
    nonnegative = re.compile(schema["$defs"]["nonnegative"]["pattern"])

    for value in ("0", "1", "-1", "0.2", "-0.2", "10.25", "-10.25"):
        assert signed.fullmatch(value), value
    for value in ("0", "1", "0.2", "10.25"):
        assert nonnegative.fullmatch(value), value

    for value in ("-0", "00", "01", "1.0", "0.20", "-0.20", "1e3", "NaN"):
        assert not signed.fullmatch(value), value
    for value in ("-1", "-0", "00", "01", "1.0", "0.20", "1e3", "Infinity"):
        assert not nonnegative.fullmatch(value), value

    assert schema["properties"]["sequence"]["maximum"] == 9_007_199_254_740_991
    assert schema["properties"]["period_start_sequence"]["maximum"] == 9_007_199_254_740_991
