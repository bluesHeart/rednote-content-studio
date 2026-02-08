#!/usr/bin/env python3
"""
Minimal OpenAI-compatible LLM client with retries.

Supports:
- Text chat
- Vision chat (image bytes)
- Optional JSON mode (response_format=json_object) with fallback when unsupported
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

try:
    from .config_llm import LLMConfig, mask_secret
except ImportError:
    from config_llm import LLMConfig, mask_secret

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class TransientLLMError(LLMError):
    pass


class PermanentLLMError(LLMError):
    pass


def _is_transient_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    transient_names = {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "APIStatusError",
        "APIError",
    }
    if name in transient_names:
        return True
    msg = str(exc).lower()
    return any(
        s in msg
        for s in [
            "rate limit",
            "timeout",
            "timed out",
            "temporarily",
            "overload",
            "502",
            "503",
            "500",
            "connection reset",
            "connection refused",
            "network",
        ]
    )


def _retry_delay(attempt: int, base_s: float, max_s: float) -> float:
    delay = min(max_s, base_s * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0, min(1.0, delay * 0.1))
    return delay + jitter


@dataclass(frozen=True)
class ChatResult:
    content: str
    raw: Any | None = None


class LLMClient:
    def __init__(self, config: LLMConfig):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Missing dependency: openai. Install with: pip install openai") from e

        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_s,
            default_headers={"User-Agent": "Mozilla/5.0"},
        )

        logger.info(
            "LLM client ready: model=%s base_url=%s api_key=%s",
            config.model,
            config.base_url,
            mask_secret(config.api_key),
        )

    def _call_chat(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise TransientLLMError("Empty response content")
        return ChatResult(content=content, raw=response)

    def _call_with_retry(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> ChatResult:
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self._call_chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            except Exception as e:
                last_error = e

                # Auth is the only truly non-retryable category.
                if type(e).__name__ == "AuthenticationError":
                    raise PermanentLLMError(str(e)) from e

                # JSON mode unsupported: retry once without json_mode.
                msg = str(e).lower()
                if json_mode and any(
                    s in msg for s in ["response_format", "unknown parameter", "unrecognized", "invalid request"]
                ):
                    logger.warning("Provider rejected JSON mode; retrying once without json_mode.")
                    return self._call_chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=False,
                    )

                if attempt >= self.config.max_retries:
                    raise TransientLLMError(str(e)) from e

                if _is_transient_error(e) or isinstance(e, TransientLLMError):
                    delay = _retry_delay(attempt, self.config.base_retry_delay_s, self.config.max_retry_delay_s)
                    logger.warning(
                        "Transient LLM error (%s). Retry %d/%d in %.1fs",
                        type(e).__name__,
                        attempt,
                        self.config.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                raise PermanentLLMError(str(e)) from e

        raise TransientLLMError(str(last_error))

    def chat_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> ChatResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._call_with_retry(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    def chat_with_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        image_mime: str = "image/png",
        temperature: float = 0.0,
        max_tokens: int = 1200,
        json_mode: bool = False,
    ) -> ChatResult:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{image_mime};base64,{image_b64}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        return self._call_with_retry(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Strip a top-level markdown code fence if present."""
        value = (text or "").strip()
        if not value.startswith("```"):
            return value

        lines = value.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return value

    @staticmethod
    def _extract_first_json_block(text: str) -> str | None:
        """Extract first balanced JSON object/array from text."""
        if not text:
            return None

        def _scan(open_char: str, close_char: str) -> str | None:
            start = text.find(open_char)
            while start != -1:
                depth = 0
                in_string = False
                escaped = False

                for idx in range(start, len(text)):
                    ch = text[idx]

                    if in_string:
                        if escaped:
                            escaped = False
                            continue
                        if ch == "\\":
                            escaped = True
                            continue
                        if ch == '"':
                            in_string = False
                        continue

                    if ch == '"':
                        in_string = True
                        continue

                    if ch == open_char:
                        depth += 1
                        continue

                    if ch == close_char:
                        depth -= 1
                        if depth == 0:
                            return text[start: idx + 1]

                start = text.find(open_char, start + 1)
            return None

        # Prefer object first, then array.
        return _scan("{", "}") or _scan("[", "]")

    @staticmethod
    def parse_json(content: str, default: Any | None = None) -> Any:
        """Best-effort JSON parser for imperfect LLM outputs."""
        raw = (content or "").strip()
        if not raw:
            if default is not None:
                return default
            raise ValueError("Empty JSON content")

        candidates: list[str] = []

        stripped = LLMClient._strip_code_fence(raw)
        extracted_from_raw = LLMClient._extract_first_json_block(raw)
        extracted_from_stripped = LLMClient._extract_first_json_block(stripped)

        for candidate in [raw, stripped, extracted_from_raw, extracted_from_stripped]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception:
                continue

        if default is not None:
            return default

        preview = raw[:200].replace("\n", " ")
        raise ValueError(f"Failed to parse JSON from LLM response: {preview}")

    @staticmethod
    def to_json(obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return str(obj)
