# Filtres de recherche avancés Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add autocomplete-based place selection (Photon proxy, precise `extent` bounds) and 4 optional filters (max price, min area, occupation mode, PMR accessibility) to the search-creation form, matching what trouverunlogement.lescrous.fr's own form offers — verified against the real site's HTML and API behavior.

**Architecture:** The 4 filters (`maxPrice`, `minArea`, `occupationMode`, `prm`) are appended as query parameters to the search URL stored in `searches.json` — CROUS's own server applies them before we ever fetch results, so `check_logement.py` needs zero changes. The autocomplete's selected-place `extent` (four floats, same `west_north_east_south` format already used for `bounds`) replaces the fixed-size box currently computed around a geocoded point, but only when present and valid — the existing geocode-and-compute-a-box fallback stays intact for manual GitHub Issue submissions and for free-text entries with no selected suggestion.

**Tech Stack:** Python 3.12 stdlib (`re`), vanilla JS (no new npm dependencies), YAML (GitHub Issue Forms). No new runtime dependencies anywhere.

## Global Constraints

- No new runtime dependencies (Python: stdlib only; JS: no npm packages).
- French for all user-facing strings (labels, descriptions, error messages).
- All 5 new fields (place selection's `extent`, `maxPrice`, `minArea`, `occupationMode`, `prm`) are optional — omitting all of them must reproduce today's exact behavior (fixed-box geocoding, unfiltered search URL).
- Field ids in the GitHub Issue Form, the JS payload keys, and the Python `FIELD_*` constant *values* (the rendered `### Label` text) must all match exactly — this project has an established cross-file contract-test convention (`tests/test_add_search.py`) for exactly this; extend it, don't bypass it.
- `check_logement.py` is not modified by this plan — filtering happens server-side on CROUS's end via URL query parameters already proven to work (see spec).

---

### Task 1: `add_search.py` — extent, price, area, occupation mode, PMR

**Files:**
- Modify: `add_search.py` (constants near top, `build_search_url`, `main()`)
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_search_url(lon: float | None, lat: float | None, location_label: str, extent: str | None = None, max_price: int | None = None, min_area: int | None = None, occupation_modes: list[str] | None = None, prm: bool = False) -> str` (was `build_search_url(lon: float, lat: float, location_label: str) -> str` — the two new positional params stay required-by-position but `lon`/`lat` are now allowed to be `None` when `extent` is valid, since geocoding becomes unnecessary in that case). New module constants `FIELD_EXTENT`, `FIELD_MAX_PRICE`, `FIELD_MIN_AREA`, `FIELD_OCCUPATION_MODE`, `FIELD_PRM`, `EXTENT_RE`, `VALID_OCCUPATION_MODES`, `OCCUPATION_MODE_LABELS` — Task 3 (Issue Form) and Task 4 (frontend) depend on these exact field label strings and occupation-mode value set.

- [ ] **Step 1: Write the failing tests for `build_search_url`**

Add to `tests/test_add_search.py` (near the existing `test_build_search_url_contains_bounds_and_tool_id`, around line 95):

```python
def test_build_search_url_uses_extent_when_valid():
    url = mod.build_search_url(
        None, None, "Brest", extent="-4.5689169_48.4595521_-4.4278311_48.3572972"
    )
    assert url == (
        "https://trouverunlogement.lescrous.fr/tools/47/search"
        "?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest"
    )


def test_build_search_url_falls_back_when_extent_invalid():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", extent="not-a-valid-extent")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=0.56")


def test_build_search_url_falls_back_when_extent_missing():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=0.56")


def test_build_search_url_appends_max_price():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", max_price=400)
    assert "&maxPrice=400" in url


def test_build_search_url_appends_min_area():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", min_area=15)
    assert "&minArea=15" in url


def test_build_search_url_appends_occupation_modes():
    url = mod.build_search_url(
        0.631041, 44.202304, "Agen 47000", occupation_modes=["alone", "house_sharing"]
    )
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url


def test_build_search_url_ignores_invalid_occupation_mode():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", occupation_modes=["alone", "bogus"])
    assert "&occupationMode=alone" in url
    assert "bogus" not in url


def test_build_search_url_appends_prm():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", prm=True)
    assert "&prm=true" in url


