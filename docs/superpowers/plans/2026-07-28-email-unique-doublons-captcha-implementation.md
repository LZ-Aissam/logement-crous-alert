# Email unique, anti-doublon, captcha et sortie des données — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'email obligatoire et unique par recherche, refuser les doublons avec un retour immédiat, ajouter Cloudflare Turnstile, et sortir les données d'abonnés du dépôt GitHub public.

**Architecture :** Les chemins de fichiers Python deviennent relatifs à un `DATA_DIR` configurable, que les workflows pointent vers un second checkout d'un dépôt privé. Chaque recherche stocke désormais un bloc `criteria` normalisé, ce qui permet à la fonction Netlify de détecter un doublon sans reconstruire l'URL CROUS en JavaScript. Trois petits modules JS (`_criteria.js`, `_data-repo.js`, `_turnstile.js`) portent la nouvelle logique, `create-search.js` se contentant de les enchaîner.

**Tech Stack :** Python 3.12 + pytest, Node.js `node:test`, GitHub Actions, Netlify Functions (CommonJS), Cloudflare Turnstile, API GitHub REST v2022-11-28.

**Spec :** `docs/superpowers/specs/2026-07-28-email-unique-doublons-captcha-design.md`

## Global Constraints

- Dépôt de données : `LZ-Aissam/logement-crous-alert-data`, privé, contenant `searches.json` (`[]`), `pending_searches.json` (`{}`), `seen.json` (`{}`).
- `DATA_DIR` vaut `.` par défaut — les tests et l'usage local ne doivent pas régresser.
- Les libellés `FIELD_*` doivent rester identiques octet pour octet entre `add_search.py`, `netlify/functions/create-search.js` et `.github/ISSUE_TEMPLATE/new-search.yml`. Deux tests verrouillent cette égalité (`tests/test_add_search.py:351` et `:368`).
- Ordre des contrôles dans `create-search.js`, non négociable : `honeypot → rate limit → Turnstile → champs requis → doublon`.
- Le jeton Turnstile est à usage unique : le front doit appeler `turnstile.reset()` après tout refus.
- Sur échec de lecture du dépôt de données, la fonction Netlify **laisse passer** (fail-open) en loguant l'erreur.
- Une entrée sans bloc `criteria` ne peut jamais correspondre à un doublon.
- Le code Python et les messages restent sans accents (convention du dépôt) ; le HTML et les messages utilisateur du front sont accentués.
- Commandes de test : `python -m pytest -q` et `npm test`.

## File Structure

**Créés :**
- `search_criteria.py` — construction et comparaison des critères, côté Python.
- `netlify/functions/_criteria.js` — miroir JavaScript strict de `search_criteria.py`.
- `netlify/functions/_data-repo.js` — lecture des fichiers JSON du dépôt privé via l'API GitHub.
- `netlify/functions/_turnstile.js` — vérification du jeton Turnstile.
- `tests/test_search_criteria.py`
- `netlify/functions/__tests__/_criteria.test.js`
- `netlify/functions/__tests__/_data-repo.test.js`
- `netlify/functions/__tests__/_turnstile.test.js`
- `docs/superpowers/plans/2026-07-28-migration-checklist.md` — la checklist d'exploitation.

**Modifiés :**
- `check_logement.py:22-23` (chemins), `:244` et `:258` (suppression du repli)
- `add_search.py:32` (libellé), `:141` (chemin), `:287-304` (validation email), `:320` (bloc criteria), `:394-398` (branche morte)
- `unsubscribe.py:58-68` (commentaire)
- `netlify/functions/create-search.js` (enchaînement complet)
- `public/index.html:182-183` (champ email), `:191` (widget Turnstile), `:362-397` (payload et reset)
- `.github/ISSUE_TEMPLATE/new-search.yml:36-40`
- Les quatre workflows `.github/workflows/*.yml`
- `README.md`

---

### Task 1: Rendre les chemins de données configurables

Aucun changement de comportement : `DATA_DIR` vaut `.` par défaut, donc tout continue de fonctionner comme avant. C'est la fondation des tâches suivantes.

**Files:**
- Modify: `check_logement.py:22-23`
- Modify: `add_search.py:141`
- Test: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: rien.
- Produces: `check_logement.DATA_DIR: Path`, `check_logement.SEARCHES_PATH: Path`, `check_logement.SEEN_PATH: Path`, `add_search.PENDING_SEARCHES_PATH: Path`. Toutes résolues au moment de l'import, depuis `os.environ["DATA_DIR"]`.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/test_check_logement.py` :

```python
def test_data_dir_defaults_to_current_directory(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    assert reloaded.SEARCHES_PATH == Path("searches.json")
    assert reloaded.SEEN_PATH == Path("seen.json")


def test_data_dir_env_var_relocates_data_files(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "data")
    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    assert reloaded.SEARCHES_PATH == Path("data/searches.json")
    assert reloaded.SEEN_PATH == Path("data/seen.json")
    monkeypatch.delenv("DATA_DIR", raising=False)
    importlib.reload(check_logement)
```

Vérifier que `from pathlib import Path` est bien importé en tête de `tests/test_check_logement.py` ; l'ajouter sinon.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_logement.py -k data_dir -v`
Expected: FAIL — `SEARCHES_PATH` vaut `searches.json` même avec `DATA_DIR=data`.

- [ ] **Step 3: Write minimal implementation**

Dans `check_logement.py`, remplacer les lignes 22-23 :

```python
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
SEARCHES_PATH = DATA_DIR / "searches.json"
SEEN_PATH = DATA_DIR / "seen.json"
```

Dans `add_search.py`, remplacer la ligne 141 :

```python
PENDING_SEARCHES_PATH = clog.DATA_DIR / "pending_searches.json"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: PASS, 119 tests + les 2 nouveaux.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py add_search.py tests/test_check_logement.py
git commit -m "feat: rendre les chemins de donnees relatifs a un DATA_DIR configurable"
```

---

### Task 2: Module de critères Python

**Files:**
- Create: `search_criteria.py`
- Test: `tests/test_search_criteria.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `normalize_city(city: str | None) -> str`
  - `build_criteria(*, city, extent, max_price, min_area, occupation_modes, prm) -> dict[str, Any]` — renvoie les clés `extent`, `city`, `maxPrice`, `minArea`, `occupationModes`, `prm`.
  - `criteria_match(a: dict | None, b: dict | None) -> bool`

- [ ] **Step 1: Write the failing test**

Créer `tests/test_search_criteria.py` :

```python
from search_criteria import build_criteria, criteria_match, normalize_city


def test_normalize_city_trims_lowercases_and_collapses_spaces():
    assert normalize_city("  Saint   Denis  ") == "saint denis"
    assert normalize_city(None) == ""


