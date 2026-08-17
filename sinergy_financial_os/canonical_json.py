from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .errors import AccountingInvariantError


MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


def assert_canonical_json_profile(value: Any, path: str = "$") -> None:
    """Require the SINERGY cross-language canonical JSON primitive profile.

    Allowed JSON numeric values are discrete integers inside the JavaScript safe
    integer range. Fractional economics must be represented by already
    normalized decimal strings before this layer.
    """

    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise AccountingInvariantError(f"{path} integer exceeds cross-language safe range")
        return
    if isinstance(value, float):
        raise AccountingInvariantError(
            f"{path} contains float; canonical JSON requires decimal strings"
        )
    if isinstance(value, Decimal):
        raise AccountingInvariantError(
            f"{path} contains Decimal object; canonical JSON requires decimal strings"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AccountingInvariantError(f"{path} contains non-string JSON object key")
            assert_canonical_json_profile(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            assert_canonical_json_profile(item, f"{path}[{index}]")
        return
    raise AccountingInvariantError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def canonical_json_text(payload: Any) -> str:
    assert_canonical_json_profile(payload)
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AccountingInvariantError("payload must be canonical JSON") from exc


def canonical_json_bytes(payload: Any) -> bytes:
    return canonical_json_text(payload).encode("utf-8")


def canonical_json_digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