def test_build_search_url_omits_prm_when_false():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", prm=False)
    assert "prm" not in url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -k build_search_url -v`
Expected: FAIL with `TypeError: build_search_url() got an unexpected keyword argument 'extent'`

- [ ] **Step 3: Implement the new constants and `build_search_url`**

In `add_search.py`, add near the top (after the existing `FIELD_EMAILS` constant, around line 31):

```python
FIELD_EXTENT = "Zone geographique precise (rempli automatiquement) - optionnel"
FIELD_MAX_PRICE = "Prix maximum - optionnel"
FIELD_MIN_AREA = "Surface minimum en m2 - optionnel"
FIELD_OCCUPATION_MODE = "Type de cohabitation (individuel, couple, colocation) - optionnel"
FIELD_PRM = "Logement adapte PMR - optionnel"

EXTENT_RE = re.compile(r"^-?\d+(\.\d+)?_-?\d+(\.\d+)?_-?\d+(\.\d+)?_-?\d+(\.\d+)?$")

VALID_OCCUPATION_MODES = {"alone", "couple", "house_sharing"}

OCCUPATION_MODE_LABELS = {
    "individuel": "alone",
    "couple": "couple",
    "colocation": "house_sharing",
}
```

Replace `build_search_url` (currently `add_search.py:65-75`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -k build_search_url -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: add extent/price/area/occupation-mode/PMR params to build_search_url"
```

- [ ] **Step 6: Write the failing tests for `main()` parsing and validation**

Add to `tests/test_add_search.py`:

```python
def test_main_uses_extent_instead_of_geocoding_when_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nRésidence Kergoat\n\n"
        "### Ville\n\nRésidence Kergoat Brest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-4.5689169_48.4595521_-4.4278311_48.3572972\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\n_No response_\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    def fail_geocode(city):
        raise AssertionError("geocode_city should not be called when extent is valid")

    monkeypatch.setattr(mod, "geocode_city", fail_geocode)
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert "bounds=-4.5689169_48.4595521_-4.4278311_48.3572972" in searches[0]["url"]


def test_main_applies_price_area_occupation_prm_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n400\n\n"
        "### Surface minimum en m2 - optionnel\n\n15\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nIndividuel, Colocation\n\n"
        "### Logement adapte PMR - optionnel\n\noui\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    url = searches[0]["url"]
    assert "&maxPrice=400" in url
    assert "&minArea=15" in url
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url
    assert "&prm=true" in url


def test_main_accepts_english_occupation_mode_values_from_the_public_form(tmp_path, monkeypatch):
    # The public form's checkboxes send API values directly (e.g. "alone,house_sharing"),
    # unlike a manually-typed GitHub Issue which sends French labels -- both must work.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nalone,house_sharing\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    url = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))[0]["url"]
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url


def test_main_rejects_non_numeric_max_price(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\npas un nombre\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\n_No response_\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_main_ignores_unrecognized_occupation_mode_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nBaragouin\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    url = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))[0]["url"]
    assert "occupationMode" not in url
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -k "extent_instead_of_geocoding or applies_price_area or accepts_english_occupation_mode or rejects_non_numeric or ignores_unrecognized" -v`
Expected: FAIL (existing `main()` doesn't read these fields, existing calls to `build_search_url` don't pass them)

- [ ] **Step 8: Implement the parsing and validation in `main()`**

In `add_search.py`, replace the field-reading block (currently `add_search.py:157-160`):

```python
    name = fields.get(FIELD_NAME)
    city = fields.get(FIELD_CITY)
    keywords_raw = fields.get(FIELD_KEYWORDS)
    emails_raw = fields.get(FIELD_EMAILS)
```

with:

```python
    name = fields.get(FIELD_NAME)
    city = fields.get(FIELD_CITY)
    keywords_raw = fields.get(FIELD_KEYWORDS)
    emails_raw = fields.get(FIELD_EMAILS)
    extent_raw = fields.get(FIELD_EXTENT)
    max_price_raw = fields.get(FIELD_MAX_PRICE)
    min_area_raw = fields.get(FIELD_MIN_AREA)
    occupation_mode_raw = fields.get(FIELD_OCCUPATION_MODE)
    prm_raw = fields.get(FIELD_PRM)
```

