"""Tests for Njuškalo (Croatia) scraper parser and pagination."""

from pathlib import Path

from home_ops.scraper.njuskalo import parse_listings
from home_ops.scraper.portals import PORTALS, portal_for_url

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "njuskalo_cakovec.html"


def test_parse_listings_fixture() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    items = parse_listings(html)
    assert len(items) == 2

    first = items[0]
    assert first["external_id"] == "50586992"
    assert first["url"] == "/nekretnine/stan-cakovec-martane-oglas-50586992"
    assert first["address"] == "STAN - ČAKOVEC, Martane"
    assert first["price"] == 220000
    assert first["m2"] == 77.26
    assert first["rooms"] == 3
    assert first["portal"] == "njuskalo"
    assert first["price_includes_garage"] is False
    assert first["garage_price"] is None
    assert first["certificado_energetico_present"] is None

    second = items[1]
    assert second["external_id"] == "49812345"
    assert second["url"] == "https://www.njuskalo.hr/nekretnine/kuca-cakovec-jug-oglas-49812345"
    assert second["address"] == "Kuća Čakovec Jug"
    assert second["price"] == 185000
    assert second["m2"] == 145.5
    assert second["rooms"] is None
    assert second["portal"] == "njuskalo"


def test_parse_listings_empty_or_no_cards() -> None:
    assert parse_listings("") == []
    assert parse_listings("   ") == []
    assert parse_listings("<html><body><div>No items here</div></body></html>") == []


def test_njuskalo_portal_registration_and_pagination() -> None:
    portal = PORTALS.get("njuskalo")
    assert portal is not None
    assert portal.name == "njuskalo"
    assert portal.domains == ("njuskalo.hr",)
    assert portal.parser == "home_ops.scraper.njuskalo"

    url = "https://www.njuskalo.hr/prodaja-stanova/cakovec"
    assert portal_for_url(url) is portal
    assert portal.paginate(url, 1) == url
    assert portal.paginate(url, 2) == "https://www.njuskalo.hr/prodaja-stanova/cakovec?page=2"
    assert portal.paginate(url + "?sort=new", 2) == "https://www.njuskalo.hr/prodaja-stanova/cakovec?sort=new&page=2"
