"""Sources CLI helpers: validate and add candidate portal URLs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import typer

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
) -> None:
    """Validate a candidate portal search URL (domain + parser + >=1 item)."""
    import home_ops.cli.app as app_mod

    ok, reason, count = validate_source(url)
    if not ok:
        app_mod.console.print(f"[bold red]FAIL:[/bold red] {reason}")
        raise typer.Exit(code=1)
    app_mod.console.print(f"[bold green]PASS:[/bold green] portal={reason}, items={count}")


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

logger = logging.getLogger(__name__)

SUPPORTED_PORTALS = ("idealista", "fotocasa", "pisos", "habitaclia", "tecnocasa")


def detect_portal(url: str) -> str | None:
    """Detect portal name from URL domain."""
    netloc = urlparse(url).netloc.lower()
    for p in SUPPORTED_PORTALS:
        if p in netloc:
            return p
    return None


def _get_parser(portal: str) -> Any:
    if portal == "idealista":
        from home_ops.scraper import parse

        return parse.parse_listings
    if portal == "fotocasa":
        from home_ops.scraper import fotocasa

        return fotocasa.parse_listings
    if portal == "pisos":
        from home_ops.scraper import pisos

        return pisos.parse_listings
    if portal == "habitaclia":
        from home_ops.scraper import habitaclia

        return habitaclia.parse_listings
    if portal == "tecnocasa":
        from home_ops.scraper import tecnocasa

        return tecnocasa.parse_listings
    raise ValueError(f"No parser for portal: {portal}")


def validate_source(url: str, fetcher: Any = None) -> tuple[bool, str, int]:
    """Validate candidate portal URL.

    Returns (success, portal_or_reason, items_count).
    Does NOT bypass Cloudflare/anti-bot protection beyond standard fetcher.
    """
    portal = detect_portal(url)
    if not portal:
        return False, f"Unsupported domain (must be one of: {', '.join(SUPPORTED_PORTALS)})", 0

    if fetcher is None:
        try:
            from home_ops.scraper.lifecycle import _fetch_page_text, _get_fetcher

            fetcher_impl = _get_fetcher()
            html = _fetch_page_text(fetcher_impl, url)
        except Exception as exc:
            return False, f"Fetch failed: {exc}", 0
    else:
        # For tests / injected fetchers (callable taking url -> html string or fetcher object)
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

    try:
        parser = _get_parser(portal)
        items = parser(html)
    except Exception as exc:
        return False, f"Parse failed for {portal}: {exc}", 0

    if not items:
        return False, f"Parsed 0 items from {portal} page", 0

    return True, portal, len(items)


def add_source(config_path: Path, url: str, fetcher: Any = None) -> tuple[bool, str]:
    """Validate and append URL to portal.urls in user_profile.yml.

    Atomic write; fails fast and does not mutate config on FAIL.
    """
    ok, reason, count = validate_source(url, fetcher=fetcher)
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