def test_build_criteria_shape():
    criteria = build_criteria(
        city="  Rennes ",
        extent="-1.75_48.16_-1.61_48.05",
        max_price=500,
        min_area=18,
        occupation_modes=["house_sharing", "alone", "alone"],
        prm=True,
    )
    assert criteria == {
        "extent": "-1.75_48.16_-1.61_48.05",
        "city": "rennes",
        "maxPrice": 500,
        "minArea": 18,
        "occupationModes": ["alone", "house_sharing"],
        "prm": True,
    }


def test_build_criteria_defaults_are_null_not_zero():
    criteria = build_criteria(
        city="Brest", extent=None, max_price=None, min_area=None,
        occupation_modes=[], prm=False,
    )
    assert criteria["extent"] == ""
    assert criteria["maxPrice"] is None
    assert criteria["minArea"] is None
    assert criteria["occupationModes"] == []
    assert criteria["prm"] is False


def test_criteria_match_compares_extent_when_both_have_one():
    a = build_criteria(city="Rennes", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="Rennes Villejean", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_falls_back_to_city_when_extent_missing():
    a = build_criteria(city="Brest", extent=None, max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="  brest ", extent=None, max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_rejects_when_a_filter_differs():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=400,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="Brest", extent="1_2_3_4", max_price=500,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is False


def test_criteria_match_ignores_occupation_mode_order():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=None, min_area=None,
                       occupation_modes=["couple", "alone"], prm=False)
    b = build_criteria(city="Brest", extent="1_2_3_4", max_price=None, min_area=None,
                       occupation_modes=["alone", "couple"], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_never_matches_missing_criteria():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, None) is False
    assert criteria_match(None, a) is False
    assert criteria_match(a, {}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_search_criteria.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'search_criteria'`

- [ ] **Step 3: Write minimal implementation**

Créer `search_criteria.py` :

```python
"""Canonical representation of a search's criteria, used for duplicate detection.

Mirrored byte-for-byte in behavior by netlify/functions/_criteria.js -- any change
here must be applied there too.
"""
from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_city(city: str | None) -> str:
    if not city:
        return ""
    return _WHITESPACE_RE.sub(" ", city.strip()).lower()


def build_criteria(
    *,
    city: str | None,
    extent: str | None,
    max_price: int | None,
    min_area: int | None,
    occupation_modes: list[str],
    prm: bool,
) -> dict[str, Any]:
    return {
        "extent": (extent or "").strip(),
        "city": normalize_city(city),
        "maxPrice": max_price,
        "minArea": min_area,
        "occupationModes": sorted(set(occupation_modes)),
        "prm": bool(prm),
    }


def criteria_match(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    # An extent describes the exact search area; two identical extents mean the same
    # zone even when the typed city label differs. Fall back to the city otherwise.
    if a.get("extent") and b.get("extent"):
        if a["extent"] != b["extent"]:
            return False
    elif a.get("city") != b.get("city"):
        return False
    return (
        a.get("maxPrice") == b.get("maxPrice")
        and a.get("minArea") == b.get("minArea")
        and sorted(a.get("occupationModes") or []) == sorted(b.get("occupationModes") or [])
        and bool(a.get("prm")) == bool(b.get("prm"))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_search_criteria.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add search_criteria.py tests/test_search_criteria.py
git commit -m "feat: ajouter le module de criteres de recherche normalises"
```

---

### Task 3: Renommer le libellé FIELD_EMAILS

Le libellé est un contrat partagé entre trois fichiers, verrouillé par deux tests. Il change en un seul commit, sinon les tests de parité cassent.

**Files:**
- Modify: `add_search.py:32`
- Modify: `netlify/functions/create-search.js:12`
- Modify: `.github/ISSUE_TEMPLATE/new-search.yml:36-43`
- Test: `tests/test_add_search.py:351` et `:368` (existants, aucun changement nécessaire)

**Interfaces:**
- Consumes: rien.
- Produces: `FIELD_EMAILS == "Email de notification"` dans les trois fichiers.

- [ ] **Step 1: Run the parity tests to see them pass before the change**

Run: `python -m pytest tests/test_add_search.py -k "label" -v`
Expected: PASS — c'est le point de départ.

- [ ] **Step 2: Change the label in all three files**

`add_search.py:32` :

```python
FIELD_EMAILS = "Email de notification"
```

`netlify/functions/create-search.js:12` :

```js
const FIELD_EMAILS = "Email de notification";
```

`.github/ISSUE_TEMPLATE/new-search.yml`, remplacer le bloc `emails` (lignes 33-43) :

```yaml
  - type: input
    id: emails
    attributes:
      label: Email de notification
      description: >-
        Une seule adresse. Elle recevra un email de confirmation a valider avant
        de recevoir des alertes.
      placeholder: toi@example.com
    validations:
      required: true
```

- [ ] **Step 3: Fix the existing test fixture that hardcodes the old label**

Dans `tests/test_add_search.py:345`, remplacer :

```python
        "### Email(s) de notification - optionnel\n\n_No response_\n"
```

par :

```python
        "### Email de notification\n\n_No response_\n"
```

Puis chercher toute autre occurrence de l'ancien libellé et l'aligner :

```bash
grep -rn "Email(s) de notification" --include=*.py --include=*.js --include=*.yml .
```

Le résultat attendu après correction est vide.

- [ ] **Step 4: Run the full suites**

Run: `python -m pytest -q && npm test`
Expected: PASS des deux côtés. Le test JS `create-search.test.js:80` référence l'ancien libellé dans une regex — le corriger en :

```js
  assert.match(sentBody.body, /### Email de notification\n\na@example\.com\n/);
```

- [ ] **Step 5: Commit**

```bash
git add add_search.py netlify/functions/create-search.js .github/ISSUE_TEMPLATE/new-search.yml tests/test_add_search.py netlify/functions/__tests__/create-search.test.js
git commit -m "refactor: renommer le libelle du champ email en 'Email de notification'"
```

---

### Task 4: Email obligatoire et unique côté Python

**Files:**
- Modify: `add_search.py:287-304` (validation), `:394-398` (branche morte)
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: rien.
- Produces: `add_search.main()` retourne `1` si aucun email n'est fourni ou si plus d'une adresse est fournie. La branche « ajout direct sans confirmation » disparaît : toute recherche passe désormais par `pending_searches.json`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `tests/test_add_search.py`. Réutiliser le style des tests existants du fichier pour construire `ISSUE_BODY`.

```python
def test_missing_email_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    assert mod.main() == 1


def test_more_than_one_email_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Email de notification\n\na@example.com, b@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    assert mod.main() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -k "email_is_rejected" -v`
Expected: FAIL — l'absence d'email est aujourd'hui acceptée, et deux adresses aussi.

- [ ] **Step 3: Write the implementation**

Dans `add_search.py`, remplacer le bloc lignes 297-304 :

```python
    if not emails:
        print("ERROR: l'email de notification est obligatoire")
        return 1

    if len(emails) > 1:
        print(f"ERROR: une seule adresse email par recherche (recu {len(emails)})")
        return 1

    invalid_emails = [e for e in emails if not EMAIL_RE.match(e)]
    if invalid_emails:
        print(f"ERROR: adresse(s) email invalide(s) : {', '.join(invalid_emails)}")
        return 1
```

Puis supprimer la branche morte. Un email étant désormais garanti, le `if emails:` de la
ligne 345 est toujours vrai : le supprimer, désindenter son corps d'un niveau, et
supprimer le `else:` avec ses quatre lignes.

Concrètement, la ligne 345 `    if emails:` disparaît, les lignes 346 à 393 perdent
quatre espaces d'indentation, et ce bloc final disparaît entièrement :

```python
    else:
        searches.append(entry)
        clog.save_searches(searches)
        lines.insert(0, f"OK: recherche {name!r} ajoutee pour {city!r}.")
        lines.append("Destinataire : email par defaut (ALERT_EMAIL)")
```

La fin de `main()` doit alors ressembler à ceci :

```python
        if failed_emails:
            lines.append(
                f"AVERTISSEMENT: echec d'envoi pour : {', '.join(failed_emails)} "
                "(resoumets une nouvelle issue pour ces adresses si besoin)"
            )

    print("\n".join(lines))
    return 0
```

Après cette tâche, `searches` n'est plus jamais écrit par `add_search.py` — seul
`confirm_email.py` y ajoute une entrée, une fois l'adresse confirmée. La variable
reste utilisée en lecture pour le contrôle de doublon de la Task 6.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_add_search.py -q`
Expected: PASS. Des tests existants qui soumettaient sans email vont échouer — ils décrivent un comportement désormais interdit. Les corriger en ajoutant une adresse au corps d'Issue, sauf ceux qui testent explicitement le refus.

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: exiger exactement une adresse email par recherche"
```

---

### Task 5: Supprimer le destinataire de repli ALERT_EMAIL

**Files:**
- Modify: `check_logement.py:244` et `:258`
- Modify: `unsubscribe.py:58-61` (commentaire uniquement)
- Test: `tests/test_check_logement.py`

**Interfaces:**
- Consumes: rien.
- Produces: `check_logement.main()` n'exige plus `ALERT_EMAIL` et ignore, en loguant une erreur, toute recherche dépourvue de destinataire.

- [ ] **Step 1: Write the failing test**

Ajouter à `tests/test_check_logement.py` :

```python
def test_search_without_recipients_is_skipped_with_an_error(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Orpheline", "url": "https://example.test/search"}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text("{}", encoding="utf-8")
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "FROM_EMAIL"):
        monkeypatch.setenv(var, "1" if var == "SMTP_PORT" else "x")
    monkeypatch.delenv("ALERT_EMAIL", raising=False)

    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    monkeypatch.setattr(reloaded, "fetch_html", lambda url: "<html></html>")
    monkeypatch.setattr(reloaded, "parse_search_results", lambda html: {"items": []})

    reloaded.main()

    captured = capsys.readouterr()
    assert "aucun destinataire" in captured.err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_logement.py -k without_recipients -v`
Expected: FAIL — `main()` sort en erreur sur `_require_env("ALERT_EMAIL")` manquant.

- [ ] **Step 3: Write the implementation**

Dans `check_logement.py`, supprimer la ligne 244 :

```python
    default_email = _require_env("ALERT_EMAIL")
```

Remplacer la ligne 258 :

```python
        recipients = search.get("emails") or []
        if not recipients:
            print(
                f"[ERROR] {name}: aucun destinataire, recherche ignoree",
                file=sys.stderr,
            )
            continue
```

Dans `unsubscribe.py`, remplacer le commentaire lignes 59-61 :

```python
        # No explicit "emails" list. Since every search now requires a recipient, such
        # an entry is a data anomaly rather than a supported case. A valid token proves
        # the requester was a recipient, so removing the whole search is the right cleanup.
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. Les tests existants qui posaient `ALERT_EMAIL` doivent être nettoyés — retirer le `monkeypatch.setenv("ALERT_EMAIL", ...)` et donner un `emails` explicite aux recherches de fixture.

- [ ] **Step 5: Commit**

```bash
git add check_logement.py unsubscribe.py tests/test_check_logement.py
git commit -m "feat: supprimer le destinataire de repli ALERT_EMAIL"
```

---

### Task 6: Écrire et contrôler les critères côté Python

**Files:**
- Modify: `add_search.py:276-320`
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: `search_criteria.build_criteria`, `search_criteria.criteria_match` (Task 2).
- Produces: chaque entrée écrite dans `pending_searches.json` porte une clé `criteria`. `add_search.main()` retourne `1` quand l'adresse soumise est déjà abonnée à des critères identiques.

- [ ] **Step 1: Write the failing tests**

```python
def test_entry_carries_a_criteria_block(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nRennes\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n\n"
        "### Prix maximum - optionnel\n\n500\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 0

    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    criteria = pending["Rennes"]["search"]["criteria"]
    assert criteria["extent"] == "-1.75_48.16_-1.61_48.05"
    assert criteria["city"] == "rennes"
    assert criteria["maxPrice"] == 500
    assert criteria["prm"] is False


def test_same_email_and_same_criteria_is_refused(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Deja la",
                    "url": "https://example.test/search",
                    "emails": ["a@example.com"],
                    "criteria": {
                        "extent": "-1.75_48.16_-1.61_48.05",
                        "city": "rennes",
                        "maxPrice": None,
                        "minArea": None,
                        "occupationModes": [],
                        "prm": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 1


def test_same_criteria_but_different_email_is_allowed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Deja la",
                    "url": "https://example.test/search",
                    "emails": ["a@example.com"],
                    "criteria": {
                        "extent": "-1.75_48.16_-1.61_48.05",
                        "city": "rennes",
                        "maxPrice": None,
                        "minArea": None,
                        "occupationModes": [],
                        "prm": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\nb@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 0
```

Ajouter en haut de `tests/test_add_search.py` l'utilitaire partagé, en l'alignant sur les stubs déjà utilisés dans ce fichier :

```python
def _stub_network_and_smtp(monkeypatch):
    """Neutralise le reseau et l'envoi SMTP pour les tests de main()."""
    monkeypatch.setattr(mod.clog, "fetch_html", lambda url: "<html></html>")
    monkeypatch.setattr(mod.clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(mod.clog, "send_email", lambda **kwargs: None)
    for var, value in (
        ("SMTP_HOST", "x"), ("SMTP_PORT", "1"), ("SMTP_USER", "x"),
        ("SMTP_PASSWORD", "x"), ("FROM_EMAIL", "x@example.com"),
    ):
        monkeypatch.setenv(var, value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -k "criteria_block or same_email or different_email" -v`
Expected: FAIL — `criteria` absent de l'entrée, et le doublon est accepté.

- [ ] **Step 3: Write the implementation**

Dans `add_search.py`, ajouter l'import en tête :

```python
from search_criteria import build_criteria, criteria_match
```

Insérer le bloc suivant **juste après** la validation des emails de la Task 4 (celle qui
se termine par le `return 1` du contrôle `invalid_emails`) et **avant** le
`try:` qui appelle `clog.fetch_html(url)` :

```python
    criteria = build_criteria(
        city=city,
        extent=extent_raw if has_valid_extent else None,
        max_price=max_price,
        min_area=min_area,
        occupation_modes=occupation_modes,
        prm=prm,
    )

    submitted = emails[0].strip().lower()
    for existing in searches:
        if not criteria_match(existing.get("criteria"), criteria):
            continue
        if any(e.strip().lower() == submitted for e in existing.get("emails") or []):
            print(
                f"ERROR: {submitted} est deja abonne a une recherche aux memes "
                f"criteres ({existing['name']!r})"
            )
            return 1
    for pending_name, record in pending.items():
        if not criteria_match(record.get("search", {}).get("criteria"), criteria):
            continue
        if any(
            e.strip().lower() == submitted
            for e in (record.get("pending_emails") or {}).values()
        ):
            print(
                f"ERROR: {submitted} a deja une demande en attente sur les memes "
                f"criteres ({pending_name!r})"
            )
            return 1
```

Puis, ligne 320, ajouter `criteria` à l'entrée :

```python
    entry: dict[str, Any] = {"name": name, "url": url, "criteria": criteria}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: stocker les criteres et refuser les doublons cote Python"
```

---

### Task 7: Miroir JavaScript des critères

**Files:**
- Create: `netlify/functions/_criteria.js`
- Test: `netlify/functions/__tests__/_criteria.test.js`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `normalizeCity(city) -> string`
  - `buildCriteria(fields) -> { extent, city, maxPrice, minArea, occupationModes, prm }` où `fields` est le payload brut du formulaire.
  - `criteriaMatch(a, b) -> boolean`
  - `findDuplicate({ searches, pending, email, criteria }) -> string | null` — renvoie le nom de la recherche en doublon, ou `null`.

- [ ] **Step 1: Write the failing test**

Créer `netlify/functions/__tests__/_criteria.test.js` :

```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { buildCriteria, criteriaMatch, findDuplicate, normalizeCity } = require("../_criteria");

test("normalizeCity trims, lowercases and collapses whitespace", () => {
  assert.equal(normalizeCity("  Saint   Denis  "), "saint denis");
  assert.equal(normalizeCity(undefined), "");
});

test("buildCriteria mirrors the Python shape", () => {
  assert.deepEqual(
    buildCriteria({
      city: "  Rennes ",
      extent: "-1.75_48.16_-1.61_48.05",
      maxPrice: "500",
      minArea: "18",
      occupationMode: "house_sharing,alone,alone",
      prm: "true",
    }),
    {
      extent: "-1.75_48.16_-1.61_48.05",
      city: "rennes",
      maxPrice: 500,
      minArea: 18,
      occupationModes: ["alone", "house_sharing"],
      prm: true,
    }
  );
});

test("buildCriteria maps empty optional fields to null, not zero", () => {
  const criteria = buildCriteria({ city: "Brest" });
  assert.equal(criteria.extent, "");
  assert.equal(criteria.maxPrice, null);
  assert.equal(criteria.minArea, null);
  assert.deepEqual(criteria.occupationModes, []);
  assert.equal(criteria.prm, false);
});

test("criteriaMatch prefers extent over city label", () => {
  const a = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const b = buildCriteria({ city: "Rennes Villejean", extent: "1_2_3_4" });
  assert.equal(criteriaMatch(a, b), true);
});

test("criteriaMatch falls back to city when no extent", () => {
  assert.equal(criteriaMatch(buildCriteria({ city: "Brest" }), buildCriteria({ city: " brest " })), true);
});

test("criteriaMatch rejects a differing filter", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4", maxPrice: "400" });
  const b = buildCriteria({ city: "Brest", extent: "1_2_3_4", maxPrice: "500" });
  assert.equal(criteriaMatch(a, b), false);
});

test("criteriaMatch never matches a missing criteria block", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4" });
  assert.equal(criteriaMatch(a, null), false);
  assert.equal(criteriaMatch(a, undefined), false);
});

test("findDuplicate finds an active search with the same email and criteria", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Rennes", emails: ["A@Example.com"], criteria }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "a@example.com", criteria }), "Rennes");
});

test("findDuplicate finds a pending search awaiting confirmation", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const pending = { Rennes: { search: { criteria }, pending_emails: { abc: "a@example.com" } } };
  assert.equal(findDuplicate({ searches: [], pending, email: "a@example.com", criteria }), "Rennes");
});

test("findDuplicate returns null for a different email", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Rennes", emails: ["a@example.com"], criteria }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "b@example.com", criteria }), null);
});

test("findDuplicate ignores entries without a criteria block", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Legacy", emails: ["a@example.com"] }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "a@example.com", criteria }), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test netlify/functions/__tests__/_criteria.test.js`
Expected: FAIL — `Cannot find module '../_criteria'`

- [ ] **Step 3: Write the implementation**

Créer `netlify/functions/_criteria.js` :

```js
"use strict";

// Behavioral mirror of search_criteria.py -- any change here must be applied there too.

function normalizeCity(city) {
  return String(city || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function toNumberOrNull(value) {
  const trimmed = String(value == null ? "" : value).trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

function buildCriteria(fields) {
  const modes = String((fields && fields.occupationMode) || "")
    .split(",")
    .map((mode) => mode.trim())
    .filter(Boolean);
  return {
    extent: String((fields && fields.extent) || "").trim(),
    city: normalizeCity(fields && fields.city),
    maxPrice: toNumberOrNull(fields && fields.maxPrice),
    minArea: toNumberOrNull(fields && fields.minArea),
    occupationModes: Array.from(new Set(modes)).sort(),
    prm: Boolean(fields && fields.prm && String(fields.prm).trim()),
  };
}

function sameModes(a, b) {
  const left = [...(a || [])].sort();
  const right = [...(b || [])].sort();
  return left.length === right.length && left.every((mode, i) => mode === right[i]);
}

function criteriaMatch(a, b) {
  if (!a || !b) return false;
  // An extent describes the exact search area; two identical extents mean the same
  // zone even when the typed city label differs. Fall back to the city otherwise.
  if (a.extent && b.extent) {
    if (a.extent !== b.extent) return false;
  } else if (a.city !== b.city) {
    // Both sides are already normalized by buildCriteria -- same as search_criteria.py
    return false;
  }
  return (
    (a.maxPrice ?? null) === (b.maxPrice ?? null) &&
    (a.minArea ?? null) === (b.minArea ?? null) &&
    sameModes(a.occupationModes, b.occupationModes) &&
    Boolean(a.prm) === Boolean(b.prm)
  );
}

function findDuplicate({ searches, pending, email, criteria }) {
  const wanted = String(email || "").trim().toLowerCase();
  if (!wanted) return null;

  for (const entry of searches || []) {
    if (!criteriaMatch(entry && entry.criteria, criteria)) continue;
    const emails = (entry && entry.emails) || [];
    if (emails.some((e) => String(e).trim().toLowerCase() === wanted)) return entry.name;
  }

  for (const [name, record] of Object.entries(pending || {})) {
    const search = (record && record.search) || {};
    if (!criteriaMatch(search.criteria, criteria)) continue;
    const emails = Object.values((record && record.pending_emails) || {});
    if (emails.some((e) => String(e).trim().toLowerCase() === wanted)) return name;
  }

  return null;
}

module.exports = { normalizeCity, buildCriteria, criteriaMatch, findDuplicate };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test netlify/functions/__tests__/_criteria.test.js`
Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/_criteria.js netlify/functions/__tests__/_criteria.test.js
git commit -m "feat: ajouter le miroir JS des criteres et la detection de doublon"
```

---

### Task 8: Lecture du dépôt de données privé

**Files:**
- Create: `netlify/functions/_data-repo.js`
- Test: `netlify/functions/__tests__/_data-repo.test.js`

**Interfaces:**
- Consumes: rien.
- Produces: `readDataFile(path, fallback) -> Promise<any>` — lit un JSON du dépôt privé. Renvoie `fallback` sur `404`. Lève une `Error` sur toute autre erreur ou si `DATA_REPO_PAT` est absent.

- [ ] **Step 1: Write the failing test**

Créer `netlify/functions/__tests__/_data-repo.test.js` :

```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { readDataFile } = require("../_data-repo");

function withEnv(t, values) {
  const saved = {};
  for (const [key, value] of Object.entries(values)) {
    saved[key] = process.env[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
}

test("reads and parses a JSON file from the data repo", async (t) => {
  withEnv(t, { DATA_REPO_PAT: "tok", DATA_REPO: "o/data" });
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, text: async () => '[{"name":"Rennes"}]' };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const data = await readDataFile("searches.json", []);

  assert.deepEqual(data, [{ name: "Rennes" }]);
  assert.equal(calls[0].url, "https://api.github.com/repos/o/data/contents/searches.json");
  assert.equal(calls[0].options.headers.Authorization, "Bearer tok");
});

test("returns the fallback when the file does not exist yet", async (t) => {
  withEnv(t, { DATA_REPO_PAT: "tok", DATA_REPO: "o/data" });
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 404, text: async () => "Not Found" });
  t.after(() => {
    global.fetch = originalFetch;
  });

  assert.deepEqual(await readDataFile("searches.json", []), []);
});

test("throws on a server error", async (t) => {
  withEnv(t, { DATA_REPO_PAT: "tok", DATA_REPO: "o/data" });
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 500, text: async () => "boom" });
  t.after(() => {
    global.fetch = originalFetch;
  });

  await assert.rejects(() => readDataFile("searches.json", []), /500/);
});

test("throws when the token is not configured", async (t) => {
  withEnv(t, { DATA_REPO_PAT: undefined });
  await assert.rejects(() => readDataFile("searches.json", []), /DATA_REPO_PAT/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test netlify/functions/__tests__/_data-repo.test.js`
Expected: FAIL — `Cannot find module '../_data-repo'`

- [ ] **Step 3: Write the implementation**

Créer `netlify/functions/_data-repo.js` :

```js
"use strict";

const DEFAULT_DATA_REPO = "LZ-Aissam/logement-crous-alert-data";

async function readDataFile(path, fallback) {
  const token = process.env.DATA_REPO_PAT;
  if (!token) {
    throw new Error("DATA_REPO_PAT is not configured");
  }
  const repo = process.env.DATA_REPO || DEFAULT_DATA_REPO;
  const response = await fetch(`https://api.github.com/repos/${repo}/contents/${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      // raw+json returns the file body directly, avoiding a base64 round-trip
      Accept: "application/vnd.github.raw+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (response.status === 404) return fallback;
  if (!response.ok) {
    throw new Error(`GitHub API error ${response.status} reading ${path}`);
  }
  return JSON.parse(await response.text());
}

module.exports = { readDataFile };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test netlify/functions/__tests__/_data-repo.test.js`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/_data-repo.js netlify/functions/__tests__/_data-repo.test.js
git commit -m "feat: lire les fichiers de donnees depuis le depot prive"
```

---

### Task 9: Vérification Turnstile

**Files:**
- Create: `netlify/functions/_turnstile.js`
- Test: `netlify/functions/__tests__/_turnstile.test.js`

**Interfaces:**
- Consumes: rien.
- Produces: `verifyTurnstile(token, remoteip) -> Promise<boolean>`. Renvoie `false` pour un jeton absent, refusé, ou quand l'API Cloudflare répond en erreur. Lève une `Error` si `TURNSTILE_SECRET_KEY` est absent.

- [ ] **Step 1: Write the failing test**

Créer `netlify/functions/__tests__/_turnstile.test.js` :

```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { verifyTurnstile } = require("../_turnstile");

function withSecret(t, value) {
  const saved = process.env.TURNSTILE_SECRET_KEY;
  if (value === undefined) delete process.env.TURNSTILE_SECRET_KEY;
  else process.env.TURNSTILE_SECRET_KEY = value;
  t.after(() => {
    if (saved === undefined) delete process.env.TURNSTILE_SECRET_KEY;
    else process.env.TURNSTILE_SECRET_KEY = saved;
  });
}

test("accepts a token Cloudflare reports as valid", async (t) => {
  withSecret(t, "sec");
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ success: true }) };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  assert.equal(await verifyTurnstile("tok", "203.0.113.1"), true);
  assert.equal(calls[0].url, "https://challenges.cloudflare.com/turnstile/v0/siteverify");
  const sent = calls[0].options.body;
  assert.equal(sent.get("secret"), "sec");
  assert.equal(sent.get("response"), "tok");
  assert.equal(sent.get("remoteip"), "203.0.113.1");
});

test("rejects a token Cloudflare reports as invalid", async (t) => {
  withSecret(t, "sec");
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ success: false, "error-codes": ["invalid-input-response"] }),
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  assert.equal(await verifyTurnstile("tok", "203.0.113.1"), false);
});

test("rejects an empty token without calling Cloudflare", async (t) => {
  withSecret(t, "sec");
  const originalFetch = global.fetch;
  let called = false;
  global.fetch = async () => {
    called = true;
    return { ok: true, json: async () => ({ success: true }) };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  assert.equal(await verifyTurnstile("", "203.0.113.1"), false);
  assert.equal(called, false);
});

test("rejects when the Cloudflare API is unreachable", async (t) => {
  withSecret(t, "sec");
  const originalFetch = global.fetch;
  global.fetch = async () => {
    throw new Error("network down");
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  assert.equal(await verifyTurnstile("tok", "203.0.113.1"), false);
});

test("throws when the secret is not configured", async (t) => {
  withSecret(t, undefined);
  await assert.rejects(() => verifyTurnstile("tok", "203.0.113.1"), /TURNSTILE_SECRET_KEY/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test netlify/functions/__tests__/_turnstile.test.js`
Expected: FAIL — `Cannot find module '../_turnstile'`

- [ ] **Step 3: Write the implementation**

Créer `netlify/functions/_turnstile.js` :

```js
"use strict";

const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

async function verifyTurnstile(token, remoteip) {
  const secret = process.env.TURNSTILE_SECRET_KEY;
  if (!secret) {
    throw new Error("TURNSTILE_SECRET_KEY is not configured");
  }
  if (!token) return false;

  const body = new URLSearchParams({ secret, response: token });
  if (remoteip && remoteip !== "unknown") {
    body.set("remoteip", remoteip);
  }

  try {
    const response = await fetch(VERIFY_URL, { method: "POST", body });
    if (!response.ok) return false;
    const data = await response.json();
    return Boolean(data && data.success);
  } catch (err) {
    // A captcha we cannot verify is a captcha we must not trust.
    console.error("turnstile: verification call failed", err);
    return false;
  }
}

module.exports = { verifyTurnstile };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test netlify/functions/__tests__/_turnstile.test.js`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/_turnstile.js netlify/functions/__tests__/_turnstile.test.js
git commit -m "feat: ajouter la verification du jeton Cloudflare Turnstile"
```

---

### Task 10: Câbler la fonction create-search

**Files:**
- Modify: `netlify/functions/create-search.js`
- Test: `netlify/functions/__tests__/create-search.test.js`

**Interfaces:**
- Consumes: `verifyTurnstile` (Task 9), `readDataFile` (Task 8), `buildCriteria` et `findDuplicate` (Task 7).
- Produces: `handler(event)` applique l'ordre `honeypot → rate limit → Turnstile → champs requis → doublon`, et renvoie `409` sur doublon.

- [ ] **Step 1: Write the failing tests**

Ajouter à `netlify/functions/__tests__/create-search.test.js`. Les tests existants n'envoient pas de jeton Turnstile : ajouter en tête du fichier un utilitaire qui pose les variables d'environnement et un `fetch` par défaut, et **ajouter `turnstileToken: "tok"` à tous les `makeEvent` existants**.

```js
function stubEnv(t) {
  const saved = {
    TURNSTILE_SECRET_KEY: process.env.TURNSTILE_SECRET_KEY,
    DATA_REPO_PAT: process.env.DATA_REPO_PAT,
    DATA_REPO: process.env.DATA_REPO,
  };
  process.env.TURNSTILE_SECRET_KEY = "sec";
  process.env.DATA_REPO_PAT = "tok";
  process.env.DATA_REPO = "o/data";
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
}

// Routes each outbound call by URL: Turnstile, the data repo, then GitHub issues.
function stubFetch(t, { turnstileOk = true, searches = [], pending = {}, dataFails = false } = {}) {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    if (String(url).includes("challenges.cloudflare.com")) {
      return { ok: true, json: async () => ({ success: turnstileOk }) };
    }
    if (String(url).includes("/contents/searches.json")) {
      if (dataFails) return { ok: false, status: 500, text: async () => "boom" };
      return { ok: true, status: 200, text: async () => JSON.stringify(searches) };
    }
    if (String(url).includes("/contents/pending_searches.json")) {
      if (dataFails) return { ok: false, status: 500, text: async () => "boom" };
      return { ok: true, status: 200, text: async () => JSON.stringify(pending) };
    }
    return { ok: true, json: async () => ({ html_url: "https://github.com/o/r/issues/1" }) };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });
  return calls;
}

test("a failed Turnstile check returns 400 and never reaches GitHub", async (t) => {
  stubEnv(t);
  const calls = stubFetch(t, { turnstileOk: false });

  const result = await handler(
    makeEvent(
      { name: "Brest", city: "Brest", emails: "a@example.com", turnstileToken: "tok" },
      "203.0.113.40"
    )
  );

  assert.equal(result.statusCode, 400);
  assert.equal(calls.some((c) => String(c.url).includes("api.github.com")), false);
});

test("a honeypot submission never calls Turnstile", async (t) => {
  stubEnv(t);
  const calls = stubFetch(t);

  const result = await handler(
    makeEvent({ name: "Brest", city: "Brest", website: "spam" }, "203.0.113.41")
  );

  assert.equal(result.statusCode, 200);
  assert.equal(calls.length, 0);
});

test("a missing email returns 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent({ name: "Brest", city: "Brest", emails: "", turnstileToken: "tok" }, "203.0.113.42")
  );
  assert.equal(result.statusCode, 400);
});

test("two comma-separated emails return 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent(
      { name: "Brest", city: "Brest", emails: "a@example.com,b@example.com", turnstileToken: "tok" },
      "203.0.113.43"
    )
  );
  assert.equal(result.statusCode, 400);
});

test("a malformed email returns 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent({ name: "Brest", city: "Brest", emails: "pas-un-email", turnstileToken: "tok" }, "203.0.113.44")
  );
  assert.equal(result.statusCode, 400);
});

test("an already-subscribed email with identical criteria returns 409", async (t) => {
  stubEnv(t);
  const { buildCriteria } = require("../_criteria");
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const calls = stubFetch(t, {
    searches: [{ name: "Rennes", emails: ["a@example.com"], criteria }],
  });

  const result = await handler(
    makeEvent(
      {
        name: "Rennes bis", city: "Rennes", extent: "1_2_3_4",
        emails: "a@example.com", turnstileToken: "tok",
      },
      "203.0.113.45"
    )
  );

  assert.equal(result.statusCode, 409);
  assert.equal(calls.some((c) => String(c.url).includes("api.github.com/repos/o/r/issues")), false);
});

test("the same criteria with a different email is accepted", async (t) => {
  stubEnv(t);
  const { buildCriteria } = require("../_criteria");
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  stubFetch(t, { searches: [{ name: "Rennes", emails: ["a@example.com"], criteria }] });

  const result = await handler(
    makeEvent(
      {
        name: "Rennes bis", city: "Rennes", extent: "1_2_3_4",
        emails: "b@example.com", turnstileToken: "tok",
      },
      "203.0.113.46"
    )
  );

  assert.equal(result.statusCode, 200);
});

test("an unreadable data repo lets the submission through (fail-open)", async (t) => {
  stubEnv(t);
  stubFetch(t, { dataFails: true });

  const result = await handler(
    makeEvent(
      { name: "Brest", city: "Brest", emails: "a@example.com", turnstileToken: "tok" },
      "203.0.113.47"
    )
  );

  assert.equal(result.statusCode, 200);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — Turnstile n'est pas vérifié, l'email n'est pas exigé, et aucun `409` n'existe.

- [ ] **Step 3: Write the implementation**

Dans `netlify/functions/create-search.js`, remplacer l'entête d'imports :

```js
const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");
const { verifyTurnstile } = require("./_turnstile");
const { readDataFile } = require("./_data-repo");
const { buildCriteria, findDuplicate } = require("./_criteria");

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
```

Puis remplacer le bloc rate limit existant (lignes 54-59) par celui-ci, qui hisse `ip` en
variable locale et enchaîne sur Turnstile :

```js
  const ip = clientIp(event);

  if (rateLimiter.isRateLimited(ip)) {
    return {
      statusCode: 429,
      body: JSON.stringify({ error: "Trop de tentatives, reessaie dans une heure." }),
    };
  }

  if (!(await verifyTurnstile(fields.turnstileToken, ip))) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Verification anti-robot echouee, recharge la page et reessaie." }),
    };
  }
```

L'ordre est contraignant : le honeypot reste au-dessus (il est gratuit et ne doit
déclencher aucun appel sortant), Turnstile passe avant la lecture du dépôt de données.

Après la validation `name`/`city`, ajouter la validation email :

```js
  const email = (fields.emails || "").trim();
  if (!email) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "L'email de notification est obligatoire." }),
    };
  }
  if (email.includes(",")) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Une seule adresse email par recherche." }),
    };
  }
  if (!EMAIL_RE.test(email)) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Cette adresse email n'est pas valide." }),
    };
  }
