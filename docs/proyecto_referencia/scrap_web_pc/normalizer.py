"""
normalizer.py — Product name normalisation and cross-store matching.

Public API:
    PriceParseError          — raised when a price string cannot be parsed
    parse_price_crc(text)    — strip ₡/separators/labels; return integer colones
    normalize(raw_name, category) -> (canonical_key, brand, model)
    match(products, category) -> list[ProductGroup]
"""
from __future__ import annotations

import logging
import re
from typing import Sequence

from config import FUZZY_THRESHOLD
from scrapers.base import CanonicalProduct, ProductGroup, RawProduct

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PriceParseError(ValueError):
    """Raised when a price string cannot be converted to an integer amount."""


# ---------------------------------------------------------------------------
# Price parsing — module-level compiled patterns
# ---------------------------------------------------------------------------

# Strip: colón symbol, spaces, I.V.A.I / IVAI / IVA labels
_RE_PRICE_STRIP = re.compile(
    r"₡"                      # colón sign
    r"|\bI\.V\.A\.I\b"        # "I.V.A.I" with word boundary
    r"|\bIVAI\b"
    r"|\bIVA\b",
    re.IGNORECASE,
)

# Detect European-style thousands: digit DOT digit DOT digit  (e.g. 1.200.000)
# Must have at least two consecutive dot-groups of exactly 3 digits.
_RE_EUR_THOUSANDS = re.compile(r"^\d{1,3}(?:\.\d{3})+$")

# After cleaning, we expect only digits (and optionally a final ".00" decimal)
_RE_DECIMAL_ZERO = re.compile(r"\.00$")


def parse_price_crc(price_str: str) -> int:
    """Parse a Costa Rican colones price string to an integer.

    Handles:
    - "₡700,000 I.V.A.I"   -> 700000
    - "₡1.200.000"          -> 1200000  (European dot-thousands)
    - "₡ 85,000.00"         -> 85000
    - "₡85,000.00"          -> 85000
    - "700000"              -> 700000   (plain integer)

    Raises PriceParseError if the result is not a positive integer.
    """
    cleaned = _RE_PRICE_STRIP.sub("", price_str).strip()

    # Remove insignificant decimal ".00"
    cleaned = _RE_DECIMAL_ZERO.sub("", cleaned)

    # Decide separator convention based on what remains.
    # European-dots: "1.200.000" → all dots are thousands separators
    if _RE_EUR_THOUSANDS.match(cleaned):
        cleaned = cleaned.replace(".", "")
    else:
        # Comma is the thousands separator (Costa Rican convention: 700,000)
        # A trailing ".XX" (non-zero) would be real decimal cents — for now strip
        cleaned = cleaned.replace(",", "")
        # Remove any residual dots (shouldn't be present after stripping IVA etc.)
        cleaned = cleaned.replace(".", "")

    cleaned = cleaned.strip()

    if not cleaned.isdigit():
        raise PriceParseError(
            f"Cannot parse price string {price_str!r}: "
            f"cleaned result {cleaned!r} is not numeric"
        )

    value = int(cleaned)
    if value <= 0:
        raise PriceParseError(
            f"Cannot parse price string {price_str!r}: "
            f"result {value} is not a positive integer"
        )

    return value


# ---------------------------------------------------------------------------
# Normalisation — per-category brand + model regex (compiled at module level)
# ---------------------------------------------------------------------------

# GPU brands (case-insensitive matching)
_GPU_BRANDS = (
    "ASUS", "Gigabyte", "MSI", "Sapphire", "XFX", "Zotac",
    "PowerColor", "EVGA", "PNY", "Palit", "Inno3D",
)
_RE_GPU_BRAND = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _GPU_BRANDS) + r")\b",
    re.IGNORECASE,
)
_RE_GPU_MODEL = re.compile(
    r"\b("
    r"RTX\s*\d{4}(?:\s*Ti)?(?:\s*Super)?"
    r"|GTX\s*\d{4}(?:\s*Ti)?"
    r"|RX\s*\d{4}(?:\s*XT)?"
    r"|Arc\s+\w+"
    r")\b",
    re.IGNORECASE,
)

# CPU brands and models
_CPU_BRANDS = ("Intel", "AMD")
_RE_CPU_BRAND = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _CPU_BRANDS) + r")\b",
    re.IGNORECASE,
)
_RE_CPU_MODEL = re.compile(
    r"\b("
    r"i[3579]-\d{4,5}\w*"
    r"|Ryzen\s+[3579]\s+\d{4}\w*"
    r"|Core\s+Ultra\s+\d+\s+\d+\w*"
    r")\b",
    re.IGNORECASE,
)

# RAM brands and specs
_RAM_BRANDS = (
    "Kingston", "Corsair", "G.Skill", "Crucial",
    "TeamGroup", "HyperX", "Patriot",
)
_RE_RAM_BRAND = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _RAM_BRANDS) + r")\b",
    re.IGNORECASE,
)
_RE_RAM_SPEC = re.compile(
    r"\b(DDR[45]\s+\d+\s*GB(?:\s+\d+\s*MHz)?)\b",
    re.IGNORECASE,
)

