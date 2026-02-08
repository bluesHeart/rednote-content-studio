#!/usr/bin/env python3
"""
Unified LLM configuration for OpenAI-compatible APIs.

Prefer setting environment variables:
  - SKILL_LLM_API_KEY
  - SKILL_LLM_BASE_URL
  - SKILL_LLM_MODEL

Fallbacks:
  - OPENAI_API_KEY
  - OPENAI_BASE_URL

Optional local debugging:
  - Load a Python config file that defines:
      config = {"api_key": "...", "base_url": "...", "model": "..."}
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path


def mask_secret(value: str, *, show_last: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= show_last:
        return "*" * len(value)
    return "*" * (len(value) - show_last) + value[-show_last:]


def _first_env(*names: str) -> str | None:
    for name in names:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip()
    return None


def _load_legacy_config_dict(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location("skill_legacy_config", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load config: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    cfg = getattr(module, "config", None)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file does not define dict `config`: {path}")
    return cfg


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    timeout_s: float = 60.0
    max_retries: int = 5
    base_retry_delay_s: float = 1.0
    max_retry_delay_s: float = 20.0

    @classmethod
    def resolve(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        legacy_config_path: Path | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        base_retry_delay_s: float | None = None,
        max_retry_delay_s: float | None = None,
    ) -> "LLMConfig":
        legacy: dict | None = None
        if legacy_config_path is not None:
            legacy = _load_legacy_config_dict(legacy_config_path)

        api_key_final = (
            (api_key.strip() if api_key else None)
            or _first_env("SKILL_LLM_API_KEY", "OPENAI_API_KEY")
            or (str(legacy.get("api_key")).strip() if legacy and legacy.get("api_key") else None)
        )
        base_url_final = (
            (base_url.strip() if base_url else None)
            or _first_env("SKILL_LLM_BASE_URL", "OPENAI_BASE_URL")
            or (str(legacy.get("base_url")).strip() if legacy and legacy.get("base_url") else None)
            or "https://api.openai.com/v1"
        )
        model_final = (
            (model.strip() if model else None)
            or _first_env("SKILL_LLM_MODEL")
            or (str(legacy.get("model")).strip() if legacy and legacy.get("model") else None)
            or "gpt-4o-mini"
        )

        if not api_key_final:
            raise ValueError("Missing API key. Set env SKILL_LLM_API_KEY (or OPENAI_API_KEY).")

        return cls(
            api_key=api_key_final,
            base_url=base_url_final,
            model=model_final,
            timeout_s=timeout_s if timeout_s is not None else 60.0,
            max_retries=max(1, int(max_retries)) if max_retries is not None else 5,
            base_retry_delay_s=base_retry_delay_s if base_retry_delay_s is not None else 1.0,
            max_retry_delay_s=max_retry_delay_s if max_retry_delay_s is not None else 20.0,
        )
