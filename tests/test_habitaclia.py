"""Habitaclia parser contract tests."""

import json

from home_ops.scraper.habitaclia import parse_listings


def _html(payload: object) -> str:
    encoded = json.dumps(json.dumps(payload))
    return f"<script>window.__INITIAL_PROPS__ = JSON.parse({encoded});</script>"


def test_parse_habitaclia_payload() -> None:
    item = {
        "legacyNumericId": 24428000001606,
        "navigationUrl": "/i24428000001606.htm?from=list",
        "summary": {
            "title": "Piso en el centro",
            "description": "Description",
            "location": {"municipality": "Sanlúcar", "district": "Centro"},
        },
        "property": {
            "rooms": 3,
            "builtSurface": 90,
            "floor": "GROUND_FLOOR",
            "features": {"has": ["PRIVATE_PARKING"]},
            "energyEfficiencyCertificate": {"status": "AVAILABLE"},
        },
        "transaction": {"price": {"amount": 285000}},
        "urls": {"canonical": "/comprar/viviendas/example/d"},
    }
    payload = {
        "initialSearchResultsPage": {
            "initialSearchContext": {"results": {"items": [item]}}
        }
    }
    listing = parse_listings(_html(payload))[0]
    assert set(listing) == {
        "external_id", "url", "address", "price", "m2", "rooms", "floor",
        "description", "portal", "price_includes_garage", "garage_price",
        "certificado_energetico_present",
    }
    assert listing["external_id"] == "24428000001606"
    assert listing["url"] == "https://www.habitaclia.com/comprar/viviendas/example/d"
    assert listing["address"] == "Sanlúcar, Centro"
    assert listing["price_includes_garage"] is True
    assert listing["certificado_energetico_present"] is True


def test_empty_and_malformed_habitaclia_return_empty() -> None:
    assert parse_listings("") == []
    assert parse_listings("window.__INITIAL_PROPS__ = JSON.parse(\"bad\")") == []
