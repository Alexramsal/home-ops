"""Behavior tests for the Home-Ops Textual control panel (Phase B)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from rich.text import Text

pytest.importorskip("textual")

from home_ops.models.data_storage import get_connection  # noqa: E402
from home_ops.tui import HomeOpsTUI, _is_safe_listing_url  # noqa: E402

MANDATORY_IDS = (
    "#top-status",
    "#summary-kpis",
    "#portal-counts",
    "#config-health",
    "#pending",
    "#pending-detail",
    "#ranking",
    "#ranking-filter",
    "#ranking-detail",
    "#trend-spark",
    "#evolution",
    "#runs",
    "#log",
)


def seed_portal_listings(db_path: str) -> tuple[str, str]:
    tecnocasa_url = "https://www.tecnocasa.es/venta/piso/1"
    habitaclia_url = "https://www.habitaclia.com/comprar/vivienda/2"
    with get_connection(db_path) as db:
        db.init_db()
        for content_hash, url, address, score, portal in (
            ("tc", tecnocasa_url, "Piso Tecnocasa", 90.0, "tecnocasa"),
            ("ha", habitaclia_url, "Piso Habitaclia", 80.0, "habitaclia"),
        ):
            listing_id = db.conn.execute(
                """INSERT INTO listings
                   (content_hash, url, address, m2, price, rooms, score, portal)
                   VALUES (?, ?, ?, 80, 150000, 3, ?, ?) RETURNING id""",
                [content_hash, url, address, score, portal],
            ).fetchone()[0]
            db.conn.execute(
                """INSERT INTO pending_approvals (listing_id, approved, score)
                   VALUES (?, FALSE, ?)""",
                [listing_id, score],
            )
    return tecnocasa_url, habitaclia_url


def seed_dashboard(db_path: str) -> list[int]:
    """Seed enough persisted data to exercise every dashboard panel."""
    with get_connection(db_path) as db:
        db.init_db()
        listings = [
            ("h1", "https://example.test/one", "Calle Uno", 100.0, 100000.0, 90.0, "idealista"),
            ("h2", "javascript:alert(1)", "Calle Dos", 80.0, 96000.0, 80.0, "fotocasa"),
            ("h3", "file:///tmp/listing", "Calle Tres", 60.0, 90000.0, 65.0, "idealista"),
        ]
        ids: list[int] = []
        for content_hash, url, address, m2, price, score, portal in listings:
            row = db.conn.execute(
                """INSERT INTO listings
                   (content_hash, url, address, m2, price, rooms, score, portal)
                   VALUES (?, ?, ?, ?, ?, 3, ?, ?) RETURNING id""",
                [content_hash, url, address, m2, price, score, portal],
            ).fetchone()
            ids.append(int(row[0]))
        db.conn.execute(
            "INSERT INTO pending_approvals (listing_id, approved, score) VALUES (?, FALSE, 90)",
            [ids[0]],
        )
        db.conn.execute(
            "INSERT INTO pending_approvals (listing_id, approved, score) VALUES (?, FALSE, 80)",
            [ids[1]],
        )
        now = datetime.now(UTC)
        for observed_at, price in ((now - timedelta(days=14), 100000), (now, 120000)):
            db.conn.execute(
                """INSERT INTO price_history (content_hash, price, m2, observed_at)
                   VALUES ('history', ?, 100, ?)""",
                [price, observed_at],
            )
        db.conn.execute(
            """INSERT INTO scraping_runs
               (started_at, finished_at, listings_found, listings_new, alerts_sent, status)
               VALUES (?, ?, 3, 2, 1, 'ok')""",
            [now, now],
        )
    return ids


@pytest.mark.asyncio
async def test_tui_empty_mount_and_tabs(tmp_path) -> None:
    """Empty DB mounts, exposes the five tabs and every mandatory widget id."""
    app = HomeOpsTUI(str(tmp_path / "empty.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert len(app.query("TabPane")) == 5
        for widget_id in MANDATORY_IDS:
            assert app.query_one(widget_id)
        assert "Propiedades: 0" in str(app.query_one("#top-status").render())
        assert "TOTAL\n0" in str(app.query_one("#kpi-total").render())
        assert "Datos insuficientes" in str(app.query_one("#trend-message").render())


@pytest.mark.asyncio
async def test_tui_seeded_data(tmp_path) -> None:
    """Seeded DB populates KPIs, pending, ranking order, trend and runs."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        kpis = str(app.query_one("#kpi-total").render())
        assert "TOTAL\n3" in kpis
        assert "OPORTUNIDADES\n2" in str(app.query_one("#kpi-opportunities").render())
        assert "MEDIANA €/m²\n1200" in str(app.query_one("#kpi-median").render())
        assert "PENDIENTES\n2" in str(app.query_one("#kpi-pending").render())
        assert "Sin ejecuciones" not in str(app.query_one("#recent-activity").render())
        assert app.query_one("#pending").row_count == 2
        assert app.query_one("#ranking").row_count == 3
        assert [row["score"] for row in app._ranking_rows] == [90.0, 80.0, 65.0]
        assert app.query_one("#evolution").row_count == 2
        assert app.query_one("#runs").row_count == 1
        assert list(app.query_one("#trend-spark").data) == [1000.0, 1200.0]


