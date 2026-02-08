#!/usr/bin/env python3
"""
Markdown 转小红书排版 - CLI 入口

使用方法:
    python main.py input.md
    python main.py input.md --output ./my_output
    python main.py input.md --max-iterations 5
    python main.py input.md -v
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
from pathlib import Path

# Fix Windows console encoding for emoji/CJK characters
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

if __package__:
    from .config_llm import LLMConfig
    from .agent import RedNoteAgent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.config_llm import LLMConfig
    from scripts.agent import RedNoteAgent


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def print_banner() -> None:
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     📝 Markdown → 小红书排版智能体                          ║
║                                                              ║
║     ✨ 特点：                                                ║
║     • 多模态图片分析                                         ║
║     • 智能内容分割                                           ║
║     • 视觉反馈循环优化                                       ║
║     • 盲文空格保持空行                                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_result_summary(result, output_dir: Path) -> None:
    """打印结果摘要"""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()

        # 基本信息
        console.print("\n[bold green]✅ 转换完成！[/bold green]\n")

        # 页面统计表
        table = Table(title="页面统计")
        table.add_column("页码", style="cyan")
        table.add_column("字数", style="magenta")
        table.add_column("Emoji", style="yellow")
        table.add_column("审查评分", style="green")
        table.add_column("状态", style="blue")

        for i, page in enumerate(result.pages):
            review = result.reviews[i] if i < len(result.reviews) else None
            score = review.score if review else "-"
            status = "✅" if (review and review.pass_threshold) else "⚠️"
            table.add_row(
                str(page.page_number),
                str(page.char_count),
                str(page.emoji_count),
                str(score),
                status
            )

        console.print(table)

        # 输出文件
        console.print(f"\n[bold]📁 输出目录:[/bold] {output_dir}")
        console.print("\n[bold]📄 生成的文件:[/bold]")
        for name, path in result.output_files.items():
            console.print(f"  • {path.name}")

        # 使用提示
        console.print(Panel(
            "[yellow]💡 提示:[/yellow]\n"
            "1. 将 page_N.txt 的内容复制到小红书 App\n"
            "2. 在浏览器中打开 preview.html 查看效果\n"
            "3. 空行使用盲文空格字符 (⠀)，不会被小红书吞掉",
            title="使用说明",
            border_style="blue"
        ))

    except ImportError:
        # 回退到简单打印
        print("\n✅ 转换完成！")
        print(f"\n📁 输出目录: {output_dir}")
        print(f"\n📊 统计:")
        print(f"  • 总页数: {len(result.pages)}")
        print(f"  • 迭代次数: {result.iterations}")
        print(f"  • 图片数: {len(result.image_analyses)}")

        print("\n📄 生成的文件:")
        for name, path in result.output_files.items():
            print(f"  • {path.name}")

        print("\n💡 提示:")
        print("  1. 将 page_N.txt 的内容复制到小红书 App")
        print("  2. 在浏览器中打开 preview.html 查看效果")
        print("  3. 空行使用盲文空格字符，不会被小红书吞掉")


def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(
        description='将 Markdown 文档转换为小红书排版格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py article.md
  python main.py article.md --output ./rednote_output
  python main.py article.md --max-iterations 5 -v
  python main.py article.md --no-visual-feedback

环境变量:
  SKILL_LLM_API_KEY     API 密钥
  SKILL_LLM_BASE_URL    API 端点 (默认: https://api.openai.com/v1)
  SKILL_LLM_MODEL       模型名称 (默认: gpt-4o-mini，建议使用支持视觉的模型)
"""
    )

    parser.add_argument(
        'input',
        type=Path,
        help='输入的 Markdown 文件路径'
    )

    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='输出目录 (默认: ./output)'
    )

    parser.add_argument(
        '--max-iterations', '-m',
        type=int,
        default=3,
        help='视觉反馈循环的最大迭代次数 (默认: 3)'
    )

    parser.add_argument(
        '--no-visual-feedback',
        action='store_true',
        help='禁用视觉反馈循环 (更快但质量可能较低)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='输出详细日志'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='LLM API 密钥 (也可通过环境变量设置)'
    )

    parser.add_argument(
        '--base-url',
        type=str,
        default=None,
        help='LLM API 端点 URL'
    )

    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='LLM 模型名称'
    )

    args = parser.parse_args()

    # 设置日志
    setup_logging(args.verbose)

    # 打印横幅
    print_banner()

    # 检查输入文件
    if not args.input.exists():
        print(f"❌ 错误: 输入文件不存在: {args.input}")
        return 1

    if not args.input.suffix.lower() in ['.md', '.markdown']:
        print(f"⚠️ 警告: 输入文件可能不是 Markdown 格式: {args.input}")

    # 设置输出目录
    output_dir = args.output
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "output"

    # 初始化 LLM 配置
    try:
        llm_config = LLMConfig.resolve(
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
        )
    except ValueError as e:
        print(f"❌ 错误: {e}")
        print("\n请设置环境变量或使用命令行参数:")
        print("  export SKILL_LLM_API_KEY='your-api-key'")
        print("  或")
        print("  python main.py input.md --api-key 'your-api-key'")
        return 1

    print(f"📄 输入文件: {args.input}")
    print(f"📁 输出目录: {output_dir}")
    print(f"🤖 使用模型: {llm_config.model}")
    print(f"🔄 最大迭代: {args.max_iterations}")
    print(f"👁️ 视觉反馈: {'启用' if not args.no_visual_feedback else '禁用'}")
    print()

    # 创建智能体并执行转换
    try:
        agent = RedNoteAgent(
            llm_config=llm_config,
            max_iterations=args.max_iterations,
            output_dir=output_dir,
        )

        result = agent.convert(
            markdown_path=args.input,
            use_visual_feedback=not args.no_visual_feedback,
            verbose=args.verbose,
        )

        # 打印结果摘要
        print_result_summary(result, output_dir)

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户取消操作")
        return 130

    except Exception as e:
        logging.exception("转换失败")
        print(f"\n❌ 转换失败: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
