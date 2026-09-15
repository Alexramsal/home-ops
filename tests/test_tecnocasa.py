"""Tecnocasa parser contract tests."""

from decimal import Decimal

from home_ops.scraper.tecnocasa import parse_listings

HTML = """
<div class="estate-card"><a href="https://www.tecnocasa.es/venta/piso/cadiz/jerez/667759.html">
<h3 class="estate-card-title">Piso en venta</h3>
<h4 class="estate-card-subtitle">Jerez, Chapín</h4>
<div class="estate-card-current-price">309.500 €</div>
<div class="estate-card-rooms"><span>3 dorm.</span></div>
<div class="estate-card-surface"><span>135 m<sup>2</sup></span></div>
<div class="estate-card-bathrooms">2 baños</div></a></div>
"""


def test_parse_tecnocasa_card() -> None:
    listing = parse_listings(HTML)[0]
    assert set(listing) == {
        "external_id", "url", "address", "price", "m2", "rooms", "floor",
        "description", "portal", "price_includes_garage", "garage_price",
        "certificado_energetico_present",
    }
    assert listing["external_id"] == "667759"
    assert listing["price"] == Decimal("309500")
    assert listing["m2"] == 135.0
    assert listing["rooms"] == 3
    assert listing["address"] == "Jerez, Chapín"


def test_empty_and_malformed_tecnocasa_return_empty() -> None:
    assert parse_listings("") == []
    assert parse_listings("<div class='estate-card'>broken</div>") == []
