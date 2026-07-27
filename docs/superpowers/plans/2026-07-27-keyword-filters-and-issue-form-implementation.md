# Keyword Filters + Issue Form Search Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a search in `searches.json` optionally filter by keywords (residence name, room type), and let the user add a new search via a GitHub Issue Form instead of hand-editing JSON.

**Architecture:** `check_logement.py` gains a keyword-matching filter applied to fetched items before the new-item diff, plus a `save_searches` writer. A new, separate script `add_search.py` parses a submitted GitHub Issue Form, geocodes the city via the French government's public address API, builds a CROUS search URL, discovers currently-available residence/room-type names as a best-effort keyword sanity check, and appends the new entry to `searches.json`. A new GitHub Actions workflow triggers on issue creation, runs `add_search.py`, and commits/comments/closes the issue on success (or comments-only, leaving it open, on failure).

**Tech Stack:** Python 3.12, `requests` (already a dependency), stdlib `re`/`json`/`urllib.parse`, `pytest`, GitHub Actions (`issues` trigger), GitHub Issue Forms (YAML), `gh` CLI (already available on GitHub-hosted runners).

## Global Constraints

- `keywords` is an optional list of strings on a `searches.json` entry. A logement matches a search's keywords if it's in the geographic zone (already true via the URL) AND (if `keywords` is non-empty) at least one keyword case-insensitively substring-matches the concatenation of the item's `label`, its residence's `label`, and its residence's `address`. Absent/empty `keywords` = current behavior (no additional filtering).
- Filtering happens in `main()` right after extracting `items`, before `find_new_items` — a non-matching item is never recorded in `seen.json` and never triggers an alert.
- The Issue Form's field **label** text is the parsing contract for `add_search.py` — the YAML's `attributes.label` strings must be used verbatim as dict keys in `parse_issue_form_body`'s output. Exact labels: `"Nom de la recherche"`, `"Ville"`, `"Mots-clés (résidence, type de logement...) - optionnel"`, `"Email(s) de notification - optionnel"`.
- Residence/room-type discovery is **best-effort only**: a submitted keyword that doesn't match anything currently discovered produces a **warning in the confirmation message**, never a rejection — the search is still created. Only two things cause an outright rejection (issue stays open, `searches.json` untouched): a duplicate search name (case-insensitive match against existing entries), or a geocoding failure (city not found / network error).
- New searches use a fixed-size zone: `DEFAULT_HALF_LAT_SPAN = 0.0511`, `DEFAULT_HALF_LON_SPAN = 0.0705` (degrees), matching the size originally used for the Brest search. Tool id is always `47`.
- The new workflow (`add-search.yml`) needs `permissions: contents: write` and `issues: write`, triggers only on `issues: opened` where the label `new-search` is present, and must never crash silently — both stdout and stderr from `add_search.py` are captured into the issue comment so a bug still produces a diagnosable message.
- **The Issue Form is intentionally open to any GitHub user** (the goal is that other people can create their own searches, delivered to their own email) — but a submitted `emails` address must never receive alerts without proving its owner consents. Any email address that hasn't already been confirmed goes through a confirmation step (a second Issue Form, `confirm-email.yml`) before it can ever appear as a recipient in `searches.json`. A search with unconfirmed emails only is created in `pending_searches.json`, not `searches.json`, and sends zero alerts until at least one of its emails confirms. A search submitted with no `emails` field at all needs no confirmation (falls back to `ALERT_EMAIL`, the repo owner's own trusted address).
- Submitted email addresses must pass a basic shape check (`EMAIL_RE`) before anything else happens with them — reject clearly, no file writes, if any is malformed.
- The Issue-Form-facing field label constants (`FIELD_NAME`, `FIELD_CITY`, `FIELD_KEYWORDS`, `FIELD_EMAILS`) must be kept in sync with the actual YAML — enforced by a test that parses the real `.github/ISSUE_TEMPLATE/new-search.yml` file and compares.
- Both `add-search.yml` and `confirm-email.yml` must always post an issue comment with the script's result (success or failure) — the comment step must not be skipped just because a later step (the git commit/push) fails; only the *close* step is conditioned on the commit/push having actually succeeded.
- No placeholders anywhere in code — every function fully implemented.

---

### Task 1: Keyword-matching filter in `check_logement.py`

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `_item_matches_keywords(item: dict[str, Any], keywords: list[str] | None) -> bool`.
- Modifies: `main()` — items are now filtered by `_item_matches_keywords(item, search.get("keywords"))` right after `items = results.get("items") or []`.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_check_logement.py`:

```python
def test_item_matches_keywords_no_keywords_matches_everything():
    assert mod._item_matches_keywords({"label": "T1"}, None) is True
    assert mod._item_matches_keywords({"label": "T1"}, []) is True


