# Envoi d'emails via un service SMTP configurable (Brevo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Gmail SMTP sending in `check_logement.py`/`add_search.py` with configurable SMTP (host/port/user/password/from), so the project can send via Brevo's free tier (or any other SMTP provider) instead of the repo owner's personal Gmail account.

**Architecture:** `send_email()` gains `smtp_host`/`smtp_port`/`from_email` parameters alongside the existing `smtp_user`/`smtp_password`; it chooses `SMTP_SSL` (port 465) or `SMTP` + `starttls()` (any other port, e.g. Brevo's 587) based on the port. Both call sites (`check_logement.py main()` and `add_search.py main()`) read 5 new required env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL`) instead of the old `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` pair — a net replacement, no backward-compatibility shim.

**Tech Stack:** Python 3.12 stdlib only (`smtplib`, already used) — no new dependencies.

## Global Constraints

- No new runtime dependencies.
- French for all user-facing strings (README, error messages) — this plan touches no new user-facing strings besides README prose.
- Net replacement of `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` with `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`FROM_EMAIL` — no fallback to the old names, per the spec's explicit decision.
- `FROM_EMAIL` is a separate, required value from `SMTP_USER` (the SMTP login identity and the visible sender address are different concerns with Brevo).
- Every changed function needs its tests updated/passing before being considered done (TDD for new behavior; mechanical fixture updates for unchanged assertions are acceptable without a red step, but must be verified green at the end of each task).

---

### Task 1: `send_email()` + `main()` in `check_logement.py`

**Files:**
- Modify: `check_logement.py:205-214` (`send_email`), `check_logement.py:226-227` (`main`, env var reads), `check_logement.py:265` (`main`, `send_email` call site)
- Test: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `send_email(subject: str, body: str, to_addrs: list[str], smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str, from_email: str) -> None` (was `send_email(subject, body, to_addrs, smtp_user, smtp_password)`). Every other module that calls `send_email` (Task 2's `add_search.py`) must pass the new positional/keyword arguments in this order.

- [ ] **Step 1: Update `_FakeSMTP` and write the failing tests for both connection modes**

In `tests/test_check_logement.py`, replace the existing `_FakeSMTP` class (`tests/test_check_logement.py:234-254`):

```python
class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        self.starttls_called = False
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent = (from_addr, to_addrs, msg)
```

Replace the existing `test_send_email_logs_in_and_sends` test (`tests/test_check_logement.py:257-280`) with two tests:

```python
def test_send_email_uses_ssl_for_port_465(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP_SSL", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com", "b@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=465,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp-relay.brevo.com"
    assert smtp.port == 465
    assert smtp.starttls_called is False
    assert smtp.logged_in == ("brevo-login", "brevo-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "alerts@example.com"
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert "Subject" in msg
    msg_obj = message_from_string(msg)
    assert msg_obj["From"] == "alerts@example.com"
    decoded_body = msg_obj.get_payload(decode=True).decode("utf-8")
    assert "Body text" in decoded_body


def test_send_email_uses_starttls_for_non_ssl_port(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=587,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp-relay.brevo.com"
    assert smtp.port == 587
    assert smtp.starttls_called is True
    assert smtp.logged_in == ("brevo-login", "brevo-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "alerts@example.com"
    assert to_addrs == ["a@example.com"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_check_logement.py -k "test_send_email" -v`
Expected: FAIL with `TypeError: send_email() got an unexpected keyword argument 'smtp_host'`

- [ ] **Step 3: Implement the new `send_email()`**

Replace `check_logement.py:205-214`:

```python
def send_email(
    subject: str,
    body: str,
    to_addrs: list[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_addrs)
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=FETCH_TIMEOUT) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_addrs, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=FETCH_TIMEOUT) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_addrs, msg.as_string())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_check_logement.py -k "test_send_email" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: make send_email's SMTP host/port/sender configurable"
```

- [ ] **Step 6: Update `main()`'s env var reads and call site**

Replace `check_logement.py:226-227`:

```python
    smtp_user = _require_env("GMAIL_ADDRESS")
    smtp_password = _require_env("GMAIL_APP_PASSWORD")
```

with:

```python
    smtp_host = _require_env("SMTP_HOST")
    smtp_port = int(_require_env("SMTP_PORT"))
    smtp_user = _require_env("SMTP_USER")
    smtp_password = _require_env("SMTP_PASSWORD")
    from_email = _require_env("FROM_EMAIL")
```

Replace `check_logement.py:265`:

```python
                    send_email(subject, body, [recipient], smtp_user, smtp_password)
```

with:

```python
                    send_email(
                        subject, body, [recipient],
                        smtp_host, smtp_port, smtp_user, smtp_password, from_email,
                    )
```

- [ ] **Step 7: Update every test that sets the old Gmail env vars**

In `tests/test_check_logement.py`, every occurrence of the exact two-line block:

```python
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
```

(there are 12 occurrences, all byte-identical with 4-space indentation — confirm with
`grep -n -A1 'monkeypatch.setenv("GMAIL_ADDRESS"' tests/test_check_logement.py` before
and after) becomes:

```python
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
```

Use a single `replace_all` edit for this (the two-line block is identical at all 12 call
sites, so a straight find-and-replace is safe and exhaustive — do not hand-edit each one
separately). There is exactly one place with `monkeypatch.delenv("GMAIL_ADDRESS", ...)` /
`monkeypatch.delenv("GMAIL_APP_PASSWORD", ...)` (in
`test_main_missing_env_var_returns_error`) — replace that pair with:

```python
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
```

- [ ] **Step 8: Update every mocked `send_email` signature in this file**

Every occurrence of the exact substring `lambda subject, body, to_addrs, smtp_user, smtp_password` (4 occurrences) becomes `lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email` — use a single `replace_all` edit (the lambda bodies don't reference the SMTP parameters, so widening the parameter list is always safe).

Every occurrence of the exact substring `def fake_send_email(subject, body, to_addrs, smtp_user, smtp_password):` (2 occurrences) becomes `def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email):` — use a single `replace_all` edit.

- [ ] **Step 9: Run the full test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass. Verify with `grep -n "GMAIL_ADDRESS\|GMAIL_APP_PASSWORD" tests/test_check_logement.py check_logement.py` that nothing remains (empty output).

- [ ] **Step 10: Commit**

```bash
git add check_logement.py tests/test_check_logement.py
git commit -m "feat: read SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/FROM_EMAIL in check_logement.py"
```

---

### Task 2: `add_search.py` — same env vars for confirmation emails

**Files:**
- Modify: `add_search.py:257-258` (env var reads), `add_search.py:266-272` (`send_email` call)
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: `check_logement.send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email)` from Task 1.
- Produces: nothing consumed elsewhere in this plan.

- [ ] **Step 1: Update the env var reads and call site**

Replace `add_search.py:257-258`:

```python
        smtp_user = clog._require_env("GMAIL_ADDRESS")
        smtp_password = clog._require_env("GMAIL_APP_PASSWORD")
```

with:

```python
        smtp_host = clog._require_env("SMTP_HOST")
        smtp_port = int(clog._require_env("SMTP_PORT"))
        smtp_user = clog._require_env("SMTP_USER")
        smtp_password = clog._require_env("SMTP_PASSWORD")
        from_email = clog._require_env("FROM_EMAIL")
```

Replace `add_search.py:266-272`:

```python
                clog.send_email(
                    subject=f"Confirme ton adresse pour la recherche {name!r}",
                    body=confirmation_body,
                    to_addrs=[email],
                    smtp_user=smtp_user,
                    smtp_password=smtp_password,
                )
```

with:

```python
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
```

- [ ] **Step 2: Update every test that sets the old Gmail env vars**

In `tests/test_add_search.py`, the exact two-line block:

```python
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
```

occurs 3 times (all byte-identical, 4-space indentation — confirm with
`grep -n -A1 'monkeypatch.setenv("GMAIL_ADDRESS"' tests/test_add_search.py`). Replace all
3 with a single `replace_all` edit, using the same replacement block as Task 1 Step 7:

```python
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
```

There is exactly one `monkeypatch.delenv("GMAIL_ADDRESS", raising=False)` /
`monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)` pair, in
`test_main_requires_gmail_env_when_email_submitted`. Replace that pair with:

```python
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
```

Rename that test function from `test_main_requires_gmail_env_when_email_submitted` to
`test_main_requires_smtp_env_when_email_submitted` (the old name is now inaccurate).

- [ ] **Step 3: Update every mocked `send_email` signature in this file**

Every occurrence of the exact substring `lambda subject, body, to_addrs, smtp_user, smtp_password` (2 occurrences) becomes `lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email` — use a single `replace_all` edit.

The one occurrence of `def fake_send_email(subject, body, to_addrs, smtp_user, smtp_password):` becomes `def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email):`.

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass. Verify with `grep -n "GMAIL_ADDRESS\|GMAIL_APP_PASSWORD" tests/test_add_search.py add_search.py` that nothing remains (empty output). Also verify with `grep -rn "GMAIL_ADDRESS\|GMAIL_APP_PASSWORD" --include="*.py"` across the whole repo that no Python file references the old names anymore.

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: read SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/FROM_EMAIL in add_search.py"
```

