"""
REST + WebSocket 路由
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.config_llm import LLMConfig
from scripts.agent import RedNoteAgent
from scripts.client import LLMClient

from .schemas import (
    ConvertRequest,
    EditableStoryApplyResponse,
    EditableStoryRegenerateRequest,
    EditableStoryResponse,
    EditableStoryUpdateRequest,
    JobCreatedResponse,
    JobStatusResponse,
)
from .session_manager import SessionManager, Job
from .editable_story import (
    build_combined_html,
    build_story_from_pages,
    render_previews,
    sanitize_story,
    story_to_formatted_pages,
)
from .templates import (
    VISUAL_TEMPLATES, TONE_TEMPLATES,
    DEFAULT_VISUAL_TEMPLATE, DEFAULT_TONE_TEMPLATE,
    get_all_templates_api,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
manager = SessionManager()

# Track WebSocket connections per job
_ws_connections: dict[str, list[WebSocket]] = {}

# Background cleanup task guard
_cleanup_task_started = False


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates")
async def get_templates():
    """获取所有模板列表"""
    return get_all_templates_api()


# ---------------------------------------------------------------------------
# Env config detection
# ---------------------------------------------------------------------------

@router.get("/env-config")
async def get_env_config():
    """检测服务器端环境变量是否配置了 API Key"""
    import os
    has_key = bool(os.getenv("SKILL_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
    base_url = os.getenv("SKILL_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    model = os.getenv("SKILL_LLM_MODEL") or ""
    return {
        "has_env_key": has_key,
        "base_url_hint": base_url[:30] + "..." if len(base_url) > 30 else base_url,
        "model_hint": model,
    }


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_markdown(file: UploadFile = File(...)):
    """上传 .md 文件，返回文本内容"""
    if not file.filename or not file.filename.lower().endswith(('.md', '.markdown', '.txt')):
        raise HTTPException(400, "仅支持 .md / .markdown / .txt 文件")
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="replace")
    return {"filename": file.filename, "content": text}


# Image temp storage (shared across requests, cleaned with jobs)
_image_dir: Optional[Path] = None

def _get_image_dir() -> Path:
    global _image_dir
    if _image_dir is None or not _image_dir.exists():
        import tempfile
        _image_dir = Path(tempfile.mkdtemp(prefix="rednote_images_"))
    return _image_dir


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """上传图片（粘贴/拖拽），返回可访问的 URL"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "仅支持图片文件")

    import uuid
    ext = ".png"
    if file.filename:
        ext = Path(file.filename).suffix or ".png"
    name = f"{uuid.uuid4().hex[:8]}{ext}"

    img_dir = _get_image_dir()
    save_path = img_dir / name
    content = await file.read()
    save_path.write_bytes(content)

    return {"url": f"/api/images/{name}", "filename": name, "size": len(content)}


def _sync_uploaded_images_to_job_dir(job: Job, markdown_text: str):
    """Copy `/api/images/*` references into job work dir for LLM image analysis."""
    if not job.work_dir:
        return

    import re

    matches = re.findall(r"!\[[^\]]*\]\((/api/images/[^)]+)\)", markdown_text or "")
    if not matches:
        return

    img_dir = _get_image_dir()
    target_dir = job.work_dir / "api_images"
    target_dir.mkdir(parents=True, exist_ok=True)

    for url in set(matches):
        name = Path(url).name
        source = img_dir / name
        target = target_dir / name
        if source.exists() and source.is_file():
            try:
                shutil.copy2(source, target)
            except Exception:
                logger.warning("Failed to copy uploaded image to job dir: %s", source)


