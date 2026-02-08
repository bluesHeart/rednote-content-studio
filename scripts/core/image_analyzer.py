#!/usr/bin/env python3
"""
多模态图片分析器

使用 LLM 的视觉能力分析图片内容、情感和建议位置。
"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal
from urllib.parse import urlparse

from PIL import Image
import io

logger = logging.getLogger(__name__)


@dataclass
class ImageAnalysis:
    """图片分析结果"""
    path: str
    description: str
    mood: Literal['warm', 'cool', 'vibrant', 'neutral']
    tags: list[str]
    suggested_position: Literal['cover', 'inline', 'ending']
    width: int
    height: int
    aspect_ratio: float

    @property
    def is_vertical(self) -> bool:
        """是否为竖图"""
        return self.aspect_ratio < 1.0

    @property
    def is_square(self) -> bool:
        """是否为方图"""
        return 0.9 <= self.aspect_ratio <= 1.1


class ImageAnalyzer:
    """多模态图片分析器"""

    ANALYSIS_SYSTEM_PROMPT = """你是一个图片分析专家，专门为小红书内容创作提供图片分析服务。

分析图片并返回JSON格式的结果，包含以下字段：
- description: 图片内容的简短描述（中文，20-50字）
- mood: 图片的情感氛围，只能是以下之一：warm（温暖）、cool（冷静）、vibrant（活力）、neutral（中性）
- tags: 3-5个相关标签（中文）
- suggested_position: 建议在小红书帖子中的位置，只能是以下之一：
  - cover: 适合作为封面图（吸引眼球、主题明确）
  - inline: 适合作为正文配图（补充说明、展示细节）
  - ending: 适合作为结尾图（总结性、号召性）

只返回JSON，不要其他内容。"""

    ANALYSIS_USER_PROMPT = """请分析这张图片，为小红书内容创作提供建议。

