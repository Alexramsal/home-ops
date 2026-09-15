"""Setup wizard core: read current config, merge edits, write back safely.

Pure functions — no Textual, no network. Testable in isolation.

The wizard edits *existing* user_profile.yml and .env files in place,
preserving unknown sections/keys, so a user's hand-tuned config is
never clobbered. (ponytail: comentarios YAML no se preservan (yaml.safe_dump); upgrade path: ruamel.yaml si un día hace falta).
Secrets stay in .env, everything else in user_profile.yml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Keys that always live in .env (secrets / per-deployment), never in YAML.
ENV_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "HOME_OPS_LOG_JSON",
}

# YAML sections the wizard exposes; anything else in the file is preserved.
WIZARD_SECTIONS = {
    "portal",
    "scoring",
    "scoring_thresholds",
    "hitl_approval_required",
    "euribor_rate",
    "alert_schedule",
    "scraper",
    "buyer_protection",
    "catastro",
    "llm",
}


# Wizard-state keys that are not YAML sections (rebuilt separately on write).
_STATE_ONLY_KEYS = {"portals", "schedule", "catastro_enabled", "telegram", "env", "raw_thresholds"}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _read_env(path: Path) -> dict[str, str]:
    """Parse .env into a dict, keeping only the keys we manage."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in ENV_KEYS:
            values[key] = val.strip()
    return values


def load_state(config_path: Path, env_path: Path) -> dict[str, Any]:
    """Return the current effective wizard state (YAML + .env merged)."""
    yaml_data = _read_yaml(config_path)
    env_data = _read_env(env_path)

    portal = yaml_data.get("portal", {}) or {}
    portal_urls = portal.get("urls") or (
        [portal["idealista_url"]] if portal.get("idealista_url") else []
    )
    scoring = yaml_data.get("scoring", {}) or {}
    thresholds = scoring.get("thresholds", {}) or scoring.get("scoring_thresholds", {}) or {}

    schedule = yaml_data.get("alert_schedule", {}) or {}
    buyer = yaml_data.get("buyer_protection", {}) or {}
    llm = yaml_data.get("llm", {}) or {}
    scraper = yaml_data.get("scraper", {}) or {}

    state: dict[str, Any] = {
        "portals": [str(u) for u in portal_urls],
        "scoring": {
            "min_score_to_alert": thresholds.get("min_score_to_alert", 70),
            "price_median": thresholds.get("price_median", 250000),
            "m2_threshold": thresholds.get("m2_threshold", 80),
            "m2_large_threshold": thresholds.get("m2_large_threshold", 120),
            "salary_province": thresholds.get("salary_province", 30000),
            "weights": thresholds.get("weights", {}),
            "raw_thresholds": thresholds,
        },
        "hitl_approval_required": yaml_data.get("hitl_approval_required", True),
        "euribor_rate": yaml_data.get("euribor_rate", 3.5),
        "schedule": {
            "mode": schedule.get("mode", "daily"),
            "daily_time": schedule.get("daily_time", "09:00"),
            "interval_hours": schedule.get("interval_hours", 168),
            "timezone": schedule.get("timezone", "Europe/Madrid"),
            "max_alerts_per_day": schedule.get("max_alerts_per_day", 5),
        },
        "buyer_protection": {
            "default_itp_rate": buyer.get("default_itp_rate", 0.08),
            "mortgage_income_ceiling": buyer.get("mortgage_income_ceiling", 0.35),
            "down_payment_pct": buyer.get("down_payment_pct", 0.20),
            "mortgage_years": buyer.get("mortgage_years", 30),
        },
        "scraper": scraper,
        "catastro_enabled": bool((yaml_data.get("catastro", {}) or {}).get("enabled", False)),
        "llm": {
            "enabled": bool(llm.get("enabled", False)),
            "model": llm.get("model", ""),
        },
        "telegram": {
            "bot_token": env_data.get("TELEGRAM_BOT_TOKEN", ""),
            "chat_id": env_data.get("TELEGRAM_CHAT_ID", ""),
        },
        "env": {
            "AI_BASE_URL": env_data.get("AI_BASE_URL", ""),
            "AI_API_KEY": env_data.get("AI_API_KEY", ""),
            "AI_MODEL": env_data.get("AI_MODEL", ""),
        },
    }

    # Preserve unknown top-level sections in state
    for k, v in yaml_data.items():
        if k not in WIZARD_SECTIONS and k not in state:
            state[k] = v

    return state


