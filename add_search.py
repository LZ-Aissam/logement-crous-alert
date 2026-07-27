"""Process a GitHub Issue Form submission to add a new search to searches.json."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from typing import Any

import requests

import check_logement as clog

GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/"
GEOCODE_TIMEOUT = 20

# Half-spans (degrees) around a city's center, matching the zone size used for the
# original Brest search -- a reasonable default for most French cities. Larger cities
# may need a bigger zone; edit the URL in searches.json by hand afterward if so.
DEFAULT_HALF_LAT_SPAN = 0.0511
DEFAULT_HALF_LON_SPAN = 0.0705

TOOL_ID = 47

FIELD_NAME = "Nom de la recherche"
FIELD_CITY = "Ville"
FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel"
FIELD_EMAILS = "Email(s) de notification - optionnel"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    try:
        data = response.json()
        features = data.get("features") or []
        if not features:
            raise GeocodeError(f"no municipality found for {city!r}")
        lon, lat = features[0]["geometry"]["coordinates"]
    except GeocodeError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise GeocodeError(f"unexpected response format geocoding {city!r}: {exc}") from exc
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


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)

    name = fields.get(FIELD_NAME)
    city = fields.get(FIELD_CITY)
    keywords_raw = fields.get(FIELD_KEYWORDS)
    emails_raw = fields.get(FIELD_EMAILS)

    if not name or not city:
        print("ERROR: le nom de la recherche et la ville sont obligatoires")
        return 1

    if clog.SEARCHES_PATH.exists():
        try:
            searches = clog.load_searches()
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: impossible de lire searches.json existant : {exc}")
            return 1
    else:
        searches = []

    if any(s["name"].strip().lower() == name.strip().lower() for s in searches):
        print(f"ERROR: une recherche nommee {name!r} existe deja dans searches.json")
        return 1

    try:
        lon, lat = geocode_city(city)
    except GeocodeError as exc:
        print(f"ERROR: {exc}")
        return 1

    url = build_search_url(lon, lat, city)
    keywords = _split_csv(keywords_raw)
    emails = _split_csv(emails_raw)

    invalid_emails = [e for e in emails if not EMAIL_RE.match(e)]
    if invalid_emails:
        print(f"ERROR: adresse(s) email invalide(s) : {', '.join(invalid_emails)}")
        return 1

    try:
        html = clog.fetch_html(url)
        results = clog.parse_search_results(html)
        items = results.get("items") or []
    except clog.SearchFetchError:
        items = []

    residences, labels = discover_filters(items)

    discovered = [r.lower() for r in residences] + [l.lower() for l in labels]
    warnings = [
        kw for kw in keywords if discovered and not any(kw.lower() in d for d in discovered)
    ]

    entry: dict[str, Any] = {"name": name, "url": url}
    if keywords:
        entry["keywords"] = keywords
    if emails:
        entry["emails"] = emails

    searches.append(entry)
    clog.save_searches(searches)

    lines = [f"OK: recherche {name!r} ajoutee pour {city!r}.", f"URL : {url}"]
    if keywords:
        lines.append(f"Mots-cles : {', '.join(keywords)}")
    if warnings:
        lines.append(
            "AVERTISSEMENT: ces mots-cles ne correspondent a rien de disponible "
            f"actuellement (peut etre normal si rien n'est libre en ce moment) : "
            f"{', '.join(warnings)}"
        )
    if residences or labels:
        lines.append(
            "Residences/types actuellement disponibles dans cette zone (pour verifier "
            f"l'orthographe) : residences={residences or '(aucune)'}, "
            f"types={labels or '(aucun)'}"
        )
    else:
        lines.append(
            "Aucun logement disponible actuellement dans cette zone : impossible de "
            "suggerer une liste de residences/types pour l'instant."
        )
    lines.append(
        f"Destinataires : {', '.join(emails)}" if emails else "Destinataire : email par defaut (ALERT_EMAIL)"
    )

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
