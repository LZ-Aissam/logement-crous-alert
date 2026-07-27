"""Process a GitHub Issue Form submission to add a new search to searches.json."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

import requests

GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/"
GEOCODE_TIMEOUT = 20

# Half-spans (degrees) around a city's center, matching the zone size used for the
# original Brest search -- a reasonable default for most French cities. Larger cities
# may need a bigger zone; edit the URL in searches.json by hand afterward if so.
DEFAULT_HALF_LAT_SPAN = 0.0511
DEFAULT_HALF_LON_SPAN = 0.0705

TOOL_ID = 47


class GeocodeError(Exception):
    """Raised when a city cannot be geocoded."""


def geocode_city(city: str) -> tuple[float, float]:
    try:
        response = requests.get(
            GEOCODE_URL,
            params={"q": city, "type": "municipality", "limit": 1},
            timeout=GEOCODE_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeocodeError(f"network error geocoding {city!r}: {exc}") from exc
    if response.status_code != 200:
        raise GeocodeError(f"unexpected status {response.status_code} geocoding {city!r}")
    data = response.json()
    features = data.get("features") or []
    if not features:
        raise GeocodeError(f"no municipality found for {city!r}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return lon, lat


def build_search_url(lon: float, lat: float, location_label: str) -> str:
    west = lon - DEFAULT_HALF_LON_SPAN
    east = lon + DEFAULT_HALF_LON_SPAN
    north = lat + DEFAULT_HALF_LAT_SPAN
    south = lat - DEFAULT_HALF_LAT_SPAN
    bounds = f"{west}_{north}_{east}_{south}"
    location_name = urllib.parse.quote(location_label)
    return (
        f"https://trouverunlogement.lescrous.fr/tools/{TOOL_ID}/search"
        f"?bounds={bounds}&locationName={location_name}"
    )


_SECTION_RE = re.compile(r"^### (.+?)\s*$", re.M)


def parse_issue_form_body(body: str) -> dict[str, str | None]:
    matches = list(_SECTION_RE.finditer(body))
    result: dict[str, str | None] = {}
    for i, match in enumerate(matches):
        label = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        value = body[start:end].strip()
        result[label] = None if value == "_No response_" else (value or None)
    return result


def discover_filters(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    residences = sorted(
        {
            (item.get("residence") or {}).get("label")
            for item in items
            if (item.get("residence") or {}).get("label")
        }
    )
    labels = sorted({item.get("label") for item in items if item.get("label")})
    return residences, labels
