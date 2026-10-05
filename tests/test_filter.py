"""Tests for strict listing filtering logic (filter.py)."""

from decimal import Decimal

import pytest

from home_ops.models.schema import Listing, SearchConfig
from home_ops.scraper.filter import FilterStats, filter_listing, filter_listings
from home_ops.scraper.location import (
    MunicipalityMatch,
    classify_evidence,
    classify_municipality,
    normalize_text,
    parsed_location_evidence,
)


class TestNormalizeText:
    def test_strips_accents_case_and_separators(self) -> None:
        assert normalize_text("Chiclana_de-la  Frontera") == "chiclana de la frontera"
        assert normalize_text("CÁDIZ") == "cadiz"
        assert normalize_text("Jerez—de——la Frontera!") == "jerez de la frontera"


class TestClassifyMunicipality:
    @pytest.mark.parametrize(
        ("location", "municipality"),
        [
            ("Chiclana de la Frontera", "Chiclana de la Frontera"),
            ("chiclana-de-la-frontera", "Chiclana de la Frontera"),
            ("CHICLANA DE LA FRONTERA", "chiclana de la frontera"),
            ("Piso en Chiclana de la Frontera centro", "Chiclana de la Frontera"),
            ("Chiclana  de   la Frontera", "Chiclana de la Frontera"),
            ("CÁDIZ, Chiclana de la Frontera", "Chiclana de la Frontera"),
        ],
    )
    def test_match(self, location: str, municipality: str) -> None:
        assert classify_municipality(location, municipality) == MunicipalityMatch.MATCH

    @pytest.mark.parametrize(
        ("location", "municipality"),
        [
            ("Chiclanaa", "Chiclana"),
            ("Chiclanalandia", "Chiclana"),
        ],
    )
    def test_substring_collision_is_not_match(self, location: str, municipality: str) -> None:
        assert classify_municipality(location, municipality) != MunicipalityMatch.MATCH

    def test_explicit_different_municipality_is_mismatch(self) -> None:
        assert (
            classify_municipality("Jerez de la Frontera", "Chiclana de la Frontera", explicit=True)
            == MunicipalityMatch.MISMATCH
        )

    def test_explicit_superset_is_not_a_match(self) -> None:
        assert classify_municipality("New York", "York", explicit=True) == MunicipalityMatch.MISMATCH

    def test_explicit_region_name_is_mismatch(self) -> None:
        assert (
            classify_municipality("Cádiz", "Chiclana de la Frontera", explicit=True)
            == MunicipalityMatch.MISMATCH
        )

    def test_explicit_exact_match_still_matches(self) -> None:
        assert (
            classify_municipality("Chiclana de la Frontera", "Chiclana de la Frontera", explicit=True)
            == MunicipalityMatch.MATCH
        )

    def test_free_form_province_context_is_unresolved(self) -> None:
        assert (
            classify_municipality("Chalet en Chiclana de la Frontera, Cádiz provincia", "Cádiz")
            == MunicipalityMatch.UNRESOLVED
        )

    def test_free_form_province_with_connector_is_unresolved(self) -> None:
        assert (
            classify_municipality("Provincia de Cádiz", "Cádiz") == MunicipalityMatch.UNRESOLVED
        )
        assert (
            classify_municipality("Cádiz provincia", "Cádiz") == MunicipalityMatch.UNRESOLVED
        )

    def test_free_form_different_municipality_is_unresolved(self) -> None:
        assert (
            classify_municipality("Jerez de la Frontera", "Chiclana de la Frontera")
            == MunicipalityMatch.UNRESOLVED
        )

    def test_province_only_and_street_only_are_unresolved(self) -> None:
        assert classify_municipality("Cádiz", "Chiclana de la Frontera") == MunicipalityMatch.UNRESOLVED
        assert (
            classify_municipality("Calle Mayor 3, Cádiz", "Chiclana de la Frontera")
            == MunicipalityMatch.UNRESOLVED
        )

    def test_empty_evidence_is_unresolved(self) -> None:
        assert classify_municipality(None, "Chiclana") == MunicipalityMatch.UNRESOLVED
        assert classify_municipality("", "Chiclana") == MunicipalityMatch.UNRESOLVED
        assert classify_municipality("   ", "Chiclana") == MunicipalityMatch.UNRESOLVED


class TestParsedLocationEvidence:
    def test_explicit_nested_location_wins_over_address(self) -> None:
        evidence = parsed_location_evidence(
            {"location": {"municipality": "Jerez de la Frontera"}, "address": "Chiclana de la Frontera"}
        )
        assert evidence is not None
        assert evidence.explicit is True
        assert evidence.text == "Jerez de la Frontera"

    def test_address_is_free_form(self) -> None:
        evidence = parsed_location_evidence({"address": "Piso en Chiclana"})
        assert evidence is not None
        assert evidence.explicit is False

    def test_no_location_fields(self) -> None:
        assert parsed_location_evidence({"price": 1}) is None

    def test_classify_evidence(self) -> None:
        evidence = parsed_location_evidence({"location": {"municipality": "Jerez"}})
        assert classify_evidence(evidence, "Chiclana") == MunicipalityMatch.MISMATCH


