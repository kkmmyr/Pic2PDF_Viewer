from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import main


def _spa_app(
    monkeypatch,
    dist_dir: Path,
) -> FastAPI:
    monkeypatch.setattr(main, "FRONTEND_DIST_DIR", str(dist_dir))
    monkeypatch.setattr(main, "_INDEX_HTML", str(dist_dir / "index.html"))
    app = FastAPI()
    main._register_spa_routes(app)
    return app


def test_spa_schema_is_stable_without_build_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _spa_app(monkeypatch, tmp_path / "missing-dist")
    client = TestClient(app)

    assert {"/", "/{full_path}"} <= set(app.openapi()["paths"])
    assert client.get("/").status_code == 404
    assert client.get("/reader").status_code == 404


def test_spa_routes_serve_build_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("spa-index", encoding="utf-8")
    (dist_dir / "favicon.ico").write_text("icon", encoding="utf-8")
    client = TestClient(_spa_app(monkeypatch, dist_dir))

    assert client.get("/").text == "spa-index"
    assert client.get("/reader").text == "spa-index"
    assert client.get("/favicon.ico").text == "icon"
    assert client.get("/api/missing").status_code == 404
