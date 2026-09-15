"""Textual setup wizard — point-and-click config for Home-Ops.

Run via ``homeops setup``. Edits user_profile.yml + .env (secrets stay in
.env), with live "test" buttons for Telegram and the LLM endpoint.

Layout: left column = sections, right column = the selected section's
inputs + a live status line. Bottom row = Save / Cancel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Switch,
    TextArea,
)

from home_ops.setup.core import load_state, test_llm, test_telegram, write_config

# section -> (field id, label, key path into state, password?)
_FIELD_SPECS: dict[str, list[tuple[str, str, tuple[str, ...], bool | str]]] = {
    "Telegram": [
        ("bot_token", "Token del bot", ("telegram", "bot_token"), True),
        ("chat_id", "Chat ID", ("telegram", "chat_id"), False),
        ("tg_test", "Test Telegram", (), True),
    ],
    "LLM": [
        ("llm_enabled", "Activar LLM", ("llm", "enabled"), "boolean"),
        ("ai_base_url", "Base URL", ("env", "AI_BASE_URL"), False),
        ("ai_api_key", "API Key", ("env", "AI_API_KEY"), True),
        ("ai_model", "Model", ("env", "AI_MODEL"), False),
        ("llm_test", "Test LLM", (), True),
    ],
    "Portal": [
        ("portals", "URLs (una por línea)", ("portals",), False),
    ],
    "Scoring": [
        ("min_score", "Alerta mínima (0-100)", ("scoring", "min_score_to_alert"), False),
        ("price_median", "Mediana precio (€)", ("scoring", "price_median"), False),
        ("m2_threshold", "m² mínimo", ("scoring", "m2_threshold"), False),
        ("m2_large", "m² grande", ("scoring", "m2_large_threshold"), False),
        ("salary", "Salario provincia (€)", ("scoring", "salary_province"), False),
    ],
    "Alertas": [
        ("mode", "Modo (daily|interval)", ("schedule", "mode"), False),
        ("daily_time", "Hora diaria (HH:MM)", ("schedule", "daily_time"), False),
        ("interval_hours", "Intervalo (horas)", ("schedule", "interval_hours"), False),
        ("timezone", "Zona horaria", ("schedule", "timezone"), False),
        ("max_alerts", "Máx alertas/día", ("schedule", "max_alerts_per_day"), False),
    ],
    "Comprador": [
        ("itp", "ITP por defecto (0-1)", ("buyer_protection", "default_itp_rate"), False),
        (
            "ceiling",
            "Esfuerzo hipotecario máx (0-1)",
            ("buyer_protection", "mortgage_income_ceiling"),
            False,
        ),
        ("down", "Entrada (0-1)", ("buyer_protection", "down_payment_pct"), False),
        ("years", "Años hipoteca", ("buyer_protection", "mortgage_years"), False),
    ],
}

_DESCRIPTIONS = {
    "Telegram": "Token del bot y chat donde llegarán las alertas. "
    "Crea un bot con @BotFather y obtén el chat_id con @userinfobot.",
    "LLM": "Endpoint compatible OpenAI para enriquecer descripciones "
    "y detectar señales de estafa. Deja vacío para usar solo reglas.",
    "Portal": "URLs de búsqueda a escanear (una por línea).",
    "Scoring": "Pesos y umbrales del scoring 5 dimensiones.",
    "Alertas": "Cuándo corre el escáner y cuántas alertas máximas por día.",
    "Comprador": "Protección al comprador: ITP, esfuerzo hipotecario.",
}


def _section_id(name: str) -> str:
    return f"section-{name.lower()}"


class SetupWizard(ModalScreen[bool]):
    """TUI wizard to configure Home-Ops without touching YAML/env by hand.

    A modal screen, so the main TUI can push it as a Config tab without a
    second App; the CLI wraps it in the tiny :class:`SetupApp` host.
    """

    TITLE = "Home-Ops Setup"
    SUB_TITLE = "Configura portal, scoring, alertas, Telegram y LLM"

    BINDINGS = [
        ("ctrl+s", "save", "Guardar"),
        ("escape", "cancel", "Salir"),
    ]

    CSS = """
    Grid { grid-size: 2 1; grid-gutter: 1 2; }
    #nav { height: 100%; }
    #panel { height: 100%; }
    #fields { margin-top: 1; }
    #panel-title { text-style: bold; }
    #panel-status { margin-top: 1; }
    .actions { height: 3; }
    """

    def __init__(self, config_path: Path, env_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.env_path = env_path
        self.state = load_state(config_path, env_path)
        self._sections: list[str] = list(_FIELD_SPECS.keys())

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(classes="wizard-grid"):
            with Vertical(id="nav"):
                yield ListView(*[ListItem(Label(name)) for name in self._sections])
            with VerticalScroll(id="panel"):
                yield Static(id="panel-title")
                yield Static(id="panel-desc")
                with Vertical(id="fields"):
                    for name in self._sections:
                        with Vertical(id=_section_id(name), classes="section"):
                            for fid, label, _path, pwd in _FIELD_SPECS[name]:
                                value = self._initial_value(fid, label, _path)
                                if not _path:
                                    yield Button(label, id=fid)
                                elif fid == "portals":
                                    yield Label(f"[b]{label}[/b]")
                                    yield TextArea(
                                        value,
                                        id=fid,
                                        placeholder=label,
                                        soft_wrap=True,
                                    )
                                elif pwd == "boolean":
                                    yield Label(f"[b]{label}[/b]")
                                    yield Switch(value=str(value).lower() in ("1", "true"), id=fid)
                                else:
                                    yield Label(f"[b]{label}[/b]")
                                    yield Input(
                                        value=value,
                                        password=bool(pwd),
                                        id=fid,
                                        placeholder=label,
                                    )
                yield Static(id="panel-status")
        with Horizontal(classes="actions"):
            yield Button("Guardar", variant="primary", id="save")
            yield Button("Cancelar", id="cancel")
        yield Footer()

    def _initial_value(self, fid: str, label: str, path: tuple[str, ...]) -> str:
        """Pull the widget's pre-fill value out of the loaded state."""
        if not path:
            return ""
        node: Any = self.state
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return ""
            node = node[key]
        if isinstance(node, list):
            return "\n".join(str(u) for u in node)
        return str(node)

    def on_mount(self) -> None:
        self._render_section(0)

    # ------------------------------------------------------------------ render

    def _render_section(self, index: int) -> None:
        name = self._sections[index]
        self.query_one("#panel-title", Static).update(f"[b]{name}[/b]")
        self.query_one("#panel-desc", Static).update(_DESCRIPTIONS[name])
        for other in self._sections:
            self.query_one(f"#{_section_id(other)}", Vertical).display = other == name
        self.query_one("#panel-status", Static).update("")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is not None and idx < len(self._sections):
            self._render_section(idx)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._render_section(event.index)

    # -------------------------------------------------------------- persistence

    def _get_input(self, fid: str) -> str:
        widget = self.query_one(f"#{fid}")
        if isinstance(widget, TextArea):
            return widget.text
        if isinstance(widget, Switch):
            return "1" if widget.value else "0"
        if isinstance(widget, Input):
            return widget.value
        return ""

    def _collect_state(self) -> dict[str, Any]:
        s = self.state
        s["telegram"]["bot_token"] = self._get_input("bot_token").strip()
        s["telegram"]["chat_id"] = self._get_input("chat_id").strip()

        llm_enabled = self._get_input("llm_enabled") in ("1", "true", "True")
        s["llm"]["enabled"] = llm_enabled
        s["env"]["AI_BASE_URL"] = self._get_input("ai_base_url").strip()
        s["env"]["AI_API_KEY"] = self._get_input("ai_api_key").strip()
        s["env"]["AI_MODEL"] = self._get_input("ai_model").strip()
        s["llm"]["model"] = self._get_input("ai_model").strip()

        urls = [u.strip() for u in self._get_input("portals").splitlines() if u.strip()]
        s["portals"] = urls

        sc = s["scoring"]
        sc["min_score_to_alert"] = self._num("min_score", sc["min_score_to_alert"])
        sc["price_median"] = self._num("price_median", sc["price_median"])
        sc["m2_threshold"] = self._num("m2_threshold", sc["m2_threshold"])
        sc["m2_large_threshold"] = self._num("m2_large", sc["m2_large_threshold"])
        sc["salary_province"] = self._num("salary", sc["salary_province"])

        sch = s["schedule"]
        sch["mode"] = self._get_input("mode").strip() or "daily"
        sch["daily_time"] = self._get_input("daily_time").strip()
        sch["interval_hours"] = self._num("interval_hours", sch["interval_hours"])
        sch["timezone"] = self._get_input("timezone").strip()
        sch["max_alerts_per_day"] = int(self._num("max_alerts", sch["max_alerts_per_day"]))

        bp = s["buyer_protection"]
        bp["default_itp_rate"] = self._num("itp", bp["default_itp_rate"])
        bp["mortgage_income_ceiling"] = self._num("ceiling", bp["mortgage_income_ceiling"])
        bp["down_payment_pct"] = self._num("down", bp["down_payment_pct"])
        bp["mortgage_years"] = int(self._num("years", bp["mortgage_years"]))
        return s

    def _num(self, fid: str, default: float) -> float:
        """Parse an input as float with a sane fallback to the current value."""
        try:
            return float(self._get_input(fid).strip() or default)
        except ValueError:
            self._status(f"Valor inválido en '{fid}', usando {default}.", error=True)
            return float(default)

    def _status(self, text: str, error: bool = False) -> None:
        color = "red" if error else "green"
        self.query_one("#panel-status", Static).update(f"[{color}]{text}[/{color}]")

    def action_save(self) -> None:
        state = self._collect_state()
        if not state["telegram"]["bot_token"]:
            self._status(
                "Sin token de Telegram: las alertas por chat no se enviarán "
                "(los portales, scoring y web sí funcionan).",
                error=False,
            )
        try:
            write_config(self.config_path, self.env_path, state)
        except Exception as exc:
            self._status(f"Error al guardar: {exc}", error=True)
            return
        self.notify("Configuración guardada.")
        self.dismiss(True)

    # ------------------------------------------------------------------- tests

    def _test_telegram(self) -> None:
        # ponytail: urllib síncrono bloquea el event loop de Textual unos
        # segundos; aceptable para un wizard one-off. Upgrade path: mover
        # a run_worker + asyncio.to_thread si la UI llega a congelarse.
        ok, msg = test_telegram(
            self._get_input("bot_token").strip(),
            self._get_input("chat_id").strip(),
        )
        self._status(msg, error=not ok)

    def _test_llm(self) -> None:
        # ponytail: ídem _test_telegram — urllib síncrono en el loop.
        ok, msg = test_llm(
            self._get_input("ai_base_url").strip(),
            self._get_input("ai_api_key").strip(),
            self._get_input("ai_model").strip(),
        )
        self._status(msg, error=not ok)

    # ----------------------------------------------------------------- actions

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "save":
            self.action_save()
        elif btn_id == "cancel":
            self.action_cancel()
        elif btn_id == "tg_test":
            self._test_telegram()
        elif btn_id == "llm_test":
            self._test_llm()

    # ------------------------------------------------------------------ actions

    def action_cancel(self) -> None:
        # Screen dismissal returns control to the TUI; nothing to persist.
        self.dismiss(False)


class SetupApp(App[None]):
    """Minimal host so ``SetupWizard`` (a Screen) can run standalone via CLI."""

    def __init__(self, config_path: Path, env_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.env_path = env_path

    def on_mount(self) -> None:
        self.push_screen(SetupWizard(self.config_path, self.env_path))


def run(config_path: Path, env_path: Path) -> None:
    SetupApp(config_path, env_path).run()
