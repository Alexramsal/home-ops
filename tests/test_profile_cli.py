"""Tests for `homeops profile validate` / `homeops profile set`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PROFILE = (
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
