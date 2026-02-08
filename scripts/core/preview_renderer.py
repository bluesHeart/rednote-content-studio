#!/usr/bin/env python3
"""
预览渲染器

将格式化后的内容渲染为小红书卡片样式的预览图和 HTML。
标准尺寸 3:4 (1080×1440)。
"""

from __future__ import annotations

import html
import io
import logging
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .markdown_text_normalizer import MarkdownTextNormalizer

try:
    from ..constants.rednote_chars import PARAGRAPH_SEPARATOR
except ImportError:
    from constants.rednote_chars import PARAGRAPH_SEPARATOR

logger = logging.getLogger(__name__)


# 匹配 emoji 字符的正则
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U000025A0-\U000025FF"
    "\U0000231A-\U0000231B"
    "\U00002934-\U00002935"
    "\U00002B05-\U00002B1C"
    "]+",
)


@dataclass
class PreviewResult:
    """预览渲染结果"""

    image_bytes: bytes
    html_content: str
    width: int
    height: int


class PreviewRenderer:
    """小红书卡片预览渲染器（3:4 比例）"""

    CARD_WIDTH = 1080
    CARD_HEIGHT = 1440

    PADDING_X = 80
    PADDING_TOP = 92
    PADDING_BOTTOM = 74

    FONT_SIZE = 32
    TITLE_FONT_SIZE = 40
    PAGE_FONT_SIZE = 24

    LINE_HEIGHT = 50
    BLOCK_GAP = 24

    IMAGE_MIN_HEIGHT = 180
    IMAGE_MAX_HEIGHT = 320
    IMAGE_CORNER = 22

    HTML_WIDTH = 420
    HTML_HEIGHT = 560

    BLOCK_SEPARATOR = PARAGRAPH_SEPARATOR

    HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>小红书预览 - 第{page_number}页</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap');
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: {font_family};
            background: #e8e8e8;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .rednote-card {{
            width: {html_width}px;
            height: {html_height}px;
            background: {card_bg};
            border-radius: {border_radius};
            box-shadow: {shadow};
            overflow: hidden;
            display: flex;
            flex-direction: column;
            position: relative;
        }}
        .rednote-card-body {{
            flex: 1;
            padding: 24px 26px 34px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .rednote-card-body.no-title {{
            padding-top: 28px;
        }}
        .rednote-title {{
            font-size: 17px;
            font-weight: 700;
            color: {title_color};
            line-height: 1.45;
            margin-bottom: 12px;
        }}
        .rednote-flow {{
            flex: 1;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .rednote-text-block {{
            font-size: 14px;
            line-height: 1.82;
            color: {text_color};
            white-space: pre-wrap;
            word-break: normal;
            overflow-wrap: anywhere;
        }}
        .rednote-image-block {{
            width: 100%;
            border-radius: 10px;
            overflow: hidden;
            background: rgba(0, 0, 0, 0.04);
            min-height: 86px;
        }}
        .rednote-image-block img {{
            width: 100%;
            height: 156px;
            display: block;
            object-fit: cover;
        }}
        .rednote-image-block.is-error {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: {accent_color};
            font-size: 12px;
            letter-spacing: 0.4px;
            min-height: 110px;
        }}
        .rednote-image-block.is-error::after {{
            content: "图片加载失败";
        }}
        .rednote-page-num {{
            position: absolute;
            bottom: 12px;
            right: 20px;
            font-size: 11px;
            color: {accent_color};
            letter-spacing: 0.5px;
        }}
    </style>
</head>
<body>
    <div class="rednote-card">
        <div class="rednote-card-body {body_class}">
            {title_html}
            <div class="rednote-flow">
                {flow_html}
            </div>
        </div>
        <div class="rednote-page-num">{page_number} / {total_pages}</div>
    </div>
</body>
</html>"""

    def __init__(
        self,
        width: int = CARD_WIDTH,
        height: int = CARD_HEIGHT,
        font_path: Optional[str] = None,
        base_dir: Optional[Path] = None,
        visual_style: Optional[dict] = None,
    ):
        self.width = width
        self.height = height
        self.font_path = font_path
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        self._normalizer = MarkdownTextNormalizer()
        self._font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._emoji_font_cache: dict[int, ImageFont.FreeTypeFont | None] = {}

        vs = visual_style or {}
        self._card_bg = vs.get("card_bg", "#fffdf9")
        self._text_color = vs.get("text_color", "#333333")
        self._title_color = vs.get("title_color", "#1a1a1a")
        self._accent_color = vs.get("accent_color", "#c0b8a8")
        self._font_family = vs.get(
            "font_family",
            '"Noto Sans SC", -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        )
        self._border_radius = vs.get("border_radius", "12px")
        self._shadow = vs.get("shadow", "0 2px 20px rgba(0,0,0,0.08)")

        self._img_bg = self._hex_to_rgb(self._card_bg)
        self._img_text = self._hex_to_rgb(self._text_color)
        self._img_title = self._hex_to_rgb(self._title_color)
        self._img_accent = self._hex_to_rgb(self._accent_color)

    def set_base_dir(self, base_dir: Path | None) -> None:
        """Update base directory for resolving local image references."""
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _get_font(self, size: int = FONT_SIZE) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if size in self._font_cache:
            return self._font_cache[size]

        if self.font_path:
            try:
                font = ImageFont.truetype(self.font_path, size)
                self._font_cache[size] = font
                return font
            except Exception as exc:
                logger.warning(f"Failed to load font {self.font_path}: {exc}")

        font_paths = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]

        for path in font_paths:
            if Path(path).exists():
                try:
                    font = ImageFont.truetype(path, size)
                    self._font_cache[size] = font
                    return font
                except Exception:
                    continue

        logger.warning("No Chinese font found, using default font")
        font = ImageFont.load_default()
        self._font_cache[size] = font
        return font

    def _get_emoji_font(self, size: int = FONT_SIZE) -> ImageFont.FreeTypeFont | None:
        if size in self._emoji_font_cache:
            return self._emoji_font_cache[size]

        emoji_paths = [
            "C:/Windows/Fonts/seguiemj.ttf",
            "/System/Library/Fonts/Apple Color Emoji.ttc",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        ]

        for path in emoji_paths:
            if Path(path).exists():
                try:
                    font = ImageFont.truetype(path, size)
                    self._emoji_font_cache[size] = font
                    return font
                except Exception:
                    continue

        self._emoji_font_cache[size] = None
        return None

    @staticmethod
    def _is_emoji(char: str) -> bool:
        return bool(_EMOJI_RE.match(char))

    @staticmethod
    def _measure_text(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> int:
        try:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0]
        except AttributeError:
            return font.getsize(text)[0]

    def _draw_text_with_emoji(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[int, int],
        text: str,
        fill,
        font,
        emoji_font=None,
    ) -> None:
        x, y = xy
        for char in text:
            use_font = emoji_font if emoji_font and self._is_emoji(char) else font
            draw.text((x, y), char, fill=fill, font=use_font)
            x += self._measure_text(use_font, char)

    def _wrap_text(self, text: str, max_width: int, font) -> list[str]:
        lines: list[str] = []

        for paragraph in text.split("\n"):
            paragraph = paragraph.rstrip("⠀").rstrip()
            if not paragraph or paragraph.strip() in ("", "⠀"):
                lines.append("")
                continue

            tokens = self._tokenize_for_wrap(paragraph)
            current_line = ""

            for token in tokens:
                if token.isspace():
                    if not current_line:
                        continue
                    current_line = self._append_wrapped_token(
                        lines=lines,
                        current_line=current_line,
                        token=" ",
                        max_width=max_width,
                        font=font,
                    )
                    continue

                current_line = self._append_wrapped_token(
                    lines=lines,
                    current_line=current_line,
                    token=token,
                    max_width=max_width,
                    font=font,
                )

            if current_line:
                lines.append(current_line.rstrip())

        return lines

    @staticmethod
    def _tokenize_for_wrap(paragraph: str) -> list[str]:
        """Tokenize for wrapping: keep words intact when possible."""
        return re.findall(r"\s+|[A-Za-z0-9][A-Za-z0-9_./:+#@-]*|.", paragraph)

    def _append_wrapped_token(
        self,
        lines: list[str],
        current_line: str,
        token: str,
        max_width: int,
        font,
    ) -> str:
        test_line = current_line + token
        if self._measure_text(font, test_line) <= max_width:
            return test_line

        if current_line.strip():
            lines.append(current_line.rstrip())
            current_line = ""

        if token.isspace():
            return ""

        if self._measure_text(font, token) <= max_width:
            return token

        chunk = ""
        for char in token:
            test_chunk = chunk + char
            if not chunk or self._measure_text(font, test_chunk) <= max_width:
                chunk = test_chunk
                continue

            lines.append(chunk.rstrip())
            chunk = char

        return chunk

    def _split_content_blocks(self, content: str, use_title: bool = True) -> tuple[str, list[str]]:
        normalized_content = self._normalizer.normalize_rich_text(content or "", self.BLOCK_SEPARATOR)
        raw = normalized_content.strip()
        if not raw:
            return "", []

        blocks = [part.strip() for part in raw.split(self.BLOCK_SEPARATOR)]
        blocks = [part for part in blocks if part]

        if not blocks:
            return "", []

        if not use_title:
            return "", blocks

        if len(blocks) == 1:
            first_line, sep, remain = blocks[0].partition("\n")
            title = first_line.strip()
            body_blocks = [remain.strip()] if sep and remain.strip() else []
            return title, body_blocks

        return blocks[0], blocks[1:]

    def _normalize_image_slots(
        self,
        image_urls: list[str],
        image_slots: list[int] | None,
        body_block_count: int,
    ) -> list[int]:
        if not image_urls:
            return []

        total_slots = len(image_urls)
        raw_slots = list(image_slots or [])

        if len(raw_slots) < total_slots:
            raw_slots.extend([body_block_count] * (total_slots - len(raw_slots)))
        if len(raw_slots) > total_slots:
            raw_slots = raw_slots[:total_slots]

        normalized: list[int] = []
        prev = 0
        for raw in raw_slots:
            try:
                slot = int(raw)
            except (TypeError, ValueError):
                slot = body_block_count

            slot = max(0, min(body_block_count, slot))
            if slot < prev:
                slot = prev
            normalized.append(slot)
            prev = slot

        return normalized

    def _build_flow_items(
        self,
        content: str,
        image_urls: list[str] | None,
        image_slots: list[int] | None,
        use_title: bool = True,
    ) -> tuple[str, list[tuple[str, str]]]:
        title, body_blocks = self._split_content_blocks(content, use_title=use_title)
        urls = list(image_urls or [])

        has_title = bool(title)
        total_block_count = (1 if has_title else 0) + len(body_blocks)
        slots = self._normalize_image_slots(urls, image_slots, total_block_count)

        # formatter 里的 image_slots 是“全文块坐标”（含标题块），
        # 渲染流里图片插入锚点使用“正文块坐标”，这里做一次坐标系转换。
        if has_title:
            adjusted_slots: list[int] = []
            for slot in slots:
                mapped = max(0, slot - 1)
                mapped = min(len(body_blocks), mapped)
                adjusted_slots.append(mapped)
            slots = adjusted_slots

        flow_items: list[tuple[str, str]] = []
        img_idx = 0

        for block_idx in range(len(body_blocks) + 1):
            while img_idx < len(urls) and slots[img_idx] == block_idx:
                flow_items.append(("image", urls[img_idx]))
                img_idx += 1

            if block_idx < len(body_blocks):
                flow_items.append(("text", body_blocks[block_idx]))

        while img_idx < len(urls):
            flow_items.append(("image", urls[img_idx]))
            img_idx += 1

        return title, flow_items

    @staticmethod
    def _to_html_src(image_url: str) -> str:
        if image_url.startswith(("http://", "https://", "data:", "/")):
            return image_url

        return image_url.replace("\\", "/")

    def _load_image(self, image_url: str) -> Image.Image | None:
        try:
            if image_url.startswith(("http://", "https://")):
                with urllib.request.urlopen(image_url, timeout=8) as resp:
                    data = resp.read()
                return Image.open(io.BytesIO(data)).convert("RGB")

            if image_url.startswith("/api/images/"):
                staged_path = (self.base_dir / "api_images" / Path(image_url).name).resolve()
                if staged_path.exists() and staged_path.is_file():
                    return Image.open(staged_path).convert("RGB")

            source_path = Path(image_url)
            if not source_path.is_absolute():
                source_path = (self.base_dir / source_path).resolve()
            if not source_path.exists() or not source_path.is_file():
                return None

            return Image.open(source_path).convert("RGB")
        except (OSError, UnidentifiedImageError, ValueError, urllib.error.URLError) as exc:
            logger.debug(f"Failed to load image {image_url}: {exc}")
            return None

    @staticmethod
    def _fit_cover_image(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return Image.new("RGB", (target_w, target_h), (240, 240, 240))

        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))

        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        resized = image.resize((new_w, new_h), resample=resample)

        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))

    def _draw_image_placeholder(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        rect = (x, y, x + width, y + height)
        draw.rounded_rectangle(
            rect,
            radius=self.IMAGE_CORNER,
            fill=(245, 242, 237),
            outline=(228, 224, 216),
            width=2,
        )

        placeholder = "图片加载失败"
        font = self._get_font(24)
        text_w = self._measure_text(font, placeholder)
        text_x = x + max(0, (width - text_w) // 2)
        text_y = y + max(0, (height - 24) // 2)
        draw.text((text_x, text_y), placeholder, fill=self._img_accent, font=font)

    def _draw_inline_image(
        self,
        base_img: Image.Image,
        draw: ImageDraw.ImageDraw,
        image_url: str,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        loaded = self._load_image(image_url)
        if loaded is None:
            self._draw_image_placeholder(draw, x, y, width, height)
            return

        fitted = self._fit_cover_image(loaded, width, height)

        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, width, height), radius=self.IMAGE_CORNER, fill=255)

        base_img.paste(fitted, (x, y), mask)

    def _draw_text_block(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        max_width: int,
        font,
        emoji_font,
        text_color,
        max_y: int,
    ) -> int:
        lines = self._wrap_text(text, max_width, font)
        current_y = y

        for line in lines:
            if line.strip() in ("", "⠀"):
                current_y += self.LINE_HEIGHT // 2
                continue

            if current_y + self.LINE_HEIGHT > max_y:
                return max_y + 1

            self._draw_text_with_emoji(
                draw,
                (x, current_y),
                line,
                fill=text_color,
                font=font,
                emoji_font=emoji_font,
            )
            current_y += self.LINE_HEIGHT

        return current_y

    def _estimate_image_height(self, content_width: int, available_height: int) -> int:
        default_height = int(content_width * 0.62)
        default_height = max(self.IMAGE_MIN_HEIGHT, min(self.IMAGE_MAX_HEIGHT, default_height))
        return min(default_height, available_height)

    def render_to_image(
        self,
        content: str,
        page_number: int = 1,
        image_urls: list[str] | None = None,
        image_slots: list[int] | None = None,
        total_pages: int = 1,
        use_title: bool = True,
    ) -> bytes:
        bg_color = self._img_bg
        text_color = self._img_text
        title_color = self._img_title
        accent_color = self._img_accent

        card_img = Image.new("RGB", (self.width, self.height), color=bg_color)
        draw = ImageDraw.Draw(card_img)

        font = self._get_font(self.FONT_SIZE)
        title_font = self._get_font(self.TITLE_FONT_SIZE)
        emoji_font = self._get_emoji_font(self.FONT_SIZE)
        emoji_title_font = self._get_emoji_font(self.TITLE_FONT_SIZE)

        content_width = self.width - 2 * self.PADDING_X
        title, flow_items = self._build_flow_items(
            content,
            image_urls,
            image_slots,
            use_title=use_title,
        )

        y = self.PADDING_TOP
        max_y = self.height - self.PADDING_BOTTOM - 44

        if title:
            for line in self._wrap_text(title, content_width, title_font):
                if y + int(self.TITLE_FONT_SIZE * 1.5) > max_y:
                    break
                self._draw_text_with_emoji(
                    draw,
                    (self.PADDING_X, y),
                    line,
                    fill=title_color,
                    font=title_font,
                    emoji_font=emoji_title_font,
                )
                y += int(self.TITLE_FONT_SIZE * 1.5)

            y += self.BLOCK_GAP

        for item_type, value in flow_items:
            if y >= max_y:
                break

            if item_type == "text":
                next_y = self._draw_text_block(
                    draw=draw,
                    text=value,
                    x=self.PADDING_X,
                    y=y,
                    max_width=content_width,
                    font=font,
                    emoji_font=emoji_font,
                    text_color=text_color,
                    max_y=max_y,
                )
                if next_y > max_y:
                    break
                y = next_y + self.BLOCK_GAP
                continue

            available = max_y - y
            if available < self.IMAGE_MIN_HEIGHT:
                break

            image_height = self._estimate_image_height(content_width, available)
            self._draw_inline_image(
                base_img=card_img,
                draw=draw,
                image_url=value,
                x=self.PADDING_X,
                y=y,
                width=content_width,
                height=image_height,
            )
            y += image_height + self.BLOCK_GAP

        page_text = f"{page_number}/{max(1, total_pages)}"
        small_font = self._get_font(self.PAGE_FONT_SIZE)
        page_width = self._measure_text(small_font, page_text)
        draw.text(
            (self.width - self.PADDING_X - page_width, self.height - 52),
            page_text,
            fill=accent_color,
            font=small_font,
        )

        buffer = io.BytesIO()
        card_img.save(buffer, format="PNG", quality=95)
        return buffer.getvalue()

    def render_to_html(
        self,
        content: str,
        page_number: int = 1,
        image_urls: list[str] | None = None,
        image_slots: list[int] | None = None,
        total_pages: int = 1,
        use_title: bool = True,
    ) -> str:
        title, flow_items = self._build_flow_items(
            content,
            image_urls,
            image_slots,
            use_title=use_title,
        )

        flow_parts: list[str] = []
        for item_type, value in flow_items:
            if item_type == "text":
                if not value.strip():
                    continue
                flow_parts.append(f'<div class="rednote-text-block">{html.escape(value)}</div>')
            else:
                src = html.escape(self._to_html_src(value), quote=True)
                flow_parts.append(
                    "<div class=\"rednote-image-block\">"
                    f"<img src=\"{src}\" alt=\"配图\" loading=\"lazy\" "
                    "onerror=\"this.parentElement.classList.add('is-error');this.remove();\">"
                    "</div>"
                )

        if not flow_parts:
            flow_parts.append('<div class="rednote-text-block"></div>')

        body_class = "" if title else "no-title"
        title_html = f'<div class="rednote-title">{html.escape(title)}</div>' if title else ""

        return self.HTML_TEMPLATE.format(
            title=html.escape(title or f"第 {page_number} 页"),
            flow_html="".join(flow_parts),
            body_class=body_class,
            title_html=title_html,
            page_number=page_number,
            total_pages=total_pages,
            html_width=self.HTML_WIDTH,
            html_height=self.HTML_HEIGHT,
            card_bg=self._card_bg,
            text_color=self._text_color,
            title_color=self._title_color,
            accent_color=self._accent_color,
            font_family=self._font_family,
            border_radius=self._border_radius,
            shadow=self._shadow,
        )

    def render(
        self,
        content: str,
        page_number: int = 1,
        image_urls: list[str] | None = None,
        image_slots: list[int] | None = None,
        total_pages: int = 1,
        use_title: bool = True,
    ) -> PreviewResult:
        image_bytes = self.render_to_image(
            content=content,
            page_number=page_number,
            image_urls=image_urls,
            image_slots=image_slots,
            total_pages=total_pages,
            use_title=use_title,
        )
        html_content = self.render_to_html(
            content=content,
            page_number=page_number,
            image_urls=image_urls,
            image_slots=image_slots,
            total_pages=total_pages,
            use_title=use_title,
        )
        return PreviewResult(
            image_bytes=image_bytes,
            html_content=html_content,
            width=self.width,
            height=self.height,
        )

    def save_preview(
        self,
        content: str,
        output_dir: Path,
        page_number: int = 1,
        prefix: str = "preview",
        image_urls: list[str] | None = None,
        image_slots: list[int] | None = None,
        total_pages: int = 1,
        use_title: bool = True,
    ) -> tuple[Path, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result = self.render(
            content=content,
            page_number=page_number,
            image_urls=image_urls,
            image_slots=image_slots,
            total_pages=total_pages,
            use_title=use_title,
        )

        img_path = output_dir / f"{prefix}_page_{page_number}.png"
        with open(img_path, "wb") as file_obj:
            file_obj.write(result.image_bytes)

        html_path = output_dir / f"{prefix}_page_{page_number}.html"
        with open(html_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(result.html_content)

        logger.info(f"Preview saved: {img_path}, {html_path}")
        return img_path, html_path

    def terminal_preview(self, content: str, page_number: int = 1) -> None:
        try:
            from rich.console import Console
            from rich.panel import Panel

            console = Console()
            panel = Panel(
                content,
                title=f"第 {page_number} 页",
                border_style="blue",
                padding=(1, 2),
            )
            console.print(panel)
        except ImportError:
            print(f"\n{'=' * 40}")
            print(f"第 {page_number} 页")
            print("=" * 40)
            print(content)
            print("=" * 40)
