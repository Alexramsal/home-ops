"""ERA Belgium search-result parser."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2

_PRICE_RE = re.compile(r"€\s*((?:\d{1,3}(?:\.\d{3})+|\d{1,3}(?:\s+\d{3})+|\d+))\b", re.IGNORECASE)
_BED_RE = re.compile(r"(\d+)\s*(?:bedrooms?|bdrm\.?)", re.IGNORECASE)

_BASE_URL = "https://www.era.be"
_ALLOWED_HOSTS = {"era.be", "www.era.be"}


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse ERA result links into the shared listing contract."""
    if not html.strip():
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in Selector(html).css('a[href*="/for-sale/"]'):
        href = link.attrib.get("href", "").strip()
        url = urljoin(_BASE_URL, href)
        parsed = urlparse(url)
        segments = [part for part in parsed.path.split("/") if part]
        if (parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or
                len(segments) < 5 or url in seen):
            continue
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        seen.add(url)
        node = link
        for _ in range(6):
            parent = getattr(node, "parent", None)
            if parent is None:
                break
            node = parent
            if len(" ".join(node.css("::text").getall()).strip()) > 30:
                break
        text = " ".join(t.strip() for t in node.css("::text").getall() if t.strip())
        address = text if text and text != "View property" else " ".join(link.css("::text").getall()).strip()
        price_match = _PRICE_RE.search(text)
        bed_match = _BED_RE.search(text)
        results.append({
            "external_id": parsed.path.rstrip("/").split("/")[-1],
            "url": url,
            "address": address,
            "price": int(price_match.group(1).replace(".", "").replace(" ", "")) if price_match else None,
            "m2": _extract_m2(text),
            "rooms": int(bed_match.group(1)) if bed_match else None,
            "floor": None,
            "description": text,
            "portal": "era",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })
    return results


__all__ = ["parse_listings"]
