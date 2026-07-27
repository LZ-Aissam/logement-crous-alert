"""Poll CROUS housing searches and email alerts when new listings appear."""
from __future__ import annotations

import json
import os
import re
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

SEARCH_DATA_URL = "/api/fr/search/47"
FETCH_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; logement-alert-bot/1.0)"

SEARCHES_PATH = Path("searches.json")
SEEN_PATH = Path("seen.json")


class SearchFetchError(Exception):
    """Raised when a search page cannot be fetched or parsed."""


def fetch_html(url: str) -> str:
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT
        )
    except requests.RequestException as exc:
        raise SearchFetchError(f"network error fetching {url}: {exc}") from exc
    if response.status_code != 200:
        raise SearchFetchError(
            f"unexpected status {response.status_code} fetching {url}"
        )
    return response.text


_SCRIPT_RE = re.compile(
    r'data-url="' + re.escape(SEARCH_DATA_URL) + r'"[^>]*>(\{.*?\})</script>',
    re.S,
)


def parse_search_results(html: str) -> dict[str, Any]:
    match = _SCRIPT_RE.search(html)
    if not match:
        raise SearchFetchError(
            f"could not find embedded search data ({SEARCH_DATA_URL}) in page"
        )
    try:
        outer = json.loads(match.group(1))
        body = json.loads(outer["body"])
        return body["results"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise SearchFetchError(f"could not parse embedded search data: {exc}") from exc


def load_seen(path: Path = SEEN_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(
            f"[ERROR] corrupt JSON in {path}, falling back to empty state: {exc}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"[ERROR] unexpected JSON shape in {path} (expected an object), "
            "falling back to empty state",
            file=sys.stderr,
        )
        return {}
    return data


def save_seen(seen: dict[str, list[str]], path: Path = SEEN_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def find_new_items(
    items: list[dict[str, Any]], seen_ids: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    seen_set = set(seen_ids)
    new_items = [item for item in items if str(item["id"]) not in seen_set]
    all_ids = sorted({str(item["id"]) for item in items})
    return new_items, all_ids


def load_searches(path: Path = SEARCHES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        searches = json.load(f)
    if not isinstance(searches, list):
        raise ValueError(
            f"{path} must contain a JSON list of search objects, "
            f"got {type(searches).__name__}"
        )
    for search in searches:
        if not isinstance(search, dict) or "name" not in search or "url" not in search:
            raise ValueError(f"invalid search entry, missing name/url: {search}")
    return searches


def save_searches(searches: list[dict[str, Any]], path: Path = SEARCHES_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(searches, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _item_matches_keywords(item: dict[str, Any], keywords: list[str] | None) -> bool:
    if not keywords:
        return True
    residence = item.get("residence") or {}
    haystack = " ".join(
        str(x)
        for x in [
            item.get("label") or "",
            residence.get("label") or "",
            residence.get("address") or "",
        ]
    ).lower()
    return any(kw.strip().lower() in haystack for kw in keywords if kw.strip())


def _format_rent(item: dict[str, Any]) -> str:
    # The monthly rent lives in occupationModes[].rent (cents), not bookingData.amount
    # -- bookingData.amount is the deductible advance on the first month's rent, a
    # different, smaller figure that was mistakenly displayed as "the rent" before.
    modes = item.get("occupationModes") or []
    mode = next((m for m in modes if m.get("type") == "alone"), None)
    if mode is None and modes:
        mode = modes[0]
    rent = (mode or {}).get("rent") or {}
    rent_min = rent.get("min")
    rent_max = rent.get("max")
    if rent_min is None:
        return "loyer non precise"
    if rent_max is not None and rent_max != rent_min:
        return f"{rent_min / 100:.2f} - {rent_max / 100:.2f} EUR/mois"
    return f"{rent_min / 100:.2f} EUR/mois"


def format_email_body(
    search_name: str, new_items: list[dict[str, Any]], search_url: str
) -> str:
    lines = [
        f'{len(new_items)} nouveau(x) logement(s) pour la recherche "{search_name}" :',
        "",
    ]
    for item in new_items:
        residence = item.get("residence") or {}
        label = item.get("label", "(sans libelle)")
        address = residence.get("address", "(adresse inconnue)")
        rent_str = _format_rent(item)
        lines.append(f"- {label} - {residence.get('label', '')} - {address} - {rent_str}")
    lines.append("")
    lines.append(f"Voir la recherche : {search_url}")
    return "\n".join(lines)


def send_email(
    subject: str, body: str, to_addrs: list[str], smtp_user: str, smtp_password: str
) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(to_addrs)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=FETCH_TIMEOUT) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_addrs, msg.as_string())


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERROR] missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> int:
    smtp_user = _require_env("GMAIL_ADDRESS")
    smtp_password = _require_env("GMAIL_APP_PASSWORD")
    default_email = _require_env("ALERT_EMAIL")

    try:
        searches = load_searches()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[ERROR] could not load searches.json: {exc}", file=sys.stderr)
        return 1

    seen = load_seen()
    any_success = False

    for search in searches:
        name = search["name"]
        url = search["url"]
        recipients = search.get("emails") or [default_email]

        try:
            html = fetch_html(url)
            results = parse_search_results(html)
            items = results.get("items") or []
            items = [i for i in items if _item_matches_keywords(i, search.get("keywords"))]
            seen_ids = seen.get(name, [])
            new_items, all_ids = find_new_items(items, seen_ids)
            if new_items:
                subject = f"[Logement] {len(new_items)} nouveau(x) pour {name}"
                body = format_email_body(name, new_items, url)
        except (SearchFetchError, KeyError, TypeError, AttributeError) as exc:
            print(f"[ERROR] {name}: {exc}", file=sys.stderr)
            continue

        any_success = True

        if new_items:
            try:
                send_email(subject, body, recipients, smtp_user, smtp_password)
            except Exception as exc:
                print(f"[ERROR] {name}: failed to send email: {exc}", file=sys.stderr)
                continue
            print(f"[OK] {name}: sent alert for {len(new_items)} new listing(s)")
        else:
            print(f"[OK] {name}: no new listings ({len(items)} total)")

        seen[name] = sorted(set(seen_ids) | set(all_ids))

    if any_success:
        save_seen(seen)
    return 0 if any_success else 1


if __name__ == "__main__":
    sys.exit(main())
