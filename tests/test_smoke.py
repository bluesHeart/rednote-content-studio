from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import app


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_cli_help():
    result = run_cmd("scripts/main.py", "--help")
    assert result.returncode == 0
    assert "Markdown" in result.stdout


def test_web_help():
    result = run_cmd("app.py", "--help")
    assert result.returncode == 0
    assert "rednote-content-studio Web App" in result.stdout


def test_clean_workspace_dry_run():
    result = run_cmd("scripts/clean_workspace.py", "--dry-run")
    assert result.returncode == 0
    assert "[DONE]" in result.stdout


def test_api_templates_and_env_config():
    client = TestClient(app)

    templates_resp = client.get("/api/templates")
    assert templates_resp.status_code == 200
    templates = templates_resp.json()
    assert "visual" in templates
    assert "tone" in templates
    assert "defaults" in templates

    env_resp = client.get("/api/env-config")
    assert env_resp.status_code == 200
    payload = env_resp.json()
    assert "has_env_key" in payload
    assert "base_url_hint" in payload
    assert "model_hint" in payload


def test_api_upload_markdown_and_image_roundtrip():
    client = TestClient(app)

    upload_resp = client.post(
        "/api/upload",
        files={"file": ("sample.md", "# 标题\n\n正文", "text/markdown")},
    )
    assert upload_resp.status_code == 200
    body = upload_resp.json()
    assert body["filename"] == "sample.md"
    assert "标题" in body["content"]

    image_bytes = b"\x89PNG\r\n\x1a\n" + b"demo-bytes"
    image_resp = client.post(
        "/api/upload-image",
        files={"file": ("demo.png", image_bytes, "image/png")},
    )
    assert image_resp.status_code == 200
    image_payload = image_resp.json()
    assert image_payload["url"].startswith("/api/images/")

    image_get = client.get(image_payload["url"])
    assert image_get.status_code == 200
    assert image_get.content == image_bytes


def test_api_convert_rejects_unknown_template_and_not_found_job():
    client = TestClient(app)

    bad_template_resp = client.post(
        "/api/convert",
        json={
            "markdown": "# hello",
            "visual_template": "not-exists",
            "tone_template": "casual",
        },
    )
    assert bad_template_resp.status_code == 400

    not_found_resp = client.get("/api/jobs/notfound/status")
    assert not_found_resp.status_code == 404
