# Page Contact, Mentions légales et case de consentement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Contact page, a Mentions légales page, a shared footer linking to both across the whole public site, and a required consent checkbox on the search-creation form.

**Architecture:** Two new static HTML pages under `public/`, following the existing `confirmer.html`/`desabonnement.html` template (Bootstrap 5 nav + centered card, no JS needed). A shared footer snippet is duplicated across all 5 public pages (this codebase has no templating/build step — `public/` is served as-is by Netlify). The consent checkbox reuses the existing HTML5 `required` + `form.checkValidity()`/`reportValidity()` client-side validation already wired in `index.html`'s submit handler — no backend or payload changes.

**Tech Stack:** Static HTML, Bootstrap 5.3.3 + Bootstrap Icons (CDN, already in use), `public/styles.css`. No new dependencies.

## Global Constraints

- No backend changes: `netlify/functions/create-search.js` and its payload are untouched — the consent checkbox is front-end-only validation (per spec, confirmed with user).
- Contact email is `logementcrousalert@gmail.com` (the `FROM_EMAIL` address, per user).
- Mentions légales stay pseudonymous: no real name or postal address, per user's explicit choice.
- Match existing page conventions exactly: `<!doctype html>` + `lang="fr"`, same `<head>` block (favicon, Google Fonts preconnect, Bootstrap + Bootstrap Icons CDN links, `styles.css`), same nav bar markup, same `stamp`/`stamp-teal` badge pattern used in `confirmer.html`/`desabonnement.html`.
- No new automated tests: these are static pages with no logic, and the checkbox reuses an already-untested-but-existing validation pattern (per spec). Verification is manual, via `python -m http.server 8765 --directory public`.

---

### Task 1: Create the Contact page

**Files:**
- Create: `public/contact.html`

**Interfaces:**
- Consumes: `public/styles.css` (existing `.stamp`, `.stamp-teal` classes), `public/favicon.svg`.
- Produces: a page reachable at `contact.html`, linked from the shared footer added in Task 3.

- [ ] **Step 1: Write `public/contact.html`**

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact - Alerte logement CROUS</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body style="background: var(--color-grey); min-height: 100vh;">

<nav class="navbar navbar-expand py-3">
  <div class="container">
    <a class="navbar-brand fw-bold d-flex align-items-center gap-2 mb-0" href="index.html">
      <i class="bi bi-house-heart-fill"></i>
      Alerte Logement CROUS
    </a>
  </div>
</nav>

<main class="container py-5">
  <div class="row justify-content-center">
    <div class="col-lg-6">
      <div class="card border-0 shadow-lg p-4 p-md-5 reveal is-visible">
        <span class="stamp stamp-teal mb-3">Contact</span>
        <h1 class="h3 fw-bold mt-3 mb-2">Nous contacter</h1>
        <p class="text-secondary mb-4">Une question, un bug, une remarque sur le service ? Écris-nous, on te répond
        par email.</p>
        <a href="mailto:logementcrousalert@gmail.com" class="btn btn-primary btn-lg w-100 rounded-pill">
          <i class="bi bi-envelope-fill me-1"></i> logementcrousalert@gmail.com
        </a>
      </div>
    </div>
  </div>
</main>

<footer class="py-4 text-center text-secondary small">
  <div class="container">
    Alerte Logement CROUS, projet indépendant non affilié au CROUS.
    <div class="mt-1">
      <a href="contact.html" class="text-secondary">Contact</a>
      <span class="mx-2">·</span>
      <a href="mentions-legales.html" class="text-secondary">Mentions légales</a>
    </div>
  </div>
</footer>
</body>
</html>
```

- [ ] **Step 2: Manually verify**

Run: `python -m http.server 8765 --directory public` from the repo root, then open
`http://localhost:8765/contact.html` in a browser.

Expected: page renders with the same nav/card style as `confirmer.html`, the mailto
button shows `logementcrousalert@gmail.com`, clicking it opens the system's mail client
(or shows a `mailto:` prompt — browser-dependent, both are correct), and the footer link
"Contact" is a no-op self-link (fine, Task 3 wires the rest).

- [ ] **Step 3: Commit**

```bash
git add public/contact.html
git commit -m "feat: ajouter la page contact"
```

---

### Task 2: Create the Mentions légales page

**Files:**
- Create: `public/mentions-legales.html`

**Interfaces:**
- Consumes: `public/styles.css`, `public/favicon.svg`.
- Produces: a page reachable at `mentions-legales.html`, linked from the shared footer
  (Task 3) and from the consent checkbox label (Task 4).

