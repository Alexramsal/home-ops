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
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    # Empty DB: dashboard renders with zeroes, no crash
    assert "Home-Ops" in resp.text
    assert "0" in resp.text
    # No hardcoded legacy values leak from an empty DB
    assert "28 Scored" not in resp.text
    assert "170 observaciones brutas" not in resp.text
    assert "142 observaciones repetidas" not in resp.text
    assert "2026-09-01" not in resp.text


def test_index_renders_listing(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h1', 'Calle Falsa 123', 150000, 80, 'https://example.com/1', 85)"
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Calle Falsa 123" in resp.text
    assert "150,000 €" in resp.text
    assert "85 / 100" in resp.text
    # Dynamic counts rendered, not hardcoded legacy values
    assert "1" in resp.text  # 1 listing, not hardcoded 28
    assert "28 Scored" not in resp.text
    assert "170 observaciones brutas" not in resp.text
    assert "2026-09-01" not in resp.text
    # Pipeline and KPI sections present
    assert "Score ≥ 70" in resp.text
    assert "Fuentes indexadas" in resp.text


def test_index_renders_supported_portal_sources_and_neutralizes_unsafe_url(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings "
            "(content_hash, address, price, m2, url, score, portal) VALUES "
            "('tc', 'Tecnocasa listing', 150000, 80, "
            "'https://www.tecnocasa.es/venta/piso/1', 85, 'tecnocasa')",
            "INSERT INTO listings "
            "(content_hash, address, price, m2, url, score, portal) VALUES "
            "('ha', 'Habitaclia listing', 140000, 70, "
            "'javascript:alert(1)', 80, 'habitaclia')",
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/")

    assert resp.status_code == 200
    assert "Fuentes indexadas" in resp.text
    assert "tecnocasa" in resp.text
    assert "habitaclia" in resp.text
    assert 'href="https://www.tecnocasa.es"' in resp.text
    assert 'href="https://www.habitaclia.com"' in resp.text
    assert "javascript:" not in resp.text


def test_safe_url_resolves_supported_portal_paths() -> None:
    assert web_mod._safe_url("/venta/piso/1", "tecnocasa") == (
        "https://www.tecnocasa.es/venta/piso/1"
    )
    assert web_mod._safe_url("/comprar/vivienda/1", "habitaclia") == (
        "https://www.habitaclia.com/comprar/vivienda/1"
    )
    assert web_mod._safe_url("/listing/1", "unknown") == "#"


def test_index_neutralizes_unsafe_url_scheme(tmp_path, monkeypatch) -> None:
    """Safe-URL helper must neutralize javascript: schemes (defense-in-depth)."""
    assert web_mod._safe_url("javascript:alert(1)") == "#"
    assert web_mod._safe_url("https://example.com/1") == "https://example.com/1"

    # Render path: dirty URLs from the scraper must never leak into the page.
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h2', 'Calle Mala 1', 100000, 60, 'javascript:alert(1)', 50)"
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "javascript:" not in resp.text


def test_index_trends_section_insufficient_weeks(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO price_history (content_hash, zone, price, m2, observed_at) "
            "VALUES ('h1', 'zone1', 150000, 75, '2025-01-01 10:00:00')"
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Tendencias Temporales" in resp.text
    assert "<svg" not in resp.text
    assert "gráfico se activa" in resp.text or "insuficiente" in resp.text


def test_index_trends_section_with_two_weeks(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO price_history (content_hash, zone, price, m2, observed_at) "
            "VALUES ('h1', 'zone1', 150000, 75, '2025-01-01 10:00:00')",
            "INSERT INTO price_history (content_hash, zone, price, m2, observed_at) "
            "VALUES ('h2', 'zone1', 160000, 80, '2025-01-15 10:00:00')",
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Tendencias Temporales" in resp.text
    assert "<svg" in resp.text
    assert "Evolución semanal" in resp.text
