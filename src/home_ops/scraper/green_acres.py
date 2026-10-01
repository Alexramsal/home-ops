"""Green-Acres public HTML result parser."""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any
from urllib.parse import urlparse

from scrapling.parser import Selector

from home_ops.scraper.parse import _extract_m2

_ALLOWED_DOMAINS = {f"green-acres.{suffix}" for suffix in ("co.uk", "it", "pt", "at", "gr")}
_ALLOWED_HOSTS = _ALLOWED_DOMAINS | {f"www.{domain}" for domain in _ALLOWED_DOMAINS}
_PRICE_RE = re.compile(r"[\d.,\s]+")
_ROOMS_RE = re.compile(r"(\d+)\s+rooms?", re.IGNORECASE)


def _text(card: Selector, selector: str) -> str:
    return " ".join(t.strip() for t in card.css(selector + " ::text").getall() if t.strip())


def _price(value: str) -> float | None:
    match = _PRICE_RE.search(value.replace("\u00a0", " "))
    if not match:
        return None
    raw = re.sub(r"\s+", "", match.group())
    separators = [char for char in ".," if char in raw]
    decimal = max(separators, key=raw.rfind) if separators and len(raw) - raw.rfind(max(separators, key=raw.rfind)) - 1 in (1, 2) else None
    for separator in separators:
        raw = raw.replace(separator, "." if separator == decimal else "")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_listings(html: str) -> list[dict[str, Any]]:
    if not html.strip():
        return []
    results: list[dict[str, Any]] = []
    for card in Selector(html).css("div.announce-card[data-advertid][data-o]"):
        try:
            url = base64.b64decode(card.attrib["data-o"], validate=True).decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError, binascii.Error):
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            continue
        characteristics = _text(card, ".characteristics")
        rooms_match = _ROOMS_RE.search(characteristics)
        results.append({
            "external_id": card.attrib["data-advertid"],
            "url": url,
            "address": _text(card, ".announce-localisation"),
            "price": _price(_text(card, ".info-price-container")),
            "m2": _extract_m2(characteristics),
            "rooms": int(rooms_match.group(1)) if rooms_match else None,
            "floor": None,
            "description": _text(card, ".description-details"),
            "portal": "green_acres",
            "price_includes_garage": False,
            "garage_price": None,
            "certificado_energetico_present": None,
        })
    return results


__all__ = ["parse_listings"]