# Placa madre (motherboard) brands and chipsets
_MOBO_BRANDS = ("ASUS", "Gigabyte", "MSI", "ASRock", "Biostar")
_RE_MOBO_BRAND = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _MOBO_BRANDS) + r")\b",
    re.IGNORECASE,
)
_RE_MOBO_CHIPSET = re.compile(
    r"\b([ZBXAzxba]\d{3})\b",
    re.IGNORECASE,
)

# Storage: brand + capacity + form-factor tokens
_STORAGE_BRANDS = (
    "Samsung", "WD", "Western Digital", "Seagate", "Kingston",
    "Crucial", "Corsair", "ADATA", "Sabrent", "Lexar",
)
_RE_STORAGE_BRAND = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _STORAGE_BRANDS) + r")\b",
    re.IGNORECASE,
)
_RE_STORAGE_CAPACITY = re.compile(
    r"\b(\d+\s*(?:TB|GB))\b",
    re.IGNORECASE,
)
_RE_STORAGE_TYPE = re.compile(
    r"\b(NVMe|SATA|M\.2|SSD|HDD)\b",
    re.IGNORECASE,
)

# Generic brand extraction: first capitalised word after stripping numbers/junk
_RE_GENERIC_BRAND = re.compile(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)")

# Chip number guard: sequences of 3-4 consecutive digits within a word boundary
_RE_CHIP_NUMBERS = re.compile(r"\b\d{3,4}\b")

# Pre-processing: keep only alphanumeric, spaces, hyphens
_RE_STRIP_SPECIAL = re.compile(r"[^a-z0-9\s\-]")


def _preprocess(text: str) -> str:
    """Lowercase, collapse whitespace, strip special characters."""
    text = text.lower()
    text = _RE_STRIP_SPECIAL.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize(raw_name: str, category: str) -> tuple[str, str, str]:
    """Extract a canonical key from a raw product name.

    Returns (canonical_key, brand, model) where:
      canonical_key = f"{brand} {model}".strip() — title-cased
      brand         — extracted brand name (title-cased), or "" on fallback
      model         — extracted model token (title-cased), or cleaned_name[:60]

    Falls back to brand="" and model=cleaned_raw_name[:60] when no pattern
    matches, and logs a WARNING with the original raw name.
    """
    cleaned = _preprocess(raw_name)

    brand_raw = ""
    model_raw = ""

    cat = category.lower()

    if cat == "gpus":
        bm = _RE_GPU_BRAND.search(cleaned)
        mm = _RE_GPU_MODEL.search(cleaned)
        if bm:
            brand_raw = bm.group(1)
        if mm:
            # Normalise internal spaces in model (e.g. "RTX  4070" -> "RTX 4070")
            model_raw = re.sub(r"\s+", " ", mm.group(1))

    elif cat == "cpus":
        bm = _RE_CPU_BRAND.search(cleaned)
        mm = _RE_CPU_MODEL.search(cleaned)
        if bm:
            brand_raw = bm.group(1)
        if mm:
            model_raw = re.sub(r"\s+", " ", mm.group(1))

    elif cat == "ram":
        bm = _RE_RAM_BRAND.search(cleaned)
        sm = _RE_RAM_SPEC.search(cleaned)
        if bm:
            brand_raw = bm.group(1)
        if sm:
            model_raw = re.sub(r"\s+", " ", sm.group(1))

    elif cat in ("placas madre", "motherboards"):
        bm = _RE_MOBO_BRAND.search(cleaned)
        cm = _RE_MOBO_CHIPSET.search(cleaned)
        if bm:
            brand_raw = bm.group(1)
        if cm:
            model_raw = cm.group(1).upper()

    elif cat == "almacenamiento":
        bm = _RE_STORAGE_BRAND.search(cleaned)
        cap = _RE_STORAGE_CAPACITY.search(cleaned)
        stype = _RE_STORAGE_TYPE.search(cleaned)
        if bm:
            brand_raw = bm.group(1)
        parts = []
        if cap:
            parts.append(re.sub(r"\s+", "", cap.group(1)).upper())
        if stype:
            parts.append(stype.group(1).upper())
        model_raw = " ".join(parts)

    else:
        # Generic categories: Fuentes de poder, Cases, Disipadores, Monitores
        # Extract brand as first known token and first significant model string
        gm = _RE_GENERIC_BRAND.search(raw_name)
        if gm:
            brand_raw = gm.group(1)
        # Use first ~4 tokens after the brand as model
        tokens = cleaned.split()
        brand_tokens = brand_raw.lower().split() if brand_raw else []
        remaining = [t for t in tokens if t not in brand_tokens]
        model_raw = " ".join(remaining[:4])

    # Fallback: if either part is empty, use the cleaned name
    if not brand_raw and not model_raw:
        logger.warning(
            "normalizer: no pattern matched for raw_name=%r category=%r; "
            "using raw-fallback canonical key",
            raw_name,
            category,
        )
        fallback = cleaned[:60]
        return fallback.title(), "", fallback.title()

    # If only model is empty (brand matched but no model token), fall back model too
    if brand_raw and not model_raw:
        logger.warning(
            "normalizer: brand matched but no model for raw_name=%r category=%r",
            raw_name,
            category,
        )
        model_raw = cleaned[:60]

    brand = brand_raw.title()
    model = model_raw.title()
    canonical_key = f"{brand} {model}".strip()

    return canonical_key, brand, model