def test_filter_listing_accepted() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    listing = Listing(
        content_hash="hash1",
        price=Decimal("200000"),
        m2=90.0,
    )
    ok, reason = filter_listing(listing, search_cfg)
    assert ok is True
    assert reason is None


def test_filter_listing_missing_price() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    listing = Listing(content_hash="hash1", price=None, m2=90.0)

    # By default, allow_missing=False
    ok, reason = filter_listing(listing, search_cfg)
    assert ok is False
    assert reason == "missing_price"

    # With allow_missing=True
    ok_allow, reason_allow = filter_listing(listing, search_cfg, allow_missing=True)
    assert ok_allow is True
    assert reason_allow is None


def test_filter_listing_price_exceeded() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    listing = Listing(content_hash="hash1", price=Decimal("300000"), m2=90.0)

    ok, reason = filter_listing(listing, search_cfg)
    assert ok is False
    assert reason == "price_exceeded"

    # Even with allow_missing=True, price_exceeded is rejected
    ok_allow, reason_allow = filter_listing(listing, search_cfg, allow_missing=True)
    assert ok_allow is False
    assert reason_allow == "price_exceeded"


def test_filter_listing_missing_m2() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    listing = Listing(content_hash="hash1", price=Decimal("200000"), m2=None)

    ok, reason = filter_listing(listing, search_cfg)
    assert ok is False
    assert reason == "missing_m2"

    ok_allow, reason_allow = filter_listing(listing, search_cfg, allow_missing=True)
    assert ok_allow is True
    assert reason_allow is None


def test_filter_listing_area_insufficient() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    listing = Listing(content_hash="hash1", price=Decimal("200000"), m2=70.0)

    ok, reason = filter_listing(listing, search_cfg)
    assert ok is False
    assert reason == "area_insufficient"


def test_filter_listings_batch() -> None:
    search_cfg = SearchConfig(max_price=250000.0, min_area_sqm=80.0)
    l1 = Listing(content_hash="1", price=Decimal("200000"), m2=90.0)  # Accepted
    l2 = Listing(content_hash="2", price=Decimal("300000"), m2=90.0)  # price_exceeded
    l3 = Listing(content_hash="3", price=Decimal("200000"), m2=70.0)  # area_insufficient
    l4 = Listing(content_hash="4", price=None, m2=90.0)               # missing_price
    l5 = Listing(content_hash="5", price=Decimal("200000"), m2=None)  # missing_m2

    listings = [l1, l2, l3, l4, l5]
    accepted, stats = filter_listings(listings, search_cfg)

    assert len(accepted) == 1
    assert accepted[0].content_hash == "1"
    assert stats == FilterStats(
        total_seen=5,
        accepted=1,
        rejected_price=1,
        rejected_m2=1,
        rejected_missing_price=1,
        rejected_missing_m2=1,
    )


class TestMunicipalityFiltering:
    def _cfg(self) -> SearchConfig:
        return SearchConfig(municipality="Chiclana de la Frontera", max_price=250000.0, min_area_sqm=80.0)

    def _listing(self, address: str = "Chiclana de la Frontera") -> Listing:
        return Listing(content_hash="h", price=Decimal("200000"), m2=90.0, address=address)

    def test_matching_address_accepted(self) -> None:
        ok, reason = filter_listing(self._listing("Piso en Chiclana de la Frontera"), self._cfg())
        assert ok is True
        assert reason is None

    def test_unresolved_address_accepted(self) -> None:
        ok, reason = filter_listing(self._listing("Cádiz"), self._cfg())
        assert ok is True
        assert reason is None

    def test_explicit_out_of_town_rejected(self) -> None:
        ok, reason = filter_listing(
            self._listing(), self._cfg(), explicit_location="Jerez de la Frontera"
        )
        assert ok is False
        assert reason == "municipality_mismatch"

    def test_price_precedence_before_municipality(self) -> None:
        listing = Listing(content_hash="h", price=Decimal("999999"), m2=90.0, address="x")
        ok, reason = filter_listing(listing, self._cfg(), explicit_location="Jerez de la Frontera")
        assert ok is False
        assert reason == "price_exceeded"

    def test_area_precedence_before_municipality(self) -> None:
        listing = Listing(content_hash="h", price=Decimal("200000"), m2=10.0, address="x")
        ok, reason = filter_listing(listing, self._cfg(), explicit_location="Jerez de la Frontera")
        assert ok is False
        assert reason == "area_insufficient"

    def test_allow_missing_does_not_override_mismatch(self) -> None:
        ok, reason = filter_listing(
            self._listing(), self._cfg(), allow_missing=True, explicit_location="Jerez de la Frontera"
        )
        assert ok is False
        assert reason == "municipality_mismatch"

    def test_batch_counts_municipality_rejections(self) -> None:
        accepted, stats = filter_listings(
            [self._listing("Chiclana de la Frontera"), self._listing("Cádiz")],
            self._cfg(),
            explicit_locations=["Chiclana de la Frontera", "Jerez de la Frontera"],
        )
        assert len(accepted) == 1
        assert stats.rejected_municipality == 1
        assert stats.accepted == 1