---

### Task 3: Wire the new secrets into both GitHub Actions workflows

**Files:**
- Modify: `.github/workflows/check.yml`, `.github/workflows/add-search.yml`

**Interfaces:**
- Consumes: the env var names `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`FROM_EMAIL` from Tasks 1-2.
- Produces: nothing consumed elsewhere in this plan (Task 5 configures the actual GitHub repo secrets these reference).

- [ ] **Step 1: Update `check.yml`**

Replace in `.github/workflows/check.yml`:

```yaml
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
          UNSUBSCRIBE_SECRET: ${{ secrets.UNSUBSCRIBE_SECRET }}
          UNSUBSCRIBE_BASE_URL: ${{ secrets.UNSUBSCRIBE_BASE_URL }}
          GITHUB_REPOSITORY: ${{ github.repository }}
```

with:

```yaml
        env:
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          FROM_EMAIL: ${{ secrets.FROM_EMAIL }}
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
          UNSUBSCRIBE_SECRET: ${{ secrets.UNSUBSCRIBE_SECRET }}
          UNSUBSCRIBE_BASE_URL: ${{ secrets.UNSUBSCRIBE_BASE_URL }}
          GITHUB_REPOSITORY: ${{ github.repository }}
```

- [ ] **Step 2: Update `add-search.yml`**

Replace in `.github/workflows/add-search.yml`:

```yaml
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          CONFIRMATION_BASE_URL: ${{ secrets.CONFIRMATION_BASE_URL }}
```

with:

```yaml
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          FROM_EMAIL: ${{ secrets.FROM_EMAIL }}
          CONFIRMATION_BASE_URL: ${{ secrets.CONFIRMATION_BASE_URL }}
