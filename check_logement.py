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
