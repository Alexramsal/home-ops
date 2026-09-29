"""Status display helper module for Home-Ops CLI."""

from __future__ import annotations

from rich.table import Table


def _display_status() -> None:
    """Query the database and print a status summary."""
    import home_ops.cli.app as app_mod

    db_path = app_mod._get_db_path()

    with app_mod.get_connection(db_path) as db:
        db.init_db()

        # Total listings
        total_row = db.conn.execute("SELECT COUNT(*) FROM listings").fetchone()
        total = total_row[0] if total_row else 0

        # Last scan time
        last_scan_row = db.conn.execute(
            "SELECT MAX(fetched_at) FROM listings"
        ).fetchone()
        last_scan = last_scan_row[0] if last_scan_row else None

        # Pending approvals
        rows = db.conn.execute(
            "SELECT listing_id, created_at FROM pending_approvals "
            "WHERE approved = FALSE ORDER BY created_at ASC"
        ).fetchall()
        pending = [{"listing_id": int(r[0]), "created_at": str(r[1])} for r in rows]

    # Render a summary table
    table = Table(title="Home-Ops Pipeline Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total listings", str(total))
    table.add_row(
        "Last scan",
        str(last_scan) if last_scan else "[dim]never[/dim]",
    )
    table.add_row("Pending approvals", str(len(pending)))

    if pending:
        from rich import box

        detail = Table(box=box.SIMPLE)
        detail.add_column("Listing ID")
        detail.add_column("Created at")
        for p in pending:
            detail.add_row(str(p["listing_id"]), str(p["created_at"]))
        app_mod.console.print(table)
        app_mod.console.print("\n[bold]Pending approvals:[/bold]")
        app_mod.console.print(detail)
    else:
        app_mod.console.print(table)
