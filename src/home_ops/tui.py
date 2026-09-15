"""Textual control panel for the Home-Ops pipeline.

One screen, five tabs:

- ``s``  scan    — run one pipeline cycle in a worker thread; its output streams
                   into the log pane (Actividad tab).
- ``r``  refresh — re-read DuckDB once and repaint every panel.
- ``a``  approve — approve the selected pending listing (HITL gate).
- ``c``  config  — open the setup wizard modal.
- ``x``  reset   — invalidate cached scraper snapshots (next scan cold-starts).
- ``f``  filter  — cycle the ranking filter Todos / >=70 / >=85.
- ``o``  open    — open the selected row's URL (http/https only, never a shell).
- ``1``..``5``   — jump straight to a tab.
- ``q``  quit
"""

from __future__ import annotations

import contextlib
import io
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    RichLog,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)

from home_ops import analytics as analytics_mod
from home_ops.models.data_storage import get_connection

_TABLE_COLUMNS = ("ID", "Dirección", "Precio", "€/m²", "Score", "Portal")
_OPEN_HINT = "Atajo: o — abrir anuncio en el navegador"
_TAB_IDS = ("summary-tab", "pending-tab", "ranking-tab", "trends-tab", "activity-tab")
_URL_SCHEMES = {"http", "https"}


def _is_safe_listing_url(url: str) -> bool:
    """Accept browser URLs with a network host and no credentials or controls."""
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in _URL_SCHEMES
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


