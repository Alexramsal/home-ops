"""Tests for `homeops sources validate` and `homeops sources add`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from home_ops.cli.app import app
from home_ops.cli.sources import (
    VerificationState,
    add_source,
    validate_source,
)

PISOS_URL = "https://www.pisos.com/venta/pisos-cadiz/"
PISOS_OPAQUE_URL = "https://www.pisos.com/comprar/piso-1234567/"
PISOS_CHICLANA_URL = "https://www.pisos.com/venta/pisos-chiclana-de-la-frontera/"
UNKNOWN_URL = "https://www.inmobiliaria-desconocida.es/pisos/"
DAFT_URL = "https://www.daft.ie/for-sale/cork"
SREALITY_URL = "https://www.sreality.cz/detail/prodej/byt/brno"
NIERUCHOMOSCI_URL = "https://krakow.nieruchomosci-online.pl/mieszkanie,sprzedaz/"

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

FIXTURES = Path(__file__).parent / "fixtures"


def _write_profile(tmp_path: Path, municipality: str, name: str = "user_profile.yml") -> Path:
    profile = tmp_path / name
    profile.write_text(f"search:\n  municipality: {municipality}\nportal:\n  urls: []\n")
    return profile


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _stub_parser(monkeypatch: pytest.MonkeyPatch, items: list[dict[str, Any]]) -> None:
    monkeypatch.setattr("home_ops.cli.sources.resolve_parser", lambda _name: lambda _html: items)


def _explicit(municipality: str) -> dict[str, Any]:
    return {"location": {"municipality": municipality}, "address": "ignored"}


def test_detect_portal() -> None:
    from home_ops.cli.sources import detect_portal

    assert detect_portal("https://www.idealista.com/venta-viviendas/cadiz/") == "idealista"
    assert detect_portal("https://www.fotocasa.es/es/comprar/viviendas/") == "fotocasa"
    assert detect_portal("https://www.pisos.com/venta/pisos-cadiz/") == "pisos"
    assert detect_portal("https://www.habitaclia.com/comprar/viviendas/") == "habitaclia"
    assert detect_portal("https://www.tecnocasa.es/venta/piso/") == "tecnocasa"
    assert detect_portal("https://krakow.nieruchomosci-online.pl/mieszkania/") == "nieruchomosci_online"
    assert detect_portal("https://www.sreality.cz/detail/prodej/byt/123") == "sreality"
    assert detect_portal("https://www.daft.ie/for-sale/cork/123") == "daft"
    assert detect_portal(UNKNOWN_URL) is None


class TestErrorBoundaries:
    def test_unsupported_domain(self, tmp_path: Path) -> None:
        result = validate_source(UNKNOWN_URL, config_path=_write_profile(tmp_path, "Cádiz"))
        assert result.state is VerificationState.ERROR
        assert "Unsupported domain" in result.message
        assert result.item_count == 0

    def test_empty_html(self, tmp_path: Path) -> None:
        result = validate_source(
            PISOS_URL, config_path=_write_profile(tmp_path, "Cádiz"), fetcher=lambda url: ""
        )
        assert result.state is VerificationState.ERROR
        assert "Empty page" in result.message

    def test_zero_items(self, tmp_path: Path) -> None:
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Cádiz"),
            fetcher=lambda url: PISOS_HTML_EMPTY,
        )
        assert result.state is VerificationState.ERROR
        assert "0 items" in result.message

    def test_parse_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_name: str) -> Any:
            raise RuntimeError("parser exploded")

        monkeypatch.setattr("home_ops.cli.sources.resolve_parser", boom)
        result = validate_source(
            PISOS_URL, config_path=_write_profile(tmp_path, "Cádiz"), fetcher=lambda url: "<html/>"
        )
        assert result.state is VerificationState.ERROR
        assert "Parse failed" in result.message

    def test_fetch_failure(self, tmp_path: Path) -> None:
        def boom(_url: str) -> str:
            raise RuntimeError("network down")

        result = validate_source(PISOS_URL, config_path=_write_profile(tmp_path, "Cádiz"), fetcher=boom)
        assert result.state is VerificationState.ERROR
        assert "Fetch failed" in result.message


class TestAggregation:
    def test_match_on_free_form_content(self, tmp_path: Path) -> None:
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Cádiz"),
            fetcher=lambda url: PISOS_HTML_VALID,
        )
        assert result.state is VerificationState.VERIFIED
        assert result.portal == "pisos"
        assert result.matched == 1
        assert result.resolved == 1
        assert result.share == 1.0

    def test_two_matches_one_mismatch_verifies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [_explicit("Chiclana de la Frontera"), _explicit("Chiclana de la Frontera"), _explicit("Jerez de la Frontera")])
        result = validate_source(
            PISOS_CHICLANA_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.VERIFIED
        assert (result.matched, result.mismatched) == (2, 1)

    def test_exact_tie_is_ambiguous(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_parser(monkeypatch, [_explicit("Chiclana de la Frontera"), _explicit("Jerez de la Frontera")])
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.AMBIGUOUS
        assert result.share == 0.5

    def test_below_threshold_resolved_is_mismatch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [_explicit("Chiclana de la Frontera"), _explicit("Jerez de la Frontera"), _explicit("Cádiz")])
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.MISMATCH
        assert result.matched == 1
        assert result.resolved == 3

    def test_unresolved_excluded_from_denominator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        items: list[dict[str, Any]] = [_explicit("Chiclana de la Frontera")]
        items += [{"address": "somewhere without the town"} for _ in range(9)]
        _stub_parser(monkeypatch, items)
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.VERIFIED
        assert result.resolved == 1
        assert result.share == 1.0
        assert result.unresolved == 9

    def test_all_unresolved_is_ambiguous(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [{"address": "Cádiz provincia"}, {"address": "Calle Mayor 3"}])
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.AMBIGUOUS
        assert result.resolved == 0
        assert result.share is None

    def test_profile_without_search_uses_default_municipality(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = tmp_path / "empty.yml"
        profile.write_text("portal:\n  urls: []\n")
        _stub_parser(monkeypatch, [_explicit("Chiclana de la Frontera")])
        result = validate_source(PISOS_URL, config_path=profile, fetcher=lambda url: "<html/>")
        # SearchConfig default municipality is Cádiz; explicit Chiclana is a mismatch.
        assert result.state is VerificationState.MISMATCH

    def test_misleading_url_content_governs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [_explicit("Jerez de la Frontera"), _explicit("Jerez de la Frontera")])
        result = validate_source(
            PISOS_CHICLANA_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.MISMATCH
        assert "content evidence governs" in result.message

    def test_opaque_url_with_qualifying_content_verifies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [_explicit("Chiclana de la Frontera")])
        result = validate_source(
            PISOS_OPAQUE_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.VERIFIED

    def test_opaque_url_without_evidence_is_ambiguous(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(monkeypatch, [{"price": 1}])
        result = validate_source(
            PISOS_OPAQUE_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.AMBIGUOUS

    def test_province_and_district_only_are_ambiguous(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_parser(
            monkeypatch,
            [{"address": "Cádiz provincia"}, {"address": "Centro, distrito"}],
        )
        result = validate_source(
            PISOS_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: "<html/>",
        )
        assert result.state is VerificationState.AMBIGUOUS


class TestOfflineFixtures:
    def test_daft_cork_matches_cork(self, tmp_path: Path) -> None:
        result = validate_source(
            DAFT_URL,
            config_path=_write_profile(tmp_path, "Cork"),
            fetcher=lambda url: _fixture("daft_cork.html"),
        )
        assert result.state is VerificationState.VERIFIED
        assert result.portal == "daft"
        assert result.item_count > 0

    def test_sreality_brno_matches_brno(self, tmp_path: Path) -> None:
        result = validate_source(
            SREALITY_URL,
            config_path=_write_profile(tmp_path, "Brno"),
            fetcher=lambda url: _fixture("sreality_brno.html"),
        )
        assert result.state is VerificationState.VERIFIED
        assert result.portal == "sreality"

    def test_nieruchomosci_matches_krakow(self, tmp_path: Path) -> None:
        result = validate_source(
            NIERUCHOMOSCI_URL,
            config_path=_write_profile(tmp_path, "Kraków"),
            fetcher=lambda url: _fixture("nieruchomosci_online_krakow.html"),
        )
        assert result.state is VerificationState.VERIFIED
        assert result.portal == "nieruchomosci_online"

    def test_cross_municipality_fixture_is_not_verified(self, tmp_path: Path) -> None:
        result = validate_source(
            DAFT_URL,
            config_path=_write_profile(tmp_path, "Chiclana de la Frontera"),
            fetcher=lambda url: _fixture("daft_cork.html"),
        )
        assert result.state is VerificationState.AMBIGUOUS
        assert result.verified is False

    def test_explicit_config_wins_over_working_directory_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "user_profile.yml").write_text("search:\n  municipality: Madrid\n")
        explicit = _write_profile(tmp_path, "Cork", name="explicit.yml")
        result = validate_source(
            DAFT_URL,
            config_path=explicit,
            fetcher=lambda url: _fixture("daft_cork.html"),
        )
        assert result.state is VerificationState.VERIFIED

    def test_optional_live_probe_skips_explicitly(self) -> None:
        live_html = os.environ.get("HOME_OPS_LIVE_HTML")
        if not live_html:
            pytest.skip("optional live portal probe disabled (set HOME_OPS_LIVE_HTML)")
        pytest.skip("live probe path intentionally not executed in offline CI")


class TestAddSourceGate:
    def test_mismatch_does_not_mutate_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = _write_profile(tmp_path, "Chiclana de la Frontera")
        before = profile.read_bytes()
        _stub_parser(monkeypatch, [_explicit("Jerez de la Frontera"), _explicit("Jerez de la Frontera")])
        ok, msg = add_source(profile, PISOS_CHICLANA_URL, fetcher=lambda url: "<html/>")
        assert ok is False
        assert "Validation failed" in msg
        assert profile.read_bytes() == before

    def test_ambiguous_does_not_mutate_profile(self, tmp_path: Path) -> None:
        profile = _write_profile(tmp_path, "Chiclana de la Frontera")
        before = profile.read_bytes()
        ok, msg = add_source(profile, PISOS_URL, fetcher=lambda url: PISOS_HTML_EMPTY)
        assert ok is False
        assert profile.read_bytes() == before

    def test_error_does_not_mutate_profile(self, tmp_path: Path) -> None:
        profile = _write_profile(tmp_path, "Chiclana de la Frontera")
        before = profile.read_bytes()
        ok, _ = add_source(profile, UNKNOWN_URL, fetcher=lambda url: "<html/>")
        assert ok is False
        assert profile.read_bytes() == before

    def test_verified_add_appends_and_is_idempotent(self, tmp_path: Path) -> None:
        profile = _write_profile(tmp_path, "Cádiz")
        ok, msg = add_source(profile, PISOS_URL, fetcher=lambda url: PISOS_HTML_VALID)
        assert ok is True
        assert "Added" in msg
        data = yaml.safe_load(profile.read_text())
        assert data["portal"]["urls"] == [PISOS_URL]

        ok2, msg2 = add_source(profile, PISOS_URL, fetcher=lambda url: PISOS_HTML_VALID)
        assert ok2 is True
        assert "already present" in msg2
        data2 = yaml.safe_load(profile.read_text())
        assert data2["portal"]["urls"].count(PISOS_URL) == 1


class TestCLI:
    def test_cli_validate_verified_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = _write_profile(tmp_path, "Cádiz")
        monkeypatch.setattr("home_ops.scraper.lifecycle._get_fetcher", lambda: object())
        monkeypatch.setattr(
            "home_ops.scraper.lifecycle._fetch_page_text", lambda fetcher, url: PISOS_HTML_VALID
        )
        result = CliRunner().invoke(app, ["sources", "validate", PISOS_URL, "--config", str(profile)])
        assert result.exit_code == 0, result.output
        assert "verified" in result.output.lower()

    def test_cli_validate_ambiguous_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = _write_profile(tmp_path, "Chiclana de la Frontera")
        monkeypatch.setattr("home_ops.scraper.lifecycle._get_fetcher", lambda: object())
        monkeypatch.setattr(
            "home_ops.scraper.lifecycle._fetch_page_text", lambda fetcher, url: PISOS_HTML_EMPTY
        )
        result = CliRunner().invoke(app, ["sources", "validate", PISOS_URL, "--config", str(profile)])
        assert result.exit_code == 1


def test_clear_sources_removes_urls_and_legacy_alias(tmp_path: Path) -> None:
    from home_ops.cli.sources import clear_sources

    p = tmp_path / "user_profile.yml"
    p.write_text("portal:\n  idealista_url: https://legacy\n  urls:\n  - https://one\n")
    assert clear_sources(p) is True
    data = yaml.safe_load(p.read_text())
    assert data["portal"] == {"urls": []}


def test_clear_sources_idempotent(tmp_path: Path) -> None:
    from home_ops.cli.sources import clear_sources

    p = tmp_path / "user_profile.yml"
    p.write_text("portal:\n  urls: []\n")
    assert clear_sources(p) is True
    assert clear_sources(p) is True
    data = yaml.safe_load(p.read_text())
    assert data["portal"] == {"urls": []}


def test_clear_sources_file_not_found(tmp_path: Path) -> None:
    from home_ops.cli.sources import clear_sources

    assert clear_sources(tmp_path / "nonexistent.yml") is False


def test_clear_sources_invalid_profile_does_not_mutate(tmp_path: Path) -> None:
    from home_ops.cli.sources import clear_sources

    p = tmp_path / "user_profile.yml"
    p.write_text("portal: bad\n")
    before = p.read_text()
    assert clear_sources(p) is False
    assert p.read_text() == before


def test_cli_subcommands_registered() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "home_ops.cli.app", "sources", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "validate" in r.stdout
    assert "add" in r.stdout
    assert "clear" in r.stdout


def test_template_sources_are_municipality_scoped() -> None:
    """Template URLs target the declared municipality; no live claim is made."""
    from home_ops.scraper.location import normalize_text

    template = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "user_profile.template.yml").read_text()
    )
    municipality = normalize_text(template["search"]["municipality"])
    assert municipality == "chiclana de la frontera"
    for url in template["portal"]["urls"]:
        assert municipality in normalize_text(url), url
