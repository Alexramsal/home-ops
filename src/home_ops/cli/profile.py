"""Profile CLI helpers: validate and set keys in user_profile.yml."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def _resolve_profile_path(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path
    env = os.environ.get("HOME_OPS_CONFIG")
    if env:
        p = Path(env)
        if p.exists():
            return p
    cwd = Path.cwd() / "user_profile.yml"
    if cwd.exists():
        return cwd
    cfg_dir = Path.cwd() / "config" / "user_profile.yml"
    if cfg_dir.exists():
        return cfg_dir
    return cwd


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic YAML write: tmp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".yml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _coerce_value(raw: str, existing: Any) -> Any:
    """Coerce string CLI arg to match the type of `existing`."""
    if existing is None:
        # Try int, then float, then bool, then string
        return _coerce_fallback(raw)
    if isinstance(existing, bool):
        low = raw.lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
        raise ValueError(f"Expected bool (true/false), got: {raw!r}")
    if isinstance(existing, int):
        return int(raw)
    if isinstance(existing, float):
        return float(raw)
    return raw


def _coerce_fallback(raw: str) -> Any:
    low = raw.lower()
    if low in ("true", "yes", "1"):
        return True
    if low in ("false", "no", "0"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def validate_profile(path: Path) -> list[str]:
    """Validate user_profile.yml. Returns list of error strings (empty = OK)."""
    from pydantic import ValidationError

    from home_ops.config.loader import load_config

    try:
        load_config(path)
        return []
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(x) for x in err.get("loc", ()))
            msg = err.get("msg", "unknown error")
            errors.append(f"{loc}: {msg}" if loc else msg)
        return errors
    except Exception as exc:
        return [str(exc)]


def set_profile_value(path: Path, key_path: str, raw_value: str) -> None:
    """Set a single value in user_profile.yml by dotted key path.

    Supports:
    - Top-level scalars: euribor_rate 3.5
    - Nested dots: scoring.thresholds.price_median 200000

    Validates the value type against the existing value before writing.
    Atomic write preserves all other keys.
    """
    data = _read_yaml(path)

    parts = key_path.split(".")
    if not parts or not parts[0]:
        raise ValueError(f"Invalid key path: {key_path!r}")

    # Navigate to parent
    current = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(
                f"Key path {key_path!r} not found: '{part}' missing in {list(current.keys()) if isinstance(current, dict) else type(current).__name__}"
            )
        current = current[part]

    leaf = parts[-1]
    if not isinstance(current, dict) or leaf not in current:
        raise ValueError(
            f"Key '{leaf}' not found. Available: {list(current.keys()) if isinstance(current, dict) else type(current).__name__}"
        )

    existing = current[leaf]
    current[leaf] = _coerce_value(raw_value, existing)

    _write_yaml_atomic(path, data)
