"""Unit tests for scraper/db/_paging.py — fetch_all (ADR-010)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from db._paging import fetch_all


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Fresh query per page; serves its slice of ``rows`` for the requested range."""

    def __init__(self, rows, calls):
        self._rows = rows
        self._calls = calls
        self._range = None

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        self._calls.append(self._range)
        start, end = self._range
        return _FakeResult(self._rows[start:end + 1])


def _factory(rows):
    calls: list[tuple[int, int]] = []
    builds: list[_FakeQuery] = []

    def build():
        q = _FakeQuery(rows, calls)
        builds.append(q)
        return q

    return build, calls, builds


def _rows(n):
    return [{"i": i} for i in range(n)]


class TestFetchAll:
    def test_zero_rows_one_call(self):
        build, calls, _ = _factory([])
        assert fetch_all(build) == []
        assert calls == [(0, 999)]

    def test_999_rows_one_call(self):
        build, calls, _ = _factory(_rows(999))
        assert len(fetch_all(build)) == 999
        assert calls == [(0, 999)]

    def test_exactly_1000_rows_two_calls_second_empty(self):
        build, calls, _ = _factory(_rows(1000))
        assert fetch_all(build) == _rows(1000)
        assert calls == [(0, 999), (1000, 1999)]

    def test_2500_rows_three_calls_in_order(self):
        build, calls, builds = _factory(_rows(2500))
        assert fetch_all(build, page_size=1000) == _rows(2500)
        assert calls == [(0, 999), (1000, 1999), (2000, 2999)]
        # Each page is built from a fresh query.
        assert len({id(b) for b in builds}) == 3

    def test_custom_page_size(self):
        build, calls, _ = _factory(_rows(5))
        assert fetch_all(build, page_size=2) == _rows(5)
        assert calls == [(0, 1), (2, 3), (4, 5)]

    def test_none_data_treated_as_empty(self):
        class _NoneQuery:
            def range(self, start, end):
                return self

            def execute(self):
                return _FakeResult(None)

        assert fetch_all(lambda: _NoneQuery()) == []

    def test_non_positive_page_size_rejected(self):
        with pytest.raises(ValueError):
            fetch_all(lambda: None, page_size=0)
