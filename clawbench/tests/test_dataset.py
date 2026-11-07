"""ClawBench 发布数据集完整性测试（中文原版 + 英文翻译结构一致性）。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS = REPO_ROOT / "tasks"
METADATA = REPO_ROOT / "metadata"

EXPECTED_TASKS = 121
EXPECTED_LEAVES = 1920
EXPECTED_COMPLETION_LEAVES = 666
EXPECTED_QUALITY_LEAVES = 1254
EXPECTED_GROUPS = 533
ALLOWED_WEIGHTS = {1, 2, 3, 4, 6}
LEGACY_FIELDS = (
    "rule_verify",
    "llm_verify",
    "both_verify",
    "prompt_old",
    "scenario_category",
    "ability_category_v2",
)


def _task_dirs() -> list[Path]:
    return sorted(p for p in TASKS.iterdir() if p.is_dir())


def _load_config(task_dir: Path, lang: str = "zh") -> dict:
    name = "config.json" if lang == "zh" else "config.en.json"
    return json.loads((task_dir / name).read_text(encoding="utf-8"))


def _walk_nodes(nodes, stats: dict) -> None:
    for node in nodes:
        if node["type"] == "leaf":
            stats["leaves"] += 1
        else:
            stats["groups"] += 1
            stats["and" if node.get("combinator", "and") == "and" else "or"] += 1
        _walk_nodes(node.get("children") or [], stats)


def _rubric_shape(rubric: dict) -> dict:
    stats = {"leaves": 0, "groups": 0, "and": 0, "or": 0, "top_entries": 0}
    _walk_nodes(rubric["completion_rubric"], stats)
    completion = stats["leaves"]
    for item in rubric["quality_rubric"]:
        _walk_nodes([item["node"]], stats)
    stats["completion_leaves"] = completion
    stats["quality_leaves"] = stats["leaves"] - completion
    stats["top_entries"] = len(rubric["completion_rubric"]) + len(rubric["quality_rubric"])
    return stats


def _node_signature(nodes) -> list:
    signature = []
    for node in nodes:
        signature.append(
            (
                node["id"],
                node["type"],
                node.get("combinator", "and"),
                tuple(_node_signature(node.get("children") or [])),
            )
        )
    return signature


def test_task_set_is_complete():
    dirs = _task_dirs()
    assert len(dirs) == EXPECTED_TASKS
    ids = set()
    for task_dir in dirs:
        config = _load_config(task_dir)
        assert config["id"] == task_dir.name
        assert task_dir.name not in ids
        ids.add(task_dir.name)
        assert config["verifier_type"] == "manual"
        assert config["language"] == "zh"
        assert config["prompt"].strip()
        assert config["prompt"].strip() == config["rubric"]["query"].strip()
        assert config["rubric"]["query_id"] == task_dir.name
        assert not (task_dir / "verifier").exists()
        for field in LEGACY_FIELDS:
            assert field not in config, f"{task_dir.name}: legacy field {field}"


def test_rubric_statistics_match_paper():
    totals = {"leaves": 0, "completion_leaves": 0, "quality_leaves": 0, "groups": 0, "top": []}
    weights = set()
    for task_dir in _task_dirs():
        rubric = _load_config(task_dir)["rubric"]
        stats = _rubric_shape(rubric)
        totals["leaves"] += stats["leaves"]
        totals["completion_leaves"] += stats["completion_leaves"]
        totals["quality_leaves"] += stats["quality_leaves"]
        totals["groups"] += stats["groups"]
        totals["top"].append(stats["top_entries"])
        weights |= {int(item["weight"]) for item in rubric["quality_rubric"]}
    assert totals["leaves"] == EXPECTED_LEAVES
    assert totals["completion_leaves"] == EXPECTED_COMPLETION_LEAVES
    assert totals["quality_leaves"] == EXPECTED_QUALITY_LEAVES
    assert totals["groups"] == EXPECTED_GROUPS
    assert weights <= ALLOWED_WEIGHTS
    assert round(sum(totals["top"]) / len(totals["top"]), 2) == 8.43


def test_skills_metadata():
    expected = {
        "paper_search_1": ["baidu-search"],
        "paper_search_2": ["baidu-search"],
        "image_2_word_1": ["rapid-ocr-reader"],
    }
    for task, skills in expected.items():
        assert _load_config(TASKS / task)["skills"] == skills
    with_skills = [d.name for d in _task_dirs() if _load_config(d)["skills"]]
    assert len(with_skills) == 13


def test_init_env_state_matches_metadata():
    records = [json.loads(line) for line in (METADATA / "tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == EXPECTED_TASKS
    by_id = {record["id"]: record for record in records}
    for task_dir in _task_dirs():
        record = by_id[task_dir.name]
        has_input = any(p.is_file() for p in (task_dir / "init_env").rglob("*"))
        assert record["init_env_state"] == ("has_input" if has_input else "no_input")
        assert record["name_en"]
    assert sum(1 for r in records if r["init_env_state"] == "no_input") == 24


def test_no_sensitive_identifiers_shipped():
    """配置中不得出现内网地址、非示例邮箱或真实密钥；输入清单文件不得随仓库发布。"""
    private_ip = re.compile(r"http://(?!localhost\b|127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}")
    email = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    allowed_domains = {"example.com", "example-internal.com", "example-llm.com"}
    for task_dir in _task_dirs():
        for path in (task_dir / "config.json", task_dir / "config.en.json"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            assert not private_ip.search(text), f"{path}: private IP address"
            for domain in email.findall(text):
                assert domain.lower() in allowed_domains, f"{path}: unexpected email domain {domain}"
    assert not list(TASKS.rglob("已移除的敏感文件清单.md"))


def test_file_cleanup_corpus_has_expected_duplicates():
    download = TASKS / "file_cleanup_01" / "init_env" / "download"
    groups: dict[str, list[str]] = {}
    for path in sorted(download.iterdir()):
        if not path.is_file():
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        groups.setdefault(digest, []).append(path.name)
    duplicates = [names for names in groups.values() if len(names) > 1]
    assert len(duplicates) >= 5
    assert any(len(names) == 3 for names in duplicates)
    assert len(list(download.iterdir())) >= 30


@pytest.mark.parametrize("lang", ["en"])
def test_english_configs_match_chinese_structure(lang):
    en_files = list(TASKS.glob("*/config.en.json"))
    if not en_files:
        pytest.skip("English configs not generated yet")
    assert len(en_files) == EXPECTED_TASKS
    for task_dir in _task_dirs():
        zh = _load_config(task_dir, "zh")
        en = _load_config(task_dir, "en")
        assert en["id"] == zh["id"] == task_dir.name
        assert en["language"] == "en"
        assert en["verifier_type"] == "manual"
        assert en["prompt"].strip() == en["rubric"]["query"].strip()
        assert _rubric_shape(en["rubric"]) == _rubric_shape(zh["rubric"])
        assert _node_signature(en["rubric"]["completion_rubric"]) == _node_signature(
            zh["rubric"]["completion_rubric"]
        )
        assert _node_signature([i["node"] for i in en["rubric"]["quality_rubric"]]) == _node_signature(
            [i["node"] for i in zh["rubric"]["quality_rubric"]]
        )
        assert [i["weight"] for i in en["rubric"]["quality_rubric"]] == [
            i["weight"] for i in zh["rubric"]["quality_rubric"]
        ]


def _node_tags_by_id(rubric: dict) -> dict[str, set[str]]:
    tags: dict[str, set[str]] = {}

    def walk(nodes) -> None:
        for node in nodes:
            tags[node["id"]] = set(node.get("tags") or [])
            walk(node.get("children") or [])

    walk(rubric["completion_rubric"])
    for item in rubric["quality_rubric"]:
        walk([item["node"]])
    return tags


def test_rubric_tags_use_canonical_capabilities():
    taxonomy = json.loads((METADATA / "taxonomy.json").read_text(encoding="utf-8"))
    zh_caps = set(taxonomy["capabilities"])
    en_caps = set(taxonomy["capabilities"].values())
    for task_dir in _task_dirs():
        zh_tags = _node_tags_by_id(_load_config(task_dir)["rubric"])
        en_tags = _node_tags_by_id(_load_config(task_dir, "en")["rubric"])
        for node_id, tags in zh_tags.items():
            assert tags <= zh_caps, f"{task_dir.name}/{node_id}: non-canonical zh tags {tags - zh_caps}"
        for node_id, tags in en_tags.items():
            assert tags <= en_caps, f"{task_dir.name}/{node_id}: non-canonical en tags {tags - en_caps}"
        assert set(zh_tags) == set(en_tags)
        for node_id in zh_tags:
            assert len(zh_tags[node_id]) == len(en_tags[node_id])
