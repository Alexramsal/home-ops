"""Smoke test: web dashboard renders (empty DB and with listings), no crash."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from home_ops import web as web_mod  # noqa: E402
from home_ops.models.data_storage import get_connection  # noqa: E402


def _seed(db_path: str, listing_sql: list[str]) -> None:
    with get_connection(db_path) as db:
        db.init_db()
        for sql in listing_sql:
            db.conn.execute(sql)


def test_index_renders_empty(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "_get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    # Empty DB: zeroes everywhere, no crash
    assert "0" in resp.text
    assert "Sin oportunidades" in resp.text


def test_index_renders_listing(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h1', 'Calle Falsa 123', 150000, 80, 'https://example.com/1', 85)"
        ],
    )
    monkeypatch.setattr(web_mod, "_get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Calle Falsa 123" in resp.text
    assert "150,000 €" in resp.text
    assert "85.0" in resp.text  # score renders


def test_index_neutralizes_unsafe_url_scheme(tmp_path, monkeypatch) -> None:
    """javascript: URLs from the scraper must not reach the rendered href."""
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h2', 'Calle Mala 1', 100000, 60, 'javascript:alert(1)', 50)"
        ],
    )
    monkeypatch.setattr(web_mod, "_get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "javascript:" not in resp.text
    assert 'href="#"' in resp.text
