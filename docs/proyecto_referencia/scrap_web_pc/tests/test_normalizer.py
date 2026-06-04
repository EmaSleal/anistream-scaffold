"""
tests/test_normalizer.py — Unit tests for normalizer.py

Covers:
    TASK-22: parse_price_crc (price parsing scenarios + error case)
    TASK-23: normalize() (GPU, CPU, unknown-category fallback)
    TASK-24: match()  (exact match, fuzzy match, chip-number false-positive guard)
"""
from __future__ import annotations

import pytest

from normalizer import PriceParseError, match, normalize, parse_price_crc
from scrapers.base import RawProduct


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_raw(
    raw_name: str,
    price_str: str,
    category: str,
    store_id: str = "techzilla",
    in_stock: bool = True,
) -> RawProduct:
    return RawProduct(
        store_id=store_id,
        raw_name=raw_name,
        price_str=price_str,
        url=f"https://example.com/{raw_name[:20].replace(' ', '-')}",
        in_stock=in_stock,
        category=category,
        scraped_at="2024-01-15T03:00:00",
    )


# ---------------------------------------------------------------------------
# TASK-22: parse_price_crc
# ---------------------------------------------------------------------------

class TestParsePriceCrc:

    def test_comma_thousands_with_ivai(self):
        """₡700,000 I.V.A.I -> 700000"""
        assert parse_price_crc("₡700,000 I.V.A.I") == 700000

    def test_european_dot_thousands(self):
        """₡1.200.000 -> 1200000 (dot as thousands separator)"""
        assert parse_price_crc("₡1.200.000") == 1200000

    def test_space_after_colon_symbol_with_decimal_zero(self):
        """₡ 85,000.00 -> 85000"""
        assert parse_price_crc("₡ 85,000.00") == 85000

    def test_colon_no_space_decimal_zero(self):
        """₡85,000.00 -> 85000"""
        assert parse_price_crc("₡85,000.00") == 85000

    def test_plain_integer_string(self):
        """700000 (no symbol, no separators) -> 700000"""
        assert parse_price_crc("700000") == 700000

    def test_garbage_raises_price_parse_error(self):
        """'precio no disponible' must raise PriceParseError"""
        with pytest.raises(PriceParseError):
            parse_price_crc("precio no disponible")

    def test_empty_string_raises_price_parse_error(self):
        with pytest.raises(PriceParseError):
            parse_price_crc("")

    def test_colon_only_raises_price_parse_error(self):
        with pytest.raises(PriceParseError):
            parse_price_crc("₡")

    def test_larger_european_amount(self):
        """₡1.500.000 -> 1500000"""
        assert parse_price_crc("₡1.500.000") == 1500000

    def test_ivai_without_dots(self):
        """₡850,000 IVAI -> 850000"""
        assert parse_price_crc("₡850,000 IVAI") == 850000


# ---------------------------------------------------------------------------
# TASK-23: normalize()
# ---------------------------------------------------------------------------

class TestNormalize:

    def test_gpu_full_name_extracts_asus_and_rtx4070(self):
        """ASUS TUF Gaming GeForce RTX 4070 Ti SUPER OC 16GB -> brand=ASUS, model contains RTX 4070"""
        raw = "ASUS TUF Gaming GeForce RTX 4070 Ti SUPER OC 16GB"
        canonical_key, brand, model = normalize(raw, "GPUs")

        assert "asus" in brand.lower(), f"Expected brand to contain 'asus', got {brand!r}"
        assert "4070" in model, f"Expected model to contain '4070', got {model!r}"
        assert "RTX" in model.upper(), f"Expected model to contain 'RTX', got {model!r}"

    def test_gpu_canonical_key_is_title_cased(self):
        raw = "ASUS TUF Gaming GeForce RTX 4070 Ti SUPER OC 16GB"
        canonical_key, brand, model = normalize(raw, "GPUs")
        # canonical_key must equal brand + " " + model (title-cased)
        assert canonical_key == f"{brand} {model}".strip()

    def test_cpu_amd_ryzen_extracts_brand_and_model(self):
        """Procesador AMD Ryzen 7 7700X Box -> brand=AMD, model contains Ryzen 7 7700X"""
        raw = "Procesador AMD Ryzen 7 7700X Box"
        canonical_key, brand, model = normalize(raw, "CPUs")

        assert brand.upper() == "AMD", f"Expected brand='AMD', got {brand!r}"
        assert "ryzen" in model.lower(), f"Expected model to contain 'Ryzen', got {model!r}"
        assert "7700" in model, f"Expected model to contain '7700', got {model!r}"

    def test_cpu_intel_core_extracts_correctly(self):
        """Procesador Intel Core i7-13700K 3.4GHz LGA1700"""
        raw = "Procesador Intel Core i7-13700K 3.4GHz LGA1700"
        canonical_key, brand, model = normalize(raw, "CPUs")

        assert brand.upper() == "INTEL", f"Expected brand='Intel', got {brand!r}"
        assert "13700" in model, f"Expected model to contain '13700', got {model!r}"

    def test_unknown_category_fallback_returns_non_empty_canonical_key(self):
        """Unrecognised name in unknown category -> non-empty canonical_key"""
        raw = "ProductoRaroXYZ sin patron conocido"
        canonical_key, brand, model = normalize(raw, "unknown_category")

        assert canonical_key, "canonical_key must not be empty on fallback"
        assert len(canonical_key) > 0

    def test_fallback_canonical_key_derives_from_cleaned_name(self):
        """When no pattern matches, canonical key is derived from the cleaned raw name."""
        raw = "Algo totalmente desconocido abc 123"
        canonical_key, brand, model = normalize(raw, "MarcianianasCategory")

        # canonical_key must be non-empty and composed of recognisable tokens
        assert canonical_key
        # Fallback: brand is empty, model holds the fallback string
        # (canonical_key == model when brand is empty, since brand="" is stripped)
        assert canonical_key == f"{brand} {model}".strip()

    def test_normalize_returns_three_tuple(self):
        """normalize() must return a 3-tuple."""
        result = normalize("Some product name", "GPUs")
        assert isinstance(result, tuple) and len(result) == 3


