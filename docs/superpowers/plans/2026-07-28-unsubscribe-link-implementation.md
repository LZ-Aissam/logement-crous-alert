# Lien de désinscription dans les emails d'alerte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a personalized unsubscribe link to every alert email, letting a recipient remove their own address from a specific search (no GitHub account required if the optional Netlify facade is configured), matching the design in `docs/superpowers/specs/2026-07-28-unsubscribe-link-design.md`.

**Architecture:** A new stateless HMAC token (`HMAC-SHA256(UNSUBSCRIBE_SECRET, "{search_name}|{email}")`) is embedded in the unsubscribe link. `check_logement.py` builds the link and now sends one email per recipient (instead of one grouped email) so each link can be personalized. Clicking the link opens either a GitHub Issue (default) or a Netlify page (if configured) that recreates the same Issue; a new `unsubscribe.py`, triggered by a new GitHub Actions workflow, recomputes and verifies the token and removes the email from `searches.json` (deleting the search entirely if it was the last recipient).

**Tech Stack:** Python 3.12 (stdlib `hmac`/`hashlib`/`urllib.parse`), `pytest`, Node.js built-in `node:test`, GitHub Actions, Netlify Functions (unchanged JS patterns from the existing `create-search.js`/`confirm-email.js`).

## Global Constraints

- No new runtime dependencies (Python: stdlib only; JS: no npm packages, matching the existing `netlify/functions` code).
- French for all user-facing strings (issue templates, email text, HTML pages, error messages), matching the rest of the project.
- `UNSUBSCRIBE_SECRET` absent → no unsubscribe link is added to alert emails, and nothing else breaks (same "optional, backward-compatible" rule as `CONFIRMATION_BASE_URL`).
- Case-insensitive matching for search names and email addresses, matching existing `confirm_email.py`/`add_search.py` conventions.
- Every new/modified Python function and JS function gets tests before being considered done (TDD, per steps below).

---

### Task 1: `compute_unsubscribe_token` and `build_unsubscribe_url` in `check_logement.py`

**Files:**
- Modify: `check_logement.py` (add imports + two new functions, no changes to existing functions)
- Test: `tests/test_check_logement.py` (append new tests)

**Interfaces:**
- Consumes: nothing new (stdlib `hashlib`, `hmac`, `urllib.parse`; env vars `UNSUBSCRIBE_SECRET`, `UNSUBSCRIBE_BASE_URL`, `GITHUB_REPOSITORY`).
- Produces:
  - `compute_unsubscribe_token(search_name: str, email: str) -> str | None` — returns `None` if `UNSUBSCRIBE_SECRET` is unset, else the hex HMAC-SHA256 digest of `f"{search_name}|{email.lower()}"`.
  - `build_unsubscribe_url(search_name: str, email: str) -> str | None` — returns `None` if `compute_unsubscribe_token` returns `None`; otherwise a URL pointing at `UNSUBSCRIBE_BASE_URL` (if set) or a GitHub "new issue" URL prefilled with `template=unsubscribe.yml`.

- [ ] **Step 1: Write the failing tests for `compute_unsubscribe_token`**

Append to `tests/test_check_logement.py`:

```python
import hashlib
import hmac as hmac_module


def test_compute_unsubscribe_token_returns_none_when_secret_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    assert mod.compute_unsubscribe_token("Brest", "x@example.com") is None


def test_compute_unsubscribe_token_matches_expected_hmac(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    token = mod.compute_unsubscribe_token("Brest", "x@example.com")

    expected = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert token == expected


def test_compute_unsubscribe_token_is_case_insensitive_on_email(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    lower = mod.compute_unsubscribe_token("Brest", "x@example.com")
    upper = mod.compute_unsubscribe_token("Brest", "X@EXAMPLE.COM")

    assert lower == upper


def test_compute_unsubscribe_token_differs_per_search_and_email(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    token_a = mod.compute_unsubscribe_token("Brest", "x@example.com")
    token_b = mod.compute_unsubscribe_token("Rennes", "x@example.com")
    token_c = mod.compute_unsubscribe_token("Brest", "y@example.com")

    assert len({token_a, token_b, token_c}) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -k compute_unsubscribe_token -v`
Expected: FAIL with `AttributeError: module 'check_logement' has no attribute 'compute_unsubscribe_token'`

- [ ] **Step 3: Implement `compute_unsubscribe_token`**

In `check_logement.py`, add to the imports at the top of the file (after the existing `import json`):

```python
import hashlib
import hmac
```

Add the function anywhere after `save_seen` and before `load_searches` (grouping it near the other pure helpers):

