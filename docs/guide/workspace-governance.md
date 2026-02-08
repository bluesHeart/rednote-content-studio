# 工作区治理说明

本项目遵循“代码、文档、运行产物分层”原则，避免目录长期演化成杂物堆。

## 目录职责

- `scripts/`：CLI 与核心转换逻辑
- `web/`：Web API 与前端静态资源
- `docs/guide/`：使用与治理文档
- `docs/showcase/`：对外展示文章与素材
- `docs/adr/`：架构决策记录（建议后续补齐）
- `examples/`：示例输入
- `output/`：运行时产物（默认忽略）

## 忽略策略

`.gitignore` 已固定以下内容不入库：

- Python 缓存（`__pycache__`、`*.pyc`）
- 虚拟环境与测试缓存
- `output/` 下运行产物（保留 `.gitkeep` 和 `README.md`）
- `docs/archives/` 本地调试归档（保留 `.gitkeep`）

## 一键清理

```bash
python scripts/clean_workspace.py
```

默认行为：

- 删除所有 `__pycache__`
- 清空 `output/` 运行产物（保留占位文件）

预览清理（不执行删除）：

```bash
python scripts/clean_workspace.py --dry-run
```

同时清理调试归档：

```bash
python scripts/clean_workspace.py --include-archives
```

