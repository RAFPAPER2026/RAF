"""模块化 prompt 系统：7 模块拼接 + 版本管理 + 结构化输出 JSON Schema。

模块顺序固定：role → structure → principles → examples → constraints → capabilities → output。
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .i18n import current_language

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VERSIONS_DIR = DATA_DIR / "prompt_versions"
ACTIVE_VERSION_FILE = DATA_DIR / "active_prompt_version.txt"
CAPABILITIES_FILE = DATA_DIR / "capabilities.txt"
CAPABILITIES_EN_FILE = DATA_DIR / "capabilities.en.txt"

MODULE_ORDER = ["role", "structure", "principles", "examples", "constraints", "capabilities", "output"]
MODULE_NAMES = {
    "role": "角色定义",
    "structure": "量规结构",
    "principles": "设计原则",
    "examples": "示例",
    "constraints": "输出前自检清单",
    "capabilities": "能力项与标签",
    "output": "输出要求",
}

DEFAULT_ACTIVE_VERSION = "v5.10"

# ---------- 能力项（capabilities.txt，格式「名称：说明」） ----------

_capabilities_cache: dict[str, list[str]] = {}
_capabilities_lock = threading.Lock()


def load_capabilities(lang: str | None = None) -> list[str]:
    """读取能力项列表（按语言缓存；英文缺失回退中文）。"""
    language = current_language(lang)
    if language in _capabilities_cache:
        return _capabilities_cache[language]
    with _capabilities_lock:
        if language not in _capabilities_cache:
            path = CAPABILITIES_EN_FILE if language == "en" else CAPABILITIES_FILE
            if not path.exists():
                path = CAPABILITIES_FILE
            if path.exists():
                _capabilities_cache[language] = [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                _capabilities_cache[language] = []
        return _capabilities_cache[language]


def save_capabilities(lines: list[str]) -> list[str]:
    """更新中文能力项文件并同步内存缓存。"""
    with _capabilities_lock:
        cleaned = [line.strip() for line in lines if line.strip()]
        CAPABILITIES_FILE.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
        _capabilities_cache["zh"] = cleaned
    return _capabilities_cache["zh"]


def capability_names(lang: str | None = None) -> list[str]:
    """标签可用值：能力项名称（冒号前的部分）。"""
    names = []
    for line in load_capabilities(lang):
        names.append(line.split("：", 1)[0].split(":", 1)[0].strip())
    return names


# ---------- 版本管理 ----------

def _version_sort_key(version: str):
    m = re.match(r"v(\d+)\.(\d+)", version or "")
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def list_versions() -> list[dict]:
    """列举全部版本（按版本号排序）。"""
    versions = []
    if VERSIONS_DIR.exists():
        for path in sorted(VERSIONS_DIR.glob("v*.json")):
            if path.name.endswith(".en.json"):
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(record, dict) and record.get("version"):
                    record["has_en"] = has_english_version(record["version"])
                    versions.append(record)
            except Exception:
                continue
    versions.sort(key=lambda d: _version_sort_key(d.get("version", "")))
    return versions


def version_path(version: str, lang: str | None = None) -> Path:
    """版本文件路径（en 优先 `<version>.en.json`，缺失回退中文）。"""
    language = current_language(lang)
    if language == "en":
        en_path = VERSIONS_DIR / f"{version}.en.json"
        if en_path.exists():
            return en_path
    return VERSIONS_DIR / f"{version}.json"


def has_english_version(version: str) -> bool:
    return (VERSIONS_DIR / f"{version}.en.json").exists()


def load_version(version: str, lang: str | None = None) -> dict | None:
    path = version_path(version, lang)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else None
    except Exception:
        return None


def save_version(record: dict) -> dict:
    """新增/覆盖版本文件。"""
    record["modules"] = record.get("modules", {})
    for key in MODULE_ORDER:
        record["modules"].setdefault(key, "")
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (VERSIONS_DIR / f"{record['version']}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def get_active_version() -> str:
    """读取当前活跃 prompt 版本（记录在 data/active_prompt_version.txt）。"""
    if ACTIVE_VERSION_FILE.exists():
        v = ACTIVE_VERSION_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    return DEFAULT_ACTIVE_VERSION


def set_active_version(version: str) -> str:
    ACTIVE_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    return version


def diff_versions(version_new: str, version_old: str) -> dict:
    """按模块对比两个版本的差异。"""
    a = load_version(version_new) or {}
    b = load_version(version_old) or {}
    modules = {}
    for key in MODULE_ORDER:
        old_text = b.get("modules", {}).get(key, "")
        new_text = a.get("modules", {}).get(key, "")
        modules[key] = {"changed": old_text != new_text, "old": old_text, "new": new_text}
    return {
        "version_new": version_new,
        "version_old": version_old,
        "changed_modules": [k for k in MODULE_ORDER if modules[k]["changed"]],
        "modules": modules,
    }


def build_system_prompt(version: str | None = None, lang: str | None = None) -> str:
    """按 7 模块固定顺序拼接 system prompt，并注入能力项列表（{capabilities} 替换）。

    lang=en 时优先读取 `<version>.en.json` 与 `capabilities.en.txt`（缺失回退中文）。
    """
    language = current_language(lang)
    v = version or get_active_version()
    record = load_version(v, language)
    if record is None:
        raise ValueError(f"prompt 版本不存在: {v}")
    modules = record.get("modules", {})
    caps_bullets = "\n".join(f"- {line}" for line in load_capabilities(language))
    parts = []
    for key in MODULE_ORDER:
        text = (modules.get(key) or "").replace("{capabilities}", caps_bullets)
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


# ---------- 结构化输出 Schema（strict 模式） ----------

# strict: true 时必须用 $defs + additionalProperties: false；
# $ref 必须用 #/$defs/ 而非内联；tags 在 required 中。
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "rubric_output",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["completion_rubric", "quality_rubric"],
            "properties": {
                "completion_rubric": {"type": "array", "items": {"$ref": "#/$defs/rubric_node"}},
                "quality_rubric": {"type": "array", "items": {"$ref": "#/$defs/weighted_item"}},
            },
            "$defs": {
                "rubric_node": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "name", "combinator", "tags", "children"],
                    "properties": {
                        "type": {"type": "string", "enum": ["leaf", "group"]},
                        "name": {"type": "string"},
                        "combinator": {"type": "string", "enum": ["and", "or"]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "children": {"type": "array", "items": {"$ref": "#/$defs/rubric_node"}},
                    },
                },
                "weighted_item": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["weight", "node"],
                    "properties": {
                        # 两层级权重合法值 {1, 2, 3, 4, 6} = {1×1, 1×2/2×1, 3×1, 2×2, 3×2}
                        "weight": {"type": "number", "enum": [1, 2, 3, 4, 6]},
                        "node": {"$ref": "#/$defs/rubric_node"},
                    },
                },
            },
        },
    },
}
