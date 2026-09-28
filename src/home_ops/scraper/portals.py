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
