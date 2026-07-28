# Refonte "page vitrine" des pages publiques Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (this plan is visual/design work verified by browser screenshots, not automated tests — subagent-driven-development's diff-based task review doesn't fit; execute inline with visual checkpoints instead). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 3 public static pages (`public/index.html`, `public/confirmer.html`, `public/desabonnement.html`) a distinctive visual identity — a "tampon d'urgence" (urgency stamp) concept using the real CROUS Rennes color palette — and turn `index.html` into a proper showcase page (hero, problem, solution, form) with two hand-drawn flat-geometric character illustrations.

**Architecture:** One shared `public/styles.css` (design tokens + base styles + reusable components: stamp badge, cards, buttons, form controls) linked from all 3 pages — no build step, no framework, plain CSS. Two standalone SVG illustration files referenced via `<img>`. `index.html` gets new narrative sections built around the existing, functionally-unchanged form. `confirmer.html`/`desabonnement.html` get the same visual language applied to their existing structure, no content changes.

**Tech Stack:** Plain HTML/CSS/SVG, one external font (Google Fonts, Archivo Black, display headings only). No JavaScript changes — existing fetch/honeypot/result-message logic on all 3 pages stays exactly as-is.

## Global Constraints

- No CSS framework (no Tailwind/Bootstrap/DaisyUI) — hand-written CSS only, per the approved design.
- No new JS dependencies, and no changes to any page's existing `<script>` block (form submission logic).
- Exactly one external network dependency across all 3 pages: the Google Fonts link for Archivo Black. Everything else (illustrations, CSS) is self-hosted in `public/`.
- Colors are the real CROUS Rennes palette from the spec — do not substitute or invent new hex values:
  `--color-red:#e01020` `--color-orange:#ff732c` `--color-greenwater:#34c4b5` `--front-greenwater:#006a6f` `--color-grey:#e8e8e8` `--ink:#16191b` `--paper:#ffffff`.
- `prefers-reduced-motion: reduce` must disable the stamp entrance animation.
- Responsive down to 320px width.
- No automated tests for these files (matches existing project convention for `public/*.html`) — "done" for each visual task means: rendered in a real browser (via the claude-in-chrome tools), screenshotted at ~1280px/~768px/~375px widths, and self-critiqued against the design spec before moving on. If the claude-in-chrome browser extension is unavailable, note that explicitly in your report instead of skipping verification silently.

---

### Task 1: Shared design system — `public/styles.css` + illustrations

**Files:**
- Create: `public/styles.css`
- Create: `public/illustrations/etudiant-stresse.svg`
- Create: `public/illustrations/etudiant-soulage.svg`

**Interfaces:**
- Consumes: nothing.
- Produces: CSS custom properties (`--color-red`, `--color-orange`, `--color-greenwater`, `--front-greenwater`, `--color-grey`, `--ink`, `--paper`, plus `--font-display` and `--font-body`) and reusable component classes (`.stamp`, `.card`, `.btn`, `.btn-primary`, `.field`, `.field label`, `.field input`, `.result`, `.result.success`, `.result.error`, `.result.hidden`, `.honeypot`) that Tasks 2 and 3 depend on by exact class name. Also produces the two illustration files, referenced by Task 2 as `<img src="illustrations/etudiant-stresse.svg" alt="...">` and `<img src="illustrations/etudiant-soulage.svg" alt="...">`.

- [ ] **Step 1: Create `public/styles.css`**