# ---------------------------------------------------------------------------
# Matching — two-stage grouper
# ---------------------------------------------------------------------------

def _chip_numbers(key: str) -> frozenset[str]:
    """Return the set of 3-4 digit number tokens found in a canonical key."""
    return frozenset(_RE_CHIP_NUMBERS.findall(key))


def match(products: list[RawProduct], category: str) -> list[ProductGroup]:
    """Group RawProducts that refer to the same physical product.

    Stage 1 — exact: normalize each product; group by identical canonical_key.
    Stage 2 — fuzzy: for products whose keys didn't exactly match another, use
               RapidFuzz token_sort_ratio at threshold=FUZZY_THRESHOLD; the
               chip-number guard prevents merging products whose canonical keys
               differ in any 3-4 digit number sequence
               (e.g. RTX 3070 vs RTX 4070 must NOT be grouped together).

    Returns a list[ProductGroup] with cheapest_store_id populated.
    """
    from rapidfuzz.fuzz import token_sort_ratio  # deferred import — not at top level

    if not products:
        return []

    # ------------------------------------------------------------------
    # Pre-normalise all products; store results in a parallel list so we
    # never mutate the frozen RawProduct dataclass instances.
    # ------------------------------------------------------------------
    # Each entry: (canonical_key, brand, model, listing)
    NormEntry = tuple  # (str, str, str, CanonicalProduct)

    norm: list[NormEntry] = []
    for product in products:
        canonical_key, brand, model = normalize(product.raw_name, category)
        listing = CanonicalProduct(
            canonical_key=canonical_key,
            brand=brand,
            model=model,
            category=category,
            store_id=product.store_id,
            url=product.url,
            price_crc=_safe_price(product),
            in_stock=product.in_stock,
            scraped_at=product.scraped_at,
        )
        norm.append((canonical_key, brand, model, listing))

    # ------------------------------------------------------------------
    # Stage 1: build initial groups by exact canonical_key match
    # ------------------------------------------------------------------
    groups: dict[str, ProductGroup] = {}   # canonical_key -> ProductGroup

    for canonical_key, brand, model, listing in norm:
        if canonical_key in groups:
            groups[canonical_key].listings.append(listing)
        else:
            groups[canonical_key] = ProductGroup(
                canonical_key=canonical_key,
                brand=brand,
                model=model,
                category=category,
                listings=[listing],
                cheapest_store_id=None,
            )

    # ------------------------------------------------------------------
    # Stage 2: fuzzy merge across distinct canonical keys
    # ------------------------------------------------------------------
    group_keys = list(groups.keys())
    merged_into: dict[str, str] = {}   # source_key -> target_key

    for i, key_a in enumerate(group_keys):
        if key_a in merged_into:
            continue
        numbers_a = _chip_numbers(key_a)

        for key_b in group_keys[i + 1:]:
            if key_b in merged_into:
                continue

            # Chip-number guard: if both keys have chip numbers and they differ,
            # do NOT merge regardless of fuzzy score
            numbers_b = _chip_numbers(key_b)
            if numbers_a and numbers_b and numbers_a != numbers_b:
                continue

            score = token_sort_ratio(key_a, key_b)
            if score >= FUZZY_THRESHOLD:
                # Merge key_b into key_a (keep the earlier group as primary)
                groups[key_a].listings.extend(groups[key_b].listings)
                merged_into[key_b] = key_a

    # ------------------------------------------------------------------
    # Build final list, excluding merged-away groups
    # ------------------------------------------------------------------
    result: list[ProductGroup] = []
    for key, group in groups.items():
        if key in merged_into:
            continue
        group.cheapest_store_id = _cheapest_store(group)
        result.append(group)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_price(product: RawProduct) -> int:
    """Parse price_str from a RawProduct; return 0 on failure."""
    try:
        return parse_price_crc(product.price_str)
    except PriceParseError:
        logger.warning(
            "normalizer: unparseable price %r for product %r; using 0",
            product.price_str,
            product.raw_name,
        )
        return 0


def _cheapest_store(group: ProductGroup) -> str | None:
    """Return the store_id of the cheapest in-stock listing (or overall min)."""
    if not group.listings:
        return None
    in_stock = [lst for lst in group.listings if lst.in_stock]
    pool = in_stock if in_stock else group.listings
    return min(pool, key=lambda lst: lst.price_crc).store_id
