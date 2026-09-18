"""Tests for `homeops sources validate` and `homeops sources add`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PISOS_URL = "https://www.pisos.com/venta/pisos-cadiz/"
UNKNOWN_URL = "https://www.inmobiliaria-desconocida.es/pisos/"

PISOS_HTML_VALID = """
<html>
<body>
  <div class="grid-container">
    <div class="ad-preview" id="12345.1">
      <a class="ad-preview__title" href="/comprar/piso-cadiz-12345/1">Piso en Venta en Cadiz Centro</a>
      <p class="ad-preview__subtitle">Cadiz</p>
      <span class="ad-preview__price">180.000 €</span>
      <p class="ad-preview__char">90 m²</p>
    </div>
  </div>
</body>
</html>
"""

PISOS_HTML_EMPTY = "<html><body><div>Sin resultados</div></body></html>"


def test_detect_portal() -> None:
    from home_ops.cli.sources import detect_portal

    assert detect_portal("https://www.idealista.com/venta-viviendas/cadiz/") == "idealista"
    assert detect_portal("https://www.fotocasa.es/es/comprar/viviendas/") == "fotocasa"
    assert detect_portal("https://www.pisos.com/venta/pisos-cadiz/") == "pisos"
    assert detect_portal("https://www.habitaclia.com/comprar/viviendas/") == "habitaclia"
    assert detect_portal("https://www.tecnocasa.es/venta/piso/") == "tecnocasa"
    assert detect_portal(UNKNOWN_URL) is None


def test_validate_source_unsupported_domain() -> None:
    from home_ops.cli.sources import validate_source

    ok, reason, count = validate_source(UNKNOWN_URL, fetcher=lambda url: "<html></html>")
    assert ok is False
    assert "Unsupported domain" in reason
    assert count == 0


def test_validate_source_empty_html() -> None:
    from home_ops.cli.sources import validate_source

    ok, reason, count = validate_source(PISOS_URL, fetcher=lambda url: "")
    assert ok is False
    assert "Empty page" in reason
    assert count == 0


def test_validate_source_zero_items() -> None:
    from home_ops.cli.sources import validate_source

    ok, reason, count = validate_source(PISOS_URL, fetcher=lambda url: PISOS_HTML_EMPTY)
    assert ok is False
    assert "0 items" in reason
    assert count == 0


def test_validate_source_pass() -> None:
    from home_ops.cli.sources import validate_source

    ok, portal, count = validate_source(PISOS_URL, fetcher=lambda url: PISOS_HTML_VALID)
    assert ok is True
    assert portal == "pisos"
    assert count >= 1


def test_add_source_fail_does_not_mutate_config(tmp_path: Path) -> None:
    from home_ops.cli.sources import add_source

    p = tmp_path / "user_profile.yml"
    p.write_text("portal:\n  urls:\n  - https://www.idealista.com/test/\n")
    before = p.read_text()

    ok, msg = add_source(p, PISOS_URL, fetcher=lambda url: PISOS_HTML_EMPTY)
    assert ok is False
    assert "Validation failed" in msg
    assert p.read_text() == before


def test_add_source_pass_appends_to_urls(tmp_path: Path) -> None:
    from home_ops.cli.sources import add_source

    p = tmp_path / "user_profile.yml"
    p.write_text("portal:\n  urls:\n  - https://www.idealista.com/test/\n")

    ok, msg = add_source(p, PISOS_URL, fetcher=lambda url: PISOS_HTML_VALID)
    assert ok is True
    assert "Added" in msg
    data = yaml.safe_load(p.read_text())
    assert PISOS_URL in data["portal"]["urls"]
    assert len(data["portal"]["urls"]) == 2


def test_add_source_idempotent(tmp_path: Path) -> None:
    from home_ops.cli.sources import add_source

    p = tmp_path / "user_profile.yml"
    p.write_text(f"portal:\n  urls:\n  - {PISOS_URL}\n")

    ok, msg = add_source(p, PISOS_URL, fetcher=lambda url: PISOS_HTML_VALID)
    assert ok is True
    assert "already present" in msg
    data = yaml.safe_load(p.read_text())
    assert data["portal"]["urls"].count(PISOS_URL) == 1


def test_cli_subcommands_registered() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "home_ops.cli.app", "sources", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "validate" in r.stdout
    assert "add" in r.stdout
