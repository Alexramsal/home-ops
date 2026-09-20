"""Automated pipeline daemon module for Home-Ops CLI."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from home_ops.models.schema import ScheduleConfig

logger = logging.getLogger(__name__)


def _next_run_time(
    schedule: ScheduleConfig,
    last_run: datetime | None = None,
    now: datetime | None = None,
) -> datetime:
    """Compute the next scheduled run time as a pure function.

    Args:
        schedule: The schedule configuration (mode, daily_time, interval_hours, timezone).
        last_run: The last recorded pipeline run time, or None if never run.
        now: The current time (injectable for testing). Defaults to UTC now.

    Returns:
        The next datetime when the pipeline should run (timezone-aware in UTC).
    """
    from home_ops.models.schema import _parse_timezone

    if now is None:
        now = datetime.now(UTC)

    if schedule.mode == "interval":
        if last_run is None:
            return now
        return last_run + timedelta(hours=schedule.interval_hours)

    # Daily mode — use the configured timezone
    tz = _parse_timezone(getattr(schedule, "timezone", "Europe/Madrid"))
    hour_str, min_str = schedule.daily_time.split(":", 1)
    target_hour = int(hour_str)
    target_min = int(min_str)

    if last_run is not None:
        # Compute next daily occurrence AFTER last_run (enables catch-up detection)
        last_local = last_run.astimezone(tz)
        candidate = last_local.replace(
            hour=target_hour, minute=target_min, second=0, microsecond=0
        )
        if candidate <= last_local:
            candidate += timedelta(days=1)
    else:
        # No prior run — return now so daemon runs immediately on first start
        return now

    return candidate.astimezone(UTC)


def _schedule_day_bounds(
    timezone: str, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return UTC-naive DB bounds for the configured local calendar day."""
    from home_ops.models.schema import _parse_timezone

    tz = _parse_timezone(timezone)
    local_now = (now or datetime.now(UTC)).astimezone(tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        (local_start + timedelta(days=1)).astimezone(UTC).replace(tzinfo=None),
    )


def _get_daily_alert_count(
    conn: Any, timezone: str = "UTC", now: datetime | None = None
) -> int:
    """Count sent alerts in today's configured-schedule calendar day."""
    day_start, day_end = _schedule_day_bounds(timezone, now)
    row = conn.execute(
        "SELECT COUNT(*) FROM daily_alert_log "
        "WHERE status = 'sent' AND sent_at >= ? AND sent_at < ?",
        [day_start, day_end],
    ).fetchone()
    return row[0] if row else 0


def _run_daemon_cycle(
    config: Any,
    config_path: Path | None = None,
    run_fn: Any = None,
    now: datetime | None = None,
) -> bool:
    """Run one cycle when no other process holds the daemon lock."""
    import home_ops.cli.app as app_mod

    with app_mod.daemon_lock(app_mod._get_db_path()) as acquired:
        if not acquired:
            logger.warning("Daemon cycle: another process holds the lock, skipping")
            return False
        return _run_daemon_cycle_locked(config, config_path, run_fn, now)


def _run_daemon_cycle_locked(
    config: Any,
    config_path: Path | None = None,
    run_fn: Any = None,
    now: datetime | None = None,
) -> bool:
    """Execute one daemon cycle: check schedule and run pipeline if due.

    Args:
        config: The application Config object.
        run_fn: Injectable run function (defaults to _run_scan).
        now: The current time (injectable for testing). Defaults to UTC now.

    Returns:
        True if the pipeline was executed, False if skipped.
    """
    import home_ops.cli.app as app_mod

    if run_fn is None:
        run_fn = app_mod._run_scan
    if now is None:
        now = datetime.now(UTC)

    schedule = config.alert_schedule
    db_path = app_mod._get_db_path()

    with app_mod.get_connection(db_path) as db:
        db.init_db()

        # Cleanup stale 'running' rows from crashed/interrupted runs
        # Use started_at as finished_at so the schedule computer sees the
        # original timestamp, not the current time — otherwise it would
        # think a run just completed and skip the current cycle.
        db.conn.execute(
            "UPDATE scraping_runs SET status = 'failed', finished_at = started_at "
            "WHERE status = 'running'",
        )

        # Check if a run is already in progress (overlapping guard)
        running = db.conn.execute(
            "SELECT COUNT(*) FROM scraping_runs WHERE status = 'running'"
        ).fetchone()
        if running and running[0] > 0:
            logger.warning("Daemon cycle: previous run still in progress, skipping")
            return False

        # Get last completed run for schedule computation
        last_row = db.conn.execute(
            "SELECT finished_at FROM scraping_runs "
            "WHERE status IN ('success', 'failed') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_run: datetime | None = last_row[0] if last_row else None

        # Compute next run time
        next_time = _next_run_time(schedule, last_run, now)

        if next_time > now:
            logger.debug("Daemon cycle: next run at %s, skipping", next_time)
            return False

        # Mark run as started
        row = db.conn.execute(
            "INSERT INTO scraping_runs (started_at, status) VALUES (?, 'running') "
            "RETURNING id",
            [now],
        ).fetchone()
        assert row is not None  # RETURNING always returns a row
        run_id = row[0]

    # Execute the pipeline outside the DB context manager
    status = "success"
    try:
        run_fn(config_path)  # run_fn accepts config_path; None = auto-discover
    except BaseException as exc:
        logger.error("Daemon cycle: pipeline failed: %s", exc)
        status = "failed"
        if not isinstance(exc, Exception):
            raise
    finally:
        # Mark run as finished — always update status even on Ctrl+C
        with app_mod.get_connection(db_path) as db:
            db.init_db()
            db.conn.execute(
                "UPDATE scraping_runs SET finished_at = ?, status = ? "
                "WHERE id = ?",
                [datetime.now(UTC), status, run_id],
            )

    return True


def _run_daemon_inner_loop(
    config: Any, config_path: Path | None = None, dry_run: bool = False
) -> None:
    """Run the daemon loop: check schedule every 60s, execute when due.

    Args:
        config: The application Config object.
        dry_run: If True, only print the next scheduled time and exit.
    """
    import home_ops.cli.app as app_mod

    schedule = config.alert_schedule
    now = datetime.now(UTC)

    # Compute next run for dry-run or initial display
    db_path = app_mod._get_db_path()
    with app_mod.get_connection(db_path) as db:
        db.init_db()
        last_row = db.conn.execute(
            "SELECT finished_at FROM scraping_runs "
            "WHERE status IN ('success', 'failed') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_run: datetime | None = last_row[0] if last_row else None

    next_time = _next_run_time(schedule, last_run, now)
    app_mod.console.print(f"[cyan]Schedule mode:[/cyan] {schedule.mode}")
    app_mod.console.print(f"[cyan]Next scheduled run:[/cyan] {next_time}")

    if dry_run:
        app_mod.console.print("[green]Dry-run complete. No loop started.[/green]")
        return

    app_mod.console.print("[green]Daemon loop started. Press Ctrl+C to stop.[/green]")

    try:
        while True:
            cycle_now = datetime.now(UTC)
            _run_daemon_cycle(config, config_path=config_path, now=cycle_now)
            time.sleep(60)
    except KeyboardInterrupt:
        app_mod.console.print("[yellow]Daemon loop stopped by user.[/yellow]")
