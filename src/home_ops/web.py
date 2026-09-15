"""Minimal public-facing web view — read-only results dashboard.

No login (portfolio, not a product): defended by nginx/host rate-limit,
not application auth. Ponytail: no pagination -- add if listing count
grows past a screenful (currently tens of rows).

Numbers come straight from DuckDB (``homeops analytics``): the four
headline KPIs, the ranked opportunity list, and the per-zone median
baseline that powers the 5D scoring.
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


def _safe_url(url: str | None) -> str:
    """Neutralize non-http(s) schemes (e.g. javascript:) in scraped URLs."""
    if not url:
        return "#"
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return "#"
    return url if scheme in _SAFE_URL_SCHEMES else "#"


def _fmt_euro(value: float | None) -> str:
    return f"{value:,.0f} €" if value is not None else "—"


def _fmt_m2(value: float | None) -> str:
    return f"{value:,.0f} m²" if value is not None else "—"


def _fmt_score(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "—"


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    with get_connection(_get_db_path()) as db:
        db.init_db()
        kpis = analytics.price_history_stats(db)
        per_m2 = analytics.price_per_m2_stats(db)
        scored_row = db.conn.execute(
            "SELECT COUNT(*) FROM listings WHERE score IS NOT NULL AND score >= 70"
        ).fetchone()
        scored_70 = int(scored_row[0] or 0) if scored_row else 0
        opp_rows = db.conn.execute(
            """SELECT address, price, m2, score, url, portal
               FROM listings
               WHERE score IS NOT NULL
               ORDER BY score DESC, price ASC
               LIMIT 10"""
        ).fetchall()
    opportunities = [
        {
            "address": r[0],
            "price": _fmt_euro(r[1]),
            "m2": _fmt_m2(r[2]),
            "score": _fmt_score(r[3]),
            "url": _safe_url(r[4]),
            "portal": r[5],
        }
        for r in opp_rows
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "unique_listings": kpis["unique_listings"],
            "observations": kpis["observations"],
            "top_opportunities": opportunities,
            "median_eur_m2": per_m2["p50"],
            "scored_70": scored_70,
        },
    )
