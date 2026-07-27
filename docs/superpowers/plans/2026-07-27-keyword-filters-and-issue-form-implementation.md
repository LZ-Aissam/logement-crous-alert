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

### Task 7: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `python -m pytest -v`
Expected: 54 passed, output pristine.

- [ ] **Step 2: Locally simulate an issue submission**

```bash
export ISSUE_BODY='### Nom de la recherche

Test manuel

### Ville

Rennes

### Mots-clés (résidence, type de logement...) - optionnel

_No response_

### Email(s) de notification - optionnel

_No response_'
python add_search.py
```

Expected: prints an `OK: recherche 'Test manuel' ajoutee...` message with a real geocoded
URL for Rennes, and appends the entry to the local `searches.json`. Confirm with
`cat searches.json`, then remove the test entry (`git checkout -- searches.json` or
manually edit it back) before pushing — this was a local-only dry run.

- [ ] **Step 3: Push to GitHub and submit a real Issue Form**

Push the branch, merge, and push to the GitHub remote. On the repository's Issues tab,
click "New issue" and confirm "Nouvelle recherche de logement" appears as a template
option. Submit it with a real city (e.g. one you don't already track) and no keywords.
Confirm: the `add-search` workflow runs, the issue receives a confirmation comment, the
issue closes automatically, and `searches.json` on the default branch now contains the
new entry with a bot commit.

- [ ] **Step 4: Confirm the existing poller still works with the updated `searches.json`**

Manually trigger the "Check CROUS housing" workflow (`workflow_dispatch`) and confirm it
runs cleanly against the updated `searches.json` (no errors from the newly added
search), then remove the test entry added in Step 3 if it was only for verification
(edit `searches.json` on GitHub, or via a follow-up commit) to keep the repo's real
configuration clean.