Immediately after the existing `if not name or not city:` guard (currently `add_search.py:162-164`), insert:

```python
    max_price: int | None = None
    if max_price_raw:
        try:
            max_price = int(max_price_raw.strip())
            if max_price < 0:
                raise ValueError
        except ValueError:
            print(f"ERROR: prix maximum invalide : {max_price_raw!r}")
            return 1

    min_area: int | None = None
    if min_area_raw:
        try:
            min_area = int(min_area_raw.strip())
            if min_area < 0:
                raise ValueError
        except ValueError:
            print(f"ERROR: surface minimum invalide : {min_area_raw!r}")
            return 1

    # Two paths feed this field: the public form's checkboxes already send valid
    # API values directly (e.g. "alone,house_sharing"), while a manually-submitted
    # GitHub Issue is expected to contain French labels (e.g. "Individuel,
    # Colocation") -- accept either, matching whichever the caller sent.
    occupation_modes = []
    for label in _split_csv(occupation_mode_raw):
        normalized = label.strip().lower()
        if normalized in VALID_OCCUPATION_MODES:
            occupation_modes.append(normalized)
        elif normalized in OCCUPATION_MODE_LABELS:
            occupation_modes.append(OCCUPATION_MODE_LABELS[normalized])

    prm = bool(prm_raw)

    has_valid_extent = bool(extent_raw and EXTENT_RE.match(extent_raw))
```

Replace the geocoding + URL-building block (currently `add_search.py:190-196`):

```python
    try:
        lon, lat = geocode_city(city)
    except GeocodeError as exc:
        print(f"ERROR: {exc}")
        return 1

    url = build_search_url(lon, lat, city)
```

with:

```python
    lon: float | None = None
    lat: float | None = None
    if not has_valid_extent:
        try:
            lon, lat = geocode_city(city)
        except GeocodeError as exc:
            print(f"ERROR: {exc}")
            return 1

    url = build_search_url(
        lon,
        lat,
        city,
        extent=extent_raw,
        max_price=max_price,
        min_area=min_area,
        occupation_modes=occupation_modes,
        prm=prm,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -k "extent_instead_of_geocoding or applies_price_area or accepts_english_occupation_mode or rejects_non_numeric or ignores_unrecognized" -v`
Expected: PASS (5 tests)

- [ ] **Step 10: Run the full Python test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass — every pre-existing `ISSUE_BODY` in the test file omits the 5 new field sections entirely, and `parse_issue_form_body` simply won't have those keys, so `fields.get(FIELD_EXTENT)` etc. return `None` and every new code path takes its "not provided" branch, reproducing today's exact behavior.

- [ ] **Step 11: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: parse and validate extent/price/area/occupation-mode/PMR in add_search.py main()"
```

---

### Task 2: `netlify/functions/create-search.js` — new fields

**Files:**
- Modify: `netlify/functions/create-search.js`
- Test: `netlify/functions/__tests__/create-search.test.js`

**Interfaces:**
- Consumes: nothing new from other tasks (mirrors Task 1's field label strings by literal value, not by import — matches the existing pattern where `create-search.js` and `add_search.py` each hardcode the same strings, verified equal only by the cross-file test in Task 3).
- Produces: `buildIssueBody(fields)` now includes 5 more `### Label` sections. `handler` rejects non-numeric `maxPrice`/`minArea` with 400. Payload shape consumed by Task 4's `index.html`: `{ name, city, keywords, emails, website, extent, maxPrice, minArea, occupationMode, prm }`.

- [ ] **Step 1: Write the failing tests**

Add to `netlify/functions/__tests__/create-search.test.js` (mirroring the existing "valid payload creates a GitHub issue" test):

