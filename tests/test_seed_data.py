"""Seed script data and the keyword upsert, without a database."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from job_aggregator.db.models import JobFamilyKeyword

_SEED_PATH = Path(__file__).resolve().parent.parent / "scripts" / "seed_data.py"


@pytest.fixture(scope="module")
def seed():
    spec = importlib.util.spec_from_file_location("seed_data", _SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # builds the engine but never connects
    return module


def _keyword_lists(seed) -> dict[str, list[str]]:
    lists = {name: value for name, value in vars(seed).items() if name.endswith("_KEYWORDS")}
    assert lists, "no *_KEYWORDS lists found in seed_data.py"
    return lists


def test_seed_keyword_lists_have_no_duplicates(seed) -> None:
    # uq_family_keyword is unique on (family_id, keyword), so a duplicate in one
    # list makes the first seed on an empty database fail.
    for name, keywords in _keyword_lists(seed).items():
        duplicates = sorted({kw for kw in keywords if keywords.count(kw) > 1})
        assert not duplicates, f"{name} has duplicates: {duplicates}"


class _Result:
    def __init__(self, scalar=None, rows=None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


class FakeSession:
    """Empty database: no family, no keywords. Records what would be inserted."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self._executes = 0
        self.commits = 0

    async def execute(self, _stmt):
        self._executes += 1
        return _Result()  # first: no family; second: no existing keywords

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1


async def test_upsert_family_ignores_duplicate_keywords_in_input(seed) -> None:
    session = FakeSession()
    family_def = {"slug": "test", "display_name": "Test", "description": "d"}

    await seed._upsert_family(session, family_def, ["a", "b", "a"])

    keywords = [o.keyword for o in session.added if isinstance(o, JobFamilyKeyword)]
    assert keywords == ["a", "b"]
    assert session.commits == 1