```

- [ ] **Step 3: Validate both YAML files are well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/check.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/add-search.yml', encoding='utf-8'))"`
Expected: no output, exit code 0

- [ ] **Step 4: Run the full test suite to check for regressions**

Run: `python -m pytest -v`
Expected: all tests pass (no Python source changed in this task)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/check.yml .github/workflows/add-search.yml
git commit -m "feat: wire SMTP_* and FROM_EMAIL secrets into GitHub Actions workflows"
```

---

### Task 4: Document Brevo setup in the README

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Replace the Gmail app-password setup step**

Replace `README.md`'s step 2 of "## Mise en place":

```markdown
2. **Créer un mot de passe d'application Google** (nécessite la validation en 2 étapes
   activée sur le compte Gmail utilisé pour envoyer les emails) :
   https://myaccount.google.com/apppasswords — génère un mot de passe pour "Mail",
   copie-le (16 caractères sans espaces).
```

with:

```markdown
2. **Créer un compte Brevo** (gratuit, 300 emails/jour) sur https://www.brevo.com/ pour
   l'envoi des emails — évite de faire transiter tout le trafic (alertes, confirmations)
   par ton compte Gmail personnel :
   - Dans Brevo, va dans **Settings > SMTP & API > SMTP** pour récupérer ton identifiant
     SMTP et générer une clé SMTP (mot de passe).
   - Vérifie une adresse d'expéditeur (**Settings > Senders & IP > Senders**, ajoute et
     valide l'adresse que tu veux voir comme expéditeur des emails) — c'est cette adresse
     qui sera utilisée comme `FROM_EMAIL` ci-dessous.