```

Après les validations `maxPrice` / `minArea`, ajouter le contrôle de doublon :

```js
  try {
    const [searches, pending] = await Promise.all([
      readDataFile("searches.json", []),
      readDataFile("pending_searches.json", {}),
    ]);
    const duplicate = findDuplicate({
      searches,
      pending,
      email,
      criteria: buildCriteria(fields),
    });
    if (duplicate) {
      return {
        statusCode: 409,
        body: JSON.stringify({ error: "Tu es deja abonne a cette recherche avec cette adresse." }),
      };
    }
  } catch (err) {
    // Fail open: a data-repo outage must not block every new subscription.
    // add_search.py re-runs this check and has the final say.
    console.error("create-search: duplicate check skipped", err);
  }
```

- [ ] **Step 4: Run the full JS suite**

Run: `npm test`
Expected: PASS. Les tests préexistants qui n'envoient pas `turnstileToken` échoueront tant qu'ils n'auront pas été mis à jour comme indiqué au Step 1.

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/create-search.js netlify/functions/__tests__/create-search.test.js
git commit -m "feat: exiger Turnstile et un email unique, refuser les doublons en 409"
```

---

### Task 11: Formulaire public

Pas de test automatisé : le script est inline dans `index.html` et n'est pas couvert par le harnais. La vérification est manuelle et explicite.

