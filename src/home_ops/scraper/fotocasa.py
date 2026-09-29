"""Fotocasa search-result parser.

Fotocasa is a React SPA: the listing cards are NOT in the DOM — they live in
a JSON blob inside ``<script type="application/json">`` (the app's initial
state). The important path (verified with ordinary Scrapling fetch, Madrid
capital URL, HTTP 200, 2026-09-29) is::

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
    if not isinstance(data, dict):
        return []
    initial_search = data.get("initialSearch")
    if not isinstance(initial_search, dict):
        return []
    result = initial_search.get("result")
    if not isinstance(result, dict):
        return []
    results_v2 = result.get("resultsV2")
    if not isinstance(results_v2, dict):
        return []
    items = results_v2.get("items")
    return items if isinstance(items, list) else []


def _item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Map one fotocasa item to the shared raw-listing dict contract."""
    raw_price = item.get("price")
    price: int | float | None = None
    if isinstance(raw_price, dict):
        p = raw_price.get("amount")
        if isinstance(p, (int, float)):
            price = p
    elif isinstance(raw_price, (int, float)):
        price = raw_price

    raw_features = item.get("features")
    features: dict[str, Any] = {}
    if isinstance(raw_features, dict):
        features = raw_features
    elif isinstance(raw_features, list):
        for entry in raw_features:
            if isinstance(entry, dict) and isinstance(entry.get("key"), str):
                features[entry["key"]] = entry.get("value")

    raw_location = item.get("location")
    raw_address = item.get("address")
    address = ""

    if isinstance(raw_address, dict):
        ubication = raw_address.get("ubication")
        locality = raw_address.get("locality")
        loc_str = raw_location if isinstance(raw_location, str) else raw_address.get("location")

        if isinstance(ubication, str) and ubication:
            address = ubication
        elif isinstance(loc_str, str) and loc_str:
            address = loc_str
        elif isinstance(locality, str) and locality:
            address = locality
    elif isinstance(raw_address, str) and raw_address:
        address = raw_address
    elif isinstance(raw_location, dict):
        addr_part = raw_location.get("address")
        zone_part = raw_location.get("zone")
        if isinstance(addr_part, str) and isinstance(zone_part, str) and addr_part and zone_part:
            address = f"{addr_part}, {zone_part}"
        elif isinstance(addr_part, str):
            address = addr_part
        elif isinstance(zone_part, str):
            address = zone_part
    elif isinstance(raw_location, str):
        address = raw_location

    detail_url = item.get("detailUrl") if isinstance(item.get("detailUrl"), str) else ""

    raw_id_val = item.get("id")
    raw_id = str(raw_id_val) if raw_id_val is not None else ""
    external_id = raw_id.split("_")[-1] if "_" in raw_id else raw_id

    floor_val = features.get("floor") if isinstance(features, dict) else None

    return {
        "external_id": external_id or None,
        "url": detail_url,
        "address": address,
        "price": price,
        "m2": features.get("surface") if isinstance(features, dict) else None,
        "rooms": features.get("rooms") if isinstance(features, dict) else None,
        "floor": str(floor_val) if floor_val is not None else None,
        "description": item.get("description") if isinstance(item.get("description"), str) else "",
        "portal": _PORTAL,
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
