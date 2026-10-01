from pathlib import Path

from home_ops.scraper.funda import parse_listings


def test_funda_fixture_contract():
    rows = parse_listings((Path(__file__).parent / "fixtures" / "funda.html").read_text())
    assert len(rows) == 2
    assert all(r["portal"] == "funda" and r["url"].startswith("https://www.funda.nl") for r in rows)


def test_funda_parses_euro_price_and_rooms_from_card():
    rows = parse_listings((Path(__file__).parent / "fixtures" / "funda.html").read_text())
    assert rows[0]["price"] == 1_500_000
    assert rows[0]["m2"] == 306
    assert rows[0]["rooms"] == 3


def test_funda_price_does_not_absorb_area_and_canonicalizes_duplicates():
    html = '''<a href="/detail/koop/x/1/?a=1">A</a><span>€ 100.000</span><span>10 m²</span>
        <a href="/detail/koop/x/1/?a=2#fragment">A</a><span>€ 100.000</span><span>10 m²</span>'''
    rows = parse_listings(html)
    assert len(rows) == 1
    assert rows[0]["price"] == 100_000
    assert rows[0]["external_id"] == "1"
    assert rows[0]["url"] == "https://www.funda.nl/detail/koop/x/1/"


def test_funda_rejects_non_https_or_foreign_detail_links():
    rows = parse_listings('''<a href="http://www.funda.nl/detail/koop/rotterdam/x/1/">bad</a>
        <a href="https://evil.example/detail/koop/rotterdam/x/2/">bad</a>''')
    assert rows == []