class HomeOpsTUI(App[None]):
    """Pipeline control panel: scan/approve/reset + analytics dashboard."""

    TITLE = "Home-Ops"
    SUB_TITLE = "Radar inmobiliario"
    BINDINGS = [
        Binding("s", "scan", "Escanear"),
        Binding("r", "refresh", "Actualizar"),
        Binding("c", "config", "Configurar"),
        Binding("?", "help", "Ayuda"),
        Binding("q", "quit", "Salir"),
        Binding("a", "approve", "Aprobar", show=False),
        Binding("x", "reset_snapshots", "Reiniciar", show=False),
        Binding("f", "filter_ranking", "Filtrar", show=False),
        Binding("o", "open_listing", "Abrir", show=False),
        *[
            Binding(str(n), f"tab({n})", title, show=False)
            for n, title in enumerate(
                ("Resumen", "Pendientes", "Ranking", "Tendencias", "Actividad"), 1
            )
        ],
    ]
    CSS = """
    #top-status { height: 1; padding: 0 1; background: $panel; }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher { height: 1fr; }
    DataTable { height: 1fr; min-height: 3; }
    #summary-kpis {
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    #summary-kpis Horizontal {
        height: auto;
        min-height: 1;
    }
    .kpi-card {
        height: auto;
        min-height: 1;
        width: 1fr;
        padding: 1 2;
        margin: 0 1;
        border: solid $primary;
        text-align: center;
        content-align: center middle;
    }
    #portal-counts, #config-health, #recent-activity,
    #pending-detail, #ranking-filter, #ranking-detail, #trend-message {
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    #portal-counts { border: solid $secondary; }
    #config-health { border: solid $warning; }
    #recent-activity { border: solid $success; }
    #pending-detail, #ranking-detail, #trend-message { color: $text-muted; }
    #trend-spark { height: 3; }
    #log { height: 1fr; min-height: 3; }
    """

    def __init__(self, db_path: str, config_path: Path | None = None) -> None:
        super().__init__()
        self.db_path = db_path
        self.config_path = config_path
        self._scanning = False
        self._pending_ids: list[int] = []
        self._pending_details: list[str] = []
        self._pending_urls: list[str] = []
        self._ranking_all: list[dict[str, Any]] = []
        self._ranking_rows: list[dict[str, Any]] = []
        self._ranking_filter = 0

    # ------------------------------------------------------------- composition

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("En reposo", id="top-status")
        with TabbedContent(id="tabs"):
            with TabPane("Resumen", id="summary-tab"):
                with Horizontal(id="summary-kpis"):
                    yield Static("TOTAL\n0", id="kpi-total", classes="kpi-card")
                    yield Static("OPORTUNIDADES\n0", id="kpi-opportunities", classes="kpi-card")
                    yield Static("MEDIANA €/m²\n—", id="kpi-median", classes="kpi-card")
                    yield Static("PENDIENTES\n0", id="kpi-pending", classes="kpi-card")
                yield Static("Portales: ninguno", id="portal-counts")
                yield Static("Configuración no disponible", id="config-health")
            with TabPane("Pendientes", id="pending-tab"):
                yield DataTable(id="pending")
                yield Static(id="pending-detail")
            with TabPane("Ranking", id="ranking-tab"):
                yield Static(id="ranking-filter")
                yield DataTable(id="ranking")
                yield Static(id="ranking-detail")
            with TabPane("Tendencias", id="trends-tab"):
                yield Static(id="trend-message")
                yield Sparkline([], id="trend-spark")
                yield DataTable(id="evolution")
            with TabPane("Actividad", id="activity-tab"):
                yield DataTable(id="runs")
                yield Static("Sin ejecuciones todavía", id="recent-activity")
                yield RichLog(id="log", markup=False, highlight=False, wrap=True, max_lines=1000)
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#pending", DataTable).add_columns(*_TABLE_COLUMNS)
        self.query_one("#ranking", DataTable).add_columns(*_TABLE_COLUMNS)
        self.query_one("#evolution", DataTable).add_columns(
            "Semana", "N", "Media €/m²", "P50 €/m²"
        )
        self.query_one("#runs", DataTable).add_columns(
            "Día", "Encontrados", "Nuevos", "Alertas"
        )
        self.query_one("#log", RichLog).write("Listo. Pulsa s para escanear, a para aprobar.")
        self.action_refresh()

    # -------------------------------------------------------------------- scan

    def action_scan(self) -> None:
        if self._scanning:
            self.notify("Ya hay un escaneo en curso", severity="warning")
            return
        self._scanning = True
        self.query_one("#top-status", Static).update("ESCANEANDO")
        self.query_one("#log", RichLog).write("Escaneando portales…")
        self.run_worker(self._scan_task, thread=True, exclusive=True)

    def _scan_task(self) -> None:
        """Run one pipeline cycle off the event loop; capture its output."""
        buf = io.StringIO()
        restored = False
        try:
            try:
                from home_ops.cli import app as cli_app

                old_file = cli_app.console.file
                cli_app.console.file = buf
                try:
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        cli_app._run_scan(self.config_path)
                finally:
                    cli_app.console.file = old_file
            except Exception as exc:  # surface scraper/parse failures in the log
                buf.write(f"\nEscaneo falló: {exc}\n")
            self.call_from_thread(self._scan_finished, buf.getvalue())
            restored = True
        finally:
            if not restored:
                self._scanning = False

    def _scan_finished(self, output: str) -> None:
        self._scanning = False
        self.query_one("#top-status", Static).update("EN REPOSO")
        self.query_one("#log", RichLog).write(Text.from_ansi(output))
        self.action_refresh()

    # ----------------------------------------------------------------- approve

    def action_approve(self) -> None:
        table = self.query_one("#pending", DataTable)
        if not self._pending_ids:
            self.notify("No hay aprobaciones pendientes", severity="warning")
            return
        if not 0 <= table.cursor_row < len(self._pending_ids):
            self.notify("No hay listing seleccionado", severity="warning")
            return
        listing_id = self._pending_ids[table.cursor_row]
        now = datetime.now(UTC)
        with get_connection(self.db_path) as db:
            db.init_db()
            db.conn.execute(
                """INSERT INTO pending_approvals (listing_id, approved, approved_at)
                   VALUES (?, TRUE, ?)
                   ON CONFLICT (listing_id) DO UPDATE
                   SET approved = TRUE, approved_at = ?""",
                [listing_id, now, now],
            )
        self.query_one("#log", RichLog).write(f"Listing {listing_id} aprobado.")
        self.action_refresh()

    # ------------------------------------------------------------------ config

    def action_config(self) -> None:
        """Open the setup wizard as a modal screen (Config tab)."""
        from home_ops.setup.wizard import SetupWizard

        config_path = self.config_path or Path.cwd() / "user_profile.yml"
        env_path = config_path.parent / ".env"
        self.push_screen(SetupWizard(config_path, env_path), self._config_closed)

    def _config_closed(self, saved: bool | None) -> None:
        if saved:
            self.action_refresh()
            self.notify("Configuración actualizada. Pulsa s para re-escanear.")

    # ------------------------------------------------------------------- reset

    def action_reset_snapshots(self) -> None:
        from home_ops.scraper.lifecycle import invalidate_snapshots

        invalidate_snapshots()
        self.query_one("#log", RichLog).write(
            "Snapshots invalidados — próximo escaneo arranca en frío."
        )

    # ------------------------------------------------------- tab / filter / url

    def action_help(self) -> None:
        self.notify(
            "s escanear · r actualizar · a aprobar · f filtrar · o abrir · x reiniciar · 1–5 pestañas · q salir",
            title="Atajos",
            timeout=8,
        )

    def action_tab(self, number: int) -> None:
        self.query_one("#tabs", TabbedContent).active = _TAB_IDS[number - 1]

    def action_filter_ranking(self) -> None:
        """Cycle the ranking filter without touching the database."""
        self._ranking_filter = {0: 70, 70: 85, 85: 0}[self._ranking_filter]
        self._render_ranking()

    def action_open_listing(self) -> None:
        """Open the selected row's URL — http/https only, never a shell."""
        active = self.query_one("#tabs", TabbedContent).active
        if active == "pending-tab":
            table = self.query_one("#pending", DataTable)
            urls = self._pending_urls
        elif active == "ranking-tab":
            table = self.query_one("#ranking", DataTable)
            urls = [str(row.get("url") or "") for row in self._ranking_rows]
        else:
            self.notify("Abrir solo está disponible para listings", severity="warning")
            return
        if not urls:
            self.notify("No hay listing seleccionado", severity="warning")
            return
        if not 0 <= table.cursor_row < len(urls):
            self.notify("No hay listing seleccionado", severity="warning")
            return
        url = urls[table.cursor_row]
        if not _is_safe_listing_url(url):
            self.notify("URL de listing insegura o faltante", severity="warning")
            return
        webbrowser.open(url)

    # ------------------------------------------------------------ cursor detail

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update the detail pane from the in-memory cache (no DB access)."""
        index = event.cursor_row
        if event.data_table.id == "pending" and 0 <= index < len(self._pending_details):
            self.query_one("#pending-detail", Static).update(
                f"{self._pending_details[index]} · {_OPEN_HINT}"
            )
        elif event.data_table.id == "ranking" and 0 <= index < len(self._ranking_rows):
            self.query_one("#ranking-detail", Static).update(
                self._ranking_detail(self._ranking_rows[index])
            )

    # ------------------------------------------------------------------ helpers

    def _config_status(self) -> str:
        """Best-effort config summary — never renders secret values."""
        try:
            from home_ops.config.loader import load_config

            config = load_config(self.config_path)
            telegram = bool(config.telegram_bot_token and config.telegram_chat_id)
            llm = escape(str(config.llm.model)) if config.llm.enabled and config.llm.model else "No"
            return (
                f"Telegram: {'Sí' if telegram else 'No'}   "
                f"LLM: {llm}   Portales: {len(config.portal_urls)}"
            )
        except Exception:
            return "Configuración no disponible"

    @staticmethod
    def _price(value: Any) -> str:
        return f"{float(value):.0f} €" if value is not None else "—"

    @staticmethod
    def _eur_m2(price: Any, m2: Any) -> str:
        if price is None or not m2:
            return "—"
        return f"{float(price) / float(m2):.0f}"

    @staticmethod
    def _ranking_detail(row: dict[str, Any]) -> str:
        address = escape(str(row["address"] or ""))
        rooms = str(row["rooms"] or "—")
        m2 = str(row["m2"] or "—")
        url = escape(str(row["url"] or "sin URL"))
        return f"{address} | {rooms} hab. | {m2} m² | {url} · {_OPEN_HINT}"

    def _render_ranking(self) -> None:
        """Repaint the ranking table from the cached top-100 by score desc."""
        threshold = self._ranking_filter
        self._ranking_rows = [
            row
            for row in self._ranking_all
            if not threshold or float(row["score"]) >= threshold
        ]
        table = self.query_one("#ranking", DataTable)
        table.clear()
        for row in self._ranking_rows:
            table.add_row(
                str(row["id"]),
                str(row["address"] or ""),
                self._price(row["price"]),
                self._eur_m2(row["price"], row["m2"]),
                f"{float(row['score']):.1f}",
                str(row["portal"] or ""),
            )
        label = "Todos" if not threshold else f">={threshold}"
        self.query_one("#ranking-filter", Static).update(
            f"Filtro: {label}   (f cicla · top 100 por score)"
        )
        detail = (
            self._ranking_detail(self._ranking_rows[0])
            if self._ranking_rows
            else "Sin listings puntuados"
        )
        self.query_one("#ranking-detail", Static).update(detail)

    # ------------------------------------------------------------------ refresh

    def action_refresh(self) -> None:
        """Open the DB once, read every panel's data, close, then repaint."""
        with get_connection(self.db_path) as db:
            db.init_db()
            counts = db.conn.execute(
                "SELECT COUNT(*), MAX(fetched_at) FROM listings"
            ).fetchone()
            total = int(counts[0]) if counts else 0
            last_scan = counts[1] if counts else None
            high_row = db.conn.execute(
                "SELECT COUNT(*) FROM listings WHERE score >= 70"
            ).fetchone()
            high_score = int(high_row[0]) if high_row else 0
            pending = db.conn.execute(
                """SELECT p.listing_id, l.address, p.score, l.price, l.m2,
                          l.rooms, l.url, l.portal
                   FROM pending_approvals p
                   LEFT JOIN listings l ON l.id = p.listing_id
                   WHERE p.approved = FALSE
                   ORDER BY p.created_at ASC, p.listing_id ASC"""
            ).fetchall()
            ranking = db.conn.execute(
                """SELECT id, address, score, price, m2, rooms, url, portal
                   FROM listings
                   WHERE score IS NOT NULL
                   ORDER BY score DESC, id ASC
                   LIMIT 100"""
            ).fetchall()
            price_m2 = analytics_mod.price_per_m2_stats(db)
            portals = analytics_mod.portal_counts(db)
            evolution = analytics_mod.price_evolution_by_week(db)
            runs = analytics_mod.runs_timeseries(db)

        status_text = (
            f"Propiedades: {total}   Último escaneo: {escape(str(last_scan or 'nunca'))}   "
            f"Pendientes: {len(pending)}"
        )
        self.query_one("#top-status", Static).update(status_text)

        median = price_m2["p50"]
        median_text = f"{float(median):.0f}" if median is not None else "—"
        self.query_one("#kpi-total", Static).update(f"TOTAL\n{total}")
        self.query_one("#kpi-opportunities", Static).update(f"OPORTUNIDADES\n{high_score}")
        self.query_one("#kpi-median", Static).update(f"MEDIANA €/m²\n{median_text}")
        self.query_one("#kpi-pending", Static).update(f"PENDIENTES\n{len(pending)}")
        portal_text = ", ".join(f"{escape(str(portal))}: {count}" for portal, count in portals)
        self.query_one("#portal-counts", Static).update(
            f"Portales: {portal_text or 'ninguno'}"
        )
        self.query_one("#config-health", Static).update(self._config_status())

        # recent-activity: last run day or placeholder
        if runs:
            last = runs[-1]
            act = (
                f"{escape(str(last['day']))} — {last['listings_found']} encontrados, "
                f"{last['listings_new']} nuevos, {last['alerts_sent']} alertas"
            )
        else:
            act = "Sin ejecuciones todavía"
        self.query_one("#recent-activity", Static).update(act)

        pending_table = self.query_one("#pending", DataTable)
        pending_table.clear()
        self._pending_ids = []
        self._pending_details = []
        self._pending_urls = []
        for row in pending:
            self._pending_ids.append(int(row[0]))
            self._pending_urls.append(str(row[6] or ""))
            addr = escape(str(row[1] or ""))
            url_str = escape(str(row[6] or "sin URL"))
            self._pending_details.append(
                f"{addr} | {self._price(row[3])} | "
                f"{row[4] or '—'} m² | {row[5] or '—'} hab. | {url_str}"
            )
            pending_table.add_row(
                str(row[0]),
                str(row[1] or ""),
                self._price(row[3]),
                self._eur_m2(row[3], row[4]),
                f"{float(row[2]):.1f}" if row[2] is not None else "—",
                str(row[7] or ""),
            )
        self.query_one("#pending-detail", Static).update(
            f"{self._pending_details[0]} · {_OPEN_HINT}"
            if self._pending_details
            else "Sin pendientes"
        )

        keys = ("id", "address", "score", "price", "m2", "rooms", "url", "portal")
        self._ranking_all = [dict(zip(keys, row, strict=True)) for row in ranking]
        self._render_ranking()

        evo_table = self.query_one("#evolution", DataTable)
        evo_table.clear()
        for week_row in evolution:
            evo_table.add_row(
                week_row["week"][:10],
                str(week_row["n"]),
                f"{week_row['mean_eur_m2']:.0f}",
                f"{week_row['p50_eur_m2']:.0f}",
            )
        has_trend = len(evolution) >= 2
        self.query_one("#trend-spark", Sparkline).data = (
            [float(week_row["p50_eur_m2"]) for week_row in evolution] if has_trend else []
        )
        self.query_one("#trend-message", Static).update(
            "Histórico semanal €/m² (p50)"
            if has_trend
            else "Datos insuficientes: hacen falta al menos 2 semanas de histórico"
        )

        run_table = self.query_one("#runs", DataTable)
        run_table.clear()
        for run_row in runs:
            run_table.add_row(
                run_row["day"],
                str(run_row["listings_found"]),
                str(run_row["listings_new"]),
                str(run_row["alerts_sent"]),
            )


def run(db_path: str, config_path: Path | None = None) -> None:
    HomeOpsTUI(db_path, config_path).run()