```javascript
test("valid payload includes the 5 new optional sections in the issue body", async (t) => {
  const originalFetch = global.fetch;
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ html_url: "https://github.com/o/r/issues/3" }) };
  };
  process.env.GITHUB_REPOSITORY = "o/r";
  process.env.GITHUB_PAT = "tok";
  t.after(() => {
    global.fetch = originalFetch;
    process.env.GITHUB_REPOSITORY = originalRepo;
    process.env.GITHUB_PAT = originalToken;
  });

  const result = await handler(
    makeEvent(
      {
        name: "Brest",
        city: "Brest 29200",
        extent: "-4.5689169_48.4595521_-4.4278311_48.3572972",
        maxPrice: "400",
        minArea: "15",
        occupationMode: "alone,house_sharing",
        prm: "true",
      },
      "203.0.113.31"
    )
  );

  assert.equal(result.statusCode, 200);
  const sentBody = JSON.parse(calls[0].options.body);
  assert.match(
    sentBody.body,
    /### Zone geographique precise \(rempli automatiquement\) - optionnel\n\n-4\.5689169_48\.4595521_-4\.4278311_48\.3572972\n/
  );
  assert.match(sentBody.body, /### Prix maximum - optionnel\n\n400\n/);
  assert.match(sentBody.body, /### Surface minimum en m2 - optionnel\n\n15\n/);
  assert.match(
    sentBody.body,
    /### Type de cohabitation \(individuel, couple, colocation\) - optionnel\n\nalone,house_sharing\n/
  );
  assert.match(sentBody.body, /### Logement adapte PMR - optionnel\n\ntrue\n/);
});

test("non-numeric maxPrice returns 400", async () => {
  const result = await handler(
    makeEvent({ name: "Brest", city: "Brest 29200", maxPrice: "gratuit" }, "203.0.113.32")
  );
  assert.equal(result.statusCode, 400);
});

test("non-numeric minArea returns 400", async () => {
  const result = await handler(
    makeEvent({ name: "Brest", city: "Brest 29200", minArea: "grand" }, "203.0.113.33")
  );
  assert.equal(result.statusCode, 400);
});

test("missing optional new fields still succeeds (backward compatible)", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ html_url: "https://github.com/o/r/issues/3" }),
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(makeEvent({ name: "Brest", city: "Brest 29200" }, "203.0.113.34"));
  assert.equal(result.statusCode, 200);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — the new sections aren't in `buildIssueBody`'s output yet, and the numeric-validation tests fail because no validation exists yet.

- [ ] **Step 3: Implement the new fields and validation**

Replace the field constants block in `netlify/functions/create-search.js` (currently lines 9-12):

```javascript
const FIELD_NAME = "Nom de la recherche";
const FIELD_CITY = "Ville";
const FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel";
const FIELD_EMAILS = "Email(s) de notification - optionnel";
```

with:

```javascript
const FIELD_NAME = "Nom de la recherche";
const FIELD_CITY = "Ville";
const FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel";
const FIELD_EMAILS = "Email(s) de notification - optionnel";
const FIELD_EXTENT = "Zone geographique precise (rempli automatiquement) - optionnel";
const FIELD_MAX_PRICE = "Prix maximum - optionnel";
const FIELD_MIN_AREA = "Surface minimum en m2 - optionnel";
const FIELD_OCCUPATION_MODE = "Type de cohabitation (individuel, couple, colocation) - optionnel";
const FIELD_PRM = "Logement adapte PMR - optionnel";
```

Replace `buildIssueBody` (currently lines 19-26):

```javascript
function buildIssueBody(fields) {
  return [
    section(FIELD_NAME, fields.name),
    section(FIELD_CITY, fields.city),
    section(FIELD_KEYWORDS, fields.keywords),
    section(FIELD_EMAILS, fields.emails),
  ].join("\n");
}
```

with:

```javascript
function buildIssueBody(fields) {
  return [
    section(FIELD_NAME, fields.name),
    section(FIELD_CITY, fields.city),
    section(FIELD_KEYWORDS, fields.keywords),
    section(FIELD_EMAILS, fields.emails),
    section(FIELD_EXTENT, fields.extent),
    section(FIELD_MAX_PRICE, fields.maxPrice),
    section(FIELD_MIN_AREA, fields.minArea),
    section(FIELD_OCCUPATION_MODE, fields.occupationMode),
    section(FIELD_PRM, fields.prm),
  ].join("\n");
}
```

Add numeric validation right after the existing required-fields check (currently lines 51-56, the `if (!fields.name || ...)` block) and before the `try { const issue = ...` block:

```javascript
  if (fields.maxPrice && fields.maxPrice.trim() && Number.isNaN(Number(fields.maxPrice))) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le prix maximum doit etre un nombre." }),
    };
  }

  if (fields.minArea && fields.minArea.trim() && Number.isNaN(Number(fields.minArea))) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "La surface minimum doit etre un nombre." }),
    };
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS (all tests, including the 4 new ones)

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/create-search.js netlify/functions/__tests__/create-search.test.js
git commit -m "feat: add extent/price/area/occupation-mode/PMR fields to create-search.js"
```

---

### Task 3: Issue Form template + cross-file label contract tests

**Files:**
- Modify: `.github/ISSUE_TEMPLATE/new-search.yml`
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: `add_search.FIELD_EXTENT`/`FIELD_MAX_PRICE`/`FIELD_MIN_AREA`/`FIELD_OCCUPATION_MODE`/`FIELD_PRM` (Task 1), `netlify/functions/create-search.js`'s field constants (Task 2).
- Produces: 5 new Issue Form fields with ids `extent`, `maxPrice`, `minArea`, `occupationMode`, `prm` — these ids are also the JSON payload keys Task 4's `index.html` must use.

- [ ] **Step 1: Add the 5 fields to the Issue Form template**

Append to the `body:` list in `.github/ISSUE_TEMPLATE/new-search.yml` (after the existing `emails` field):

```yaml
  - type: input
    id: extent
    attributes:
      label: Zone geographique precise (rempli automatiquement) - optionnel
      description: >-
        Normalement rempli automatiquement par le formulaire public quand tu
        selectionnes une suggestion. Laisse vide pour une soumission manuelle -- la
        recherche utilisera la ville renseignee ci-dessus avec une zone par defaut.
    validations:
      required: false
  - type: input
    id: maxPrice
    attributes:
      label: Prix maximum - optionnel
      description: En euros. Laisse vide pour aucune limite de prix.
      placeholder: "400"
    validations:
      required: false
  - type: input
    id: minArea
    attributes:
      label: Surface minimum en m2 - optionnel
      description: Laisse vide pour aucune limite de surface.
      placeholder: "15"
    validations:
      required: false
  - type: input
    id: occupationMode
    attributes:
      label: Type de cohabitation (individuel, couple, colocation) - optionnel
      description: >-
        Separes par des virgules parmi : individuel, couple, colocation. Laisse
        vide pour ne pas filtrer par type de cohabitation.
      placeholder: individuel, colocation
    validations:
      required: false
  - type: input
    id: prm
    attributes:
      label: Logement adapte PMR - optionnel
      description: Ecris "oui" pour ne voir que les logements adaptes PMR. Laisse vide sinon.
      placeholder: "oui"
    validations:
      required: false
