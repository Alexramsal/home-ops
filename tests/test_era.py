from pathlib import Path

from home_ops.scraper.era import parse_listings


def test_era_fixture_contract():
    rows = parse_listings((Path(__file__).parent / "fixtures" / "era.html").read_text())
    assert len(rows) == 2
    assert all(r["portal"] == "era" and r["url"].startswith("https://www.era.be") for r in rows)
    assert rows[0]["price"] == 395_000
    assert rows[0]["rooms"] == 3


def test_era_parses_spaced_euro_price_and_bedrooms():
    rows = parse_listings('''<article class="card"><a href="/for-sale/antwerpen/house/villa/example-home">Home</a>
        <span>Antwerpen</span><span>€ 549 000</span><span>3 bdrm. 150 m²</span></article>''')
    assert rows[0]["price"] == 549_000
    assert rows[0]["rooms"] == 3
    assert rows[0]["m2"] == 150


def test_era_rejects_search_and_non_https_or_foreign_links():
    rows = parse_listings('''<a href="/for-sale/antwerpen">Search</a>
        <a href="http://www.era.be/for-sale/antwerpen/house/home/x">bad</a>
        <a href="https://evil.example/for-sale/antwerpen/house/home/x">bad</a>''')
    assert rows == []
