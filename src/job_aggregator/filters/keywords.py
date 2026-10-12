from __future__ import annotations

import logging

from job_aggregator.config import settings
from job_aggregator.sources.base import RawOffer

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return text.lower().strip()


def matches_sectors(offer: RawOffer) -> bool:
    if not settings.sectors_list:
        return True
    haystack = _normalize(f"{offer.title} {offer.description or ''}")
    return any(_normalize(kw) in haystack for kw in settings.sectors_list)


def matches_location(offer: RawOffer) -> bool:
    if not settings.target_location:
        return True
    if not offer.location:
        return True  # don't filter out offers with no location data
    return _normalize(settings.target_location) in _normalize(offer.location)


def matches_contract_type(offer: RawOffer) -> bool:
    if not settings.contract_types_list:
        return True
    if not offer.contract_type:
        return True
    return _normalize(offer.contract_type) in [
        _normalize(ct) for ct in settings.contract_types_list
    ]


def passes_keyword_filters(offer: RawOffer) -> bool:
    """Return True if the offer passes all configured keyword/location/contract filters."""
    if not matches_sectors(offer):
        logger.debug("Filtered out (sector): %s", offer.title)
        return False
    if not matches_location(offer):
        logger.debug("Filtered out (location): %s", offer.title)
        return False
    if not matches_contract_type(offer):
        logger.debug("Filtered out (contract): %s", offer.title)
        return False
    return True
