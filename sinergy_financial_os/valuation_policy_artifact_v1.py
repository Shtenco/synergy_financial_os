from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from .core import AccountingInvariantError
from .numeric import canonical_decimal_text
from .valuation import ValuationPolicy, ValuationRule


SCHEMA = "valuation.policy-artifact/v1"
POLICY_SCHEMA = "valuation-policy/v1"
HEX = frozenset("0123456789abcdef")


class ValuationPolicyArtifactV1Error(AccountingInvariantError):
    pass


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValuationPolicyArtifactV1Error(f"{field_name} is required")
    return value.strip()


def _hex64(value: Any, field_name: str) -> str:
    result = _text(value, field_name).lower()
    if len(result) != 64 or any(c not in HEX for c in result):
        raise ValuationPolicyArtifactV1Error(f"{field_name} must be hex64")
    return result


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValuationPolicyArtifactV1Error(f"{field_name} must be timezone-aware datetime")
    return value.astimezone(UTC)


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ValuationPolicyArtifactV1:
    policy: ValuationPolicy
    generated_at: datetime
    authority: str = "FINANCIAL_OS_VALUATION_POLICY_ARTIFACT"
    valuation_authority: str = "REFERENCE_ONLY"
    execution_authority: str = "NONE"

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ValuationPolicy):
            raise ValuationPolicyArtifactV1Error("policy must be ValuationPolicy")
        if self.authority != "FINANCIAL_OS_VALUATION_POLICY_ARTIFACT":
            raise ValuationPolicyArtifactV1Error("valuation policy artifact authority must remain Financial OS")
        if self.valuation_authority != "REFERENCE_ONLY" or self.execution_authority != "NONE":
            raise ValuationPolicyArtifactV1Error("artifact cannot change valuation policy or execute actions")
        object.__setattr__(self, "generated_at", _utc(self.generated_at, "generated_at"))

    @property
    def valuation_policy_digest(self) -> str:
        return self.policy.digest

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "policy": self.policy.canonical_dict(),
            "valuation_policy_digest": self.valuation_policy_digest,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "authority": self.authority,
            "valuation_authority": self.valuation_authority,
            "execution_authority": self.execution_authority,
        }
        if include_digest:
            payload["digest"] = _digest(payload)
        return payload

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))


def build_valuation_policy_artifact_v1(
    policy: ValuationPolicy,
    *,
    generated_at: datetime,
) -> ValuationPolicyArtifactV1:
    return ValuationPolicyArtifactV1(policy=policy, generated_at=generated_at)


