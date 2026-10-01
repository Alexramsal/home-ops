"""TDD tests for structured agentic UX CLI commands:
- location inspect [COUNTRY_CODE]
- cadastre show [COUNTRY_CODE]
- adapter verify PORTAL_NAME
"""

from __future__ import annotations

from typer.testing import CliRunner

import home_ops.cli.agent_ux as agent_ux
from home_ops.cli.app import app

runner = CliRunner()


def test_location_inspect_es() -> None:
    result = runner.invoke(app, ["location", "inspect", "ES"])
    assert result.exit_code == 0
    assert "ES" in result.output
    assert "EUR" in result.output
    assert "Europe/Madrid" in result.output
    assert "m2" in result.output
    assert "active" in result.output.lower() or "activo" in result.output.lower()


def test_location_inspect_it() -> None:
    result = runner.invoke(app, ["location", "inspect", "IT"])
    assert result.exit_code == 0
    assert "IT" in result.output
    assert "Europe/Rome" in result.output
    assert "Inactive" in result.output


def test_location_inspect_non_es() -> None:
    result = runner.invoke(app, ["location", "inspect", "DE"])
    assert result.exit_code == 0
    assert "DE" in result.output
    assert "EUR" in result.output
    assert "Europe/Berlin" in result.output
    assert "m2" in result.output
    assert "inactive" in result.output.lower() or "desactivado" in result.output.lower() or "disabled" in result.output.lower()


def test_location_inspect_municipalities(monkeypatch) -> None:
    countries = {
        "Roma": "IT",
        "Berlin": "DE",
        "Chiclana de la Frontera": "ES",
    }
    monkeypatch.setattr(agent_ux, "_geocode_location", lambda location: countries[location])
    for location, country in countries.items():
        result = runner.invoke(app, ["location", "inspect", location])
        assert result.exit_code == 0
        assert location in result.output
        assert country in result.output
        assert ("Active" if country == "ES" else "Inactive") in result.output


def test_location_inspect_geocoder_failure(monkeypatch) -> None:
    monkeypatch.setattr(agent_ux, "_geocode_location", lambda location: None)
    result = runner.invoke(app, ["location", "inspect", "Unknown"])
    assert result.exit_code == 1
    assert "geocod" in result.output.lower()
    assert "ES" not in result.output


def test_location_inspect_unknown_country(monkeypatch) -> None:
    monkeypatch.setattr(agent_ux, "_geocode_location", lambda location: "XX")
    result = runner.invoke(app, ["location", "inspect", "Unknown"])
    assert result.exit_code == 1
    assert "country" in result.output.lower()


def test_cadastre_show_es() -> None:
    result = runner.invoke(app, ["cadastre", "show", "ES"])
    assert result.exit_code == 0
    assert "Sede Electrónica del Catastro" in result.output
    assert "https://www.sedecatastro.gob.es/" in result.output
    assert "automatic" in result.output.lower() or "automático" in result.output.lower() or "true" in result.output.lower()


def test_cadastre_show_de() -> None:
    result = runner.invoke(app, ["cadastre", "show", "DE"])
    assert result.exit_code == 0
    assert "BORIS-D" in result.output
    assert "https://www.boris-d.de/" in result.output
    assert "manual" in result.output.lower() or "false" in result.output.lower()


def test_cadastre_show_unknown() -> None:
    result = runner.invoke(app, ["cadastre", "show", "XX"])
    assert result.exit_code == 1
    assert "XX" in result.output or "not found" in result.output.lower() or "no cadastre" in result.output.lower()


def test_adapter_verify_supported() -> None:
    for name in ["idealista", "fotocasa", "pisos", "tecnocasa", "habitaclia", "njuskalo", "kleinanzeigen", "green_acres", "bienici"]:
        result = runner.invoke(app, ["adapter", "verify", name])
        assert result.exit_code == 0
        assert name in result.output
        assert "pass" in result.output.lower() or "ok" in result.output.lower() or "valid" in result.output.lower()


def test_adapter_verify_unsupported() -> None:
    result = runner.invoke(app, ["adapter", "verify", "unsupported_portal"])
    assert result.exit_code == 1
    assert "unsupported_portal" in result.output


def test_profile_module_does_not_export_location_app() -> None:
    import home_ops.cli.profile as profile_mod

    assert not hasattr(profile_mod, "location_app")
    assert not hasattr(profile_mod, "location_inspect")
