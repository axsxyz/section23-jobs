from __future__ import annotations

import logging
import re

import feedparser
import httpx

from job_aggregator.config import settings
from job_aggregator.sources.base import BaseSource, RawOffer

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


class RSSSource(BaseSource):
    name = "rss"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def _fetch_feed(self, url: str) -> list[RawOffer]:
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Failed to fetch RSS feed %s", url, exc_info=True)
            return []

        feed = feedparser.parse(resp.text)
        offers: list[RawOffer] = []

        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue
            offers.append(
                RawOffer(
                    url=link,
                    title=entry.get("title", "Untitled"),
                    company=entry.get("author"),
                    location=entry.get("geo_name") or entry.get("where"),
                    description=_strip_html(entry.get("summary", "")),
                    source=self.name,
                    raw_json={
                        "feed_url": url,
                        "published": entry.get("published", ""),
                    },
                )
            )

        return offers

    async def fetch(self, **kwargs: object) -> list[RawOffer]:
        all_offers: list[RawOffer] = []
        for url in settings.feed_urls_list:
            offers = await self._fetch_feed(url)
            logger.info("RSS feed %s returned %d entries", url, len(offers))
            all_offers.extend(offers)
        return all_offers

    async def close(self) -> None:
        await self._client.aclose()
