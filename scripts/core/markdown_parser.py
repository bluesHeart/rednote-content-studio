#!/usr/bin/env python3
"""
Markdown 解析器

解析 Markdown 文档，提取结构化内容块和图片引用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class BlockType(Enum):
    """内容块类型"""
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    CODE = "code"
    QUOTE = "quote"
    IMAGE = "image"
    HORIZONTAL_RULE = "hr"


@dataclass
class ImageRef:
    """图片引用"""
    alt: str
    path: str
    original_line: str

    @property
    def is_url(self) -> bool:
        """是否为远程 URL"""
        return self.path.startswith(('http://', 'https://'))

    def resolve_path(self, base_dir: Path) -> Path:
        """解析图片的绝对路径（仅用于本地文件）"""
        if self.is_url:
            return Path(self.path)  # URL 原样返回
        img_path = Path(self.path)
        if img_path.is_absolute():
            return img_path
        return (base_dir / img_path).resolve()


@dataclass
class ContentBlock:
    """内容块"""
    type: BlockType
    content: str
    level: int = 0  # 用于标题级别或列表嵌套
    language: str = ""  # 用于代码块
    items: list[str] = field(default_factory=list)  # 用于列表
    image_ref: Optional[ImageRef] = None  # 用于图片块


@dataclass
class ParsedMarkdown:
    """解析后的 Markdown 文档"""
    blocks: list[ContentBlock]
    images: list[ImageRef]
    raw_content: str
    source_path: Optional[Path] = None

    @property
    def text_content(self) -> str:
        """获取纯文本内容（不含图片标记）"""
        texts = []
        for block in self.blocks:
            if block.type == BlockType.IMAGE:
                continue
            if block.type == BlockType.LIST:
                texts.extend(block.items)
            else:
                texts.append(block.content)
        return "\n".join(texts)

    @property
    def char_count(self) -> int:
        """统计字符数"""
        return len(self.text_content)


class MarkdownParser:
    """Markdown 解析器"""

    # 正则表达式模式
    PATTERNS = {
        'heading': re.compile(r'^(#{1,6})\s+(.+)$'),
        'image': re.compile(r'!\[([^\]]*)\]\(([^)]+)\)'),
        'code_block_start': re.compile(r'^```(\w*)$'),
        'code_block_end': re.compile(r'^```$'),
        'list_unordered': re.compile(r'^(\s*)[-*+]\s+(.+)$'),
        'list_ordered': re.compile(r'^(\s*)(\d+)\.\s+(.+)$'),
        'quote': re.compile(r'^>\s*(.*)$'),
        'horizontal_rule': re.compile(r'^[-*_]{3,}$'),
    }

    def __init__(self):
        pass

    def parse(self, content: str, source_path: Optional[Path] = None) -> ParsedMarkdown:
        """解析 Markdown 内容"""
        lines = content.split('\n')
        blocks: list[ContentBlock] = []
        images: list[ImageRef] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 空行跳过
            if not stripped:
                i += 1
                continue

            # 检查代码块
            code_match = self.PATTERNS['code_block_start'].match(stripped)
            if code_match:
                language = code_match.group(1)
                code_lines = []
                i += 1
                while i < len(lines):
                    if self.PATTERNS['code_block_end'].match(lines[i].strip()):
                        i += 1
                        break
                    code_lines.append(lines[i])
                    i += 1
                blocks.append(ContentBlock(
                    type=BlockType.CODE,
                    content='\n'.join(code_lines),
                    language=language,
                ))
                continue

            # 检查标题
            heading_match = self.PATTERNS['heading'].match(stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                blocks.append(ContentBlock(
                    type=BlockType.HEADING,
                    content=text,
                    level=level,
                ))
                i += 1
                continue

            # 检查图片
            image_match = self.PATTERNS['image'].search(stripped)
            if image_match:
                alt = image_match.group(1)
                path = image_match.group(2)
                img_ref = ImageRef(alt=alt, path=path, original_line=stripped)
                images.append(img_ref)
                blocks.append(ContentBlock(
                    type=BlockType.IMAGE,
                    content=stripped,
                    image_ref=img_ref,
                ))
                i += 1
                continue

            # 检查水平分隔线
            if self.PATTERNS['horizontal_rule'].match(stripped):
                blocks.append(ContentBlock(
                    type=BlockType.HORIZONTAL_RULE,
                    content='---',
                ))
                i += 1
                continue

            # 检查引用块
            quote_match = self.PATTERNS['quote'].match(stripped)
            if quote_match:
                quote_lines = [quote_match.group(1)]
                i += 1
                while i < len(lines):
                    qm = self.PATTERNS['quote'].match(lines[i].strip())
                    if qm:
                        quote_lines.append(qm.group(1))
                        i += 1
                    else:
                        break
                blocks.append(ContentBlock(
                    type=BlockType.QUOTE,
                    content='\n'.join(quote_lines),
                ))
                continue

            # 检查无序列表
            ul_match = self.PATTERNS['list_unordered'].match(line)
            if ul_match:
                list_items = [ul_match.group(2)]
                indent_level = len(ul_match.group(1))
                i += 1
                while i < len(lines):
                    next_ul = self.PATTERNS['list_unordered'].match(lines[i])
                    if next_ul and len(next_ul.group(1)) >= indent_level:
                        list_items.append(next_ul.group(2))
                        i += 1
                    elif lines[i].strip() == '':
                        i += 1
                        # 检查下一行是否还是列表
                        if i < len(lines) and self.PATTERNS['list_unordered'].match(lines[i]):
                            continue
                        break
                    else:
                        break
                blocks.append(ContentBlock(
                    type=BlockType.LIST,
                    content='',
                    items=list_items,
                ))
                continue

            # 检查有序列表
            ol_match = self.PATTERNS['list_ordered'].match(line)
            if ol_match:
                list_items = [ol_match.group(3)]
                indent_level = len(ol_match.group(1))
                i += 1
                while i < len(lines):
                    next_ol = self.PATTERNS['list_ordered'].match(lines[i])
                    if next_ol and len(next_ol.group(1)) >= indent_level:
                        list_items.append(next_ol.group(3))
                        i += 1
                    elif lines[i].strip() == '':
                        i += 1
                        if i < len(lines) and self.PATTERNS['list_ordered'].match(lines[i]):
                            continue
                        break
                    else:
                        break
                blocks.append(ContentBlock(
                    type=BlockType.LIST,
                    content='',
                    items=list_items,
                    level=1,  # 标记为有序列表
                ))
                continue

            # 普通段落
            para_lines = [stripped]
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    break
                # 检查是否是新的块级元素
                if (self.PATTERNS['heading'].match(next_line) or
                    self.PATTERNS['code_block_start'].match(next_line) or
                    self.PATTERNS['image'].search(next_line) or
                    self.PATTERNS['quote'].match(next_line) or
                    self.PATTERNS['list_unordered'].match(lines[i]) or
                    self.PATTERNS['list_ordered'].match(lines[i]) or
                    self.PATTERNS['horizontal_rule'].match(next_line)):
                    break
                para_lines.append(next_line)
                i += 1

            blocks.append(ContentBlock(
                type=BlockType.PARAGRAPH,
                content=' '.join(para_lines),
            ))

        return ParsedMarkdown(
            blocks=blocks,
            images=images,
            raw_content=content,
            source_path=source_path,
        )

    def parse_file(self, file_path: Path) -> ParsedMarkdown:
        """解析 Markdown 文件"""
        file_path = Path(file_path)
        content = file_path.read_text(encoding='utf-8')
        return self.parse(content, source_path=file_path)