- [ ] **Step 1: Write `public/mentions-legales.html`**

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mentions légales - Alerte logement CROUS</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body style="background: var(--color-grey); min-height: 100vh;">

<nav class="navbar navbar-expand py-3">
  <div class="container">
    <a class="navbar-brand fw-bold d-flex align-items-center gap-2 mb-0" href="index.html">
      <i class="bi bi-house-heart-fill"></i>
      Alerte Logement CROUS
    </a>
  </div>
</nav>

<main class="container py-5">
  <div class="row justify-content-center">
    <div class="col-lg-8">
      <div class="card border-0 shadow-lg p-4 p-md-5 reveal is-visible">
        <span class="stamp stamp-teal mb-3">Informations légales</span>
        <h1 class="h3 fw-bold mt-3 mb-4">Mentions légales</h1>

        <h2 class="h6 fw-bold text-uppercase text-secondary mt-4">Éditeur</h2>
        <p>Alerte Logement CROUS est un projet indépendant et non commercial, non affilié au
        CROUS. Contact : <a href="mailto:logementcrousalert@gmail.com">logementcrousalert@gmail.com</a>.
        Le code source est public sur GitHub :
        <a href="https://github.com/LZ-Aissam/logement-crous-alert" target="_blank" rel="noopener">LZ-Aissam/logement-crous-alert</a>.</p>

        <h2 class="h6 fw-bold text-uppercase text-secondary mt-4">Hébergement</h2>
        <p>Le site et les fonctions serveur sont hébergés par Netlify, Inc. Les vérifications
        automatisées (surveillance des logements) sont exécutées par GitHub, Inc. via GitHub
        Actions.</p>

        <h2 class="h6 fw-bold text-uppercase text-secondary mt-4">Données personnelles</h2>
        <p>La seule donnée collectée est l'adresse email fournie volontairement lors de
        l'inscription. Un email de confirmation doit être validé avant l'envoi de toute alerte
        (double opt-in). Chaque email d'alerte contient un lien de désinscription en un clic.
        Cette adresse n'est jamais revendue ni partagée avec des tiers.</p>

        <h2 class="h6 fw-bold text-uppercase text-secondary mt-4">Cookies et traceurs</h2>
        <p>Ce site ne dépose aucun cookie de mesure d'audience. Cloudflare Turnstile
        (protection anti-robot) et Google Fonts sont chargés depuis des services tiers lors de
        la visite.</p>
      </div>
    </div>
  </div>
</main>

<footer class="py-4 text-center text-secondary small">
  <div class="container">
    Alerte Logement CROUS, projet indépendant non affilié au CROUS.
    <div class="mt-1">
      <a href="contact.html" class="text-secondary">Contact</a>
      <span class="mx-2">·</span>
      <a href="mentions-legales.html" class="text-secondary">Mentions légales</a>
    </div>
  </div>
</footer>
</body>
</html>
```

- [ ] **Step 2: Manually verify**

Run: `python -m http.server 8765 --directory public` (if not already running), then open
`http://localhost:8765/mentions-legales.html`.

Expected: page renders with all 4 sections (Éditeur, Hébergement, Données personnelles,
Cookies et traceurs), the GitHub link opens the repo in a new tab, the mailto link works.

- [ ] **Step 3: Commit**

```bash
git add public/mentions-legales.html
git commit -m "feat: ajouter la page mentions legales"
```

---

### Task 3: Add the shared footer to every public page

**Files:**
- Modify: `public/index.html` (replace existing footer, around line 206-208)
- Modify: `public/confirmer.html` (add footer before `</body>`, around line 87)
- Modify: `public/desabonnement.html` (add footer before `</body>`, around line 92)
- Modify: `public/contact.html` (already has the target footer from Task 1 — no change needed here, just verify)
- Modify: `public/mentions-legales.html` (already has the target footer from Task 2 — no change needed here, just verify)

**Interfaces:**
- Consumes: `contact.html`, `mentions-legales.html` (created in Tasks 1-2).
- Produces: consistent footer navigation across all 5 pages.

- [ ] **Step 1: Update the footer in `public/index.html`**

Find:

```html
<footer class="py-4 text-center text-secondary small">
  <div class="container">Alerte Logement CROUS, projet indépendant non affilié au CROUS.</div>
</footer>
```

Replace with:

```html
<footer class="py-4 text-center text-secondary small">
  <div class="container">
    Alerte Logement CROUS, projet indépendant non affilié au CROUS.
    <div class="mt-1">
      <a href="contact.html" class="text-secondary">Contact</a>
      <span class="mx-2">·</span>
      <a href="mentions-legales.html" class="text-secondary">Mentions légales</a>
    </div>
  </div>
</footer>
```

