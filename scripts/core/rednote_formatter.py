#!/usr/bin/env python3
"""
小红书排版格式化器

将内容格式化为小红书风格，包括：
- 使用盲文空格保持空行
- 智能插入 emoji
- 应用分隔线和装饰
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from .markdown_parser import ContentBlock, BlockType
from .content_splitter import PageContent
from .markdown_text_normalizer import MarkdownTextNormalizer

try:
    from ..constants.rednote_chars import (
        BRAILLE_BLANK,
        PARAGRAPH_SEPARATOR,
        make_blank_lines,
        make_numbered_item,
        make_emphasis,
        make_divider,
        make_title,
        NUMBER_EMOJIS,
        LIST_MARKERS,
        QUOTE_MARKS,
    )
    from ..constants.emoji_library import (
        get_emotion_emoji,
        get_scene_emoji,
        get_topic_emoji,
        get_indicator,
        INDICATOR_EMOJIS,
    )
except ImportError:
    from constants.rednote_chars import (
        BRAILLE_BLANK,
        PARAGRAPH_SEPARATOR,
        make_blank_lines,
        make_numbered_item,
        make_emphasis,
        make_divider,
        make_title,
        NUMBER_EMOJIS,
        LIST_MARKERS,
        QUOTE_MARKS,
    )
    from constants.emoji_library import (
        get_emotion_emoji,
        get_scene_emoji,
        get_topic_emoji,
        get_indicator,
        INDICATOR_EMOJIS,
    )

logger = logging.getLogger(__name__)


@dataclass
class FormattedPage:
    """格式化后的页面"""
    page_number: int
    content: str
    char_count: int
    emoji_count: int
    has_proper_spacing: bool
    image_urls: list[str] = None  # 该页关联的图片 URL / 路径
    image_slots: list[int] = None  # 图片在文本块中的插入锚点（块间位置）

    def __post_init__(self):
        if self.image_urls is None:
            self.image_urls = []
        if self.image_slots is None:
            self.image_slots = []


class RedNoteFormatter:
    """小红书排版格式化器"""

    FORMAT_SYSTEM_PROMPT = """你是一个 25 岁的小红书博主，把内容改写成你自己发帖的风格。

你的风格特点：
- 说人话！像跟朋友聊天一样，别端着
- 句子要短，一句话别超过 20 字
- 多换行，看着不累
- emoji 要自然，别硬塞，用就用年轻人爱用的（✨🫠💀😭🤯🔥💡👀🥹等）
- 绝对不要用【】这种老土标注
- 绝对不要用 1️⃣2️⃣3️⃣ 这种数字emoji（太丑了）
- 列表就用 · 或者 - 或者直接换行
- 不要写"记得点赞收藏"之类的（太油腻）
- 不要问"想让我..."这种AI腔
- 如果碰到超长代码块（> 15行），只保留最关键的 5-8 行，加一句"完整代码太长了放评论区"
- 每页总字数控制在 400 字以内！超了就精简

空行用 ⠀ (U+2800 盲文空格)，别用普通空行。

返回JSON：
{
    "title": "改写后的标题（要吸引人但别标题党）",
    "sections": [{"content": "改写后的正文"}],
    "ending": "简短收尾，可以为空"
}"""

    DOCUMENT_CONTINUITY_SYSTEM_PROMPT = """你是同一位小红书作者的“整篇改稿编辑”。
你的任务不是逐页润色，而是把整篇分页草稿重写成“一条连续叙事”的多页图文。

核心要求（必须同时满足）：
1) 页数锁定：输出 pages 数量必须与输入完全一致。
2) 连续叙事：
   - 第1页可以有短标题/钩子。
   - 第2页及以后必须承接上一页，不允许每页都像新开一条帖子。
   - 禁止“重新起题、重复总结、重复开场白”。
