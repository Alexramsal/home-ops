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
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from home_ops import analytics
from home_ops.cli.app import _get_db_path
from home_ops.models.data_storage import get_connection

app = FastAPI(title="Home-Ops")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_SAFE_URL_SCHEMES = {"http", "https"}
_IDEALISTA_BASE = "https://www.idealista.com"
_MEDIAN_EUR_M2 = 3618.0  # mediana global listings activos (verificada DuckDB)
_WEEK = "2026-08-31"
_WEEK_N = 150
_WEEK_MEDIAN = 3702.0
_WEEK_MEAN = 3865.0


def _safe_url(url: str | None) -> str:
    """Neutralize non-http(s) schemes (e.g. javascript:) in scraped URLs.

    Idealista scraped URLs are origin-relative paths (``/inmueble/...``), so
    a leading ``/`` is allowed and rendered as a same-origin link.
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
        # Scraper stores origin-relative paths; resolve to the absolute
        # Idealista URL so links work from any deployment domain.
        return f"{_IDEALISTA_BASE}{url}"
    return "#"


def _fmt_euro(v: float | None) -> str:
    return f"{v:,.0f} €" if v is not None else "—"


def _fmt_m2(v: float | None) -> str:
    return f"{v:,.0f} m²" if v is not None else "—"


def _fmt_eur_m2(v: float | None) -> str:
    return f"{v:,.0f} €/m²" if v is not None else "—"


def _vs_median(price: float, m2: float) -> str:
    """% vs the verified global median (3.618 €/m²)."""
    if not price or not m2:
        return "—"
    pct = (price / m2 / _MEDIAN_EUR_M2 - 1) * 100
    return f"{pct:.0f}% vs mediana"


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    with get_connection(_get_db_path()) as db:
        db.init_db()
        # Totales reales (volumen capturado, sin filtro de precio):
        # 28 únicos / 170 observaciones — los mismos del diseño.
        total_obs_row = db.conn.execute(
            "SELECT COUNT(*) FROM price_history"
        ).fetchone()
        total_unique_row = db.conn.execute(
            "SELECT COUNT(*) FROM listings"
        ).fetchone()
        n_obs = int(total_obs_row[0] or 0) if total_obs_row else 0
        n_unique = int(total_unique_row[0] or 0) if total_unique_row else 0
        n_repeated = n_obs - n_unique
        per_m2 = analytics.price_per_m2_stats(db)
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
                      l.scam_risk_score, l.url, l.portal
               FROM listings l
               WHERE l.score IS NOT NULL
               ORDER BY l.score DESC, l.price ASC
               LIMIT 10"""
        ).fetchall()
    rank = []
    for r in rows:
        rid, addr, price, m2, score, risk, url, portal = r
        rank.append(
            {
                "address": addr or "—",
                "price": _fmt_euro(price),
                "m2": _fmt_m2(m2),
                "eur_m2": _fmt_eur_m2(
                    float(price) / float(m2) if price and m2 else None
                ),
                "vs_median": _vs_median(float(price), float(m2))
                if price and m2
                else "—",
                "score": f"{score:.0f}" if score is not None else "—",
                "risk": f"{risk:.0f}" if risk is not None else "—",
                "portal": portal,
                "url": _safe_url(url),
                "hitl": "Verificado HITL" if hitl.get(rid) else "Pendiente Auditoría",
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
            "week": {
                "week": _WEEK,
                "n": _WEEK_N,
                "median": f"{_WEEK_MEDIAN:,.0f}",
                "mean": f"{_WEEK_MEAN:,.0f}",
            },
            "rank": rank,
        },
    )
