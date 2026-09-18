"""Minimal public-facing web view — read-only audit dashboard.

No login (portfolio, not a product): defended by nginx/host rate-limit,
not application auth. Every number comes straight from DuckDB — no
synthetic data, no invented trends (the UI itself declares the 1-week
sample is too small to model seasonality).

Ponytail: no pagination -- add if listing count grows past a screenful
(currently tens of rows).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from home_ops import analytics, i18n
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
    locale: i18n.Locale = "es",
    ubicacion: str | None = None,
    ubicacion_motivo: str | None = None,
    auditoria: str | None = None,
) -> str:
    """Compact LLM audit summary: state, orientation, noise, location verdict,
    red flags and full audit text; or a clear placeholder when absent."""
    if llm_id is None:
        return i18n.t("llm.none", locale)
    parts = [p for p in (estado, orient, ruido) if p]
    if ubicacion:
        badge = {"buena": "✓", "regular": "~", "mala": "✗"}.get(ubicacion, "")
        parts.append(f"{badge} {ubicacion.capitalize()} ({ubicacion_motivo})")
    if flags:
        parts.append("Flags: " + ", ".join(flags))
    if parts:
        text = " · ".join(parts)
        if auditoria:
            text += f" — {auditoria}"
        return text
    # Audit run produced a summary but no structured fields (e.g. description
    # too short to audit): surface the summary instead of "not analyzed".
    if auditoria:
        return auditoria
    return i18n.t("llm.none", locale)


def _vs_median(price: float, m2: float, median_eur_m2: float, locale: i18n.Locale = "es") -> str:
    """% vs the current global median (€/m²)."""
    if not price or not m2 or not median_eur_m2:
        return "—"
    pct = (price / m2 / median_eur_m2 - 1) * 100
    return i18n.t("vs.median", locale, pct=f"{pct:.0f}")


def _is_db_lock_error(exc: Exception) -> bool:
    """Return True if exc represents a DuckDB database file lock error."""
    if not isinstance(exc, (duckdb.Error, RuntimeError)):
        return False
    msgs = [str(exc)]
    if exc.__cause__:
        msgs.append(str(exc.__cause__))
    combined = " ".join(msgs).lower()
    lock_keywords = (
        "could not set lock",
        "conflicting lock",
        "database is locked",
        "db locked",
        "lock on file",
        "could not obtain lock",
        "locked by",
    )
    return any(k in combined for k in lock_keywords)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, lang: str | None = None, page: int | str = 1) -> HTMLResponse:
    locale = i18n.resolve_locale(lang, request.headers.get("accept-language"))
    try:
        page_num = int(page)
    except (ValueError, TypeError):
        page_num = 1
    if page_num < 1:
        page_num = 1

    try:
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

            total_scored_row = db.conn.execute(
                "SELECT COUNT(*) FROM listings WHERE score IS NOT NULL"
            ).fetchone()
            total_scored = int(total_scored_row[0] or 0) if total_scored_row else 0

            scored_70_row = db.conn.execute(
                "SELECT COUNT(*) FROM listings WHERE score IS NOT NULL AND score >= 70"
            ).fetchone()
            scored_70 = int(scored_70_row[0] or 0) if scored_70_row else 0

            risk_row = db.conn.execute(
                "SELECT COUNT(*) FROM listings WHERE scam_risk_score IS NOT NULL"
            ).fetchone()
            n_risk = int(risk_row[0] or 0) if risk_row else 0

            # Pagination calculations (10 per page)
            per_page = 10
            total_pages = max(1, math.ceil(total_scored / per_page)) if total_scored > 0 else 1
            if page_num > total_pages:
                page_num = total_pages
            offset = (page_num - 1) * per_page

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
                          a.ruido_zona, a.red_flags_llm, a.ubicacion,
                          a.ubicacion_motivo, a.auditoria
                   FROM listings l
                   LEFT JOIN llm_analysis a ON a.listing_id = l.id
                   WHERE l.score IS NOT NULL
                   ORDER BY l.score DESC, l.price ASC, l.id ASC
                   LIMIT ? OFFSET ?""",
                (per_page, offset),
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
    except Exception as exc:
        if _is_db_lock_error(exc):
            raise HTTPException(
                status_code=503,
                detail=i18n.t("web.db_locked", locale),
                headers={"Retry-After": "5"},
            ) from exc
        raise
    rank = []
    for r in rows:
        (
            rid, addr, price, m2, score, risk, url, portal,
            llm_id, estado, orient, ruido, flags, ubicacion,
            ubicacion_motivo, auditoria,
        ) = r
        rank.append(
            {
                "id": rid,
                "address": addr or "—",
                "price": _fmt_euro(price),
                "m2": _fmt_m2(m2),
                "eur_m2": _fmt_eur_m2(
                    float(price) / float(m2) if price and m2 else None
                ),
                "vs_median": _vs_median(float(price), float(m2), median_eur_m2, locale)
                if price and m2
                else "—",
                "score": f"{score:.0f}" if score is not None else "—",
                "risk": f"{risk:.0f}" if risk is not None else "—",
                "portal": portal,
                "url": _safe_url(url, portal),
                "hitl": i18n.t("hitl.verified", locale)
                if hitl.get(rid)
                else i18n.t("hitl.pending", locale),
                "hitl_raw": bool(hitl.get(rid)),
                "llm": _fmt_llm(
                    llm_id, estado, orient, ruido, flags, locale,
                    ubicacion, ubicacion_motivo, auditoria,
                ),
                "llm_id": llm_id,
            }
        )

    pagination = {
        "page": page_num,
        "per_page": per_page,
        "total_items": total_scored,
        "total_pages": total_pages,
        "has_prev": page_num > 1,
        "has_next": page_num < total_pages,
        "prev_page": page_num - 1,
        "next_page": page_num + 1,
        "start_item": (page_num - 1) * per_page + 1 if total_scored > 0 else 0,
        "end_item": min(page_num * per_page, total_scored),
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "locale": locale,
            "t": lambda key, **kwargs: i18n.t(key, locale, **kwargs),
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
            "pagination": pagination,
        },
    )
