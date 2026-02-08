#!/usr/bin/env python3
"""
智能内容分割器

使用 LLM 智能决定内容分页策略，保持语义完整性。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .markdown_parser import ParsedMarkdown, ContentBlock, BlockType
from .image_analyzer import ImageAnalysis

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """单页内容"""
    page_number: int
    blocks: list[ContentBlock]
    images: list[ImageAnalysis]
    char_count: int
    is_cover: bool = False

    @property
    def text_content(self) -> str:
        """获取纯文本内容"""
        texts = []
        for block in self.blocks:
            if block.type == BlockType.IMAGE:
                continue
            if block.type == BlockType.LIST:
                texts.extend(block.items)
            else:
                texts.append(block.content)
        return "\n".join(texts)


@dataclass
class SplitPlan:
    """分割计划"""
    pages: list[dict]  # 每页包含的块索引和图片索引
    reasoning: str


class ContentSplitter:
    """智能内容分割器"""

    # 字数限制（小红书风格：短平快）
    IDEAL_CHARS = 280  # 理想字数：一屏能看完
    MAX_CHARS = 450    # 最大字数
    MIN_CHARS = 120    # 最小字数（避免页面过短）

    SPLIT_SYSTEM_PROMPT = """你是小红书内容分割专家。把长文拆成多个短页，每页 250-400 字。

分割原则：
1. 一屏能看完！不要堆太多字
2. 标题跟着内容走，别单独一页
3. 短代码块（< 400字）保持完整；超长代码块（> 400字）直接跳过不放进任何页面——小红书放不下大段代码，用户会在评论区贴完整版
4. 列表别拆开

