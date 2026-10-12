"""DATABASE_URL rewriting in db/engine.py, without a database."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from job_aggregator.db.engine import _async_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # What Railway injects.
        ("postgresql://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        # Short alias; SQLAlchemy has no "postgres" dialect.
        ("postgres://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
        # Already names the async driver (docker-compose / .env): unchanged.
        ("postgresql+asyncpg://u:p@db:5432/app", "postgresql+asyncpg://u:p@db:5432/app"),
    ],
)
def test_database_url_uses_asyncpg(url: str, expected: str) -> None:
    rewritten = _async_url(url)
    assert rewritten == expected
    # SQLAlchemy must resolve the rewritten URL to the asyncpg dialect.
    assert make_url(rewritten).get_dialect().driver == "asyncpg"
