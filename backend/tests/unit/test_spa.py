"""Serving the built frontend from the API process (single-container hosting)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.spa import mount_spa

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def spa(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("TOP SECRET")

    app = FastAPI()

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    assert mount_spa(app, str(dist)) is True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_root_and_deep_links_return_index(spa):
    for path in ("/", "/dashboard", "/strategies/abc-123"):
        resp = await spa.get(path)
        assert resp.status_code == 200 and "INDEX" in resp.text, path


async def test_real_files_are_served(spa):
    resp = await spa.get("/assets/app.js")
    assert resp.status_code == 200 and "console.log" in resp.text


async def test_api_routes_win_and_unknown_api_paths_stay_404(spa):
    assert (await spa.get("/api/v1/health")).json() == {"status": "ok"}
    assert (await spa.get("/api/v1/does-not-exist")).status_code == 404
    assert (await spa.get("/ws")).status_code == 404


async def test_path_traversal_cannot_escape_dist(spa, tmp_path):
    absolute = (tmp_path / "secret.txt").as_posix()
    for path in (
        "/%2e%2e/secret.txt",                 # encoded dots (a literal /../ is normalised by the client)
        "/assets/..%2f..%2fsecret.txt",
        "/..%5csecret.txt",                   # backslash
        f"/%2F{absolute.lstrip('/')}",        # absolute path smuggled after the leading slash
        "/secret.txt%00.js",                  # null byte
    ):
        resp = await spa.get(path)
        assert "TOP SECRET" not in resp.text, path
        assert resp.status_code in (200, 404), path


async def test_missing_asset_is_a_404_not_the_html_shell(spa):
    """A stale tab asking for an old hashed bundle must get 404, not index.html as JS."""
    for path in ("/assets/old-hash.js", "/favicon.ico"):
        assert (await spa.get(path)).status_code == 404, path


async def test_api_trailing_slash_redirect_still_works(spa):
    resp = await spa.get("/api/v1/health/")
    assert resp.status_code == 307 and resp.headers["location"].endswith("/api/v1/health")


async def test_non_get_requests_are_not_answered_with_the_shell(spa):
    assert (await spa.post("/dashboard")).status_code in (404, 405)


async def test_missing_dist_is_a_noop(tmp_path):
    app = FastAPI()
    assert mount_spa(app, str(tmp_path / "nope")) is False
    assert mount_spa(app, "") is False
