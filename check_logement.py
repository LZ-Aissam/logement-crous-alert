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
