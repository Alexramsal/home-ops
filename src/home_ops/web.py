"""Minimal public-facing web view — read-only audit dashboard.

No login (portfolio, not a product): defended by nginx/host rate-limit,
not application auth. Every number comes straight from DuckDB — no
synthetic data, no invented trends (the UI itself declares the 1-week
sample is too small to model seasonality).

Ponytail: no pagination -- add if listing count grows past a screenful
(currently tens of rows).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from home_ops import analytics
from home_ops.models.data_storage import get_connection, get_db_path

app = FastAPI(title="Home-Ops")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_SAFE_URL_SCHEMES = {"http", "https"}
_PORTAL_BASES = {
    "idealista": "https://www.idealista.com",
    "fotocasa": "https://www.fotocasa.es",
    "pisos": "https://www.pisos.com",
    "tecnocasa": "https://www.tecnocasa.es",
    "habitaclia": "https://www.habitaclia.com",
}


def _safe_url(url: str | None, portal: str = "idealista") -> str:
    """Neutralize non-http(s) schemes (e.g. javascript:) in scraped URLs.

    Scraped URLs may be origin-relative paths, so a leading ``/`` is resolved
    against the matching controlled portal base.
    """
    if not url:
        return "#"
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return "#"
    if scheme in _SAFE_URL_SCHEMES:
        return url
    if url.startswith("/"):
        # Scrapers store origin-relative paths; resolve them to the matching
        # portal so links work from any deployment domain.
        base = _PORTAL_BASES.get(portal)
        return f"{base}{url}" if base else "#"
    return "#"


def _fmt_euro(v: float | None) -> str:
    return f"{v:,.0f} €" if v is not None else "—"


def _fmt_m2(v: float | None) -> str:
    return f"{v:,.0f} m²" if v is not None else "—"


def _fmt_eur_m2(v: float | None) -> str:
    return f"{v:,.0f} €/m²" if v is not None else "—"


def _fmt_es_number(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _build_weekly_chart(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build SVG coordinates from observed weekly values only."""
    if not series:
        return None
    width, height = 760, 340
    left, right, top, bottom = 82, 58, 42, 82
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [float(row[key]) for row in series for key in ("median_raw", "mean_raw")]
    low, high = min(values), max(values)
    padding = max((high - low) * 0.12, max(high, 1) * 0.04)
    y_min, y_max = max(0.0, low - padding), high + padding
    span = y_max - y_min or 1.0

    def y(value: float) -> float:
        return top + (y_max - value) / span * plot_height

    points: list[dict[str, Any]] = []
    for index, row in enumerate(series):
        x = left + (plot_width / 2 if len(series) == 1 else index * plot_width / (len(series) - 1))
        points.append({
            **row,
            "x": round(x, 2),
            "median_y": round(y(float(row["median_raw"])), 2),
            "mean_y": round(y(float(row["mean_raw"])), 2),
        })
    ticks = [
        {"y": round(top + index * plot_height / 4, 2), "label": _fmt_es_number(y_max - index * span / 4)}
        for index in range(5)
    ]
    first = float(series[0]["median_raw"])
    last = float(series[-1]["median_raw"])
    variation = ((last / first) - 1) * 100 if len(series) > 1 and first else None
    return {
        "view_box": f"0 0 {width} {height}", "left": left, "right_x": width - right,
        "top": top, "bottom_y": height - bottom, "points": points, "ticks": ticks,
        "median_path": " ".join(f"{p['x']},{p['median_y']}" for p in points),
        "mean_path": " ".join(f"{p['x']},{p['mean_y']}" for p in points),
        "variation": f"{variation:+.1f}".replace(".", ",") if variation is not None else None,
    }


def _fmt_llm(
    llm_id: int | None,
    estado: str | None,
    orient: str | None,
    ruido: str | None,
    flags: list[str] | None,
) -> str:
    """Compact one-line LLM summary, or a clear placeholder when absent."""
    if llm_id is None:
        return "Sin analizar"
    parts = [p for p in (estado, orient, ruido) if p]
    if flags:
        parts.append("Flags: " + ", ".join(flags))
    return " · ".join(parts) if parts else "Sin analizar"