```

- [ ] **Step 2: Write the failing cross-file contract tests**

Extend `test_field_label_constants_match_issue_form_yaml` in `tests/test_add_search.py` (find it, currently around line 297) by adding these assertions inside the existing test function, right after the existing `assert labels_by_id["emails"] == mod.FIELD_EMAILS` line:

```python
    assert labels_by_id["extent"] == mod.FIELD_EXTENT
    assert labels_by_id["maxPrice"] == mod.FIELD_MAX_PRICE
    assert labels_by_id["minArea"] == mod.FIELD_MIN_AREA
    assert labels_by_id["occupationMode"] == mod.FIELD_OCCUPATION_MODE
    assert labels_by_id["prm"] == mod.FIELD_PRM
```

Extend `test_js_field_labels_match_python_constants` (currently around line 309) by adding these assertions right after the existing `assert f'const FIELD_EMAILS = "{mod.FIELD_EMAILS}";' in js_source` line:

```python
    assert f'const FIELD_EXTENT = "{mod.FIELD_EXTENT}";' in js_source
    assert f'const FIELD_MAX_PRICE = "{mod.FIELD_MAX_PRICE}";' in js_source
    assert f'const FIELD_MIN_AREA = "{mod.FIELD_MIN_AREA}";' in js_source
    assert f'const FIELD_OCCUPATION_MODE = "{mod.FIELD_OCCUPATION_MODE}";' in js_source
    assert f'const FIELD_PRM = "{mod.FIELD_PRM}";' in js_source
