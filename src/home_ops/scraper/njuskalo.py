"""Njuškalo (Croatia) search-result HTML parser."""

from __future__ import annotations

import re
from typing import Any

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2, _extract_price, _extract_rooms

_ID_RE = re.compile(r"(\d+)(?:[?#]|/|$)")

_ROOM_WORDS = {
    "jednosoban": 1,
    "jednosobni": 1,
    "dvosoban": 2,
    "dvosobni": 2,
    "trosoban": 3,
    "trosobni": 3,
    "četverosoban": 4,
    "cetverosoban": 4,
    "četverosobni": 4,
    "cetverosobni": 4,
}
_ROOM_RE = re.compile(r"(\d+)\s*[-–]?\s*(?:sobe|soba|soban|sobni)", re.IGNORECASE)


def _extract_m2_hr(text: str) -> float | None:
    text_clean = text.replace(",", ".")
    return _extract_m2(text_clean)


def _extract_rooms_hr(text: str) -> int | None:
    low = text.lower()
    for word, count in _ROOM_WORDS.items():
        if word in low:
            return count
    match = _ROOM_RE.search(text)
    if match:
        return int(match.group(1))
    return _extract_rooms(text)


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Njuškalo search result cards into the shared listing contract."""
    if not html or not html.strip():
        return []

    page = Selector(html)
    results: list[dict[str, Any]] = []

    for card in page.css("li.EntityList-item"):
        classes = card.attrib.get("class", "").split()
        if "EntityList-item--banner" in classes:
            continue

        links = card.css("a.link") or card.css("h3.entity-title a") or card.css("a")
        if not links:
            continue

        link = links[0]
        href = (link.attrib.get("href") or "").strip()
        if not href:
            continue

        id_match = _ID_RE.search(href)
        if not id_match:
            continue
        external_id = id_match.group(1)

        title_text = link.css("::text").get("").strip()
        if not title_text:
            continue

        main_desc = card.css(".entity-description-main")
        desc_text = main_desc[0].css("::text").get("").strip() if main_desc else ""
        if not desc_text:
            desc_nodes = card.css(".entity-description")
            desc_text = desc_nodes[0].css("::text").get("").strip() if desc_nodes else ""

        price_nodes = card.css(".entity-prices .price")
        price_text = price_nodes[0].css("::text").get("") if price_nodes else ""
        raw_price = _extract_price(price_text)
        price = int(raw_price) if raw_price is not None else None

        combined_text = f"{title_text} {desc_text}"
        m2 = _extract_m2_hr(combined_text)
        rooms = _extract_rooms_hr(combined_text)

        results.append(
            {
                "external_id": external_id,
                "url": href,
                "address": title_text,
                "price": price,
                "m2": m2,
                "rooms": rooms,
                "floor": None,
                "description": desc_text,
                "portal": "njuskalo",
                "price_includes_garage": False,
                "garage_price": None,
                "certificado_energetico_present": None,
            }
        )

    return results


__all__ = ["parse_listings"]
