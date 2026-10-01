"""Sources CLI helpers: validate and add candidate portal URLs."""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import typer

from home_ops.scraper.challenge import detect_challenge
from home_ops.scraper.portals import PORTALS, portal_for_url, resolve_parser

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

sources_app = typer.Typer(help="Validate candidate portal URLs or add them to user_profile.yml.")


@sources_app.command("validate")
def sources_validate(
    url: str = typer.Argument(..., help="Portal search URL to validate"),
    config_path: ConfigOpt = None,
) -> None:
    """Validate a candidate portal search URL (domain + parser + >=1 item)."""
    import home_ops.cli.app as app_mod

    ok, reason, count = validate_source(url, config_path=config_path)
    if not ok:
        app_mod.console.print(f"[bold red]FAIL:[/bold red] {reason}")
        raise typer.Exit(code=1)
    app_mod.console.print(
        f"[bold green]URL validada para portal {reason} (items={count})[/bold green]"
    )


@sources_app.command("add")
def sources_add(
    url: str = typer.Argument(..., help="Portal search URL to add"),
    config_path: ConfigOpt = None,
) -> None:
    """Validate a portal search URL and append it to portal.urls in user_profile.yml."""
    import home_ops.cli.app as app_mod
    from home_ops.cli.profile import _resolve_profile_path

    try:
        path = _resolve_profile_path(config_path)
        if not path.exists():
            app_mod.console.print(f"[bold red]Profile not found:[/bold red] {path}")
            raise typer.Exit(code=1)
        ok, msg = add_source(path, url)
    except Exception as exc:
        app_mod.console.print(f"[bold red]Add failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    if not ok:
        app_mod.console.print(f"[bold red]FAIL:[/bold red] {msg}")
        raise typer.Exit(code=1)
    app_mod.console.print(f"[bold green]SUCCESS:[/bold green] {msg}")


@sources_app.command("clear")
def sources_clear(
    config_path: ConfigOpt = None,
) -> None:
    """Clear all portal search URLs in user_profile.yml."""
    import home_ops.cli.app as app_mod
    from home_ops.cli.profile import _resolve_profile_path

    path = _resolve_profile_path(config_path)
    if not path.exists():
        app_mod.console.print(f"[bold red]Profile not found:[/bold red] {path}")
        raise typer.Exit(code=1)

    ok = clear_sources(path)
    if not ok:
        app_mod.console.print(
            "[bold red]Clear failed:[/bold red] Profile or portal section invalid"
        )
        raise typer.Exit(code=1)

    app_mod.console.print(f"[bold green]SUCCESS:[/bold green] Cleared portal URLs in {path}")


logger = logging.getLogger(__name__)

SUPPORTED_PORTALS = tuple(PORTALS.keys())


def detect_portal(url: str) -> str | None:
    """Detect portal name from URL domain."""
    p = portal_for_url(url)
    return p.name if p else None


def _get_parser(portal_name: str) -> Any:
    return resolve_parser(portal_name)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return no_accents.replace("-", " ")


def _municipality_matches(url: str, municipality: str) -> bool:
    if not municipality:
        return True
    parsed = urlparse(url)
    target = _normalize((parsed.hostname or "") + " " + parsed.path + " " + parsed.query)
    muni_norm = _normalize(municipality)
    return muni_norm in target


def validate_source(
    url: str,
    config_path: Path | str | None = None,
    fetcher: Any = None,
) -> tuple[bool, str, int]:
    """Validate candidate portal URL.

    Returns (success, portal_or_reason, items_count).
    Does NOT bypass Cloudflare/anti-bot protection beyond standard fetcher.
    """
    if fetcher is None and config_path is not None and not isinstance(config_path, (str, Path)):
        fetcher = config_path
        config_path = None
    if isinstance(config_path, str):
        config_path = Path(config_path)

    portal = portal_for_url(url)
    if not portal:
        return False, f"Unsupported domain (must be one of: {', '.join(SUPPORTED_PORTALS)})", 0

    municipality = ""
    try:
        from home_ops.cli.profile import _resolve_profile_path
        from home_ops.config.loader import load_config

        resolved_path = _resolve_profile_path(config_path)
        if resolved_path.exists():
            cfg = load_config(resolved_path)
            municipality = cfg.search.municipality
    except Exception:
        pass

    if municipality and not _municipality_matches(url, municipality):
        return False, f"URL does not contain expected municipality '{municipality}'", 0

    if fetcher is None:
        try:
            from home_ops.scraper.lifecycle import _fetch_page_text, _get_fetcher

            fetcher_impl = _get_fetcher()
            html = _fetch_page_text(fetcher_impl, url)
        except Exception as exc:
            return False, f"Fetch failed: {exc}", 0
    else:
        try:
            if callable(fetcher):
                raw_html = fetcher(url)
            elif hasattr(fetcher, "fetch"):
                page = fetcher.fetch(url)
                raw_html = page.body.decode("utf-8") if hasattr(page, "body") else str(page)
            else:
                raw_html = str(fetcher)
            html = str(raw_html)
        except Exception as exc:
            return False, f"Fetch failed: {exc}", 0

    if not html or not html.strip():
        return False, "Empty page response", 0

    challenge = detect_challenge(html, url=url)
    if challenge.detected:
        return False, f"Anti-bot challenge detected: {challenge.kind.value} ({challenge.details})", 0

    try:
        parser = resolve_parser(portal.name)
        items = parser(html)
    except Exception as exc:
        return False, f"Parse failed for {portal.name}: {exc}", 0

    if not items:
        return False, f"Parsed 0 items from {portal.name} page", 0

    return True, portal.name, len(items)


def add_source(config_path: Path, url: str, fetcher: Any = None) -> tuple[bool, str]:
    """Validate and append URL to portal.urls in user_profile.yml.

    Atomic write; fails fast and does not mutate config on FAIL.
    """
    ok, reason, count = validate_source(url, config_path=config_path, fetcher=fetcher)
    if not ok:
        return False, f"Validation failed: {reason}"

    from home_ops.cli.profile import _read_yaml, _write_yaml_atomic

    data = _read_yaml(config_path)
    portal_block = data.setdefault("portal", {})
    urls = portal_block.setdefault("urls", [])
    if not isinstance(urls, list):
        urls = [str(urls)]
        portal_block["urls"] = urls

    if url in urls:
        return True, f"URL already present in portal.urls (validated {count} items from {reason})"

    urls.append(url)
    _write_yaml_atomic(config_path, data)
    return True, f"Added {url} to portal.urls (validated {count} items from {reason})"


def clear_sources(config_path: Path) -> bool:
    """Clear portal.urls and remove legacy portal.idealista_url in user_profile.yml.

    Returns True if successfully cleared, False if profile does not exist or profile/portal is invalid.
    """
    if not config_path.exists():
        return False

    from home_ops.cli.profile import _read_yaml, _write_yaml_atomic

    try:
        data = _read_yaml(config_path)
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    if "portal" in data:
        if not isinstance(data["portal"], dict):
            return False
        portal_block = data["portal"]
    else:
        portal_block = {}
        data["portal"] = portal_block

    portal_block.pop("idealista_url", None)
    portal_block["urls"] = []

    try:
        _write_yaml_atomic(config_path, data)
        return True
    except Exception:
        return False