- [ ] **Step 2: Add the same footer to `public/confirmer.html`**

Find the closing tags at the end of the file:

```html
</script>
</body>
</html>
```

Replace with (footer inserted before the closing `<script>`'s preceding structure —
concretely, insert the `<footer>` block immediately before the final `<script>` tag,
right after `</main>`):

```html
</main>

<footer class="py-4 text-center text-secondary small">
  <div class="container">
    Alerte Logement CROUS, projet indépendant non affilié au CROUS.
    <div class="mt-1">
      <a href="contact.html" class="text-secondary">Contact</a>
      <span class="mx-2">·</span>
      <a href="mentions-legales.html" class="text-secondary">Mentions légales</a>
    </div>
  </div>
</footer>

<script>
```

(i.e. find the literal line `</main>` in `confirmer.html` and insert the `<footer>...</footer>`
block directly after it, before the existing `<script>` block.)

- [ ] **Step 3: Add the same footer to `public/desabonnement.html`**

Same edit as Step 2: find the literal line `</main>` in `desabonnement.html` and insert the
identical `<footer>...</footer>` block directly after it, before the existing `<script>` block.

- [ ] **Step 4: Manually verify**

With the local server still running (`python -m http.server 8765 --directory public`), open
each of the 5 pages (`index.html`, `confirmer.html?code=x`, `desabonnement.html?search=a&email=b&token=c`,
`contact.html`, `mentions-legales.html`) and confirm the footer with both links appears at
the bottom of every one, and that clicking "Contact" / "Mentions légales" navigates correctly
from every page.

- [ ] **Step 5: Commit**

```bash
git add public/index.html public/confirmer.html public/desabonnement.html
git commit -m "feat: ajouter un pied de page commun avec liens contact et mentions legales"
```

---

### Task 4: Add the required consent checkbox to the search form

**Files:**
- Modify: `public/index.html` (form in the `#formulaire` section, around lines 189-195)

**Interfaces:**
- Consumes: the existing `form.checkValidity()` / `form.reportValidity()` client-side
  validation already present in the `submit` handler (`public/index.html`, current lines
  ~364-369) — no changes needed there, `required` on a new checkbox is automatically
  included by `checkValidity()`.
- Produces: nothing consumed by later tasks — this is the last task in the plan.

- [ ] **Step 1: Add the checkbox markup**

Find, in `public/index.html`:

```html
            <div class="honeypot" aria-hidden="true">
              <label for="website">Laisse ce champ vide</label>
              <input id="website" name="website" tabindex="-1" autocomplete="off">
            </div>

            <!-- CLE DE TEST -- remplacer par la vraie site key Turnstile avant deploiement (voir la checklist de migration, etape 3) -->
            <div class="cf-turnstile mb-3" data-sitekey="1x00000000000000000000AA"></div>
```

Replace with:

```html
            <div class="honeypot" aria-hidden="true">
              <label for="website">Laisse ce champ vide</label>
              <input id="website" name="website" tabindex="-1" autocomplete="off">
            </div>

            <div class="mb-3">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="consent" name="consent" required>
                <label class="form-check-label" for="consent">
                  J'accepte de recevoir les alertes logement par email à l'adresse indiquée
                  ci-dessus, conformément aux
                  <a href="mentions-legales.html" target="_blank" rel="noopener">mentions légales</a>.
                </label>
              </div>
            </div>

            <!-- CLE DE TEST -- remplacer par la vraie site key Turnstile avant deploiement (voir la checklist de migration, etape 3) -->
            <div class="cf-turnstile mb-3" data-sitekey="1x00000000000000000000AA"></div>
```

Do not add `consent` to the `payload` object built later in the `submit` handler — the spec
requires this to stay a client-side-only gate, no backend change.

- [ ] **Step 2: Manually verify**

With the local server running, open `http://localhost:8765/index.html`, scroll to the form,
fill every required field except leave "J'accepte de recevoir..." unchecked, and click
"Créer la recherche".

Expected: the browser blocks submission and shows the native HTML5 validation bubble on the
checkbox (same behavior already relied on for the other `required` fields — no custom JS
needed). Checking the box and re-submitting should proceed past client-side validation (it
will then attempt the real network call to `/.netlify/functions/create-search`, which won't
succeed against the static file server — that failure is expected and out of scope here; the
point of this check is only that the checkbox no longer blocks submission once checked).

Also confirm the "mentions légales" link inside the label opens `mentions-legales.html` in a
new tab.

- [ ] **Step 3: Commit**

```bash
git add public/index.html
git commit -m "feat: ajouter une case de consentement obligatoire au formulaire d'inscription"
```
