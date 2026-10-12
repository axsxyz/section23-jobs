from __future__ import annotations

import logging

import httpx

from job_aggregator.config import settings
from job_aggregator.db.models import JobOffer

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _build_embed(offer: JobOffer) -> dict:
    score = offer.relevance_score or 0
    color = 0x2ECC71 if score >= 8 else 0xF39C12 if score >= 6 else 0xE74C3C

    fields = [
        {"name": "Company", "value": offer.company or "N/A", "inline": True},
        {"name": "Location", "value": offer.location or "N/A", "inline": True},
        {"name": "Contract", "value": offer.contract_type or "N/A", "inline": True},
        {"name": "Score", "value": f"{score}/10", "inline": True},
    ]
    if offer.relevance_reason and offer.relevance_reason != "scoring_error":
        fields.append({"name": "Reason", "value": offer.relevance_reason, "inline": False})

    desc = (offer.description or "")[:300]
    if len(offer.description or "") > 300:
        desc += "..."

    return {
        "title": offer.title,
        "url": offer.url,
        "description": desc,
        "color": color,
        "fields": fields,
    }


async def send_discord(offer: JobOffer) -> None:
    payload = {
        "embeds": [_build_embed(offer)],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(settings.discord_webhook_url, json=payload)
                resp.raise_for_status()
                logger.info("Discord notification sent for '%s'", offer.title)
                return
            except httpx.HTTPError:
                logger.warning(
                    "Discord send attempt %d/%d failed",
                    attempt,
                    MAX_RETRIES,
                    exc_info=True,
                )
                if attempt == MAX_RETRIES:
                    raise
