"""Profile CLI helpers: validate and set keys in user_profile.yml."""

from __future__ import annotations

import contextlib
import importlib.resources
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

ConfigOpt = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path to user_profile.yml (default: auto-discover)",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]

ConfigInitOpt = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path for new user_profile.yml (default: user_profile.yml)",
        dir_okay=False,
        writable=True,
    ),
]

profile_app = typer.Typer(help="Validate or update user_profile.yml.")

COUNTRY_DEFAULTS: dict[str, tuple[str, str, str, str]] = {
    "ES": ("España", "EUR", "Europe/Madrid", "m2"),
    "DE": ("Deutschland", "EUR", "Europe/Berlin", "m2"),
    "HR": ("Hrvatska", "EUR", "Europe/Zagreb", "m2"),
    "FR": ("France", "EUR", "Europe/Paris", "m2"),
    "US": ("United States", "USD", "America/New_York", "ft2"),
    "GB": ("United Kingdom", "GBP", "Europe/London", "m2"),
    "UK": ("United Kingdom", "GBP", "Europe/London", "m2"),
    "IT": ("Italia", "EUR", "Europe/Rome", "m2"),
    "PT": ("Portugal", "EUR", "Europe/Lisbon", "m2"),
    "NL": ("Nederland", "EUR", "Europe/Amsterdam", "m2"),
    "BE": ("Belgique", "EUR", "Europe/Brussels", "m2"),
    "AT": ("Österreich", "EUR", "Europe/Vienna", "m2"),
    "PL": ("Polska", "PLN", "Europe/Warsaw", "m2"),
    "CZ": ("Česko", "CZK", "Europe/Prague", "m2"),
    "IE": ("Ireland", "EUR", "Europe/Dublin", "m2"),
    "SE": ("Sverige", "SEK", "Europe/Stockholm", "m2"),
    "GR": ("Ελλάδα", "EUR", "Europe/Athens", "m2"),
}

@profile_app.command("init")
def profile_init(config_path: ConfigInitOpt = None) -> None:
    """Initialize a new profile from template. Fails if target file exists."""
    import home_ops.cli.app as app_mod

    dest = config_path if config_path is not None else Path.cwd() / "user_profile.yml"
    if dest.exists():
        app_mod.console.print(f"[bold red]Profile already exists:[/bold red] {dest}")
        raise typer.Exit(code=1)

    template_path = _resolve_template_path()
    if not template_path.exists():
        app_mod.console.print(f"[bold red]Template file not found:[/bold red] {template_path}")
        raise typer.Exit(code=1)

    try:
        content = template_path.read_text(encoding="utf-8")
        _copy_file_atomic(dest, content)
    except Exception as exc:
        app_mod.console.print(f"[bold red]Init failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    app_mod.console.print(f"[bold green]Initialized profile:[/bold green] {dest}")


def _resolve_template_path() -> Path:
    cwd_template = Path.cwd() / "config" / "user_profile.template.yml"
    if cwd_template.exists():
        return cwd_template
    repo_template = Path(__file__).resolve().parents[3] / "config" / "user_profile.template.yml"
    if repo_template.exists():
        return repo_template
    return Path(
        str(importlib.resources.files("home_ops.config").joinpath("user_profile.template.yml"))
    )


@profile_app.command("validate")
def profile_validate(config_path: ConfigOpt = None) -> None:
    """Validate user_profile.yml structure and values. Exit 0 if OK."""
    import home_ops.cli.app as app_mod

    try:
        path = _resolve_profile_path(config_path)
        if not path.exists():
            app_mod.console.print(f"[bold red]Profile not found:[/bold red] {path}")
            raise typer.Exit(code=1)
        errors = validate_profile(path)
    except Exception as exc:
        app_mod.console.print(f"[bold red]Validation failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if errors:
        app_mod.console.print(f"[bold red]Profile invalid ({len(errors)} error(s)):[/bold red]")
        for e in errors:
            app_mod.console.print(f"  - {e}")
        raise typer.Exit(code=1)
    app_mod.console.print(f"[green]Profile valid:[/green] {path}")


@profile_app.command("set")
def profile_set(
    key_path: str,
    value: str,
    config_path: ConfigOpt = None,
) -> None:
    """Set a key in user_profile.yml (dotted path). Atomic write; other keys preserved."""
    import home_ops.cli.app as app_mod

    try:
        path = _resolve_profile_path(config_path)
        if not path.exists():
            app_mod.console.print(f"[bold red]Profile not found:[/bold red] {path}")
            raise typer.Exit(code=1)
        set_profile_value(path, key_path, value)
    except Exception as exc:
        app_mod.console.print(f"[bold red]Set failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    app_mod.console.print(f"[green]Set {key_path}={value}[/green] in {path}")



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


def _copy_file_atomic(path: Path, content: str) -> None:
    """Atomic text write: tmp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".yml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
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
    if isinstance(existing, list):
        try:
            parsed = yaml.safe_load(raw)
        except Exception as exc:
            raise ValueError(f"Expected list, got: {raw!r}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"Expected list, got: {raw!r}")
        return parsed
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
    if key_path == "market.area_unit":
        raw_value = {
            "m²": "m2", "m^2": "m2", "sqm": "m2", "sq m": "m2",
            "ft²": "ft2", "ft^2": "ft2", "sqft": "ft2", "sq ft": "ft2",
        }.get(raw_value, raw_value)
    current[leaf] = _coerce_value(raw_value, existing)

    _write_yaml_atomic(path, data)
