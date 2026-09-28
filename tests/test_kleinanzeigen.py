"""Tests for Kleinanzeigen (Germany) scraper parser and pagination."""

from decimal import Decimal
from pathlib import Path

from home_ops.scraper.kleinanzeigen import parse_listings
from home_ops.scraper.portals import PORTALS, portal_for_url

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kleinanzeigen_berlin.html"


def test_parse_kleinanzeigen_fixture() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    items = parse_listings(html)
    assert len(items) == 27

    first = items[0]
    assert first["external_id"] == "3521932112"
    assert "kleinanzeigen.de" in first["url"]
    assert first["price"] == Decimal("249000")
    assert first["m2"] == 46.0
    assert first["rooms"] == 2
    assert first["portal"] == "kleinanzeigen"

    second = items[3]
    assert second["external_id"] == "3429860830"
    assert second["price"] == Decimal("180400")
    assert second["m2"] == 44.16
    assert second["rooms"] == 1


def test_parse_kleinanzeigen_empty() -> None:
    assert parse_listings("") == []
    assert parse_listings("   ") == []


def test_kleinanzeigen_portal_registration_and_pagination() -> None:
    portal = PORTALS.get("kleinanzeigen")
    assert portal is not None
    assert portal.name == "kleinanzeigen"
    assert portal.domains == ("kleinanzeigen.de",)
    assert portal.parser == "home_ops.scraper.kleinanzeigen"

    url = "https://www.kleinanzeigen.de/s-wohnung-kaufen/berlin/c196l3331"
    assert portal_for_url(url) == portal
    assert portal.paginate(url, 1) == url
    assert portal.paginate(url, 2) == "https://www.kleinanzeigen.de/s-wohnung-kaufen/berlin/seite:2/c196l3331"
