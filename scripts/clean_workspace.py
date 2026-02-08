#!/usr/bin/env python3
"""
工作区清理脚本。

默认清理：
1) 所有 __pycache__ 目录
2) output/ 目录中的运行产物（保留 .gitkeep 与 README.md）

可选清理：
3) docs/archives/ 中的本地调试归档（保留 .gitkeep）
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupStats:
    removed_files: int = 0
    removed_dirs: int = 0


def _remove_path(target: Path, dry_run: bool, stats: CleanupStats) -> None:
    if not target.exists():
        return

    if target.is_dir():
        if dry_run:
            print(f"[DRY-RUN] remove dir: {target}")
        else:
            shutil.rmtree(target, ignore_errors=True)
            print(f"[OK] removed dir: {target}")
        stats.removed_dirs += 1
    else:
        if dry_run:
            print(f"[DRY-RUN] remove file: {target}")
        else:
            target.unlink(missing_ok=True)
            print(f"[OK] removed file: {target}")
        stats.removed_files += 1


def clean_pycache(root: Path, dry_run: bool, stats: CleanupStats) -> None:
    for cache_dir in root.rglob("__pycache__"):
        if cache_dir.is_dir():
            _remove_path(cache_dir, dry_run=dry_run, stats=stats)


def clean_output(root: Path, dry_run: bool, stats: CleanupStats) -> None:
    output_dir = root / "output"
    if not output_dir.exists():
        return

    keep_names = {".gitkeep", "README.md"}
    for item in output_dir.iterdir():
        if item.name in keep_names:
            continue
        _remove_path(item, dry_run=dry_run, stats=stats)


def clean_archives(root: Path, dry_run: bool, stats: CleanupStats) -> None:
    archives_dir = root / "docs" / "archives"
    if not archives_dir.exists():
        return

    keep_names = {".gitkeep"}
    for item in archives_dir.iterdir():
        if item.name in keep_names:
            continue
        _remove_path(item, dry_run=dry_run, stats=stats)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理工作区临时产物")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将删除的内容，不实际删除",
    )
    parser.add_argument(
        "--include-archives",
        action="store_true",
        help="同时清理 docs/archives 下的调试归档",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    stats = CleanupStats()

    print(f"[INFO] project root: {project_root}")
    print(f"[INFO] dry-run: {args.dry_run}")

    clean_pycache(project_root, dry_run=args.dry_run, stats=stats)
    clean_output(project_root, dry_run=args.dry_run, stats=stats)

    if args.include_archives:
        clean_archives(project_root, dry_run=args.dry_run, stats=stats)

    print(
        f"[DONE] removed files={stats.removed_files}, removed dirs={stats.removed_dirs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

