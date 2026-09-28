"""Tests for scraper portals registry, URL domain matching, and pagination."""


import pytest

from home_ops.scraper.portals import (
    PORTALS,
    Portal,
    portal_for_url,
    resolve_parser,
)


def test_portals_registry_contains_five_portals() -> None:
    expected_names = {"idealista", "fotocasa", "pisos", "tecnocasa", "habitaclia"}
    assert set(PORTALS.keys()) == expected_names
    for p in PORTALS.values():
        assert isinstance(p, Portal)
        assert len(p.domains) >= 1


@pytest.mark.parametrize(
    ("url", "expected_portal"),
    [
        ("https://www.idealista.com/venta-viviendas/cadiz/", "idealista"),
        ("http://idealista.com/venta-viviendas/cadiz/", "idealista"),
        ("https://www.fotocasa.es/es/comprar/viviendas/", "fotocasa"),
        ("https://fotocasa.es/es/comprar/", "fotocasa"),
        ("https://www.pisos.com/venta/pisos-cadiz/", "pisos"),
        ("https://pisos.com/venta/", "pisos"),
        ("https://www.tecnocasa.es/venta/piso/", "tecnocasa"),
        ("https://tecnocasa.es/venta/", "tecnocasa"),
        ("https://www.habitaclia.com/comprar/viviendas/", "habitaclia"),
        ("https://habitaclia.com/comprar/", "habitaclia"),
    ],
)
def test_portal_for_url_valid_domains(url: str, expected_portal: str) -> None:
    portal = portal_for_url(url)
    assert portal is not None
    assert portal.name == expected_portal


@pytest.mark.parametrize(
    "url",
    [
        "https://idealista.com.evil.test/search",
        "https://fotocasa.es.fake.domain/page",
        "https://pisos.com.attacker.com/pisos/",
        "https://tecnocasa.es.spoof.net/",
        "https://habitaclia.com.phishing.org/",
        "ftp://www.idealista.com/search",
        "file:///tmp/idealista.com",
        "javascript:alert(1)",
        "https://unknown-portal.es/viviendas/",
    ],
)
def test_portal_for_url_rejects_impostors_and_invalid_schemes(url: str) -> None:
    assert portal_for_url(url) is None


@pytest.mark.parametrize(
    ("portal_name", "url", "page_num", "expected_url"),
    [
        ("idealista", "https://www.idealista.com/search", 1, "https://www.idealista.com/search"),
        ("idealista", "https://www.idealista.com/search", 2, "https://www.idealista.com/search?pagina=2"),
        ("idealista", "https://www.idealista.com/search?a=1", 2, "https://www.idealista.com/search?a=1&pagina=2"),
        ("fotocasa", "https://www.fotocasa.es/es/comprar/l", 1, "https://www.fotocasa.es/es/comprar/l"),
        ("fotocasa", "https://www.fotocasa.es/es/comprar/l", 2, "https://www.fotocasa.es/es/comprar/l/2"),
        ("pisos", "https://www.pisos.com/venta/cadiz", 1, "https://www.pisos.com/venta/cadiz"),
        ("pisos", "https://www.pisos.com/venta/cadiz", 2, "https://www.pisos.com/venta/cadiz/2/"),
        ("tecnocasa", "https://www.tecnocasa.es/piso/cadiz.html", 1, "https://www.tecnocasa.es/piso/cadiz.html"),
        ("tecnocasa", "https://www.tecnocasa.es/piso/cadiz.html", 2, "https://www.tecnocasa.es/piso/cadiz.html/pag-2"),
        ("habitaclia", "https://www.habitaclia.com/comprar/s", 1, "https://www.habitaclia.com/comprar/s"),
        ("habitaclia", "https://www.habitaclia.com/comprar/s", 2, "https://www.habitaclia.com/comprar/s/2"),
    ],
)
def test_portal_pagination(portal_name: str, url: str, page_num: int, expected_url: str) -> None:
    portal = PORTALS[portal_name]
    assert portal.paginate(url, page_num) == expected_url


def test_resolve_parser() -> None:
    parser_fn = resolve_parser("idealista")
    assert callable(parser_fn)
    parser_fn_foto = resolve_parser(PORTALS["fotocasa"])
    assert callable(parser_fn_foto)

    with pytest.raises(ValueError, match="Unknown portal"):
        resolve_parser("nonexistent")