def _vs_median(price: float, m2: float, median_eur_m2: float) -> str:
    """% vs the current global median (€/m²)."""
    if not price or not m2 or not median_eur_m2:
        return "—"
    pct = (price / m2 / median_eur_m2 - 1) * 100
    return f"{pct:.0f}% vs mediana"


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    with get_connection(get_db_path()) as db:
        db.init_db()
        # Mediana global actual
        per_m2 = analytics.price_per_m2_stats(db)
        median_eur_m2 = float(per_m2["p50"] or 0)

        # Semana más reciente
        weekly = db.conn.execute("""
            SELECT date_trunc('week', observed_at), COUNT(*),
                   quantile_cont(price / m2, 0.5), AVG(price / m2)
            FROM price_history WHERE price > 0 AND m2 > 0
            GROUP BY 1 ORDER BY 1 DESC
        """).fetchall()
        latest_week = weekly[0] if weekly else (None, 0, None, None)
        n_weeks = len(weekly)

        series = [
            {
                "date": w[0].strftime("%Y-%m-%d") if w[0] else "—",
                "n": int(w[1]),
                "median": _fmt_es_number(float(w[2])) if w[2] else "—",
                "mean": _fmt_es_number(float(w[3])) if w[3] else "—",
                "median_raw": float(w[2]) if w[2] else None,
                "mean_raw": float(w[3]) if w[3] else None,
            }
            for w in reversed(weekly)  # weekly viene DESC; reverse a ASC
        ]

        # Fecha de corte (última observación)
        cutoff = db.conn.execute("SELECT MAX(observed_at) FROM price_history").fetchone()
        cutoff_date = cutoff[0].strftime("%Y-%m-%d") if cutoff and cutoff[0] else "—"

        # Totales reales (volumen capturado, sin filtro de precio):
        total_obs_row = db.conn.execute(
            "SELECT COUNT(*) FROM price_history"
        ).fetchone()
        total_unique_row = db.conn.execute(
            "SELECT COUNT(*) FROM listings"
        ).fetchone()
        n_obs = int(total_obs_row[0] or 0) if total_obs_row else 0
        n_unique = int(total_unique_row[0] or 0) if total_unique_row else 0
        n_repeated = n_obs - n_unique
        scored_row = db.conn.execute(
            "SELECT COUNT(*) FROM listings WHERE score IS NOT NULL AND score >= 70"
        ).fetchone()
        scored_70 = int(scored_row[0] or 0) if scored_row else 0
        risk_row = db.conn.execute(
            "SELECT COUNT(*) FROM listings WHERE scam_risk_score IS NOT NULL"
        ).fetchone()
        n_risk = int(risk_row[0] or 0) if risk_row else 0
        # HITL state per listing (approved flag from pending_approvals)
        hitl = {
            row[0]: row[1]
            for row in db.conn.execute(
                "SELECT listing_id, approved FROM pending_approvals"
            ).fetchall()
        }
        rows = db.conn.execute(
            """SELECT l.id, l.address, l.price, l.m2, l.score,
                      l.scam_risk_score, l.url, l.portal,
                      a.listing_id, a.estado_reforma, a.orientacion,
                      a.ruido_zona, a.red_flags_llm
               FROM listings l
               LEFT JOIN llm_analysis a ON a.listing_id = l.id
               WHERE l.score IS NOT NULL
               ORDER BY l.score DESC, l.price ASC
               LIMIT 10"""
        ).fetchall()
        counts = {
            str(portal): int(count)
            for portal, count in db.conn.execute(
                """SELECT portal, COUNT(*) AS count
                   FROM listings GROUP BY portal ORDER BY count DESC"""
            ).fetchall()
        }
        # Declared sources stay visible even at 0 coverage until a scan lands rows.
        portals = [
            {
                "portal": name,
                "count": counts.get(name, 0),
                "url": _PORTAL_BASES.get(name),
            }
            for name in sorted(
                {*_PORTAL_BASES, *counts}, key=lambda name: (-counts.get(name, 0), name)
            )
        ]
    rank = []
    for r in rows:
        (
            rid, addr, price, m2, score, risk, url, portal,
            llm_id, estado, orient, ruido, flags,
        ) = r
        rank.append(
            {
                "address": addr or "—",
                "price": _fmt_euro(price),
                "m2": _fmt_m2(m2),
                "eur_m2": _fmt_eur_m2(
                    float(price) / float(m2) if price and m2 else None
                ),
                "vs_median": _vs_median(float(price), float(m2), median_eur_m2)
                if price and m2
                else "—",
                "score": f"{score:.0f}" if score is not None else "—",
                "risk": f"{risk:.0f}" if risk is not None else "—",
                "portal": portal,
                "url": _safe_url(url, portal),
                "hitl": "Verificado HITL" if hitl.get(rid) else "Pendiente Auditoría",
                "llm": _fmt_llm(llm_id, estado, orient, ruido, flags),
            }
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "kpis": {
                "unique": n_unique,
                "obs": n_obs,
                "repeated": n_repeated,
                "median": f"{per_m2['p50']:,.0f}" if per_m2["p50"] is not None else "—",
                "scored70": scored_70,
                "risk": n_risk,
            },
            "n_obs_total": n_obs,
            "n_unique": n_unique,
            "n_repeated": n_repeated,
            "n_scored": scored_70,
            "median_eur_m2": f"{median_eur_m2:,.0f}" if median_eur_m2 else "—",
            "cutoff": cutoff_date,
            "series": series,
            "chart": _build_weekly_chart(series),
            "trend_qty": len(series),
            "week": {
                "date": latest_week[0].strftime("%Y-%m-%d") if latest_week[0] else "—",
                "n": int(latest_week[1]),
                "median": f"{latest_week[2]:,.0f}" if latest_week[2] else "—",
                "mean": f"{latest_week[3]:,.0f}" if latest_week[3] else "—",
                "count": n_weeks,
            },
            "rank": rank,
            "portals": portals,
        },
    )