async def _cleanup_loop(interval_seconds: int = 300):
    """Periodic cleanup for expired in-memory jobs and dead websocket buckets."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            manager.cleanup_old_jobs()
            dead_keys = [job_id for job_id, conns in _ws_connections.items() if not conns]
            for job_id in dead_keys:
                _ws_connections.pop(job_id, None)
        except Exception:
            logger.exception("Background cleanup task failed")


def ensure_cleanup_task_started() -> None:
    """Start periodic cleanup task once per process.

    由 app lifespan 调用，避免使用已弃用的 on_event。
    """
    global _cleanup_task_started
    if _cleanup_task_started:
        return
    _cleanup_task_started = True
    asyncio.create_task(_cleanup_loop())


@router.get("/images/{name}")
async def get_image(name: str):
    """获取上传的临时图片"""
    img_dir = _get_image_dir()
    file_path = img_dir / name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "图片不存在")
    # Determine mime type
    suffix = file_path.suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(suffix.lstrip("."), "image/png")
    return Response(content=file_path.read_bytes(), media_type=mime)


# ---------------------------------------------------------------------------
# Convert
# ---------------------------------------------------------------------------

@router.post("/convert", response_model=JobCreatedResponse)
async def start_convert(req: ConvertRequest):
    """提交转换任务"""
    # Validate templates
    if req.visual_template not in VISUAL_TEMPLATES:
        raise HTTPException(400, f"未知的视觉模板: {req.visual_template}")
    if req.tone_template not in TONE_TEMPLATES:
        raise HTTPException(400, f"未知的语气模板: {req.tone_template}")

    job = manager.create_job()

    # Launch background task
    asyncio.create_task(_run_conversion(job, req))

    return JobCreatedResponse(job_id=job.id, status="pending")


async def _run_conversion(job: Job, req: ConvertRequest):
    """后台执行转换"""
    manager.update_job(job.id, status="running")

    try:
        visual_tmpl = VISUAL_TEMPLATES[req.visual_template]
        tone_tmpl = TONE_TEMPLATES[req.tone_template]

        llm_config = LLMConfig.resolve(
            api_key=req.api_key or None,
            base_url=req.base_url or None,
            model=req.model or None,
        )

        manager.update_job(
            job.id,
            visual_style=visual_tmpl.to_style_dict(),
            tone_system_prompt=tone_tmpl.system_prompt,
            llm_config=llm_config,
        )

        agent = RedNoteAgent(
            llm_config=llm_config,
            max_iterations=req.max_iterations,
            output_dir=job.work_dir,
            tone_system_prompt=tone_tmpl.system_prompt,
            visual_style=visual_tmpl.to_style_dict(),
        )

        # Shared store for incremental page results (agent fills this)
        result_store = {"pages": [], "previews": []}
        job.result_store = result_store

        # Mirror uploaded API images into this job workspace for analysis.
        _sync_uploaded_images_to_job_dir(job, req.markdown)

        # Capture the running event loop BEFORE entering the worker thread
        loop = asyncio.get_running_loop()

        def progress_callback(data: dict):
            """同步回调（在 worker thread 中执行）— 更新 job 状态并推送 WebSocket"""
            manager.update_job(
                job.id,
                progress=data.get("progress", job.progress),
                detail=data.get("detail", job.detail),
            )
            if data.get("total_pages"):
                manager.update_job(job.id, total_pages=data["total_pages"])
            if data["type"] == "page_done":
                manager.update_job(job.id, completed_pages=data["page"])
            # Schedule WS broadcast on the main event loop
            asyncio.run_coroutine_threadsafe(_broadcast(job.id, data), loop)

        result = await asyncio.to_thread(
            agent.convert_from_string,
            req.markdown,
            use_visual_feedback=req.use_visual_feedback,
            progress_callback=progress_callback,
            result_store=result_store,
            base_dir=job.work_dir,
        )

        manager.update_job(
            job.id,
            status="completed",
            progress=1.0,
            detail=f"完成！共 {len(result.pages)} 页",
            total_pages=len(result.pages),
            completed_pages=len(result.pages),
            result=result,
        )

        try:
            story = build_story_from_pages(
                result.pages,
                base_dir=job.work_dir or Path("."),
                visual_style=visual_tmpl.to_style_dict(),
            )
            manager.update_job(job.id, editable_story=story)
            if job.work_dir:
                story_path = job.work_dir / "editable_story.json"
                story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to build editable story for job=%s", job.id)

        await _broadcast(job.id, {
            "type": "complete",
            "progress": 1.0,
            "detail": f"完成！共 {len(result.pages)} 页",
            "total_pages": len(result.pages),
        })

    except Exception as e:
        logger.exception("Conversion failed")
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
            error_msg = "API Key 无效或已过期"
        manager.update_job(job.id, status="failed", error=error_msg)
        await _broadcast(job.id, {"type": "error", "detail": error_msg})


async def _broadcast(job_id: str, data: dict):
    """广播 WebSocket 消息"""
    connections = _ws_connections.get(job_id, [])
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.remove(ws)


def _save_rendered_outputs(job: Job, pages: list, previews: list, combined_html: str) -> None:
    """Persist regenerated outputs into job work dir and in-memory result store."""
    if not job.work_dir:
        return

    total_pages = len(pages)

    for idx, page in enumerate(pages, start=1):
        txt_path = job.work_dir / f"page_{idx}.txt"
        txt_path.write_text(page.content, encoding="utf-8")

    for idx, preview in enumerate(previews, start=1):
        img_path = job.work_dir / f"preview_page_{idx}.png"
        img_path.write_bytes(preview.image_bytes)

        html_path = job.work_dir / f"preview_page_{idx}.html"
        html_path.write_text(preview.html_content, encoding="utf-8")

    preview_path = job.work_dir / "preview.html"
    preview_path.write_text(combined_html, encoding="utf-8")

    result_json_path = job.work_dir / "result.json"
    if result_json_path.exists():
        try:
            data = json.loads(result_json_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    data["total_pages"] = total_pages
    data["pages"] = [
        {
            "page_number": idx,
            "char_count": len(page.content),
            "emoji_count": page.emoji_count,
            "has_proper_spacing": page.has_proper_spacing,
            "image_urls": list(page.image_urls),
            "image_slots": list(page.image_slots),
            "content": page.content,
        }
        for idx, page in enumerate(pages, start=1)
    ]
    result_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if job.result_store is None:
        job.result_store = {}
    job.result_store["pages"] = pages
    job.result_store["previews"] = previews

    if job.result:
        job.result.pages = pages
        job.result.previews = previews


def _ensure_editable_story(job: Job) -> dict:
    """Lazily build editable story for completed jobs."""
    if job.editable_story:
        return sanitize_story(job.editable_story, page_count_hint=job.total_pages)

    if not job.result or not getattr(job.result, "pages", None):
        raise HTTPException(400, "任务结果尚不可编辑")

    story = build_story_from_pages(
        job.result.pages,
        base_dir=job.work_dir or Path("."),
        visual_style=job.visual_style,
    )
    job.editable_story = story

    if job.work_dir:
        story_path = job.work_dir / "editable_story.json"
        story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    return story


def _save_editable_story(job: Job, story: dict) -> dict:
    """Store normalized editable story to memory + disk."""
    normalized = sanitize_story(story, page_count_hint=job.total_pages or None)
    job.editable_story = normalized

    if job.work_dir:
        story_path = job.work_dir / "editable_story.json"
        story_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    return normalized


def _regenerate_single_page(job: Job, page_number: int, instruction: str | None = None) -> dict:
    """Regenerate one editable page while preserving locked blocks and image order."""
    story = _ensure_editable_story(job)
    pages = story.get("pages", [])

    target_page = None
    for page in pages:
        if int(page.get("page_number", 0)) == page_number:
            target_page = page
            break
    if target_page is None:
        raise HTTPException(404, "页面不存在")

    if target_page.get("locked"):
        raise HTTPException(400, "该页已锁定，无法重写")

    if not job.llm_config:
        raise HTTPException(400, "当前任务缺少 LLM 配置，无法重写")

    tone_prompt = job.tone_system_prompt or "你是小红书内容编辑。"
    llm_client = LLMClient(job.llm_config)

    blocks = target_page.get("blocks", [])
    locked_blocks = [b for b in blocks if isinstance(b, dict) and b.get("locked")]
    editable_blocks = [b for b in blocks if isinstance(b, dict) and not b.get("locked")]

    if not editable_blocks:
        return story

    payload = {
        "page_number": page_number,
        "instruction": instruction or "",
        "locked_blocks": locked_blocks,
        "editable_blocks": editable_blocks,
        "rules": {
            "must_keep_locked": True,
            "must_keep_image_order": True,
            "must_keep_block_count": True,
            "preserve_image_blocks": True,
        },
    }

    system_prompt = (
        f"{tone_prompt}\n\n"
        "你在做‘局部改写’：只允许重写 editable_blocks 里的文本块。"
        "禁止修改 locked_blocks 和任何 image 块。"
        "输出严格 JSON：{\"editable_blocks\":[{\"id\":\"...\",\"text\":\"...\"}]}"
    )
    user_prompt = f"输入：{json.dumps(payload, ensure_ascii=False)}"

    try:
        result = llm_client.chat_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.35,
            max_tokens=1800,
            json_mode=True,
        )
        data = llm_client.parse_json(result.content, default={})
    except Exception as exc:
        raise HTTPException(500, f"局部重写失败: {exc}") from exc

    rewritten = data.get("editable_blocks") if isinstance(data, dict) else None
    if not isinstance(rewritten, list):
        raise HTTPException(500, "局部重写返回格式无效")

    rewritten_map: dict[str, str] = {}
    for item in rewritten:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("id", "")).strip()
        if not block_id:
            continue
        rewritten_map[block_id] = str(item.get("text", ""))

    new_blocks: list[dict] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("locked"):
            new_blocks.append(block)
            continue

        if block.get("type") == "image":
            new_blocks.append(block)
            continue

        block_id = str(block.get("id", ""))
        if block_id in rewritten_map:
            updated = dict(block)
            updated["text"] = rewritten_map[block_id]
            new_blocks.append(updated)
        else:
            new_blocks.append(block)

    target_page["blocks"] = new_blocks
    updated_story = _save_editable_story(job, story)
    return updated_story


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws/{job_id}")
async def ws_job(ws: WebSocket, job_id: str):
    """WebSocket 实时进度推送"""
    job = manager.get_job(job_id)
    if not job:
        await ws.close(code=4004)
        return

    await ws.accept()

    if job_id not in _ws_connections:
        _ws_connections[job_id] = []
    _ws_connections[job_id].append(ws)

    try:
        # Send current status immediately
        await ws.send_json(job.to_status_dict())

        # Keep alive until client disconnects or job finishes
        while True:
            try:
                # Wait for pings from client (keepalive)
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break
            except WebSocketDisconnect:
                break
    finally:
        conns = _ws_connections.get(job_id, [])
        if ws in conns:
            conns.remove(ws)


# ---------------------------------------------------------------------------
# Job status (polling fallback)
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """轮询获取任务状态"""
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return JobStatusResponse(**job.to_status_dict())


# ---------------------------------------------------------------------------
# Result endpoints
# ---------------------------------------------------------------------------

def _get_completed_job(job_id: str) -> Job:
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status != "completed":
        raise HTTPException(400, f"任务未完成 (status={job.status})")
    return job


def _get_job_with_pages(job_id: str) -> Job:
    """获取有部分结果的 job（running 或 completed 均可）"""
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if job.status == "failed":
        raise HTTPException(400, f"任务失败: {job.error}")
    if job.status == "pending":
        raise HTTPException(400, "任务尚未开始")
    return job


@router.get("/jobs/{job_id}/page/{page_num}/text")
async def get_page_text(job_id: str, page_num: int):
    """下载单页纯文本"""
    job = _get_job_with_pages(job_id)
    # Use final result if completed, otherwise partial store
    pages = job.result.pages if (job.result and job.status == "completed") else getattr(job, 'result_store', {}).get('pages', [])
    if not pages or page_num < 1 or page_num > len(pages):
        raise HTTPException(404, "页面不存在")
    page = pages[page_num - 1]
    return Response(content=page.content, media_type="text/plain; charset=utf-8")


@router.get("/jobs/{job_id}/page/{page_num}/image")
async def get_page_image(job_id: str, page_num: int):
    """下载单页 PNG"""
    job = _get_job_with_pages(job_id)
    previews = job.result.previews if (job.result and job.status == "completed") else getattr(job, 'result_store', {}).get('previews', [])
    if not previews or page_num < 1 or page_num > len(previews):
        raise HTTPException(404, "页面不存在")
    preview = previews[page_num - 1]
    return Response(content=preview.image_bytes, media_type="image/png")


@router.get("/jobs/{job_id}/page/{page_num}/html")
async def get_page_html(job_id: str, page_num: int):
    """获取单页 HTML 卡片"""
    job = _get_job_with_pages(job_id)
    previews = job.result.previews if (job.result and job.status == "completed") else getattr(job, 'result_store', {}).get('previews', [])
    if not previews or page_num < 1 or page_num > len(previews):
        raise HTTPException(404, "页面不存在")
    preview = previews[page_num - 1]
    return HTMLResponse(content=preview.html_content)


@router.get("/jobs/{job_id}/preview")
async def get_preview(job_id: str):
    """获取合并预览 HTML"""
    job = _get_completed_job(job_id)
    # Read the combined preview.html from work dir
    preview_path = job.work_dir / "preview.html"
    if not preview_path.exists():
        raise HTTPException(404, "预览文件不存在")
    content = preview_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


@router.get("/jobs/{job_id}/editable-story", response_model=EditableStoryResponse)
async def get_editable_story(job_id: str):
    """获取可编辑中间层结构（用户最后一公里编辑入口）。"""
    job = _get_completed_job(job_id)
    story = _ensure_editable_story(job)
    return EditableStoryResponse(job_id=job_id, story=story)


@router.put("/jobs/{job_id}/editable-story", response_model=EditableStoryResponse)
async def update_editable_story(job_id: str, req: EditableStoryUpdateRequest):
    """覆盖保存可编辑中间层（不触发渲染）。"""
    job = _get_completed_job(job_id)
    story = _save_editable_story(job, req.story)
    return EditableStoryResponse(job_id=job_id, story=story)


@router.post("/jobs/{job_id}/editable-story/regenerate", response_model=EditableStoryResponse)
async def regenerate_editable_page(job_id: str, req: EditableStoryRegenerateRequest):
    """局部重写某一页未锁定文本块。"""
    job = _get_completed_job(job_id)
    story = _regenerate_single_page(job, req.page_number, req.instruction)
    return EditableStoryResponse(job_id=job_id, story=story)


@router.post("/jobs/{job_id}/editable-story/apply", response_model=EditableStoryApplyResponse)
async def apply_editable_story(job_id: str):
    """将可编辑中间层重新渲染为最终页面与预览。"""
    job = _get_completed_job(job_id)
    story = _ensure_editable_story(job)

    pages = story_to_formatted_pages(story)
    previews, renderer = render_previews(
        pages,
        base_dir=job.work_dir or Path("."),
        visual_style=job.visual_style,
    )
    combined_html = build_combined_html(pages, renderer)
    _save_rendered_outputs(job, pages, previews, combined_html)

    manager.update_job(
        job.id,
        total_pages=len(pages),
        completed_pages=len(pages),
        detail=f"已应用编辑并重渲染（{len(pages)} 页）",
    )
    return EditableStoryApplyResponse(
        job_id=job_id,
        total_pages=len(pages),
        detail="已应用编辑并更新预览",
    )


@router.get("/jobs/{job_id}/download")
async def download_zip(job_id: str):
    """打包下载所有结果为 .zip"""
    job = _get_completed_job(job_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add text files
        result = job.result
        if result:
            for page in result.pages:
                zf.writestr(f"page_{page.page_number}.txt", page.content)
            for i, preview in enumerate(result.previews):
                zf.writestr(f"preview_page_{i + 1}.png", preview.image_bytes)
                zf.writestr(f"preview_page_{i + 1}.html", preview.html_content)

        # Add combined preview
        preview_path = job.work_dir / "preview.html"
        if preview_path.exists():
            zf.write(preview_path, "preview.html")

        # Add result.json
        json_path = job.work_dir / "result.json"
        if json_path.exists():
            zf.write(json_path, "result.json")

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=rednote_{job_id}.zip"},
    )
