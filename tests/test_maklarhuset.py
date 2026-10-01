from pathlib import Path

from home_ops.scraper.maklarhuset import parse_listings


def test_maklarhuset_fixture_contract():
    rows = parse_listings((Path(__file__).parent / "fixtures" / "maklarhuset.html").read_text())
    assert len(rows) == 2
    assert all(r["portal"] == "maklarhuset" and r["url"].startswith("https://www.maklarhuset.se") for r in rows)


def test_maklarhuset_price_does_not_capture_address_number():
    rows = parse_listings((Path(__file__).parent / "fixtures" / "maklarhuset.html").read_text())
    assert rows[0]["price"] == 2_495_000
    assert rows[0]["rooms"] == 4
    assert rows[0]["m2"] == 112.0
    assert rows[0]["address"] == "Kållered, Rektor Jonssons väg"


def test_maklarhuset_rejects_non_https_or_foreign_links():
    rows = parse_listings('''<div class="mh-object"><a href="http://www.maklarhuset.se/bostad/x">x</a></div>
        <div class="mh-object"><a href="https://evil.example/bostad/x">x</a></div>''')
    assert rows == []
