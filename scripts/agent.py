#!/usr/bin/env python3
"""
智能体协调器

协调各模块执行完整的 Markdown 转小红书排版流程。
核心创新：视觉反馈循环 - LLM 像人一样"看到"排版效果并迭代优化。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

try:
    from .config_llm import LLMConfig
    from .client import LLMClient
    from .core.markdown_parser import MarkdownParser, ParsedMarkdown
    from .core.image_analyzer import ImageAnalyzer, ImageAnalysis
    from .core.content_splitter import ContentSplitter
    from .core.rednote_formatter import RedNoteFormatter, FormattedPage
    from .core.preview_renderer import PreviewRenderer, PreviewResult
except ImportError:
    from config_llm import LLMConfig
    from client import LLMClient
    from core.markdown_parser import MarkdownParser, ParsedMarkdown
    from core.image_analyzer import ImageAnalyzer, ImageAnalysis
    from core.content_splitter import ContentSplitter
    from core.rednote_formatter import RedNoteFormatter, FormattedPage
    from core.preview_renderer import PreviewRenderer, PreviewResult

logger = logging.getLogger(__name__)


@dataclass
class VisualReview:
    """视觉审查结果"""
    score: int  # 1-10
    issues: list[str]
    suggestions: list[str]
    pass_threshold: bool


@dataclass
class ConversionResult:
    """转换结果"""
    pages: list[FormattedPage]
    previews: list[PreviewResult]
    reviews: list[VisualReview]
    iterations: int
    image_analyses: list[ImageAnalysis]
    output_files: dict[str, Path] = field(default_factory=dict)


class RedNoteAgent:
    """小红书排版智能体"""

    DEFAULT_MAX_ITERATIONS = 3
    PASS_SCORE_THRESHOLD = 7

    REVIEW_SYSTEM_PROMPT = """你是一个小红书排版审查专家，负责评估排版效果。

请查看预览图片，评估以下方面：
1. 空行效果：空行是否正确显示（不被吞掉）
2. Emoji 使用：是否恰当、不过度
3. 可读性：文字是否清晰、段落分明
4. 美感：整体视觉效果是否舒适

返回JSON格式：
{
    "score": 8,  // 1-10分
    "issues": ["问题1", "问题2"],  // 发现的问题
    "suggestions": ["建议1", "建议2"]  // 改进建议
}

如果评分>=7分，说明排版合格。"""

    REVIEW_USER_PROMPT = """请审查这张小红书排版预览图。

评估空行效果、emoji使用、可读性和美感。
返回JSON格式的评分和建议。"""

    OPTIMIZE_SYSTEM_PROMPT = """你是一个小红书排版优化专家。
根据审查反馈优化排版内容。

优化原则：
1. 修复指出的问题
2. 采纳改进建议
3. 保持内容不变，只优化格式
4. 空行使用字符 ⠀ (U+2800 盲文空格)

