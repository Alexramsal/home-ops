"""Unit tests for the Fotocasa search-result parser."""

import json
from typing import Any

from home_ops.scraper.fotocasa import parse_listings


def _fake_html(items: list[Any]) -> str:
    """Build a minimal fotocasa page with the embedded application/json state."""
    state = {"initialSearch": {"result": {"resultsV2": {"items": items}}}}
    return (
        "<html><head>"
        f'<script type="application/json">{json.dumps(state)}</script>'
        "</head><body></body></html>"
    )


def test_parse_listings_maps_item_fields() -> None:
    html = _fake_html(
        [
            {
                "id": "1_187417980",
                "detailUrl": "/es/comprar/vivienda/chiclana/parking/187417980/d",
                "price": {"amount": 525000, "amountDrop": 25000},
                "features": {"surface": 210, "rooms": 4, "floor": 0},
                "location": {
                    "address": "Las Lagunas - Campano",
                    "zone": "Chiclana de la Frontera, Cádiz",
                },
                "propertySubtype": "SINGLE_FAMILY_SEMI_DETACHED",
            }
        ]
    )
    items = parse_listings(html)
    assert len(items) == 1
    it = items[0]
    assert it["portal"] == "fotocasa"
    assert it["external_id"] == "187417980"
    assert it["price"] == 525000
    assert it["m2"] == 210
    assert it["rooms"] == 4
    assert it["floor"] == "0"
    assert it["address"] == "Las Lagunas - Campano, Chiclana de la Frontera, Cádiz"
    assert it["url"] == "/es/comprar/vivienda/chiclana/parking/187417980/d"


def test_parse_listings_empty_on_no_json() -> None:
    assert parse_listings("<html><body>no state</body></html>") == []
    assert parse_listings("") == []


def test_parse_listings_skips_bad_items() -> None:
    html = _fake_html([{"id": "x"}, "not-a-dict", {"id": "1_1", "price": {"amount": 1}}])
    items = parse_listings(html)
    assert len(items) == 2  # both dicts survive; the string is skipped
