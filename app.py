#!/usr/bin/env python3
"""
rednote-content-studio Web App 入口

Usage:
    python app.py
    python app.py --port 8000
    python app.py --no-open
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.api import router as api_router, ensure_cleanup_task_started


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_cleanup_task_started()
    yield


app = FastAPI(title="rednote-content-studio", docs_url="/docs", lifespan=lifespan)

# Mount API routes
app.include_router(api_router)

# Serve static files
STATIC_DIR = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the SPA"""
    return FileResponse(str(STATIC_DIR / "index.html"))


def open_browser(port: int, delay: float = 1.5):
    """Delayed browser open"""
    time.sleep(delay)
    webbrowser.open(f"http://localhost:{port}")


def main():
    parser = argparse.ArgumentParser(description="rednote-content-studio Web App")
    parser.add_argument("--port", "-p", type=int, default=8000, help="端口 (默认: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="主机 (默认: 127.0.0.1)")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    if not args.no_open:
        threading.Thread(target=open_browser, args=(args.port,), daemon=True).start()

    print(f"\n  rednote-content-studio Web App")
    print(f"  http://{args.host}:{args.port}\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
