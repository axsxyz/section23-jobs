from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import httpx

from job_aggregator.config import settings
from job_aggregator.sources.base import BaseSource, RawOffer

logger = logging.getLogger(__name__)

TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    "?realm=/partenaire"
)
SEARCH_URL = (
    "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
)
SCOPES = "api_offresdemploiv2 o2dsoffre"
PAGE_SIZE = 150  # API max
API_HARD_CAP = 1000  # France Travail max range index (0-based) → 1050 results

# All metropolitan + overseas departments
ALL_DEPARTMENTS = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09",
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
    "60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
    "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "90", "91", "92", "93", "94", "95",
    "971", "972", "973", "974", "976",  # DOM
]


class FranceTravailSource(BaseSource):
    name = "france_travail"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)
        self._token: str | None = None
        self._token_expires: float = 0
        self._semaphore = asyncio.Semaphore(10)  # 10 req/s rate limit

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires - 30:
            return self._token

        logger.info("Refreshing France Travail OAuth2 token")
        resp = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.france_travail_client_id,
                "client_secret": settings.france_travail_client_secret,
                "scope": SCOPES,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + body.get("expires_in", 1500)
        return self._token  # type: ignore[return-value]

    async def _search_page(
        self, params: dict, range_start: int = 0
    ) -> list[dict]:
        token = await self._ensure_token()
        params_with_range = {
            **params,
            "range": f"{range_start}-{range_start + PAGE_SIZE - 1}",
        }

        async with self._semaphore:
            resp = await self._client.get(
                SEARCH_URL,
                params=params_with_range,
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code == 401:
            self._token = None
            token = await self._ensure_token()
            async with self._semaphore:
                resp = await self._client.get(
                    SEARCH_URL,
                    params=params_with_range,
                    headers={"Authorization": f"Bearer {token}"},
                )

        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("resultats", [])

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _to_raw_offer(self, item: dict) -> RawOffer:
        lieu = item.get("lieuTravail", {})
        entreprise = item.get("entreprise", {})
        lat = lieu.get("latitude")
        lon = lieu.get("longitude")
        return RawOffer(
            url=item.get("origineOffre", {}).get("urlOrigine", "")
            or f"https://candidat.francetravail.fr/offres/recherche/detail/{item.get('id', '')}",
            title=item.get("intitule", ""),
            company=entreprise.get("nom"),
            location=lieu.get("libelle"),
            department=lieu.get("codePostal", "")[:2] if lieu.get("codePostal") else None,
            contract_type=item.get("typeContrat"),
            description=item.get("description", ""),
            source=self.name,
            raw_json=item,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            expires_at=self._parse_date(item.get("dateEcheance")),
        )

    async def _fetch_pages(self, params: dict) -> tuple[list[dict], bool]:
        """Paginate through all results for a single set of search params.

        Returns ``(results, hit_cap)``. ``hit_cap`` is true when pagination stopped
        because the next range start would reach ``API_HARD_CAP`` while pages were
        still full, i.e. the API probably holds more results than it will return.
        """
        results: list[dict] = []
        offset = 0
        while True:
            page = await self._search_page(params, offset)
            if not page:
                return results, False
            results.extend(page)
            if len(page) < PAGE_SIZE:
                return results, False
            offset += PAGE_SIZE
            if offset >= API_HARD_CAP:
                return results, True

    async def _fetch_all(self, params: dict, seen_ids: set[str]) -> list[dict]:
        """Fetch all results for a keyword, sweeping by department if the API cap is hit."""
        results, capped = await self._fetch_pages(params)

        if capped:
            kw = params.get("motsCles", "<no keyword>")
            logger.info(
                "Cap hit for '%s' (%d results) — switching to department sweep for full coverage",
                kw, len(results),
            )
            # Build dept params: drop commune (incompatible with departement filter)
            dept_base = {k: v for k, v in params.items() if k != "commune"}
            dept_results: list[dict] = []
            dept_seen: set[str] = set(r["id"] for r in results)

            for dept in ALL_DEPARTMENTS:
                dept_params = {**dept_base, "departement": dept}
                dept_page, _ = await self._fetch_pages(dept_params)
                for item in dept_page:
                    oid = item.get("id", "")
                    if oid not in dept_seen and oid not in seen_ids:
                        dept_seen.add(oid)
                        dept_results.append(item)

            logger.info(
                "Department sweep for '%s': %d additional offers (total %d)",
                kw, len(dept_results), len(results) + len(dept_results),
            )
            results.extend(dept_results)

        return [r for r in results if r.get("id", "") not in seen_ids]

    async def fetch(self, **kwargs: object) -> list[RawOffer]:
        # France Travail motsCles uses AND logic for space-separated terms, so we
        # fire one request per keyword and deduplicate by offer ID.
        base_params: dict[str, str] = {"sort": "1"}  # newest first
        if settings.target_location:
            base_params["commune"] = settings.target_location
        if settings.contract_types_list:
            base_params["typeContrat"] = ",".join(settings.contract_types_list)

        keywords = settings.sectors_list or [""]  # empty string = no keyword filter

        seen_ids: set[str] = set()
        all_items: list[dict] = []

        for kw in keywords:
            params = dict(base_params)
            if kw:
                params["motsCles"] = kw
            logger.info("Fetching France Travail offers with params=%s", params)
            for item in await self._fetch_all(params, seen_ids):
                offer_id = item.get("id", "")
                if offer_id not in seen_ids:
                    seen_ids.add(offer_id)
                    all_items.append(item)

        logger.info(
            "France Travail returned %d raw offers (%d keywords, deduplicated)",
            len(all_items), len(keywords),
        )
        return [self._to_raw_offer(item) for item in all_items]

    async def close(self) -> None:
        await self._client.aclose()
