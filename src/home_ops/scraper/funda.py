"""Funda search-result parser."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2

_BASE = "https://www.funda.nl"
_ALLOWED_HOSTS = {"funda.nl", "www.funda.nl"}
_PRICE_RE = re.compile(r"€\s*((?:\d{1,3}(?:\.\d{3})+|\d+))\b")
_ROOMS_RE = re.compile(r"(?:^|\s)(\d+)\s*(?:kamers?|rooms?|slaapkamers?)(?:\s|$)", re.IGNORECASE)
_FEATURE_ROOMS_RE = re.compile(r"(?:m²|m2)\s+(?:[\d.]+\s*m²\s+)?(\d+)\s+[A-G]\b")


def parse_listings(html: str) -> list[dict[str, Any]]:
    page = Selector(html)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in page.css('a[href*="/detail/koop/"]'):
        href = link.attrib.get("href", "").strip()
        url = urljoin(_BASE, href)
        parsed = urlparse(url)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or
                not parsed.path.startswith("/detail/koop/") or url in seen):
            continue
        seen.add(url)
        node = link
        for _ in range(6):
            parent = getattr(node, "parent", None)
            if parent is None:
                break
            text = " ".join(parent.css("::text").getall())
            if "m²" in text or "m2" in text:
                node = parent
                break
            node = parent
        text = " ".join(node.css("::text").getall()).strip()
        price_match = _PRICE_RE.search(text)
        price = int(price_match.group(1).replace(".", "").replace(" ", "")) if price_match else None
        m2 = _extract_m2(text)
        rooms_match = _ROOMS_RE.search(text) or _FEATURE_ROOMS_RE.search(text)
        rooms = int(rooms_match.group(1)) if rooms_match else None
        title = " ".join(link.css("::text").getall()).strip() or text[:120]
        ident = (re.search(r"/(\d+)/?$", parsed.path) or [None, parsed.path])[1]
        out.append({
            "external_id": ident,
            "url": url,
            "address": title,
            "price": int(price) if price is not None else None,
            "m2": m2,
            "rooms": rooms,
            "floor": None,
            "description": text,
            "portal": "funda",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })
    return out


__all__ = ["parse_listings"]
