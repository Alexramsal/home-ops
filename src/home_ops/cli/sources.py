"""Sources CLI helpers: validate and add candidate portal URLs."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from home_ops.scraper.challenge import detect_challenge
from home_ops.scraper.location import (
    MunicipalityMatch,
    classify_evidence,
    normalize_text,
    parsed_location_evidence,
)
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


class VerificationState(StrEnum):
    """Explicit outcome of comparing parsed source content against a town."""

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass(frozen=True)
class SourceValidation:
    """Structured source-validation result with evidence distribution."""

    state: VerificationState
    portal: str | None
    item_count: int
    matched: int = 0
    mismatched: int = 0
    unresolved: int = 0
    message: str = ""

    @property
    def resolved(self) -> int:
        return self.matched + self.mismatched

    @property
    def share(self) -> float | None:
        """Matching share over resolved items, or None when none resolved."""
        return self.matched / self.resolved if self.resolved else None

    @property
    def verified(self) -> bool:
        return self.state is VerificationState.VERIFIED


@sources_app.command("validate")
def sources_validate(
    url: str = typer.Argument(..., help="Portal search URL to validate"),
    config_path: ConfigOpt = None,
) -> None:
    """Validate a candidate portal search URL against configured municipality."""
    import home_ops.cli.app as app_mod

    result = validate_source(url, config_path=config_path)
    if not result.verified:
        app_mod.console.print(f"[bold red]FAIL:[/bold red] {result.message}")
        raise typer.Exit(code=1)
    app_mod.console.print(
        f"[bold green]Source verified for portal {result.portal} "
        f"(items={result.item_count})[/bold green]"
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


def _resolve_municipality(config_path: Path | None) -> str:
    try:
        from home_ops.cli.profile import _resolve_profile_path
        from home_ops.config.loader import load_config

        resolved_path = _resolve_profile_path(config_path)
        if resolved_path.exists():
            return load_config(resolved_path).search.municipality
    except Exception:
        pass
    return ""


def _is_error(result: SourceValidation) -> bool:
    return result.state is VerificationState.ERROR


def _aggregate(
    portal: str,
    item_count: int,
    counts: Counter[MunicipalityMatch],
    municipality: str,
    url: str,
) -> SourceValidation:
    matched = counts[MunicipalityMatch.MATCH]
    mismatched = counts[MunicipalityMatch.MISMATCH]
    unresolved = counts[MunicipalityMatch.UNRESOLVED]
    resolved = matched + mismatched
    distribution = f"parsed={item_count}, matched={matched}, mismatched={mismatched}, resolved={resolved}"

    if not municipality:
        return SourceValidation(
            VerificationState.AMBIGUOUS,
            portal,
            item_count,
            matched,
            mismatched,
            unresolved,
            f"Ambiguous: no search.municipality configured to verify against ({distribution})",
        )

    if resolved == 0:
        return SourceValidation(
            VerificationState.AMBIGUOUS,
            portal,
            item_count,
            matched,
            mismatched,
            unresolved,
            f"Ambiguous: no resolved municipality evidence for '{municipality}' "
            f"({distribution}, unresolved={unresolved}); provide a municipality-specific source "
            "or verify manually",
        )

    share = matched / resolved
    share_pct = f"{share * 100:.0f}%"
    if normalize_text(municipality) in normalize_text(url):
        url_note = " (URL text mentions the municipality; content evidence governs)"
    else:
        url_note = " (URL text does not mention the municipality; content evidence governs)"

    if share > 0.5:
        return SourceValidation(
            VerificationState.VERIFIED,
            portal,
            item_count,
            matched,
            mismatched,
            unresolved,
            f"Verified: expected '{municipality}' ({distribution}, unresolved={unresolved}, "
            f"share={share_pct}){url_note}",
        )
    if share == 0.5:
        return SourceValidation(
            VerificationState.AMBIGUOUS,
            portal,
            item_count,
            matched,
            mismatched,
            unresolved,
            f"Ambiguous: matching share for '{municipality}' is an exact tie "
            f"({distribution}, unresolved={unresolved}, share={share_pct}){url_note}",
        )
    return SourceValidation(
        VerificationState.MISMATCH,
        portal,
        item_count,
        matched,
        mismatched,
        unresolved,
        f"Municipality mismatch: expected '{municipality}' ({distribution}, "
        f"unresolved={unresolved}, share={share_pct}){url_note}",
    )


def validate_source(
    url: str,
    config_path: Path | str | None = None,
    fetcher: Any = None,
) -> SourceValidation:
    """Validate a candidate portal URL against parsed listing location evidence.

    Returns an explicit :class:`SourceValidation`. URL text is diagnostic
    only; parsed content evidence governs the ``verified`` contract. Does
    NOT bypass Cloudflare/anti-bot protection beyond the standard fetcher.
    """
    if fetcher is None and config_path is not None and not isinstance(config_path, (str, Path)):
        fetcher = config_path
        config_path = None
    if isinstance(config_path, str):
        config_path = Path(config_path)

    portal = portal_for_url(url)
    if not portal:
        return SourceValidation(
            VerificationState.ERROR,
            None,
            0,
            message=f"Unsupported domain (must be one of: {', '.join(SUPPORTED_PORTALS)})",
        )

    municipality = _resolve_municipality(config_path)

    if fetcher is None:
        try:
            from home_ops.scraper.lifecycle import _fetch_page_text, _get_fetcher

            fetcher_impl = _get_fetcher()
            html = _fetch_page_text(fetcher_impl, url)
        except Exception as exc:
            return SourceValidation(
                VerificationState.ERROR, portal.name, 0, message=f"Fetch failed: {exc}"
            )
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
            return SourceValidation(
                VerificationState.ERROR, portal.name, 0, message=f"Fetch failed: {exc}"
            )

    if not html or not html.strip():
        return SourceValidation(
            VerificationState.ERROR, portal.name, 0, message="Empty page response"
        )

    challenge = detect_challenge(html, url=url)
    if challenge.detected:
        return SourceValidation(
            VerificationState.ERROR,
            portal.name,
            0,
            message=f"Anti-bot challenge detected: {challenge.kind.value} ({challenge.details})",
        )

    try:
        parser = resolve_parser(portal.name)
        items = parser(html)
    except Exception as exc:
        return SourceValidation(
            VerificationState.ERROR,
            portal.name,
            0,
            message=f"Parse failed for {portal.name}: {exc}",
        )

    if not items:
        return SourceValidation(
            VerificationState.ERROR,
            portal.name,
            0,
            message=f"Parsed 0 items from {portal.name} page",
        )

    counts: Counter[MunicipalityMatch] = Counter()
    for item in items:
        counts[classify_evidence(parsed_location_evidence(item), municipality)] += 1

    return _aggregate(portal.name, len(items), counts, municipality, url)


def add_source(config_path: Path, url: str, fetcher: Any = None) -> tuple[bool, str]:
    """Validate and append URL to portal.urls in user_profile.yml.

    Only a ``verified`` source can mutate the profile. Atomic write; fails
    fast and does not mutate config on FAIL.
    """
    result = validate_source(url, config_path=config_path, fetcher=fetcher)
    if not result.verified:
        return False, f"Validation failed: {result.message}"

    from home_ops.cli.profile import _read_yaml, _write_yaml_atomic

    data = _read_yaml(config_path)
    portal_block = data.setdefault("portal", {})
    urls = portal_block.setdefault("urls", [])
    if not isinstance(urls, list):
        urls = [str(urls)]
        portal_block["urls"] = urls

    if url in urls:
        return True, (
            f"URL already present in portal.urls (validated {result.item_count} items "
            f"from {result.portal})"
        )

    urls.append(url)
    _write_yaml_atomic(config_path, data)
    return True, f"Added {url} to portal.urls (validated {result.item_count} items from {result.portal})"


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
