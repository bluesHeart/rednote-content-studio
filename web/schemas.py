"""
Pydantic 请求/响应模型
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class ConvertRequest(BaseModel):
    """转换请求"""
    markdown: str = Field(..., min_length=1, description="Markdown 文本内容")
    api_key: Optional[str] = Field(default=None, description="LLM API Key（留空则用环境变量）")
    base_url: Optional[str] = Field(default=None, description="LLM API Base URL（留空则用环境变量）")
    model: Optional[str] = Field(default=None, description="LLM 模型名称（留空则用环境变量）")
    visual_template: str = Field(default="minimal_white", description="视觉模板 ID")
    tone_template: str = Field(default="casual", description="语气模板 ID")
    use_visual_feedback: bool = Field(default=False, description="是否启用视觉反馈循环")
    max_iterations: int = Field(default=2, ge=1, le=5, description="最大迭代次数")


class JobCreatedResponse(BaseModel):
    """任务创建响应"""
    job_id: str
    status: str = "pending"


class JobStatusResponse(BaseModel):
    """任务状态响应"""
    job_id: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    detail: str = ""
    total_pages: int = 0
    completed_pages: int = 0
    error: Optional[str] = None


class TemplatesResponse(BaseModel):
    """模板列表响应"""
    visual: list[dict]
    tone: list[dict]
    defaults: dict


class EditableStoryUpdateRequest(BaseModel):
    """Editable story full update payload."""
    story: dict = Field(..., description="完整可编辑中间层 JSON")


class EditableStoryRegenerateRequest(BaseModel):
    """Partial regenerate request for one page."""
    page_number: int = Field(..., ge=1, description="页码（从 1 开始）")
    instruction: Optional[str] = Field(
        default=None,
        description="用户补充要求（例如：更口语、更短句）",
    )


class EditableStoryResponse(BaseModel):
    """Editable story response."""
    job_id: str
    story: dict


class EditableStoryApplyResponse(BaseModel):
    """Apply/re-render response."""
    job_id: str
    total_pages: int
    detail: str
