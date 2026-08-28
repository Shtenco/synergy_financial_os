import json
from decimal import Decimal
from pathlib import Path

import pytest

from sinergy_financial_os.canonical_json import (
    assert_canonical_json_profile,
    canonical_json_digest,
    canonical_json_text,
)
from sinergy_financial_os.errors import AccountingInvariantError
from sinergy_financial_os.numeric import canonical_decimal_text


ROOT = Path(__file__).resolve().parents[1]


def test_fixed_unicode_vector_matches_exact_canonical_bytes() -> None:
    vector = json.loads(
        (
            ROOT
            / "fixtures/conformance/canonical_json_v1_unicode_safe_integer.json"
        ).read_text(encoding="utf-8")
    )
    assert vector["profile"] == "sinergy.canonical-json/v1"
    assert canonical_json_text(vector["payload"]) == vector["canonical_json"]
    assert canonical_json_digest(vector["payload"]) == canonical_json_digest(
        json.loads(vector["canonical_json"])
    )


@pytest.mark.parametrize("bad", [0.1, -0.0, float("inf"), float("nan")])
def test_canonical_profile_rejects_all_python_floats(bad: float) -> None:
    with pytest.raises(AccountingInvariantError, match="contains float"):
        assert_canonical_json_profile({"value": bad})


def test_canonical_profile_rejects_decimal_objects() -> None:
    with pytest.raises(AccountingInvariantError, match="Decimal object"):
        assert_canonical_json_profile({"value": Decimal("0.1")})


def test_canonical_profile_rejects_unsafe_integers() -> None:
    with pytest.raises(AccountingInvariantError, match="safe range"):
        assert_canonical_json_profile({"value": 9_007_199_254_740_992})


def test_canonical_profile_rejects_non_string_object_keys() -> None:
    with pytest.raises(AccountingInvariantError, match="non-string JSON object key"):
        assert_canonical_json_profile({1: "value"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.20", "0.2"),
        ("1.000", "1"),
        ("-0.00", "0"),
        ("1000", "1000"),
        ("0.0010", "0.001"),
        ("-12.3400", "-12.34"),
    ],
)
def test_canonical_decimal_text_has_unique_non_exponent_representation(
    raw: str,
    expected: str,
) -> None:
    assert canonical_decimal_text(raw) == expected