```

Note: this reads `netlify/functions/create-search.js`, which Task 2 already updated with these exact `const` declarations — if Task 2 was skipped or done differently, this test will fail and that's the point (it's the safety net for label drift between the three files).

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -k "field_label_constants_match_issue_form_yaml or js_field_labels_match_python_constants" -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Validate the YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/new-search.yml', encoding='utf-8'))"`
Expected: no output, exit code 0

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `python -m pytest -v && npm test`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add .github/ISSUE_TEMPLATE/new-search.yml tests/test_add_search.py
git commit -m "feat: add extent/price/area/occupation-mode/PMR fields to the new-search Issue Form"
```

---

### Task 4: `public/index.html` — autocomplete combobox + filter fields

**Files:**
- Modify: `public/index.html`

**Interfaces:**
- Consumes: `https://trouverunlogement.lescrous.fr/photon/api` (third-party, verified working, see spec), `/.netlify/functions/create-search` payload contract from Task 2 (`{ name, city, keywords, emails, website, extent, maxPrice, minArea, occupationMode, prm }`).
- Produces: nothing consumed elsewhere in this plan.

- [ ] **Step 1: Read the current file**

Read `public/index.html` in full. You'll replace the "Ville" field block and insert new filter fields; the `<script>` block's `fetch`/honeypot/result-message logic keeps its existing structure — you're adding new payload keys and new DOM wiring, not changing the success/error handling shape.

- [ ] **Step 2: Replace the "Ville" field with the autocomplete combobox**

Replace this block (currently inside the `<form id="search-form">`):

```html
            <div class="mb-3">
              <label for="city" class="form-label fw-semibold">Ville</label>
              <input id="city" name="city" required placeholder="Brest 29200" class="form-control form-control-lg">
            </div>
```

with:

```html
            <div class="mb-3" style="position: relative;">
              <label for="city" class="form-label fw-semibold">Ville, résidence ou lieu d'étude</label>
              <input id="city" name="city" required placeholder="Brest, ou une résidence, ou une école..."
                     class="form-control form-control-lg" autocomplete="off" role="combobox"
                     aria-expanded="false" aria-controls="city-suggestions" aria-autocomplete="list">
              <input type="hidden" id="extent" name="extent">
              <ul id="city-suggestions" class="list-group position-absolute w-100 d-none"
                  role="listbox" style="z-index: 1000; max-height: 260px; overflow-y: auto;"></ul>
            </div>
```

- [ ] **Step 3: Add the 4 new filter fields**

Insert this block right after the "Mots-clés" field's closing `</div>` and before the "Email(s)" field's opening `<div class="mb-4">`:

```html
            <div class="row g-3 mb-3">
              <div class="col-sm-6">
                <label for="maxPrice" class="form-label fw-semibold">Prix maximum - optionnel</label>
                <input id="maxPrice" name="maxPrice" type="number" min="0" step="1"
                       placeholder="Sans limite" class="form-control form-control-lg">
              </div>
              <div class="col-sm-6">
                <label for="minArea" class="form-label fw-semibold">Surface minimum en m² - optionnel</label>
                <input id="minArea" name="minArea" type="number" min="0" step="1"
                       placeholder="Sans limite" class="form-control form-control-lg">
              </div>
            </div>

            <div class="mb-3">
              <span class="form-label fw-semibold d-block">Type de cohabitation - optionnel</span>
              <div class="form-check form-check-inline">
                <input class="form-check-input" type="checkbox" id="occupation-alone" name="occupationMode" value="alone">
                <label class="form-check-label" for="occupation-alone">Individuel</label>
              </div>
              <div class="form-check form-check-inline">
                <input class="form-check-input" type="checkbox" id="occupation-couple" name="occupationMode" value="couple">
                <label class="form-check-label" for="occupation-couple">Couple</label>
              </div>
              <div class="form-check form-check-inline">
                <input class="form-check-input" type="checkbox" id="occupation-house_sharing" name="occupationMode" value="house_sharing">
                <label class="form-check-label" for="occupation-house_sharing">Colocation</label>
              </div>
            </div>

            <div class="mb-3">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="prm" name="prm">
                <label class="form-check-label" for="prm">Logement adapté PMR</label>
              </div>
            </div>
```

- [ ] **Step 4: Add the autocomplete JS**

