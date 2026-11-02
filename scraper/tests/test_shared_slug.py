"""Unit tests for domain.shared_slug (ADR-012), fixtures mirror franchise 37430 (Slime)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.shared_slug import compute_shared_slug_offset

S4_SLUG = "tensei-shitara-slime-datta-ken-4th-season"
S2_SLUG = "tensei-shitara-slime-datta-ken-2nd-season"


def _s(sid, order, count, principal=None, fallback=None):
    return {"id": sid, "season_order": order, "episode_count": count,
            "principal_slug": principal, "fallback_slug": fallback}


def _offset(siblings, sid, slug):
    me = next(s for s in siblings if s["id"] == sid)
    return compute_shared_slug_offset(
        siblings, {"id": sid, "season_order": me["season_order"]}, slug
    )


class TestComputeSharedSlugOffset:
    def test_a_season4_ignores_later_part2(self):
        siblings = [_s("s4", 5, 24, principal=S4_SLUG), _s("p2", 6, 0, fallback=S4_SLUG)]
        result = _offset(siblings, "s4", S4_SLUG)
        assert result == {"offset": 0, "earlier_ids": [], "reason": None}

    def test_b_part2_with_zero_count_has_defined_offset(self):
        siblings = [_s("s4", 5, 24, principal=S4_SLUG), _s("p2", 6, 0, fallback=S4_SLUG)]
        result = _offset(siblings, "p2", S4_SLUG)
        assert result["offset"] == 24
        assert result["earlier_ids"] == ["s4"]
        # A continuation with unknown own count claims nothing (ADR-012).
        from routes.ingest_routes import _build_episodes_from_animeav1
        from unittest.mock import patch
        eps = [{"episode_number": n, "thumbnail_url": None} for n in range(1, 25)]
        with patch("routes.ingest_routes.scrape_animeav1_episodes", return_value=eps):
            claimed = _build_episodes_from_animeav1(
                "p2", S4_SLUG, {}, {}, episode_offset=result["offset"], max_episodes=0,
            )
        assert [e["episode_number"] for e in claimed] == []

    def test_c_journal_between_seasons_counts(self):
        siblings = [
            _s("s2", 3, 12, principal=S2_SLUG),
            _s("vj2", 4, 1, principal=S2_SLUG),
            _s("s2p2", 5, 12, fallback=S2_SLUG),
        ]
        result = _offset(siblings, "s2p2", S2_SLUG)
        assert result["offset"] == 13
        assert result["earlier_ids"] == ["s2", "vj2"]

    def test_d_earlier_sibling_unknown_count_is_undeterminable(self):
        for count in (None, 0):
            siblings = [_s("s4", 5, count, principal=S4_SLUG), _s("p2", 6, 12, fallback=S4_SLUG)]
            result = _offset(siblings, "p2", S4_SLUG)
            assert result["offset"] is None
            assert "episode_count" in result["reason"]

    def test_e_null_or_tied_season_order_is_undeterminable(self):
        null_sib = [_s("a", None, 12, principal="x"), _s("b", 2, 12, fallback="x")]
        tied = [_s("a", 2, 12, principal="x"), _s("b", 2, 12, fallback="x")]
        assert _offset(null_sib, "b", "x")["offset"] is None
        assert _offset(null_sib, "a", "x")["offset"] is None  # self NULL
        result = _offset(tied, "b", "x")
        assert result["offset"] is None and "tied" in result["reason"]

    def test_f_no_sharing_siblings_is_zero(self):
        siblings = [_s("a", 1, 12, principal="x"), _s("b", 2, 12, principal="y")]
        assert _offset(siblings, "b", "y")["offset"] == 0
        assert _offset([_s("solo", None, None, principal="x")], "solo", "x")["offset"] == 0

    def test_nonsharing_null_order_is_ignored(self):
        siblings = [_s("a", 1, 12, principal="x"), _s("b", 2, 12, principal="x"),
                    _s("c", None, None, principal="other")]
        assert _offset(siblings, "b", "x")["offset"] == 12
