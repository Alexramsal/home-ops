"""F2: locale/regional defaults guard — explicit user values win, schema defaults apply when missing.

The locale "config" is not a YAML file: regional defaults (EUR, ITP, mortgage
years, timezone) live in the Pydantic models. These tests pin the guard.
"""

from __future__ import annotations

import textwrap

from home_ops.config.loader import load_config


def _write(tmp_path, body: str):
    p = tmp_path / "user_profile.yml"
    p.write_text(textwrap.dedent(body))
    return p


def test_missing_sections_fall_back_to_regional_defaults(tmp_path) -> None:
    # Minimal profile: no buyer_protection, no alert_schedule, no scoring
    p = _write(
        tmp_path,
        """
        portal:
          idealista_url: https://example.com/
        hitl_approval_required: true
        """,
    )
    cfg = load_config(p, env_path=tmp_path / ".env")
    # buyer_protection es opt-in: sin bloque, queda None (los defaults de ITP/
    # hipoteca viven en el modelo y solo se usan si el bloque existe).
    assert cfg.buyer_protection is None
    assert cfg.alert_schedule.timezone == "Europe/Madrid"
    assert cfg.alert_schedule.mode == "daily"
    assert cfg.euribor_rate == 3.5


def test_explicit_user_values_win_over_defaults(tmp_path) -> None:
    p = _write(
        tmp_path,
        """
        portal:
          idealista_url: https://example.com/
        alert_schedule:
          timezone: America/Mexico_City
          mode: interval
          interval_hours: 24.0
        euribor_rate: 2.1
        buyer_protection:
          default_itp_rate: 0.05
          mortgage_years: 25
        """,
    )
    cfg = load_config(p, env_path=tmp_path / ".env")
    assert cfg.alert_schedule.timezone == "America/Mexico_City"
    assert cfg.alert_schedule.mode == "interval"
    assert cfg.alert_schedule.interval_hours == 24.0
    assert cfg.euribor_rate == 2.1
    assert cfg.buyer_protection is not None
    assert cfg.buyer_protection.default_itp_rate == 0.05
    assert cfg.buyer_protection.mortgage_years == 25


def test_partial_block_merges_defaults_and_explicit(tmp_path) -> None:
    # Only mortgage_years set: other BuyerProtection defaults survive
    p = _write(
        tmp_path,
        """
        portal:
          idealista_url: https://example.com/
        buyer_protection:
          mortgage_years: 40
        """,
    )
    cfg = load_config(p, env_path=tmp_path / ".env")
    assert cfg.buyer_protection is not None
    assert cfg.buyer_protection.mortgage_years == 40
    assert cfg.buyer_protection.down_payment_pct == 0.20  # default survives
    assert cfg.buyer_protection.mortgage_income_ceiling == 0.35
