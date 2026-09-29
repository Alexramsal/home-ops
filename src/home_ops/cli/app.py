"""Typer CLI entry point for Home-Ops pipeline orchestration.

Usage:
    homeops scan
    homeops status
    homeops snapshots-reset
    homeops approve <listing_id>
    homeops daemon
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from home_ops.alerter.telegram import TelegramAlerter
from home_ops.cli.agent_ux import adapter_app, cadastre_app, location_app
from home_ops.cli.analytics import _display_analytics
from home_ops.cli.daemon import (
    _get_daily_alert_count,
    _next_run_time,
    _run_daemon_cycle,
    _run_daemon_cycle_locked,
    _run_daemon_inner_loop,
    _schedule_day_bounds,
)
from home_ops.cli.profile import profile_app
from home_ops.cli.scan_runner import _run_scan, _scam_fields_from_result
from home_ops.cli.sources import sources_app
from home_ops.cli.status import _display_status
from home_ops.config.loader import load_config
from home_ops.enricher import catastro, llm_analyzer
from home_ops.logging_setup import configure_logging
from home_ops.models.data_storage import daemon_lock, get_connection, get_db_path
from home_ops.scorer import RulesScorer

__all__ = [
    "RulesScorer",
    "TelegramAlerter",
    "_display_analytics",
    "_display_status",
    "_get_daily_alert_count",
    "_next_run_time",
    "_run_daemon_cycle",
    "_run_daemon_cycle_locked",
    "_run_daemon_inner_loop",
    "_run_scan",
    "_scam_fields_from_result",
    "_schedule_day_bounds",
    "app",
    "catastro",
    "console",
    "daemon_lock",
    "get_connection",
    "get_db_path",
    "llm_analyzer",
    "load_config",
]

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Home-Ops: Real estate agentic pipeline — scrape, score, alert.",
    no_args_is_help=True,
    callback=configure_logging,
)
console = Console()

app.add_typer(profile_app, name="profile")
app.add_typer(sources_app, name="sources")
app.add_typer(location_app, name="location")
app.add_typer(cadastre_app, name="cadastre")
app.add_typer(adapter_app, name="adapter")

# Shared Typer argument/option types
ConfigPathArg = Annotated[
    Path | None,
    typer.Argument(
        help="Path to user_profile.yml (default: auto-discover)",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]

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

ForceOpt = Annotated[
    bool,
    typer.Option(
        "--force",
        "-f",
        help="Force full scan bypassing early-stop pagination",
    ),
]


def _get_db_path() -> str:
    """Resolve the DuckDB path, honoring HOME_OPS_DB_PATH."""
    return str(get_db_path())


# ---------------------------------------------------------------------------
# Main Top-Level Commands
# ---------------------------------------------------------------------------


@app.command()
def scan(
    config_path: ConfigPathArg = None,
    force: ForceOpt = False,
) -> None:
    """Run the full pipeline: scrape → deduplicate → score → alert."""
    try:
        _run_scan(config_path, force)
    except Exception as exc:
        console.print(f"[bold red]Pipeline failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def status(config_path: ConfigPathArg = None) -> None:
    """Show pipeline state and recent listings."""
    try:
        load_config(config_path)
        _display_status()
    except Exception as exc:
        console.print(f"[bold red]Status failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def analytics() -> None:
    """Show price-distribution and run-time-series analytics (Big Data surface)."""
    try:
        _display_analytics()
    except Exception as exc:
        console.print(f"[bold red]Analytics failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def setup(
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to user_profile.yml (default: auto-discover / ./user_profile.yml)",
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Interactive setup wizard: configure portal, scoring, Telegram, LLM."""
    try:
        from home_ops.setup.wizard import run as run_wizard
    except ImportError as exc:
        console.print("[bold red]Setup needs the 'tui' extra:[/bold red] uv pip install '.[tui]'")
        raise typer.Exit(code=1) from exc

    if config_path is None:
        config_path = Path.cwd() / "user_profile.yml"
    env_path = Path.cwd() / ".env"
    run_wizard(config_path, env_path)


@app.command()
def tui(config_path: ConfigPathArg = None) -> None:
    """Launch the interactive control panel: scan, approve, reset, monitor."""
    try:
        from home_ops.tui import run as run_tui
    except ImportError as exc:
        console.print("[bold red]TUI needs the 'tui' extra:[/bold red] uv pip install '.[tui]'")
        raise typer.Exit(code=1) from exc
    run_tui(_get_db_path(), config_path)


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port")] = 8000,
) -> None:
    """Launch the public read-only web dashboard (no login, no writes)."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print("[bold red]Web needs the 'web' extra:[/bold red] uv pip install '.[web]'")
        raise typer.Exit(code=1) from exc
    uvicorn.run("home_ops.web:app", host=host, port=port)


@app.command(name="snapshots-reset")
def snapshots_reset() -> None:
    """Invalidate all cached scraper snapshots to force cold-start."""
    from home_ops.scraper.lifecycle import invalidate_snapshots

    try:
        invalidate_snapshots()
        console.print("[green]All snapshots invalidated. Next scan will cold-start.[/green]")
    except Exception as exc:
        console.print(f"[bold red]Failed to reset snapshots:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def approve(
    listing_id: Annotated[int, typer.Argument(help="The listing ID to approve")],
    config_path: ConfigOpt = None,
) -> None:
    """Approve a listing via the human-in-the-loop gate."""
    load_config(config_path)
    db_path = _get_db_path()

    try:
        with get_connection(db_path) as db:
            db.init_db()
            now = datetime.now(UTC)
            db.conn.execute(
                """INSERT INTO pending_approvals (listing_id, approved, approved_at)
                   VALUES (?, TRUE, ?)
                   ON CONFLICT (listing_id) DO UPDATE SET approved = TRUE, approved_at = ?;""",
                [listing_id, now, now],
            )
            console.print(
                f"[green]Listing {listing_id} approved. "
                f"Alerts will be sent on next scan.[/green]"
            )
    except Exception as exc:
        console.print(f"[bold red]Failed to approve listing {listing_id}:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def daemon(
    config_path: ConfigOpt = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print next scheduled run and exit without starting the loop",
        ),
    ] = False,
) -> None:
    """Run the automated pipeline daemon."""
    try:
        config = load_config(config_path)
        _run_daemon_inner_loop(config, config_path=config_path, dry_run=dry_run)
    except Exception as exc:
        console.print(f"[bold red]Daemon failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
