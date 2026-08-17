import json
from pathlib import Path

import pytest

from sinergy_financial_os import (
    AccountingInvariantError,
    MaturityTranslation,
    contractual_outflows_by_horizon,
    translate_maturity_outflows,
    verify_maturity_snapshot_digest,
)
from sinergy_financial_os.canonical_json import canonical_json_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/conformance/maturity_snapshot_v1_callable_term_locked.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _resign(snapshot: dict) -> None:
    payload = dict(snapshot)
    payload.pop("digest", None)
    snapshot["digest"] = canonical_json_digest(payload)


def test_financial_os_accepts_shared_maturity_fixture_and_uses_noncallable_curve() -> None:
    snapshot = _fixture()
    assert verify_maturity_snapshot_digest(snapshot) == snapshot["digest"]
    assert contractual_outflows_by_horizon(snapshot) == {
        1: 100,
        4: 300,
        8: 600,
    }


def test_same_currency_translation_preserves_shared_fixture_outflows() -> None:
    translated = translate_maturity_outflows(
        _fixture(),
        MaturityTranslation("USD", "USD", "1"),
    )
    assert translated == {1: 100, 4: 300, 8: 600}


def test_fresh_digest_cannot_hide_noncallable_cumulative_arithmetic_tampering() -> None:
    snapshot = _fixture()
    snapshot["buckets"][3]["cumulative_noncallable_unlock"] = "250"
    _resign(snapshot)
    with pytest.raises(AccountingInvariantError, match="cumulative_noncallable_unlock mismatch"):
        verify_maturity_snapshot_digest(snapshot)


def test_fresh_digest_cannot_hide_callable_double_count_rule_change() -> None:
    snapshot = _fixture()
    snapshot["metadata"]["liquidity_outflow_rule"] = (
        "immediately_callable_principal + cumulative_unlock"
    )
    _resign(snapshot)
    with pytest.raises(AccountingInvariantError, match="liquidity_outflow_rule"):
        verify_maturity_snapshot_digest(snapshot)


def test_noncanonical_decimal_text_is_rejected_even_with_fresh_digest() -> None:
    snapshot = _fixture()
    snapshot["total_open_principal"] = "600.0"
    _resign(snapshot)
    with pytest.raises(AccountingInvariantError, match="not canonical decimal text"):
        verify_maturity_snapshot_digest(snapshot)
