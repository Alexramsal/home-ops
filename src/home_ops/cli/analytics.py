"""Analytics command display module for Home-Ops CLI."""

from __future__ import annotations

from rich.table import Table


def _display_analytics() -> None:
    """Show price-distribution and run-time-series analytics."""
    import home_ops.cli.app as app_mod
    from home_ops import analytics as analytics_mod

    db_path = app_mod._get_db_path()
    with app_mod.get_connection(db_path) as db:
        db.init_db()
        prices = analytics_mod.price_stats(db)
        per_m2 = analytics_mod.price_per_m2_stats(db)
        portals = analytics_mod.portal_counts(db)
        runs = analytics_mod.runs_timeseries(db)
        hist = analytics_mod.price_history_stats(db)
        evolution = analytics_mod.price_evolution_by_week(db)

    table = Table(title="Price distribution (EUR)")
    table.add_column("Stat")
    table.add_column("Value", justify="right")
    for key in ("count", "mean", "min", "max", "p25", "p50", "p75"):
        value = prices[key]
        table.add_row(key, f"{value:.0f}" if isinstance(value, (int, float)) else str(value))

    m2_table = Table(title="Price per m² (EUR/m²)")
    m2_table.add_column("Stat")
    m2_table.add_column("Value", justify="right")
    for key in ("count", "mean", "min", "max", "p25", "p50", "p75"):
        value = per_m2[key]
        m2_table.add_row(key, f"{value:.0f}" if isinstance(value, (int, float)) else str(value))

    portal_table = Table(title="Listings by portal")
    portal_table.add_column("Portal")
    portal_table.add_column("Count", justify="right")
    for portal, count in portals:
        portal_table.add_row(portal, str(count))

    app_mod.console.print(table)
    app_mod.console.print(m2_table)
    app_mod.console.print(portal_table)

    hist_summary = (
        f"Price history: {hist['observations']} observations, "
        f"{hist['unique_listings']} unique listings"
    )
    app_mod.console.print(f"[dim]{hist_summary}[/dim]")
    if evolution:
        evo_table = Table(title="Price-per-m² evolution (weekly)")
        evo_table.add_column("Week")
        evo_table.add_column("N", justify="right")
        evo_table.add_column("Mean €/m²", justify="right")
        evo_table.add_column("P50 €/m²", justify="right")
        for r in evolution[-10:]:
            mean = f"{r['mean_eur_m2']:.0f}" if r["mean_eur_m2"] is not None else "—"
            p50 = f"{r['p50_eur_m2']:.0f}" if r["p50_eur_m2"] is not None else "—"
            evo_table.add_row(r["week"][:10], str(r["n"]), mean, p50)
        app_mod.console.print(evo_table)

    if runs:
        run_table = Table(title="Run time-series (per day)")
        run_table.add_column("Day")
        run_table.add_column("Found", justify="right")
        run_table.add_column("New", justify="right")
        run_table.add_column("Alerts", justify="right")
        for r in runs[-10:]:
            run_table.add_row(
                r["day"],
                str(r["listings_found"]),
                str(r["listings_new"]),
                str(r["alerts_sent"]),
            )
        app_mod.console.print(run_table)
    else:
        app_mod.console.print("[dim]No completed scraping runs recorded yet.[/dim]")