def _portal_block(state: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the portal YAML block, keeping a single idealista_url alias."""
    urls = [str(u) for u in state.get("portals", []) if str(u).strip()]
    block: dict[str, Any] = {}
    if urls:
        block["idealista_url"] = urls[0]
        block["urls"] = urls
    return block


def _scoring_block(state: dict[str, Any]) -> dict[str, Any]:
    s = state.get("scoring", {})
    raw = dict(s.get("raw_thresholds", {}))
    defaults = {
        "min_score_to_alert": 70,
        "price_median": 250000,
        "price_over_median_penalty": 0.30,
        "price_under_median_bonus": 0.20,
        "m2_threshold": 80,
        "m2_large_threshold": 120,
        "affordability_high_ratio": 0.50,
        "affordability_medium_ratio": 0.30,
        "salary_province": 30000,
    }
    thresholds = {**defaults, **raw}
    thresholds["min_score_to_alert"] = s.get("min_score_to_alert", thresholds["min_score_to_alert"])
    thresholds["price_median"] = s.get("price_median", thresholds["price_median"])
    thresholds["m2_threshold"] = s.get("m2_threshold", thresholds["m2_threshold"])
    thresholds["m2_large_threshold"] = s.get("m2_large_threshold", thresholds["m2_large_threshold"])
    thresholds["salary_province"] = s.get("salary_province", thresholds["salary_province"])
    weights = s.get("weights")
    if weights:
        thresholds["weights"] = weights
    return {"thresholds": thresholds}


def _schedule_block(state: dict[str, Any]) -> dict[str, Any]:
    s = state.get("schedule", {})
    block: dict[str, Any] = {
        "timezone": s.get("timezone", "Europe/Madrid"),
        "max_alerts_per_day": s.get("max_alerts_per_day", 5),
    }
    mode = s.get("mode", "daily")
    if mode == "interval":
        block["mode"] = "interval"
        block["interval_hours"] = s.get("interval_hours", 168)
    else:
        block["mode"] = "daily"
        block["daily_time"] = s.get("daily_time", "09:00")
    return block


def _buyer_block(state: dict[str, Any]) -> dict[str, Any]:
    b = state.get("buyer_protection", {})
    block = {
        "default_itp_rate": b.get("default_itp_rate", 0.08),
        "mortgage_income_ceiling": b.get("mortgage_income_ceiling", 0.35),
        "down_payment_pct": b.get("down_payment_pct", 0.20),
        "mortgage_years": b.get("mortgage_years", 30),
    }
    return block


def _llm_block(state: dict[str, Any]) -> dict[str, Any]:
    llm = state.get("llm", {})
    block: dict[str, Any] = {"enabled": bool(llm.get("enabled", False))}
    model = str(llm.get("model", "")).strip()
    if model:
        block["model"] = model
    return block


def _catastro_block(state: dict[str, Any]) -> dict[str, Any]:
    return {"enabled": bool(state.get("catastro_enabled", False))}


def _scraper_block(state: dict[str, Any]) -> dict[str, Any]:
    scraper = state.get("scraper", {})
    return scraper if isinstance(scraper, dict) else {}


def build_yaml(state: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge wizard state into the existing YAML, preserving other sections."""
    merged = dict(existing or {})
    for k, v in state.items():
        if k not in WIZARD_SECTIONS and k not in _STATE_ONLY_KEYS and k not in merged:
            merged[k] = v

    merged["portal"] = _portal_block(state)
    merged["scoring"] = _scoring_block(state)
    merged["scoring_thresholds"] = {"min_score_to_alert": state["scoring"]["min_score_to_alert"]}
    merged["hitl_approval_required"] = state.get("hitl_approval_required", True)
    merged["euribor_rate"] = state.get("euribor_rate", 3.5)
    merged["alert_schedule"] = _schedule_block(state)
    merged["buyer_protection"] = _buyer_block(state)
    merged["catastro"] = _catastro_block(state)
    merged["llm"] = _llm_block(state)
    scraper = _scraper_block(state)
    if scraper:
        merged["scraper"] = scraper
    return merged


# Comment header for .env files the wizard writes.
_ENV_HEADER = (
    "# ─── Home-Ops Environment (written by `homeops setup`) ────────────────────\n"
    "# Secrets only. Non-secret config lives in user_profile.yml.\n"
    "# Never commit this file.\n"
)


def _env_line(key: str, value: str) -> str:
    value = str(value).strip()
    if value and (" " in value or "#" in value):
        value = f'"{value}"'
    return f"{key}={value}"


def build_env(state: dict[str, Any], existing: dict[str, str] | list[str] | None = None) -> str:
    """Render the managed .env content, preserving unmanaged lines/comments."""
    managed = {
        "TELEGRAM_BOT_TOKEN": state["telegram"]["bot_token"],
        "TELEGRAM_CHAT_ID": str(state["telegram"]["chat_id"]),
        "AI_BASE_URL": state["env"]["AI_BASE_URL"],
        "AI_API_KEY": state["env"]["AI_API_KEY"],
        "AI_MODEL": state["env"].get("AI_MODEL") or state["llm"].get("model", ""),
    }

    kept: list[str] = []
    if isinstance(existing, dict):
        for k, v in existing.items():
            if k not in managed:
                kept.append(_env_line(k, str(v)))
    elif isinstance(existing, (list, tuple)):
        for line in existing:
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                kept.append(line)
                continue
            key = line_str.split("=", 1)[0].strip()
            if key not in managed:
                kept.append(line)

    out = [_ENV_HEADER]
    if kept:
        out.extend(kept)
        if kept and kept[-1] != "":
            out.append("")

    for key, value in managed.items():
        if value:
            out.append(_env_line(key, value))
    return "\n".join(out).rstrip() + "\n"


def write_config(config_path: Path, env_path: Path, state: dict[str, Any]) -> None:
    """Persist wizard state to user_profile.yml and .env atomically.

    (ponytail: comentarios YAML no se preservan (yaml.safe_dump); upgrade path: ruamel.yaml si un día hace falta).
    """
    import os

    existing_yaml = _read_yaml(config_path)
    merged = build_yaml(state, existing_yaml)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_suffix(".yml.tmp")
    tmp.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
    tmp.replace(config_path)

    existing_env = _read_env(env_path)
    raw_lines = env_path.read_text().splitlines() if env_path.exists() else []
    preserved: dict[str, str] = {}
    for line in raw_lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("#") or "=" not in line_str:
            continue
        key, _, val = line_str.partition("=")
        key = key.strip()
        if key not in ENV_KEYS and key not in preserved:
            preserved[key] = val.strip()
    env_content = build_env(state, {**{k: v for k, v in existing_env.items()}, **preserved})
    env_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_env = env_path.with_suffix(".env.tmp")
    tmp_env.write_text(env_content)
    tmp_env.replace(env_path)
    os.chmod(env_path, 0o600)


# --- Live validators (network best-effort; return (ok, message)) --------------


def test_telegram(bot_token: str, chat_id: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Try to reach the Telegram Bot API and confirm the chat is reachable."""
    import json
    import urllib.request

    if not bot_token:
        return False, "Token vacío."
    if not chat_id:
        return False, "Chat ID vacío."

    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{bot_token}/getMe", timeout=timeout
        ) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("ok"):
            return False, f"API respondió: {data.get('description', 'error')}"
        bot_name = data["result"].get("username", "?")
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={chat_id}",
            timeout=timeout,
        ) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("ok"):
            return False, f"Chat no accesible: {data.get('description', 'error')}"
        chat_title = data["result"].get("title") or data["result"].get("username") or "?"
        return True, f"Bot @{bot_name} → chat '{chat_title}' OK."
    except Exception as exc:
        return False, f"Error de red: {exc}"


def test_llm(base_url: str, api_key: str, model: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Send one tiny chat completion to the configured OpenAI-compatible endpoint."""
    import json
    import urllib.request

    if not base_url or not api_key or not model:
        return False, "base_url, api_key y model son obligatorios."
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        if "choices" not in data:
            return False, f"Respuesta inesperada: {str(data)[:120]}"
        return True, f"LLM OK: {model} respondió."
    except Exception as exc:
        return False, f"Error de red: {exc}"


# Tell pytest not to collect these validator functions as test cases.
test_telegram.__test__ = False  # type: ignore[attr-defined]
test_llm.__test__ = False  # type: ignore[attr-defined]