```css
/* Design tokens — real CROUS Rennes brand colors, see docs/superpowers/specs/2026-07-28-showcase-redesign-design.md */
:root {
  --color-red: #e01020;
  --color-orange: #ff732c;
  --color-greenwater: #34c4b5;
  --front-greenwater: #006a6f;
  --color-grey: #e8e8e8;
  --ink: #16191b;
  --paper: #ffffff;
  --font-display: "Archivo Black", system-ui, sans-serif;
  --font-body: system-ui, -apple-system, "Segoe UI", sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--font-body);
  color: var(--ink);
  background: var(--paper);
  line-height: 1.6;
}

h1, h2, h3 {
  font-family: var(--font-display);
  line-height: 1.15;
  margin: 0 0 0.5em;
}

a { color: var(--front-greenwater); }

.container {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 1.25rem;
}

/* Stamp badge — the site's signature element */
.stamp {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 3px solid var(--color-red);
  color: var(--color-red);
  font-family: var(--font-display);
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  transform: rotate(-6deg);
  transform-origin: center;
}

@media (prefers-reduced-motion: no-preference) {
  .stamp {
    animation: stamp-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  }
}

@keyframes stamp-in {
  from { transform: rotate(-6deg) scale(2); opacity: 0; }
  to { transform: rotate(-6deg) scale(1); opacity: 1; }
}

.card {
  border: 1px solid var(--color-grey);
  border-radius: 8px;
  padding: 1.5rem;
  background: var(--paper);
}

.btn {
  font-family: var(--font-body);
  font-weight: 600;
  font-size: 1rem;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.btn:hover { transform: translateY(-2px); }
.btn:focus-visible { outline: 3px solid var(--front-greenwater); outline-offset: 2px; }

.btn-primary {
  background: var(--color-red);
  color: var(--paper);
}

.btn-primary:hover { background: #c00e1c; }

.field { margin-top: 1.25rem; }

.field label {
  display: block;
  font-weight: 600;
  margin-bottom: 0.3rem;
}

.field input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-grey);
  border-radius: 6px;
  font-size: 1rem;
  font-family: var(--font-body);
}

.field input:focus-visible {
  outline: 3px solid var(--front-greenwater);
  outline-offset: 1px;
}

.result {
  margin-top: 1.5rem;
  padding: 1rem;
  border-radius: 8px;
}

.result.success { background: #e3f5f3; color: var(--front-greenwater); }
.result.error { background: #fce8e6; color: var(--color-red); }
.result.hidden { display: none; }

.honeypot { position: absolute; left: -9999px; top: -9999px; }
```

- [ ] **Step 2: Create `public/illustrations/etudiant-stresse.svg`**

A flat-geometric silhouette figure hunched over a glowing phone, with a small urgency clock. Silhouette in `--ink`, phone screen and clock in `--color-red`, soft background wash in `--color-grey`.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" role="img" aria-label="Etudiant stresse penche sur son telephone">
  <circle cx="120" cy="120" r="110" fill="#e8e8e8" />
  <g transform="rotate(6 120 150)">
    <rect x="88" y="120" width="64" height="90" rx="30" fill="#16191b" />
    <circle cx="120" cy="88" r="32" fill="#16191b" />
  </g>
  <rect x="140" y="95" width="34" height="58" rx="6" fill="#ffffff" stroke="#16191b" stroke-width="4" transform="rotate(18 157 124)" />
  <rect x="146" y="102" width="22" height="30" rx="2" fill="#e01020" transform="rotate(18 157 124)" />
  <circle cx="176" cy="70" r="16" fill="none" stroke="#e01020" stroke-width="4" />
  <line x1="176" y1="70" x2="176" y2="60" stroke="#e01020" stroke-width="3" stroke-linecap="round" />
  <line x1="176" y1="70" x2="183" y2="70" stroke="#e01020" stroke-width="3" stroke-linecap="round" />
  <path d="M78 96 Q84 108 78 116 Q72 108 78 96 Z" fill="#34c4b5" />
</svg>
```

- [ ] **Step 3: Create `public/illustrations/etudiant-soulage.svg`**

A flat-geometric silhouette figure standing upright holding a key, with a checkmark stamp. Silhouette in `--ink`, key and checkmark stamp in `--front-greenwater`.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" role="img" aria-label="Etudiant soulage tenant une cle">
  <circle cx="120" cy="120" r="110" fill="#e3f5f3" />
  <rect x="88" y="118" width="64" height="92" rx="30" fill="#16191b" />
  <circle cx="120" cy="86" r="32" fill="#16191b" />
  <g transform="rotate(-18 168 150)">
    <rect x="160" y="145" width="44" height="10" rx="5" fill="#006a6f" />
    <circle cx="160" cy="150" r="12" fill="none" stroke="#006a6f" stroke-width="6" />
    <rect x="196" y="145" width="6" height="14" fill="#006a6f" />
    <rect x="188" y="145" width="6" height="10" fill="#006a6f" />
  </g>
  <g transform="rotate(10 190 70)">
    <circle cx="190" cy="70" r="24" fill="none" stroke="#006a6f" stroke-width="4" />
    <path d="M180 70 l7 7 l14 -14" fill="none" stroke="#006a6f" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
  </g>
</svg>
```

- [ ] **Step 4: Render and visually verify the illustrations**

