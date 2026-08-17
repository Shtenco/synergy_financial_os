from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping

from .errors import AccountingInvariantError
from .project_bridge import (
    ProjectMoneyTranslation,
    ProjectScreeningPolicy,
    ProjectScreeningResult,
    screen_project_for_financial_review,
)


MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


def _assert_canonical_json_profile(value: Any, path: str = "$") -> None:
    """Require cross-language-stable JSON primitives for proposal v2.

    Fractional economic values belong in decimal strings. JSON numeric values
    are allowed only for discrete safe integers.
    """

    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise AccountingInvariantError(f"{path} integer exceeds cross-language safe range")
        return
    if isinstance(value, float):
        raise AccountingInvariantError(
            f"{path} contains float; project.proposal/v2 requires decimal strings"
        )
    if isinstance(value, Decimal):
        raise AccountingInvariantError(
            f"{path} contains Decimal object; project.proposal/v2 requires decimal strings"
        )
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_canonical_json_profile(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AccountingInvariantError(f"{path} contains non-string JSON object key")
            _assert_canonical_json_profile(item, f"{path}.{key}")
        return
    raise AccountingInvariantError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def project_proposal_v2_digest(proposal: Mapping[str, Any]) -> str:
    if proposal.get("schema") != "project.proposal/v2":
        raise AccountingInvariantError("unsupported project proposal v2 schema")
    _assert_canonical_json_profile(proposal)
    try:
        encoded = json.dumps(
            dict(proposal),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AccountingInvariantError("project.proposal/v2 must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def screen_project_v2_for_financial_review(
    proposal: Mapping[str, Any],
    policy: ProjectScreeningPolicy,
    *,
    reporting_currency: str,
    translations: Mapping[str, ProjectMoneyTranslation] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
) -> ProjectScreeningResult:
    """Screen canonical project.proposal/v2 through the established economics gate.

    The mature economic/evidence logic remains in the existing v1 bridge. This
    adapter performs the stricter v2 canonical-JSON validation, reuses those
    rules on an internal compatibility view, then restores the digest binding to
    the original v2 proposal bytes. No funding or execution authority is added.
    """

    proposal_digest = project_proposal_v2_digest(proposal)
    compatibility_view = dict(proposal)
    compatibility_view["schema"] = "project.proposal/v1"

    result = screen_project_for_financial_review(
        compatibility_view,
        policy,
        reporting_currency=reporting_currency,
        translations=translations,
        evidence_bundle=evidence_bundle,
    )
    return replace(result, proposal_digest=proposal_digest)