返回优化后的纯文本内容，可直接复制到小红书。"""

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        output_dir: Optional[Path] = None,
        tone_system_prompt: Optional[str] = None,
        visual_style: Optional[dict] = None,
    ):
        """
        初始化智能体

        Args:
            llm_config: LLM 配置（可选，不提供则从环境变量读取）
            max_iterations: 最大迭代次数
            output_dir: 输出目录
            tone_system_prompt: 可选的自定义语气 system prompt
            visual_style: 可选的视觉样式字典
        """
        self.max_iterations = max_iterations
        self.output_dir = Path(output_dir) if output_dir else Path("./output")

        # 初始化 LLM 客户端
        if llm_config is None:
            llm_config = LLMConfig.resolve()
        self.llm_client = LLMClient(llm_config)

        # 初始化各模块
        self.parser = MarkdownParser()
        self.image_analyzer = ImageAnalyzer(self.llm_client)
        self.content_splitter = ContentSplitter(self.llm_client)
        self.formatter = RedNoteFormatter(self.llm_client, tone_system_prompt=tone_system_prompt)
        self.renderer = PreviewRenderer(base_dir=self.output_dir, visual_style=visual_style)

    @staticmethod
    def _resolve_image_analysis_target(image_path: str, base_dir: Path) -> str | Path:
        """Resolve image path for analysis while preserving original reference path."""
        if image_path.startswith(("http://", "https://")):
            return image_path

        if image_path.startswith("/api/images/"):
            staged_path = (base_dir / "api_images" / Path(image_path).name).resolve()
            if staged_path.exists():
                return staged_path

        return Path(image_path)

    def _visual_review(self, preview: PreviewResult, page_number: int) -> VisualReview:
        """
        视觉审查预览图

        Args:
            preview: 预览结果
            page_number: 页码

        Returns:
            VisualReview 对象
        """
        try:
            result = self.llm_client.chat_with_image(
                system_prompt=self.REVIEW_SYSTEM_PROMPT,
                user_prompt=self.REVIEW_USER_PROMPT,
                image_bytes=preview.image_bytes,
                image_mime="image/png",
                temperature=0.3,
                max_tokens=500,
                json_mode=True,
            )

            data = self.llm_client.parse_json(result.content, default={})
            if not isinstance(data, dict):
                data = {}

            try:
                score = int(float(data.get('score', 5)))
            except Exception:
                score = 5
            score = max(1, min(10, score))

            issues = data.get('issues', [])
            if not isinstance(issues, list):
                issues = [str(issues)]

            suggestions = data.get('suggestions', [])
            if not isinstance(suggestions, list):
                suggestions = [str(suggestions)]

            return VisualReview(
                score=score,
                issues=[str(item) for item in issues if str(item).strip()],
                suggestions=[str(item) for item in suggestions if str(item).strip()],
                pass_threshold=score >= self.PASS_SCORE_THRESHOLD,
            )

        except Exception as e:
            logger.warning(f"Visual review failed for page {page_number}: {e}")
            # 回退：假设通过
            return VisualReview(
                score=7,
                issues=[f"审查失败: {str(e)}"],
                suggestions=[],
                pass_threshold=True,
            )

    def _optimize_content(
        self,
        content: str,
        review: VisualReview,
        page_number: int
    ) -> str:
        """
        根据审查反馈优化内容

        Args:
            content: 原始格式化内容
            review: 审查结果
            page_number: 页码

        Returns:
            优化后的内容
        """
        try:
            feedback = f"""审查评分：{review.score}/10

发现的问题：
{chr(10).join(f'- {issue}' for issue in review.issues) if review.issues else '无'}

改进建议：
{chr(10).join(f'- {sug}' for sug in review.suggestions) if review.suggestions else '无'}"""

            result = self.llm_client.chat_text(
                system_prompt=self.OPTIMIZE_SYSTEM_PROMPT,
                user_prompt=f"""原始内容：
{content}

审查反馈：
{feedback}

