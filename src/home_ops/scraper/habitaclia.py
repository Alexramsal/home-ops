"""Habitaclia embedded-state search-result parser."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

_INITIAL_PROPS_RE = re.compile(r"window\.__INITIAL_PROPS__\s*=\s*JSON\.parse\(")
_BASE_URL = "https://www.habitaclia.com"


def _extract_items(html: str) -> list[dict[str, Any]]:
    match = _INITIAL_PROPS_RE.search(html)
    if not match:
        return []
    try:
        encoded, _ = json.JSONDecoder().raw_decode(html, match.end())
        data = json.loads(encoded)
        items = data["initialSearchResultsPage"]["initialSearchContext"]["results"]["items"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return []
    return items if isinstance(items, list) else []


def _item_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("summary") or {}
    location = summary.get("location") or {}
    prop = item.get("property") or {}
    features = prop.get("features") or {}
    transaction = item.get("transaction") or {}
    price = transaction.get("price") or {}
    urls = item.get("urls") or {}
    path = urls.get("canonical") or item.get("navigationUrl") or ""
    municipality = location.get("municipality") or ""
    district = location.get("district") or ""
    certificate = prop.get("energyEfficiencyCertificate") or {}
    certificate_status = certificate.get("status")

    return {
        "external_id": str(item.get("legacyNumericId")) if item.get("legacyNumericId") else None,
        "url": urljoin(_BASE_URL, path),
        "address": ", ".join(part for part in (municipality, district) if part),
        "price": price.get("amount"),
        "m2": prop.get("builtSurface"),
        "rooms": prop.get("rooms"),
        "floor": prop.get("floor"),
        "description": summary.get("description") or summary.get("title") or "",
        "portal": "habitaclia",
        "price_includes_garage": "PRIVATE_PARKING" in (features.get("has") or []),
        "garage_price": None,
        "certificado_energetico_present": (
            certificate_status in {"AVAILABLE", "EXEMPT"} if certificate_status else None
        ),
    }


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Decode Habitaclia's JSON.parse payload into the shared listing contract."""
    if not html or not html.strip():
        return []
    return [_item_to_dict(item) for item in _extract_items(html) if isinstance(item, dict)]


__all__ = ["parse_listings"]