Inside the existing `<script>` block, add this code **before** the existing `const form = document.getElementById("search-form");` line:

```javascript
  const cityInput = document.getElementById("city");
  const extentInput = document.getElementById("extent");
  const suggestionsList = document.getElementById("city-suggestions");
  let debounceTimer = null;
  let activeIndex = -1;
  let currentSuggestions = [];

  function clearSuggestions() {
    suggestionsList.innerHTML = "";
    suggestionsList.classList.add("d-none");
    cityInput.setAttribute("aria-expanded", "false");
    currentSuggestions = [];
    activeIndex = -1;
  }

  function renderSuggestions(features) {
    currentSuggestions = features;
    activeIndex = -1;
    if (!features.length) {
      clearSuggestions();
      return;
    }
    suggestionsList.innerHTML = features
      .map((f, i) => {
        const p = f.properties || {};
        const context = [p.postcode, p.state].filter(Boolean).join(" - ");
        const label = context ? `${p.name} (${context})` : p.name;
        return `<li class="list-group-item list-group-item-action" role="option" id="suggestion-${i}" data-index="${i}">${label}</li>`;
      })
      .join("");
    suggestionsList.classList.remove("d-none");
    cityInput.setAttribute("aria-expanded", "true");
  }

  function updateActiveOption() {
    Array.from(suggestionsList.children).forEach((li, i) => {
      li.classList.toggle("active", i === activeIndex);
    });
    const active = suggestionsList.children[activeIndex];
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  function selectSuggestion(index) {
    const feature = currentSuggestions[index];
    if (!feature) return;
    const p = feature.properties || {};
    cityInput.value = p.name || "";
    const extent = p.extent;
    extentInput.value = extent && extent.length === 4 ? extent.join("_") : "";
    clearSuggestions();
  }

  cityInput.addEventListener("input", () => {
    extentInput.value = "";
    const query = cityInput.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);
    if (query.length < 2) {
      clearSuggestions();
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q: query, limit: "8", lang: "fr" });
        [
          "amenity:college", "amenity:library", "amenity:school", "amenity:university",
          "place:country", "place:region", "place:state", "place:city", "place:town",
          "place:village", "place:house", "landuse:residential",
        ].forEach((tag) => params.append("osm_tag", tag));
        const response = await fetch("https://trouverunlogement.lescrous.fr/photon/api?" + params.toString());
        if (!response.ok) {
          clearSuggestions();
          return;
        }
        const data = await response.json();
        renderSuggestions(data.features || []);
      } catch (err) {
        clearSuggestions();
      }
    }, 300);
  });

  cityInput.addEventListener("keydown", (event) => {
    if (suggestionsList.classList.contains("d-none")) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, currentSuggestions.length - 1);
      updateActiveOption();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      updateActiveOption();
    } else if (event.key === "Enter") {
      if (activeIndex >= 0) {
        event.preventDefault();
        selectSuggestion(activeIndex);
      }
    } else if (event.key === "Escape") {
      clearSuggestions();
    }
  });

  suggestionsList.addEventListener("click", (event) => {
    const li = event.target.closest("li[data-index]");
    if (!li) return;
    selectSuggestion(parseInt(li.dataset.index, 10));
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("#city") && !event.target.closest("#city-suggestions")) {
      clearSuggestions();
    }
  });
```

- [ ] **Step 5: Extend the submit payload**

Replace the `payload` object inside the existing `form.addEventListener("submit", ...)` handler:

```javascript
    const payload = {
      name: form.name.value,
      city: form.city.value,
      keywords: form.keywords.value,
      emails: form.emails.value,
      website: form.website.value,
    };
```

with:

```javascript
    const payload = {
      name: form.name.value,
      city: form.city.value,
      keywords: form.keywords.value,
      emails: form.emails.value,
      website: form.website.value,
      extent: extentInput.value,
      maxPrice: form.maxPrice.value,
      minArea: form.minArea.value,
      occupationMode: Array.from(form.querySelectorAll('input[name="occupationMode"]:checked'))
        .map((cb) => cb.value)
        .join(","),
      prm: form.prm.checked ? "true" : "",
    };
```

- [ ] **Step 6: Render and self-critique via headless browser**