请优化后返回新的内容，保持语义不变。
记住空行要用字符 ⠀ (U+2800)。""",
                temperature=0.5,
                max_tokens=2000,
            )

            optimized = result.content.strip()
            if optimized:
                logger.info(f"Page {page_number} optimized based on review")
                return optimized

        except Exception as e:
            logger.warning(f"Content optimization failed for page {page_number}: {e}")

        return content

    def _save_results(
        self,
        result: ConversionResult,
        source_name: str
    ) -> dict[str, Path]:
        """
        保存转换结果

        Args:
            result: 转换结果
            source_name: 源文件名

        Returns:
            输出文件路径字典
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_files: dict[str, Path] = {}

        # 保存每页文本
        for page in result.pages:
            txt_path = self.output_dir / f"page_{page.page_number}.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(page.content)
            output_files[f'page_{page.page_number}_txt'] = txt_path

        # 保存每页预览
        for i, preview in enumerate(result.previews):
            page_num = i + 1

            img_path = self.output_dir / f"preview_page_{page_num}.png"
            with open(img_path, 'wb') as f:
                f.write(preview.image_bytes)
            output_files[f'page_{page_num}_png'] = img_path

            html_path = self.output_dir / f"preview_page_{page_num}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(preview.html_content)
            output_files[f'page_{page_num}_html'] = html_path

        # 保存合并的 HTML 预览
        combined_html = self._generate_combined_html(result)
        combined_path = self.output_dir / "preview.html"
        with open(combined_path, 'w', encoding='utf-8') as f:
            f.write(combined_html)
        output_files['preview_html'] = combined_path

        # 保存 JSON 数据
        json_data = {
            'source': source_name,
            'total_pages': len(result.pages),
            'iterations': result.iterations,
            'pages': [
                {
                    'page_number': page.page_number,
                    'char_count': page.char_count,
                    'emoji_count': page.emoji_count,
                    'has_proper_spacing': page.has_proper_spacing,
                    'image_urls': list(page.image_urls),
                    'image_slots': list(page.image_slots),
                    'content': page.content,
                }
                for page in result.pages
            ],
            'reviews': [
                {
                    'score': review.score,
                    'issues': review.issues,
                    'suggestions': review.suggestions,
                    'passed': review.pass_threshold,
                }
                for review in result.reviews
            ],
            'image_analyses': [
                {
                    'path': img.path,
                    'description': img.description,
                    'mood': img.mood,
                    'tags': img.tags,
                    'suggested_position': img.suggested_position,
                }
                for img in result.image_analyses
            ],
        }

        json_path = self.output_dir / "result.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        output_files['result_json'] = json_path

        return output_files

    def _generate_combined_html(self, result: ConversionResult) -> str:
        """生成合并的 HTML 预览（统一使用 PreviewRenderer 输出）"""
        import html as html_mod

        total = len(result.pages)
        cards_html: list[str] = []

        for idx, page in enumerate(result.pages):
            card_html = self.renderer.render_to_html(
                content=page.content,
                page_number=idx + 1,
                image_urls=page.image_urls,
                image_slots=page.image_slots,
                total_pages=total,
                use_title=(idx == 0),
            )
            escaped_card_html = html_mod.escape(card_html, quote=True)
            cards_html.append(f'<iframe class="card-frame" srcdoc="{escaped_card_html}"></iframe>')

        return f'''<!DOCTYPE html>
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
            scroll-snap-type: x mandatory;
            -webkit-overflow-scrolling: touch;
        }}
        .cards::-webkit-scrollbar {{ height: 4px; }}
        .cards::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 2px; }}
        .card-frame {{
            flex: 0 0 420px;
            width: 420px;
            height: 560px;
            border: 0;
            border-radius: 12px;
            overflow: hidden;
            background: #fffdf9;
            box-shadow: 0 2px 16px rgba(0,0,0,0.06);
            scroll-snap-align: center;
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
</html>'''

    @staticmethod
    def _emit_progress(
        progress_callback: Optional[Callable[[dict], None]],
        data: dict,
    ) -> None:
        if progress_callback:
            progress_callback(data)

    def _run_render_feedback_loop(
        self,
        formatted_pages: list[FormattedPage],
        use_visual_feedback: bool,
        result_store: Optional[dict] = None,
        progress_callback: Optional[Callable[[dict], None]] = None,
        log_steps: bool = False,
        log_reviews: bool = False,
    ) -> tuple[list[FormattedPage], list[PreviewResult], list[VisualReview], int]:
        """Run preview rendering + optional visual feedback optimization loop."""
        total_pages = len(formatted_pages)
        divisor = total_pages if total_pages > 0 else 1

        all_reviews: list[VisualReview] = []
        all_previews: list[PreviewResult] = []
        total_iterations = 0

        if use_visual_feedback:
            if progress_callback:
                self._emit_progress(
                    progress_callback,
                    {"type": "step", "step": "visual_feedback", "progress": 0.45,
                     "detail": "视觉反馈优化..."},
                )
            elif log_steps:
                logger.info("Step 5: Visual feedback loop...")

            for page_idx, formatted in enumerate(formatted_pages):
                page_num = page_idx + 1
                current_content = formatted.content

                for iteration in range(1, self.max_iterations + 1):
                    total_iterations = max(total_iterations, iteration)

                    preview = self.renderer.render(
                        current_content,
                        page_num,
                        image_urls=formatted.image_urls,
                        image_slots=formatted.image_slots,
                        total_pages=total_pages,
                        use_title=(page_num == 1),
                    )

                    review = self._visual_review(preview, page_num)
                    if log_reviews:
                        logger.info(
                            f"  Page {page_num}, iteration {iteration}: "
                            f"score={review.score}, passed={review.pass_threshold}"
                        )

                    if review.pass_threshold:
                        all_reviews.append(review)
                        all_previews.append(preview)
                        formatted_pages[page_idx] = FormattedPage(
                            page_number=page_num,
                            content=current_content,
                            char_count=len(current_content),
                            emoji_count=formatted.emoji_count,
                            has_proper_spacing=formatted.has_proper_spacing,
                            image_urls=formatted.image_urls,
                            image_slots=formatted.image_slots,
                        )
                        break

                    if iteration < self.max_iterations:
                        current_content = self._optimize_content(current_content, review, page_num)
                    else:
                        all_reviews.append(review)
                        all_previews.append(preview)
                        formatted_pages[page_idx] = FormattedPage(
                            page_number=page_num,
                            content=current_content,
                            char_count=len(current_content),
                            emoji_count=formatted.emoji_count,
                            has_proper_spacing=formatted.has_proper_spacing,
                            image_urls=formatted.image_urls,
                            image_slots=formatted.image_slots,
                        )

                progress = 0.45 + (0.45 * page_num / divisor)
                if result_store is not None:
                    result_store["pages"] = list(formatted_pages[:page_idx + 1])
                    result_store["previews"] = list(all_previews)
                if progress_callback:
                    self._emit_progress(
                        progress_callback,
                        {"type": "page_done", "page": page_num, "total_pages": total_pages,
                         "progress": progress},
                    )
        else:
            if log_steps:
                logger.info("Step 5: Rendering previews (no visual feedback)...")
            for page_idx, formatted in enumerate(formatted_pages):
                page_num = page_idx + 1
                preview = self.renderer.render(
                    formatted.content,
                    formatted.page_number,
                    image_urls=formatted.image_urls,
                    image_slots=formatted.image_slots,
                    total_pages=total_pages,
                    use_title=(page_num == 1),
                )
                all_previews.append(preview)
                all_reviews.append(VisualReview(
                    score=7,
                    issues=[],
                    suggestions=[],
                    pass_threshold=True,
                ))

                progress = 0.45 + (0.45 * page_num / divisor)
                if result_store is not None:
                    result_store["pages"] = list(formatted_pages[:page_idx + 1])
                    result_store["previews"] = list(all_previews)
                if progress_callback:
                    self._emit_progress(
                        progress_callback,
                        {"type": "page_done", "page": page_num, "total_pages": total_pages,
                         "progress": progress},
                    )

        return formatted_pages, all_previews, all_reviews, total_iterations

    def _run_pipeline(
        self,
        parsed: ParsedMarkdown,
        image_analyses: list[ImageAnalysis],
        source_name: str,
        use_visual_feedback: bool,
        progress_callback: Optional[Callable[[dict], None]] = None,
        result_store: Optional[dict] = None,
        log_steps: bool = False,
        log_reviews: bool = False,
    ) -> ConversionResult:
        """Run shared conversion pipeline from split to save."""
        if log_steps:
            logger.info("Step 3: Splitting content...")
        if progress_callback:
            self._emit_progress(
                progress_callback,
                {"type": "step", "step": "splitting", "progress": 0.15, "detail": "智能分割内容..."},
            )

        pages = self.content_splitter.split(parsed, image_analyses)
        total_pages = len(pages)
        divisor = total_pages if total_pages > 0 else 1

        if log_steps:
            logger.info(f"  Split into {total_pages} pages")
        if progress_callback:
            self._emit_progress(
                progress_callback,
                {"type": "step", "step": "splitting_done", "progress": 0.20,
                 "detail": f"分割为 {total_pages} 页", "total_pages": total_pages},
            )

        if log_steps:
            logger.info("Step 4: Formatting for REDnote...")
        if progress_callback:
            self._emit_progress(
                progress_callback,
                {"type": "step", "step": "formatting", "progress": 0.25, "detail": "格式化排版..."},
            )

        formatted_pages: list[FormattedPage] = []
        for idx, page in enumerate(pages):
            page_num = idx + 1
            if progress_callback:
                progress = 0.25 + (0.15 * page_num / divisor)
                self._emit_progress(
                    progress_callback,
                    {"type": "step", "step": "formatting_page", "progress": progress,
                     "page": page_num, "total_pages": total_pages,
                     "detail": f"排版第 {page_num}/{total_pages} 页..."},
                )

            formatted = self.formatter.format_page(page, use_llm=False)
            formatted_pages.append(formatted)

            if log_steps:
                logger.info(
                    f"Page {page.page_number}: {formatted.char_count} chars, "
                    f"{formatted.emoji_count} emojis, proper_spacing={formatted.has_proper_spacing}"
                )

        formatted_pages = self.formatter.optimize_document_pages(
            formatted_pages,
            use_llm=True,
        )

        formatted_pages, all_previews, all_reviews, total_iterations = self._run_render_feedback_loop(
            formatted_pages=formatted_pages,
            use_visual_feedback=use_visual_feedback,
            result_store=result_store,
            progress_callback=progress_callback,
            log_steps=log_steps,
            log_reviews=log_reviews,
        )

        result = ConversionResult(
            pages=formatted_pages,
            previews=all_previews,
            reviews=all_reviews,
            iterations=total_iterations,
            image_analyses=image_analyses,
        )

        if progress_callback:
            self._emit_progress(
                progress_callback,
                {"type": "step", "step": "saving", "progress": 0.95, "detail": "保存结果..."},
            )
        elif log_steps:
            logger.info("Step 6: Saving results...")

        output_files = self._save_results(result, source_name)
        result.output_files = output_files

        if progress_callback:
            self._emit_progress(
                progress_callback,
                {"type": "complete", "progress": 1.0, "detail": f"完成！共 {total_pages} 页"},
            )

        if log_steps:
            logger.info(f"  Saved to {self.output_dir}")
            logger.info("Conversion complete!")

        return result

    def convert_from_string(
        self,
        markdown_text: str,
        use_visual_feedback: bool = True,
        verbose: bool = False,
        progress_callback: Optional[Callable[[dict], None]] = None,
        result_store: Optional[dict] = None,
        base_dir: Optional[Path] = None,
    ) -> ConversionResult:
        """
        从 Markdown 文本字符串执行完整转换流程

        Args:
            markdown_text: Markdown 文本
            use_visual_feedback: 是否启用视觉反馈循环
            verbose: 是否输出详细日志
            progress_callback: 可选的进度回调函数，接受 dict 参数
            result_store: 可选的共享字典，用于存储中间结果 (pages/previews 列表)
            base_dir: 可选基础目录（用于解析字符串输入中的本地/临时图片）

        Returns:
            ConversionResult 对象
        """
        # Shared store for incremental page results
        store = result_store if result_store is not None else {}
        if "pages" not in store:
            store["pages"] = []
        if "previews" not in store:
            store["previews"] = []

        if verbose:
            logging.basicConfig(level=logging.INFO)

        logger.info("Starting conversion from string")

        resolve_base = Path(base_dir).resolve() if base_dir else Path(".").resolve()
        self.renderer.set_base_dir(resolve_base)

        # Step 1: 解析 Markdown
        self._emit_progress(
            progress_callback,
            {"type": "step", "step": "parsing", "progress": 0.05, "detail": "解析 Markdown..."},
        )
        parsed = self.parser.parse(markdown_text)
        logger.info(f"  Parsed {len(parsed.blocks)} blocks, {len(parsed.images)} images")

        # Step 2: 分析图片
        self._emit_progress(
            progress_callback,
            {"type": "step", "step": "analyzing_images", "progress": 0.10, "detail": "分析图片..."},
        )
        image_analyses: list[ImageAnalysis] = []
        if parsed.images:
            for ref in parsed.images:
                original_path = str(ref.path)
                target = self._resolve_image_analysis_target(original_path, resolve_base)
                analysis = self.image_analyzer.analyze(target, resolve_base)
                analysis.path = original_path
                image_analyses.append(analysis)
            logger.info(f"  Analyzed {len(image_analyses)} images")

        return self._run_pipeline(
            parsed=parsed,
            image_analyses=image_analyses,
            source_name="web_input.md",
            use_visual_feedback=use_visual_feedback,
            progress_callback=progress_callback,
            result_store=store,
            log_steps=False,
            log_reviews=False,
        )

    def convert(
        self,
        markdown_path: Path,
        use_visual_feedback: bool = True,
        verbose: bool = False
    ) -> ConversionResult:
        """
        执行完整的 Markdown 转小红书排版流程

        Args:
            markdown_path: Markdown 文件路径
            use_visual_feedback: 是否启用视觉反馈循环
            verbose: 是否输出详细日志

        Returns:
            ConversionResult 对象
        """
        markdown_path = Path(markdown_path)

        if verbose:
            logging.basicConfig(level=logging.INFO)

        logger.info(f"Starting conversion: {markdown_path}")

        self.renderer.set_base_dir(markdown_path.parent)

        # Step 1: 解析 Markdown
        logger.info("Step 1: Parsing Markdown...")
        parsed = self.parser.parse_file(markdown_path)
        logger.info(f"  Parsed {len(parsed.blocks)} blocks, {len(parsed.images)} images")

        # Step 2: 分析图片
        logger.info("Step 2: Analyzing images...")
        image_analyses: list[ImageAnalysis] = []
        if parsed.images:
            base_dir = markdown_path.parent
            for ref in parsed.images:
                original_path = str(ref.path)
                target = self._resolve_image_analysis_target(original_path, base_dir)
                analysis = self.image_analyzer.analyze(target, base_dir)
                analysis.path = original_path
                image_analyses.append(analysis)
            logger.info(f"  Analyzed {len(image_analyses)} images")
        else:
            logger.info("  No images to analyze")

        return self._run_pipeline(
            parsed=parsed,
            image_analyses=image_analyses,
            source_name=markdown_path.name,
            use_visual_feedback=use_visual_feedback,
            progress_callback=None,
            result_store=None,
            log_steps=True,
            log_reviews=True,
        )
