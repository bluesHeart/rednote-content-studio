#!/usr/bin/env python3
"""
Markdown 文本归一化。

职责：
- 统一清洗 Markdown 行内语法（加粗、链接、行内代码等）
- 统一压缩超长代码块，避免卡片可读性崩溃
- 输出稳定的“可渲染纯文本”，作为 formatter / renderer 的共享中间层
"""

from __future__ import annotations

import re


class MarkdownTextNormalizer:
    """Normalize markdown-ish text to readable card text."""

    MAX_CODE_LINES = 8
    MAX_CODE_LINE_CHARS = 92

    _CODE_FENCE_RE = re.compile(r"```(?P<lang>[\w+-]*)\n(?P<code>.*?)```", re.S)
    _IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    _LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    _INLINE_CODE_RE = re.compile(r"`([^`]+)`")
    _BOLD_AST_RE = re.compile(r"\*\*([^*]+)\*\*")
    _BOLD_UNDER_RE = re.compile(r"__([^_]+)__")
    _ITALIC_AST_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
    _ITALIC_UNDER_RE = re.compile(r"(?<!_)_([^_\n]+)_(?!_)")
    _STRIKE_RE = re.compile(r"~~([^~]+)~~")
    _HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
    _QUOTE_RE = re.compile(r"^\s*>+\s*")
    _UL_RE = re.compile(r"^\s*[-*+]\s+")
    _OL_RE = re.compile(r"^\s*\d+[\.)]\s+")
    _WS_RE = re.compile(r"[ \t]{2,}")
    _BRACKET_TAG_RE = re.compile(r"\[([A-Z][A-Z0-9 _:-]{2,})\]")

    def normalize_inline(self, text: str) -> str:
        """Normalize markdown inline syntax in one line."""
        if not text:
            return ""

        normalized = text
        normalized = self._IMAGE_RE.sub(lambda m: (m.group(1) or "配图").strip(), normalized)
        normalized = self._LINK_RE.sub(lambda m: m.group(1).strip(), normalized)
        normalized = self._INLINE_CODE_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._BOLD_AST_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._BOLD_UNDER_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._ITALIC_AST_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._ITALIC_UNDER_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._STRIKE_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._BRACKET_TAG_RE.sub(lambda m: m.group(1), normalized)
        normalized = self._WS_RE.sub(" ", normalized)
        return normalized.strip()

    def normalize_line(self, line: str) -> str:
        """Normalize one markdown line (block-prefix + inline)."""
        if not line:
            return ""

        stripped = line.rstrip()
        if not stripped:
            return ""

        normalized = self._HEADING_RE.sub("", stripped)
        normalized = self._QUOTE_RE.sub("", normalized)

        if self._UL_RE.match(normalized):
            normalized = self._UL_RE.sub("· ", normalized)
        elif self._OL_RE.match(normalized):
            normalized = self._OL_RE.sub("· ", normalized)

        return self.normalize_inline(normalized)

    def normalize_multiline(self, text: str) -> str:
        """Normalize multi-line markdown-ish text and keep compact spacing."""
        if not text:
            return ""

        output_lines: list[str] = []
        prev_blank = False

        for raw_line in text.splitlines():
            normalized = self.normalize_line(raw_line)
            if not normalized:
                if not prev_blank and output_lines:
                    output_lines.append("")
                prev_blank = True
                continue

            output_lines.append(normalized)
            prev_blank = False

        while output_lines and not output_lines[-1]:
            output_lines.pop()

        return "\n".join(output_lines)

    def compact_code_block(self, code: str, language: str = "") -> str:
        """Compact long code blocks into readable excerpts."""
        raw_lines = [(line or "").rstrip() for line in (code or "").splitlines()]
        lines = [line for line in raw_lines if line.strip()]

        if not lines:
            return "代码片段："

        clipped = [self._clip_code_line(line) for line in lines]
        truncated = len(clipped) > self.MAX_CODE_LINES

        if truncated:
            head_count = max(3, self.MAX_CODE_LINES - 3)
            tail_count = 2
            selected = clipped[:head_count] + ["..."] + clipped[-tail_count:]
        else:
            selected = clipped

        label = f"代码片段（{language}）：" if language else "代码片段："
        parts = [label, *selected]
        if truncated:
            parts.append("（代码较长，已截取关键片段）")
        return "\n".join(parts)

    def normalize_rich_text(self, text: str, block_separator: str) -> str:
        """Normalize full page text (including fenced code blocks)."""
        if not text:
            return ""

        def _code_replace(match: re.Match) -> str:
            language = (match.group("lang") or "").strip()
            code = match.group("code") or ""
            return self.compact_code_block(code, language)

        normalized = self._CODE_FENCE_RE.sub(_code_replace, text)

        blocks = normalized.split(block_separator)
        clean_blocks: list[str] = []
        for block in blocks:
            clean = self.normalize_multiline(block)
            if clean:
                clean_blocks.append(clean)

        return block_separator.join(clean_blocks)

    def _clip_code_line(self, line: str) -> str:
        if len(line) <= self.MAX_CODE_LINE_CHARS:
            return line
        return line[: self.MAX_CODE_LINE_CHARS - 1].rstrip() + "…"

