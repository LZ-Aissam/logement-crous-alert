# Alerte disponibilité logement CROUS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script + GitHub Actions workflow that polls one or more CROUS housing searches on a schedule and emails the right recipients when a new listing appears.

**Architecture:** A single-file script (`check_logement.py`) fetches each search's page, extracts a JSON blob the site's server already embeds in the HTML, diffs the listing IDs against a committed `seen.json`, and emails any new listings to that search's configured recipients. A GitHub Actions cron workflow runs the script every ~10 minutes and commits the updated `seen.json` back to the repo.

**Tech Stack:** Python 3.12, `requests` (HTTP), stdlib `smtplib`/`email` (Gmail SMTP), stdlib `json`/`re`, `pytest` for tests, GitHub Actions (`schedule` trigger).

## Global Constraints

- Repo is **public** on GitHub (unlimited free Actions minutes) — no sensitive data is ever committed; credentials live only in GitHub encrypted Secrets.
- Cron schedule: `*/10 * * * *` (~10 minutes, GitHub Actions' practical minimum).
- Email via Gmail SMTP over SSL, `smtp.gmail.com:465`. Credentials come from env vars `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL` (default recipient), injected from GitHub Secrets in CI.
- Config lives in two root-level JSON files: `searches.json` (list of `{name, url, emails?}`, user-edited, committed) and `seen.json` (dict `{name: [ids]}`, script-maintained, committed).
- A search whose `emails` field is absent falls back to `ALERT_EMAIL` as its sole recipient.
- One email per search that has new listings (not one global summary), addressed to that search's own recipients.
- A broken search (network error, unexpected page structure) must not block other searches: log to stderr and skip it; `seen.json` is left untouched for that search only.
- On the very first run for a given search name (no prior entry in `seen.json`), every currently-listed item counts as "new" and triggers an email (explicit user decision — no silent baselining).
- No Windows notifications, no web UI. `check_logement.py` is the only executable entry point.
- No placeholders anywhere in code — every function fully implemented.

---

### Task 1: Project scaffolding + HTML fetcher

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `check_logement.py`
- Create: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `SearchFetchError(Exception)`, `fetch_html(url: str) -> str` (raises `SearchFetchError` on network error or non-200 status), module constants `FETCH_TIMEOUT = 20`, `USER_AGENT`.

- [ ] **Step 1: Create scaffolding files**

`requirements.txt`:
```
requests
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest
```

`pytest.ini`:
```ini
[pytest]
pythonpath = .
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements-dev.txt`
Expected: `requests` and `pytest` install without error.

- [ ] **Step 3: Write the failing test for `fetch_html`**

Create `tests/test_check_logement.py` with:

```python
import requests
import pytest

import check_logement as mod


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def test_fetch_html_returns_text_on_200(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert "example.com" in url
        return _FakeResponse(200, "<html>ok</html>")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_html("https://example.com/search") == "<html>ok</html>"


def test_fetch_html_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(500, ""))
    with pytest.raises(mod.SearchFetchError):
        mod.fetch_html("https://example.com/search")


def test_fetch_html_raises_on_network_error(monkeypatch):
    def fake_get(*a, **k):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    with pytest.raises(mod.SearchFetchError):
        mod.fetch_html("https://example.com/search")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_logement'` (file doesn't exist yet).

- [ ] **Step 5: Create `check_logement.py` with `fetch_html`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt pytest.ini .gitignore check_logement.py tests/test_check_logement.py
git commit -m "feat: scaffold project and add HTML fetcher"
```

---

### Task 2: Search result parser

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: `SearchFetchError` from Task 1.
- Produces: `parse_search_results(html: str) -> dict[str, Any]` (returns the `results` dict: `{"total": {...}, "page": int, "pageSize": int, "items": [...]}`; raises `SearchFetchError` if the embedded block is missing or malformed).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_logement.py`:

```python
def _make_fixture_html(total, items):
    body_obj = {
        "results": {
            "total": {"value": total, "relation": "eq"},
            "page": 0,
            "pageSize": 24,
            "items": items,
        }
    }
    outer = {
        "status": 200,
        "statusText": "OK",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body_obj),
    }
    return (
        '<html><body><script type="application/json" data-sveltekit-fetched '
        f'data-url="/api/fr/search/47" data-hash="abc">{json.dumps(outer)}</script>'
        "</body></html>"
    )


def test_parse_search_results_extracts_items():
    html = _make_fixture_html(2, [{"id": 1}, {"id": 2}])
    results = mod.parse_search_results(html)
    assert results["total"]["value"] == 2
    assert [item["id"] for item in results["items"]] == [1, 2]


def test_parse_search_results_raises_when_block_missing():
    with pytest.raises(mod.SearchFetchError):
        mod.parse_search_results("<html><body>nothing here</body></html>")


def test_parse_search_results_raises_on_malformed_json():
    broken = (
        '<html><body><script type="application/json" data-sveltekit-fetched '
        'data-url="/api/fr/search/47" data-hash="abc">{not json}</script></body></html>'
    )
    with pytest.raises(mod.SearchFetchError):
        mod.parse_search_results(broken)
```

Add `import json` at the top of the test file (next to the existing imports).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'parse_search_results'`.

- [ ] **Step 3: Implement `parse_search_results`**

Add to `check_logement.py` (after `fetch_html`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: parse embedded search results JSON from page HTML"
```

---

### Task 3: Seen-state persistence

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `load_seen(path: Path = SEEN_PATH) -> dict[str, list[str]]` (returns `{}` if file absent), `save_seen(seen: dict[str, list[str]], path: Path = SEEN_PATH) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_load_seen_returns_empty_dict_when_missing(tmp_path):
    missing = tmp_path / "seen.json"
    assert mod.load_seen(missing) == {}


def test_save_then_load_seen_round_trips(tmp_path):
    path = tmp_path / "seen.json"
    mod.save_seen({"Brest": ["1", "2"]}, path)
    assert mod.load_seen(path) == {"Brest": ["1", "2"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'load_seen'`.

- [ ] **Step 3: Implement `load_seen` and `save_seen`**

Add to `check_logement.py`:

```python
def load_seen(path: Path = SEEN_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_seen(seen: dict[str, list[str]], path: Path = SEEN_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: add seen.json load/save"
```

---

### Task 4: New-item diffing

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `find_new_items(items: list[dict[str, Any]], seen_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]` — returns `(new_items, all_ids_sorted)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_find_new_items_first_run_all_new():
    items = [{"id": 1}, {"id": 2}]
    new_items, all_ids = mod.find_new_items(items, [])
    assert new_items == items
    assert all_ids == ["1", "2"]


def test_find_new_items_only_returns_unseen():
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    new_items, all_ids = mod.find_new_items(items, ["1", "2"])
    assert new_items == [{"id": 3}]
    assert all_ids == ["1", "2", "3"]


def test_find_new_items_no_items_no_new():
    new_items, all_ids = mod.find_new_items([], ["1"])
    assert new_items == []
    assert all_ids == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'find_new_items'`.

- [ ] **Step 3: Implement `find_new_items`**

Add to `check_logement.py`:

```python
def find_new_items(
    items: list[dict[str, Any]], seen_ids: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    seen_set = set(seen_ids)
    new_items = [item for item in items if str(item["id"]) not in seen_set]
    all_ids = sorted({str(item["id"]) for item in items})
    return new_items, all_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: diff listing ids to find new items"
```

---

### Task 5: Searches config loader

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `load_searches(path: Path = SEARCHES_PATH) -> list[dict[str, Any]]` — raises `ValueError` if any entry is missing `name` or `url`.

- [ ] **Step 1: Write the failing tests**

```python
def test_load_searches_reads_valid_list(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    searches = mod.load_searches(path)
    assert searches == [{"name": "Brest", "url": "https://example.com/brest"}]


def test_load_searches_rejects_entry_missing_name(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(json.dumps([{"url": "https://example.com/brest"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_searches(path)


def test_load_searches_rejects_entry_missing_url(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(json.dumps([{"name": "Brest"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_searches(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'load_searches'`.

- [ ] **Step 3: Implement `load_searches`**

Add to `check_logement.py`:

```python
def load_searches(path: Path = SEARCHES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        searches = json.load(f)
    for search in searches:
        if "name" not in search or "url" not in search:
            raise ValueError(f"invalid search entry, missing name/url: {search}")
    return searches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: load and validate searches.json"
```

---

### Task 6: Email body formatting

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `format_email_body(search_name: str, new_items: list[dict[str, Any]], search_url: str) -> str`.
- Note: `bookingData.amount` from the CROUS API is in cents (verified against the live site: a real listing had `"bookingData": {"amount": 7000}` for a ~70 EUR/month room), hence the `/ 100` conversion below.

- [ ] **Step 1: Write the failing test**

```python
def test_format_email_body_includes_listing_details():
    new_items = [
        {
            "label": "T1 meuble",
            "residence": {"label": "Residence Foo", "address": "1 rue Test, 29200 Brest"},
            "bookingData": {"amount": 25000},
        }
    ]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "Brest" in body
    assert "T1 meuble" in body
    assert "Residence Foo" in body
    assert "1 rue Test, 29200 Brest" in body
    assert "250.00" in body
    assert "https://example.com/search" in body


def test_format_email_body_handles_missing_rent():
    new_items = [{"label": "Chambre", "residence": {"label": "R", "address": "A"}}]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "non pr" in body  # "loyer non précisé"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'format_email_body'`.

- [ ] **Step 3: Implement `format_email_body`**

Add to `check_logement.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: format new-listing email bodies"
```

---

### Task 7: Email sending

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `send_email(subject: str, body: str, to_addrs: list[str], smtp_user: str, smtp_password: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent = (from_addr, to_addrs, msg)


def test_send_email_logs_in_and_sends(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP_SSL", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com", "b@example.com"],
        smtp_user="me@gmail.com",
        smtp_password="app-password",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 465
    assert smtp.logged_in == ("me@gmail.com", "app-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "me@gmail.com"
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert "Subject" in msg
    assert "Body text" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'send_email'`.

- [ ] **Step 3: Implement `send_email`**

Add to `check_logement.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: send alert emails via Gmail SMTP"
```

---

### Task 8: Main orchestration

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: every function produced in Tasks 1-7 (`fetch_html`, `parse_search_results`, `load_seen`, `save_seen`, `find_new_items`, `load_searches`, `format_email_body`, `send_email`), plus `SEARCHES_PATH`, `SEEN_PATH`.
- Produces: `main() -> int` (exit code: `0` if at least one search succeeded, `1` if all failed or a required env var is missing), CLI entry point via `if __name__ == "__main__"`.

- [ ] **Step 1: Write the failing integration tests**

```python
def test_main_sends_email_for_new_listings_and_updates_seen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["x@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(
            (subject, to_addrs)
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert sent == [(sent[0][0], ["x@example.com"])]
    assert "Brest" in sent[0][0]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


def test_main_no_new_listings_sends_no_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text(json.dumps({"Brest": ["1"]}), encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    monkeypatch.setattr(
        mod, "send_email", lambda *a, **k: pytest.fail("should not send email")
    )

    assert mod.main() == 0


def test_main_broken_search_does_not_block_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Broken", "url": "https://example.com/broken"},
                {"name": "Brest", "url": "https://example.com/brest"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    def fake_fetch(url):
        if "broken" in url:
            raise mod.SearchFetchError("boom")
        return "<fake html>"

    monkeypatch.setattr(mod, "fetch_html", fake_fetch)
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 0}, "items": []},
    )
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: None)

    assert mod.main() == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": []}


def test_main_all_searches_fail_returns_error_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    def fake_fetch(url):
        raise mod.SearchFetchError("boom")

    monkeypatch.setattr(mod, "fetch_html", fake_fetch)
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: pytest.fail("should not send email"))

    assert mod.main() == 1
    assert not (tmp_path / "seen.json").exists() or json.loads(
        (tmp_path / "seen.json").read_text(encoding="utf-8")
    ) == {}


def test_main_missing_env_var_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ALERT_EMAIL", raising=False)

    with pytest.raises(SystemExit):
        mod.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'main'`.

- [ ] **Step 3: Implement `main`**

Add to `check_logement.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: wire up main orchestration and CLI entry point"
```

---

### Task 9: GitHub Actions workflow, real config, and README

**Files:**
- Create: `.github/workflows/check.yml`
- Create: `searches.json`
- Create: `README.md`

**Interfaces:**
- Consumes: `main()` from Task 8 as the workflow's executable entry point.

- [ ] **Step 1: Create the real `searches.json`**

```json
[
  {
    "name": "Brest",
    "url": "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest+%2829200%29",
    "emails": ["theaissam@gmail.com"]
  }
]
```

- [ ] **Step 2: Create the workflow file**

`.github/workflows/check.yml`:

```yaml
name: Check CROUS housing

on:
  schedule:
    - cron: '*/10 * * * *'
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run housing check
        run: python check_logement.py
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}

      - name: Commit updated seen.json
        if: always()
        run: |
          git config user.name "logement-alert-bot"
          git config user.email "actions@users.noreply.github.com"
          git add seen.json
          git diff --staged --quiet || git commit -m "chore: update seen listings"
          git diff --staged --quiet || git push
```

- [ ] **Step 3: Write the README with setup instructions**

`README.md`:

```markdown
# Alerte logement CROUS

Surveille une ou plusieurs recherches sur trouverunlogement.lescrous.fr et envoie un
email dès qu'un nouveau logement apparaît. Tourne gratuitement 24h/24 via GitHub
Actions — pas besoin de garder un PC allumé.

## Mise en place

1. **Créer un mot de passe d'application Google** (nécessite la validation en 2 étapes
   activée sur le compte Gmail utilisé pour envoyer les emails) :
   https://myaccount.google.com/apppasswords — génère un mot de passe pour "Mail",
   copie-le (16 caractères sans espaces).

2. **Configurer les secrets du dépôt GitHub** : Settings > Secrets and variables >
   Actions > New repository secret, ajouter :
   - `GMAIL_ADDRESS` : l'adresse Gmail utilisée pour envoyer (ex: theaissam@gmail.com)
   - `GMAIL_APP_PASSWORD` : le mot de passe d'application généré à l'étape 1
   - `ALERT_EMAIL` : l'email destinataire par défaut, utilisé pour toute recherche
     dans `searches.json` qui n'a pas son propre champ `emails`

3. **Éditer `searches.json`** pour ajouter/retirer des recherches. Pour obtenir l'URL
   d'une recherche : va sur trouverunlogement.lescrous.fr, règle les filtres voulus
   (ville, type de logement, prix...) dans l'interface, puis copie l'URL de la barre
   d'adresse. Champ `emails` optionnel (liste de destinataires spécifiques à cette
   recherche) ; s'il est absent, `ALERT_EMAIL` est utilisé.

4. **Activer le workflow** : l'onglet Actions du dépôt doit afficher "Check CROUS
   housing". Il se déclenche automatiquement toutes les ~10 minutes une fois poussé
   sur la branche par défaut. Pour un premier test immédiat sans attendre : onglet
   Actions > "Check CROUS housing" > "Run workflow".

## Développement local

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

Pour lancer le script en local (nécessite les 3 variables d'environnement ci-dessus) :

```bash
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... ALERT_EMAIL=...
python check_logement.py
```
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/check.yml searches.json README.md
git commit -m "feat: add GitHub Actions workflow, real search config, and README"
```

---

### Task 10: Manual end-to-end verification against the live site

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Dry-run against the real Brest search (no email expected)**

```bash
export GMAIL_ADDRESS=<real address> GMAIL_APP_PASSWORD=<real app password> ALERT_EMAIL=<real address>
python check_logement.py
```

Expected: prints `[OK] Brest: no new listings (0 total)` (or a small positive count if a
listing has appeared since design time), creates/updates `seen.json` with a `"Brest"`
key, exit code 0. No email is expected only because there are currently 0 listings —
this confirms the real fetch + parse path works end-to-end.

- [ ] **Step 3: Temporarily verify the email-sending path with a non-empty search**

Add a throwaway second entry to `searches.json` pointing at an unfiltered search that
reliably returns results (confirmed during design to return dozens of listings
nationwide), e.g.:

```json
{"name": "TEST-national", "url": "https://trouverunlogement.lescrous.fr/tools/47/search", "emails": ["theaissam@gmail.com"]}
```

Delete `seen.json` (or just the `"TEST-national"` key) so it's treated as a first run,
then re-run `python check_logement.py`. Expected: a real email arrives listing several
"nouveaux" logements from across France. This confirms SMTP auth and formatting work
with real credentials.

- [ ] **Step 4: Remove the throwaway test entry**

Delete the `"TEST-national"` entry from `searches.json` and its key from `seen.json`
(or delete `seen.json` entirely — it will be regenerated on the next run).

```bash
git add searches.json seen.json
git commit -m "chore: remove throwaway test search after verification"
```

- [ ] **Step 5: Push to GitHub and confirm the scheduled workflow runs**

Push the branch to the GitHub remote (repo must already exist and secrets must already
be configured per the README). Trigger it once manually via Actions > "Check CROUS
housing" > "Run workflow", confirm the run succeeds and (if `seen.json` changed) a
bot commit appears. From then on it runs automatically every ~10 minutes.
