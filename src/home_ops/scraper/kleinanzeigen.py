"""Kleinanzeigen (Germany) search-result HTML parser."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2, _extract_price, _extract_rooms

_BASE_URL = "https://www.kleinanzeigen.de"


def _extract_m2_de(text: str) -> float | None:
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*m[²2]", text, re.IGNORECASE)
    if m:
        try:
            val_str = m.group(1).replace(".", "").replace(",", ".")
            return float(val_str)
        except ValueError:
            pass
    return _extract_m2(text)


def _extract_rooms_de(text: str) -> int | None:
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:-?\s*Zimmer|-?\s*Zi\.)", text, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            return int(val)
        except ValueError:
            pass
    return _extract_rooms(text)


def parse_listings(html: str) -> list[dict[str, Any]]:
    """Parse Kleinanzeigen (Germany) search result cards into the shared contract."""
    if not html or not html.strip():
        return []

    page = Selector(html)
    results: list[dict[str, Any]] = []

    raw_headings = list(page.xpath("//h3//a[contains(@href, '/s-anzeige/')]"))
    if not raw_headings:
        raw_headings = [a for a in page.css("a") if "/s-anzeige/" in (a.attrib.get("href") or "")]

    seen_ids: set[str] = set()

    for a in raw_headings:
        href = a.attrib.get("href", "").strip()
        if not href or "/s-anzeige/" not in href:
            continue

        full_url = urljoin(_BASE_URL, href)
        m_id = re.search(r"(\d+)-\d+-\d+$", href)
        if not m_id:
            m_id = re.search(r"/(\d+)(?:[?#]|$)", href)
        external_id = m_id.group(1) if m_id else None

        if external_id and external_id in seen_ids:
            continue
        if external_id:
            seen_ids.add(external_id)

        title_text = " ".join(a.css("::text").getall()).strip()
        if not title_text:
            continue

        parents = a.xpath("./ancestor::article | ./ancestor::li | ./ancestor::div[contains(@class, 'card') or contains(@class, 'ad')]")
        node = parents[0] if parents else a
        card_text = " ".join(node.css("::text").getall())

        price_m = re.search(r"([\d\.]+(?:,\d+)?\s*€|VB)", card_text)
        price_str = price_m.group(1) if price_m else None
        price = _extract_price(price_str) if price_str else None

        combined_text = f"{title_text} {card_text}"
        m2 = _extract_m2_de(combined_text)
        rooms = _extract_rooms_de(combined_text)

        results.append(
            {
                "external_id": external_id,
                "url": full_url,
                "address": title_text,
                "price": price,
                "m2": m2,
                "rooms": rooms,
                "floor": None,
                "description": title_text,
                "portal": "kleinanzeigen",
                "price_includes_garage": False,
                "garage_price": None,
                "certificado_energetico_present": None,
            }
        )

    return results


__all__ = ["parse_listings"]
