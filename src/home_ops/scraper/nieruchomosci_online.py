"""Nieruchomosci-online (Poland) search-result parser."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Selector

_BASE_URL = "https://krakow.nieruchomosci-online.pl"


def _is_allowed_host(host: str) -> bool:
    host = host.lower()
    return host == "nieruchomosci-online.pl" or host.endswith(".nieruchomosci-online.pl")


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Nieruchomosci-online HTML search results into shared listing dictionary."""
    if not html or not html.strip():
        return []

    page = Selector(html)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tile in page.css("div.tile, div.box-tile, div.offer-item, div.item"):
        data_id = tile.attrib.get("data-id")
        links = tile.css("a[href]")
        url = None
        for a in links:
            href = a.attrib.get("href", "").strip()
            if not href or href == "#":
                continue
            full_url = urljoin(_BASE_URL, href)
            parsed = urlparse(full_url)
            if (parsed.scheme == "https" and _is_allowed_host(parsed.hostname or "") and
                    parsed.path.endswith(".html")):
                url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
                break

        if not url or url in seen:
            continue
        seen.add(url)

        text = " ".join(t.strip() for t in tile.css("::text").getall() if t.strip())

        # price (PLN)
        price = None
        pm = re.search(r"(?:od\s*)?(\d[\d\s\xa0]{2,})\s*(?:zł|PLN)", text, re.IGNORECASE)
        if pm:
            raw_p = re.sub(r"[^\d]", "", pm.group(1))
            if raw_p:
                price = int(raw_p)

        # m2
        m2 = None
        mm = re.search(r"(\d+)\s*(?:-\s*\d+\s*)?(?:m²|m2)", text, re.IGNORECASE)
        if mm:
            m2 = int(mm.group(1))

        # rooms
        rooms = None
        rm = re.search(r"(\d+)\s*(?:pokoje|pokój|pokojowe|pok\b)", text, re.IGNORECASE)
        if rm:
            rooms = int(rm.group(1))

        # address
        title_el = tile.css("h2 a::text, .name a::text, h2::text").get()
        prov_els = tile.css(".province span::text, .province::text").getall()
        prov_clean = ", ".join(p.strip() for p in prov_els if p.strip())
        if title_el and prov_clean:
            address = f"{title_el.strip()}, {prov_clean}"
        else:
            address = prov_clean or (title_el.strip() if title_el else "Kraków")

        parsed_path = urlparse(url).path
        ext_id = data_id or (re.search(r"/([^/]+)\.html$", parsed_path) or [None, parsed_path])[1]

        out.append({
            "external_id": str(ext_id),
            "url": url,
            "address": address,
            "price": price,
            "m2": m2,
            "rooms": rooms,
            "floor": None,
            "description": text[:300],
            "portal": "nieruchomosci_online",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })

    return out


__all__ = ["parse_listings"]
