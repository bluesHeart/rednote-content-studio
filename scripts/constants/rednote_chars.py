#!/usr/bin/env python3
"""
小红书特殊字符常量

核心解决方案：使用盲文空格字符 (U+2800) 来保持空行，
因为小红书会自动吞掉普通的空行。
"""

# 盲文空格 - 小红书不会吞掉的空白字符
BRAILLE_BLANK = '⠀'  # U+2800

# 分隔线样式
DIVIDERS = {
    'thin': '━' * 20,
    'double': '═' * 20,
    'dotted': '·' * 20,
    'wave': '〰' * 10,
    'star': '✦' * 10,
    'heart': '♡' * 10,
    'diamond': '◇' * 10,
    'arrow': '➤' * 10,
}

# 数字 emoji (1-10)
NUMBER_EMOJIS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

# 重点标记
EMPHASIS_MARKS = {
    'bracket': ('【', '】'),
    'star': ('⭐', '⭐'),
    'fire': ('🔥', '🔥'),
    'point': ('👉', ''),
    'check': ('✅', ''),
    'spark': ('✨', '✨'),
}

# 列表项标记
LIST_MARKERS = {
    'dot': '•',
    'star': '★',
    'arrow': '➜',
    'check': '✓',
    'diamond': '◆',
    'heart': '♥',
    'flower': '❀',
}

# 引用标记
QUOTE_MARKS = {
    'line': '｜',
    'double_line': '‖',
    'bracket': '「',
    'bracket_end': '」',
    'guillemet': '»',
}

# 小红书推荐的标题装饰
TITLE_DECORATIONS = [
    ('📝', ''),
    ('💡', ''),
    ('🎯', ''),
    ('📌', ''),
    ('🔖', ''),
    ('✨', '✨'),
    ('🌟', '🌟'),
]

# 结尾装饰
ENDING_DECORATIONS = [
    '感谢阅读 ❤️',
    '喜欢请点赞收藏 🙏',
    '关注我获取更多内容 ✨',
    '有问题评论区见 💬',
]

# 常用标签前缀
TAG_PREFIX = '#'

# 空行模板（使用盲文空格）
BLANK_LINE = BRAILLE_BLANK

# 段落间隔模板
PARAGRAPH_SEPARATOR = f"\n{BRAILLE_BLANK}\n"

# 格式化函数
def make_blank_lines(count: int = 1) -> str:
    """生成指定数量的空行（使用盲文空格）"""
    return '\n'.join([BRAILLE_BLANK] * count)


def make_numbered_item(index: int, text: str) -> str:
    """生成带数字emoji的列表项"""
    if 1 <= index <= 10:
        return f"{NUMBER_EMOJIS[index - 1]} {text}"
    return f"{index}. {text}"


def make_emphasis(text: str, style: str = 'bracket') -> str:
    """添加重点标记"""
    marks = EMPHASIS_MARKS.get(style, EMPHASIS_MARKS['bracket'])
    return f"{marks[0]}{text}{marks[1]}"


def make_divider(style: str = 'thin') -> str:
    """生成分隔线"""
    return DIVIDERS.get(style, DIVIDERS['thin'])


def make_title(text: str, decoration_index: int = 0) -> str:
    """生成装饰标题"""
    if 0 <= decoration_index < len(TITLE_DECORATIONS):
        prefix, suffix = TITLE_DECORATIONS[decoration_index]
        return f"{prefix} {text} {suffix}".strip()
    return text
