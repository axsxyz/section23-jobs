from __future__ import annotations

import logging

import httpx

from job_aggregator.config import settings
from job_aggregator.sources.base import BaseSource, RawOffer

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaSource(BaseSource):
    name = "adzuna"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)

    async def fetch(self, **kwargs: object) -> list[RawOffer]:
        country = settings.adzuna_country
        params: dict[str, str | int] = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": 50,
            "content-type": "application/json",
        }

        if settings.sectors_list:
            params["what"] = " ".join(settings.sectors_list[:5])
        if settings.target_location:
            params["where"] = settings.target_location

        all_offers: list[RawOffer] = []
        for page in range(1, 4):  # fetch up to 3 pages (150 results)
            url = f"{BASE_URL}/{country}/search/{page}"
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("Adzuna page %d failed", page, exc_info=True)
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            for item in results:
                loc = item.get("location", {})
                lat = item.get("latitude")
                lon = item.get("longitude")
                all_offers.append(
                    RawOffer(
                        url=item.get("redirect_url", ""),
                        title=item.get("title", ""),
                        company=item.get("company", {}).get("display_name"),
                        location=", ".join(loc.get("area", [])),
                        description=item.get("description", ""),
                        contract_type=item.get("contract_type"),
                        source=self.name,
                        raw_json=item,
                        latitude=float(lat) if lat is not None else None,
                        longitude=float(lon) if lon is not None else None,
                    )
                )

        logger.info("Adzuna returned %d offers", len(all_offers))
        return all_offers

    async def close(self) -> None:
        await self._client.aclose()
