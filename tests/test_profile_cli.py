"""Tests for `homeops profile validate` / `homeops profile set`."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

PROFILE = (
    "market:\n"
    "  currency: EUR\n"
    "  area_unit: m2\n"
    "  timezone: Europe/Madrid\n"
    "portal:\n"
    "  idealista_url: https://www.idealista.com/venta-viviendas/cadiz-provincia/\n"
    "  urls:\n"
    "  - https://www.idealista.com/venta-viviendas/cadiz-provincia/\n"
    "scoring:\n"
    "  thresholds:\n"
    "    min_score_to_alert: 70.0\n"
    "    price_median: 250000.0\n"
    "    price_over_median_penalty: 0.3\n"
    "    price_under_median_bonus: 0.2\n"
    "    m2_threshold: 80.0\n"
    "    weights:\n"
    "      price: 0.35\n"
    "      size: 0.25\n"
    "      energy_cert: 0.15\n"
    "      garage: 0.1\n"
    "      affordability: 0.15\n"
    "hitl_approval_required: true\n"
    "euribor_rate: 3.5\n"
    "alert_schedule:\n"
    "  timezone: Europe/Madrid\n"
    "  max_alerts_per_day: 5\n"
    "  mode: interval\n"
    "  interval_hours: 168.0\n"
)


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "home_ops.cli.app", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_init_creates_profile_from_template(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    assert not p.exists()
    r = _run("profile", "init", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert p.exists()
    data = yaml.safe_load(p.read_text())
    assert data["search"]["municipality"] == "Chiclana de la Frontera"
    assert data["search"]["max_price"] == 250000


def test_init_fails_if_profile_exists(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "init", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 1
    assert "already exists" in (r.stdout + r.stderr).lower()


def test_wheel_contains_profile_template(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "home_ops/config/user_profile.template.yml" in archive.namelist()


def test_init_write_error_reports_original_error(monkeypatch, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    import home_ops.cli.profile as profile
    from home_ops.cli.app import app

    def fail_write(dest: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(profile, "_copy_file_atomic", fail_write)
    result = CliRunner().invoke(
        app,
        ["profile", "init", "--config", str(tmp_path / "profile.yml")],
    )

    assert result.exit_code == 1
    assert "disk full" in result.output


def test_validate_ok(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "validate", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0
    assert "valid" in r.stdout.lower()


def test_validate_invalid_timezone(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE.replace("Europe/Madrid", "Mars/Olympus"))
    r = _run("profile", "validate", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 1
    assert "timezone" in (r.stdout + r.stderr).lower()


def test_set_float_ok(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "set", "euribor_rate", "3.0", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(p.read_text())
    assert data["euribor_rate"] == 3.0
    # Other keys preserved
    assert data["hitl_approval_required"] is True
    assert data["scoring"]["thresholds"]["price_median"] == 250000.0


def test_set_nested_ok(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run(
        "profile",
        "set",
        "scoring.thresholds.price_median",
        "200000",
        "--config",
        str(p),
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(p.read_text())
    assert data["scoring"]["thresholds"]["price_median"] == 200000
    assert data["scoring"]["thresholds"]["min_score_to_alert"] == 70.0


def test_set_string_ok(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run(
        "profile",
        "set",
        "alert_schedule.timezone",
        "Europe/London",
        "--config",
        str(p),
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(p.read_text())
    assert data["alert_schedule"]["timezone"] == "Europe/London"


@pytest.mark.parametrize(
    ("raw_unit", "canonical"),
    [
        ("m²", "m2"),
        ("m^2", "m2"),
        ("sqm", "m2"),
        ("sq m", "m2"),
        ("ft²", "ft2"),
        ("ft^2", "ft2"),
        ("sqft", "ft2"),
        ("sq ft", "ft2"),
    ],
)
def test_set_market_area_unit_normalizes_aliases(
    tmp_path: Path, raw_unit: str, canonical: str
) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "set", "market.area_unit", raw_unit, "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert yaml.safe_load(p.read_text())["market"]["area_unit"] == canonical


def test_set_market_area_unit_unknown_remains_invalid(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "set", "market.area_unit", "yards", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    validation = _run("profile", "validate", "--config", str(p), cwd=tmp_path)
    assert validation.returncode == 1
    assert "area_unit" in (validation.stdout + validation.stderr)


def test_set_invalid_key_rejected(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    before = p.read_text()
    r = _run("profile", "set", "nonexistent.key", "1", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 1
    assert "not found" in (r.stdout + r.stderr).lower()
    assert p.read_text() == before  # nothing written


def test_set_invalid_type_rejected(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    before = p.read_text()
    r = _run("profile", "set", "euribor_rate", "abc", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 1
    assert p.read_text() == before  # atomic: nothing written on failure


def test_set_list_coercion_ok(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run("profile", "set", "portal.urls", "[]", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(p.read_text())
    assert data["portal"]["urls"] == []


def test_set_list_coercion_elements(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    r = _run(
        "profile",
        "set",
        "portal.urls",
        "['https://www.pisos.com/test/']",
        "--config",
        str(p),
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(p.read_text())
    assert data["portal"]["urls"] == ["https://www.pisos.com/test/"]


def test_set_list_invalid_rejected(tmp_path: Path) -> None:
    p = tmp_path / "user_profile.yml"
    p.write_text(PROFILE)
    before = p.read_text()
    r = _run("profile", "set", "portal.urls", "not_a_list", "--config", str(p), cwd=tmp_path)
    assert r.returncode == 1
    assert p.read_text() == before
