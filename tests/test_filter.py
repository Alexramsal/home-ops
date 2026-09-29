"""Tests for strict listing filtering logic (filter.py)."""

from decimal import Decimal

from home_ops.models.schema import Listing, SearchConfig
from home_ops.scraper.filter import FilterStats, filter_listing, filter_listings


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