```python
def compute_unsubscribe_token(search_name: str, email: str) -> str | None:
    secret = os.environ.get("UNSUBSCRIBE_SECRET")
    if not secret:
        return None
    return hmac.new(
        secret.encode("utf-8"),
        f"{search_name}|{email.lower()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -k compute_unsubscribe_token -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: add compute_unsubscribe_token helper"
```

- [ ] **Step 6: Write the failing tests for `build_unsubscribe_url`**

Append to `tests/test_check_logement.py`:

```python
def test_build_unsubscribe_url_returns_none_when_secret_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    assert mod.build_unsubscribe_url("Brest", "x@example.com") is None


def test_build_unsubscribe_url_uses_base_url_when_set(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url("Brest", "x@example.com")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
    )


def test_build_unsubscribe_url_falls_back_to_github_when_base_url_unset(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.delenv("UNSUBSCRIBE_BASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")

    url = mod.build_unsubscribe_url("Brest", "x@example.com")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://github.com/LZ-Aissam/logement-crous-alert/issues/new"
        f"?template=unsubscribe.yml&search=Brest&email=x%40example.com&token={expected_token}"
    )
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -k build_unsubscribe_url -v`
Expected: FAIL with `AttributeError: module 'check_logement' has no attribute 'build_unsubscribe_url'`

- [ ] **Step 8: Implement `build_unsubscribe_url`**

Add to the imports at the top of `check_logement.py`:

```python
import urllib.parse
```

Add the function directly after `compute_unsubscribe_token`:

```python
def build_unsubscribe_url(search_name: str, email: str) -> str | None:
    token = compute_unsubscribe_token(search_name, email)
    if token is None:
        return None
    query = (
        f"search={urllib.parse.quote(search_name)}"
        f"&email={urllib.parse.quote(email)}"
        f"&token={token}"
    )
    base_url = os.environ.get("UNSUBSCRIBE_BASE_URL")
    if base_url:
        return f"{base_url}?{query}"
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    return f"https://github.com/{repo}/issues/new?template=unsubscribe.yml&{query}"
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -k build_unsubscribe_url -v`
Expected: PASS (3 tests)

- [ ] **Step 10: Run the full Python test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass (no existing test references `compute_unsubscribe_token`/`build_unsubscribe_url`, so none should be affected)

- [ ] **Step 11: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: add build_unsubscribe_url helper"
```

---

### Task 2: Per-recipient alert emails with a personalized unsubscribe footer

**Files:**
- Modify: `check_logement.py:151-166` (`format_email_body`), `check_logement.py:189-238` (`main`)
- Test: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: `build_unsubscribe_url(search_name, email) -> str | None` from Task 1.
- Produces: `format_email_body(search_name: str, new_items: list, search_url: str, unsubscribe_url: str | None = None) -> str` (new 4th optional parameter — existing 3-arg call sites keep working unchanged). `main()`'s observable behavior changes from one `send_email` call per search (with all recipients in one `to_addrs` list) to one `send_email` call per recipient (each with a single-element `to_addrs` list).

- [ ] **Step 1: Write the failing tests for the `format_email_body` footer**

Append to `tests/test_check_logement.py`:

```python
def test_format_email_body_appends_unsubscribe_link_when_provided():
    new_items = [{"id": 1, "label": "T1", "residence": {"label": "R"}}]

    body = mod.format_email_body(
        "Brest",
        new_items,
        "https://example.com/search",
        unsubscribe_url="https://example.com/unsub?token=abc",
    )

    assert "Pour ne plus recevoir ces alertes : https://example.com/unsub?token=abc" in body


