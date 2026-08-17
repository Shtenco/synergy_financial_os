import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_source_baseline_has_unique_repository_ref_pairs_and_commit_ids() -> None:
    baseline = load_json("config/source_baseline_20260817.json")
    assert baseline["schema"] == "sinergy.source-baseline/v1"
    seen: set[tuple[str, str]] = set()
    for source in baseline["sources"]:
        key = (source["repository"], source["ref"])
        assert key not in seen
        seen.add(key)
        assert GIT_SHA1.fullmatch(source["commit"])
        assert source["role"]


def test_required_historical_sources_are_bound() -> None:
    baseline = load_json("config/source_baseline_20260817.json")
    repositories = {item["repository"] for item in baseline["sources"]}
    assert {
        "Shtenco/ai_financial_system",
        "Shtenco/synergy_pay_system",
        "Shtenco/synergychain",
        "Shtenco/agi_olga",
        "Shtenco/ai_compress",
        "Shtenco/usds",
        "Shtenco/cashero",
    } <= repositories


def test_versioned_json_schemas_have_unique_ids_and_object_roots() -> None:
    schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
    assert schema_paths
    ids: set[str] = set()
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["$id"] not in ids
        ids.add(schema["$id"])
        assert schema.get("additionalProperties") is False
        assert schema.get("required")
