"""
Editable story middle-layer helpers.

目标：让 LLM 负责初稿，最后一公里由用户主导。
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from pathlib import Path

from scripts.constants.rednote_chars import BRAILLE_BLANK, PARAGRAPH_SEPARATOR
from scripts.core.preview_renderer import PreviewRenderer, PreviewResult
from scripts.core.rednote_formatter import FormattedPage


ALLOWED_BLOCK_TYPES = {"title", "text", "image"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_story(story: dict, page_count_hint: int | None = None) -> dict:
    """Normalize story payload and keep only supported fields."""
    pages_raw = story.get("pages") if isinstance(story, dict) else None
    if not isinstance(pages_raw, list):
        pages_raw = []

    pages: list[dict] = []
    for page_idx, raw_page in enumerate(pages_raw):
        page_dict = raw_page if isinstance(raw_page, dict) else {}

        try:
            page_number = int(page_dict.get("page_number", page_idx + 1))
        except (TypeError, ValueError):
            page_number = page_idx + 1
        if page_number < 1:
            page_number = page_idx + 1

        blocks_raw = page_dict.get("blocks")
        if not isinstance(blocks_raw, list):
            blocks_raw = []

        blocks: list[dict] = []
        text_seq = 0
        image_seq = 0

        for block_idx, raw_block in enumerate(blocks_raw):
            block_dict = raw_block if isinstance(raw_block, dict) else {}

            block_type = str(block_dict.get("type", "text")).strip().lower()
            if block_type not in ALLOWED_BLOCK_TYPES:
                block_type = "text"

            block_id = str(block_dict.get("id", "")).strip()
            if not block_id:
                if block_type == "image":
                    image_seq += 1
                    block_id = f"p{page_number}_img_{image_seq}"
                elif block_type == "title":
                    text_seq += 1
                    block_id = f"p{page_number}_title_{text_seq}"
                else:
                    text_seq += 1
                    block_id = f"p{page_number}_text_{text_seq}"

            locked = bool(block_dict.get("locked", False))

            if block_type == "image":
                url = str(block_dict.get("url", "")).strip()
                if not url:
                    continue
                blocks.append(
                    {
                        "id": block_id,
                        "type": "image",
                        "url": url,
                        "locked": locked,
                    }
                )
                continue

            text = str(block_dict.get("text", ""))
            blocks.append(
                {
                    "id": block_id,
                    "type": block_type,
                    "text": text,
                    "locked": locked,
                }
            )

        if not blocks:
            blocks = [
                {
                    "id": f"p{page_number}_text_1",
                    "type": "text",
                    "text": "",
                    "locked": False,
                }
            ]

        use_title_default = page_number == 1
        use_title = bool(page_dict.get("use_title", use_title_default))

        pages.append(
            {
                "page_number": page_number,
                "use_title": use_title,
                "locked": bool(page_dict.get("locked", False)),
                "blocks": blocks,
            }
        )

    if page_count_hint and page_count_hint > 0:
        existing = {int(page["page_number"]) for page in pages}
        for page_number in range(1, page_count_hint + 1):
            if page_number in existing:
                continue
            pages.append(
                {
                    "page_number": page_number,
                    "use_title": page_number == 1,
                    "locked": False,
                    "blocks": [
                        {
                            "id": f"p{page_number}_text_1",
                            "type": "text",
                            "text": "",
                            "locked": False,
                        }
                    ],
                }
            )

    pages.sort(key=lambda item: int(item.get("page_number", 0)))

    return {
        "version": 1,
        "type": "editable_story",
        "updated_at": _now_iso(),
        "pages": pages,
    }


def build_story_from_pages(
    pages: list[FormattedPage],
    *,
    base_dir: Path,
    visual_style: dict | None,
) -> dict:
    """Build editable story from formatted pages."""
    renderer = PreviewRenderer(base_dir=base_dir, visual_style=visual_style)

    story_pages: list[dict] = []
    for idx, page in enumerate(pages):
        use_title = idx == 0
        title, flow_items = renderer._build_flow_items(
            page.content,
            page.image_urls,
            page.image_slots,
            use_title=use_title,
        )

        blocks: list[dict] = []
        text_seq = 0
        image_seq = 0

        if use_title and title:
            text_seq += 1
            blocks.append(
                {
                    "id": f"p{page.page_number}_title_{text_seq}",
                    "type": "title",
                    "text": title,
                    "locked": False,
                }
            )

        for item_type, value in flow_items:
            if item_type == "image":
                image_seq += 1
                blocks.append(
                    {
                        "id": f"p{page.page_number}_img_{image_seq}",
                        "type": "image",
                        "url": value,
                        "locked": False,
                    }
                )
                continue

            if not str(value).strip():
                continue
            text_seq += 1
            blocks.append(
                {
                    "id": f"p{page.page_number}_text_{text_seq}",
                    "type": "text",
                    "text": value,
                    "locked": False,
                }
            )

        if not blocks:
            blocks = [
                {
                    "id": f"p{page.page_number}_text_1",
                    "type": "text",
                    "text": page.content,
                    "locked": False,
                }
            ]

        story_pages.append(
            {
                "page_number": page.page_number,
                "use_title": use_title,
                "locked": False,
                "blocks": blocks,
            }
        )

    return sanitize_story({"pages": story_pages}, page_count_hint=len(pages))


def story_to_formatted_pages(story: dict) -> list[FormattedPage]:
    """Compile editable story into renderer-ready FormattedPage list."""
    normalized = sanitize_story(story)
    pages: list[FormattedPage] = []

    for page_idx, page_data in enumerate(normalized.get("pages", []), start=1):
        page_number = int(page_data.get("page_number", page_idx))
        use_title = bool(page_data.get("use_title", page_number == 1))
        blocks = page_data.get("blocks", [])

        title_text = ""
        has_title = False
        body_blocks: list[str] = []
        image_urls: list[str] = []
        image_slots: list[int] = []

        for block in blocks:
            block_type = str(block.get("type", "text")).strip().lower()

            if block_type == "image":
                url = str(block.get("url", "")).strip()
                if not url:
                    continue
                full_slot = len(body_blocks) + (1 if has_title else 0)
                image_urls.append(url)
                image_slots.append(full_slot)
                continue

            text = str(block.get("text", "")).strip()
            if not text:
                continue

            if block_type == "title" and use_title and not has_title:
                title_text = text
                has_title = True
                continue

            body_blocks.append(text)

        if use_title and not has_title and body_blocks:
            title_text = body_blocks.pop(0)
            has_title = True

        content_blocks: list[str] = []
        if has_title and title_text:
            content_blocks.append(title_text)
        content_blocks.extend(body_blocks)

        content = PARAGRAPH_SEPARATOR.join(content_blocks).strip()
        if not content:
            content = title_text if title_text else ""

        pages.append(
            FormattedPage(
                page_number=page_number,
                content=content,
                char_count=len(content),
                emoji_count=len(re.findall(r"[\U0001F300-\U0001F9FF]", content)),
                has_proper_spacing=BRAILLE_BLANK in content,
                image_urls=image_urls,
                image_slots=image_slots,
            )
        )

    pages.sort(key=lambda page: page.page_number)
    return pages


def render_previews(
    pages: list[FormattedPage],
    *,
    base_dir: Path,
    visual_style: dict | None,
) -> tuple[list[PreviewResult], PreviewRenderer]:
    """Render page previews from formatted pages."""
    renderer = PreviewRenderer(base_dir=base_dir, visual_style=visual_style)
    previews: list[PreviewResult] = []
    total_pages = len(pages)

    for idx, page in enumerate(pages, start=1):
        previews.append(
            renderer.render(
                content=page.content,
                page_number=idx,
                image_urls=page.image_urls,
                image_slots=page.image_slots,
                total_pages=total_pages,
                use_title=(idx == 1),
            )
        )

    return previews, renderer


def build_combined_html(pages: list[FormattedPage], renderer: PreviewRenderer) -> str:
    """Generate combined horizontal preview HTML."""
    total = len(pages)
    cards_html: list[str] = []

    for idx, page in enumerate(pages, start=1):
        card_html = renderer.render_to_html(
            content=page.content,
            page_number=idx,
            image_urls=page.image_urls,
            image_slots=page.image_slots,
            total_pages=total,
            use_title=(idx == 1),
        )
        escaped_card_html = html.escape(card_html, quote=True)
        cards_html.append(f'<iframe class="card-frame" srcdoc="{escaped_card_html}"></iframe>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>小红书排版预览</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: "Noto Sans SC", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f0ede8;
            min-height: 100vh;
            padding: 40px 24px;
        }}
        .header {{ text-align: center; margin-bottom: 32px; }}
        .header h1 {{ font-size: 20px; font-weight: 500; color: #333; letter-spacing: 1px; }}
        .header p {{ font-size: 13px; color: #999; margin-top: 6px; }}
        .cards {{
            display: flex;
            gap: 24px;
            overflow-x: auto;
            padding: 8px 0 24px;
        }}
        .card-frame {{
            width: 420px;
            height: 560px;
            border: 0;
            border-radius: 14px;
            background: #fff;
            box-shadow: 0 10px 24px rgba(0,0,0,0.10);
            flex: 0 0 auto;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>小红书排版预览</h1>
        <p>共 {total} 页 · 左右滑动查看</p>
    </div>
    <div class="cards">
        {''.join(cards_html)}
    </div>
</body>
</html>"""