def test_format_email_body_omits_unsubscribe_section_when_none():
    new_items = [{"id": 1, "label": "T1", "residence": {"label": "R"}}]

    body = mod.format_email_body("Brest", new_items, "https://example.com/search")

    assert "Pour ne plus recevoir ces alertes" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -k unsubscribe_link_when_provided -v`
Expected: FAIL with `TypeError: format_email_body() got an unexpected keyword argument 'unsubscribe_url'`

- [ ] **Step 3: Implement the footer in `format_email_body`**

Replace the existing `format_email_body` function (`check_logement.py:151-166`):

```python
def format_email_body(
    search_name: str,
    new_items: list[dict[str, Any]],
    search_url: str,
    unsubscribe_url: str | None = None,
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
    if unsubscribe_url:
        lines.append("")
        lines.append(f"Pour ne plus recevoir ces alertes : {unsubscribe_url}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -k "unsubscribe_link_when_provided or omits_unsubscribe" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: add optional unsubscribe footer to alert emails"
```

- [ ] **Step 6: Write the failing tests for per-recipient sending**

Append to `tests/test_check_logement.py`:

```python
def test_main_sends_individual_email_per_recipient_with_personalized_unsubscribe_link(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Brest",
                    "url": "https://example.com/brest",
                    "emails": ["a@example.com", "b@example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

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
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append((to_addrs, body)),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert [addrs for addrs, _ in sent] == [["a@example.com"], ["b@example.com"]]
    body_a = next(body for addrs, body in sent if addrs == ["a@example.com"])
    body_b = next(body for addrs, body in sent if addrs == ["b@example.com"])
    assert "email=a%40example.com" in body_a
    assert "email=b%40example.com" in body_b
    token_a = body_a.rsplit("token=", 1)[1]
    token_b = body_b.rsplit("token=", 1)[1]
    assert token_a != token_b


def test_main_marks_seen_when_at_least_one_recipient_succeeds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Brest",
                    "url": "https://example.com/brest",
                    "emails": ["a@example.com", "b@example.com"],
                }
            ]
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
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )

    def fake_send_email(subject, body, to_addrs, smtp_user, smtp_password):
        if to_addrs == ["a@example.com"]:
            raise mod.smtplib.SMTPException("boom")

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -k "personalized_unsubscribe_link or marks_seen_when_at_least_one" -v`
Expected: FAIL — `test_main_sends_individual_email_per_recipient...` fails because `sent` currently gets one call with `to_addrs == ["a@example.com", "b@example.com"]` instead of two separate calls.

- [ ] **Step 8: Refactor `main()` for per-recipient sending**

In `check_logement.py`, inside `main()` (`check_logement.py:189-238`), replace:

```python
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
```

with:

```python
        try:
            html = fetch_html(url)
            results = parse_search_results(html)
            items = results.get("items") or []
            items = [i for i in items if _item_matches_keywords(i, search.get("keywords"))]
            seen_ids = seen.get(name, [])
            new_items, all_ids = find_new_items(items, seen_ids)
            if new_items:
                subject = f"[Logement] {len(new_items)} nouveau(x) pour {name}"
        except (SearchFetchError, KeyError, TypeError, AttributeError) as exc:
            print(f"[ERROR] {name}: {exc}", file=sys.stderr)
            continue

        any_success = True

        if new_items:
            sent_count = 0
            for recipient in recipients:
                unsubscribe_url = build_unsubscribe_url(name, recipient)
                try:
                    body = format_email_body(name, new_items, url, unsubscribe_url)
                    send_email(subject, body, [recipient], smtp_user, smtp_password)
                except Exception as exc:
                    print(f"[ERROR] {name}: failed to send email to {recipient}: {exc}", file=sys.stderr)
                    continue
                sent_count += 1
            if sent_count == 0:
                print(f"[ERROR] {name}: failed to send alert to any recipient", file=sys.stderr)
                continue
            print(f"[OK] {name}: sent alert for {len(new_items)} new listing(s) to {sent_count} recipient(s)")
        else:
            print(f"[OK] {name}: no new listings ({len(items)} total)")

        seen[name] = sorted(set(seen_ids) | set(all_ids))
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -k "personalized_unsubscribe_link or marks_seen_when_at_least_one" -v`
Expected: PASS (2 tests)

- [ ] **Step 10: Run the full Python test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass — existing single-recipient tests (`test_main_sends_email_for_new_listings_and_updates_seen`, `test_main_uses_alert_email_default_when_search_has_no_emails`, `test_main_email_send_failure_does_not_block_others_or_mark_seen`, etc.) all use exactly one recipient per search, so a loop over one recipient still produces exactly one `send_email` call with the same `to_addrs` shape as before.

- [ ] **Step 11: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: send one alert email per recipient with a personalized unsubscribe link"
```

---

### Task 3: `unsubscribe.py` — verify the token and update `searches.json`

**Files:**
- Create: `unsubscribe.py`
- Test: `tests/test_unsubscribe.py`

**Interfaces:**
- Consumes: `check_logement.compute_unsubscribe_token`, `check_logement.SEARCHES_PATH`, `check_logement.load_searches`, `check_logement.save_searches` (all already exist); `add_search.parse_issue_form_body` (already exists, used identically by `confirm_email.py`).
- Produces: `unsubscribe.py` with `main() -> int`, reading `ISSUE_BODY` and `UNSUBSCRIBE_SECRET` from the environment. Exit code `0` on success (including no-op idempotent cases), `1` on validation failure.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_unsubscribe.py`:

```python
import json

import check_logement as clog
import unsubscribe as mod


def _issue_body(search, email, token):
    return (
        f"### Nom de la recherche\n\n{search}\n\n"
        f"### Email\n\n{email}\n\n"
        f"### Jeton\n\n{token}\n"
    )


def test_main_removes_email_and_keeps_search_when_others_remain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Brest",
                    "url": "https://example.com/brest",
                    "emails": ["a@example.com", "b@example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}
    ]


def test_main_removes_search_entirely_when_last_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]},
                {"name": "Rennes", "url": "https://example.com/rennes", "emails": ["c@example.com"]},
            ]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Rennes", "url": "https://example.com/rennes", "emails": ["c@example.com"]}
    ]