3) 小红书节奏：
   - 短句优先，尽量一行一句或两句。
   - 每页用 3-8 个自然换行组织信息，避免整页单段长文。
   - 段落要轻，不写大段说明书式长文。
   - 非步骤页不要整页都写成项目符号列表（避免说明书感）。
   - 语气自然口语化，但不要油腻口播腔。
4) 信息完整：工具名、步骤顺序、关键术语、关键代码片段不能丢。
5) 图片感知：若某页标注有图片，不要把该页写成纯抽象总结，应与该步骤/信息同步。
   - 若输入正文里出现 <IMG_1>、<IMG_2>... 图片锚点，必须原样保留。
   - 每个锚点必须且只能出现一次，顺序不可改变。
   - 锚点应作为独立段落（单独一行）放置在最合适的位置。
6) 清理语法噪声：去掉 Markdown 痕迹（如 **、`、```、[]()）。
7) 篇幅控制：每页建议 180-360 字，允许少量浮动；硬上限 430 字，超出必须主动压缩。

输出格式（严格）：
只输出 JSON，不要输出任何解释文字。
{
  "pages": [
    {"content": "第1页内容"},
    {"content": "第2页内容"}
  ]
}
"""

    BLOCK_SEPARATOR = PARAGRAPH_SEPARATOR
    IMAGE_TOKEN_RE = re.compile(r"<IMG_(\d+)>")

    def __init__(self, llm_client=None, tone_system_prompt: str | None = None):
        """
        初始化格式化器

        Args:
            llm_client: 可选的 LLMClient 实例
            tone_system_prompt: 可选的自定义语气 system prompt，替换默认的 FORMAT_SYSTEM_PROMPT
        """
        self.llm_client = llm_client
        self._tone_system_prompt = tone_system_prompt
        self._normalizer = MarkdownTextNormalizer()

    def _format_heading(self, block: ContentBlock, is_title: bool = False) -> str:
        """格式化标题"""
        text = self._normalizer.normalize_line(block.content)
        return text

    def _format_paragraph(self, block: ContentBlock, context: str = '') -> str:
        """格式化段落"""
        return self._normalizer.normalize_multiline(block.content)

    def _format_list(self, block: ContentBlock) -> str:
        """格式化列表"""
        lines = []
        for item in block.items:
            normalized = self._normalizer.normalize_line(item)
            if normalized.startswith("· "):
                lines.append(normalized)
            else:
                lines.append(f"· {normalized}")
        return '\n'.join(lines)

    def _format_quote(self, block: ContentBlock) -> str:
        """格式化引用"""
        lines = self._normalizer.normalize_multiline(block.content).split('\n')
        formatted_lines = []

        for line in lines:
            if not line.strip():
                continue
            formatted_lines.append(f"{QUOTE_MARKS['line']} {line}")

        return '\n'.join(formatted_lines)

    def _format_code(self, block: ContentBlock) -> str:
        """格式化代码块"""
        return self._normalizer.compact_code_block(block.content, block.language)

    def _format_block(self, block: ContentBlock, is_first: bool = False) -> str:
        """格式化单个内容块"""
        if block.type == BlockType.HEADING:
            return self._format_heading(block, is_title=is_first)
        elif block.type == BlockType.PARAGRAPH:
            return self._format_paragraph(block)
        elif block.type == BlockType.LIST:
            return self._format_list(block)
        elif block.type == BlockType.QUOTE:
            return self._format_quote(block)
        elif block.type == BlockType.CODE:
            return self._format_code(block)
        elif block.type == BlockType.HORIZONTAL_RULE:
            return "—"  # 简洁分隔符
        elif block.type == BlockType.IMAGE:
            # 图片在小红书是单独上传的，这里只返回占位说明
            if block.image_ref:
                return f"[图片: {block.image_ref.alt or '配图'}]"
            return "[图片]"
        else:
            return block.content

    def format_page(self, page: PageContent, use_llm: bool = False) -> FormattedPage:
        """
        格式化单页内容

        Args:
            page: PageContent 对象
            use_llm: 是否使用 LLM 优化格式

        Returns:
            FormattedPage 对象
        """
        formatted_parts: list[str] = []
        emoji_count = 0

        # 收集该页关联的图片 URL（按 markdown 中图片块顺序）
        image_urls: list[str] = []
        image_slots: list[int] = []

        for i, block in enumerate(page.blocks):
            # 图片块：收集 URL 但不输出占位文字
            if block.type == BlockType.IMAGE:
                if block.image_ref:
                    image_urls.append(str(block.image_ref.path))
                    image_slots.append(len(formatted_parts))
                continue

            formatted = self._format_block(block, is_first=(i == 0))
            formatted_parts.append(formatted)

            # 统计 emoji 数量
            emoji_count += len(re.findall(r'[\U0001F300-\U0001F9FF]', formatted))

        # 使用盲文空格连接各部分
        content = self.BLOCK_SEPARATOR.join(formatted_parts)

        # 如果启用 LLM 且可用，进行优化
        if use_llm and self.llm_client:
            content = self._llm_optimize(content, page)

        content = self._normalizer.normalize_rich_text(content, self.BLOCK_SEPARATOR)

        # 若页面内没有显式图片块，回退到 splitter 给的图片列表
        if not image_urls:
            for img in page.images:
                image_urls.append(str(img.path))
                image_slots.append(len(formatted_parts))

        image_slots = self._remap_image_slots(
            image_slots=image_slots,
            original_block_count=len(formatted_parts),
            optimized_content=content,
        )

        return FormattedPage(
            page_number=page.page_number,
            content=content,
            char_count=len(content),
            emoji_count=emoji_count,
            has_proper_spacing=BRAILLE_BLANK in content,
            image_urls=image_urls,
            image_slots=image_slots,
        )

    def _remap_image_slots(
        self,
        image_slots: list[int],
        original_block_count: int,
        optimized_content: str,
    ) -> list[int]:
        """Remap image anchor slots after LLM text rewrite."""
        if not image_slots:
            return []

        old_count = max(1, original_block_count)
        new_count = max(1, len((optimized_content or "").split(self.BLOCK_SEPARATOR)))

        remapped: list[int] = []
        for slot in image_slots:
            ratio = slot / old_count
            mapped = int(round(ratio * new_count))
            mapped = max(0, min(new_count, mapped))
            remapped.append(mapped)

        # Keep stable non-decreasing order.
        for i in range(1, len(remapped)):
            if remapped[i] < remapped[i - 1]:
                remapped[i] = remapped[i - 1]

        return remapped

    @staticmethod
    def _extract_image_tokens(text: str) -> list[int]:
        """Extract ordered image token ids from content text."""
        if not text:
            return []
        token_ids: list[int] = []
        for match in RedNoteFormatter.IMAGE_TOKEN_RE.finditer(text):
            try:
                token_ids.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
        return token_ids

    def _prepare_text_for_token_parse(self, text: str) -> str:
        """Normalize standalone token lines into block separators for robust parsing."""
        if not text:
            return ""

        prepared = re.sub(
            r"(?m)^[ \t]*(<IMG_\d+>)[ \t]*$",
            lambda m: f"{self.BLOCK_SEPARATOR}{m.group(1)}{self.BLOCK_SEPARATOR}",
            text,
        )
        prepared = re.sub(
            rf"{re.escape(self.BLOCK_SEPARATOR)}{{2,}}",
            self.BLOCK_SEPARATOR,
            prepared,
        )
        return prepared

    def _inject_image_tokens(self, content: str, image_slots: list[int], image_count: int) -> str:
        """Inject <IMG_n> anchors into content based on current slots."""
        if image_count <= 0:
            return content or ""

        blocks = [block.strip() for block in (content or "").split(self.BLOCK_SEPARATOR)]
        blocks = [block for block in blocks if block]
        block_count = len(blocks)

        slots = list(image_slots or [])
        if len(slots) < image_count:
            slots.extend([block_count] * (image_count - len(slots)))
        if len(slots) > image_count:
            slots = slots[:image_count]

        normalized_slots: list[int] = []
        prev = 0
        for raw_slot in slots:
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                slot = block_count
            slot = max(0, min(block_count, slot))
            if slot < prev:
                slot = prev
            normalized_slots.append(slot)
            prev = slot

        output_blocks: list[str] = []
        image_idx = 0
        for block_idx in range(block_count + 1):
            while image_idx < image_count and normalized_slots[image_idx] == block_idx:
                output_blocks.append(f"<IMG_{image_idx + 1}>")
                image_idx += 1

            if block_idx < block_count:
                output_blocks.append(blocks[block_idx])

        while image_idx < image_count:
            output_blocks.append(f"<IMG_{image_idx + 1}>")
            image_idx += 1

        return self.BLOCK_SEPARATOR.join(output_blocks)

    def _strip_image_tokens_and_build_slots(
        self,
        content: str,
        image_count: int,
    ) -> tuple[str, list[int]]:
        """Parse <IMG_n> anchors from content and convert them into image slots."""
        if image_count <= 0:
            normalized = self._normalizer.normalize_rich_text(content or "", self.BLOCK_SEPARATOR)
            return normalized, []

        token_ready_content = self._prepare_text_for_token_parse(content or "")
        blocks = [block.strip() for block in token_ready_content.split(self.BLOCK_SEPARATOR)]
        blocks = [block for block in blocks if block]

        token_positions: dict[int, int] = {}
        text_blocks: list[str] = []

        for block in blocks:
            cursor = 0
            has_token = False
            for match in self.IMAGE_TOKEN_RE.finditer(block):
                has_token = True
                prefix = block[cursor:match.start()].strip()
                if prefix:
                    text_blocks.append(prefix)

                try:
                    token_id = int(match.group(1))
                except (TypeError, ValueError):
                    token_id = -1
                if 1 <= token_id <= image_count and token_id not in token_positions:
                    token_positions[token_id] = len(text_blocks)

                cursor = match.end()

            if has_token:
                suffix = block[cursor:].strip()
                if suffix:
                    text_blocks.append(suffix)
                continue

            text_blocks.append(block)

        fallback_slot = len(text_blocks)
        slots: list[int] = []
        prev = 0
        for token_id in range(1, image_count + 1):
            slot = token_positions.get(token_id, fallback_slot)
            slot = max(0, min(fallback_slot, slot))
            if slot < prev:
                slot = prev
            slots.append(slot)
            prev = slot

        text_only_content = self.BLOCK_SEPARATOR.join(text_blocks)
        normalized_content = self._normalizer.normalize_rich_text(text_only_content, self.BLOCK_SEPARATOR)
        if not normalized_content:
            normalized_content = self._normalizer.normalize_rich_text(content or "", self.BLOCK_SEPARATOR)

        return normalized_content, slots

    def _llm_optimize(self, content: str, page: PageContent) -> str:
        """使用 LLM 优化排版"""
        try:
            # 获取图片情感信息
            moods = [img.mood for img in page.images] if page.images else ['neutral']
            dominant_mood = max(set(moods), key=moods.count)

            base_prompt = self._tone_system_prompt or self.FORMAT_SYSTEM_PROMPT
            system_prompt = f"""{base_prompt}

