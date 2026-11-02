"""Repair production episodes owned by the wrong series on a shared AnimeAV1
page (ADR-013), preserving user watch history.

Background: several franchise members ended up with the same ``principal_slug``
/ ``fallback_slug`` and each ingested episodes from that page, so the page's
real owner (the series the page actually belongs to) lacks its episodes while
other series hold copies. This tool, driven by an explicit human-curated JSON
plan, releases the slug from the wrong series, recovers the owner's missing
episodes (ADR-011 recovery path), moves every user reference to the owner's
episode with the same page-native ``episode_number`` and deletes the released
series' episodes.

Workflow:
  1. Dry-run (default, zero writes):
         cd scraper && python scripts/repair_shared_slug.py \\
             --plan scripts/repair_plans/2026-11-02-shared-slug.json
     Prints the discovered ``episodes.id`` reference columns and one block per
     page, and writes ``scripts/output/shared_slug_repair_plan.csv`` (one row
     per page and released series: released numbers, reference counts per
     table.column, owner's existing numbers, offset/window, numbers to
     recover, remap targets, planned deletions, status).
  2. Review the CSV.
  3. Fill every ``"todo"`` field in the plan (set the real values and delete
     the field). Pages with a ``todo`` are reported but REFUSED on --apply
     (counted as skipped, exit code unaffected).
  4. ``--apply`` (asks "Apply repair to N pages? [y/N]" unless ``--yes``).
     Per page, in order: (a) update the released series' slugs; (b) recover
     the owner via ``simulcast_check.run_simulcast_update(..., mode="grace",
     backfill_mode="write")`` (skipped when the owner already has every
     released number the window covers); (c) verify every released number that
     has user references exists for the owner, else stop the page with
     ``owner_missing_numbers`` BEFORE any remap/deletion; (d) remap references
     (watch_progress, user_continue_watching); on a uniqueness conflict the
     row with the most recent ``updated_at`` (tie: greater ``progress_sec``)
     is kept; (e) delete the released series' episodes. Pages are independent:
     a failure stops that page only; exit code is 1 if any page failed.
  5. Re-run ``scripts/audit_shared_slug_offsets.py`` to confirm the result.

Plan file: a JSON list of pages::

    [{"slug": str, "owner_series_id": str,
      "release": [{"series_id": str, "principal_slug": str|null,
                   "fallback_slug": str|null}],
      "todo": str (optional), "comment": str (optional)}]

``todo``/``comment`` are also allowed on release entries. Only the listed
series release the slug; other legitimate sharers are not listed and keep it.
A release series must currently hold ``slug`` (principal or fallback) or
already hold exactly its planned slugs (already released). Invalid plans exit
with code 2 before any database access.

Idempotency: a series that already holds its planned slugs with a null planned
principal_slug and still has episodes is a leftover of an interrupted run and
is resumed (remap + delete). One already released with a non-null planned
principal_slug is treated as done (its episodes may be its own). A page with
nothing left to do is ``no_changes`` and --apply performs zero writes on it.

Statuses: ok, invalid_plan, ambiguous_offset (ADR-012 offset undeterminable),
owner_missing_numbers, no_changes.

Reference columns: discovered by scanning ``migrations/*.sql`` (columns named
``episode_id`` / ``*_episode_id`` or ``REFERENCES episodes``) plus a static
registry for tables whose schema is not in the repo. A discovered column
without a handler blocks --apply.

Scripts are excluded from the Docker image: run locally with production
credentials (cwd=scraper/).
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simulcast_check  # noqa: E402
import storage  # noqa: E402
from db._paging import fetch_all  # noqa: E402
from domain.shared_slug import compute_shared_slug_offset, shares_slug  # noqa: E402

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)
_CSV_NAME = "shared_slug_repair_plan.csv"
_ID_CHUNK = 100  # keep the IN (...) filter's URL short
_SERIES_COLS = "id, title, franchise_id, season_order, episode_count, principal_slug, fallback_slug"

# Columns this script knows how to remap. Anything discovered outside this set
# blocks --apply.
HANDLED_COLUMNS = (
    ("watch_progress", "episode_id"),
    ("user_continue_watching", "episode_id"),
    ("user_continue_watching", "next_episode_id"),
)
# References whose schema is not in the repo's migrations.
STATIC_REFERENCES = (
    ("watch_progress", "episode_id", "documented in db/progress.py; base schema not in repo"),
)
_ORDER = {
    "watch_progress": ("id",),
    "user_continue_watching": ("user_id", "franchise_key"),
}

COLUMNS = (
    "page_slug", "owner_series_id", "series_id", "release_state", "planned_principal_slug",
    "planned_fallback_slug", "released_numbers", "ref_counts", "owner_existing_numbers",
    "owner_offset", "owner_window", "owner_to_recover", "remap_targets",
    "planned_deletions", "reference_columns", "status", "todo", "notes",
)


class PlanError(ValueError):
    """The plan file is malformed."""


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------


def _check_str(obj: dict, key: str, where: str, nullable: bool = False) -> None:
    if key not in obj:
        raise PlanError(f"{where}: missing key {key!r}")
    val = obj[key]
    if val is None and nullable:
        return
    if not isinstance(val, str) or not val.strip():
        raise PlanError(f"{where}: {key!r} must be a non-empty string"
                        + (" or null" if nullable else ""))


def validate_plan(data) -> list[dict]:
    """Validate the plan structure; returns it unchanged or raises PlanError."""
    if not isinstance(data, list):
        raise PlanError("plan must be a JSON list of pages")
    page_keys = {"slug", "owner_series_id", "release", "todo", "comment"}
    rel_keys = {"series_id", "principal_slug", "fallback_slug", "todo", "comment"}
    for i, page in enumerate(data):
        where = f"page[{i}]"
        if not isinstance(page, dict):
            raise PlanError(f"{where}: must be an object")
        _check_str(page, "slug", where)
        _check_str(page, "owner_series_id", where)
        extra = set(page) - page_keys
        if extra:
            raise PlanError(f"{where}: unknown keys {sorted(extra)}")
        for opt in ("todo", "comment"):
            if opt in page and not isinstance(page[opt], str):
                raise PlanError(f"{where}: {opt!r} must be a string")
        release = page.get("release")
        if not isinstance(release, list) or not release:
            raise PlanError(f"{where}: 'release' must be a non-empty list")
        for j, rel in enumerate(release):
            rwhere = f"{where}.release[{j}]"
            if not isinstance(rel, dict):
                raise PlanError(f"{rwhere}: must be an object")
            _check_str(rel, "series_id", rwhere)
            _check_str(rel, "principal_slug", rwhere, nullable=True)
            _check_str(rel, "fallback_slug", rwhere, nullable=True)
            extra = set(rel) - rel_keys
            if extra:
                raise PlanError(f"{rwhere}: unknown keys {sorted(extra)}")
            for opt in ("todo", "comment"):
                if opt in rel and not isinstance(rel[opt], str):
                    raise PlanError(f"{rwhere}: {opt!r} must be a string")
    return data


def load_plan(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise PlanError(f"cannot read plan {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"plan {path} is not valid JSON: {exc}") from exc
    return validate_plan(data)


# ---------------------------------------------------------------------------
# Reference-column discovery
# ---------------------------------------------------------------------------

_CREATE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)\s*\((.*?)\n\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w.\"]+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(\w+)([^;]*);",
    re.IGNORECASE,
)


def _is_episode_ref(col: str, definition: str) -> bool:
    return (
        col == "episode_id"
        or col.endswith("_episode_id")
        or re.search(r"REFERENCES\s+episodes\b", definition, re.IGNORECASE) is not None
    )


def discover_reference_columns(migrations_dir: str | None = None) -> list[dict]:
    """Find every column that references ``episodes.id``.

    Returns ``[{"table", "column", "source", "handled"}]`` sorted by
    table/column. Sources: ``migrations/<file>`` for migration scans, and the
    static registry for tables whose schema is not in the repo.
    """
    found: dict[tuple[str, str], list[str]] = {}

    def add(table: str, column: str, source: str) -> None:
        table = table.strip('"').split(".")[-1]
        sources = found.setdefault((table, column), [])
        if source not in sources:
            sources.append(source)

    for path in sorted(glob.glob(os.path.join(migrations_dir or MIGRATIONS_DIR, "*.sql"))):
        name = f"migrations/{os.path.basename(path)}"
        with open(path, encoding="utf-8") as f:
            sql = re.sub(r"--[^\n]*", "", f.read())
        for table, body in _CREATE_RE.findall(sql):
            for line in body.split("\n"):
                m = re.match(r"\s*(\w+)\s+(.*)", line)
                if m and m.group(1).upper() not in ("PRIMARY", "UNIQUE", "CONSTRAINT", "FOREIGN", "CHECK") \
                        and _is_episode_ref(m.group(1), m.group(2)):
                    add(table, m.group(1), name)
        for table, col, rest in _ALTER_RE.findall(sql):
            if _is_episode_ref(col, rest):
                add(table, col, name)
    for table, column, source in STATIC_REFERENCES:
        add(table, column, source)

    return [
        {"table": t, "column": c, "source": "; ".join(srcs), "handled": (t, c) in HANDLED_COLUMNS}
        for (t, c), srcs in sorted(found.items())
    ]


# ---------------------------------------------------------------------------
# Reads (paginated, ADR-010)
# ---------------------------------------------------------------------------


def _fetch_in(table: str, select: str, column: str, values: list[str], order: tuple[str, ...]) -> list[dict]:
    client = storage.get_client()
    rows: list[dict] = []
    values = list(values)
    for i in range(0, len(values), _ID_CHUNK):
        chunk = values[i:i + _ID_CHUNK]

        def build(chunk=chunk):
            q = client.table(table).select(select).in_(column, chunk)
            for col in order:
                q = q.order(col)
            return q
        rows.extend(fetch_all(build))
    return rows


def _fetch_eq(table: str, select: str, filters: dict, order: tuple[str, ...]) -> list[dict]:
    client = storage.get_client()

    def build():
        q = client.table(table).select(select)
        for col, val in filters.items():
            q = q.eq(col, val)
        for col in order:
            q = q.order(col)
        return q
    return fetch_all(build)


def _fetch_episodes(series_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {sid: [] for sid in series_ids}
    rows = _fetch_in("episodes", "id, series_id, episode_number", "series_id", series_ids,
                     ("series_id", "episode_number"))
    for r in rows:
        if r["series_id"] in out and r.get("episode_number") is not None:
            out[r["series_id"]].append(r)
    return out


def _fetch_references(episode_ids: list[str]) -> dict[tuple[str, str], list[dict]]:
    """Rows referencing any of ``episode_ids``, per handled (table, column)."""
    refs: dict[tuple[str, str], list[dict]] = {}
    for table, column in HANDLED_COLUMNS:
        refs[(table, column)] = _fetch_in(table, "*", column, episode_ids, _ORDER[table])
    return refs


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def _fmt_nums(nums) -> str:
    return ",".join(str(n) for n in sorted(nums))


def _plan_skeleton(page: dict) -> dict:
    return {
        "slug": page["slug"], "owner": page["owner_series_id"],
        "status": "ok", "reason": "", "todo": _page_todo(page),
        "offset": None, "expected": None, "window": None,
        "owner_nums": [], "owner_eps": {}, "owner_row": None,
        "to_recover": [], "recoverable": [], "needs_recovery": False,
        "releases": [], "released_eps": [], "ref_numbers": [], "unrecoverable": [],
        "slug_updates": [],
    }


def _page_todo(page: dict) -> str:
    todos = [page["todo"]] if page.get("todo") else []
    todos += [f"{r['series_id']}: {r['todo']}" for r in page["release"] if r.get("todo")]
    return " | ".join(todos)


def _invalid(plan: dict, reason: str) -> dict:
    plan["status"], plan["reason"] = "invalid_plan", reason
    return plan


def build_page_plan(page: dict, reference_columns: list[dict]) -> dict:
    """Read-only: compute everything the repair of one page needs."""
    plan = _plan_skeleton(page)
    slug, owner_id = page["slug"], page["owner_series_id"]
    rel_ids = [r["series_id"] for r in page["release"]]
    if len(set(rel_ids)) != len(rel_ids):
        return _invalid(plan, "duplicate series in release list")
    if owner_id in rel_ids:
        return _invalid(plan, f"owner {owner_id} cannot be in the release list")

    rows = {r["id"]: r for r in _fetch_in("series", _SERIES_COLS, "id", [owner_id] + rel_ids, ("id",))}
    owner = rows.get(owner_id)
    if owner is None:
        return _invalid(plan, f"owner {owner_id} does not exist")
    if owner.get("principal_slug") != slug:
        return _invalid(plan, f"owner principal_slug is {owner.get('principal_slug')!r}, not {slug!r}")
    plan["owner_row"] = owner

    episodes = _fetch_episodes([owner_id] + rel_ids)
    plan["owner_eps"] = {e["episode_number"]: e["id"] for e in episodes[owner_id]}
    plan["owner_nums"] = sorted(plan["owner_eps"])

    planned_by_id: dict[str, dict] = {}
    for rel in page["release"]:
        sid = rel["series_id"]
        row = rows.get(sid)
        if row is None:
            return _invalid(plan, f"release series {sid} does not exist")
        pp, pf = rel["principal_slug"], rel["fallback_slug"]
        if slug in (pp, pf):
            return _invalid(plan, f"{sid}: planned slugs still contain {slug!r}")
        notes = []
        if shares_slug(row, slug):
            state, eps = "holding", episodes[sid]
        elif (row.get("principal_slug"), row.get("fallback_slug")) == (pp, pf):
            if pp is None:
                state, eps = "released", episodes[sid]
                if eps:
                    notes.append("leftover episodes of an interrupted run: resuming")
            else:
                state, eps = "released", []
                notes.append("already released with its own principal_slug: treated as done, "
                             "episodes kept")
        else:
            return _invalid(plan, f"{sid} neither holds {slug!r} nor its planned slugs "
                                  f"(has {row.get('principal_slug')!r}/{row.get('fallback_slug')!r})")
        if state == "holding":
            plan["slug_updates"].append({"series_id": sid, "principal_slug": pp, "fallback_slug": pf})
        planned_by_id[sid] = {**row, "principal_slug": pp, "fallback_slug": pf}
        plan["releases"].append({
            "series_id": sid, "title": row.get("title") or "", "state": state,
            "planned_principal": pp, "planned_fallback": pf,
            "episodes": [{"id": e["id"], "number": e["episode_number"]} for e in eps],
            "todo": rel.get("todo", ""), "ref_counts": {}, "notes": notes,
        })
    plan["released_eps"] = [e for r in plan["releases"] for e in r["episodes"]]

    # ADR-012 offset AS IT WILL BE after the planned slug changes.
    franchise_id = owner.get("franchise_id")
    siblings = _fetch_eq("series", _SERIES_COLS, {"franchise_id": franchise_id}, ("id",)) if franchise_id else []
    siblings = [planned_by_id.get(s["id"], s) for s in siblings]
    off = compute_shared_slug_offset(siblings, owner, slug)
    plan["offset"], plan["expected"] = off["offset"], owner.get("episode_count")
    if off["offset"] is None:
        plan["status"], plan["reason"] = "ambiguous_offset", off["reason"] or ""
        return plan

    # References per released series.
    ep_ids = [e["id"] for e in plan["released_eps"]]
    id_to_num = {e["id"]: e["number"] for e in plan["released_eps"]}
    id_to_series = {e["id"]: r["series_id"] for r in plan["releases"] for e in r["episodes"]}
    refs = _fetch_references(ep_ids) if ep_ids else {k: [] for k in HANDLED_COLUMNS}
    ref_numbers: set[int] = set()
    for (table, column), rrows in refs.items():
        for row in rrows:
            eid = row.get(column)
            if eid in id_to_num:
                ref_numbers.add(id_to_num[eid])
                rel = next(r for r in plan["releases"] if r["series_id"] == id_to_series[eid])
                key = f"{table}.{column}"
                rel["ref_counts"][key] = rel["ref_counts"].get(key, 0) + 1
    plan["ref_numbers"] = sorted(ref_numbers)

    released_nums = {e["number"] for e in plan["released_eps"]}
    owner_nums = set(plan["owner_eps"])
    expected = plan["expected"] or 0
    lo, hi = off["offset"] + 1, off["offset"] + expected
    plan["window"] = (lo, hi)
    in_window = lambda n: lo <= n <= hi  # noqa: E731
    plan["to_recover"] = [n for n in range(lo, hi + 1) if n not in owner_nums]
    plan["recoverable"] = sorted(n for n in released_nums - owner_nums if in_window(n))
    plan["needs_recovery"] = bool(plan["recoverable"])
    plan["unrecoverable"] = sorted(n for n in ref_numbers - owner_nums if not in_window(n))

    if not plan["slug_updates"] and not plan["released_eps"]:
        plan["status"] = "no_changes"
    elif plan["unrecoverable"]:
        plan["status"] = "owner_missing_numbers"
        plan["reason"] = (f"referenced numbers {plan['unrecoverable']} are missing for the owner "
                          f"and outside its recovery window {lo}..{hi}")
    return plan


def build_plans(pages: list[dict], reference_columns: list[dict]) -> list[dict]:
    return [build_page_plan(p, reference_columns) for p in pages]


def plan_rows(plan: dict, reference_columns: list[dict]) -> list[dict]:
    """CSV rows: one per (page, released series)."""
    cols = ";".join(f"{c['table']}.{c['column']}" for c in reference_columns)
    owner = plan["owner"]
    rows = []
    for rel in plan["releases"]:
        nums = sorted(e["number"] for e in rel["episodes"])
        targets = []
        for n in nums:
            tid = plan["owner_eps"].get(n)
            targets.append(f"{n}->{tid}" if tid else f"{n}->(after recovery)")
        notes = list(rel["notes"])
        if plan["reason"]:
            notes.append(plan["reason"])
        missing_unref = [n for n in nums if n not in plan["owner_eps"] and n not in plan["ref_numbers"]]
        if missing_unref:
            notes.append(f"released numbers without references and missing for owner: {missing_unref}")
        todo = plan["todo"] if plan["todo"] else ""
        rows.append({
            "page_slug": plan["slug"], "owner_series_id": owner, "series_id": rel["series_id"],
            "release_state": rel["state"],
            "planned_principal_slug": rel["planned_principal"] or "",
            "planned_fallback_slug": rel["planned_fallback"] or "",
            "released_numbers": _fmt_nums(nums),
            "ref_counts": ";".join(f"{k}={v}" for k, v in sorted(rel["ref_counts"].items())),
            "owner_existing_numbers": _fmt_nums(plan["owner_nums"]),
            "owner_offset": "" if plan["offset"] is None else plan["offset"],
            "owner_window": "" if not plan["window"] else f"{plan['window'][0]}..{plan['window'][1]}",
            "owner_to_recover": _fmt_nums(plan["to_recover"]),
            "remap_targets": ";".join(targets),
            "planned_deletions": len(rel["episodes"]),
            "reference_columns": cols, "status": plan["status"], "todo": todo,
            "notes": " | ".join(notes),
        })
    if not rows:  # invalid pages may fail before any release row is built
        rows.append({c: "" for c in COLUMNS} | {
            "page_slug": plan["slug"], "owner_series_id": owner, "status": plan["status"],
            "todo": plan["todo"], "notes": plan["reason"], "reference_columns": cols,
        })
    return rows


def _print_discovery(columns: list[dict]) -> None:
    print("Columns referencing episodes.id:")
    for c in columns:
        print(f"  {c['table']}.{c['column']} [{'handled' if c['handled'] else 'UNHANDLED'}] "
              f"discovered via {c['source']}")


def _print_plan(plan: dict) -> None:
    head = f"[{plan['status']}] page {plan['slug']} owner={plan['owner']}"
    print(head + (f" ({plan['reason']})" if plan["reason"] else "")
          + (f" TODO: {plan['todo']}" if plan["todo"] else ""))
    if plan["status"] == "invalid_plan":
        return
    print(f"    offset={plan['offset']} window={plan['window']} owner_has={_fmt_nums(plan['owner_nums'])} "
          f"to_recover={_fmt_nums(plan['to_recover'])} recovery_needed={plan['needs_recovery']}")
    for rel in plan["releases"]:
        nums = [e["number"] for e in rel["episodes"]]
        print(f"    release {rel['series_id']} ({rel['state']}): numbers={_fmt_nums(nums)} "
              f"refs={rel['ref_counts']} delete={len(nums)}"
              + "".join(f"\n      note: {n}" for n in rel["notes"]))


def _write_csv(rows: list[dict]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, _CSV_NAME)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _ts(value) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def released_wins(released: dict, existing: dict) -> bool:
    """True when the released-episode row must replace the owner-episode row:
    most recent updated_at, tie -> greater progress_sec, full tie -> keep existing."""
    a, b = _ts(released.get("updated_at")), _ts(existing.get("updated_at"))
    if a != b:
        return a > b
    return (released.get("progress_sec") or 0) > (existing.get("progress_sec") or 0)


def _remap_watch_progress(rows: list[dict], id_map: dict[str, str], owner_id: str) -> None:
    client = storage.get_client()
    for r in rows:
        target = id_map[r["episode_id"]]
        existing = _fetch_eq("watch_progress", "*",
                             {"user_id": r["user_id"], "episode_id": target}, ("id",))
        if existing:
            if released_wins(r, existing[0]):
                client.table("watch_progress").delete().eq("id", existing[0]["id"]).execute()
            else:
                client.table("watch_progress").delete().eq("id", r["id"]).execute()
                continue
        client.table("watch_progress").update(
            {"episode_id": target, "series_id": owner_id}
        ).eq("id", r["id"]).execute()


def _remap_continue_watching(rows: list[dict], id_map: dict[str, str], owner_id: str,
                             owner_key: str) -> None:
    client = storage.get_client()
    for snapshot in rows:
        # Re-read: an earlier iteration may have deleted or rewritten this row.
        fresh = _fetch_eq("user_continue_watching", "*",
                          {"user_id": snapshot["user_id"], "franchise_key": snapshot["franchise_key"]},
                          ("user_id", "franchise_key"))
        if not fresh:
            continue
        r = fresh[0]
        changes: dict = {}
        if r.get("episode_id") in id_map:
            changes.update(episode_id=id_map[r["episode_id"]], series_id=owner_id)
            if r["franchise_key"] != owner_key:
                changes["franchise_key"] = owner_key
        if r.get("next_episode_id") in id_map:
            changes["next_episode_id"] = id_map[r["next_episode_id"]]
        if not changes:
            continue
        if "franchise_key" in changes:
            existing = _fetch_eq("user_continue_watching", "*",
                                 {"user_id": r["user_id"], "franchise_key": owner_key},
                                 ("user_id", "franchise_key"))
            if existing:
                if released_wins(r, existing[0]):
                    client.table("user_continue_watching").delete() \
                        .eq("user_id", r["user_id"]).eq("franchise_key", owner_key).execute()
                else:
                    client.table("user_continue_watching").delete() \
                        .eq("user_id", r["user_id"]).eq("franchise_key", r["franchise_key"]).execute()
                    continue
        client.table("user_continue_watching").update(changes) \
            .eq("user_id", r["user_id"]).eq("franchise_key", r["franchise_key"]).execute()


def apply_page(plan: dict) -> str:
    """Run steps (a)-(e) for one planned page. Returns ``applied`` / ``failed``
    / ``owner_missing_numbers``. Never raises."""
    slug, owner_id = plan["slug"], plan["owner"]
    client = storage.get_client()
    try:
        # (a) release the slugs
        for upd in plan["slug_updates"]:
            client.table("series").update(
                {"principal_slug": upd["principal_slug"], "fallback_slug": upd["fallback_slug"]}
            ).eq("id", upd["series_id"]).execute()
            print(f"  (a) {upd['series_id']}: slugs -> {upd['principal_slug']}/{upd['fallback_slug']}")

        # (b) recover the owner (ADR-011 path)
        if plan["needs_recovery"]:
            owner = plan["owner_row"]
            current = [e["episode_number"] for e in _fetch_episodes([owner_id])[owner_id]]
            # The forward path has no lower bound at the offset: start at least
            # at the offset so sharers' numbers are never re-claimed.
            start = max(max(current) if current else 0, plan["offset"] or 0)
            added = simulcast_check.run_simulcast_update(
                owner_id, slug, start,
                mode="grace", backfill_mode="write",
                franchise_id=owner.get("franchise_id"), expected=owner.get("episode_count"),
            )
            print(f"  (b) recovery for {owner_id}: forward added={added}")
        else:
            print("  (b) recovery skipped: owner already has every released number")

        # (c) verify every referenced released number exists for the owner
        owner_eps = {e["episode_number"]: e["id"] for e in _fetch_episodes([owner_id])[owner_id]}
        released = {e["id"]: e["number"] for e in plan["released_eps"]}
        refs = _fetch_references(list(released))
        needed = {released[r[c]] for (t, c), rows in refs.items() for r in rows if r.get(c) in released}
        missing = sorted(needed - set(owner_eps))
        if missing:
            print(f"  FAILED page {slug}: owner {owner_id} lacks referenced numbers {missing}; "
                  "no remap/deletion done")
            return "owner_missing_numbers"
        id_map = {eid: owner_eps[num] for eid, num in released.items() if num in owner_eps}

        # (d) remap references
        _remap_watch_progress(refs[("watch_progress", "episode_id")], id_map, owner_id)
        ucw: dict[tuple, dict] = {}
        for col in ("episode_id", "next_episode_id"):
            for r in refs[("user_continue_watching", col)]:
                ucw[(r["user_id"], r["franchise_key"])] = r
        owner_key = plan["owner_row"].get("franchise_id") or owner_id
        _remap_continue_watching(list(ucw.values()), id_map, owner_id, owner_key)
        left = _fetch_references(list(released))
        if any(rows for rows in left.values()):
            print(f"  FAILED page {slug}: references remain after remap; nothing deleted")
            return "failed"
        print(f"  (d) remapped {sum(len(r) for r in refs.values())} reference rows")

        # (e) delete the released episodes
        ids = list(released)
        for i in range(0, len(ids), _ID_CHUNK):
            client.table("episodes").delete().in_("id", ids[i:i + _ID_CHUNK]).execute()
        print(f"  (e) deleted {len(ids)} released episodes")
        return "applied"
    except Exception as exc:
        print(f"  FAILED page {slug}: {exc}")
        return "failed"


def _confirm(count: int) -> bool:
    try:
        answer = input(f"Apply repair to {count} pages? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def repair_main(plan_path: str, apply: bool = False, assume_yes: bool = False) -> int:
    """Plan (always) and optionally apply. Returns the exit code."""
    try:
        pages = load_plan(plan_path)
    except PlanError as exc:
        print(f"Invalid plan: {exc}")
        return 2

    columns = discover_reference_columns()
    _print_discovery(columns)
    plans = build_plans(pages, columns)
    rows = []
    for p in plans:
        _print_plan(p)
        rows.extend(plan_rows(p, columns))
    print(f"Wrote {len(rows)} rows -> {_write_csv(rows)}")
    if not apply:
        return 0

    unhandled = [c for c in columns if not c["handled"]]
    if unhandled:
        print("Refusing --apply: columns referencing episodes.id without a handler: "
              + ", ".join(f"{c['table']}.{c['column']}" for c in unhandled))
        return 1

    todo = [p for p in plans if p["status"] == "ok" and p["todo"]]
    ready = [p for p in plans if p["status"] == "ok" and not p["todo"]]
    for p in todo:
        print(f"  refused {p['slug']}: plan has a todo ({p['todo']})")
    skipped = [p for p in plans if p["status"] not in ("ok",)]
    if not ready:
        print("No pages with status=ok and no todo; nothing to apply.")
        return 0
    if not assume_yes and not _confirm(len(ready)):
        print("Aborted, nothing written.")
        return 0

    outcomes = []
    for p in ready:
        print(f"Applying page {p['slug']} (owner {p['owner']})...")
        outcomes.append(apply_page(p))
    failed = len(outcomes) - outcomes.count("applied")
    print(f"Summary: applied={outcomes.count('applied')} failed={failed} "
          f"skipped={len(todo) + len(skipped)}")
    return 1 if failed else 0


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shared-slug repair tool (see module docstring).")
    parser.add_argument("--plan", required=True, help="path to the JSON repair plan")
    parser.add_argument("--apply", action="store_true", help="write the planned repair")
    parser.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    args = parser.parse_args(argv)
    if args.yes and not args.apply:
        parser.error("--yes requires --apply")
    return repair_main(args.plan, apply=args.apply, assume_yes=args.yes)


if __name__ == "__main__":
    sys.exit(cli())
