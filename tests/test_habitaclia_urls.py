"""Habitaclia truncated canonical URLs fall back to the numeric detail URL."""

import json

from home_ops.scraper import habitaclia


def _html(payload: dict) -> str:
    inner = json.dumps(payload).replace('"', '\\"')
    return f'<script>window.__INITIAL_PROPS__ = JSON.parse("{inner}")</script>'


def _item(canonical: str) -> dict:
    return {
        "legacyNumericId": 55419000000455,
        "urls": {"canonical": canonical},
        "summary": {
            "location": {"municipality": "Cádiz", "district": "Centro"},
            "description": "Piso céntrico reformado",
            "title": "Piso",
        },
        "property": {"features": {}, "builtSurface": 80, "rooms": 3},
        "transaction": {"price": {"amount": 150000}},
    }


def test_truncated_canonical_falls_back_to_numeric() -> None:
    payload = {
        "initialSearchResultsPage": {
            "initialSearchContext": {
                "results": {
                    "items": [
                        _item("/comprar/viviendas/plantas-intermedias-calle-san-agustin-centro-")
                    ]
                }
            }
        }
    }
    listings = habitaclia.parse_listings(_html(payload))
    assert len(listings) == 1
    assert listings[0]["url"] == (
        "https://www.habitaclia.com/i55419000000455.htm?from=list"
    )


def test_full_canonical_untouched() -> None:
    payload = {
        "initialSearchResultsPage": {
            "initialSearchContext": {
                "results": {
                    "items": [
                        _item(
                            "/comprar/viviendas/piso-centro-cadiz/"
                            "ef7618e2-b7e2-42f5-95b5-c0b9f2d5109b/d"
                        )
                    ]
                }
            }
        }
    }
    listings = habitaclia.parse_listings(_html(payload))
    assert len(listings) == 1
    assert listings[0]["url"].endswith("/d")
    assert ".htm" not in listings[0]["url"]
