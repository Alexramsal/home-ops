"""Strict data quality filtering for scraped listings."""

from dataclasses import dataclass

from home_ops.models.schema import Listing, SearchConfig


@dataclass
class FilterStats:
    total_seen: int = 0
    accepted: int = 0
    rejected_price: int = 0
    rejected_m2: int = 0
    rejected_missing_price: int = 0
    rejected_missing_m2: int = 0


def filter_listing(
    listing: Listing, search_cfg: SearchConfig, allow_missing: bool = False
) -> tuple[bool, str | None]:
    """Validate a single listing against search criteria and data completeness rules."""
    if listing.price is None:
        if not allow_missing:
            return False, "missing_price"
    elif float(listing.price) > search_cfg.max_price:
        return False, "price_exceeded"

    if listing.m2 is None:
        if not allow_missing:
            return False, "missing_m2"
    elif listing.m2 < search_cfg.min_area_sqm:
        return False, "area_insufficient"

    return True, None


def filter_listings(
    listings: list[Listing], search_cfg: SearchConfig, allow_missing: bool = False
) -> tuple[list[Listing], FilterStats]:
    """Filter a list of listings and return accepted listings with filter statistics."""
    stats = FilterStats(total_seen=len(listings))
    accepted: list[Listing] = []

    for listing in listings:
        is_ok, reason = filter_listing(listing, search_cfg, allow_missing=allow_missing)
        if is_ok:
            accepted.append(listing)
            stats.accepted += 1
        else:
            if reason == "price_exceeded":
                stats.rejected_price += 1
            elif reason == "area_insufficient":
                stats.rejected_m2 += 1
            elif reason == "missing_price":
                stats.rejected_missing_price += 1
            elif reason == "missing_m2":
                stats.rejected_missing_m2 += 1

    return accepted, stats