Open `public/illustrations/etudiant-stresse.svg` and `public/illustrations/etudiant-soulage.svg` directly in a browser (via the claude-in-chrome tools if available — `mcp__claude-in-chrome__navigate` to a `file://` URL, then screenshot; if the extension isn't connected, note this in your report and skip to a manual visual read of the SVG source instead of blocking the task). Check: figures read clearly as a person at a glance, colors match the palette, nothing overlaps illegibly. Adjust coordinates/shapes if the rendered result looks broken or the pose is unclear — this is expected first-pass SVG, treat the screenshot as the real spec and iterate until it reads well, not the code above verbatim.

- [ ] **Step 5: Commit**

```bash
git add public/styles.css public/illustrations/etudiant-stresse.svg public/illustrations/etudiant-soulage.svg
git commit -m "feat: add shared design system and character illustrations for public pages"
```

---

### Task 2: Rebuild `public/index.html` as the showcase page

**Files:**
- Modify: `public/index.html` (full rewrite of the `<head>`/`<body>`, existing `<script>` block content is preserved unchanged — only wrapped in new markup)

**Interfaces:**
- Consumes: `public/styles.css` classes from Task 1 (`.stamp`, `.card`, `.btn-primary`, `.field`, `.result`, `.honeypot`), both illustration files from Task 1.
- Produces: nothing consumed elsewhere in this plan (Task 3 is independent).

- [ ] **Step 1: Read the current file to preserve the exact `<script>` block**

Read `public/index.html` in full. The `<script>` block (the `form.addEventListener("submit", ...)` handler, the `fetch("/.netlify/functions/create-search", ...)` call, and its success/error handling) must be copied verbatim into the new file — do not change any of its logic, only the HTML/CSS around it. The element `id`s it depends on (`search-form`, `name`, `city`, `keywords`, `emails`, `website`, `result`) must be preserved exactly.

- [ ] **Step 2: Write the new `public/index.html`**

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alerte logement CROUS - Ne rate plus jamais un logement</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
<style>
  .hero {
    display: flex;
    align-items: center;
    gap: 2rem;
    padding: 3rem 0 2rem;
  }
  .hero-text { flex: 1 1 320px; }
  .hero-text h1 { font-size: clamp(1.8rem, 4vw, 2.6rem); margin: 0.6em 0 0.5em; }
  .hero-text p { font-size: 1.1rem; }
  .hero img { flex: 0 0 220px; width: 220px; height: 220px; }

  .constat {
    background: var(--color-grey);
    border-left: 4px solid var(--color-red);
    padding: 1.5rem;
    border-radius: 4px;
    margin: 3rem 0;
  }
  .constat .eyebrow { font-family: var(--font-display); font-size: 0.8rem; letter-spacing: 0.08em; color: var(--color-red); }

  .solution { display: flex; align-items: center; gap: 2rem; margin: 3rem 0; }
  .solution img { flex: 0 0 200px; width: 200px; height: 200px; }
  .steps { flex: 1 1 320px; list-style: none; padding: 0; margin: 0; counter-reset: step; }
  .steps li { counter-increment: step; padding-left: 2.75rem; position: relative; margin-bottom: 1.25rem; }
  .steps li::before {
    content: counter(step);
    position: absolute; left: 0; top: 0;
    width: 2rem; height: 2rem;
    background: var(--front-greenwater); color: var(--paper);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-family: var(--font-display); font-size: 0.95rem;
  }

  .trust { font-size: 0.95rem; color: #4a4a4a; margin: 2rem 0; }
  .trust ul { padding-left: 1.25rem; }

  @media (max-width: 700px) {
    .hero, .solution { flex-direction: column; text-align: center; }
  }
</style>
</head>
<body>
<div class="container">

  <section class="hero">
    <div class="hero-text">
      <span class="stamp">Urgent</span>
      <h1>Les logements CROUS disparaissent en quelques minutes.</h1>
      <p>Toi, tu ne peux pas rafraichir la page toute la journee. Ce robot le fait
      pour toi, gratuitement, et t'alerte par email des qu'un logement correspond a
      ta recherche.</p>
      <a href="#formulaire" class="btn btn-primary">Creer mon alerte</a>
    </div>
    <img src="illustrations/etudiant-stresse.svg" alt="Etudiant stresse qui rafraichit son telephone en boucle">
  </section>

  <div class="constat card">
    <div class="eyebrow">Le constat</div>
    <p>Sur trouverunlogement.lescrous.fr, les nouvelles disponibilites partent
    presque instantanement. Le temps de te connecter, de chercher, de comparer,
    c'est deja trop tard. Il faudrait surveiller le site en permanence, ce que
    personne n'a le temps de faire.</p>
  </div>

  <section class="solution">
    <img src="illustrations/etudiant-soulage.svg" alt="Etudiant soulage tenant les cles de son nouveau logement">
    <div>
      <h2>Comment ca marche</h2>
      <ol class="steps">
        <li><strong>Tu crees ta recherche</strong> — ville, mots-cles optionnels, email.</li>
        <li><strong>Le robot verifie toutes les 5 minutes</strong> — gratuitement, 24h/24, sans que tu aies rien a faire.</li>
        <li><strong>Tu recois une alerte email</strong> des qu'un logement correspond — tu n'as plus qu'a foncer le reserver.</li>
      </ol>
    </div>
  </section>

  <div class="trust">
    <strong>Pourquoi lui faire confiance :</strong>
    <ul>
      <li>Gratuit, sans compte GitHub necessaire</li>
      <li>Confirmation email obligatoire avant toute alerte (anti-abus)</li>
      <li>Code source ouvert</li>
    </ul>
  </div>

  <h2 id="formulaire">Creer ma recherche</h2>
  <form id="search-form">
    <div class="field">
      <label for="name">Nom de la recherche</label>
      <input id="name" name="name" required placeholder="Brest">
    </div>

    <div class="field">
      <label for="city">Ville</label>
      <input id="city" name="city" required placeholder="Brest 29200">
    </div>

    <div class="field">
      <label for="keywords">Mots-cles (residence, type de logement...) - optionnel</label>
      <input id="keywords" name="keywords" placeholder="Kergoat, studio">
    </div>

    <div class="field">
      <label for="emails">Email(s) de notification - optionnel (max 3, separes par des virgules)</label>
      <input id="emails" name="emails" placeholder="toi@example.com">
    </div>

    <div class="honeypot" aria-hidden="true">
      <label for="website">Laisse ce champ vide</label>
      <input id="website" name="website" tabindex="-1" autocomplete="off">
    </div>

    <button type="submit" class="btn btn-primary">Creer la recherche</button>
  </form>
  <div id="result" class="result hidden"></div>

</div>

<script>
  const form = document.getElementById("search-form");
  const result = document.getElementById("result");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    result.className = "result hidden";

    const payload = {
      name: form.name.value,
      city: form.city.value,
      keywords: form.keywords.value,
      emails: form.emails.value,
      website: form.website.value,
    };

    try {
      const response = await fetch("/.netlify/functions/create-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();

      if (!response.ok) {
        result.textContent = data.error || "Une erreur est survenue.";
        result.className = "result error";
        return;
      }

      result.textContent = "Recherche soumise.";
      result.className = "result success";
      form.reset();
    } catch (err) {
      result.textContent = "Une erreur est survenue, reessaie dans quelques minutes.";
      result.className = "result error";
    }
  });
</script>
</body>
</html>
```

Note: `result.className` changed from `"hidden"`/`"success"`/`"error"` to
`"result hidden"`/`"result success"`/`"result error"` because Task 1's `styles.css`
scopes the result styling under a `.result` base class (matching the `.result.success`
etc. selectors defined in Task 1 Step 1) — this is the one deliberate change to the
script block's string literals; every other line of the script is byte-identical to
the original file.

- [ ] **Step 3: Verify the form still works end-to-end**

Open `public/index.html` locally in a browser (`file://` path, or via a quick static
server if `fetch` to the Netlify function needs a real origin — check by opening the
file directly first). Confirm: the hero renders with the stamp badge and illustration,
clicking "Creer mon alerte" scrolls to the form, the form fields and honeypot are
present with the original `id`s, and — if you can reach the real deployed
`/.netlify/functions/create-search` endpoint (e.g. by testing against
`https://logement-crous-alert.netlify.app/` after this change ships, not required to
block this task locally) — that submission still produces a success/error message
styled with the new `.result` classes.