**Files:**
- Modify: `public/index.html:181-184` (champ email), `:191` (widget), `:362-397` (payload et reset)

**Interfaces:**
- Consumes: le contrat de `create-search` (Task 10) — le payload gagne `turnstileToken`.
- Produces: rien pour les tâches suivantes.

- [ ] **Step 1: Make the email field required**

Remplacer les lignes 181-184 :

```html
            <div class="mb-4">
              <label for="emails" class="form-label fw-semibold">Email de notification</label>
              <input id="emails" name="emails" type="email" required
                     placeholder="toi@example.com" class="form-control form-control-lg">
              <div class="form-text">Tu recevras un email de confirmation a valider avant les alertes.</div>
            </div>
```

- [ ] **Step 2: Add the Turnstile widget and script**

Juste avant le bouton d'envoi (ligne 191), insérer :

```html
            <div class="cf-turnstile mb-3" data-sitekey="1x00000000000000000000AA"></div>
```

`1x00000000000000000000AA` est la clé de test Cloudflare, qui réussit toujours. Elle est remplacée par la vraie site key à l'étape 3 de la checklist de migration.

Dans le `<head>`, après la balise `<link rel="icon">` (ligne 8), ajouter :

```html
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
```

- [ ] **Step 3: Send the token and reset the widget after any refusal**

