"""Pagination and département sweep in the France Travail source, with a fake API."""

from __future__ import annotations

import itertools

from job_aggregator.sources.france_travail import (
    ALL_DEPARTMENTS,
    API_HARD_CAP,
    PAGE_SIZE,
    FranceTravailSource,
)


class FakeSearch:
    """Stands in for ``_search_page``: records calls, returns synthetic offers."""

    def __init__(self, national_total: int, per_department: int = 1) -> None:
        self.national_total = national_total
        self.per_department = per_department
        self.calls: list[tuple[dict, int]] = []
        self._ids = itertools.count()

    async def __call__(self, params: dict, range_start: int = 0) -> list[dict]:
        self.calls.append((dict(params), range_start))
        total = self.per_department if "departement" in params else self.national_total
        size = max(0, min(PAGE_SIZE, total - range_start))
        return [{"id": f"o{next(self._ids)}"} for _ in range(size)]


async def _run(fake: FakeSearch) -> list[dict]:
    source = FranceTravailSource()
    source._search_page = fake  # type: ignore[method-assign]
    try:
        return await source._fetch_all({"motsCles": "python", "commune": "Paris"}, set())
    finally:
        await source.close()


async def test_department_sweep_runs_when_pagination_hits_the_cap() -> None:
    # The API keeps returning full pages: pagination stops at the cap.
    fake = FakeSearch(national_total=10_000)
    results = await _run(fake)

    dept_calls = [p for p, _ in fake.calls if "departement" in p]
    assert {p["departement"] for p in dept_calls} == set(ALL_DEPARTMENTS)
    assert all("commune" not in p for p in dept_calls)

    national_pages = len(range(0, API_HARD_CAP, PAGE_SIZE))
    assert len(results) == national_pages * PAGE_SIZE + len(ALL_DEPARTMENTS)


async def test_no_sweep_when_results_end_before_the_cap() -> None:
    # Short last page: every result was returned, no sweep needed.
    fake = FakeSearch(national_total=PAGE_SIZE * 3 + 20)
    results = await _run(fake)

    assert not [p for p, _ in fake.calls if "departement" in p]
    assert len(results) == PAGE_SIZE * 3 + 20


async def test_no_sweep_when_last_full_page_is_followed_by_an_empty_one() -> None:
    fake = FakeSearch(national_total=PAGE_SIZE * 2)
    await _run(fake)

    assert not [p for p, _ in fake.calls if "departement" in p]