返回格式：
{
    "description": "图片描述",
    "mood": "warm|cool|vibrant|neutral",
    "tags": ["标签1", "标签2", "标签3"],
    "suggested_position": "cover|inline|ending"
}"""

    def __init__(self, llm_client):
        """
        初始化分析器

        Args:
            llm_client: LLMClient 实例，需要支持 chat_with_image
        """
        self.llm_client = llm_client

    @staticmethod
    def _is_url(path: str) -> bool:
        """检查路径是否为 URL"""
        return path.startswith(('http://', 'https://'))

    def _download_image(self, url: str) -> tuple[bytes, str]:
        """下载远程图片"""
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower()

        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_bytes = resp.read()
            content_type = resp.headers.get('Content-Type', '')

        # 从 Content-Type 或 URL 后缀推断 MIME 类型
        if 'jpeg' in content_type or 'jpg' in content_type:
            mime_type = 'image/jpeg'
        elif 'png' in content_type:
            mime_type = 'image/png'
        elif 'gif' in content_type:
            mime_type = 'image/gif'
        elif 'webp' in content_type:
            mime_type = 'image/webp'
        else:
            mime_type = mime_map.get(suffix, 'image/png')

        return image_bytes, mime_type

    def _get_image_dimensions_from_bytes(self, image_bytes: bytes) -> tuple[int, int]:
        """从字节获取图片尺寸"""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return img.size
        except Exception as e:
            logger.warning(f"Failed to get image dimensions from bytes: {e}")
            return (0, 0)

    def _get_image_dimensions(self, image_path: Path) -> tuple[int, int]:
        """获取图片尺寸"""
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            logger.warning(f"Failed to get image dimensions for {image_path}: {e}")
            return (0, 0)

    def _load_image_bytes(self, image_path: Path) -> tuple[bytes, str]:
        """加载图片为字节"""
        image_path = Path(image_path)
        suffix = image_path.suffix.lower()

        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }

        mime_type = mime_map.get(suffix, 'image/png')

        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        return image_bytes, mime_type

    def analyze(self, image_path: Path, base_dir: Optional[Path] = None) -> ImageAnalysis:
        """
        分析单张图片（支持本地文件和远程 URL）

        Args:
            image_path: 图片路径或 URL
            base_dir: 基础目录（用于解析相对路径）

        Returns:
            ImageAnalysis 对象
        """
        path_str = str(image_path)
        is_url = self._is_url(path_str)

        # 加载图片字节
        image_bytes: Optional[bytes] = None
        mime_type = 'image/png'
        width, height = 0, 0

        if is_url:
            # 远程图片：下载
            try:
                image_bytes, mime_type = self._download_image(path_str)
                width, height = self._get_image_dimensions_from_bytes(image_bytes)
                logger.info(f"Downloaded image from URL: {path_str[:80]}...")
            except Exception as e:
                logger.warning(f"Failed to download image {path_str[:80]}: {e}")
        else:
            # 本地图片
            local_path = Path(path_str)
            if not local_path.is_absolute() and base_dir:
                local_path = (base_dir / local_path).resolve()

            width, height = self._get_image_dimensions(local_path)

            try:
                image_bytes, mime_type = self._load_image_bytes(local_path)
            except (FileNotFoundError, OSError) as e:
                logger.warning(f"Image not found: {local_path}: {e}")

        aspect_ratio = width / height if height > 0 else 1.0

        # 如果无法加载图片，返回默认分析
        if image_bytes is None:
            return ImageAnalysis(
                path=path_str,
                description="图片无法加载",
                mood='neutral',
                tags=[],
                suggested_position='inline',
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
            )

        # 调用 LLM 分析
        try:
            result = self.llm_client.chat_with_image(
                system_prompt=self.ANALYSIS_SYSTEM_PROMPT,
                user_prompt=self.ANALYSIS_USER_PROMPT,
                image_bytes=image_bytes,
                image_mime=mime_type,
                temperature=0.3,
                max_tokens=500,
                json_mode=True,
            )

            analysis_data = self.llm_client.parse_json(result.content, default={})
            if not isinstance(analysis_data, dict):
                analysis_data = {}

            mood = str(analysis_data.get('mood', 'neutral'))
            if mood not in ('warm', 'cool', 'vibrant', 'neutral'):
                mood = 'neutral'

            suggested_position = str(analysis_data.get('suggested_position', 'inline'))
            if suggested_position not in ('cover', 'inline', 'ending'):
                suggested_position = 'inline'

            tags = analysis_data.get('tags', [])
            if not isinstance(tags, list):
                tags = [str(tags)]

            return ImageAnalysis(
                path=path_str,
                description=str(analysis_data.get('description', '')),
                mood=mood,
                tags=[str(item) for item in tags if str(item).strip()],
                suggested_position=suggested_position,
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
            )

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return ImageAnalysis(
                path=path_str,
                description=f"分析出错: {str(e)}",
                mood='neutral',
                tags=[],
                suggested_position='inline',
                width=width,
                height=height,
                aspect_ratio=aspect_ratio,
            )

    def analyze_multiple(
        self,
        image_refs: list,
        base_dir: Optional[Path] = None
    ) -> list[ImageAnalysis]:
        """
        分析多张图片

        Args:
            image_refs: ImageRef 对象列表或路径列表
            base_dir: 基础目录

        Returns:
            ImageAnalysis 对象列表
        """
        results = []
        for ref in image_refs:
            # 支持 ImageRef 对象和 Path/str
            if hasattr(ref, 'is_url') and ref.is_url:
                path = ref.path  # 保持 URL 字符串
            elif hasattr(ref, 'path'):
                path = ref.path
            else:
                path = ref
            analysis = self.analyze(Path(path) if not self._is_url(str(path)) else path, base_dir)
            results.append(analysis)
            logger.info(f"Analyzed image: {str(path)[:60]} -> {analysis.mood}, {analysis.suggested_position}")
        return results