Dans le handler de soumission, ajouter le jeton au payload après `website` (ligne 367) :

```js
      turnstileToken: (form["cf-turnstile-response"] || {}).value || "",
```

Puis, dans la branche `if (!response.ok)` et dans le `catch`, ajouter la réinitialisation avant le `return` :

```js
        if (window.turnstile) window.turnstile.reset();
```

Le jeton Turnstile est a usage unique : sans ce reset, la deuxieme tentative de l'utilisateur echoue systematiquement.

- [ ] **Step 4: Verify by hand**

```bash
python -m http.server 8765 --directory public
```

Ouvrir `http://localhost:8765/index.html` et vérifier :
- le widget Turnstile s'affiche au-dessus du bouton ;
- soumettre avec le champ email vide déclenche la validation navigateur ;
- soumettre avec `pas-un-email` déclenche la validation navigateur ;
- la console ne montre aucune erreur JS.

Le bouton d'envoi ne peut pas aboutir en local : il appelle une fonction Netlify qui n'existe qu'une fois déployée.

Vérifier aussi la syntaxe du script inline. La substitution de processus n'étant pas
disponible partout, passer par un fichier temporaire :

```bash
python -c "import re; h=open('public/index.html',encoding='utf-8').read(); open('inline_check.js','w',encoding='utf-8').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))"
node --check inline_check.js && echo "SYNTAXE JS OK"
rm inline_check.js
```

