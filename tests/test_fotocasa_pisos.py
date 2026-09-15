"""Unit tests for the Pisos.com results parser."""

from home_ops.scraper.pisos import parse_listings


def test_parse_listings_maps_card_fields() -> None:
    html = """
    <div class="ad-preview" id="63408664871.516894">
      <span class="ad-preview__price">190.000 €</span>
      <a class="ad-preview__title"
         href="/comprar/atico-cadiz-63408664871_516894/">Ático en Cádiz</a>
      <p class="ad-preview__subtitle">Centro (Cádiz Capital)</p>
      <p class="ad-preview__char p-sm">1 hab.</p>
      <p class="ad-preview__char p-sm">1 baño</p>
      <p class="ad-preview__char p-sm">45 m²</p>
    </div>
    """
    items = parse_listings(html)
    assert len(items) == 1
    item = items[0]
    assert item["portal"] == "pisos"
    assert item["external_id"] == "63408664871"
    assert item["price"] == 190000
    assert item["m2"] == 45.0
    assert item["rooms"] == 1
    assert item["address"] == "Ático en Cádiz, Centro (Cádiz Capital)"


def test_parse_listings_skips_cards_without_link() -> None:
    assert parse_listings('<div class="ad-preview"></div>') == []
    assert parse_listings("") == []
