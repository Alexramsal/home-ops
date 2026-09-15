"""Pisos.com search-result HTML parser.

Selectors verified against the live Cádiz results page on 2026-09-15.
"""

from __future__ import annotations

from typing import Any

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2, _extract_price, _extract_rooms


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse organic Pisos.com cards into the shared listing contract."""
    if not html or not html.strip():
        return []
    page = Selector(html)
    results: list[dict[str, Any]] = []
    for card in page.css("div.ad-preview"):
        link = card.css("a.ad-preview__title")
        if not link:
            continue
        href = link[0].css("::attr(href)").get("")
        title = link[0].css("::text").get("").strip()
        zone_nodes = card.css("p.ad-preview__subtitle")
        zone = zone_nodes[0].css("::text").get("").strip() if zone_nodes else ""
        price_nodes = card.css("span.ad-preview__price")
        price_text = price_nodes[0].css("::text").get("") if price_nodes else ""
        chars = [n.css("::text").get("").strip() for n in card.css("p.ad-preview__char")]
        external_id = card.attrib.get("id", "").split(".")[0] or None
        results.append(
            {
                "external_id": external_id,
                "url": href,
                "address": f"{title}, {zone}" if zone else title,
                "price": _extract_price(price_text),
                "m2": next((_extract_m2(x) for x in chars if _extract_m2(x)), None),
                "rooms": next((_extract_rooms(x) for x in chars if _extract_rooms(x)), None),
                "floor": None,
                "description": "",
                "portal": "pisos",
                "price_includes_garage": False,
                "garage_price": None,
                "certificado_energetico_present": None,
            }
        )
    return results


__all__ = ["parse_listings"]
