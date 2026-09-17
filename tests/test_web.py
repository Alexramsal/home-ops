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
    assert "<svg" in resp.text
    assert "2024-12-30" in resp.text
    assert "2.000 €/m²" in resp.text
    assert "N=1" in resp.text
    assert "Comparación descriptiva; no constituye una tendencia" in resp.text


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
    assert "Mediana" in resp.text
    assert "Media" in resp.text
    assert "2024-12-30" in resp.text
    assert "2025-01-13" in resp.text
    assert "Comparación semanal real" in resp.text
    assert "DuckDB" in resp.text


def test_index_trends_section_without_observations(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/")

    assert resp.status_code == 200
    assert "Aún no hay observaciones semanales válidas" in resp.text
    assert "<svg" not in resp.text

def test_index_shows_llm_analysis_column(tmp_path, monkeypatch) -> None:
    """Top-10 table must LEFT JOIN llm_analysis and render real values."""
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h1', 'Piso Analizado', 200000, 90, 'https://example.com/a', 90)",
            "INSERT INTO listings (content_hash, address, price, m2, url, score) "
            "VALUES ('h2', 'Piso Sin Analizar', 180000, 70, 'https://example.com/b', 80)",
            "INSERT INTO llm_analysis "
            "(listing_id, estado_reforma, orientacion, ruido_zona, red_flags_llm) "
            "SELECT id, 'Reformado', 'Sur', 'Bajo', "
            "['Humedades', '<script>alert(1)</script>'] "
            "FROM listings WHERE content_hash = 'h1'",
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/")
    assert resp.status_code == 200
    assert "Análisis IA" in resp.text
    assert "Reformado" in resp.text
    assert "Sur" in resp.text
    assert "Bajo" in resp.text
    assert "Humedades" in resp.text
    # Analyzed listing and unanalyzed listing both present
    assert "Piso Analizado" in resp.text
    assert "Piso Sin Analizar" in resp.text
    assert "Sin analizar" in resp.text
    # Jinja escapes LLM-provided text (no raw HTML execution)
    assert "<script>alert(1)</script>" not in resp.text


def test_index_defaults_to_spanish(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/")

    assert resp.status_code == 200
    assert '<html lang="es">' in resp.text
    assert "Selección Cuantitativa Auditada" in resp.text
    assert "Capturas brutas registradas" in resp.text


def test_index_english_via_query(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/?lang=en")

    assert resp.status_code == 200
    assert '<html lang="en">' in resp.text
    assert "Audited Quantitative Selection" in resp.text
    assert "Raw captures recorded" in resp.text
    assert "Indexed sources" in resp.text
    assert "Selección Cuantitativa Auditada" not in resp.text


def test_index_english_via_accept_language(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/", headers={"accept-language": "en-US,en;q=0.9"})

    assert resp.status_code == 200
    assert '<html lang="en">' in resp.text
    assert "Audited Quantitative Selection" in resp.text


def test_index_query_beats_accept_language(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    resp = TestClient(web_mod.app).get("/?lang=es", headers={"accept-language": "en-US,en"})

    assert resp.status_code == 200
    assert '<html lang="es">' in resp.text
    assert "Selección Cuantitativa Auditada" in resp.text


def test_index_lang_selector_visible_and_accessible(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(db_path, [])
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    es = TestClient(web_mod.app).get("/").text
    assert 'href="?lang=es"' in es
    assert 'href="?lang=en"' in es
    assert 'aria-label="Seleccionar idioma"' in es

    en = TestClient(web_mod.app).get("/?lang=en").text
    assert 'aria-label="Select language"' in en


def test_index_pagination_and_stable_sort(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    # Seed 15 listings with identical scores to test stable sort by ID
    sql_list = []
    for i in range(1, 16):
        sql_list.append(
            f"INSERT INTO listings (id, content_hash, address, price, m2, url, score) "
            f"VALUES ({i}, 'h{i}', 'Avenida {i:02d} Norte', 100000, 50, 'https://example.com/{i}', 80)"
        )
    _seed(db_path, sql_list)
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)

    # Default / page 1
    resp1 = client.get("/")
    assert resp1.status_code == 200
    assert "Avenida 01 Norte" in resp1.text
    assert "Avenida 10 Norte" in resp1.text
    assert "Avenida 11 Norte" not in resp1.text
    assert "15" in resp1.text  # Total count in pagination bar

    # Page 2
    resp2 = client.get("/?page=2")
    assert resp2.status_code == 200
    assert "Avenida 11 Norte" in resp2.text
    assert "Avenida 15 Norte" in resp2.text
    assert "Avenida 01 Norte" not in resp2.text

    # Invalid page out of bounds -> clamped to page 1 or max page
    resp_invalid = client.get("/?page=999")
    assert resp_invalid.status_code == 200
    assert "Avenida 11 Norte" in resp_invalid.text  # Clamped to last page (2)

    resp_neg = client.get("/?page=-5")
    assert resp_neg.status_code == 200
    assert "Avenida 01 Norte" in resp_neg.text  # Clamped to page 1


def test_index_expandable_accessible_ai_row_and_responsive_wrapper(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    _seed(
        db_path,
        [
            "INSERT INTO listings (id, content_hash, address, price, m2, url, score) "
            "VALUES (42, 'h42', 'Calle Accessible 42', 120000, 60, 'https://example.com/42', 90)",
            "INSERT INTO llm_analysis "
            "(listing_id, estado_reforma, orientacion, ruido_zona, red_flags_llm, auditoria) "
            "VALUES (42, 'Excelente', 'Sur', 'Bajo', ['Ninguno'], 'Auditoría completa verificada.')",
        ],
    )
    monkeypatch.setattr(web_mod, "get_db_path", lambda: db_path)

    client = TestClient(web_mod.app)
    resp = client.get("/")
    assert resp.status_code == 200

    # Responsive wrapper
    assert 'class="table-responsive"' in resp.text or 'style="overflow-x:auto' in resp.text

    # Accessible toggle button and hidden detail row matching ID
    assert 'aria-controls="ai-detail-42"' in resp.text
    assert 'aria-expanded="false"' in resp.text
    assert 'id="ai-detail-42"' in resp.text
    assert 'hidden' in resp.text
    assert 'Auditoría completa verificada.' in resp.text
