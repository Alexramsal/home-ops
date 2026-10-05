"""Tests for price history (append-only observations + zone analytics)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from home_ops.analytics import (
    price_evolution_by_week,
    price_history_stats,
    zone_from_portal_url,
)
from home_ops.models.schema import Listing

if TYPE_CHECKING:
    from home_ops.models.data_storage import DuckDBConnection


class TestZoneFromPortalUrl:
    def test_extracts_location_slug(self) -> None:
        url = "https://www.idealista.com/venta-viviendas/chiclana-de-la-frontera-cadiz/"
        assert zone_from_portal_url(url) == "chiclana-de-la-frontera-cadiz"

    def test_distinct_source_zones(self) -> None:
        assert (
            zone_from_portal_url("https://www.idealista.com/venta-viviendas/jerez-de-la-frontera-cadiz/")
            == "jerez-de-la-frontera-cadiz"
        )
        assert (
            zone_from_portal_url("https://www.fotocasa.es/es/comprar/viviendas/chiclana-de-la-frontera/todas-las-zonas/l")
            == "chiclana-de-la-frontera"
        )

    def test_returns_none_without_location(self) -> None:
        assert zone_from_portal_url("https://www.idealista.com/venta-viviendas/") is None

    def test_opaque_listing_url_is_not_a_zone(self) -> None:
        assert zone_from_portal_url("https://www.pisos.com/comprar/piso-1234567/") is None

    def test_hostname_is_not_a_zone(self) -> None:
        assert zone_from_portal_url("https://krakow.nieruchomosci-online.pl/mieszkanie/") is None

    def test_filter_and_query_segments_are_not_zones(self) -> None:
        assert (
            zone_from_portal_url("https://www.idealista.com/venta-viviendas/con-precio-hasta-250000/")
            is None
        )
        assert (
            zone_from_portal_url("https://www.idealista.com/venta-viviendas/precio-max-250000/")
            is None
        )
        assert zone_from_portal_url("https://www.idealista.com/venta-viviendas/?zona=no-es-zona") is None


class TestLatestPriceZone:
    def test_no_history_returns_none(self, db: DuckDBConnection) -> None:
        assert db.latest_price_zone("missing-hash") is None

    def test_returns_most_recent_non_null(self, db: DuckDBConnection) -> None:
        db.record_price_observation("h1", "zona-a", Decimal("100000"), 100.0)
        db.record_price_observation("h1", "zona-b", Decimal("110000"), 100.0)
        assert db.latest_price_zone("h1") == "zona-b"

    def test_newer_null_does_not_erase_known_zone(self, db: DuckDBConnection) -> None:
        db.record_price_observation("h2", "zona-c", Decimal("100000"), 100.0)
        db.record_price_observation("h2", None, Decimal("100000"), 100.0)
        assert db.latest_price_zone("h2") == "zona-c"

    def test_scoped_by_content_hash(self, db: DuckDBConnection) -> None:
        db.record_price_observation("h3", "zona-d", Decimal("100000"), 100.0)
        db.record_price_observation("h4", "zona-e", Decimal("100000"), 100.0)
        assert db.latest_price_zone("h3") == "zona-d"


def _listing(db: DuckDBConnection, content_hash: str, price: float, m2: float) -> Listing:
    return Listing(
        content_hash=content_hash,
        url=f"https://idealista.com/inmueble/{content_hash}/",
        portal="idealista",
        price=Decimal(str(price)),
        m2=m2,
    )


class TestPriceHistoryStats:
    def test_empty_db(self, db: DuckDBConnection) -> None:
        stats = price_history_stats(db)
        assert stats["observations"] == 0
        assert stats["unique_listings"] == 0

    def test_counts_observations_and_uniques(self, db: DuckDBConnection) -> None:
        # Same listing observed twice (price change), another once.
        for _ in range(2):
            db.record_price_observation("hash-a", "zona-x", Decimal("100000"), 100.0)
        db.record_price_observation("hash-b", "zona-x", Decimal("200000"), 100.0)
        stats = price_history_stats(db)
        assert stats["observations"] == 3
        assert stats["unique_listings"] == 2
        # Mean over OBSERVATIONS (100k, 100k, 200k), not unique listings.
        assert stats["mean"] == 133333.33333333334


class TestPriceEvolutionByWeek:
    def test_empty(self, db: DuckDBConnection) -> None:
        assert price_evolution_by_week(db) == []

    def test_groups_by_zone(self, db: DuckDBConnection) -> None:
        db.record_price_observation("h1", "zona-a", Decimal("150000"), 75.0)
        db.record_price_observation("h2", "zona-b", Decimal("300000"), 100.0)
        evo_a = price_evolution_by_week(db, zone="zona-a")
        assert len(evo_a) == 1
        assert evo_a[0]["mean_eur_m2"] == 2000.0  # 150000 / 75
        evo_all = price_evolution_by_week(db)
        assert len(evo_all) == 1  # same week, both zones aggregated
        assert evo_all[0]["n"] == 2


class TestScanRecordsObservations:
    def test_record_for_duplicate_too(self, db: DuckDBConnection) -> None:
        """The observation must be recorded even when the listing is a dup."""
        listing = _listing(db, "hash-dup", 120000.0, 80.0)
        first = db.insert_listing(listing)
        second = db.insert_listing(listing)  # duplicate → None
        assert first is not None
        assert second is None
        db.record_price_observation(listing.content_hash, "z", listing.price, listing.m2)
        stats = price_history_stats(db)
        assert stats["observations"] >= 1
