"""Daft.ie (Ireland) adapter tests."""

from pathlib import Path

import pytest

from home_ops.scraper.daft import parse_listings
from home_ops.scraper.portals import PORTALS, portal_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "daft_cork.html"


def test_parse_daft_cork_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) >= 2

    for listing in listings:
        assert set(listing.keys()) == {
            "external_id", "url", "address", "price", "m2", "rooms", "floor",
            "description", "portal", "price_includes_garage", "garage_price",
            "certificado_energetico_present",
        }
        assert listing["portal"] == "daft"
        assert listing["external_id"] is not None
        assert listing["url"].startswith("https://")
        assert "daft.ie" in listing["url"]
        assert "Cork" in listing["address"] or "cork" in listing["url"].lower()
        assert isinstance(listing["price"], int) and listing["price"] > 0
        assert isinstance(listing["m2"], int) and listing["m2"] > 0


def test_parse_daft_empty() -> None:
    assert parse_listings("") == []


def test_daft_url_security_and_registry() -> None:
    assert PORTALS["daft"].name == "daft"
    assert portal_for_url("https://www.daft.ie/for-sale/cork/12345") is PORTALS["daft"]
    assert portal_for_url("https://daft.ie/for-sale/cork/12345") is PORTALS["daft"]

    # Reject HTTP
    assert portal_for_url("http://www.daft.ie/for-sale/cork/12345") is None
    # Reject other subdomains or impostors
    assert portal_for_url("https://sub.daft.ie/for-sale/cork/12345") is None
    assert portal_for_url("https://daft.ie.fake.com/") is None


def test_parse_daft_live_snapshot() -> None:
    live_path = Path("/tmp/IE-live.html")
    if not live_path.exists():
        pytest.skip("/tmp/IE-live.html not present")
    html = live_path.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) > 0
    for item in listings:
        assert item["external_id"]
        assert item["price"] is not None and item["price"] > 0
        assert item["m2"] is not None and item["m2"] > 0
        assert "Cork" in item["address"] or "cork" in item["url"].lower()