- [ ] **Step 4: Screenshot and self-critique at 3 widths**

Using the claude-in-chrome tools (if available — note in your report if not and
proceed with a manual read-through of the CSS instead of blocking): screenshot the
page at ~1280px, ~768px, and ~375px wide. Check against the design spec
(`docs/superpowers/specs/2026-07-28-showcase-redesign-design.md`): hero/solution
sections stack to a single column under 700px, text stays readable, the stamp badge
doesn't clip, illustrations don't overflow their containers, focus outline is visible
when tabbing through the form. Adjust the CSS in Task 1's `styles.css` or this file's
inline `<style>` block if anything looks broken — this is the "critique and refine"
step the design is expected to need before it's done, not optional polish.

- [ ] **Step 5: Commit**

```bash
git add public/index.html
git commit -m "feat: rebuild index.html as a showcase page with hero, problem, and solution sections"
```

---

### Task 3: Restyle `public/confirmer.html` and `public/desabonnement.html`

**Files:**
- Modify: `public/confirmer.html`
- Modify: `public/desabonnement.html`

**Interfaces:**
- Consumes: `public/styles.css` classes from Task 1 (`.stamp`, `.card`, `.btn`, `.field`, `.result`, `.honeypot`).
- Produces: nothing consumed elsewhere in this plan.

