"""Tecnocasa search-result parser.

Selectors verified against a live capture of the Cádiz province feed
(2026-09-15): cards are server-rendered ``div.estate-card`` nodes with absolute
detail links like ``/venta/piso/cadiz/jerez-de-la-frontera/667759.html``.

Public interface (mirrors ``home_ops.scraper.parse``):
    parse_listings(html: str) -> list[dict[str, Any]]
"""

from __future__ import annotations

import re
from typing import Any

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2, _extract_price

_ID_RE = re.compile(r"/(\d+)\.html(?:[?#]|$)")
_INT_RE = re.compile(r"\d+")


def _text(node: Selector) -> str:
    """Return the node's text, joining split content (``135 m`` + ``2``)."""
    return "".join(node.css("::text").getall()).strip()


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Tecnocasa cards into the shared listing contract."""
    if not html or not html.strip():
        return []

    page = Selector(html)
    results: list[dict[str, Any]] = []
    for card in page.css("div.estate-card"):
        url = card.css("a::attr(href)").get("") or ""
        id_match = _ID_RE.search(url)
        if not id_match:
            continue

        titles = card.css("h3.estate-card-title")
        subtitles = card.css("h4.estate-card-subtitle")
        prices = card.css("div.estate-card-current-price")
        rooms = card.css("div.estate-card-rooms span")
        surfaces = card.css("div.estate-card-surface span")
        title = _text(titles[0]) if titles else ""
        subtitle = _text(subtitles[0]) if subtitles else ""
        rooms_match = _INT_RE.search(_text(rooms[0])) if rooms else None

        results.append(
            {
                "external_id": id_match.group(1),
                "url": url,
                "address": subtitle or title,
                "price": _extract_price(_text(prices[0]) if prices else ""),
                # ``_text`` joins the split surface text back to "135 m2".
                "m2": _extract_m2(_text(surfaces[0]) if surfaces else ""),
                "rooms": int(rooms_match.group()) if rooms_match else None,
                "floor": None,
                "description": title,
                "portal": "tecnocasa",
                "price_includes_garage": False,
                "garage_price": None,
                "certificado_energetico_present": None,
            }
        )
    return results


__all__ = ["parse_listings"]
