"""Portal registry, URL matcher, paginators, and lazy parser resolver."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


@dataclass(frozen=True)
class Portal:
    """Supported property portal configuration."""

    name: str
    domains: tuple[str, ...]
    parser: str
    paginate: Callable[[str, int], str]


def _paginate_query_page(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page_num)]
    parsed = parsed._replace(query=urlencode(qs, doseq=True))
    return urlunparse(parsed)


def _paginate_query_pagina(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["pagina"] = [str(page_num)]
    parsed = parsed._replace(query=urlencode(qs, doseq=True))
    return urlunparse(parsed)


def _paginate_slash_n(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    return f"{url.rstrip('/')}/{page_num}"


def _paginate_slash_n_slash(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    return f"{url.rstrip('/')}/{page_num}/"


def _paginate_tecnocasa(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    base = url.removesuffix(".html")
    return f"{base}.html/pag-{page_num}"


def _paginate_kleinanzeigen(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    import re
    if "/seite:" in url:
        return re.sub(r"/seite:\d+/", f"/seite:{page_num}/", url)
    m = re.search(r"(/c\d+l\d+)", url)
    if m:
        return url.replace(m.group(1), f"/seite:{page_num}" + m.group(1))
    return f"{url}?seite={page_num}"


def _paginate_green_acres(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["p_n"] = [str(page_num)]
    parsed = parsed._replace(query=urlencode(qs, doseq=True))
    return urlunparse(parsed)


def _paginate_bienici(url: str, page_num: int) -> str:
    if page_num == 1:
        return url
    import json
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filters_raw = qs.get("filters", ["{}"])[0]
    try:
        filters = json.loads(filters_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Invalid Bien'ici filters") from exc
    if not isinstance(filters, dict):
        raise ValueError("Invalid Bien'ici filters")
    page_size = filters.get("perPage") or filters.get("size") or 24
    try:
        page_size_int = int(page_size)
    except (ValueError, TypeError):
        page_size_int = 24
    filters["from"] = (page_num - 1) * page_size_int
    filters["page"] = page_num
    qs["filters"] = [json.dumps(filters, separators=(",", ":"))]
    parsed = parsed._replace(query=urlencode(qs, doseq=True))
    return urlunparse(parsed)


PORTALS: dict[str, Portal] = {
    "idealista": Portal(
        name="idealista",
        domains=("idealista.com",),
        parser="home_ops.scraper.parse",
        paginate=_paginate_query_pagina,
    ),
    "fotocasa": Portal(
        name="fotocasa",
        domains=("fotocasa.es",),
        parser="home_ops.scraper.fotocasa",
        paginate=_paginate_slash_n,
    ),
    "pisos": Portal(
        name="pisos",
        domains=("pisos.com",),
        parser="home_ops.scraper.pisos",
        paginate=_paginate_slash_n_slash,
    ),
    "tecnocasa": Portal(
        name="tecnocasa",
        domains=("tecnocasa.es",),
        parser="home_ops.scraper.tecnocasa",
        paginate=_paginate_tecnocasa,
    ),
    "habitaclia": Portal(
        name="habitaclia",
        domains=("habitaclia.com",),
        parser="home_ops.scraper.habitaclia",
        paginate=_paginate_slash_n,
    ),
    "njuskalo": Portal(
        name="njuskalo",
        domains=("njuskalo.hr",),
        parser="home_ops.scraper.njuskalo",
        paginate=_paginate_query_page,
    ),
    "kleinanzeigen": Portal(
        name="kleinanzeigen",
        domains=("kleinanzeigen.de",),
        parser="home_ops.scraper.kleinanzeigen",
        paginate=_paginate_kleinanzeigen,
    ),
    "green_acres": Portal(
        name="green_acres",
        domains=("green-acres.co.uk", "green-acres.it", "green-acres.pt", "green-acres.at", "green-acres.gr"),
        parser="home_ops.scraper.green_acres",
        paginate=_paginate_green_acres,
    ),
    "bienici": Portal(
        name="bienici",
        domains=("bienici.com",),
        parser="home_ops.scraper.bienici",
        paginate=_paginate_bienici,
    ),
}


def portal_for_url(url: str) -> Portal | None:
    """Return matching Portal object if URL scheme is http/https and domain matches."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None

    for portal in PORTALS.values():
        for d in portal.domains:
            if host == d or host.endswith("." + d):
                if portal.name == "green_acres" and parsed.scheme != "https":
                    return None
                return portal

    return None


def resolve_parser(portal: Portal | str) -> Any:
    """Lazily import parser module and return parse_listings function."""
    if isinstance(portal, str):
        if portal not in PORTALS:
            raise ValueError(f"Unknown portal: {portal}")
        p_obj = PORTALS[portal]
    else:
        p_obj = portal

    if p_obj.name == "idealista":
        lifecycle_mod = sys.modules.get("home_ops.scraper.lifecycle")
        if lifecycle_mod is not None and hasattr(lifecycle_mod, "parse_listings"):
            return lifecycle_mod.parse_listings

    mod = importlib.import_module(p_obj.parser)
    return mod.parse_listings
