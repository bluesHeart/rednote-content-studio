# rednote-content-studio

把 Markdown 内容（含图片）转换成 REDnote 可发布的图文卡片，支持 CLI 与 Web 双入口，并提供“最后一公里”可编辑中间层。

---

## 项目定位

- **输入**：Markdown 文本 + 图片引用（本地/远程）
- **输出**：分页文案、单页 HTML/PNG、合并预览、结构化结果
- **核心原则**：`LLM 负责生成，用户负责定稿`

这不是“一次性改写器”，而是“可回滚、可约束、可局部重写”的内容生产链路。

---

## 架构总览

```text
Markdown Input
  -> markdown_parser          (结构解析)
  -> image_analyzer           (图片语义分析，可多模态)
  -> content_splitter         (分页规划)
  -> rednote_formatter        (小红书风格格式化)
  -> preview_renderer         (HTML/PNG 渲染)
  -> editable_story layer     (块级编辑/锁定/局部重写)
  -> output artifacts         (txt/html/png/json)
```

Web 端在上述流程外增加：任务状态管理、进度推送、文件上传、下载打包。

---

## 目录结构（已整理）

```text
rednote-content-studio/
├─ app.py                       # Web 启动入口
├─ requirements.txt
├─ .gitignore
├─ README.md
├─ scripts/
│  ├─ main.py                   # CLI 入口
│  ├─ agent.py                  # 主编排流程
│  ├─ client.py                 # OpenAI 兼容客户端
│  ├─ config_llm.py             # LLM 配置解析
│  ├─ constants/                # 常量与字符库
│  └─ core/                     # 解析/分页/排版/渲染核心模块
├─ web/
│  ├─ api.py                    # REST + WebSocket 接口
│  ├─ editable_story.py         # 可编辑中间层模型与逻辑
│  ├─ schemas.py                # API 数据结构
│  ├─ session_manager.py        # 任务会话管理
│  ├─ templates.py              # 视觉/语气模板
│  └─ static/                   # 前端静态资源
├─ docs/
│  ├─ guide/                    # 使用与治理文档
│  ├─ showcase/                 # 展示文章与素材
│  ├─ adr/                      # 架构决策记录
│  └─ archives/                 # 调试归档（默认忽略）
├─ examples/
│  └─ test_input.md             # 示例输入
└─ output/
   ├─ .gitkeep
   └─ README.md                 # 运行时输出目录说明
```

---

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置 LLM 环境变量

优先读取：

- `SKILL_LLM_API_KEY`
- `SKILL_LLM_BASE_URL`（可选，默认 `https://api.openai.com/v1`）
- `SKILL_LLM_MODEL`（可选，默认 `gpt-4o-mini`）

兼容：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

PowerShell 示例：

```powershell
$env:SKILL_LLM_API_KEY = "your-api-key"
$env:SKILL_LLM_BASE_URL = "https://api.openai.com/v1"
$env:SKILL_LLM_MODEL = "gpt-4o"
```

---

## CLI 用法

```bash
python scripts/main.py examples/test_input.md
```

常用参数：

```bash
python scripts/main.py examples/test_input.md --output ./output
python scripts/main.py examples/test_input.md --no-visual-feedback
python scripts/main.py examples/test_input.md --max-iterations 5 -v
python scripts/main.py examples/test_input.md --api-key "sk-..." --model "gpt-4o"
```

---

## Web 用法

启动服务：

```bash
python app.py --port 8000
```

访问：`http://127.0.0.1:8000`

Web 功能：

- Markdown 粘贴/上传
- 图片粘贴/上传并转为 Markdown 引用
- 实时进度（WebSocket）
- 分页预览与单页复制
- 最后一公里编辑（块级编辑、锁定、局部重写、图片块顺序调整）

---

## 输出说明

默认输出目录：`output/`（运行时生成，默认不入库）

- `page_N.txt`：第 N 页文案
- `preview_page_N.html`：第 N 页 HTML
- `preview_page_N.png`：第 N 页图片
- `preview.html`：合并预览
- `result.json`：结构化结果

---

## Web API（核心）

- `POST /api/convert`：创建转换任务
- `GET /api/jobs/{job_id}/status`：查询状态
- `WS /api/ws/{job_id}`：实时进度
- `GET /api/jobs/{job_id}/preview`：合并预览
- `GET /api/jobs/{job_id}/download`：下载结果包
- `GET /api/jobs/{job_id}/editable-story`：读取可编辑中间层
- `PUT /api/jobs/{job_id}/editable-story`：保存编辑结果
- `POST /api/jobs/{job_id}/editable-story/regenerate`：局部重写当前页
- `POST /api/jobs/{job_id}/editable-story/apply`：应用编辑并重渲染

---

## 工程治理约定

- `output/` 是运行时目录：不提交历史结果
- `docs/archives/` 存放本地调试抓图：默认忽略
- `docs/showcase/` 存放对外文章与配图素材
- 示例输入放在 `examples/`
- 根目录仅保留“入口 + 配置 + 文档"

这套约定已经通过 `.gitignore` 固化，避免后续目录再次失控。

配套清理命令：

```bash
python scripts/clean_workspace.py
```

治理细则见：`docs/guide/workspace-governance.md`

展示文章示例：`docs/showcase/cases/rednote_final_mile_story.md`

---

## 常见问题

- **空行被吞？** 使用盲文空格 `⠀`（U+2800）保留空行。
- **转换慢？** 关闭视觉反馈 `--no-visual-feedback` 可提速。
- **第三方模型兼容？** 只要兼容 OpenAI Chat Completions 即可。

---

## 下一步建议（架构师视角）

- 为 `web/session_manager.py` 增加持久化后端（Redis/SQLite）
- 为 Web 任务增加失败重试与可观测埋点（trace/job timeline）
- 增加 CI 流水线（lint + smoke + docs link check）