def verify_valuation_policy_artifact_payload_v1(
    payload: Mapping[str, Any],
) -> ValuationPolicyArtifactV1:
    if not isinstance(payload, Mapping) or payload.get("schema") != SCHEMA:
        raise ValuationPolicyArtifactV1Error("unsupported valuation policy artifact schema")
    raw_policy = payload.get("policy")
    if not isinstance(raw_policy, Mapping) or raw_policy.get("schema") != POLICY_SCHEMA:
        raise ValuationPolicyArtifactV1Error("policy must use valuation-policy/v1")
    raw_rules = raw_policy.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValuationPolicyArtifactV1Error("valuation policy requires non-empty rules")
    rules: list[ValuationRule] = []
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, Mapping):
            raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}] must be object")
        staleness = raw.get("max_staleness_seconds")
        if staleness is not None and (isinstance(staleness, bool) or not isinstance(staleness, int)):
            raise ValuationPolicyArtifactV1Error(
                f"policy.rules[{index}].max_staleness_seconds must be integer or null"
            )
        for flag in ("requires_external_enforceability", "requires_intragroup_elimination"):
            if not isinstance(raw.get(flag), bool):
                raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}].{flag} must be boolean")
        rule = ValuationRule(
            valuation_class=_text(raw.get("valuation_class"), f"policy.rules[{index}].valuation_class"),
            hard_factor=Decimal(_text(raw.get("hard_factor"), f"policy.rules[{index}].hard_factor")),
            liquid_factor=Decimal(_text(raw.get("liquid_factor"), f"policy.rules[{index}].liquid_factor")),
            economic_factor=Decimal(_text(raw.get("economic_factor"), f"policy.rules[{index}].economic_factor")),
            price_source_class=_text(raw.get("price_source_class"), f"policy.rules[{index}].price_source_class"),
            requires_external_enforceability=raw["requires_external_enforceability"],
            requires_intragroup_elimination=raw["requires_intragroup_elimination"],
            max_staleness_seconds=staleness,
            notes=raw.get("notes"),
        )
        if raw.get("hard_factor") != canonical_decimal_text(rule.hard_factor):
            raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}].hard_factor is not canonical decimal text")
        if raw.get("liquid_factor") != canonical_decimal_text(rule.liquid_factor):
            raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}].liquid_factor is not canonical decimal text")
        if raw.get("economic_factor") != canonical_decimal_text(rule.economic_factor):
            raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}].economic_factor is not canonical decimal text")
        if dict(raw) != rule.canonical_dict():
            raise ValuationPolicyArtifactV1Error(f"policy.rules[{index}] is not canonical")
        rules.append(rule)

    as_of_text = _text(raw_policy.get("as_of"), "policy.as_of")
    try:
        as_of = datetime.fromisoformat(as_of_text)
    except ValueError as exc:
        raise ValuationPolicyArtifactV1Error("policy.as_of is invalid") from exc
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValuationPolicyArtifactV1Error("policy.as_of must be timezone-aware")
    policy = ValuationPolicy(
        policy_id=_text(raw_policy.get("policy_id"), "policy.policy_id"),
        reporting_currency=_text(raw_policy.get("reporting_currency"), "policy.reporting_currency"),
        as_of=as_of,
        rules=tuple(rules),
    )
    if policy.canonical_dict() != dict(raw_policy):
        raise ValuationPolicyArtifactV1Error("valuation policy body is not canonical")

    generated_text = _text(payload.get("generated_at"), "generated_at")
    if not generated_text.endswith("Z"):
        raise ValuationPolicyArtifactV1Error("generated_at must use canonical UTC Z time")
    try:
        generated = datetime.fromisoformat(generated_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValuationPolicyArtifactV1Error("generated_at is invalid") from exc
    artifact = ValuationPolicyArtifactV1(
        policy=policy,
        generated_at=generated,
        authority=_text(payload.get("authority"), "authority"),
        valuation_authority=_text(payload.get("valuation_authority"), "valuation_authority"),
        execution_authority=_text(payload.get("execution_authority"), "execution_authority"),
    )
    if _hex64(payload.get("valuation_policy_digest"), "valuation_policy_digest") != policy.digest:
        raise ValuationPolicyArtifactV1Error("valuation_policy_digest mismatch")
    if _hex64(payload.get("digest"), "digest") != artifact.digest:
        raise ValuationPolicyArtifactV1Error("valuation policy artifact digest mismatch")
    if artifact.to_dict() != dict(payload):
        raise ValuationPolicyArtifactV1Error("valuation policy artifact payload is not canonical")
    return artifact


def verify_valuation_policy_against_snapshot_v1(
    artifact: ValuationPolicyArtifactV1,
    financial_snapshot: Mapping[str, Any],
) -> bool:
    if financial_snapshot.get("schema") != "financial.snapshot/v2":
        raise ValuationPolicyArtifactV1Error("financial snapshot must use financial.snapshot/v2")
    if financial_snapshot.get("reporting_currency") != artifact.policy.reporting_currency:
        raise ValuationPolicyArtifactV1Error("snapshot/valuation-policy reporting currency mismatch")
    if financial_snapshot.get("valuation_policy_id") != artifact.policy.policy_id:
        raise ValuationPolicyArtifactV1Error("snapshot valuation_policy_id mismatch")
    if _hex64(financial_snapshot.get("valuation_policy_digest"), "snapshot.valuation_policy_digest") != artifact.policy.digest:
        raise ValuationPolicyArtifactV1Error("snapshot valuation_policy_digest mismatch")
    if financial_snapshot.get("valuation_policy_as_of") != artifact.policy.as_of.isoformat():
        raise ValuationPolicyArtifactV1Error("snapshot valuation_policy_as_of mismatch")
    return True
