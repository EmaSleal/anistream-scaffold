"""Tests for scripts/audit_source_slugs.py (read-only ADR-016 audit)."""
import csv
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import audit_source_slugs as audit  # noqa: E402
from tests.test_audit_shared_slug_offsets import _FakeClient  # noqa: E402


def _s(sid, title, **kw):
    base = {"id": sid, "mal_id": 1, "title": title, "titles": [], "media_type": "tv", "year": 2018,
            "episode_count": 12, "principal_slug": None, "fallback_slug": None,
            "franchise_relation": None}
    return {**base, **kw}


def _pages(av1=None, jk=None):
    return (lambda slug: av1.get(slug) if av1 else None), (lambda slug: jk.get(slug) if jk else None)


class TestAuditRow:
    def test_exact_and_valid_is_ok(self):
        row = audit.audit_row(_s("a", "Show"), "animeav1", "show", "Show",
                              {"media_type": "TV Anime", "year": 2018, "episode_count": 13})
        assert row["verdict"] == "ok" and row["exact_match"] is True

    def test_containment_is_suspect(self):
        row = audit.audit_row(_s("a", "Owarimonogatari Second Season Recaps"), "animeav1",
                              "owarimonogatari", "Owarimonogatari", {"episode_count": 13})
        assert row["verdict"] == "suspect" and row["exact_match"] is False

    def test_failed_validation_and_failed_fetch_are_suspect(self):
        bad = audit.audit_row(_s("a", "Show"), "animeav1", "show", "Show",
                              {"media_type": "Película", "year": 2018, "episode_count": 1})
        assert bad["verdict"] == "suspect" and '"type": "fail"' in bad["checks"]
        gone = audit.audit_row(_s("a", "Show"), "jkanime", "show", None, None)
        assert gone["verdict"] == "suspect" and gone["checks"] == "fetch_failed"


class TestMain:
    def test_zero_writes_and_expected_csvs(self, tmp_path, monkeypatch):
        series = [
            _s("ok", "Show", principal_slug="show"),
            _s("bad", "Show Recap", media_type="special", principal_slug="show", fallback_slug="show-jk"),
            _s("sum", "Recap Compilation", franchise_relation="Summary"),
            _s("promo", "Promo", media_type="cm"),
            _s("none", "Nothing"),
        ]
        client = _FakeClient(series, [])
        monkeypatch.setattr(audit.storage, "get_client", lambda: client)
        monkeypatch.setattr(audit, "OUTPUT_DIR", str(tmp_path))
        monkeypatch.setattr(audit, "REQUEST_DELAY", 0)
        monkeypatch.setattr(audit.time, "sleep", lambda s: None)
        monkeypatch.setattr(audit, "fetch_animeav1_page", lambda slug: {
            "title": "Show", "media_type": "TV Anime", "year": 2018, "episode_count": 13})
        monkeypatch.setattr(audit, "fetch_jkanime_series_info", lambda slug: None)

        assert audit.main() == 0
        assert client.writes == []

        with open(tmp_path / "source_slug_audit.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert tuple(reader.fieldnames) == audit.COLUMNS
            rows = [(r["series_id"], r["source"], r["verdict"]) for r in reader]
        assert rows == [("ok", "animeav1", "ok"), ("bad", "animeav1", "suspect"),
                        ("bad", "jkanime", "suspect")]

        with open(tmp_path / "summary_relation_audit.csv", newline="", encoding="utf-8") as f:
            review = {r["series_id"]: r["reason"] for r in csv.DictReader(f)}
        assert review == {"sum": "franchise_relation=Summary", "promo": "media_type=cm"}
