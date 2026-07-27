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
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(
            f"error: corrupt JSON in {path}, falling back to empty state: {exc}",
            file=sys.stderr,
        )
        return {}


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
    for search in searches:
        if "name" not in search or "url" not in search:
            raise ValueError(f"invalid search entry, missing name/url: {search}")
    return searches


def format_email_body(
    search_name: str, new_items: list[dict[str, Any]], search_url: str
) -> str:
    lines = [
        f'{len(new_items)} nouveau(x) logement(s) pour la recherche "{search_name}" :',
        "",
    ]
    for item in new_items:
        residence = item.get("residence", {})
        label = item.get("label", "(sans libelle)")
        address = residence.get("address", "(adresse inconnue)")
        amount = item.get("bookingData", {}).get("amount")
        rent_str = f"{amount / 100:.2f} EUR/mois" if amount is not None else "loyer non precise"
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

    searches = load_searches()
    seen = load_seen()
    any_success = False

    for search in searches:
        name = search["name"]
        url = search["url"]
        recipients = search.get("emails") or [default_email]
        try:
            html = fetch_html(url)
            results = parse_search_results(html)
        except SearchFetchError as exc:
            print(f"[ERROR] {name}: {exc}", file=sys.stderr)
            continue

        items = results.get("items", [])
        seen_ids = seen.get(name, [])
        new_items, all_ids = find_new_items(items, seen_ids)

        if new_items:
            subject = f"[Logement] {len(new_items)} nouveau(x) pour {name}"
            body = format_email_body(name, new_items, url)
            send_email(subject, body, recipients, smtp_user, smtp_password)
            print(f"[OK] {name}: sent alert for {len(new_items)} new listing(s)")
        else:
            print(f"[OK] {name}: no new listings ({len(items)} total)")

        seen[name] = all_ids
        any_success = True

    save_seen(seen)
    return 0 if any_success else 1


if __name__ == "__main__":
    sys.exit(main())