def test_item_matches_keywords_matches_residence_label():
    item = {"label": "T1", "residence": {"label": "Kergoat", "address": "1 rue X"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is True


def test_item_matches_keywords_matches_item_label():
    item = {"label": "Studio meuble", "residence": {"label": "R", "address": "A"}}
    assert mod._item_matches_keywords(item, ["studio"]) is True


def test_item_matches_keywords_matches_address():
    item = {"label": "T1", "residence": {"label": "R", "address": "5 rue de Kergoat"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is True


def test_item_matches_keywords_no_match_returns_false():
    item = {"label": "T1", "residence": {"label": "Foo", "address": "Bar"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is False


def test_item_matches_keywords_case_insensitive_and_any_of_multiple():
    item = {"label": "CHAMBRE", "residence": {"label": "Foo", "address": "Bar"}}
    assert mod._item_matches_keywords(item, ["Kergoat", "chambre"]) is True


def test_main_filters_items_by_keywords(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "keywords": ["kergoat"]}]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {
            "total": {"value": 2},
            "items": [
                {"id": 1, "label": "T1", "residence": {"label": "Kergoat", "address": "A"}},
                {"id": 2, "label": "T1", "residence": {"label": "Autre", "address": "B"}},
            ],
        },
    )
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(body),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert len(sent) == 1
    assert "Kergoat" in sent[0]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute '_item_matches_keywords'`.

- [ ] **Step 3: Implement `_item_matches_keywords` and wire it into `main()`**

Add to `check_logement.py` (e.g. right before `format_email_body`):

```python
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
```

In `main()`, change:
```python
            items = results.get("items") or []
```
to:
```python
            items = results.get("items") or []
            items = [i for i in items if _item_matches_keywords(i, search.get("keywords"))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: all tests pass (33 pre-existing + 7 new = 40).

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: filter items by optional per-search keywords"
```

---

### Task 2: `save_searches` in `check_logement.py`

**Files:**
- Modify: `check_logement.py`
- Modify: `tests/test_check_logement.py`

**Interfaces:**
- Produces: `save_searches(searches: list[dict[str, Any]], path: Path = SEARCHES_PATH) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_save_searches_writes_valid_json_list(tmp_path):
    path = tmp_path / "searches.json"
    entries = [{"name": "Brest", "url": "https://example.com/brest"}]
    mod.save_searches(entries, path)
    assert json.loads(path.read_text(encoding="utf-8")) == entries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: FAIL — `AttributeError: module 'check_logement' has no attribute 'save_searches'`.

- [ ] **Step 3: Implement `save_searches`**

Add to `check_logement.py` (right after `load_searches`):

```python
def save_searches(searches: list[dict[str, Any]], path: Path = SEARCHES_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(searches, f, indent=2, ensure_ascii=False)
        f.write("\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_check_logement.py -v`
Expected: all tests pass (40 pre-existing + 1 new = 41).

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: add save_searches writer"
```

---

### Task 3: `add_search.py` building blocks (geocoding, URL, parsing, discovery)

**Files:**
- Create: `add_search.py`
- Create: `tests/test_add_search.py`

**Interfaces:**
- Consumes: nothing from other new-feature tasks (this task is self-contained scaffolding).
- Produces: `GeocodeError(Exception)`, `geocode_city(city: str) -> tuple[float, float]`, `build_search_url(lon: float, lat: float, location_label: str) -> str`, `parse_issue_form_body(body: str) -> dict[str, str | None]`, `discover_filters(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]`, module constants `GEOCODE_URL`, `GEOCODE_TIMEOUT`, `DEFAULT_HALF_LAT_SPAN`, `DEFAULT_HALF_LON_SPAN`, `TOOL_ID`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_add_search.py`:

```python
import json

import pytest

import add_search as mod


def test_parse_issue_form_body_all_fields_filled():
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest 29200\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat, studio\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com, b@example.com\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Brest"
    assert fields["Ville"] == "Brest 29200"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] == "Kergoat, studio"
    assert fields["Email(s) de notification - optionnel"] == "a@example.com, b@example.com"


def test_parse_issue_form_body_empty_optional_fields():
    body = (
        "### Nom de la recherche\n\nRennes\n\n"
        "### Ville\n\nRennes\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Rennes"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] is None
    assert fields["Email(s) de notification - optionnel"] is None


def test_geocode_city_returns_lon_lat(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"features": [{"geometry": {"coordinates": [0.631041, 44.202304]}}]}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    lon, lat = mod.geocode_city("Agen")
    assert lon == 0.631041
    assert lat == 44.202304


def test_geocode_city_raises_when_not_found(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"features": []}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("VilleImaginaireQuiNExistePas")


def test_geocode_city_raises_on_network_error(monkeypatch):
    def fake_get(*a, **k):
        raise mod.requests.ConnectionError("boom")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("Agen")


def test_build_search_url_contains_bounds_and_tool_id():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=")
    assert "locationName=" in url


def test_discover_filters_returns_distinct_sorted_names():
    items = [
        {"label": "T1", "residence": {"label": "Kergoat"}},
        {"label": "Studio", "residence": {"label": "Kergoat"}},
        {"label": "T1", "residence": {"label": "Autre"}},
    ]
    residences, labels = mod.discover_filters(items)
    assert residences == ["Autre", "Kergoat"]
    assert labels == ["Studio", "T1"]


def test_discover_filters_empty_items_returns_empty_lists():
    assert mod.discover_filters([]) == ([], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'add_search'`.

- [ ] **Step 3: Create `add_search.py` with the building-block functions**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: add geocoding, URL building, issue-form parsing, and filter discovery"
```

---

### Task 4: `add_search.py` main orchestration

**Files:**
- Modify: `add_search.py`
- Modify: `tests/test_add_search.py`

**Interfaces:**
- Consumes: everything from Task 3, plus `check_logement.load_searches`, `check_logement.save_searches` (Task 2), `check_logement.fetch_html`, `check_logement.parse_search_results`, `check_logement.SearchFetchError` (existing).
- Produces: `main() -> int` reading `ISSUE_BODY` from the environment; CLI entry point via `if __name__ == "__main__"`.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_add_search.py` (add `import check_logement as clog` near the top alongside the existing imports):

```python
def test_main_adds_search_successfully(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    assert searches[0]["name"] == "Agen"
    assert searches[0]["keywords"] == ["Kergoat"]
    assert "url" in searches[0]
    assert "emails" not in searches[0]
    out = capsys.readouterr().out
    assert "OK" in out


def test_main_rejects_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com"}]), encoding="utf-8"
    )
    body = (
        "### Nom de la recherche\n\nbrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1


def test_main_reports_error_when_city_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nTest\n\n"
        "### Ville\n\nVilleInexistante\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(
        mod, "geocode_city", lambda city: (_ for _ in ()).throw(mod.GeocodeError("not found"))
    )

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []


def test_main_warns_when_keyword_not_found_but_still_adds(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nTypo123\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    out = capsys.readouterr().out
    assert "Typo123" in out


def test_main_requires_name_and_city(monkeypatch):
    body = (
        "### Nom de la recherche\n\n_No response_\n\n"
        "### Ville\n\n_No response_\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    assert mod.main() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -v`
Expected: FAIL — `AttributeError: module 'add_search' has no attribute 'main'`.

- [ ] **Step 3: Implement `main()`**

Add to `add_search.py` (add `import os`, `import sys`, `import json`, and `import check_logement as clog` to the imports at the top; add the function after `discover_filters`):

```python
def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)

    name = fields.get("Nom de la recherche")
    city = fields.get("Ville")
    keywords_raw = fields.get("Mots-clés (résidence, type de logement...) - optionnel")
    emails_raw = fields.get("Email(s) de notification - optionnel")

    if not name or not city:
        print("ERROR: le nom de la recherche et la ville sont obligatoires")
        return 1

    try:
        searches = clog.load_searches()
    except (ValueError, json.JSONDecodeError, OSError):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -v`
Expected: 13 passed.

- [ ] **Step 5: Run the full project test suite**

Run: `python -m pytest -v`
Expected: all tests pass (41 from `test_check_logement.py` + 13 from `test_add_search.py` = 54).

- [ ] **Step 6: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: wire up add_search main orchestration"
```

---

### Task 5: Issue Form and workflow

**Files:**
- Create: `.github/ISSUE_TEMPLATE/new-search.yml`
- Create: `.github/workflows/add-search.yml`

**Interfaces:**
- Consumes: `add_search.py`'s `main()` (Task 4) as the workflow's executable entry point, reading `ISSUE_BODY` from the environment and exiting 0/1.

- [ ] **Step 1: Create the Issue Form**

`.github/ISSUE_TEMPLATE/new-search.yml`:

```yaml
name: Nouvelle recherche de logement
description: Ajoute une nouvelle recherche CROUS a surveiller (ville + filtres optionnels)
title: "[Nouvelle recherche] "
labels: ["new-search"]
body:
  - type: input
    id: name
    attributes:
      label: Nom de la recherche
      description: Un nom court et unique pour identifier cette recherche (ex. "Brest", "Rennes Kergoat")
      placeholder: Brest
    validations:
      required: true
  - type: input
    id: city
    attributes:
      label: Ville
      description: Ville (et code postal si tu veux etre precis), ex. "Brest" ou "Brest 29200"
      placeholder: Brest 29200
    validations:
      required: true
  - type: input
    id: keywords
    attributes:
      label: Mots-clés (résidence, type de logement...) - optionnel
      description: >-
        Separes par des virgules (ex. "Kergoat, studio, chambre grand confort").
        Un logement doit correspondre a au moins un mot-cle pour declencher une alerte.
        Laisse vide pour recevoir toutes les annonces de cette ville.
      placeholder: Kergoat, studio
    validations:
      required: false
  - type: input
    id: emails
    attributes:
      label: Email(s) de notification - optionnel
      description: Separes par des virgules. Laisse vide pour utiliser l'email par defaut.
      placeholder: toi@example.com
    validations:
      required: false
```

- [ ] **Step 2: Create the workflow**

`.github/workflows/add-search.yml`:

```yaml
name: Add search from issue

on:
  issues:
    types: [opened]

permissions:
  contents: write
  issues: write

jobs:
  add-search:
    if: contains(github.event.issue.labels.*.name, 'new-search')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Process new search request
        id: process
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
        run: |
          if python add_search.py > result.txt 2>&1; then
            echo "success=true" >> "$GITHUB_OUTPUT"
          else
            echo "success=false" >> "$GITHUB_OUTPUT"
          fi
          cat result.txt

      - name: Commit updated searches.json
        if: steps.process.outputs.success == 'true'
        run: |
          git config user.name "logement-alert-bot"
          git config user.email "actions@users.noreply.github.com"
          git add searches.json
          git commit -m "chore: add search from issue #${{ github.event.issue.number }}"
          git pull --rebase --autostash
          git push

      - name: Comment and close on success
        if: steps.process.outputs.success == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body-file result.txt
          gh issue close ${{ github.event.issue.number }} --repo ${{ github.repository }}

      - name: Comment on failure
        if: steps.process.outputs.success == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body-file result.txt
```

- [ ] **Step 3: Run the full test suite once (sanity check, no code changed in this task)**

Run: `python -m pytest -v`
Expected: 54 passed (unchanged from Task 4 — this task added no Python code).

- [ ] **Step 4: Commit**

```bash
git add .github/ISSUE_TEMPLATE/new-search.yml .github/workflows/add-search.yml
git commit -m "feat: add Issue Form and workflow to create searches without editing JSON"
```

---

### Task 6: README updates

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Add a section documenting keyword filters**

Add a new section to `README.md` (after the existing `searches.json` explanation), covering:
- The optional `keywords` field: a list of strings; a listing must match the city/zone AND at least one keyword (case-insensitive, matched against the residence name, room label, or address) to trigger an alert; omit the field to get everything in the zone as before.
- Example JSON snippet showing a search with `keywords`.

- [ ] **Step 2: Add a section documenting the Issue Form**

Add a new section explaining: click "New issue" on the repository, choose "Nouvelle recherche de logement", fill in the name/city/keywords/emails fields, submit. A bot will geocode the city, build the search automatically, and comment on the issue confirming what was added (or explaining what went wrong, in which case the issue stays open so you can fix it and open a new one). Mention explicitly: if there are currently no available listings in that city, the bot cannot suggest real residence/room-type names to check your keywords against — it will still create the search, just without that sanity check for now.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document keyword filters and the Issue Form search creation flow"
```

---

### Task 7: Local dry-run verification (completed)

**Files:** none (verification only).

- [x] **Step 1: Run the full test suite**

Run: `python -m pytest -v` — 58 passed, output pristine (already done).

- [x] **Step 2: Locally simulate an issue submission**

Already done: a local dry run against the real `geocode_city`/CROUS site for "Rennes"
succeeded and the entry was reverted afterward. `searches.json` is back to its original
state (only the real "Brest" entry).

**Steps 3-4 of the original Task 7 (push + real Issue Form submission) are superseded
by Task 13 below** — a final whole-branch review found a critical security gap (the
Issue Form has no submitter restriction, combined with an unverified `emails` field,
which would let anyone make the bot send repeated mail from the owner's Gmail account to
a third party who never consented) plus several important robustness gaps. Tasks 8-12
fix these and add mandatory email confirmation before any submitted address can receive
alerts. Task 13 is the real final end-to-end verification, covering both the "new
search" and "confirm email" flows together.

---

### Task 8: Security/robustness fixes (email format validation, label-constant test, workflow hardening, README disclosure)

**Files:**
- Modify: `add_search.py`
- Modify: `tests/test_add_search.py`
- Modify: `.github/workflows/add-search.yml`
- Modify: `README.md`
- Modify: `requirements-dev.txt`

**Interfaces:**
- Produces: module constants `FIELD_NAME = "Nom de la recherche"`, `FIELD_CITY = "Ville"`, `FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel"`, `FIELD_EMAILS = "Email(s) de notification - optionnel"` in `add_search.py`, and `EMAIL_RE` (a compiled regex for basic email-shape validation).
- Modifies: `main()` — uses the new `FIELD_*` constants instead of inline string literals, and validates each submitted email against `EMAIL_RE` right after parsing, rejecting (no file writes, exit 1) if any is malformed.

- [ ] **Step 1: Write the failing tests**

Add `pyyaml` to `requirements-dev.txt` (append a new line, keep the existing `-r requirements.txt` and `pytest` lines):
```
-r requirements.txt
pytest
pyyaml
```

Append to `tests/test_add_search.py`:

```python
import yaml


def test_field_label_constants_match_issue_form_yaml():
    with open(".github/ISSUE_TEMPLATE/new-search.yml", encoding="utf-8") as f:
        form = yaml.safe_load(f)
    labels_by_id = {
        field["id"]: field["attributes"]["label"] for field in form["body"]
    }
    assert labels_by_id["name"] == mod.FIELD_NAME
    assert labels_by_id["city"] == mod.FIELD_CITY
    assert labels_by_id["keywords"] == mod.FIELD_KEYWORDS
    assert labels_by_id["emails"] == mod.FIELD_EMAILS


def test_main_rejects_invalid_email_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\npas-un-email\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_load_searches_round_trips_through_add_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    assert mod.main() == 0

    loaded = clog.load_searches()
    assert loaded == [{"name": "Agen", "url": loaded[0]["url"]}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pip install -r requirements-dev.txt && python -m pytest tests/test_add_search.py -v`
Expected: FAIL — `AttributeError: module 'add_search' has no attribute 'FIELD_NAME'` (and the email-validation test fails since nothing rejects `pas-un-email` yet).

- [ ] **Step 3: Add the constants and email validation to `add_search.py`**

Near the top of `add_search.py`, after the existing module constants (`GEOCODE_URL`, etc.), add:

```python
FIELD_NAME = "Nom de la recherche"
FIELD_CITY = "Ville"
FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel"
FIELD_EMAILS = "Email(s) de notification - optionnel"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
```

In `main()`, change the field lookups from inline literals to the constants:
```python
    name = fields.get(FIELD_NAME)
    city = fields.get(FIELD_CITY)
    keywords_raw = fields.get(FIELD_KEYWORDS)
    emails_raw = fields.get(FIELD_EMAILS)
```

Right after `emails = _split_csv(emails_raw)` (wherever that line currently is in
`main()`), add:
```python
    invalid_emails = [e for e in emails if not EMAIL_RE.match(e)]
    if invalid_emails:
        print(f"ERROR: adresse(s) email invalide(s) : {', '.join(invalid_emails)}")
        return 1
```

- [ ] **Step 4: Harden `.github/workflows/add-search.yml`**

Replace its full content with:

```yaml
name: Add search from issue

on:
  issues:
    types: [opened]

permissions:
  contents: write
  issues: write

concurrency:
  group: add-search
  cancel-in-progress: false

jobs:
  add-search:
    if: contains(github.event.issue.labels.*.name, 'new-search')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Process new search request
        id: process
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: |
          if python add_search.py > result.txt 2>&1; then
            echo "success=true" >> "$GITHUB_OUTPUT"
          else
            echo "success=false" >> "$GITHUB_OUTPUT"
          fi
          cat result.txt

      - name: Comment with result
        if: always()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body-file result.txt

      - name: Commit and push data files
        id: persist
        if: steps.process.outputs.success == 'true'
        run: |
          git config user.name "logement-alert-bot"
          git config user.email "actions@users.noreply.github.com"
          git add searches.json pending_searches.json
          if git diff --staged --quiet; then
            echo "persisted=true" >> "$GITHUB_OUTPUT"
          else
            if git commit -m "chore: add search from issue #${{ github.event.issue.number }}" \
                && git pull --rebase --autostash \
                && git push; then
              echo "persisted=true" >> "$GITHUB_OUTPUT"
            else
              echo "persisted=false" >> "$GITHUB_OUTPUT"
            fi
          fi

      - name: Close issue on full success
        if: steps.process.outputs.success == 'true' && steps.persist.outputs.persisted == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue close ${{ github.event.issue.number }} --repo ${{ github.repository }}

      - name: Warn if persistence failed
        if: steps.process.outputs.success == 'true' && steps.persist.outputs.persisted == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body "Erreur technique lors de l'enregistrement (collision Git). Le workflow va probablement reussir si tu resoumets une nouvelle issue dans quelques minutes."
```

(Note: `pending_searches.json` doesn't exist as a concept yet in this task — `git add
searches.json pending_searches.json` is safe even though the second file doesn't exist
yet, since `git add` on a path that doesn't currently exist but was previously tracked,
or genuinely never existed, is a no-op for that path as long as at least one path in the
command matches something — but to keep this task's diff self-contained and not
forward-reference Task 9's file, only add `searches.json` in this step; Task 9 will
update this line to `git add searches.json pending_searches.json` when it introduces
that file.)

- [ ] **Step 5: Add the README zone-size disclosure**

In the Issue Form section of `README.md`, add a sentence noting: the search zone
created via the form is a **fixed size** (roughly 11 km × 10 km) centered on the city.
For a very large city (Paris, Lyon, Marseille...), this may not cover the whole
metropolitan area — the URL's `bounds` can be widened by hand in `searches.json`
afterward if needed.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -v`
Expected: 61 passed (58 pre-existing + 3 new), output pristine.

- [ ] **Step 7: Commit**

```bash
git add add_search.py tests/test_add_search.py .github/workflows/add-search.yml README.md requirements-dev.txt
git commit -m "fix: validate emails, lock field-label contract, harden workflow persistence"
```

---

### Task 9: `pending_searches.json` + email confirmation in `add_search.py`

**Files:**
- Modify: `add_search.py`
- Modify: `tests/test_add_search.py`

**Interfaces:**
- Consumes: `check_logement.send_email`, `check_logement._require_env` (both existing).
- Produces: `PENDING_SEARCHES_PATH = Path("pending_searches.json")`, `load_pending_searches(path=PENDING_SEARCHES_PATH) -> dict[str, Any]`, `save_pending_searches(pending, path=PENDING_SEARCHES_PATH) -> None`, `build_confirmation_url(token: str) -> str`, `build_confirmation_email_body(search_name: str, confirmation_url: str) -> str`.
- Modifies: `main()` — when `emails` is non-empty, the search is no longer added directly to `searches.json`; instead each email gets a random token, a confirmation email is sent to it, and the search + pending tokens are written to `pending_searches.json`. When `emails` is empty, behavior is unchanged (immediate activation, `ALERT_EMAIL` fallback).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_add_search.py` (add `import secrets` is NOT needed in the test
file — only production code needs it):

```python
def test_main_creates_pending_entry_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    sent = []
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(
            (subject, to_addrs, body)
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" in pending
    assert list(pending["Agen"]["pending_emails"].values()) == ["a@example.com"]
    assert len(sent) == 1
    assert sent[0][1] == ["a@example.com"]
    assert "issues/new?template=confirm-email.yml&code=" in sent[0][2]
    assert "LZ-Aissam/logement-crous-alert" in sent[0][2]


def test_main_rejects_duplicate_name_already_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Brest": {
                    "search": {"name": "Brest", "url": "https://example.com"},
                    "pending_emails": {},
                }
            }
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nbrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1


def test_main_requires_gmail_env_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    with pytest.raises(SystemExit):
        mod.main()


def test_main_still_activates_immediately_without_emails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    assert not (tmp_path / "pending_searches.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -v`
Expected: FAIL — `AttributeError: module 'add_search' has no attribute 'PENDING_SEARCHES_PATH'` (or similar, for the pending-related tests); `test_main_still_activates_immediately_without_emails` may already pass since it matches current behavior — that's fine, TDD is about the *new* behavior.

- [ ] **Step 3: Implement the pending-confirmation flow**

Add near the top of `add_search.py`, alongside the other module constants:

```python
import secrets as secrets_module
```

(Use `secrets_module` as the import alias to avoid any confusion with a local variable
named `secrets` if one exists in `main()` — check the current code first; if there is no
naming conflict, a plain `import secrets` is fine and preferred. Use whichever is
clean given the actual current file content.)

Add after `discover_filters`:

```python
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


def build_confirmation_url(token: str) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    return (
        f"https://github.com/{repo}/issues/new"
        f"?template=confirm-email.yml&code={urllib.parse.quote(token)}"
    )


def build_confirmation_email_body(search_name: str, confirmation_url: str) -> str:
    return (
        "Quelqu'un a demande a recevoir des alertes de logement CROUS a cette adresse "
        f"email, pour la recherche {search_name!r}.\n\n"
        "Si c'est bien toi, confirme en cliquant sur ce lien (necessite un compte "
        f"GitHub, gratuit) :\n{confirmation_url}\n\n"
        "Si tu n'es pas a l'origine de cette demande, ignore simplement cet email -- "
        "rien ne sera active sans ta confirmation."
    )
```

Now restructure `main()`. Read the current implementation first (from Task 8) to see
its exact current shape, then apply these changes precisely:

1. The duplicate-name check must also look in pending searches:
```python
    pending = load_pending_searches()
    existing_names = {s["name"].strip().lower() for s in searches} | {
        n.strip().lower() for n in pending
    }
    if name.strip().lower() in existing_names:
        print(f"ERROR: une recherche nommee {name!r} existe deja")
        return 1
```
   (Replace the current single-source duplicate check with this two-source version —
   keep it positioned exactly where the current duplicate check is, i.e. after loading
   `searches` and before `geocode_city`.)

2. Replace the final "build entry, append, save" block with a branch on whether `emails`
   is empty:

```python
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
        smtp_user = clog._require_env("GMAIL_ADDRESS")
        smtp_password = clog._require_env("GMAIL_APP_PASSWORD")
        pending_emails: dict[str, str] = {}
        for email in emails:
            token = secrets.token_urlsafe(16)
            pending_emails[token] = email
            confirmation_url = build_confirmation_url(token)
            confirmation_body = build_confirmation_email_body(name, confirmation_url)
            clog.send_email(
                subject=f"Confirme ton adresse pour la recherche {name!r}",
                body=confirmation_body,
                to_addrs=[email],
                smtp_user=smtp_user,
                smtp_password=smtp_password,
            )
        pending[name] = {"search": entry, "pending_emails": pending_emails}
        save_pending_searches(pending)
        lines.insert(
            0,
            f"OK: recherche {name!r} creee EN ATTENTE de confirmation email pour {city!r}.",
        )
        lines.append(
            f"Email(s) en attente de confirmation : {', '.join(emails)}. Un email de "
            "confirmation a ete envoye a chaque adresse. La recherche ne sera active "
            "qu'une fois qu'au moins un email aura confirme."
        )
    else:
        searches.append(entry)
        clog.save_searches(searches)
        lines.insert(0, f"OK: recherche {name!r} ajoutee pour {city!r}.")
        lines.append("Destinataire : email par defaut (ALERT_EMAIL)")

    print("\n".join(lines))
    return 0
```

   Remove whatever old code block this replaces (the version from Task 4/8 that always
   called `searches.append(entry)` / `clog.save_searches(searches)` unconditionally, and
   always appended a `Destinataires : ...` / `Destinataire : email par defaut` line at
   the end regardless of the emails branch). Use `import secrets` (plain, no alias)
   unless you find an actual naming collision in the current file — check first.

3. Update `.github/workflows/add-search.yml`'s "Commit and push data files" step (added
   in Task 8) to also stage the new file:
```yaml
          git add searches.json pending_searches.json
```
   (This is the one line that Task 8 deliberately left as `git add searches.json` only,
   forward-referencing this task.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -v`
Expected: 65 passed (61 pre-existing + 4 new), output pristine.

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py .github/workflows/add-search.yml
git commit -m "feat: require email confirmation before activating a submitted search"
```

---

### Task 10: `confirm_email.py`

**Files:**
- Create: `confirm_email.py`
- Create: `tests/test_confirm_email.py`

**Interfaces:**
- Consumes: `add_search.load_pending_searches`, `add_search.save_pending_searches`, `add_search.parse_issue_form_body`, `check_logement.load_searches`, `check_logement.save_searches`, `check_logement.SEARCHES_PATH` (all existing).
- Produces: `main() -> int` reading `ISSUE_BODY` from the environment; CLI entry point via `if __name__ == "__main__"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_confirm_email.py`:

```python
import json

import pytest

import check_logement as clog
import confirm_email as mod


def test_main_confirms_first_email_and_activates_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {"tok123": "a@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Agen", "url": "https://example.com/agen", "emails": ["a@example.com"]}
    ]
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" not in pending


def test_main_confirms_second_email_appends_to_existing_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Agen", "url": "https://example.com/agen", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {"tok456": "b@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok456\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com", "b@example.com"]
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" not in pending


def test_main_keeps_pending_entry_when_other_emails_remain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {"tok1": "a@example.com", "tok2": "b@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok1\n")

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert list(pending["Agen"]["pending_emails"].values()) == ["b@example.com"]


def test_main_rejects_unknown_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pending_searches.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\nunknown-token\n")

    exit_code = mod.main()

    assert exit_code == 1


def test_main_requires_code(monkeypatch):
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\n_No response_\n")

    assert mod.main() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_confirm_email.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'confirm_email'`.

- [ ] **Step 3: Create `confirm_email.py`**

```python
"""Process a GitHub Issue Form submission confirming an email address for a pending search."""
from __future__ import annotations

import json
import os
import sys

import check_logement as clog
from add_search import (
    load_pending_searches,
    parse_issue_form_body,
    save_pending_searches,
)

FIELD_CODE = "Code de confirmation"


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)
    code = fields.get(FIELD_CODE)

    if not code:
        print("ERROR: code de confirmation manquant")
        return 1

    pending = load_pending_searches()

    for search_name, record in pending.items():
        pending_emails = record.get("pending_emails", {})
        if code not in pending_emails:
            continue

        email = pending_emails.pop(code)

        if clog.SEARCHES_PATH.exists():
            try:
                searches = clog.load_searches()
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                print(f"ERROR: impossible de lire searches.json existant : {exc}")
                return 1
        else:
            searches = []

        existing = next(
            (
                s
                for s in searches
                if s["name"].strip().lower() == search_name.strip().lower()
            ),
            None,
        )
        if existing is not None:
            emails_list = existing.setdefault("emails", [])
            if email not in emails_list:
                emails_list.append(email)
        else:
            entry = dict(record["search"])
            entry["emails"] = [email]
            searches.append(entry)

        clog.save_searches(searches)

        if pending_emails:
            pending[search_name]["pending_emails"] = pending_emails
        else:
            del pending[search_name]
        save_pending_searches(pending)

        print(
            f"OK: email {email!r} confirme pour la recherche {search_name!r}. "
            "Cette recherche est maintenant active."
        )
        return 0

    print("ERROR: code de confirmation invalide ou deja utilise")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_confirm_email.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full project test suite**

Run: `python -m pytest -v`
Expected: 71 passed (65 pre-existing + 6 new), output pristine.

- [ ] **Step 6: Commit**

```bash
git add confirm_email.py tests/test_confirm_email.py
git commit -m "feat: add confirm_email script to activate pending searches"
```

---

### Task 11: Confirmation Issue Form and workflow

**Files:**
- Create: `.github/ISSUE_TEMPLATE/confirm-email.yml`
- Create: `.github/workflows/confirm-email.yml`

**Interfaces:**
- Consumes: `confirm_email.py`'s `main()` (Task 10) as the workflow's executable entry point, reading `ISSUE_BODY` from the environment and exiting 0/1.

- [ ] **Step 1: Create the confirmation Issue Form**

`.github/ISSUE_TEMPLATE/confirm-email.yml`:

```yaml
name: Confirmer mon email
description: Confirme que tu acceptes de recevoir des alertes logement a cette adresse
title: "[Confirmation email]"
labels: ["confirm-email"]
body:
  - type: input
    id: code
    attributes:
      label: Code de confirmation
      description: Le code fourni dans l'email de confirmation que tu as recu
    validations:
      required: true
```

- [ ] **Step 2: Create the confirmation workflow**

`.github/workflows/confirm-email.yml`:

```yaml
name: Confirm email for pending search

on:
  issues:
    types: [opened]

permissions:
  contents: write
  issues: write

concurrency:
  group: confirm-email
  cancel-in-progress: false

jobs:
  confirm-email:
    if: contains(github.event.issue.labels.*.name, 'confirm-email')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Process email confirmation
        id: process
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
        run: |
          if python confirm_email.py > result.txt 2>&1; then
            echo "success=true" >> "$GITHUB_OUTPUT"
          else
            echo "success=false" >> "$GITHUB_OUTPUT"
          fi
          cat result.txt

      - name: Comment with result
        if: always()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body-file result.txt

      - name: Commit and push data files
        id: persist
        if: steps.process.outputs.success == 'true'
        run: |
          git config user.name "logement-alert-bot"
          git config user.email "actions@users.noreply.github.com"
          git add searches.json pending_searches.json
          if git diff --staged --quiet; then
            echo "persisted=true" >> "$GITHUB_OUTPUT"
          else
            if git commit -m "chore: confirm email from issue #${{ github.event.issue.number }}" \
                && git pull --rebase --autostash \
                && git push; then
              echo "persisted=true" >> "$GITHUB_OUTPUT"
            else
              echo "persisted=false" >> "$GITHUB_OUTPUT"
            fi
          fi

      - name: Close issue on full success
        if: steps.process.outputs.success == 'true' && steps.persist.outputs.persisted == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue close ${{ github.event.issue.number }} --repo ${{ github.repository }}

      - name: Warn if persistence failed
        if: steps.process.outputs.success == 'true' && steps.persist.outputs.persisted == 'false'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh issue comment ${{ github.event.issue.number }} --repo ${{ github.repository }} --body "Erreur technique lors de l'enregistrement (collision Git). Le workflow va probablement reussir si tu resoumets une nouvelle issue dans quelques minutes."
```

- [ ] **Step 3: Run the full test suite once (sanity check, no code changed in this task)**

Run: `python -m pytest -v`
Expected: 71 passed (unchanged from Task 10 — this task added no Python code).

- [ ] **Step 4: Commit**

```bash
git add .github/ISSUE_TEMPLATE/confirm-email.yml .github/workflows/confirm-email.yml
git commit -m "feat: add confirmation Issue Form and workflow"
```

---

### Task 12: README updates for email confirmation

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Document the email confirmation requirement**

Add a section (near the existing Issue Form documentation from Task 6) explaining:
- If the "new search" form includes one or more email addresses, the search is created
  **en attente** (pending) — no alerts are sent yet.
- A confirmation email is sent to each address, with a link to a second form
  ("Confirmer mon email"). Clicking it requires a GitHub account (free) to submit the
  confirmation form.
- Once at least one email confirms, the search becomes active with that email as
  recipient; other emails can confirm later and get added too.
- If no email is given, the search activates immediately using the default
  (`ALERT_EMAIL`) — no confirmation needed, since that's the repo owner's own trusted
  address.
- This confirmation step exists specifically to stop someone from entering a stranger's
  email address and causing them to receive unwanted automated mail.

- [ ] **Step 2: Run the test suite once (docs-only change)**

Run: `python -m pytest -v`
Expected: 71 passed, unchanged.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the email confirmation requirement"
```

---

### Task 13: Manual end-to-end verification (final)

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `python -m pytest -v`
Expected: 71 passed, output pristine.

- [ ] **Step 2: Locally simulate the full new-search + confirmation flow**

```bash
export GMAIL_ADDRESS="<real address>" GMAIL_APP_PASSWORD="<real app password>" \
       GITHUB_REPOSITORY="LZ-Aissam/logement-crous-alert"
export ISSUE_BODY='### Nom de la recherche

Test manuel confirmation

### Ville

Rennes

### Mots-clés (résidence, type de logement...) - optionnel

_No response_

### Email(s) de notification - optionnel

<a real, disposable test address you control>'
python add_search.py
cat pending_searches.json
```

Expected: prints an "EN ATTENTE" message, `pending_searches.json` contains the new
entry with one token, and a real confirmation email arrives at the test address with a
working `https://github.com/LZ-Aissam/logement-crous-alert/issues/new?template=confirm-email.yml&code=...`
link. Then simulate confirming it locally:

```bash
export ISSUE_BODY="### Code de confirmation

<the token from pending_searches.json>"
python confirm_email.py
cat searches.json
```

Expected: the search moves into `searches.json` with the test email as recipient, and
`pending_searches.json` no longer has an entry for it. Afterward, restore both files to
their original committed state (`git checkout -- searches.json pending_searches.json`
or delete `pending_searches.json` if it didn't exist before and reset `searches.json`) —
this was a local-only dry run.

- [ ] **Step 3: Push to GitHub and submit real Issue Forms**

Push the branch, merge, and push to the GitHub remote (secrets `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, `ALERT_EMAIL` must already be configured, per the existing
README). On the repository's Issues tab, confirm both "Nouvelle recherche de logement"
and "Confirmer mon email" appear as template options. Submit a new search with a real
city and a real test email address you control (not the repo owner's own email, to
prove the pending flow). Confirm: the `add-search` workflow runs, comments that the
search is pending, and does NOT close the issue... actually it should still close on
success even though the search is pending (creating the pending record successfully
IS the "success" outcome) — confirm the issue closes and a real confirmation email
arrives at the test address. Click the link in that email (creating/using a GitHub
account if needed) and submit the "Confirmer mon email" form. Confirm the
`confirm-email` workflow runs, comments confirmation, closes that second issue, and
`searches.json` on the default branch now contains the entry with the confirmed email.

- [ ] **Step 4: Confirm the existing poller still works with the updated `searches.json`**

Manually trigger the "Check CROUS housing" workflow (`workflow_dispatch`) and confirm it
runs cleanly against the updated `searches.json`, then remove the test entries added in
Step 3 (edit `searches.json`/`pending_searches.json` on GitHub, or via a follow-up
commit) to keep the repo's real configuration clean.
