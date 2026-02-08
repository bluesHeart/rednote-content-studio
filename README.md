# rednote-content-studio

把 Markdown 直接变成可发布的 REDnote 图文卡片，并把“最后一公里定稿权”交还给你。

> 🚀 GitHub: https://github.com/bluesHeart/rednote-content-studio
>
> 如果这个项目对你有帮助，欢迎先点个 **Star**，我会持续迭代。

---

## 为什么值得用

- **不是一次性 AI 改写**：支持块级编辑、锁定、局部重写
- **图文顺序可控**：图片按正文流动，不再乱序/堆顶
- **双入口**：CLI 批处理 + Web 可视化操作
- **工程化输出**：`txt/html/png/json` 全套产物

---

## 效果预览

![Demo Cards A](docs/showcase/article_assets/21_cards_pair_clean_a.png)

![Demo Cards B](docs/showcase/article_assets/22_cards_pair_clean_b.png)

完整案例文章（含 Web 操作截图）：

- `docs/showcase/cases/rednote_final_mile_story.md`

---

## 快速开始（3 分钟）

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置模型

必填（至少一个 API Key）：

- `SKILL_LLM_API_KEY`（或 `OPENAI_API_KEY`）

可选：

- `SKILL_LLM_BASE_URL`（默认 `https://api.openai.com/v1`）
- `SKILL_LLM_MODEL`（默认 `gpt-4o-mini`）

### 3) 运行

CLI：

```bash
python scripts/main.py examples/test_input.md --output ./output
```

Web：

```bash
python app.py --port 8000
```

打开：`http://127.0.0.1:8000`

---

## 核心能力

- Markdown 结构解析（标题/列表/引用/代码块/图片）
- 多模态图片分析（语义 + 建议位置）
- 智能分页（短页优先，阅读节奏友好）
- REDnote 风格排版（语气模板 + 视觉模板）
- 预览渲染（单页与合并）
- 最后一公里编辑（`editable_story`）

---

## 项目结构

```text
rednote-content-studio/
├─ app.py
├─ requirements.txt
├─ scripts/                  # CLI 与核心流程
├─ web/                      # API + 前端
├─ docs/
│  ├─ guide/
│  ├─ showcase/
│  ├─ adr/
│  └─ archives/
├─ examples/
└─ output/
```

---

## 输出产物

- `page_N.txt`：可直接发布文案
- `preview_page_N.html`：单页 HTML
- `preview_page_N.png`：单页图片
- `preview.html`：合并预览
- `result.json`：结构化结果

---

## 工程治理

- 运行产物默认不入库（`output/`）
- 调试归档默认不入库（`docs/archives/`）
- 一键清理命令：

```bash
python scripts/clean_workspace.py
```

治理文档：`docs/guide/workspace-governance.md`

---

## 路线图（欢迎共建）

- [ ] Session 持久化（Redis/SQLite）
- [ ] 更强的排版评估指标
- [ ] CI（lint + smoke + docs link check）
- [ ] Docker 一键部署

欢迎提 Issue / PR：

- https://github.com/bluesHeart/rednote-content-studio/issues

---

## License

MIT

