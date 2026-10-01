"""Mäklarhuset search-result parser."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from scrapling.parser import Selector

_BASE_URL = "https://www.maklarhuset.se"
_ALLOWED_HOSTS = {"maklarhuset.se", "www.maklarhuset.se"}


def _number(value: str) -> float | None:
    raw = value.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Mäklarhuset result cards into the shared listing contract."""
    if not html.strip():
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in Selector(html).css(".mh-object"):
        links = card.css('a[href^="/bostad/"]')
        link = next((a for a in links if "kr" in " ".join(a.css("::text").getall())), links[-1] if links else None)
        if link is None:
            continue
        url = urljoin(_BASE_URL, link.attrib["href"])
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or url in seen:
            continue
        seen.add(url)
        text = " ".join(t.strip() for t in card.css("::text").getall() if t.strip())
        price_match = re.search(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})+)\s*kr", text, re.IGNORECASE)
        rooms_match = re.search(r"(\d+(?:[,.]\d+)?)\s*Rum", text, re.IGNORECASE)
        area_match = re.search(r"(?:ca\s*)?(\d+(?:[,.]\d+)?)\s*kvm", text, re.IGNORECASE)
        address = " ".join(t.strip() for t in link.css("::text").getall() if t.strip())
        price = _number(price_match.group(1)) if price_match else None
        rooms = _number(rooms_match.group(1)) if rooms_match else None
        results.append({
            "external_id": parsed.path.rstrip("/").split("/")[-1],
            "url": url,
            "address": address,
            "price": int(price) if price is not None else None,
            "m2": _number(area_match.group(1)) if area_match else None,
            "rooms": int(rooms) if rooms is not None else None,
            "floor": None,
            "description": text,
            "portal": "maklarhuset",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })
    return results


__all__ = ["parse_listings"]