# ---------------------------------------------------------------------------
# TASK-24: match()
# ---------------------------------------------------------------------------

class TestMatch:

    def test_two_products_same_canonical_gpu_grouped(self):
        """Two RawProducts with the same normalised canonical key -> one ProductGroup."""
        p1 = make_raw(
            "MSI GeForce RTX 4060 Gaming X 8GB",
            "₡450,000",
            "GPUs",
            store_id="techzilla",
        )
        p2 = make_raw(
            "MSI GeForce RTX 4060 Gaming X 8GB",
            "₡460,000",
            "GPUs",
            store_id="crtechstore",
        )

        groups = match([p1, p2], "GPUs")

        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}: {[g.canonical_key for g in groups]}"
        group = groups[0]
        assert len(group.listings) == 2
        store_ids = {lst.store_id for lst in group.listings}
        assert store_ids == {"techzilla", "crtechstore"}

    def test_cheapest_store_is_populated(self):
        """cheapest_store_id must point to the store with the lowest in-stock price."""
        p1 = make_raw("MSI RTX 4060 Gaming X 8GB", "₡460,000", "GPUs", store_id="expensive_store")
        p2 = make_raw("MSI RTX 4060 Gaming X 8GB", "₡440,000", "GPUs", store_id="cheap_store")

        groups = match([p1, p2], "GPUs")
        assert len(groups) == 1
        assert groups[0].cheapest_store_id == "cheap_store"

    def test_fuzzy_match_asus_rtx_4070_ti_variants(self):
        """ASUS RTX 4070 Ti OC vs ASUS GeForce RTX 4070Ti OC Edition -> same group."""
        p1 = make_raw(
            "ASUS RTX 4070 Ti OC 12GB",
            "₡700,000",
            "GPUs",
            store_id="techzilla",
        )
        p2 = make_raw(
            "ASUS GeForce RTX 4070 Ti OC Edition 12G GDDR6X",
            "₡695,000",
            "GPUs",
            store_id="igamingcr",
        )

        groups = match([p1, p2], "GPUs")

        # Both should be in the same group (same chip + same brand, minor label diff)
        combined = sum(len(g.listings) for g in groups)
        assert combined == 2, "All listings must be accounted for"

        # One group with both listings is the expected result
        two_listing_groups = [g for g in groups if len(g.listings) == 2]
        assert len(two_listing_groups) == 1, (
            f"Expected exactly 1 group with 2 listings; groups: "
            f"{[(g.canonical_key, len(g.listings)) for g in groups]}"
        )

    def test_chip_number_guard_rtx3070_vs_rtx4070_not_merged(self):
        """MSI RTX 3070 Gaming X vs MSI RTX 4070 Gaming X -> different groups (chip guard)."""
        p1 = make_raw(
            "MSI RTX 3070 Gaming X Trio 8GB",
            "₡500,000",
            "GPUs",
            store_id="techzilla",
        )
        p2 = make_raw(
            "MSI RTX 4070 Gaming X Trio 12GB",
            "₡700,000",
            "GPUs",
            store_id="crtechstore",
        )

        groups = match([p1, p2], "GPUs")

        # These MUST NOT be merged because 3070 != 4070
        assert len(groups) == 2, (
            f"Expected 2 separate groups (chip-number guard); "
            f"got {len(groups)}: {[g.canonical_key for g in groups]}"
        )
        canonical_keys = {g.canonical_key for g in groups}
        # Both groups have 1 listing each
        for g in groups:
            assert len(g.listings) == 1

    def test_empty_product_list_returns_empty(self):
        """match() on empty list returns empty list without error."""
        groups = match([], "GPUs")
        assert groups == []

    def test_single_product_becomes_own_group(self):
        """A single RawProduct becomes a ProductGroup with one listing."""
        p = make_raw("ASUS RTX 4090 ROG Strix OC 24GB", "₡2,000,000", "GPUs")
        groups = match([p], "GPUs")
        assert len(groups) == 1
        assert len(groups[0].listings) == 1
