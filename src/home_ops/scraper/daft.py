"""Daft.ie (Ireland) search-result parser."""
from __future__ import annotations

import contextlib
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from scrapling.parser import Selector

_ALLOWED_HOSTS = {"daft.ie", "www.daft.ie"}
_BASE_URL = "https://www.daft.ie"


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Daft.ie search result HTML (NEXT_DATA JSON or DOM) into listing dictionary."""
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
            listings = data.get("props", {}).get("pageProps", {}).get("listings", [])
            for l_item in listings:
                listing = l_item.get("listing", {})
                ext_id = str(listing.get("id") or "")
                if not ext_id:
                    continue

                seo_path = listing.get("seoFriendlyPath") or f"/for-sale/{ext_id}"
                full_url = urljoin(_BASE_URL, seo_path)
                parsed = urlparse(full_url)
                if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
                    continue
                url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

                if url in seen:
                    continue
                seen.add(url)

                address = listing.get("title") or listing.get("seoTitle") or "Cork"

                price_raw = listing.get("price") or ""
                price = None
                pm = re.search(r"€\s*([\d,]+)", str(price_raw))
                if pm:
                    price = int(pm.group(1).replace(",", ""))
                elif isinstance(price_raw, (int, float)):
                    price = int(price_raw)

                m2 = None
                floor_area = listing.get("floorArea") or {}
                if isinstance(floor_area, dict) and floor_area.get("value"):
                    with contextlib.suppress(ValueError, TypeError):
                        m2 = int(float(floor_area["value"]))
                if m2 is None:
                    mm = re.search(r"(\d+)\s*(?:m²|m2|sq\.?\s*m)", str(listing), re.IGNORECASE)
                    if mm:
                        m2 = int(mm.group(1))

                rooms = None
                num_beds = listing.get("numBedrooms") or ""
                rm = re.search(r"(\d+)", str(num_beds))
                if rm:
                    rooms = int(rm.group(1))

                out.append({
                    "external_id": ext_id,
                    "url": url,
                    "address": address,
                    "price": price,
                    "m2": m2,
                    "rooms": rooms,
                    "floor": None,
                    "description": address,
                    "portal": "daft",
                    "price_includes_garage": False,
                    "garage_price": None,
                    "certificado_energetico_present": None,
                })
        except Exception:
            pass

    if out:
        return out

    # Strategy 2: DOM fallback
    for link in page.css("a[href*='/for-sale/']"):
        href = link.attrib.get("href", "").strip()
        full_url = urljoin(_BASE_URL, href)
        parsed = urlparse(full_url)
        if (parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or
                not parsed.path.startswith("/for-sale/")):
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
            if "€" in text or "Bed" in text or "Bath" in text:
                node = parent
                break
        text = " ".join(t.strip() for t in node.css("::text").getall() if t.strip())

        price = None
        pm = re.search(r"€\s*([\d,]+)", text)
        if pm:
            raw_p = pm.group(1).replace(",", "")
            if raw_p:
                price = int(raw_p)

        m2 = None
        mm = re.search(r"(\d+)\s*(?:m²|m2|sq\.?\s*m)", text, re.IGNORECASE)
        if mm:
            m2 = int(mm.group(1))

        rooms = None
        rm = re.search(r"(\d+)\s*Bed", text, re.IGNORECASE)
        if rm:
            rooms = int(rm.group(1))

        out.append({
            "external_id": ext_id,
            "url": url,
            "address": text[:100],
            "price": price,
            "m2": m2,
            "rooms": rooms,
            "floor": None,
            "description": text[:300],
            "portal": "daft",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })

    return out


__all__ = ["parse_listings"]