- [ ] **Step 1: Read both current files in full**

Read `public/confirmer.html` and `public/desabonnement.html`. Both `<script>` blocks
(the `fetch` calls to `/.netlify/functions/confirm-email` and
`/.netlify/functions/unsubscribe`, their query-param reading, button
enable/disable/result-message logic) must be preserved with identical behavior — same
`id`s (`confirm-button`/`unsubscribe-button`, `result`, `website`), same fetch payload
shape, same success/error text. Only the surrounding HTML/CSS and the `result`
class-name strings change (same `"result hidden"`/`"result success"`/`"result error"`
adjustment as Task 2, to match `styles.css`'s `.result` scoping).

- [ ] **Step 2: Restyle `public/confirmer.html`**

Replace the file's `<head>` and body wrapper with the shared stylesheet/font link (same
`<link>` tags as Task 2 Step 2) and a `.container` + `.card` layout: page title, a
small `.stamp` badge reading "Confirmation" instead of "Urgent", the existing intro
paragraph, the existing honeypot div, the existing button (now `class="btn
btn-primary"`), and the existing `#result` div (now `class="result hidden"`). Do not
add a hero illustration or narrative sections — this stays a short, focused action
page per the spec. Keep the exact same `<script>` logic, only updating the
`result.className` string literals as described in Step 1.

- [ ] **Step 3: Restyle `public/desabonnement.html`**

Same treatment as Step 2: shared stylesheet/font link, `.container` + `.card` layout,
a `.stamp` badge reading "Desinscription", the existing dynamic intro-text logic
unchanged, existing honeypot/button/result elements with the new classes, same
`<script>` logic with only the `result.className` string literals updated.

- [ ] **Step 4: Screenshot and self-critique both pages**

Same verification approach as Task 2 Step 4 — screenshot both pages at ~1280px/~768px/~375px
(use realistic query params for `desabonnement.html`, e.g.
`?search=Test&email=a%40example.com&token=abc`, to see the populated intro-text state,
not just the "lien invalide" empty state). Confirm visual consistency with `index.html`
(same colors/type/card style) and that both remain short, single-purpose pages.

- [ ] **Step 5: Commit**

```bash
git add public/confirmer.html public/desabonnement.html
git commit -m "feat: apply the showcase design system to confirmer.html and desabonnement.html"
```

---

### Task 4: Final cross-page verification

**Files:** none (manual verification, no code changes expected unless it surfaces a bug).

**Interfaces:** consumes the fully styled system from Tasks 1-3.

- [ ] **Step 1: Visual consistency pass**

With all 3 pages open (screenshots or live browser tabs), confirm: identical color
usage across pages (red for urgency/primary actions, teal for calm/confirmation
states, grey for structure), identical type scale and font-family usage, the stamp
badge reads as the same recognizable element on all 3 pages just with different text.

- [ ] **Step 2: Functional smoke test of all 3 forms**

If the claude-in-chrome browser tools are available and the site is already deployed
to Netlify (it is, per prior sessions — `https://logement-crous-alert.netlify.app/`):
navigate to the live `index.html`, submit a real test search; then use a real
confirmation/unsubscribe link (from an email, or construct one with known-valid query
params) to check `confirmer.html`/`desabonnement.html` end-to-end, same pattern as the
unsubscribe-link and configurable-SMTP features' own manual verification steps earlier
in this project. Clean up any test data created (remove test searches from
`searches.json`/`seen.json`), matching the established project convention.

- [ ] **Step 3: Report back**

Summarize what was verified, attach or describe screenshots, and flag anything that
still looks off. No further code changes are expected unless this surfaces a bug.