Use the Playwright-based headless screenshot technique (no build step needed — `npm install playwright-core` in the scratchpad dir if not already available this session, cached Chromium binary, launch pointed at a local `python -m http.server` serving `public/`; see project memory `feedback_design_iteration.md` for the exact working recipe from the prior showcase-redesign session). Screenshot the form area at ~1280px and ~390px. Additionally, drive it with Playwright's `page.fill`/`page.keyboard.type` on the `#city` field with a real query (e.g. "Brest") and screenshot again after ~1s to confirm the suggestions dropdown actually renders with real Photon results (this hits the real network, which is fine for a one-off manual verification, not a repeatable test). Confirm: the dropdown doesn't overflow/clip oddly, selecting a suggestion fills the hidden `extent` field (check via `page.$eval('#extent', el => el.value)`), the new filter fields are visibly present and usable, keyboard arrow-down/enter selects a suggestion. Fix any CSS/JS issue found before moving on — this is the same "build, screenshot, critique, fix" loop used for the showcase redesign, not optional polish.

- [ ] **Step 7: Commit**

```bash
git add public/index.html
git commit -m "feat: add place autocomplete and price/area/occupation-mode/PMR filters to the search form"
```

---

### Task 5: Document the new filters in the README

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Extend the "Ajouter une recherche via une Issue GitHub" section**

In `README.md`, find the numbered list of Issue Form fields under "## Ajouter une recherche via une Issue GitHub" (the one listing "Nom de la recherche", "Ville", "Mots-clés", "Email(s) de notification"). Add after the existing `emails` bullet:

```markdown
   - **Zone géographique précise** (optionnel) : normalement laissé vide pour une
     Issue manuelle — rempli automatiquement par le formulaire public quand une
     suggestion est sélectionnée.
   - **Prix maximum** (optionnel) : en euros.
   - **Surface minimum en m²** (optionnel).
   - **Type de cohabitation** (optionnel) : `individuel`, `couple`, `colocation`,
     séparés par des virgules.
   - **Logement adapté PMR** (optionnel) : écris `oui` pour filtrer sur
     l'accessibilité PMR.
```

- [ ] **Step 2: Add a short note near the public form description**

In the section describing the public form (`## Formulaire public sans compte GitHub`), add one paragraph:

```markdown
Le champ "Ville, résidence ou lieu d'étude" propose des suggestions en direct (ville,
résidence, école...) via le même service que le site CROUS officiel — sélectionner une
suggestion cible précisément le bon endroit plutôt qu'une zone approximative autour
d'une ville. Les filtres prix/surface/cohabitation/PMR sont transmis tels quels au
site CROUS, qui applique le filtrage lui-même avant que le robot ne récupère les
résultats.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the place autocomplete and price/area/occupation-mode/PMR filters"
```

---

### Task 6: Manual end-to-end verification

**Files:** none (manual, no code changes expected unless it surfaces a bug).

**Interfaces:** consumes the fully implemented system from Tasks 1-5, deployed to Netlify.

- [ ] **Step 1: Verify autocomplete on the live site**

Open `https://logement-crous-alert.netlify.app/`, type a city name in "Ville, résidence ou lieu d'étude", confirm suggestions appear, select one, confirm the field fills with the selected name (the `extent` hidden field isn't visible in the UI — that's expected).

- [ ] **Step 2: Submit a test search with filters**

Fill the form with a test search name, a selected place, a max price, a min area, one occupation mode, and PMR checked. Submit. Confirm success message. Check the created GitHub Issue (`gh issue list --label new-search`) to confirm all 5 new fields appear correctly in the Issue body.

- [ ] **Step 3: Verify the stored search URL**

After the bot processes the Issue (`gh issue view <number> --comments`), check `searches.json` (`git pull` first) for the new entry — confirm its `url` contains `bounds=<the selected place's extent>`, `maxPrice=`, `minArea=`, `occupationMode=`, and `prm=true` as submitted.

- [ ] **Step 4: Clean up the test search**

Remove the test entry from `searches.json` (and its `seen.json` key if present) the same way prior features' manual verification steps did in this project, and push.

- [ ] **Step 5: Report back**

Summarize what was verified. No further code changes are expected unless this surfaces a bug.
