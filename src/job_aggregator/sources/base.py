from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawOffer:
    """Normalized offer coming out of any source."""

    url: str
    title: str
    company: str | None = None
    location: str | None = None
    department: str | None = None
    contract_type: str | None = None
    description: str | None = None
    source: str = ""
    raw_json: dict = field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None
    expires_at: datetime | None = None


class BaseSource(abc.ABC):
    """Every source must implement an async fetch that yields normalized offers."""

    name: str = "unknown"

    @abc.abstractmethod
    async def fetch(self, **kwargs: object) -> list[RawOffer]:
        ...

    async def close(self) -> None:
        pass
