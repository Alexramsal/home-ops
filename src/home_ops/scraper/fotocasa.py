"""Fotocasa search-result parser.

Fotocasa is a React SPA: the listing cards are NOT in the DOM — they live in
a JSON blob inside ``<script type="application/json">`` (the app's initial
state). The important path (verified against a live capture of
``cadiz-provincia``, 2026-09-15) is::

    initialSearch.result.resultsV2.items -> list[dict]

Each item has the fields we map below. Everything else on the page
(footer links, SEO blocks) is ignored.

Public interface (mirrors ``home_ops.scraper.parse``):
    parse_listings(html: str) -> list[dict[str, Any]]
"""

from __future__ import annotations

import json
import re
from typing import Any

_PORTAL = "fotocasa"
_JSON_BLOCK_RE = re.compile(
    r"<script[^>]*type=\"application/json\"[^>]*>(.*?)</script>", re.S
)

# Property subtypes fotocasa -> our classification (rooms/m2 are in features)
# Kept minimal: we only need price, surface, rooms, floor, address, url.
_SUBTYPE_LABELS = {
    "SINGLE_FAMILY_SEMI_DETACHED": "adosado",
    "SINGLE_FAMILY_DETACHED": "chalet",
    "FLAT": "piso",
    "DUPLEX": "dúplex",
    "PENTHOUSE": "ático",
}


def _extract_items(html: str) -> list[dict[str, Any]]:
    """Pull the listing items from the embedded application/json state."""
    if not html or not html.strip():
        return []
    m = _JSON_BLOCK_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    items = data.get("initialSearch", {}).get("result", {}).get("resultsV2", {}).get(
        "items", []
    )
    return items if isinstance(items, list) else []


def _item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Map one fotocasa item to the shared raw-listing dict contract."""
    price = item.get("price") or {}
    features = item.get("features") or {}
    location = item.get("location") or {}
    detail_url = item.get("detailUrl") or ""
    # external_id: fotocasa ids look like "1_187417980"
    raw_id = str(item.get("id") or "")
    external_id = raw_id.split("_")[-1] if "_" in raw_id else raw_id

    address = location.get("address") or ""
    zone = location.get("zone") or ""
    if address and zone:
        address = f"{address}, {zone}"

    return {
        "external_id": external_id or None,
        "url": detail_url,
        "address": address,
        "price": price.get("amount"),
        "m2": features.get("surface"),
        "rooms": features.get("rooms"),
        "floor": str(features["floor"]) if features.get("floor") is not None else None,
        "description": item.get("description", ""),
        "portal": _PORTAL,
        # fotocasa has no garage-price concept in search results; the detail
        # page would, but we don't fetch it separately yet.
        "price_includes_garage": False,
        "garage_price": None,
        "certificado_energetico_present": None,
        "property_subtype": _SUBTYPE_LABELS.get(
            str(item.get("propertySubtype") or "")
        ),
    }


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Fotocasa search-result HTML into raw listing dicts."""
    items = _extract_items(html)
    return [_item_to_dict(it) for it in items if isinstance(it, dict)]
