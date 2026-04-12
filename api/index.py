"""Vercel serverless entry point for the ContractGuard FastAPI backend.

Vercel looks for a Python file in the `api/` directory and expects an `app`
ASGI/WSGI object.  This thin wrapper adds the project root to sys.path so
that the existing `backend` package imports resolve correctly, then re-exports
the FastAPI `app` under an `/api` prefix.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend.*` imports work.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.main import app as _original_app

# Create a wrapper app that mounts the original app under /api
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api", _original_app)
