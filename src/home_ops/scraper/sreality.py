"""Sreality (Czechia) search-result parser."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Selector

_ALLOWED_HOSTS = {"sreality.cz", "www.sreality.cz"}
_BASE_URL = "https://www.sreality.cz"


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Sreality search result HTML (NEXT_DATA JSON or DOM) into listing dictionary."""
    if not html or not html.strip():
        return []

    page = Selector(html)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Strategy 1: NEXT_DATA JSON
    script = page.css("script#__NEXT_DATA__::text").get()
    if script:
        try:
            data = json.loads(script)
            queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
            for q in queries:
                if q.get("queryKey", []) and q["queryKey"][0] == "estatesSearch":
                    items = q.get("state", {}).get("data", {}).get("results", [])
                    for item in items:
                        ext_id = str(item.get("id") or "")
                        if not ext_id:
                            continue

                        price = item.get("priceCzk") or item.get("priceSummaryCzk")
                        price = int(price) if price else None

                        name = item.get("name") or ""
                        m2 = None
                        m2_match = re.search(r"(\d+)\s*m²", name)
                        if m2_match:
                            m2 = int(m2_match.group(1))

                        rooms = None
                        sub_cat = item.get("categorySubCb", {}).get("name", "")
                        room_match = re.search(r"(\d+)", sub_cat)
                        if room_match:
                            rooms = int(room_match.group(1))

                        loc = item.get("locality", {})
                        city = loc.get("city") or "Brno"
                        street = loc.get("street") or ""
                        part = loc.get("cityPart") or loc.get("quarter") or ""
                        addr_parts = [p for p in [street, part, city] if p]
                        address = ", ".join(addr_parts) if addr_parts else city

                        url = f"https://www.sreality.cz/detail/prodej/byt/{ext_id}"
                        if url in seen:
                            continue
                        seen.add(url)

                        out.append({
                            "external_id": ext_id,
                            "url": url,
                            "address": address,
                            "price": price,
                            "m2": m2,
                            "rooms": rooms,
                            "floor": None,
                            "description": name,
                            "portal": "sreality",
                            "price_includes_garage": False,
                            "garage_price": None,
                            "certificado_energetico_present": None,
                        })
        except Exception:
            pass

    if out:
        return out

    # Strategy 2: DOM fallback
    for link in page.css("a[href*='/detail/']"):
        href = link.attrib.get("href", "").strip()
        full_url = urljoin(_BASE_URL, href)
        parsed = urlparse(full_url)
        if (parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or
                not parsed.path.startswith("/detail/")):
            continue
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if url in seen:
            continue
        seen.add(url)

        ext_id = parsed.path.rstrip("/").split("/")[-1]

        node = link
        for _ in range(5):
            parent = getattr(node, "parent", None)
            if parent is None:
                break
            text = " ".join(t.strip() for t in parent.css("::text").getall() if t.strip())
            if "Kč" in text or "m²" in text:
                node = parent
                break
        text = " ".join(t.strip() for t in node.css("::text").getall() if t.strip())

        price = None
        pm = re.search(r"(\d[\d\s\xa0]*)\s*Kč", text)
        if pm:
            raw_p = re.sub(r"[^\d]", "", pm.group(1))
            if raw_p:
                price = int(raw_p)

        m2 = None
        mm = re.search(r"(\d+)\s*m²", text)
        if mm:
            m2 = int(mm.group(1))

        rooms = None
        rm = re.search(r"(\d+)(?:\+\d+|\+kk|\s*pokoj|\s*byty)", text, re.IGNORECASE)
        if rm:
            rooms = int(rm.group(1))

        addr_match = re.search(r"m²\s+(.+?)(?:\s+\d[\d\s\xa0]*\s*Kč|$)", text)
        address = addr_match.group(1).strip() if addr_match else text[:80]

        out.append({
            "external_id": ext_id,
            "url": url,
            "address": address,
            "price": price,
            "m2": m2,
            "rooms": rooms,
            "floor": None,
            "description": text[:300],
            "portal": "sreality",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })

    return out


__all__ = ["parse_listings"]
