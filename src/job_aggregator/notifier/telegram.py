from __future__ import annotations

import logging

import httpx

from job_aggregator.config import settings
from job_aggregator.db.models import JobOffer

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_RETRIES = 3


def _format_message(offer: JobOffer) -> str:
    score = offer.relevance_score or "?"
    reason = offer.relevance_reason or ""
    lines = [
        f"*{_escape_md(offer.title)}*",
        f"Company: {_escape_md(offer.company or 'N/A')}",
        f"Location: {_escape_md(offer.location or 'N/A')}",
        f"Contract: {_escape_md(offer.contract_type or 'N/A')}",
        f"Score: {score}/10",
    ]
    if reason and reason != "scoring_error":
        lines.append(f"_{_escape_md(reason)}_")
    lines.append(f"\n[View offer]({offer.url})")
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    for ch in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        text = text.replace(ch, f"\\{ch}")
    return text


async def send_telegram(offer: JobOffer) -> None:
    url = API_URL.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": _format_message(offer),
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Telegram notification sent for '%s'", offer.title)
                return
            except httpx.HTTPError:
                logger.warning(
                    "Telegram send attempt %d/%d failed",
                    attempt,
                    MAX_RETRIES,
                    exc_info=True,
                )
                if attempt == MAX_RETRIES:
                    raise