Attention : cette extraction ne capture que les `<script>` sans attribut. La balise
Turnstile ajoutée au Step 2 porte un `src`, elle est donc ignorée — c'est voulu.

- [ ] **Step 5: Commit**

```bash
git add public/index.html
git commit -m "feat: email obligatoire et widget Turnstile sur le formulaire public"
```

---

### Task 12: Brancher les workflows sur le dépôt de données

**Files:**
- Modify: `.github/workflows/check.yml`, `add-search.yml`, `confirm-email.yml`, `unsubscribe.yml`

**Interfaces:**
- Consumes: `DATA_DIR` (Task 1).
- Produces: rien pour les tâches suivantes.

- [ ] **Step 1: Add the data checkout to all four workflows**

Dans chacun des quatre fichiers, juste après le `- uses: actions/checkout@v4` existant (ligne 20), insérer :

```yaml
      - uses: actions/checkout@v4
        with:
          repository: LZ-Aissam/logement-crous-alert-data
          token: ${{ secrets.DATA_REPO_PAT }}
          path: data
```

- [ ] **Step 2: Point the Python step at the data directory**

Ajouter `DATA_DIR: data` au bloc `env:` de l'étape qui lance Python, dans les quatre workflows.

Dans `check.yml`, retirer aussi la ligne 37 :

