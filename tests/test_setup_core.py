"""Tests for the setup wizard core: state load, safe merge, env render."""

from __future__ import annotations

from pathlib import Path

from home_ops.setup.core import (
    build_env,
    build_yaml,
    load_state,
    test_llm,
    test_telegram,
    write_config,
)

YAML = """\
# Header comment
portal:
  idealista_url: "https://example.com/a"
  urls:
    - "https://example.com/a"
scoring:
  thresholds:
    min_score_to_alert: 70
    price_median: 250000
    m2_threshold: 80
    salary_province: 30000
hitl_approval_required: true
custom_section:
  keep_me: true
"""

ENV = """\
# Existing env comment
TELEGRAM_BOT_TOKEN=old_token
TELEGRAM_CHAT_ID=12345
HOME_OPS_LOG_JSON=1
"""


def test_load_state_merges_yaml_and_env(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    env = tmp_path / ".env"
    cfg.write_text(YAML)
    env.write_text(ENV)

    state = load_state(cfg, env)
    assert state["telegram"]["bot_token"] == "old_token"
    assert state["telegram"]["chat_id"] == "12345"
    assert state["portals"] == ["https://example.com/a"]
    assert state["scoring"]["min_score_to_alert"] == 70
    assert state["scoring"]["price_median"] == 250000
    assert state["llm"]["enabled"] is False


def test_build_yaml_preserves_unknown_sections_and_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text(YAML)
    existing = load_state(cfg, tmp_path / ".env")  # .env missing -> empty

    merged = build_yaml(existing, existing)
    assert merged["custom_section"] == {"keep_me": True}
    assert merged["portal"]["urls"] == ["https://example.com/a"]
    assert merged["scoring"]["thresholds"]["price_median"] == 250000
    # User-provided sections survive even when wizard didn't touch them.
    assert merged["hitl_approval_required"] is True
    # (ponytail: comentarios YAML no se preservan — yaml.safe_dump.)


def test_build_env_keeps_unmanaged_keys_and_quotes(tmp_path: Path) -> None:
    state = {
        "telegram": {"bot_token": "tok 1", "chat_id": "id#2"},
        "env": {"AI_BASE_URL": "http://x", "AI_API_KEY": "k", "AI_MODEL": ""},
        "llm": {"model": "", "enabled": False},
    }
    existing = {"HOME_OPS_LOG_JSON": "1"}
    out = build_env(state, existing)
    assert "HOME_OPS_LOG_JSON=1" in out
    assert 'TELEGRAM_BOT_TOKEN="tok 1"' in out
    assert 'TELEGRAM_CHAT_ID="id#2"' in out
    assert "AI_MODEL=" not in out  # empty -> omitted


def test_write_config_roundtrip_preserves_sections_and_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    env = tmp_path / ".env"
    cfg.write_text(YAML)
    env.write_text(ENV)

    state = load_state(cfg, env)
    state["telegram"]["bot_token"] = "new_token"
    state["telegram"]["chat_id"] = "999"
    state["scoring"]["min_score_to_alert"] = 85
    state["scoring"]["price_median"] = 200000
    state["llm"]["enabled"] = True
    state["env"]["AI_BASE_URL"] = "http://127.0.0.1:20128/v1"
    state["env"]["AI_API_KEY"] = "sk-test"
    state["env"]["AI_MODEL"] = "9r-apply"

    write_config(cfg, env, state)

    # YAML: custom section + updated values survive.
    written = cfg.read_text()
    assert "custom_section" in written
    assert "keep_me" in written
    assert "min_score_to_alert: 85" in written
    assert "price_median: 200000" in written
    assert "llm:" in written
    assert "enabled: true" in written

    # .env: token updated, HOME_OPS_LOG_JSON kept, new AI vars added.
    env_written = env.read_text()
    assert "TELEGRAM_BOT_TOKEN=new_token" in env_written
    assert "TELEGRAM_CHAT_ID=999" in env_written
    assert "HOME_OPS_LOG_JSON=1" in env_written
    assert "AI_BASE_URL=http://127.0.0.1:20128/v1" in env_written
    assert "AI_API_KEY=sk-test" in env_written
    assert "AI_MODEL=9r-apply" in env_written

    # Reload: loader still parses it (roundtrip via real loader).
    from home_ops.config.loader import load_config

    cfg2 = load_config(config_path=cfg, env_path=env)
    assert cfg2.telegram_bot_token == "new_token"
    assert cfg2.telegram_chat_id == "999"
    assert cfg2.scoring is not None
    assert cfg2.scoring.min_score_to_alert == 85
    assert cfg2.scoring.price_median == 200000
    assert cfg2.llm.enabled is True


def test_load_state_missing_files_defaults(tmp_path: Path) -> None:
    state = load_state(tmp_path / "nope.yml", tmp_path / "no.env")
    assert state["telegram"]["bot_token"] == ""
    assert state["portals"] == []
    assert state["scoring"]["min_score_to_alert"] == 70


def test_telegram_validator_missing_creds() -> None:
    ok, _ = test_telegram("", "")
    assert ok is False
    ok, _ = test_telegram("tok", "")
    assert ok is False


def test_llm_validator_missing_creds() -> None:
    ok, _ = test_llm("", "", "")
    assert ok is False
    ok, _ = test_llm("http://x", "", "m")
    assert ok is False


def test_write_config_preserves_custom_thresholds(tmp_path: Path) -> None:
    """F1: wizard save must not reset unexposed scoring.thresholds keys."""
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text(
        "scoring:\n"
        "  thresholds:\n"
        "    min_score_to_alert: 70\n"
        "    price_median: 250000\n"
        "    price_over_median_penalty: 0.40\n"
        "    price_under_median_bonus: 0.10\n"
        "    affordability_high_ratio: 0.55\n"
        "    affordability_medium_ratio: 0.35\n"
        "    custom_extra: 7\n"
    )
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    state = load_state(cfg, env)
    state["scoring"]["min_score_to_alert"] = 85  # wizard-exposed key changes
    write_config(cfg, env, state)

    reloaded = load_state(cfg, env)
    sc = reloaded["scoring"]["raw_thresholds"]
    assert sc["price_over_median_penalty"] == 0.40
    assert sc["price_under_median_bonus"] == 0.10
    assert sc["affordability_high_ratio"] == 0.55
    assert sc["affordability_medium_ratio"] == 0.35
    assert sc["custom_extra"] == 7
    assert sc["min_score_to_alert"] == 85


def test_write_config_restricts_env_permissions(tmp_path: Path) -> None:
    """F3: .env holds secrets -> must be 0600 after write_config."""
    import stat

    cfg = tmp_path / "user_profile.yml"
    env = tmp_path / ".env"
    state = {
        "portals": [],
        "scoring": {"min_score_to_alert": 70, "price_median": 250000},
        "schedule": {},
        "buyer_protection": {},
        "telegram": {"bot_token": "tok", "chat_id": "1"},
        "env": {"AI_BASE_URL": "", "AI_API_KEY": "", "AI_MODEL": ""},
        "llm": {"model": "", "enabled": False},
        "catastro_enabled": False,
        "scraper": {},
    }
    for path in (cfg, env):
        path.write_text("")

    write_config(cfg, env, state)
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_write_config_missing_files_creates_both(tmp_path: Path) -> None:
    """F12c: nonexistent yml + .env are created, no crash."""
    cfg = tmp_path / "sub" / "user_profile.yml"
    env = tmp_path / "sub" / ".env"
    state = {
        "portals": ["https://x"],
        "scoring": {"min_score_to_alert": 70, "price_median": 250000},
        "schedule": {},
        "buyer_protection": {},
        "telegram": {"bot_token": "tok", "chat_id": "1"},
        "env": {"AI_BASE_URL": "", "AI_API_KEY": "", "AI_MODEL": ""},
        "llm": {"model": "", "enabled": False},
        "catastro_enabled": False,
        "scraper": {},
    }

    write_config(cfg, env, state)
    assert cfg.exists()
    assert env.exists()
    assert "TELEGRAM_BOT_TOKEN=tok" in env.read_text()


def test_telegram_validator_api_error() -> None:
    """F12a: Telegram API answers ok=false -> (False, message)."""
    import json
    from unittest import mock

    payload = json.dumps({"ok": False, "description": "unauthorized"}).encode()

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return payload

    with mock.patch("urllib.request.urlopen", return_value=_Resp()):
        ok, msg = test_telegram("tok", "123")
    assert ok is False
    assert "unauthorized" in msg


def test_llm_validator_response_without_choices() -> None:
    """F12b: LLM response lacking 'choices' -> (False, message)."""
    import json
    from unittest import mock

    payload = json.dumps({"error": "nope"}).encode()

    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return payload

    with mock.patch("urllib.request.urlopen", return_value=_Resp()):
        ok, msg = test_llm("http://x", "key", "model")
    assert ok is False
    assert msg
