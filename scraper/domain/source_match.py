"""Strict source-slug matching rules (ADR-016). Pure: no I/O.

A source slug (AnimeAV1 ``principal_slug``, jkanime ``fallback_slug``) may be
auto-assigned to a series only when the page title EXACTLY equals, after
normalization, the series title or one of its alt titles, AND the page passes
validation against the Jikan data (media type family, start year, episode
count). Everything else that looks plausible becomes a pending suggestion.
"""
from __future__ import annotations

import re
import unicodedata

# A non-exact candidate must score at least this much (scrapers' _score_*_item:
# 20 = equals the base title, 12 = substring containment, 6 = base-title
# containment) to be stored as a suggestion. 12 keeps containment and base-title
# matches (e.g. "Owarimonogatari" for "Owarimonogatari Second Season Recaps")
# and drops the weak base-containment hits (6).
SUGGESTION_MIN_SCORE = 12

# Page episode count may exceed Jikan's by this much (pages often list a bonus
# or recap episode, e.g. Owarimonogatari: 13 on the page vs 12 on MAL).
EPISODE_TOLERANCE = 2

# MAL media types that are not real series: skipped by franchise discovery.
SKIPPED_MEDIA_TYPES = frozenset({"cm", "pv", "music"})

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_title(title: str | None) -> str:
    """Lowercase + NFKC + strip punctuation + collapse whitespace.

    Deliberately simple: season markers ("2nd season" vs "season 2" vs "II")
    are NOT unified, so differently-worded seasons stay distinct and fall back
    to a suggestion instead of an auto-assignment.
    """
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", title).lower()
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def is_exact_match(page_title: str | None, titles: list[str | None]) -> bool:
    """True when the normalized page title equals any normalized title."""
    page = normalize_title(page_title)
    if not page:
        return False
    return any(page == normalize_title(t) for t in titles if t)


def split_candidates(
    results: list[dict],
    titles: list[str | None],
    score_item,
    min_score: int = SUGGESTION_MIN_SCORE,
) -> tuple[list[dict], dict | None]:
    """Split search results into ``(exacts, best_non_exact)``.

    ``exacts`` lists EVERY result whose title matches exactly, in search order
    (e.g. a TV page and a movie page sharing a title), so the caller can
    validate each. ``best_non_exact``
    is the highest-scoring other result with ``score_item(item) >= min_score``,
    returned as a copy carrying its ``score``; None when there is none.
    """
    exacts = [r for r in results if is_exact_match(r.get("title"), titles)]
    best, best_score = None, 0
    for r in results:
        if is_exact_match(r.get("title"), titles):
            continue
        score = score_item(r)
        if score >= min_score and score > best_score:
            best, best_score = r, score
    return exacts, ({**best, "score": best_score} if best else None)


_TYPE_FAMILIES = {
    "tv": "tv", "tv anime": "tv", "serie": "tv", "series": "tv",
    "movie": "movie", "pelicula": "movie",
    "ova": "short", "ona": "short", "special": "short", "tv special": "short",
    "especial": "short", "web": "short",
}


def media_type_family(media_type: str | None) -> str | None:
    """Map a MAL / AnimeAV1 / jkanime type label to tv | movie | short.

    ``short`` groups OVA, ONA and specials. Unknown labels return None.
    """
    key = unicodedata.normalize("NFKD", (media_type or "").strip().lower())
    key = "".join(c for c in key if not unicodedata.combining(c))
    return _TYPE_FAMILIES.get(key)


def _check(outcome: str, page, jikan) -> dict:
    return {"outcome": outcome, "page": page, "jikan": jikan}


def validate_candidate(page: dict | None, jikan: dict) -> dict:
    """Compare a source page against Jikan: type family, start year, episodes.

    ``page`` / ``jikan`` carry ``media_type``, ``year``, ``episode_count``.
    Each check is "pass", "fail" or "unknown" (a side is missing -> skipped,
    0 episodes counts as missing). ``passed`` is False only when a check fails.
    """
    page = page or {}
    p_fam = media_type_family(page.get("media_type"))
    j_fam = media_type_family(jikan.get("media_type"))
    if p_fam and j_fam:
        type_check = _check("pass" if p_fam == j_fam else "fail", p_fam, j_fam)
    else:
        type_check = _check("unknown", p_fam, j_fam)

    p_year, j_year = page.get("year") or None, jikan.get("year") or None
    if p_year and j_year:
        year_check = _check("pass" if int(p_year) == int(j_year) else "fail", p_year, j_year)
    else:
        year_check = _check("unknown", p_year, j_year)

    p_eps, j_eps = page.get("episode_count") or None, jikan.get("episode_count") or None
    if p_eps and j_eps:
        ok = int(p_eps) <= int(j_eps) + EPISODE_TOLERANCE
        eps_check = _check("pass" if ok else "fail", p_eps, j_eps)
    else:
        eps_check = _check("unknown", p_eps, j_eps)

    checks = {"type": type_check, "year": year_check, "episodes": eps_check}
    return {"passed": all(c["outcome"] != "fail" for c in checks.values()), "checks": checks}