```yaml
          ALERT_EMAIL: ${{ secrets.ALERT_EMAIL }}
```

- [ ] **Step 3: Move the commit steps into the data checkout**

Dans `check.yml`, l'étape « Commit updated seen.json » devient :

```yaml
      - name: Commit updated seen.json
        if: always()
        working-directory: data
        run: |
          git config user.name "logement-alert-bot"
          git config user.email "actions@users.noreply.github.com"
          git add seen.json
          if git diff --staged --quiet; then
            echo "seen.json unchanged, nothing to commit"
          else
            git commit -m "chore: update seen listings"
            git pull --rebase --autostash
            git push
          fi
```

Appliquer le même `working-directory: data` aux étapes de commit de `add-search.yml` (ligne 55), `confirm-email.yml` (ligne 54) et `unsubscribe.yml` (ligne 55). Ne rien changer d'autre dans ces étapes.

- [ ] **Step 4: Validate the YAML**

```bash
python -c "import yaml,glob; [yaml.safe_load(open(f,encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')]; print('YAML OK')"
```

Expected: `YAML OK`

Vérifier ensuite qu'aucun workflow ne référence encore `ALERT_EMAIL` :

```bash
grep -rn "ALERT_EMAIL" .github/ || echo "aucune reference restante"
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/
git commit -m "chore: lire et ecrire les donnees dans le depot prive dedie"
```

