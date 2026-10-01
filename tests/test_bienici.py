"""Bien'ici JSON adapter contract tests."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from home_ops.scraper.bienici import parse_listings
from home_ops.scraper.portals import _paginate_bienici

FIXTURE = Path(__file__).parent / "fixtures" / "bienici_response.json"


def test_parse_bienici_public_search_cards_from_live_fixture() -> None:
    payload = FIXTURE.read_text()
    listings = parse_listings(payload)
    assert len(listings) == 3

    expected = [
        {
            "external_id": "ag757613-550665272",
            "url": "https://www.bienici.com/annonce/ag757613-550665272",
            "address": "Paris 15e, 75015",
            "price": 265000,
            "m2": 30,
            "rooms": 2,
            "floor": "2",
        },
        {
            "external_id": "ag757613-550161659",
            "url": "https://www.bienici.com/annonce/ag757613-550161659",
            "address": "Paris 11e, 75011",
            "price": 448997,
            "m2": 38,
            "rooms": 2,
            "floor": "2",
        },
        {
            "external_id": "ag757613-548662421",
            "url": "https://www.bienici.com/annonce/ag757613-548662421",
            "address": "Paris 20e, 75020",
            "price": 814000,
            "m2": 105,
            "rooms": 5,
            "floor": "2",
        },
    ]

    for listing, exp in zip(listings, expected, strict=True):
        assert set(listing) == {
            "external_id", "url", "address", "price", "m2", "rooms", "floor",
            "description", "portal", "price_includes_garage", "garage_price",
            "certificado_energetico_present",
        }
        assert listing["external_id"] == exp["external_id"]
        assert listing["url"] == exp["url"]
        assert listing["address"] == exp["address"]
        assert listing["price"] == exp["price"]
        assert listing["m2"] == exp["m2"]
        assert listing["rooms"] == exp["rooms"]
        assert listing["floor"] == exp["floor"]
        assert listing["portal"] == "bienici"
        assert listing["price_includes_garage"] is False
        assert listing["garage_price"] is None
        assert listing["certificado_energetico_present"] is None


def test_parse_bienici_malformed_or_empty() -> None:
    assert parse_listings("") == []
    assert parse_listings(json.dumps({"realEstateAds": "bad"})) == []


def test_bienici_registry_and_json_pagination() -> None:
    from home_ops.scraper.portals import PORTALS, portal_for_url

    assert PORTALS["bienici"].name == "bienici"
    assert PORTALS["bienici"].domains == ("bienici.com",)
    assert portal_for_url("https://www.bienici.com/recherche") is PORTALS["bienici"]
    url = "https://www.bienici.com/recherche?filters=%7B%22perPage%22%3A24%2C%22foo%22%3A%22x%22%7D&keep=a%20b"
    paged = PORTALS["bienici"].paginate(url, 2)
    query = parse_qs(urlparse(paged).query)
    assert json.loads(query["filters"][0]) == {
        "perPage": 24, "foo": "x", "from": 24, "page": 2,
    }
    assert query["keep"] == ["a b"]


def test_bienici_pagination_uses_size_when_per_page_is_absent() -> None:
    from home_ops.scraper.portals import PORTALS

    url = "https://www.bienici.com/recherche?filters=%7B%22size%22%3A10%7D"
    query = parse_qs(urlparse(PORTALS["bienici"].paginate(url, 3)).query)
    assert json.loads(query["filters"][0]) == {"size": 10, "from": 20, "page": 3}


@pytest.mark.parametrize(
    "filters",
    ["not-json", json.dumps(["not", "a", "mapping"])],
)
def test_bienici_pagination_rejects_invalid_filters(filters: str) -> None:
    with pytest.raises(ValueError, match="Invalid Bien'ici filters"):
        _paginate_bienici(f"https://www.bienici.com/recherche?filters={filters}", 2)


def test_bienici_dashboard_url_safety() -> None:
    from home_ops.web import _safe_url

    absolute = "https://www.bienici.com/annonce/ag757613-550665272"
    assert _safe_url(absolute, "bienici") == absolute
    assert _safe_url("/annonce/ag757613-550665272", "bienici") == absolute
    assert _safe_url("javascript:alert(1)", "bienici") == "#"
