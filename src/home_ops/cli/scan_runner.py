"""Pipeline scan runner module for Home-Ops CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from home_ops.enricher import catastro, llm_analyzer
from home_ops.models.schema import Listing
from home_ops.scorer import RulesScorer
from home_ops.scorer.models import AcquisitionCostBreakdown, ScoreResult


def _scam_fields_from_result(
    score_result: ScoreResult,
) -> tuple[list[str], float, Decimal | None]:
    """Map a ScoreResult to the persisted (scam_flags, risk_score, cost) triple.

    Buyer protection is opt-in, so breakdowns may be None — neutral
    values are returned then.
    """
    scam_flags = score_result.scam_breakdown.red_flags if score_result.scam_breakdown else []
    scam_risk_score = (
        score_result.scam_breakdown.risk_score if score_result.scam_breakdown else 0.0
    )
    total_acquisition_cost = (
        score_result.cost_breakdown.total_acquisition_cost
        if score_result.cost_breakdown
        else None
    )
    return scam_flags, scam_risk_score, total_acquisition_cost


def _run_scan(config_path: Path | None = None, force: bool = False) -> None:
    """Orchestrate one pipeline scan cycle."""
    import home_ops.cli.app as app_mod

    config = app_mod.load_config(config_path)

    threshold = config.scoring.min_score_to_alert if config.scoring is not None else 70.0
    scorer = RulesScorer(config)

    db_path = app_mod._get_db_path()
    with app_mod.get_connection(db_path) as db:
        db.init_db()

        # 1. Auto-detect: cold start (empty DB) vs subsequent run
        #    Iterate all configured portal URLs (idealista + fotocasa + ...)
        from home_ops.scraper.lifecycle import cold_start, subsequent_run

        configured_urls = getattr(config, "portal_urls", None)
        portal_urls = (
            configured_urls
            if isinstance(configured_urls, (list, tuple)) and configured_urls
            else [config.portal_url]
        )
        listings: list[Listing] = []
        portal_errors: list[tuple[str, Exception]] = []
        successful_portals = 0
        scraper_cfg = getattr(config, "scraper", None)
        max_pages = (
            scraper_cfg.max_pages_per_scan
            if scraper_cfg is not None
            and isinstance(getattr(scraper_cfg, "max_pages_per_scan", None), int)
            else 5
        )
        for purl in portal_urls:
            app_mod.console.print(f"[bold]Scanning {purl}...[/bold]")
            row = db.conn.execute("SELECT COUNT(*) FROM listings").fetchone()
            has_data = row is not None and row[0] is not None and row[0] != 0
            try:
                if has_data:
                    new = subsequent_run(
                        purl, db, max_pages=max_pages, force=force
                    )
                else:
                    new = cold_start(purl, max_pages=max_pages)
            except Exception as exc:
                app_mod.console.print(f"[yellow]Scraper failed ({purl}): {exc}[/yellow]")
                portal_errors.append((purl, exc))
                continue
            successful_portals += 1
            listings.extend(new)

        if not successful_portals and portal_errors:
            raise portal_errors[0][1]

        # 2. Filter listings based on search criteria
        if listings:
            from home_ops.models.schema import SearchConfig
            from home_ops.scraper.filter import filter_listings

            search_cfg = getattr(config, "search", None)
            if not isinstance(search_cfg, SearchConfig):
                search_cfg = SearchConfig()

            listings, filter_stats = filter_listings(listings, search_cfg)
            if filter_stats.total_seen > 0:
                total_rejected = (
                    filter_stats.rejected_price
                    + filter_stats.rejected_m2
                    + filter_stats.rejected_missing_price
                    + filter_stats.rejected_missing_m2
                )
                if total_rejected > 0:
                    app_mod.console.print(
                        f"  [yellow]Filtered {total_rejected}/{filter_stats.total_seen} listings "
                        f"(price: {filter_stats.rejected_price}, m2: {filter_stats.rejected_m2}, "
                        f"missing_price: {filter_stats.rejected_missing_price}, missing_m2: {filter_stats.rejected_missing_m2})[/yellow]"
                    )

        # 3. Process new listings (if any)
        from home_ops.analytics import zone_from_portal_url

        zone = zone_from_portal_url(portal_urls[0])

        if listings:
            scored: list[
                tuple[Listing, float, list[str], AcquisitionCostBreakdown | None]
            ] = []

            for listing in listings:
                # Append-only price observation: recorded for EVERY seen
                # listing (new or duplicate) so price evolution over time
                # is captured even though listings itself is deduped.
                db.record_price_observation(
                    listing.content_hash,
                    zone,
                    listing.price,
                    listing.m2,
                )

                inserted_id = db.insert_listing(listing)

                if inserted_id is not None:
                    listing.id = inserted_id

                if inserted_id is None:
                    app_mod.console.print(
                        f"  [dim]Skipped (duplicate): {listing.address or listing.url}[/dim]"
                    )
                    continue

                catastro_cfg = getattr(config, "catastro", None)
                catastro_enabled = (
                    getattr(catastro_cfg, "enabled", False)
                    if catastro_cfg is not None
                    else False
                )
                search_cfg = getattr(config, "search", None)
                country_code = (
                    getattr(search_cfg, "country_code", "ES")
                    if search_cfg is not None
                    else "ES"
                )
                if catastro_enabled and country_code == "ES":
                    catastro.lookup(listing, config.portal_url, db)

                # Optional LLM description enrichment (best-effort, opt-in).
                # Persists raw call for traceability; red_flags_llm are passed as
                # extra_flags to RulesScorer to apply risk penalties.
                llm_flags: list[str] = []
                if config.llm.enabled:
                    llm_result = llm_analyzer.analyze_description(listing, config, db)
                    if llm_result is not None and llm_result.red_flags_llm:
                        llm_flags = llm_result.red_flags_llm

                # Score — use RulesScorer; multiply by 100 for 0-100 threshold compatibility
                score_result = scorer.score(
                    listing, db_conn=db.conn, zone=zone, extra_flags=llm_flags
                )
                score_value = score_result.total * 100.0

                # Persist scam-risk fields regardless of alert gating, so the
                # buyer-protection output survives even when no alert is sent
                listing.scam_flags, listing.scam_risk_score, listing.total_acquisition_cost = (
                    _scam_fields_from_result(score_result)
                )
                db.update_listing_scam_fields(
                    listing.content_hash,
                    listing.scam_flags,
                    listing.scam_risk_score,
                    listing.total_acquisition_cost,
                    score_value,
                )

                if score_result.flags:
                    app_mod.console.print(
                        f"  [yellow]Flags:[/yellow] {', '.join(score_result.flags)}"
                    )
                app_mod.console.print(
                    f"  [cyan]Scored:[/cyan] {listing.address or listing.url} "
                    f"→ [bold]{score_value:.1f}[/bold] (threshold {threshold})"
                )
                scored.append(
                    (listing, score_value, score_result.flags, score_result.cost_breakdown)
                )

            # Alert gating
            approval_required = config.hitl_approval_required
            alerter = app_mod.TelegramAlerter(
                bot_token=config.telegram_bot_token or None,
                chat_id=config.telegram_chat_id or None,
                score_threshold=threshold,
            )

            for listing, score, flags, cost_breakdown in scored:
                if score < threshold:
                    app_mod.console.print(
                        f"  [dim]Alert gated (score {score:.1f} < {threshold}): "
                        f"{listing.address or listing.url}[/dim]"
                    )
                    continue

                if listing.id is None:
                    app_mod.console.print("  [yellow]Listing has no id — skipping[/yellow]")
                    continue

                if approval_required:
                    db.conn.execute(
                        """INSERT INTO pending_approvals (listing_id, approved, score)
                           VALUES (?, FALSE, ?)
                           ON CONFLICT (listing_id) DO NOTHING;""",
                        [listing.id, score],
                    )
                    row = db.conn.execute(
                        "SELECT approved FROM pending_approvals WHERE listing_id = ?",
                        [listing.id],
                    ).fetchone()
                    if not row or not row[0]:
                        app_mod.console.print(
                            f"  [yellow]Awaiting HITL approval: listing {listing.id}[/yellow]"
                        )
                        continue

                # Check daily alert quota
                max_per_day = config.alert_schedule.max_alerts_per_day
                daily_count = app_mod._get_daily_alert_count(db.conn, config.alert_schedule.timezone)
                if daily_count >= max_per_day:
                    app_mod.console.print(
                        f"  [yellow]Daily alert limit reached ({max_per_day}), "
                        f"queued: {listing.address or listing.url}[/yellow]"
                    )
                    db.conn.execute(
                        "INSERT INTO daily_alert_log (listing_hash, status) VALUES (?, 'queued')",
                        [listing.content_hash],
                    )
                    continue

                success = alerter.send_alert(listing, score, flags, cost_breakdown)
                status = "sent" if success else "failed"
                db.conn.execute(
                    "INSERT INTO daily_alert_log (listing_hash, status) VALUES (?, ?)",
                    [listing.content_hash, status],
                )
                if success:
                    app_mod.console.print(
                        f"  [green]Alert sent:[/green] {listing.address or listing.url} "
                        f"(score {score:.1f})"
                    )
                else:
                    app_mod.console.print(
                        f"  [red]Alert failed:[/red] {listing.address or listing.url} "
                        f"(score {score:.1f})"
                    )

        # 3. Process approved-but-not-alerted listings from previous scans (always runs)
        alerter = app_mod.TelegramAlerter(
            bot_token=config.telegram_bot_token or None,
            chat_id=config.telegram_chat_id or None,
            score_threshold=threshold,
        )
        pending_rows = db.conn.execute(
            "SELECT listing_id, score FROM pending_approvals "
            "WHERE approved = TRUE AND (alerted = FALSE OR alerted IS NULL) "
            "ORDER BY listing_id ASC"
        ).fetchall()

        for listing_id, stored_score in pending_rows:
            row = db.conn.execute(
                "SELECT id, content_hash, url, address, m2, floor, price, "
                "garage_price, price_includes_garage, certificado_energetico_present, "
                "rooms, description, portal, external_id, fetched_at "
                "FROM listings WHERE id = ?", [listing_id]
            ).fetchone()
            if row is None:
                continue
            cols = (
                "id", "content_hash", "url", "address", "m2", "floor", "price",
                "garage_price", "price_includes_garage", "certificado_energetico_present",
                "rooms", "description", "portal", "external_id", "fetched_at"
            )
            data = dict(zip(cols, row, strict=True))
            listing = Listing(**data)

            # Re-score to get flags; use stored score when available
            score_result = scorer.score(listing, db_conn=db.conn, zone=zone)
            flags = score_result.flags
            score = stored_score if stored_score is not None else score_result.total * 100.0

            # Backfill scam fields for rows persisted before scoring existed
            listing.scam_flags, listing.scam_risk_score, listing.total_acquisition_cost = (
                _scam_fields_from_result(score_result)
            )
            db.update_listing_scam_fields(
                listing.content_hash,
                listing.scam_flags,
                listing.scam_risk_score,
                listing.total_acquisition_cost,
                score,
            )

            # Check daily alert quota
            max_per_day = config.alert_schedule.max_alerts_per_day
            daily_count = app_mod._get_daily_alert_count(db.conn, config.alert_schedule.timezone)
            if daily_count >= max_per_day:
                app_mod.console.print(
                    f"  [yellow]Daily alert limit reached ({max_per_day}), "
                    f"queued (approved): {listing.address or listing.url}[/yellow]"
                )
                db.conn.execute(
                    "INSERT INTO daily_alert_log (listing_hash, status) VALUES (?, 'queued')",
                    [listing.content_hash],
                )
                db.conn.execute(
                    "UPDATE pending_approvals SET alerted = TRUE WHERE listing_id = ?",
                    [listing_id],
                )
                continue

            success = alerter.send_alert(listing, score, flags, score_result.cost_breakdown)
            if success:
                db.conn.execute(
                    "UPDATE pending_approvals SET alerted = TRUE WHERE listing_id = ?",
                    [listing_id],
                )
                status = "sent"
                db.conn.execute(
                    "INSERT INTO daily_alert_log (listing_hash, status) VALUES (?, ?)",
                    [listing.content_hash, status],
                )
                app_mod.console.print(
                    f"  [green]Alert sent (approved):[/green] {listing.address or listing.url} "
                    f"(score {score:.1f})"
                )
            else:
                # No log row on failure (design D3): alerted stays FALSE so the
                # row is re-picked next cycle; a 'failed' row would double-send
                # via the step-4 requeue.
                app_mod.console.print(
                    f"  [red]Alert failed (approved):[/red] {listing.address or listing.url} "
                    f"(score {score:.1f})"
                )

        # 4. Re-attempt queued/failed alerts from previous days (always runs)
        today_start, _ = app_mod._schedule_day_bounds(config.alert_schedule.timezone)
        queued_rows = db.conn.execute(
            "SELECT dlh.id, dlh.listing_hash, dlh.sent_at FROM daily_alert_log dlh "
            "WHERE dlh.status IN ('queued', 'failed') "
            "AND (dlh.sent_at IS NULL OR dlh.sent_at < ?) "
            "AND NOT EXISTS (SELECT 1 FROM pending_approvals pa "
            "JOIN listings l ON l.id = pa.listing_id "
            "WHERE l.content_hash = dlh.listing_hash AND pa.alerted = FALSE) "
            "AND NOT EXISTS (SELECT 1 FROM daily_alert_log d2 "
            "WHERE d2.listing_hash = dlh.listing_hash AND d2.status = 'sent') "
            "ORDER BY dlh.id ASC",
            [today_start],
        ).fetchall()

        queued_max_per_day = config.alert_schedule.max_alerts_per_day
        for queued_id, listing_hash, _queued_at in queued_rows:
            daily_count = app_mod._get_daily_alert_count(db.conn, config.alert_schedule.timezone)
            if daily_count >= queued_max_per_day:
                app_mod.console.print(
                    f"  [yellow]Daily alert limit reached ({queued_max_per_day}), "
                    f"deferred (queued): hash {listing_hash}[/yellow]"
                )
                break

            row = db.conn.execute(
                "SELECT id, url, address, content_hash, m2, floor, price, "
                "garage_price, price_includes_garage, certificado_energetico_present, "
                "rooms, description, portal, external_id, fetched_at "
                "FROM listings WHERE content_hash = ? LIMIT 1",
                [listing_hash],
            ).fetchone()
            if row is None:
                db.conn.execute("DELETE FROM daily_alert_log WHERE id = ?", [queued_id])
                continue

            cols = (
                "id", "url", "address", "content_hash", "m2", "floor", "price",
                "garage_price", "price_includes_garage", "certificado_energetico_present",
                "rooms", "description", "portal", "external_id", "fetched_at"
            )
            data = dict(zip(cols, row, strict=True))
            listing = Listing(**data)

            score_result = scorer.score(listing, db_conn=db.conn, zone=zone)
            score_value = score_result.total * 100.0

            # Persist scam fields before the threshold gate so data is kept
            listing.scam_flags, listing.scam_risk_score, listing.total_acquisition_cost = (
                _scam_fields_from_result(score_result)
            )
            db.update_listing_scam_fields(
                listing.content_hash,
                listing.scam_flags,
                listing.scam_risk_score,
                listing.total_acquisition_cost,
                score_value,
            )

            if score_value < threshold:
                app_mod.console.print(
                    f"  [dim]Alert gated (queued re-attempt, score {score_value:.1f} "
                    f"< {threshold}): {listing.address or listing.url}[/dim]"
                )
                continue

            success = alerter.send_alert(
                listing, score_value, score_result.flags, score_result.cost_breakdown
            )
            status = 'sent' if success else 'failed'
            db.conn.execute(
                "UPDATE daily_alert_log SET status = ?, sent_at = ? WHERE id = ?",
                # UTC-naive is the canonical storage format (DEFAULT writes
                # (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')); passing an aware
                # datetime lets DuckDB shift it to local naive and the row
                # then falls outside today's UTC bounds, inflating the quota.
                [status, datetime.now(UTC).replace(tzinfo=None), queued_id],
            )
            if success:
                app_mod.console.print(
                    f"  [green]Alert sent (queued re-attempt):[/green] "
                    f"{listing.address or listing.url} (score {score_value:.1f})"
                )
            else:
                app_mod.console.print(
                    f"  [red]Alert failed (queued re-attempt):[/red] "
                    f"{listing.address or listing.url} (score {score_value:.1f})"
                )

    app_mod.console.print("[bold green]Pipeline scan complete.[/bold green]")
