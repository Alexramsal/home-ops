"""Sreality (Czechia) adapter tests."""

from pathlib import Path

import pytest

from home_ops.scraper.portals import PORTALS, portal_for_url
from home_ops.scraper.sreality import parse_listings

FIXTURE = Path(__file__).parent / "fixtures" / "sreality_brno.html"


def test_parse_sreality_brno_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) >= 2

    for listing in listings:
        assert set(listing.keys()) == {
            "external_id", "url", "address", "price", "m2", "rooms", "floor",
            "description", "portal", "price_includes_garage", "garage_price",
            "certificado_energetico_present",
        }
        assert listing["portal"] == "sreality"
        assert listing["external_id"] is not None
        assert listing["url"].startswith("https://")
        assert "sreality.cz" in listing["url"]
        assert "Brno" in listing["address"] or "brno" in listing["url"].lower()
        assert isinstance(listing["price"], int) and listing["price"] > 0
        assert isinstance(listing["m2"], int) and listing["m2"] > 0


def test_parse_sreality_empty() -> None:
    assert parse_listings("") == []


def test_sreality_url_security_and_registry() -> None:
    assert PORTALS["sreality"].name == "sreality"
    assert portal_for_url("https://www.sreality.cz/detail/prodej/byt/12345") is PORTALS["sreality"]
    assert portal_for_url("https://sreality.cz/detail/prodej/byt/12345") is PORTALS["sreality"]

    # Reject HTTP
    assert portal_for_url("http://www.sreality.cz/detail/prodej/byt/12345") is None
    # Reject other subdomains or impostors
    assert portal_for_url("https://sub.sreality.cz/detail/prodej/byt/12345") is None
    assert portal_for_url("https://sreality.cz.fake.com/") is None


def test_parse_sreality_live_snapshot() -> None:
    live_path = Path("/tmp/CZ-live.html")
    if not live_path.exists():
        pytest.skip("/tmp/CZ-live.html not present")
    html = live_path.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) > 0
    for item in listings:
        assert item["external_id"]
        assert item["price"] is None or item["price"] > 0
        assert item["m2"] is not None and item["m2"] > 0
        assert "Brno" in item["address"] or "brno" in item["url"].lower()
