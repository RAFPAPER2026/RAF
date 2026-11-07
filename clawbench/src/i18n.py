"""Language selection shared by the evaluation harness.

The active language is resolved from (in order): explicit argument, the
``CLAWBENCH_LANG`` environment variable, then ``zh``.  ``config.json`` is the
Chinese task definition and ``config.en.json`` the English one; English falls
back to Chinese when the translated file is missing.
"""

from __future__ import annotations

import os

SUPPORTED_LANGUAGES = ("zh", "en")
LANGUAGE_ENV = "CLAWBENCH_LANG"
DEFAULT_LANGUAGE = "zh"


def current_language(lang: str | None = None) -> str:
    value = (lang or os.environ.get(LANGUAGE_ENV) or DEFAULT_LANGUAGE).strip().lower()
    if value not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"unsupported language {value!r}; expected one of {SUPPORTED_LANGUAGES}"
        )
    return value


def set_language(lang: str) -> str:
    value = current_language(lang)
    os.environ[LANGUAGE_ENV] = value
    return value