@pytest.mark.asyncio
async def test_tui_tied_rows_use_id_as_deterministic_tiebreaker(tmp_path) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    ids = seed_dashboard(db_path)
    with get_connection(db_path) as db:
        tied_at = datetime(2025, 1, 1, tzinfo=UTC)
        db.conn.execute("UPDATE listings SET score = 90 WHERE id = ?", [ids[1]])
        db.conn.execute(
            "UPDATE pending_approvals SET created_at = ? WHERE listing_id IN (?, ?)",
            [tied_at, ids[0], ids[1]],
        )
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._pending_ids == sorted(ids[:2])
        assert [row["id"] for row in app._ranking_rows[:2]] == sorted(ids[:2])


@pytest.mark.asyncio
async def test_tui_approve_action(tmp_path) -> None:
    """Pressing 'a' approves the selected pending listing."""
    db_path = str(tmp_path / "home_ops.duckdb")
    ids = seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert app.query_one("#pending").row_count == 1
    with get_connection(db_path) as db:
        approved = db.conn.execute(
            "SELECT approved FROM pending_approvals WHERE listing_id = ?", [ids[0]]
        ).fetchone()[0]
    assert approved is True


@pytest.mark.asyncio
async def test_tui_approve_negative_cursor_does_nothing(tmp_path, monkeypatch) -> None:
    """A negative pending cursor must not approve anything."""
    db_path = str(tmp_path / "home_ops.duckdb")
    ids = seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    warnings: list[str] = []
    monkeypatch.setattr(app, "notify", lambda message, **kw: warnings.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#pending")
        monkeypatch.setattr(type(table), "cursor_row", property(lambda self: -1))
        app.action_approve()
    with get_connection(db_path) as db:
        approved = db.conn.execute(
            "SELECT approved FROM pending_approvals WHERE listing_id = ?", [ids[0]]
        ).fetchone()[0]
    assert approved is False
    assert warnings == ["No hay listing seleccionado"]


@pytest.mark.asyncio
async def test_tui_approve_cursor_past_cache_does_nothing(tmp_path, monkeypatch) -> None:
    """A pending cursor past the cache must not approve anything."""
    db_path = str(tmp_path / "home_ops.duckdb")
    ids = seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    warnings: list[str] = []
    monkeypatch.setattr(app, "notify", lambda message, **kw: warnings.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#pending")
        monkeypatch.setattr(
            type(table), "cursor_row", property(lambda self: len(app._pending_ids))
        )
        app.action_approve()
    with get_connection(db_path) as db:
        approved = db.conn.execute(
            "SELECT approved FROM pending_approvals WHERE listing_id = ?", [ids[0]]
        ).fetchone()[0]
    assert approved is False
    assert warnings == ["No hay listing seleccionado"]


@pytest.mark.asyncio
async def test_tui_open_negative_cursor_does_nothing(tmp_path, monkeypatch) -> None:
    """A negative ranking cursor must not open any URL."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    opened: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr("home_ops.tui.webbrowser.open", opened.append)
    monkeypatch.setattr(app, "notify", lambda message, **kw: warnings.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_tab(3)
        table = app.query_one("#ranking")
        monkeypatch.setattr(type(table), "cursor_row", property(lambda self: -1))
        app.action_open_listing()
    assert opened == []
    assert warnings == ["No hay listing seleccionado"]


@pytest.mark.asyncio
async def test_tui_open_cursor_past_cache_does_nothing(tmp_path, monkeypatch) -> None:
    """A ranking cursor past the cache must not open any URL."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    opened: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr("home_ops.tui.webbrowser.open", opened.append)
    monkeypatch.setattr(app, "notify", lambda message, **kw: warnings.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_tab(3)
        table = app.query_one("#ranking")
        monkeypatch.setattr(
            type(table), "cursor_row", property(lambda self: len(app._ranking_rows))
        )
        app.action_open_listing()
    assert opened == []
    assert warnings == ["No hay listing seleccionado"]


@pytest.mark.asyncio
async def test_tui_filter_ranking_cycle(tmp_path) -> None:
    """'f' cycles Todos -> >=70 -> >=85 and re-filters the ranking table."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Todos" in str(app.query_one("#ranking-filter").render())
        assert app.query_one("#ranking").row_count == 3
        await pilot.press("f")
        await pilot.pause()
        assert ">=70" in str(app.query_one("#ranking-filter").render())
        assert app.query_one("#ranking").row_count == 2
        await pilot.press("f")
        await pilot.pause()
        assert ">=85" in str(app.query_one("#ranking-filter").render())
        assert app.query_one("#ranking").row_count == 1
        await pilot.press("f")
        await pilot.pause()
        assert "Todos" in str(app.query_one("#ranking-filter").render())
        assert app.query_one("#ranking").row_count == 3


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///tmp/listing",
        "https:///missing-host",
        "https://user@example.test/listing",
        "https://user:pass@example.test/listing",
        "https://example.test/listing\nheader: injected",
        "https://exa mple.test",
        "https://example.test/listing\tmore",
        "https://example.test/listing\nmore",
        "https://example.test/listing\x7f",
    ],
)
def test_tui_rejects_unsafe_listing_urls(url: str) -> None:
    assert not _is_safe_listing_url(url)


@pytest.mark.parametrize("url", ["http://example.test/x", "https://example.test/x"])
def test_tui_accepts_safe_listing_urls(url: str) -> None:
    assert _is_safe_listing_url(url)


@pytest.mark.asyncio
async def test_tui_portals_render_and_open_exact_urls_in_listing_tabs(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "portals.duckdb")
    urls = seed_portal_listings(db_path)
    app = HomeOpsTUI(db_path)
    opened: list[str] = []
    monkeypatch.setattr("home_ops.tui.webbrowser.open", opened.append)

    async with app.run_test() as pilot:
        await pilot.pause()
        pending_table = app.query_one("#pending")
        ranking_table = app.query_one("#ranking")
        assert [pending_table.get_row_at(row)[5] for row in range(2)] == [
            "tecnocasa",
            "habitaclia",
        ]
        assert [ranking_table.get_row_at(row)[5] for row in range(2)] == [
            "tecnocasa",
            "habitaclia",
        ]
        assert "Pulsa o para abrir" in str(app.query_one("#pending-detail").render())
        assert "Pulsa o para abrir" in str(app.query_one("#ranking-detail").render())

        for tab_number, table_id in ((2, "#pending"), (3, "#ranking")):
            app.action_tab(tab_number)
            await pilot.pause()
            table = app.query_one(table_id)
            for row in range(2):
                table.move_cursor(row=row)
                app.action_open_listing()

    assert opened == [*urls, *urls]


@pytest.mark.asyncio
async def test_tui_open_listing_security(tmp_path, monkeypatch) -> None:
    """'o' opens http/https only; javascript:/file: are rejected."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    opened: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr("home_ops.tui.webbrowser.open", opened.append)
    monkeypatch.setattr(app, "notify", lambda message, **kw: warnings.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_tab(3)
        await pilot.pause()
        table = app.query_one("#ranking")
        app.action_open_listing()
        table.move_cursor(row=1)
        await pilot.pause()
        app.action_open_listing()
        table.move_cursor(row=2)
        await pilot.pause()
        app.action_open_listing()
    assert opened == ["https://example.test/one"]
    assert sum("insegura" in message for message in warnings) == 2


@pytest.mark.asyncio
async def test_tui_open_listing_ignores_non_listing_tabs(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    opened: list[str] = []
    monkeypatch.setattr("home_ops.tui.webbrowser.open", opened.append)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_tab(3)
        await pilot.pause()
        app.query_one("#ranking").move_cursor(row=1)
        app.action_tab(1)
        await pilot.pause()
        app.action_open_listing()
    assert opened == []


@pytest.mark.asyncio
async def test_tui_cursor_detail_update_uses_cache(tmp_path) -> None:
    """Row highlight updates the detail panes from cache, with no DB access."""
    db_path = str(tmp_path / "home_ops.duckdb")
    seed_dashboard(db_path)
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()

        def explode(*_args, **_kwargs):
            raise AssertionError("cursor event must not query the database")

        monkeypatch_db = pytest.MonkeyPatch()
        monkeypatch_db.setattr("home_ops.tui.get_connection", explode)
        try:
            pending_table = app.query_one("#pending")
            ranking_table = app.query_one("#ranking")
            app.on_data_table_row_highlighted(
                SimpleNamespace(data_table=pending_table, cursor_row=1)
            )
            app.on_data_table_row_highlighted(
                SimpleNamespace(data_table=ranking_table, cursor_row=1)
            )
            await pilot.pause()
        finally:
            monkeypatch_db.undo()
        assert "Calle Dos" in str(app.query_one("#pending-detail").render())
        assert "Calle Dos" in str(app.query_one("#ranking-detail").render())


@pytest.mark.asyncio
async def test_tui_80x24_terminal(tmp_path) -> None:
    """Compact 80x24 terminal mounts and refreshes without crashing."""
    app = HomeOpsTUI(str(tmp_path / "small.duckdb"))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert "Propiedades: 0" in str(app.query_one("#top-status").render())
        assert app.query_one("#ranking").row_count == 0


@pytest.mark.asyncio
async def test_tui_log_lives_in_activity_tab(tmp_path) -> None:
    """#log must be inside the Actividad pane, not Resumen."""
    app = HomeOpsTUI(str(tmp_path / "log.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log")
        ancestors = [w.id for w in log.ancestors]
        assert "activity-tab" in ancestors
        assert "summary-tab" not in ancestors


@pytest.mark.asyncio
async def test_tui_scan_finished_strips_ansi(tmp_path, monkeypatch) -> None:
    """_scan_finished must convert ANSI via Text.from_ansi (no raw escapes)."""
    app = HomeOpsTUI(str(tmp_path / "ansi.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        written: list[str] = []
        monkeypatch.setattr(app, "action_refresh", lambda: None)
        monkeypatch.setattr(
            app.query_one("#log"),
            "write",
            lambda content: written.append(content.plain),
        )
        app._scan_finished("\x1b[1;32mPipeline scan complete.\x1b[0m\n")
        await pilot.pause()
        assert written and "Pipeline scan complete" in written[0]


@pytest.mark.asyncio
async def test_tui_empty_recent_activity(tmp_path) -> None:
    """Empty DB shows the recent-activity placeholder."""
    app = HomeOpsTUI(str(tmp_path / "empty.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "Sin ejecuciones todavía" in str(
            app.query_one("#recent-activity").render()
        )


@pytest.mark.asyncio
async def test_tui_title_and_subtitle(tmp_path) -> None:
    """Header exposes the Home-Ops brand and the radar subtitle."""
    app = HomeOpsTUI(str(tmp_path / "brand.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.TITLE == "Home-Ops"
        assert app.SUB_TITLE == "Radar inmobiliario"


@pytest.mark.asyncio
async def test_tui_help_binding_notifies(tmp_path, monkeypatch) -> None:
    """'?' action surfaces the shortcut cheat-sheet via notify."""
    app = HomeOpsTUI(str(tmp_path / "help.duckdb"))
    notices: list[str] = []
    monkeypatch.setattr(app, "notify", lambda message, **kw: notices.append(str(message)))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_help()
        await pilot.pause()
    assert notices and "escanear" in notices[0]


@pytest.mark.asyncio
async def test_tui_footer_shows_only_primary_bindings(tmp_path) -> None:
    """Secondary bindings (a/x/f/o/1-5) stay hidden; primary s/r/c/?/q shown."""
    app = HomeOpsTUI(str(tmp_path / "footer.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        shown = [b.key for b in app._bindings.shown_keys]
        assert shown == ["s", "r", "c", "question_mark", "q"]


@pytest.mark.asyncio
async def test_tui_config_opens_setup_wizard(tmp_path) -> None:
    """Binding 'c' pushes the setup wizard modal without leaving the TUI."""
    from home_ops.setup.wizard import SetupWizard

    app = HomeOpsTUI(":memory:", config_path=tmp_path / "user_profile.yml")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SetupWizard)

        # Escape dismisses back to the main TUI.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SetupWizard)


@pytest.mark.asyncio
async def test_tui_config_save_refreshes_and_returns(tmp_path) -> None:
    """Saving in the Config tab writes config, returns to the TUI, refreshes."""
    from home_ops.setup.wizard import SetupWizard

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = HomeOpsTUI(":memory:", config_path=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, SetupWizard)

        wizard.query_one("#bot_token").value = "new_tok"
        await pilot.pause()
        await pilot.press("ctrl+s")  # dismiss(True) -> _config_closed -> refresh
        await pilot.pause()

        assert not isinstance(app.screen, SetupWizard)
        assert "TELEGRAM_BOT_TOKEN=new_tok" in env.read_text()
        assert "Propiedades: 0" in str(app.query_one("#top-status").render())


def test_tui_ranking_detail_localizes_and_escapes_markup() -> None:
    """Detail text uses Spanish units and neutralizes external Rich markup."""
    detail = HomeOpsTUI._ranking_detail(
        {"address": "[red]Calle[2]", "rooms": 3, "m2": 90.0, "url": "https://x.test/[a]"}
    )
    rendered = Text.from_markup(detail)
    assert rendered.plain == (
        "[red]Calle[2] | 3 hab. | 90.0 m² | https://x.test/[a] · Pulsa o para abrir"
    )
    assert not rendered.spans


@pytest.mark.asyncio
async def test_tui_panels_escape_external_markup(tmp_path) -> None:
    """External brackets render literally in the detail and portal panels."""
    db_path = str(tmp_path / "markup.duckdb")
    with get_connection(db_path) as db:
        db.init_db()
        db.conn.execute(
            """INSERT INTO listings
               (content_hash, url, address, m2, price, rooms, score, portal)
               VALUES ('m1', 'https://e.test/[a]', '[b]Calle[/b]', 50.0, 50000.0, 2,
                       75.0, '[i]portal[/i]')"""
        )
    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "[b]Calle[/b]" in str(app.query_one("#ranking-detail").render())
        assert "[i]portal[/i]" in str(app.query_one("#portal-counts").render())


@pytest.mark.asyncio
async def test_tui_scan_task_clears_scanning_when_cli_import_fails(
    tmp_path, monkeypatch
) -> None:
    """A failed cli_app import must never leave _scanning stuck at True."""
    app = HomeOpsTUI(str(tmp_path / "scan.duckdb"))
    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "call_from_thread", lambda fn, value: fn(value))
        monkeypatch.setitem(sys.modules, "home_ops.cli", None)
        app._scanning = True
        app._scan_task()
        await pilot.pause()
        assert app._scanning is False
