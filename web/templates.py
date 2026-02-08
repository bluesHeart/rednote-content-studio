"""
模板系统

定义视觉模板（颜色/样式）和语气模板（system prompt）。
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Visual templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VisualTemplate:
    """视觉模板定义"""
    id: str
    name: str
    description: str
    card_bg: str
    text_color: str
    title_color: str
    accent_color: str
    font_family: str = (
        '"Noto Sans SC", -apple-system, BlinkMacSystemFont, '
        '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    )
    border_radius: str = "12px"
    shadow: str = "0 2px 20px rgba(0,0,0,0.08)"

    def to_style_dict(self) -> dict:
        return {
            "card_bg": self.card_bg,
            "text_color": self.text_color,
            "title_color": self.title_color,
            "accent_color": self.accent_color,
            "font_family": self.font_family,
            "border_radius": self.border_radius,
            "shadow": self.shadow,
        }

    def to_api_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "card_bg": self.card_bg,
            "text_color": self.text_color,
            "title_color": self.title_color,
            "accent_color": self.accent_color,
        }


VISUAL_TEMPLATES: dict[str, VisualTemplate] = {
    "minimal_white": VisualTemplate(
        id="minimal_white",
        name="简约白",
        description="通用，干净清爽",
        card_bg="#fffdf9",
        text_color="#333333",
        title_color="#1a1a1a",
        accent_color="#c0b8a8",
    ),
    "warm": VisualTemplate(
        id="warm",
        name="暖色系",
        description="适合生活/美食/日常",
        card_bg="#faf3e8",
        text_color="#5c4a32",
        title_color="#3d2e1a",
        accent_color="#c4a882",
    ),
    "tech_blue": VisualTemplate(
        id="tech_blue",
        name="科技蓝",
        description="适合编程/科技/数码",
        card_bg="#1a1f2e",
        text_color="#c8d6e5",
        title_color="#e8eef5",
        accent_color="#5b6f8a",
        shadow="0 2px 20px rgba(0,0,0,0.25)",
    ),
    "morandi": VisualTemplate(
        id="morandi",
        name="莫兰迪",
        description="适合穿搭/美妆/生活美学",
        card_bg="#f0e8e3",
        text_color="#6b5b5b",
        title_color="#4a3c3c",
        accent_color="#b5a39a",
    ),
}

DEFAULT_VISUAL_TEMPLATE = "minimal_white"


# ---------------------------------------------------------------------------
# Tone templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToneTemplate:
    """语气模板定义"""
    id: str
    name: str
    description: str
    emoji_examples: str
    system_prompt: str

    def to_api_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "emoji_examples": self.emoji_examples,
        }


TONE_TEMPLATES: dict[str, ToneTemplate] = {
    "casual": ToneTemplate(
        id="casual",
        name="轻松日常",
        description="像跟朋友聊天一样自然",
        emoji_examples="✨🫠😭👀🥹",
        system_prompt="""你是一个 25 岁的小红书博主，把内容改写成你自己发帖的风格。

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
}""",
    ),
    "professional": ToneTemplate(
        id="professional",
        name="专业科普",
        description="深入浅出地讲明白，有干货",
        emoji_examples="💡📊🔬🧐📝",
        system_prompt="""你是一个专业科普博主，擅长把复杂知识用通俗的方式讲清楚。

你的风格特点：
- 有理有据，逻辑清晰
- 用大白话讲专业内容，但不失严谨
- 句子简洁有力，关键概念加粗或用 emoji 标记
- emoji 用科普类的（💡📊🔬🧐📝🔍📌等），不要滥用
- 适当用类比和例子帮助理解
- 绝对不要用【】标注
- 绝对不要用 1️⃣2️⃣3️⃣ 这种数字emoji
- 列表用 · 或 -
- 不要写"记得点赞收藏"
- 如果碰到超长代码块（> 15行），只保留最关键的 5-8 行，加一句"完整代码太长了放评论区"
- 每页总字数控制在 400 字以内

空行用 ⠀ (U+2800 盲文空格)，别用普通空行。

返回JSON：
{
    "title": "改写后的标题（要有信息量）",
    "sections": [{"content": "改写后的正文"}],
    "ending": "简短总结，可以为空"
}""",
    ),
    "hype": ToneTemplate(
        id="hype",
        name="种草安利",
        description="热情推荐，让人想买/想试",
        emoji_examples="🔥💯✨😍🤩",
        system_prompt="""你是一个超有感染力的种草博主，特别会安利好东西。

你的风格特点：
- 热情！让人读了就想试试
- 真实体验感强，用"我用了/我试了/我发现"开头
- 句子短促有力，节奏感强
- emoji 要热情但不浮夸（🔥💯✨😍🤩❗💕🙌等）
- 善用对比（"以前...现在..."、"本来以为...没想到..."）
- 绝对不要用【】标注
- 绝对不要用 1️⃣2️⃣3️⃣ 这种数字emoji
- 列表用 · 或 -
- 不要写"记得点赞收藏"之类的
- 如果碰到超长代码块（> 15行），只保留最关键的 5-8 行，加一句"完整代码太长了放评论区"
- 每页总字数控制在 400 字以内

空行用 ⠀ (U+2800 盲文空格)，别用普通空行。

返回JSON：
{
    "title": "改写后的标题（要有种草感）",
    "sections": [{"content": "改写后的正文"}],
    "ending": "简短收尾，可以为空"
}""",
    ),
    "academic": ToneTemplate(
        id="academic",
        name="学术分享",
        description="严谨但不枯燥的学术风格",
        emoji_examples="📖🎓📌🔍✍️",
        system_prompt="""你是一个学术分享博主，擅长用清晰的结构分享学术内容。

你的风格特点：
- 结构清晰，有条理
- 语言简洁精准，不啰嗦
- 保持学术严谨但不死板
- emoji 用学术类的（📖🎓📌🔍✍️📋🧪📈等），点缀即可
- 重点用加粗或 emoji 标记
- 引用和出处简明标注
- 绝对不要用【】标注
- 绝对不要用 1️⃣2️⃣3️⃣ 这种数字emoji
- 列表用 · 或 -
- 不要写"记得点赞收藏"
- 如果碰到超长代码块（> 15行），只保留最关键的 5-8 行，加一句"完整代码太长了放评论区"
- 每页总字数控制在 400 字以内

空行用 ⠀ (U+2800 盲文空格)，别用普通空行。

返回JSON：
{
    "title": "改写后的标题（简洁有信息量）",
    "sections": [{"content": "改写后的正文"}],
    "ending": "简短总结，可以为空"
}""",
    ),
}

DEFAULT_TONE_TEMPLATE = "casual"


def get_all_templates_api() -> dict:
    """返回所有模板的 API 友好格式"""
    return {
        "visual": [t.to_api_dict() for t in VISUAL_TEMPLATES.values()],
        "tone": [t.to_api_dict() for t in TONE_TEMPLATES.values()],
        "defaults": {
            "visual": DEFAULT_VISUAL_TEMPLATE,
            "tone": DEFAULT_TONE_TEMPLATE,
        },
    }
