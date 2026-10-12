from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from job_aggregator.config import settings
from job_aggregator.db.models import JobOffer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a job-offer relevance scorer. You will receive a target professional \
profile and a job offer. Rate the offer's relevance to the profile on a scale \
of 1 (completely irrelevant) to 10 (perfect match).

Reply with ONLY a JSON object: {"score": <int>, "reason": "<one sentence>"}
No other text."""

USER_TEMPLATE = """\
Target profile: {profile}

Job offer:
- Title: {title}
- Company: {company}
- Location: {location}
- Contract: {contract_type}
- Description (truncated): {description}"""


def _build_user_message(offer: JobOffer) -> str:
    desc = (offer.description or "")[:2000]
    return USER_TEMPLATE.format(
        profile=settings.target_profile,
        title=offer.title,
        company=offer.company or "N/A",
        location=offer.location or "N/A",
        contract_type=offer.contract_type or "N/A",
        description=desc if desc else "N/A",
    )


async def score_offer(offer: JobOffer) -> tuple[int, str]:
    """Call the LLM and return (score, reason). Falls back to (5, error_msg) on failure."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model=settings.scoring_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(offer)},
            ],
            temperature=0.1,
            max_tokens=100,
        )

        text = response.choices[0].message.content or ""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        score = int(data["score"])
        score = max(1, min(10, score))
        reason = data.get("reason", "")
        logger.info("Scored offer '%s': %d/10 — %s", offer.title, score, reason)
        return score, reason

    except Exception:
        logger.warning("LLM scoring failed for '%s'", offer.title, exc_info=True)
        return 5, "scoring_error"
    finally:
        await client.close()
