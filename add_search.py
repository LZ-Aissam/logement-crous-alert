"""Process a GitHub Issue Form submission to add a new search to searches.json."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
import urllib.parse
from pathlib import Path
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
FIELD_EXTENT = "Zone geographique precise (rempli automatiquement) - optionnel"
FIELD_MAX_PRICE = "Prix maximum - optionnel"
FIELD_MIN_AREA = "Surface minimum en m2 - optionnel"
FIELD_OCCUPATION_MODE = "Type de cohabitation (individuel, couple, colocation) - optionnel"
FIELD_PRM = "Logement adapte PMR - optionnel"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EXTENT_RE = re.compile(r"^-?\d+(\.\d+)?_-?\d+(\.\d+)?_-?\d+(\.\d+)?_-?\d+(\.\d+)?$")

VALID_OCCUPATION_MODES = {"alone", "couple", "house_sharing"}

OCCUPATION_MODE_LABELS = {
    "individuel": "alone",
    "couple": "couple",
    "colocation": "house_sharing",
}


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


def build_search_url(
    lon: float | None,
    lat: float | None,
    location_label: str,
    extent: str | None = None,
    max_price: int | None = None,
    min_area: int | None = None,
    occupation_modes: list[str] | None = None,
    prm: bool = False,
) -> str:
    if extent and EXTENT_RE.match(extent):
        bounds = extent
    else:
        west = lon - DEFAULT_HALF_LON_SPAN
        east = lon + DEFAULT_HALF_LON_SPAN
        north = lat + DEFAULT_HALF_LAT_SPAN
        south = lat - DEFAULT_HALF_LAT_SPAN
        bounds = f"{west}_{north}_{east}_{south}"
    location_name = urllib.parse.quote(location_label)
    url = (
        f"https://trouverunlogement.lescrous.fr/tools/{TOOL_ID}/search"
        f"?bounds={bounds}&locationName={location_name}"
    )
    if max_price is not None:
        url += f"&maxPrice={max_price}"
    if min_area is not None:
        url += f"&minArea={min_area}"
    for mode in occupation_modes or []:
        if mode in VALID_OCCUPATION_MODES:
            url += f"&occupationMode={mode}"
    if prm:
        url += "&prm=true"
    return url


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


PENDING_SEARCHES_PATH = Path("pending_searches.json")


def load_pending_searches(path: Path = PENDING_SEARCHES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_pending_searches(pending: dict[str, Any], path: Path = PENDING_SEARCHES_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
        f.write("\n")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_confirmation_url(token: str) -> str:
    base_url = os.environ.get("CONFIRMATION_BASE_URL")
    if base_url:
        return f"{base_url}?code={urllib.parse.quote(token)}"
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    return (
        f"https://github.com/{repo}/issues/new"
        f"?template=confirm-email.yml&code={urllib.parse.quote(token)}"
    )


def build_confirmation_email_body(search_name: str, confirmation_url: str) -> str:
    return (
        "Quelqu'un a demande a recevoir des alertes de logement CROUS a cette adresse "
        f"email, pour la recherche {search_name!r}.\n\n"
        "Si c'est bien toi, confirme en cliquant sur ce lien :\n"
        f"{confirmation_url}\n\n"
        "Si tu n'es pas a l'origine de cette demande, ignore simplement cet email -- "
        "rien ne sera active sans ta confirmation."
    )


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

    if PENDING_SEARCHES_PATH.exists():
        try:
            pending = load_pending_searches()
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: impossible de lire pending_searches.json existant : {exc}")
            return 1
    else:
        pending = {}
    existing_names = {s["name"].strip().lower() for s in searches} | {
        n.strip().lower() for n in pending
    }
    if name.strip().lower() in existing_names:
        print(f"ERROR: une recherche nommee {name!r} existe deja")
        return 1

    try:
        lon, lat = geocode_city(city)
    except GeocodeError as exc:
        print(f"ERROR: {exc}")
        return 1

    url = build_search_url(lon, lat, city)
    keywords = _split_csv(keywords_raw)
    emails = _split_csv(emails_raw)

    seen_lower = set()
    deduped_emails = []
    for e in emails:
        if e.lower() not in seen_lower:
            seen_lower.add(e.lower())
            deduped_emails.append(e)
    emails = deduped_emails

    if len(emails) > 3:
        print(f"ERROR: trop d'adresses email soumises (max 3, recu {len(emails)})")
        return 1

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

    lines = [f"URL : {url}"]
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

    if emails:
        smtp_host = clog._require_env("SMTP_HOST")
        smtp_port = int(clog._require_env("SMTP_PORT"))
        smtp_user = clog._require_env("SMTP_USER")
        smtp_password = clog._require_env("SMTP_PASSWORD")
        from_email = clog._require_env("FROM_EMAIL")
        pending_emails: dict[str, str] = {}
        failed_emails: list[str] = []
        for email in emails:
            token = secrets.token_urlsafe(16)
            confirmation_url = build_confirmation_url(token)
            confirmation_body = build_confirmation_email_body(name, confirmation_url)
            try:
                clog.send_email(
                    subject=f"Confirme ton adresse pour la recherche {name!r}",
                    body=confirmation_body,
                    to_addrs=[email],
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    smtp_user=smtp_user,
                    smtp_password=smtp_password,
                    from_email=from_email,
                )
            except Exception as exc:
                print(f"ERROR: echec d'envoi de l'email de confirmation a {email!r}: {exc}")
                failed_emails.append(email)
                continue
            pending_emails[hash_token(token)] = email

        if not pending_emails:
            print(f"ERROR: aucun email de confirmation n'a pu etre envoye pour {name!r}")
            return 1

        pending[name] = {"search": entry, "pending_emails": pending_emails}
        save_pending_searches(pending)
        lines.insert(
            0,
            f"OK: recherche {name!r} creee EN ATTENTE de confirmation email pour {city!r}.",
        )
        lines.append(
            f"Email(s) en attente de confirmation : {', '.join(pending_emails.values())}. Un "
            "email de confirmation a ete envoye a chaque adresse. La recherche ne sera "
            "active qu'une fois qu'au moins un email aura confirme."
        )
        if failed_emails:
            lines.append(
                f"AVERTISSEMENT: echec d'envoi pour : {', '.join(failed_emails)} "
                "(resoumets une nouvelle issue pour ces adresses si besoin)"
            )
    else:
        searches.append(entry)
        clog.save_searches(searches)
        lines.insert(0, f"OK: recherche {name!r} ajoutee pour {city!r}.")
        lines.append("Destinataire : email par defaut (ALERT_EMAIL)")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
