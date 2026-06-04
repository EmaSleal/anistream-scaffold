"""
Category reassignment tool.

Uses verified items from data/sample_100.json as ground truth
to reclassify all products in the DB using TF-IDF scoring.

Usage:
  python tools/reassign_categories.py           # dry run (preview only)
  python tools/reassign_categories.py --apply   # update DB
  python tools/reassign_categories.py --min-confidence 0.4
"""

import argparse
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict

DB_PATH = "data/data.db"
SAMPLE_PATH = "data/sample_100.json"
DEFAULT_MIN_CONFIDENCE = 0.45

STOPWORDS = {"de", "la", "el", "los", "las", "con", "para", "sin", "por",
             "and", "the", "with", "for", "rgb", "negro", "blanco", "gris"}

# Keyword anchors: if ANY token matches, assign that category directly (bypasses TF-IDF).
# Order matters for overlapping cases — first match wins.
KEYWORD_ANCHORS: list[tuple[str, list[str]]] = [
    # MiniPC before Pc Gaming: "Pc Mini ..." should not → Pc Gaming
    ("MiniPC",         ["mini pc", "pc mini"]),
    # Complete PCs before GPUs: "Pc Gaming ... RTX" should not → GPUs
    ("Pc Gaming",      ["pc gaming", "pc professional"]),
    # GPUs before RAM: GPU cards mention "ddr3/ddr5" as video memory spec
    ("GPUs",           ["rtx", "radeon", "geforce", "gddr5", "gddr6", "gddr3"]),
    ("RAM",            ["ddr3", "ddr4", "ddr5", "sodimm", "dimm"]),
    ("Almacenamiento", ["microsd", "micro sd", "memoria usb", "pendrive", "nvme"]),
    ("Redes",          ["router"]),
    ("Juguetes",       ["fischer"]),
]


def check_anchors(raw_name: str) -> str | None:
    """Return the anchored category if a keyword matches, else None."""
    tokens = set(tokenize(raw_name))
    # also check raw lowercase for multi-word anchors like 'micro sd'
    raw_lower = raw_name.lower()
    for category, keywords in KEYWORD_ANCHORS:
        for kw in keywords:
            if kw in tokens or kw in raw_lower:
                return category
    return None


def tokenize(text: str) -> list[str]:
    tokens = re.sub(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ0-9]", " ", text.lower()).split()
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS]


def build_model(verified: list[dict]) -> tuple[dict, dict, int]:
    cat_profiles: dict[str, Counter] = defaultdict(Counter)

    for item in verified:
        tokens = tokenize(item["raw_name"])
        for t in tokens:
            cat_profiles[item["category"]][t] += 1

    # token → number of categories that contain it
    token_cat_count: Counter = Counter()
    for profile in cat_profiles.values():
        for token in profile:
            token_cat_count[token] += 1

    return dict(cat_profiles), token_cat_count, len(cat_profiles)


def score_product(raw_name: str, cat_profiles: dict, token_cat_count: Counter,
                  num_cats: int) -> tuple[str | None, float, dict]:
    tokens = tokenize(raw_name)
    if not tokens:
        return None, 0.0, {}

    scores: dict[str, float] = {}
    for cat, profile in cat_profiles.items():
        total_tokens_in_cat = sum(profile.values()) or 1
        s = 0.0
        for t in tokens:
            if t in profile:
                tf = profile[t] / total_tokens_in_cat
                idf = math.log((num_cats + 1) / (token_cat_count[t] + 1))
                s += tf * idf
        scores[cat] = s

    total = sum(scores.values())
    if total == 0:
        return None, 0.0, scores

    best_cat = max(scores, key=scores.get)
    confidence = scores[best_cat] / total
    return best_cat, confidence, scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Write changes to DB (default: dry run)")
    parser.add_argument("--min-confidence", type=float,
                        default=DEFAULT_MIN_CONFIDENCE,
                        help=f"Minimum confidence to reassign (default: {DEFAULT_MIN_CONFIDENCE})")
    args = parser.parse_args()

    with open(SAMPLE_PATH, encoding="utf-8") as f:
        sample = json.load(f)

    verified = [r for r in sample if r["verified"]]
    print(f"Ground truth: {len(verified)} verified items across "
          f"{len({r['category'] for r in verified})} categories\n")

    cat_profiles, token_cat_count, num_cats = build_model(verified)

    # IDs protected from reassignment (already verified by user)
    protected_ids = {r["id"] for r in verified}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, raw_name, category FROM products")
    products = cur.fetchall()

    changes: list[tuple[int, str, str, float]] = []  # (id, old_cat, new_cat, confidence)
    uncertain: list[tuple[int, str, float]] = []
    protected_count = 0

    for row in products:
        pid, raw_name, old_cat = row["id"], row["raw_name"], row["category"]

        if pid in protected_ids:
            protected_count += 1
            continue

        anchored = check_anchors(raw_name)
        if anchored is not None:
            new_cat, confidence = anchored, 1.0
        else:
            new_cat, confidence, _ = score_product(
                raw_name, cat_profiles, token_cat_count, num_cats
            )

        if new_cat is None:
            uncertain.append((pid, raw_name, 0.0))
        elif confidence < args.min_confidence:
            uncertain.append((pid, raw_name, confidence))
        elif new_cat != old_cat:
            changes.append((pid, old_cat, new_cat, confidence))

    # --- Report ---
    print(f"{'='*60}")
    print(f"DRY RUN" if not args.apply else "APPLYING CHANGES")
    print(f"{'='*60}")
    print(f"Total products in DB : {len(products)}")
    print(f"Protected (verified) : {protected_count}")
    print(f"Would reassign       : {len(changes)}")
    print(f"Uncertain (skipped)  : {len(uncertain)}")
    print()

    if changes:
        # Group by old_cat → new_cat
        change_summary: Counter = Counter()
        for _, old, new, _ in changes:
            change_summary[(old, new)] += 1

        print("Changes by category:")
        for (old, new), count in sorted(change_summary.items(), key=lambda x: -x[1]):
            print(f"  {old:25s} -> {new:25s}  ({count} products)")
        print()

        print("Sample changes (up to 10):")
        for pid, old, new, conf in sorted(changes, key=lambda x: -x[3])[:10]:
            cur.execute("SELECT raw_name FROM products WHERE id=?", (pid,))
            name = cur.fetchone()["raw_name"]
            print(f"  [{conf:.0%}] {name[:55]:<55}  {old} -> {new}")
        print()

    if uncertain[:5]:
        print(f"Sample uncertain (confidence below {args.min_confidence:.0%}):")
        for pid, name, conf in uncertain[:5]:
            print(f"  [{conf:.0%}] {name[:70]}")
        print()

    if args.apply:
        if not changes:
            print("Nothing to update.")
        else:
            cur.executemany(
                "UPDATE products SET category=? WHERE id=?",
                [(new, pid) for pid, _, new, _ in changes]
            )
            conn.commit()
            print(f"Done. {len(changes)} products updated in DB.")
    else:
        print("Run with --apply to commit changes to DB.")

    conn.close()


if __name__ == "__main__":
    main()