---

### Task 13: Documentation et checklist de migration

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/plans/2026-07-28-migration-checklist.md`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: rien.

- [ ] **Step 1: Update the README**

Dans la section du formulaire Issue, remplacer la puce « Email(s) de notification » par :

```markdown
   - **Email de notification** (obligatoire) : une seule adresse. Elle recevra un
     email de confirmation a valider avant de recevoir des alertes.
```

Ajouter, après le paragraphe qui décrit l'autocomplétion :

```markdown
Le formulaire est protege par Cloudflare Turnstile et refuse une inscription en
double : la meme adresse ne peut pas s'abonner deux fois a une recherche aux
criteres identiques.

Les donnees d'abonnes (`searches.json`, `pending_searches.json`, `seen.json`) ne
vivent pas dans ce depot public mais dans un depot prive dedie, pour que les
adresses email des inscrits ne soient pas publiees. Les workflows y accedent via le
secret `DATA_REPO_PAT`.
```

- [ ] **Step 2: Write the migration checklist**

Créer `docs/superpowers/plans/2026-07-28-migration-checklist.md` :

```markdown
# Checklist de migration

Etapes d'exploitation, a faire dans l'ordre. Le code doit etre deploye avant
l'etape 5, sinon le robot tourne a vide.

- [ ] 1. Creer le depot prive `LZ-Aissam/logement-crous-alert-data` avec trois
      fichiers : `searches.json` contenant `[]`, `pending_searches.json` et
      `seen.json` contenant `{}`.
- [ ] 2. Creer un PAT fine-grained limite a ce seul depot, permission
      Contents read/write. Le poser en secret `DATA_REPO_PAT` sur le depot public
      (Settings > Secrets > Actions) **et** en variable d'environnement Netlify.
- [ ] 3. Creer le widget Turnstile sur dash.cloudflare.com pour le domaine du site.
      Poser la secret key en variable d'environnement Netlify
      `TURNSTILE_SECRET_KEY`, et remplacer la cle de test
      `1x00000000000000000000AA` dans `public/index.html` par la vraie site key.
- [ ] 4. Deployer (merge sur master + deploiement Netlify).
- [ ] 5. Supprimer `searches.json`, `pending_searches.json` et `seen.json` du depot
      public. Pour purger aussi l'historique : `git filter-repo --invert-paths
      --path searches.json --path pending_searches.json --path seen.json` puis
      force-push. Rappel : cela ne depublie pas retroactivement les adresses deja
      exposees.
- [ ] 6. Supprimer le secret `ALERT_EMAIL` du depot public.
- [ ] 7. Verifier de bout en bout : soumettre une recherche de test via le
      formulaire, confirmer l'email, verifier que l'entree apparait dans le depot
      prive avec son bloc `criteria`, resoumettre la meme chose et verifier le
      refus en 409, puis supprimer l'entree de test.

Les recherches `Brest` et `Rennes` cessent d'etre surveillees a l'etape 5. La
personne abonnee a `Brest` cesse de recevoir ses alertes.
```

- [ ] **Step 3: Run every suite one last time**

Run: `python -m pytest -q && npm test`
Expected: PASS des deux côtés.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-07-28-migration-checklist.md
git commit -m "docs: documenter l'email unique, le captcha et la migration des donnees"
```

---

## Notes pour l'exécutant

- **Ne pas pousser sur GitHub.** Ce dépôt attend une validation explicite de son propriétaire avant tout push. Tout reste en commits locaux sur la branche courante.
- Les tâches 1 à 6 sont Python, 7 à 10 JavaScript, 11 le front, 12 les workflows, 13 la documentation. Chaque tâche se termine sur une suite verte.
- Si un test préexistant casse après une tâche, c'est presque toujours parce qu'il décrit l'ancien contrat (email optionnel, `ALERT_EMAIL`, ancien libellé). Le corriger fait partie de la tâche.
- Les tests des tâches 1 et 5 utilisent `importlib.reload(check_logement)`, parce que les
  chemins sont résolus à l'import. Un module rechargé casse les références que d'autres
  modules gardent sur l'ancien objet — d'où le `importlib.reload` de restauration en fin de
  test. Si des tests voisins deviennent instables, c'est la première piste à regarder.
- La lecture du dépôt de données par la fonction Netlify passe par l'API GitHub et non par
  un clone : c'est le seul composant qui ne peut pas utiliser `actions/checkout`.