返回JSON：
{
    "pages": [
        {"block_indices": [0, 1], "image_indices": [0], "estimated_chars": 280}
    ],
    "reasoning": "简短理由"
}"""

    def __init__(self, llm_client):
        """
        初始化分割器

        Args:
            llm_client: LLMClient 实例
        """
        self.llm_client = llm_client

    def _estimate_block_chars(self, block: ContentBlock) -> int:
        """估算内容块字数"""
        if block.type == BlockType.IMAGE:
            return 0
        if block.type == BlockType.LIST:
            return sum(len(item) for item in block.items)
        return len(block.content)

    @staticmethod
    def _collect_images_for_blocks(
        blocks: list[ContentBlock],
        image_analyses: list[ImageAnalysis],
    ) -> list[ImageAnalysis]:
        """Collect page images from image blocks in the same order as markdown."""
        if not image_analyses:
            return []

        by_path = {str(img.path): img for img in image_analyses}
        images: list[ImageAnalysis] = []
        seen: set[str] = set()

        for block in blocks:
            if block.type != BlockType.IMAGE or not block.image_ref:
                continue
            path = str(block.image_ref.path)
            if path in seen:
                continue

            analysis = by_path.get(path)
            if analysis is None:
                continue

            images.append(analysis)
            seen.add(path)

        return images

    def _build_content_summary(
        self,
        parsed: ParsedMarkdown,
        image_analyses: list[ImageAnalysis]
    ) -> str:
        """构建内容摘要供 LLM 分析"""
        summary_parts = ["内容块列表："]

        for i, block in enumerate(parsed.blocks):
            chars = self._estimate_block_chars(block)
            if block.type == BlockType.HEADING:
                summary_parts.append(f"[{i}] 标题(H{block.level}): {block.content[:50]}... ({chars}字)")
            elif block.type == BlockType.PARAGRAPH:
                preview = block.content[:100] + "..." if len(block.content) > 100 else block.content
                summary_parts.append(f"[{i}] 段落: {preview} ({chars}字)")
            elif block.type == BlockType.LIST:
                summary_parts.append(f"[{i}] 列表({len(block.items)}项): {chars}字")
            elif block.type == BlockType.QUOTE:
                summary_parts.append(f"[{i}] 引用: {block.content[:50]}... ({chars}字)")
            elif block.type == BlockType.CODE:
                summary_parts.append(f"[{i}] 代码块: {chars}字")
            elif block.type == BlockType.IMAGE:
                summary_parts.append(f"[{i}] 图片引用")
            elif block.type == BlockType.HORIZONTAL_RULE:
                summary_parts.append(f"[{i}] 分隔线")

        summary_parts.append("\n图片分析结果：")
        for i, img in enumerate(image_analyses):
            summary_parts.append(
                f"[{i}] {img.description} (建议位置: {img.suggested_position}, 情感: {img.mood})"
            )

        total_chars = sum(self._estimate_block_chars(b) for b in parsed.blocks)
        summary_parts.append(f"\n总字数: {total_chars}")

        return "\n".join(summary_parts)

    def _simple_split(
        self,
        parsed: ParsedMarkdown,
        image_analyses: list[ImageAnalysis]
    ) -> list[PageContent]:
        """简单分割（当 LLM 不可用时的回退方案）"""
        pages: list[PageContent] = []
        current_blocks: list[ContentBlock] = []
        current_chars = 0
        page_num = 1

        for block in parsed.blocks:
            block_chars = self._estimate_block_chars(block)

            # 检查是否需要新页
            if current_chars + block_chars > self.MAX_CHARS and current_blocks:
                page_images = self._collect_images_for_blocks(current_blocks, image_analyses)

                pages.append(PageContent(
                    page_number=page_num,
                    blocks=current_blocks,
                    images=page_images,
                    char_count=current_chars,
                    is_cover=(page_num == 1),
                ))
                page_num += 1
                current_blocks = []
                current_chars = 0

            current_blocks.append(block)
            current_chars += block_chars

        # 最后一页
        if current_blocks:
            page_images = self._collect_images_for_blocks(current_blocks, image_analyses)

            pages.append(PageContent(
                page_number=page_num,
                blocks=current_blocks,
                images=page_images,
                char_count=current_chars,
                is_cover=(page_num == 1),
            ))

        return pages

    def _is_split_plan_reasonable(
        self,
        pages: list[PageContent],
        total_chars: int,
    ) -> bool:
        """Basic quality gate for LLM split plans."""
        if not pages:
            return False

        # Long content should not collapse to a single giant page.
        if total_chars > self.MAX_CHARS and len(pages) < 2:
            return False

        # Avoid obviously overlong pages from bad plans.
        for page in pages:
            if page.char_count > int(self.MAX_CHARS * 1.6):
                return False

        return True

    def split(
        self,
        parsed: ParsedMarkdown,
        image_analyses: list[ImageAnalysis],
        use_llm: bool = True
    ) -> list[PageContent]:
        """
        智能分割内容

        Args:
            parsed: 解析后的 Markdown
            image_analyses: 图片分析结果
            use_llm: 是否使用 LLM 进行智能分割

        Returns:
            PageContent 列表
        """
        # 如果内容很短，不需要分页
        total_chars = sum(self._estimate_block_chars(b) for b in parsed.blocks)
        if total_chars <= self.MAX_CHARS:
            page_images = self._collect_images_for_blocks(parsed.blocks, image_analyses)
            return [PageContent(
                page_number=1,
                blocks=parsed.blocks,
                images=page_images,
                char_count=total_chars,
                is_cover=True,
            )]

        if not use_llm or self.llm_client is None:
            return self._simple_split(parsed, image_analyses)

        # 使用 LLM 智能分割
        try:
            summary = self._build_content_summary(parsed, image_analyses)

            result = self.llm_client.chat_text(
                system_prompt=self.SPLIT_SYSTEM_PROMPT,
                user_prompt=f"请分析以下内容并给出分页方案：\n\n{summary}",
                temperature=0.3,
                max_tokens=1000,
                json_mode=True,
            )

            plan_data = self.llm_client.parse_json(result.content, default={})
            if not isinstance(plan_data, dict):
                plan_data = {}
            pages: list[PageContent] = []

            used_indices: set[int] = set()
            normalized_pages: list[list[int]] = []

            for page_plan in plan_data.get('pages', []):
                if not isinstance(page_plan, dict):
                    continue

                block_indices = page_plan.get('block_indices', [])
                if not isinstance(block_indices, list):
                    continue

                normalized_indices: list[int] = []
                for raw_idx in block_indices:
                    idx_val: Optional[int] = None
                    if isinstance(raw_idx, int):
                        idx_val = raw_idx
                    elif isinstance(raw_idx, str) and raw_idx.strip().isdigit():
                        idx_val = int(raw_idx.strip())

                    if idx_val is None:
                        continue
                    if not (0 <= idx_val < len(parsed.blocks)):
                        continue
                    if idx_val in used_indices:
                        continue
                    normalized_indices.append(idx_val)
                    used_indices.add(idx_val)

                if normalized_indices:
                    normalized_indices.sort()
                    normalized_pages.append(normalized_indices)

            missing_indices = [idx for idx in range(len(parsed.blocks)) if idx not in used_indices]
            if missing_indices:
                if normalized_pages:
                    normalized_pages[-1].extend(missing_indices)
                else:
                    normalized_pages.append(missing_indices)

            for i, block_indices in enumerate(normalized_pages):
                page_blocks = [parsed.blocks[idx] for idx in block_indices]
                page_images = self._collect_images_for_blocks(page_blocks, image_analyses)

                char_count = sum(self._estimate_block_chars(b) for b in page_blocks)

                pages.append(PageContent(
                    page_number=i + 1,
                    blocks=page_blocks,
                    images=page_images,
                    char_count=char_count,
                    is_cover=(i == 0),
                ))

            if self._is_split_plan_reasonable(pages, total_chars):
                logger.info(f"LLM split into {len(pages)} pages: {plan_data.get('reasoning', '')}")
                return pages

        except Exception as e:
            logger.warning(f"LLM split failed, using simple split: {e}")

        return self._simple_split(parsed, image_analyses)