额外上下文（仅供你参考，不要在输出中出现这些元数据）：
- 图片情感：{dominant_mood}
- 是否为封面页：{page.is_cover}

严格要求：输出的 JSON 中只包含排版后的正文内容，禁止出现任何元数据、指令或说明文字。"""

            result = self.llm_client.chat_text(
                system_prompt=system_prompt,
                user_prompt=f"""请优化以下小红书内容的排版，空行必须使用字符 ⠀ (U+2800)。
返回 JSON 格式。

原始内容：
{content}""",
                temperature=0.5,
                max_tokens=2000,
                json_mode=True,
            )

            data = self.llm_client.parse_json(result.content, default={})
            if not isinstance(data, dict):
                data = {}

            # 重建内容
            optimized_parts = []
            if 'title' in data:
                optimized_parts.append(str(data['title']))

            for section in data.get('sections', []):
                if isinstance(section, dict):
                    optimized_parts.append(str(section.get('content', '')))

            if 'ending' in data and data['ending']:
                optimized_parts.append(str(data['ending']))

            if optimized_parts:
                return PARAGRAPH_SEPARATOR.join(optimized_parts)

        except Exception as e:
            logger.warning(f"LLM optimization failed: {e}")

        return content

    def _normalize_formatted_pages(self, pages: list[FormattedPage]) -> list[FormattedPage]:
        """Apply only minimal normalization; avoid local rule-based rewriting."""
        rebuilt: list[FormattedPage] = []
        for page in pages:
            old_content = page.content
            new_content = self._normalizer.normalize_rich_text(old_content or "", self.BLOCK_SEPARATOR)
            if not new_content:
                new_content = old_content

            remapped_slots = list(page.image_slots)

            if len(remapped_slots) != len(page.image_urls):
                old_block_count = max(1, len((old_content or "").split(self.BLOCK_SEPARATOR)))
                remapped_slots = self._remap_image_slots(
                    image_slots=list(page.image_slots),
                    original_block_count=old_block_count,
                    optimized_content=new_content,
                )

            rebuilt.append(
                FormattedPage(
                    page_number=page.page_number,
                    content=new_content,
                    char_count=len(new_content),
                    emoji_count=len(re.findall(r'[\U0001F300-\U0001F9FF]', new_content)),
                    has_proper_spacing=BRAILLE_BLANK in new_content,
                    image_urls=list(page.image_urls),
                    image_slots=remapped_slots,
                )
            )
        return rebuilt

    def optimize_document_pages(
        self,
        pages: list[FormattedPage],
        use_llm: bool = True,
    ) -> list[FormattedPage]:
        """Globally rewrite all pages once to improve cross-page continuity."""
        if not pages:
            return pages
        if not use_llm or not self.llm_client:
            return self._normalize_formatted_pages(pages)

        page_payload = [
            {
                "page_number": page.page_number,
                "content": self._inject_image_tokens(
                    page.content,
                    page.image_slots,
                    len(page.image_urls),
                ),
                "has_images": bool(page.image_urls),
                "image_count": len(page.image_urls),
                "char_count": len(page.content or ""),
            }
            for page in pages
        ]
        payload_json = json.dumps(
            {
                "total_pages": len(pages),
                "pages": page_payload,
                "output_contract": {
                    "must_keep_page_count": True,
                    "style": "single_continuous_story_across_pages",
                    "forbid_restart_after_page_1": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            result = self.llm_client.chat_text(
                system_prompt=self.DOCUMENT_CONTINUITY_SYSTEM_PROMPT,
                user_prompt=(
                    "请基于下面的 JSON 输入重写整篇分页草稿。\n"
                    "关键：第2页开始必须承接，不要每页重新起标题。\n"
                    "请直接输出 JSON（只含 pages 字段）。\n\n"
                    f"{payload_json}"
                ),
                temperature=0.3,
                max_tokens=4000,
                json_mode=True,
            )

            data = self.llm_client.parse_json(result.content, default={})
            if not isinstance(data, dict):
                return pages

            raw_pages = data.get("pages")
            if not isinstance(raw_pages, list):
                return pages

            if len(raw_pages) != len(pages):
                logger.warning(
                    "Document continuity rewrite returned mismatched page count: "
                    f"expected={len(pages)}, got={len(raw_pages)}"
                )
                return pages

            rebuilt_pages: list[FormattedPage] = []
            for idx, old_page in enumerate(pages):
                raw_item = raw_pages[idx]
                content_candidate = ""
                if isinstance(raw_item, dict):
                    content_candidate = str(raw_item.get("content", "")).strip()
                elif isinstance(raw_item, str):
                    content_candidate = raw_item.strip()

                if not content_candidate:
                    content_candidate = old_page.content

                tokenized_fallback = self._inject_image_tokens(
                    old_page.content,
                    old_page.image_slots,
                    len(old_page.image_urls),
                )

                if len(old_page.image_urls) > 0:
                    expected_tokens = [idx + 1 for idx in range(len(old_page.image_urls))]
                    candidate_tokens = self._extract_image_tokens(content_candidate)
                    if candidate_tokens != expected_tokens:
                        logger.warning(
                            "Page %s image tokens invalid, fallback to tokenized source. expected=%s got=%s",
                            old_page.page_number,
                            expected_tokens,
                            candidate_tokens,
                        )
                        content_candidate = tokenized_fallback

                new_content, semantic_slots = self._strip_image_tokens_and_build_slots(
                    content_candidate,
                    image_count=len(old_page.image_urls),
                )
                if not new_content:
                    new_content = old_page.content

                if len(semantic_slots) == len(old_page.image_urls):
                    remapped_slots = semantic_slots
                else:
                    old_block_count = max(1, len((old_page.content or "").split(self.BLOCK_SEPARATOR)))
                    remapped_slots = self._remap_image_slots(
                        image_slots=list(old_page.image_slots),
                        original_block_count=old_block_count,
                        optimized_content=new_content,
                    )

                rebuilt_pages.append(
                    FormattedPage(
                        page_number=old_page.page_number,
                        content=new_content,
                        char_count=len(new_content),
                        emoji_count=len(re.findall(r'[\U0001F300-\U0001F9FF]', new_content)),
                        has_proper_spacing=BRAILLE_BLANK in new_content,
                        image_urls=list(old_page.image_urls),
                        image_slots=remapped_slots,
                    )
                )

            return self._normalize_formatted_pages(rebuilt_pages)

        except Exception as exc:
            logger.warning(f"Document continuity rewrite failed: {exc}")
            return self._normalize_formatted_pages(pages)

    def format_all_pages(
        self,
        pages: list[PageContent],
        use_llm: bool = False
    ) -> list[FormattedPage]:
        """
        格式化所有页面

        Args:
            pages: PageContent 列表
            use_llm: 是否使用 LLM 优化

        Returns:
            FormattedPage 列表
        """
        formatted_pages = []
        for page in pages:
            formatted = self.format_page(page, use_llm=use_llm)
            formatted_pages.append(formatted)
            logger.info(
                f"Page {page.page_number}: {formatted.char_count} chars, "
                f"{formatted.emoji_count} emojis, proper_spacing={formatted.has_proper_spacing}"
            )
        return formatted_pages

    def add_ending(self, formatted_page: FormattedPage, style: str = 'default') -> FormattedPage:
        """
        为页面添加结尾（一般不需要调用）

        Args:
            formatted_page: 格式化后的页面
            style: 结尾风格

        Returns:
            更新后的 FormattedPage
        """
        # 大部分情况不加结尾，内容自然收尾就好
        endings = {
            'default': "",  # 不加结尾
            'simple': f"\n{BRAILLE_BLANK}\n.",
            'question': f"\n{BRAILLE_BLANK}\n你们觉得呢",
        }

        ending = endings.get(style, "")
        if not ending:
            return formatted_page

        new_content = formatted_page.content + ending

        return FormattedPage(
            page_number=formatted_page.page_number,
            content=new_content,
            char_count=len(new_content),
            emoji_count=formatted_page.emoji_count,
            has_proper_spacing=formatted_page.has_proper_spacing,
            image_urls=formatted_page.image_urls,
            image_slots=formatted_page.image_slots,
        )
