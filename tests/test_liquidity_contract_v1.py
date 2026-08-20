from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json

import pytest

from sinergy_financial_os.liquidity_contract_v1 import (
    verify_liquidity_replay_payload_v1,
    verify_liquidity_resources_payload_v1,
    verify_maturity_translation_payload_v1,
)
from sinergy_financial_os.liquidity_replay_v1 import LiquidityReplayHorizonV1, LiquidityReplayV1, LiquidityReplayV1Error
from sinergy_financial_os.liquidity_resources_v1 import LiquidityResourceHorizonV1, LiquidityResourcesV1
from sinergy_financial_os.maturity_translation_v1 import MaturityTranslationArtifactV1


def t(hour: int) -> datetime:
    return datetime(2026, 8, 20, hour, 0, tzinfo=UTC)


def test_contract_round_trips_are_content_addressed():
    resources = LiquidityResourcesV1(
        measurement_id="resources", statement_replay_digest="10"*32, affected_period_id="p1",
        as_of=t(2), reporting_currency="USD", account_registry_digest="11"*32,
        valuation_policy_digest="12"*32, liquidity_policy_digest="13"*32,
        horizons=(
            LiquidityResourceHorizonV1(1, Decimal("50"), "14"*32),
            LiquidityResourceHorizonV1(4, Decimal("75"), "15"*32),
            LiquidityResourceHorizonV1(8, Decimal("90"), "16"*32),
        ), generated_at=t(3)
    )
    assert verify_liquidity_resources_payload_v1(resources.to_dict()).digest == resources.digest

    translation = MaturityTranslationArtifactV1(
        maturity_snapshot_digest="17"*32, source_currency="USD", reporting_currency="USD",
        reporting_units_per_source_unit=Decimal("1"), as_of=t(2), translation_evidence_digest=None,
        generated_at=t(3)
    )
    assert verify_maturity_translation_payload_v1(translation.to_dict()).digest == translation.digest

    replay = LiquidityReplayV1(
        replay_id="liquidity", statement_replay_digest="10"*32,
        original_financial_snapshot_digest="18"*32, liquidity_resources_digest=resources.digest,
        maturity_snapshot_digests=("17"*32,), maturity_translation_digests=(translation.digest,),
        affected_period_id="p1", as_of=t(2), reporting_currency="USD",
        restated_liquid_haircut_assets=Decimal("100"),
        horizons=(
            LiquidityReplayHorizonV1(1, Decimal("50"), Decimal("10"), Decimal("5"), Decimal("40")),
            LiquidityReplayHorizonV1(4, Decimal("75"), Decimal("30"), Decimal("2.5"), Decimal("45")),
            LiquidityReplayHorizonV1(8, Decimal("90"), Decimal("60"), Decimal("1.5"), Decimal("30")),
        ), generated_at=t(4)
    )
    assert verify_liquidity_replay_payload_v1(replay.to_dict()).digest == replay.digest


def test_recomputed_outer_hash_cannot_legalize_wrong_lcr():
    replay = LiquidityReplayV1(
        replay_id="liquidity", statement_replay_digest="20"*32,
        original_financial_snapshot_digest="21"*32, liquidity_resources_digest="22"*32,
        maturity_snapshot_digests=("23"*32,), maturity_translation_digests=("24"*32,),
        affected_period_id="p1", as_of=t(2), reporting_currency="USD",
        restated_liquid_haircut_assets=Decimal("100"),
        horizons=(
            LiquidityReplayHorizonV1(1, Decimal("50"), Decimal("10"), Decimal("5"), Decimal("40")),
            LiquidityReplayHorizonV1(4, Decimal("75"), Decimal("30"), Decimal("2.5"), Decimal("45")),
            LiquidityReplayHorizonV1(8, Decimal("90"), Decimal("60"), Decimal("1.5"), Decimal("30")),
        ), generated_at=t(4)
    )
    payload = replay.to_dict()
    payload["horizons"][1]["lcr"] = "9"
    body = dict(payload)
    body.pop("digest")
    payload["digest"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    with pytest.raises(LiquidityReplayV1Error, match="lcr"):
        verify_liquidity_replay_payload_v1(payload)
