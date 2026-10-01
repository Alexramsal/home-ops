"""Nieruchomosci-online (Poland) adapter tests."""

from pathlib import Path

import pytest

from home_ops.scraper.nieruchomosci_online import parse_listings
from home_ops.scraper.portals import PORTALS, portal_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "nieruchomosci_online_krakow.html"


def test_parse_nieruchomosci_online_krakow_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) >= 2

    for listing in listings:
        assert set(listing.keys()) == {
            "external_id", "url", "address", "price", "m2", "rooms", "floor",
            "description", "portal", "price_includes_garage", "garage_price",
            "certificado_energetico_present",
        }
        assert listing["portal"] == "nieruchomosci_online"
        assert listing["external_id"] is not None
        assert listing["url"].startswith("https://")
        assert "nieruchomosci-online.pl" in listing["url"]
        assert "Kraków" in listing["address"] or "krakow" in listing["url"].lower()
        assert isinstance(listing["price"], int) and listing["price"] > 0
        assert isinstance(listing["m2"], int) and listing["m2"] > 0


def test_parse_nieruchomosci_online_empty() -> None:
    assert parse_listings("") == []


def test_nieruchomosci_online_url_security_and_registry() -> None:
    assert PORTALS["nieruchomosci_online"].name == "nieruchomosci_online"
    assert portal_for_url("https://krakow.nieruchomosci-online.pl/mieszkania/") is PORTALS["nieruchomosci_online"]
    assert portal_for_url("https://nieruchomosci-online.pl/mieszkania/") is PORTALS["nieruchomosci_online"]

    # Reject HTTP
    assert portal_for_url("http://krakow.nieruchomosci-online.pl/mieszkania/") is None
    # Reject impostors
    assert portal_for_url("https://nieruchomosci-online.pl.fake.com/") is None
    assert portal_for_url("https://fake-nieruchomosci-online.pl/") is None


def test_parse_nieruchomosci_online_live_snapshot() -> None:
    live_path = Path("/tmp/PL-live.html")
    if not live_path.exists():
        pytest.skip("/tmp/PL-live.html not present")
    html = live_path.read_text(encoding="utf-8")
    listings = parse_listings(html)
    assert len(listings) > 0
    for item in listings:
        assert item["external_id"]
        assert item["price"] is not None and item["price"] > 0
        assert item["m2"] is not None and item["m2"] > 0
        assert "Kraków" in item["address"] or "krakow" in item["url"].lower()
