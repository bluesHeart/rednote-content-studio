"""
Job 内存管理

管理转换任务的状态、临时文件和结果。
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import threading
import time


@dataclass
class Job:
    """单个转换任务"""
    id: str
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0
    detail: str = ""
    total_pages: int = 0
    completed_pages: int = 0
    error: Optional[str] = None
    work_dir: Optional[Path] = None
    created_at: float = field(default_factory=time.time)

    # Conversion result reference (set after completion)
    result: Optional[object] = None

    # Partial results available during conversion (pages/previews added incrementally)
    partial_pages: list = field(default_factory=list)
    partial_previews: list = field(default_factory=list)

    # User-editable story middle layer (for final-mile manual adjustments)
    editable_story: Optional[dict] = None

    # Rendering / rewrite context captured from current conversion job
    visual_style: Optional[dict] = None
    tone_system_prompt: Optional[str] = None
    llm_config: Optional[object] = None

    def to_status_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "detail": self.detail,
            "total_pages": self.total_pages,
            "completed_pages": self.completed_pages,
            "error": self.error,
        }


class SessionManager:
    """Job 管理器（内存 + 临时目录）"""

    # Cleanup jobs older than 1 hour
    MAX_JOB_AGE_S = 3600

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create_job(self) -> Job:
        """创建新任务"""
        job_id = uuid.uuid4().hex[:12]
        work_dir = Path(tempfile.mkdtemp(prefix=f"rednote_{job_id}_"))
        job = Job(id=job_id, work_dir=work_dir)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """获取任务"""
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs):
        """更新任务状态"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kwargs.items():
                    if hasattr(job, k):
                        setattr(job, k, v)

    def cleanup_old_jobs(self):
        """清理过期任务"""
        now = time.time()
        with self._lock:
            expired = [
                jid for jid, j in self._jobs.items()
                if now - j.created_at > self.MAX_JOB_AGE_S
            ]
            for jid in expired:
                job = self._jobs.pop(jid, None)
                if job and job.work_dir and job.work_dir.exists():
                    shutil.rmtree(job.work_dir, ignore_errors=True)