```

- [ ] **Step 2: Replace the secrets list**

Replace the `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` bullets in step 3 of "## Mise en
place":

```markdown
   - `GMAIL_ADDRESS` : l'adresse Gmail utilisée pour envoyer (ex: theaissam@gmail.com)
   - `GMAIL_APP_PASSWORD` : le mot de passe d'application généré à l'étape 2
```

with:

```markdown
   - `SMTP_HOST` : l'hôte SMTP de Brevo, `smtp-relay.brevo.com`
   - `SMTP_PORT` : `587`
   - `SMTP_USER` : ton identifiant SMTP Brevo (récupéré à l'étape 2)
   - `SMTP_PASSWORD` : ta clé SMTP Brevo (générée à l'étape 2, pas ton mot de passe de
     compte Brevo)
   - `FROM_EMAIL` : l'adresse expéditeur vérifiée dans Brevo à l'étape 2 — distincte de
     `SMTP_USER`, qui sert uniquement à l'authentification
```

- [ ] **Step 3: Update the local-development section**

Replace in "## Développement local":

```markdown
```bash
export GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=... ALERT_EMAIL=...
python check_logement.py
```

En PowerShell (Windows) :

```powershell
$env:GMAIL_ADDRESS = "..."
$env:GMAIL_APP_PASSWORD = "..."
$env:ALERT_EMAIL = "..."
python check_logement.py
```
```

with:

```markdown
```bash
export SMTP_HOST=... SMTP_PORT=587 SMTP_USER=... SMTP_PASSWORD=... FROM_EMAIL=... ALERT_EMAIL=...
python check_logement.py
```

En PowerShell (Windows) :

```powershell
$env:SMTP_HOST = "..."
$env:SMTP_PORT = "587"
$env:SMTP_USER = "..."
$env:SMTP_PASSWORD = "..."
$env:FROM_EMAIL = "..."
$env:ALERT_EMAIL = "..."
python check_logement.py
```
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Brevo SMTP setup, replacing Gmail app-password instructions"
```

---

### Task 5: Manual migration and verification

**Files:** none (manual, no code changes).

**Interfaces:** consumes the fully implemented system from Tasks 1-4 plus real Brevo credentials configured by the repo owner.

- [ ] **Step 1: Create the Brevo account and get credentials**

Sign up at https://www.brevo.com/ (free plan), go to **Settings > SMTP & API > SMTP** to
get the SMTP login and generate an SMTP key, and go to **Settings > Senders & IP >
Senders** to add and verify a sender email address (Brevo sends a verification email to
that address — click the link there).

- [ ] **Step 2: Replace the GitHub repo secrets**

On GitHub (Settings > Secrets and variables > Actions):
- Delete `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`.
- Add `SMTP_HOST` = `smtp-relay.brevo.com`, `SMTP_PORT` = `587`, `SMTP_USER` = (the
  Brevo SMTP login from Step 1), `SMTP_PASSWORD` = (the Brevo SMTP key from Step 1),
  `FROM_EMAIL` = (the verified sender address from Step 1).

Do this in one sitting — once the code from Tasks 1-4 is merged, both workflows require
all 5 new secrets to run at all (`_require_env` fails the whole run otherwise), so there
is no working intermediate state with only some of the old/new secrets present.

- [ ] **Step 3: Verify a real alert email still arrives**

Trigger the "Check CROUS housing" workflow manually (Actions tab > "Check CROUS housing"
> "Run workflow"). If no search currently has new listings, temporarily add a test search
known to have availability (same approach as the unsubscribe-link feature's Task 8 used
Agen — geocode a city, check listing count locally, add a temporary `searches.json`
entry, remove it after verifying) to force a real alert email through Brevo.

- [ ] **Step 4: Verify a real confirmation email still arrives**

Submit a test search with an email address via the public form (`nouvelle-recherche`
page) or a GitHub Issue, and confirm the confirmation email arrives with `From:` set to
the `FROM_EMAIL` address (not a Gmail address).

- [ ] **Step 5: Report back**

Report the outcome (success, or the exact error message/behavior observed) — no further
code changes are expected unless this surfaces a bug. If both emails arrive correctly,
the migration is complete.
