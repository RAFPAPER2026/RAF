"""Language selection for RAF prompt assets.

``RAF_LANG`` selects the prompt language (``zh`` by default). Chinese prompt
versions live in ``data/prompt_versions/<version>.json``; English versions in
``<version>.en.json`` and fall back to Chinese when missing.
"""

from __future__ import annotations

import os

SUPPORTED_LANGUAGES = ("zh", "en")
LANGUAGE_ENV = "RAF_LANG"
DEFAULT_LANGUAGE = "zh"


def current_language(lang: str | None = None) -> str:
    value = (lang or os.environ.get(LANGUAGE_ENV) or DEFAULT_LANGUAGE).strip().lower()
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language {value!r}; expected one of {SUPPORTED_LANGUAGES}")
    return value


def set_language(lang: str) -> str:
    value = current_language(lang)
    os.environ[LANGUAGE_ENV] = value
    return value
