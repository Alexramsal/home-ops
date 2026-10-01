from pathlib import Path

from home_ops.scraper.green_acres import _price, parse_listings

FIXTURE = Path(__file__).parent / "fixtures" / "green_acres.html"


def test_parse_one_sanitized_card_per_country() -> None:
    listings = parse_listings(FIXTURE.read_text())
    assert len(listings) == 5
    assert {item["portal"] for item in listings} == {"green_acres"}
    for item in listings:
        assert item["external_id"]
        assert item["url"].startswith("https://www.green-acres.")
        assert item["address"]
        assert isinstance(item["price"], (int, float))
        assert item["m2"]
        assert item["rooms"]
        assert {"floor", "price_includes_garage", "garage_price", "certificado_energetico_present"} <= item.keys()

    italy = next(item for item in listings if ".it/" in item["url"])
    assert "This penthouse represents a rare combination" in italy["description"]


def test_price_parsing_handles_locale_separators() -> None:
    assert _price("€123,45") == 123.45
    assert _price("€ 1 234 567") == 1234567
    assert _price("€\u00a01\u00a0234\u00a0567") == 1234567
    assert _price("1,690,000") == 1690000
    assert _price("12.700.000") == 12700000


def test_rejects_unsafe_obfuscated_urls() -> None:
    import base64
    html = '<div class="announce-card" data-advertid="x" data-o="{}"><div class="announce-localisation">X</div></div>'
    for target in ("https://evil.test/x", "http://green-acres.it/x", "javascript:alert(1)"):
        encoded = base64.b64encode(target.encode()).decode()
        assert parse_listings(html.format(encoded)) == []
    assert parse_listings(html.format("%%%")) == []
