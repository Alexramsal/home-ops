"""Bien'ici search-result JSON parser."""

from __future__ import annotations

import json
from typing import Any

_PORTAL = "bienici"
_BASE_LISTING_URL = "https://www.bienici.com/annonce"


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Bien'ici search-result direct JSON response."""
    if not html or not html.strip():
        return []

    try:
        data = json.loads(html)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, dict):
        return []

    ads = data.get("realEstateAds")
    if not isinstance(ads, list):
        return []

    results: list[dict[str, Any]] = []
    for ad in ads:
        if not isinstance(ad, dict):
            continue

        raw_id = ad.get("id")
        external_id = str(raw_id) if raw_id is not None else None
        url = f"{_BASE_LISTING_URL}/{external_id}" if external_id else ""

        city = ad.get("city")
        postal_code = ad.get("postalCode")
        description = ad.get("description") if isinstance(ad.get("description"), str) else ""

        addr_parts: list[str] = []
        if isinstance(city, str) and city.strip():
            addr_parts.append(city.strip())
        if isinstance(postal_code, (str, int)) and str(postal_code).strip():
            addr_parts.append(str(postal_code).strip())
        address = ", ".join(addr_parts)

        price = ad.get("price")
        if not isinstance(price, (int, float)):
            price = None

        m2 = ad.get("surfaceArea")
        if not isinstance(m2, (int, float)):
            m2 = None

        rooms = ad.get("roomsQuantity")
        if not isinstance(rooms, int):
            rooms = None

        floor_val = ad.get("floor")
        floor = str(floor_val) if floor_val is not None else None

        results.append(
            {
                "external_id": external_id,
                "url": url,
                "address": address,
                "price": price,
                "m2": m2,
                "rooms": rooms,
                "floor": floor,
                "description": description,
                "portal": _PORTAL,
                "price_includes_garage": False,
                "garage_price": None,
                "certificado_energetico_present": None,
            }
        )

    return results


__all__ = ["parse_listings"]
