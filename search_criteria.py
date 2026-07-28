"""Canonical representation of a search's criteria, used for duplicate detection.

Mirrored byte-for-byte in behavior by netlify/functions/_criteria.js -- any change
here must be applied there too.
"""
from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_city(city: str | None) -> str:
    if not city:
        return ""
    return _WHITESPACE_RE.sub(" ", city.strip()).lower()


def build_criteria(
    *,
    city: str | None,
    extent: str | None,
    max_price: int | None,
    min_area: int | None,
    occupation_modes: list[str],
    prm: bool,
) -> dict[str, Any]:
    return {
        "extent": (extent or "").strip(),
        "city": normalize_city(city),
        "maxPrice": max_price,
        "minArea": min_area,
        "occupationModes": sorted(set(occupation_modes)),
        "prm": bool(prm),
    }


def criteria_match(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    # An extent describes the exact search area; two identical extents mean the same
    # zone even when the typed city label differs. Fall back to the city otherwise.
    if a.get("extent") and b.get("extent"):
        if a["extent"] != b["extent"]:
            return False
    elif a.get("city") != b.get("city"):
        return False
    return (
        a.get("maxPrice") == b.get("maxPrice")
        and a.get("minArea") == b.get("minArea")
        and sorted(a.get("occupationModes") or []) == sorted(b.get("occupationModes") or [])
        and bool(a.get("prm")) == bool(b.get("prm"))
    )