def test_main_rejects_invalid_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", "not-the-real-token"))

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com"]


def test_main_requires_all_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "_No response_", "sometoken"))

    assert mod.main() == 1


def test_main_requires_unsubscribe_secret_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", "sometoken"))

    assert mod.main() == 1


def test_main_noop_when_search_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_main_noop_when_email_not_subscribed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "stranger@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "stranger@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com"]


def test_main_is_case_insensitive_for_search_name_and_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["A@Example.com"]}]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_unsubscribe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'unsubscribe'`

- [ ] **Step 3: Implement `unsubscribe.py`**

Create `unsubscribe.py`:

```python
"""Process a GitHub Issue Form submission unsubscribing an email from a search."""
from __future__ import annotations

import hmac
import json
import os
import sys

import check_logement as clog
from add_search import parse_issue_form_body

FIELD_SEARCH = "Nom de la recherche"
FIELD_EMAIL = "Email"
FIELD_TOKEN = "Jeton"


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)
    search_name = fields.get(FIELD_SEARCH)
    email = fields.get(FIELD_EMAIL)
    token = fields.get(FIELD_TOKEN)

    if not search_name or not email or not token:
        print("ERROR: nom de la recherche, email et jeton sont obligatoires")
        return 1

    expected = clog.compute_unsubscribe_token(search_name, email)
    if expected is None:
        print("ERROR: UNSUBSCRIBE_SECRET n'est pas configure sur ce depot")
        return 1

    if not hmac.compare_digest(expected, token.strip()):
        print("ERROR: jeton de desinscription invalide")
        return 1

    if not clog.SEARCHES_PATH.exists():
        print(f"OK: recherche {search_name!r} introuvable, rien a faire")
        return 0

    try:
        searches = clog.load_searches()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: impossible de lire searches.json existant : {exc}")
        return 1

    target = next(
        (s for s in searches if s["name"].strip().lower() == search_name.strip().lower()),
        None,
    )
    if target is None:
        print(f"OK: recherche {search_name!r} introuvable, deja desinscrite ou supprimee")
        return 0

    emails = target.get("emails") or []
    remaining = [e for e in emails if e.strip().lower() != email.strip().lower()]

    if len(remaining) == len(emails):
        print(f"OK: {email!r} n'etait pas destinataire de {search_name!r}, rien a faire")
        return 0

    if remaining:
        target["emails"] = remaining
        clog.save_searches(searches)
        print(
            f"OK: {email!r} desinscrit de {search_name!r}. "
            "La recherche continue pour les autres destinataires."
        )
    else:
        searches = [s for s in searches if s is not target]
        clog.save_searches(searches)
        print(
            f"OK: {email!r} desinscrit de {search_name!r}. "
            "C'etait le dernier destinataire, la recherche a ete supprimee."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_unsubscribe.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full Python test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add unsubscribe.py tests/test_unsubscribe.py
git commit -m "feat: add unsubscribe.py to process desinscription requests"
```

---

### Task 4: Issue template, GitHub Actions workflow, and `check.yml` wiring

**Files:**
- Create: `.github/ISSUE_TEMPLATE/unsubscribe.yml`
- Create: `.github/workflows/unsubscribe.yml`
- Modify: `.github/workflows/check.yml`

**Interfaces:**
- Consumes: `unsubscribe.py` (Task 3, invoked as `python unsubscribe.py`), `check_logement.py`'s `UNSUBSCRIBE_SECRET`/`UNSUBSCRIBE_BASE_URL`/`GITHUB_REPOSITORY` env var names (Task 1/2).
- Produces: label `unsubscribe` triggers the new workflow on issue creation; three Issue Form fields (`search`/`email`/`token` ids) whose rendered `### Label` headers (`Nom de la recherche` / `Email` / `Jeton`) exactly match `unsubscribe.py`'s `FIELD_SEARCH`/`FIELD_EMAIL`/`FIELD_TOKEN` constants and Task 5's `unsubscribe.js` `buildIssueBody`.

- [ ] **Step 1: Create the Issue Form template**

Create `.github/ISSUE_TEMPLATE/unsubscribe.yml`:

```yaml
name: Desinscription des alertes
description: Retire une adresse email des notifications d'une recherche
title: "[Desinscription]"
labels: ["unsubscribe"]
body:
  - type: input
    id: search
    attributes:
      label: Nom de la recherche
      description: Le nom exact de la recherche indique dans l'email d'alerte
    validations:
      required: true
  - type: input
    id: email
    attributes:
      label: Email
      description: L'adresse email a retirer de cette recherche
    validations:
      required: true
  - type: input
    id: token
    attributes:
      label: Jeton
      description: Le jeton fourni dans le lien de desinscription de l'email
    validations:
      required: true
```

- [ ] **Step 2: Validate the YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/ISSUE_TEMPLATE/unsubscribe.yml', encoding='utf-8'))"`
Expected: no output, exit code 0

- [ ] **Step 3: Create the workflow**

Create `.github/workflows/unsubscribe.yml`:

```yaml
name: Unsubscribe from search alerts

on:
  issues:
    types: [opened]

permissions:
  contents: write
  issues: write

concurrency:
  group: unsubscribe
  cancel-in-progress: false

jobs:
  unsubscribe:
    if: contains(github.event.issue.labels.*.name, 'unsubscribe')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Process unsubscribe request
        id: process
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
          UNSUBSCRIBE_SECRET: ${{ secrets.UNSUBSCRIBE_SECRET }}
        run: |
          if python unsubscribe.py > result.txt 2>&1; then
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
          git add searches.json
          if git diff --staged --quiet; then
            echo "persisted=true" >> "$GITHUB_OUTPUT"
          else
            if git commit -m "chore: unsubscribe from issue #${{ github.event.issue.number }}" \
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

- [ ] **Step 4: Validate the YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/unsubscribe.yml', encoding='utf-8'))"`
Expected: no output, exit code 0

- [ ] **Step 5: Wire the new env vars into `check.yml`**

In `.github/workflows/check.yml`, replace the `Run housing check` step's `env:` block:

```yaml
      - name: Run housing check
        run: python check_logement.py
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
```

with:

```yaml
      - name: Run housing check
        run: python check_logement.py
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
          UNSUBSCRIBE_SECRET: ${{ secrets.UNSUBSCRIBE_SECRET }}
          UNSUBSCRIBE_BASE_URL: ${{ secrets.UNSUBSCRIBE_BASE_URL }}
          GITHUB_REPOSITORY: ${{ github.repository }}
```

- [ ] **Step 6: Validate the YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/check.yml', encoding='utf-8'))"`
Expected: no output, exit code 0

- [ ] **Step 7: Run the full Python test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass (no Python source changed in this task)

- [ ] **Step 8: Commit**

```bash
git add .github/ISSUE_TEMPLATE/unsubscribe.yml .github/workflows/unsubscribe.yml .github/workflows/check.yml
git commit -m "feat: add unsubscribe Issue Form, workflow, and check.yml wiring"
```

---

### Task 5: `netlify/functions/unsubscribe.js`

**Files:**
- Create: `netlify/functions/unsubscribe.js`
- Test: `netlify/functions/__tests__/unsubscribe.test.js`

**Interfaces:**
- Consumes: `isHoneypotFilled`, `createRateLimiter`, `createGithubIssue`, `clientIp` from `./_github` (unchanged); the Issue Form field labels from Task 4 (`Nom de la recherche` / `Email` / `Jeton`) and label `unsubscribe`.
- Produces: `module.exports = { handler, buildIssueBody }`. `handler(event)` accepts `POST` with JSON body `{ search, email, token, website }` and returns `{ statusCode, body }` where `body` is JSON `{ issueUrl }` on success or `{ error }` on failure — same contract as `confirm-email.js`/`create-search.js`.

- [ ] **Step 1: Write the failing tests**

Create `netlify/functions/__tests__/unsubscribe.test.js`:

```javascript
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { handler } = require("../unsubscribe");

function makeEvent(fields, ip) {
  return {
    httpMethod: "POST",
    headers: { "x-forwarded-for": ip },
    body: JSON.stringify(fields),
  };
}

test("rejects non-POST requests", async () => {
  const result = await handler({ httpMethod: "GET" });
  assert.equal(result.statusCode, 405);
});

test("honeypot filled returns fake success without calling the GitHub API", async (t) => {
  const originalFetch = global.fetch;
  let called = false;
  global.fetch = async () => {
    called = true;
    return { ok: true, json: async () => ({ html_url: "unused" }) };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(
    makeEvent(
      { search: "Brest", email: "a@example.com", token: "tok", website: "spam" },
      "203.0.113.21"
    )
  );

  assert.equal(result.statusCode, 200);
  assert.equal(called, false);
});

test("missing fields returns 400", async () => {
  const result = await handler(
    makeEvent({ search: "Brest", email: "", token: "tok" }, "203.0.113.22")
  );
  assert.equal(result.statusCode, 400);
});

test("valid payload creates a GitHub issue matching the Issue Form contract", async (t) => {
  const originalFetch = global.fetch;
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ html_url: "https://github.com/o/r/issues/5" }) };
  };
  process.env.GITHUB_REPOSITORY = "o/r";
  process.env.GITHUB_PAT = "tok";
  t.after(() => {
    global.fetch = originalFetch;
    process.env.GITHUB_REPOSITORY = originalRepo;
    process.env.GITHUB_PAT = originalToken;
  });

  const result = await handler(
    makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, "203.0.113.23")
  );

  assert.equal(result.statusCode, 200);
  assert.deepEqual(JSON.parse(result.body), { issueUrl: "https://github.com/o/r/issues/5" });
  const sentBody = JSON.parse(calls[0].options.body);
  assert.equal(sentBody.title, "[Desinscription]");
  assert.deepEqual(sentBody.labels, ["unsubscribe"]);
  assert.equal(
    sentBody.body,
    "### Nom de la recherche\n\nBrest\n\n### Email\n\na@example.com\n\n### Jeton\n\nabc123\n"
  );
});

test("GitHub API failure returns 502", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 500, text: async () => "boom" });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(
    makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, "203.0.113.24")
  );
  assert.equal(result.statusCode, 502);
});

test("rate limit trips after 5 requests from the same IP within the window", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ html_url: "https://github.com/o/r/issues/5" }),
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const ip = "203.0.113.25";
  for (let i = 0; i < 5; i++) {
    const result = await handler(
      makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, ip)
    );
    assert.equal(result.statusCode, 200);
  }
  const sixth = await handler(
    makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, ip)
  );
  assert.equal(sixth.statusCode, 429);
});
```

- [ ] **Step 2: Update the test glob to pick up the new file**

`package.json`'s test script already globs `netlify/functions/__tests__/*.test.js`, so no change is needed here — just run the tests to confirm they fail first:

Run: `npm test`
Expected: FAIL with `Error: Cannot find module '../unsubscribe'`

- [ ] **Step 3: Implement `unsubscribe.js`**

Create `netlify/functions/unsubscribe.js`:

```javascript
"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

function section(label, value) {
  const trimmed = value && value.trim();
  return `### ${label}\n\n${trimmed || "_No response_"}\n`;
}

