"""Serve the built frontend from the API process.

Lets the whole app run as one container on one port: the frontend already calls
relative `/api/v1` and same-host `/ws`. Enabled only when FRONTEND_DIST_DIR points at
a Vite build; in dev the Vite server does this job instead.

Installed as the router's *not-found fallback*, not as a catch-all route: a matching
`/{path:path}` route would pre-empt Starlette's trailing-slash redirect for every API
route, and only in the container — never in dev.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse

_RESERVED = ("api", "ws")   # never answer these with the SPA shell


def _resolve(dist: Path, index: Path, path: str) -> Optional[Path]:
    """File to send for `path`, or None for a real 404."""
    if path.split("/", 1)[0] in _RESERVED:
        return None
    try:
        target = (dist / path).resolve()
        # is_relative_to: a decoded `..` or an absolute path must not escape the build dir.
        if path and target.is_relative_to(dist) and target.is_file():
            return target
    except (ValueError, OSError):   # e.g. an embedded null byte
        return None
    # A missing *file* (old hashed bundle, favicon) is a 404; only extension-less paths
    # are client-side routes that should get the shell.
    return None if Path(path).suffix else index


def mount_spa(app: FastAPI, dist_dir: str) -> bool:
    if not dist_dir:
        return False
    dist = Path(dist_dir).resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    not_found = app.router.default

    async def spa_fallback(scope, receive, send):
        if scope["type"] == "http" and scope["method"] in ("GET", "HEAD"):
            target = _resolve(dist, index, scope["path"].lstrip("/"))
            if target is not None:
                await FileResponse(target)(scope, receive, send)
                return
        await not_found(scope, receive, send)

    app.router.default = spa_fallback
    return True