function buildIssueBody(fields) {
  return [
    section("Nom de la recherche", fields.search),
    section("Email", fields.email),
    section("Jeton", fields.token),
  ].join("\n");
}

async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  let fields;
  try {
    fields = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: "JSON invalide" }) };
  }

  if (isHoneypotFilled(fields)) {
    return { statusCode: 200, body: JSON.stringify({ issueUrl: null }) };
  }

  if (rateLimiter.isRateLimited(clientIp(event))) {
    return {
      statusCode: 429,
      body: JSON.stringify({ error: "Trop de tentatives, reessaie dans une heure." }),
    };
  }

  const missing =
    !fields.search || !fields.search.trim() ||
    !fields.email || !fields.email.trim() ||
    !fields.token || !fields.token.trim();
  if (missing) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "La recherche, l'email et le jeton sont obligatoires." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: "[Desinscription]",
      body: buildIssueBody(fields),
      labels: ["unsubscribe"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch (err) {
    console.error("unsubscribe: GitHub API call failed", err);
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, reessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS (all tests across all three `__tests__/*.test.js` files, including the 6 new ones)

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/unsubscribe.js netlify/functions/__tests__/unsubscribe.test.js
git commit -m "feat: add unsubscribe Netlify function"
```

---

### Task 6: `public/desabonnement.html`

**Files:**
- Create: `public/desabonnement.html`

**Interfaces:**
- Consumes: `POST /.netlify/functions/unsubscribe` from Task 5, contract `{ search, email, token, website } -> { issueUrl }` or `{ error }`. Reads `search`, `email`, `token` from the page's own URL query string (as built by `build_unsubscribe_url` in Task 1).
- Produces: a static page, no other file depends on it.

- [ ] **Step 1: Create the page**

Create `public/desabonnement.html`:

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Se desinscrire - Alerte logement CROUS</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
  button { margin-top: 1.5rem; padding: 0.6rem 1.2rem; }
  #result { margin-top: 1.5rem; padding: 1rem; border-radius: 4px; }
  #result.success { background: #e6f4ea; }
  #result.error { background: #fce8e6; }
  #result.hidden { display: none; }
  .honeypot { position: absolute; left: -9999px; top: -9999px; }
</style>
</head>
<body>
<h1>Se desinscrire</h1>
<p id="intro">Clique sur le bouton ci-dessous pour ne plus recevoir d'alertes pour cette recherche.</p>

<div class="honeypot" aria-hidden="true">
  <label for="website">Laisse ce champ vide</label>
  <input id="website" tabindex="-1" autocomplete="off">
</div>

<button id="unsubscribe-button" type="button">Se desinscrire</button>
<div id="result" class="hidden"></div>

<script>
  const params = new URLSearchParams(window.location.search);
  const search = params.get("search");
  const email = params.get("email");
  const token = params.get("token");
  const button = document.getElementById("unsubscribe-button");
  const result = document.getElementById("result");
  const intro = document.getElementById("intro");
  const website = document.getElementById("website");

  if (!search || !email || !token) {
    button.disabled = true;
    result.textContent = "Lien invalide : informations manquantes dans l'URL.";
    result.className = "error";
  } else {
    intro.textContent = 'Se desinscrire de la recherche "' + search + '" pour l\'adresse ' + email + ' ?';
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    result.className = "hidden";

    try {
      const response = await fetch("/.netlify/functions/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ search, email, token, website: website.value }),
      });
      const data = await response.json();

      if (!response.ok) {
        result.textContent = data.error || "Une erreur est survenue.";
        result.className = "error";
        button.disabled = false;
        return;
      }

      result.textContent = "Desinscription envoyee.";
      result.className = "success";
    } catch (err) {
      result.textContent = "Une erreur est survenue, reessaie dans quelques minutes.";
      result.className = "error";
      button.disabled = false;
    }
  });
</script>
</body>
</html>
```

- [ ] **Step 2: Manual smoke check (no automated test exists for static pages in this project, matching `index.html`/`confirmer.html`)**

Open `public/desabonnement.html` directly in a browser (file:// URL) with `?search=Test&email=a@example.com&token=abc` appended. Confirm:
- The intro text shows `Se desinscrire de la recherche "Test" pour l'adresse a@example.com ?`
- The button is enabled
- Opening the file without query params disables the button and shows "Lien invalide"

- [ ] **Step 3: Commit**

```bash
git add public/desabonnement.html
git commit -m "feat: add public unsubscribe page"
```

---

### Task 7: Document the feature in the README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed elsewhere.

- [ ] **Step 1: Add `UNSUBSCRIBE_SECRET` to the secrets list**

In the "## Mise en place" section, step 3 (`README.md`, the bullet list starting with `GMAIL_ADDRESS`), add a new bullet after `ALERT_EMAIL`:

```markdown
   - `UNSUBSCRIBE_SECRET` : une chaine aleatoire (ex. generee avec
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`), utilisee pour
     signer les liens de desinscription dans les emails d'alerte. Optionnel : sans ce
     secret, les emails sont envoyes normalement, simplement sans lien de
     desinscription.
```

- [ ] **Step 2: Add a "Se désinscrire" subsection**

Insert a new subsection right after the "### Confirmation d'email obligatoire" section and before "## Formulaire public sans compte GitHub (optionnel, via Netlify)":

```markdown
### Se désinscrire d'une recherche

Chaque email d'alerte contient, en pied de message, un lien de désinscription
personnalisé (nom de la recherche, adresse email et jeton de sécurité). En cliquant
dessus, tu retires ton adresse de **cette recherche précise** — les autres recherches
auxquelles tu es éventuellement abonné ne sont pas affectées. Si tu étais la dernière
adresse inscrite sur cette recherche, elle est supprimée entièrement.

Comme pour la confirmation d'email, ce lien ouvre soit une Issue GitHub pré-remplie
(compte GitHub requis), soit une simple page web si le formulaire public Netlify est
configuré (voir plus bas) — le bot choisit automatiquement le bon format selon la
configuration du dépôt, rien à faire de ton côté.

Ce lien n'apparaît dans l'email que si le secret `UNSUBSCRIBE_SECRET` est configuré
(voir étape 3 ci-dessus) ; sans lui, les emails d'alerte fonctionnent comme avant,
simplement sans lien de désinscription.
```

- [ ] **Step 3: Update the Netlify section's intro and file list**

In the "## Formulaire public sans compte GitHub (optionnel, via Netlify)" section, replace:

```markdown
peux déployer les pages `public/index.html` (nouvelle recherche) et `public/confirmer.html` sur
Netlify — elles créent les mêmes Issues GitHub à ta place, via deux Netlify Functions
(`netlify/functions/create-search.js` et `confirm-email.js`). Le backend Python et les
```

with:

```markdown
peux déployer les pages `public/index.html` (nouvelle recherche), `public/confirmer.html`
et `public/desabonnement.html` sur Netlify — elles créent les mêmes Issues GitHub à ta
place, via trois Netlify Functions (`netlify/functions/create-search.js`,
`confirm-email.js` et `unsubscribe.js`). Le backend Python et les
```

- [ ] **Step 4: Add `UNSUBSCRIBE_BASE_URL` to the Netlify deployment steps**

In the same section, replace step 4:

```markdown
4. Ajoute un secret sur le dépôt GitHub (Settings > Secrets and variables > Actions) :
   - `CONFIRMATION_BASE_URL` : l'URL de la page de confirmation sur ton site Netlify,
     ex. `https://ton-site.netlify.app/confirmer.html`

   Sans ce secret, les liens de confirmation continuent de pointer vers GitHub comme
   avant — rien ne casse si tu ne déploies jamais Netlify.
```

with:

```markdown
4. Ajoute ces secrets sur le dépôt GitHub (Settings > Secrets and variables > Actions) :
   - `CONFIRMATION_BASE_URL` : l'URL de la page de confirmation sur ton site Netlify,
     ex. `https://ton-site.netlify.app/confirmer.html`
   - `UNSUBSCRIBE_BASE_URL` (optionnel, nécessite `UNSUBSCRIBE_SECRET` déjà configuré à
     l'étape 3 de la mise en place) : l'URL de la page de désinscription, ex.
     `https://ton-site.netlify.app/desabonnement.html`

   Sans ces secrets, les liens de confirmation et de désinscription continuent de
   pointer vers GitHub comme avant — rien ne casse si tu ne déploies jamais Netlify.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document the unsubscribe link and its secrets"
```

---

### Task 8: Manual end-to-end verification

**Files:** none (manual, no code changes).

**Interfaces:** consumes the fully deployed system from Tasks 1-7 plus the two new GitHub secrets configured by the repo owner.

- [ ] **Step 1: Configure the new secrets**

On GitHub (Settings > Secrets and variables > Actions), add:
- `UNSUBSCRIBE_SECRET`: generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- `UNSUBSCRIBE_BASE_URL` (only if the Netlify facade from Task 6 is deployed): `https://<ton-site>.netlify.app/desabonnement.html`.

If Netlify is used, also redeploy the site (Deploys > Trigger deploy) so `unsubscribe.js` picks up the existing `GITHUB_PAT`/`GITHUB_REPOSITORY` env vars — no new Netlify env vars are needed for this feature, it reuses the ones already configured.

- [ ] **Step 2: Trigger a real alert email**

`searches.json` currently contains a "Rennes" search with `theaissam@gmail.com` as its only recipient (from the earlier end-to-end test of the Netlify public form). Temporarily remove the "Rennes" entry from `seen.json` for the currently-listed ids (or add a search that currently has available housing) so the next run of `check_logement.py` treats at least one listing as new and sends an alert email — then trigger the workflow manually from the Actions tab ("Check CROUS housing" > "Run workflow") instead of waiting for the 5-minute cron.

- [ ] **Step 3: Verify the email and the link**

Open the received alert email and confirm it ends with a line `Pour ne plus recevoir ces alertes : <url>`. If `UNSUBSCRIBE_BASE_URL` is configured, the URL should point at `.../desabonnement.html?search=Rennes&email=...&token=...`; otherwise it should point at a GitHub "new issue" URL with `template=unsubscribe.yml`.

- [ ] **Step 4: Click through and confirm the result**

Click the link. If it's the Netlify page, confirm the intro text names the right search/email, click "Se désinscrire", and confirm the success message. If it's the GitHub Issue path, confirm the three fields are pre-filled and submit the issue.

- [ ] **Step 5: Verify `searches.json`**

Within a minute or two, check that the GitHub Action "Unsubscribe from search alerts" ran, closed the Issue, and that `searches.json` no longer contains `theaissam@gmail.com` under "Rennes" (and, since it was the only recipient, that the "Rennes" entry itself was removed entirely).

- [ ] **Step 6: Report back**

Report the outcome (success, or the exact error message/behavior observed) — no further code changes are expected unless this surfaces a bug.
