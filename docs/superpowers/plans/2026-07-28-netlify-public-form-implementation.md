# Netlify Public Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let visitors create a search and confirm their email without a GitHub account, by hosting a form on Netlify whose serverless functions create GitHub Issues on their behalf — reusing the existing Issue-Form backend (`add_search.py`, `confirm_email.py`, the two workflows) unchanged except for one confirmation-URL setting.

**Architecture:** Two static HTML pages (`public/nouvelle-recherche.html`, `public/confirmer.html`) POST JSON to two Netlify Functions (`netlify/functions/create-search.js`, `netlify/functions/confirm-email.js`), which build the same Issue body text the GitHub Issue Form already produces and call the GitHub REST API to open the Issue with the right labels. The existing `add-search.yml`/`confirm-email.yml` workflows pick it up exactly as if a human had submitted the Issue Form directly. A shared helper module (`netlify/functions/_github.js`) provides honeypot detection, a best-effort in-memory rate limiter, and the GitHub API call.

**Tech Stack:** Plain JS (Node 18+ global `fetch`, `node:test` built-in test runner — zero new dependencies), static HTML/CSS/vanilla JS, Netlify Functions (classic Lambda-compatible handler format), Python 3.12 (one small change to `add_search.py`).

## Global Constraints

- No new npm dependencies — use Node's built-in `fetch` and `node:test`/`node:assert`.
- Issue Form field labels must match exactly (they're the parsing contract for `add_search.py`'s `parse_issue_form_body`): `"Nom de la recherche"`, `"Ville"`, `"Mots-clés (résidence, type de logement...) - optionnel"`, `"Email(s) de notification - optionnel"`. Empty optional fields must render as literal `_No response_`, matching GitHub's own Issue Form output.
- Issues created via the API must include the correct `labels` (`["new-search"]` or `["confirm-email"]`) — the existing workflows trigger on `issues: opened` and gate on `contains(github.event.issue.labels.*.name, '...')`; without the label at creation time, nothing runs.
- Honeypot field name: `website`, present on both forms per the approved spec (`docs/superpowers/specs/2026-07-28-netlify-public-form-design.md`, section 4).
- Rate limit: 5 requests/hour per IP, best-effort in-memory (explicitly not durable across cold starts — documented, not a bug).
- The confirmation page requires an explicit button click (POST) — never auto-confirm on page load (GET), to avoid email-scanner pre-fetch triggering false confirmations.
- `CONFIRMATION_BASE_URL` is the exact env var name `add_search.py` reads; when unset, behavior must be byte-identical to today (fallback to the GitHub issue-creation URL).
- Real business validation (email format, geocoding, duplicate names, the 3-email cap) stays in `add_search.py`/`confirm_email.py` — Netlify Functions only check that required fields are non-empty.

---

### Task 1: Shared GitHub helper (`_github.js`) + project scaffolding

**Files:**
- Create: `netlify.toml`
- Create: `package.json`
- Create: `netlify/functions/_github.js`
- Test: `netlify/functions/_github.test.js`

**Interfaces:**
- Produces: `isHoneypotFilled(fields: object) -> boolean`, `createRateLimiter(maxRequests: number, windowMs: number) -> { isRateLimited(ip: string, now?: number) -> boolean }`, `createGithubIssue({ repo, token, title, body, labels }) -> Promise<{ url: string }>`, `clientIp(event: object) -> string`. All exported from `netlify/functions/_github.js` via `module.exports`.

- [ ] **Step 1: Create scaffolding files**

`netlify.toml`:
```toml
[build]
  publish = "public"
  functions = "netlify/functions"
```

`package.json`:
```json
{
  "name": "logement-crous-alert-netlify",
  "private": true,
  "scripts": {
    "test": "node --test \"netlify/functions/*.test.js\""
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `netlify/functions/_github.test.js`:
```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  isHoneypotFilled,
  createRateLimiter,
  createGithubIssue,
  clientIp,
} = require("./_github");

test("isHoneypotFilled returns true when website field is non-empty", () => {
  assert.equal(isHoneypotFilled({ website: "http://spam.example" }), true);
});

test("isHoneypotFilled returns false when website field is empty or absent", () => {
  assert.equal(isHoneypotFilled({ website: "" }), false);
  assert.equal(isHoneypotFilled({}), false);
});

test("createRateLimiter allows up to maxRequests within the window", () => {
  const limiter = createRateLimiter(2, 60000);
  const now = 1000;
  assert.equal(limiter.isRateLimited("1.2.3.4", now), false);
  assert.equal(limiter.isRateLimited("1.2.3.4", now + 10), false);
  assert.equal(limiter.isRateLimited("1.2.3.4", now + 20), true);
});

test("createRateLimiter resets the count after the window elapses", () => {
  const limiter = createRateLimiter(1, 1000);
  const now = 0;
  assert.equal(limiter.isRateLimited("5.6.7.8", now), false);
  assert.equal(limiter.isRateLimited("5.6.7.8", now + 500), true);
  assert.equal(limiter.isRateLimited("5.6.7.8", now + 1500), false);
});

test("createRateLimiter tracks each IP independently", () => {
  const limiter = createRateLimiter(1, 1000);
  assert.equal(limiter.isRateLimited("1.1.1.1", 0), false);
  assert.equal(limiter.isRateLimited("2.2.2.2", 0), false);
});

test("clientIp reads the first address from x-forwarded-for", () => {
  assert.equal(
    clientIp({ headers: { "x-forwarded-for": "9.9.9.9, 10.0.0.1" } }),
    "9.9.9.9"
  );
});

test("clientIp returns 'unknown' when the header is missing", () => {
  assert.equal(clientIp({ headers: {} }), "unknown");
});

test("createGithubIssue posts to the GitHub API and returns the issue URL", async (t) => {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      json: async () => ({ html_url: "https://github.com/o/r/issues/42" }),
    };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await createGithubIssue({
    repo: "o/r",
    token: "tok",
    title: "[Nouvelle recherche] Brest",
    body: "corps",
    labels: ["new-search"],
  });

  assert.equal(result.url, "https://github.com/o/r/issues/42");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.github.com/repos/o/r/issues");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, "Bearer tok");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    title: "[Nouvelle recherche] Brest",
    body: "corps",
    labels: ["new-search"],
  });
});

test("createGithubIssue throws when the GitHub API responds with an error", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: false,
    status: 401,
    text: async () => "Bad credentials",
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  await assert.rejects(
    () =>
      createGithubIssue({ repo: "o/r", token: "bad", title: "t", body: "b", labels: [] }),
    /GitHub API error 401/
  );
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `node --test "netlify/functions/*.test.js"`
Expected: FAIL — `Error: Cannot find module './_github'`

- [ ] **Step 4: Implement `_github.js`**

Create `netlify/functions/_github.js`:
```js
"use strict";

function isHoneypotFilled(fields) {
  return Boolean(fields && fields.website);
}

function createRateLimiter(maxRequests, windowMs) {
  const hits = new Map();

  return {
    isRateLimited(ip, now = Date.now()) {
      const key = ip || "unknown";
      const entry = hits.get(key);

      if (!entry || now - entry.windowStart >= windowMs) {
        hits.set(key, { windowStart: now, count: 1 });
        return false;
      }

      entry.count += 1;
      return entry.count > maxRequests;
    },
  };
}

async function createGithubIssue({ repo, token, title, body, labels }) {
  const response = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ title, body, labels }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub API error ${response.status}: ${text}`);
  }

  const issue = await response.json();
  return { url: issue.html_url };
}

function clientIp(event) {
  const headers = event.headers || {};
  const forwarded = headers["x-forwarded-for"] || headers["X-Forwarded-For"];
  if (!forwarded) return "unknown";
  return forwarded.split(",")[0].trim();
}

module.exports = { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp };
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node --test "netlify/functions/*.test.js"`
Expected: all tests pass (9 pass, 0 fail)

- [ ] **Step 6: Commit**

```bash
git add netlify.toml package.json netlify/functions/_github.js netlify/functions/_github.test.js
git commit -m "feat: add Netlify Functions scaffolding and shared GitHub helper"
```

---

### Task 2: `create-search.js` Netlify Function

**Files:**
- Create: `netlify/functions/create-search.js`
- Test: `netlify/functions/create-search.test.js`

**Interfaces:**
- Consumes: `isHoneypotFilled`, `createRateLimiter`, `createGithubIssue`, `clientIp` from `./_github` (Task 1).
- Produces: `handler(event: { httpMethod, headers, body }) -> Promise<{ statusCode, body }>`, `buildIssueBody(fields) -> string`, both exported via `module.exports` from `netlify/functions/create-search.js`. Reads `process.env.GITHUB_REPOSITORY` and `process.env.GITHUB_PAT`.

- [ ] **Step 1: Write the failing tests**

Create `netlify/functions/create-search.test.js`:
```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { handler } = require("./create-search");

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
    makeEvent({ name: "Brest", city: "Brest", website: "spam" }, "203.0.113.1")
  );

  assert.equal(result.statusCode, 200);
  assert.equal(called, false);
});

test("missing required fields returns 400", async () => {
  const result = await handler(makeEvent({ name: "", city: "" }, "203.0.113.2"));
  assert.equal(result.statusCode, 400);
});

test("valid payload creates a GitHub issue matching the Issue Form contract", async (t) => {
  const originalFetch = global.fetch;
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ html_url: "https://github.com/o/r/issues/1" }) };
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
      { name: "Brest", city: "Brest 29200", keywords: "", emails: "a@example.com" },
      "203.0.113.3"
    )
  );

  assert.equal(result.statusCode, 200);
  assert.deepEqual(JSON.parse(result.body), { issueUrl: "https://github.com/o/r/issues/1" });
  assert.equal(calls[0].url, "https://api.github.com/repos/o/r/issues");
  const sentBody = JSON.parse(calls[0].options.body);
  assert.equal(sentBody.title, "[Nouvelle recherche] Brest");
  assert.deepEqual(sentBody.labels, ["new-search"]);
  assert.match(sentBody.body, /### Nom de la recherche\n\nBrest\n/);
  assert.match(sentBody.body, /### Ville\n\nBrest 29200\n/);
  assert.match(
    sentBody.body,
    /### Mots-clés \(résidence, type de logement\.\.\.\) - optionnel\n\n_No response_\n/
  );
  assert.match(sentBody.body, /### Email\(s\) de notification - optionnel\n\na@example\.com\n/);
});

test("GitHub API failure returns 502", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 500, text: async () => "boom" });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(makeEvent({ name: "Brest", city: "Brest" }, "203.0.113.4"));
  assert.equal(result.statusCode, 502);
});

test("rate limit trips after 5 requests from the same IP within the window", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ html_url: "https://github.com/o/r/issues/1" }),
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const ip = "203.0.113.5";
  for (let i = 0; i < 5; i++) {
    const result = await handler(makeEvent({ name: "Brest", city: "Brest" }, ip));
    assert.equal(result.statusCode, 200);
  }
  const sixth = await handler(makeEvent({ name: "Brest", city: "Brest" }, ip));
  assert.equal(sixth.statusCode, 429);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test "netlify/functions/*.test.js"`
Expected: FAIL — `Error: Cannot find module './create-search'`

- [ ] **Step 3: Implement `create-search.js`**

Create `netlify/functions/create-search.js`:
```js
"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

const FIELD_NAME = "Nom de la recherche";
const FIELD_CITY = "Ville";
const FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel";
const FIELD_EMAILS = "Email(s) de notification - optionnel";

function section(label, value) {
  const trimmed = value && value.trim();
  return `### ${label}\n\n${trimmed || "_No response_"}\n`;
}

function buildIssueBody(fields) {
  return [
    section(FIELD_NAME, fields.name),
    section(FIELD_CITY, fields.city),
    section(FIELD_KEYWORDS, fields.keywords),
    section(FIELD_EMAILS, fields.emails),
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

  if (!fields.name || !fields.name.trim() || !fields.city || !fields.city.trim()) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le nom de la recherche et la ville sont obligatoires." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: `[Nouvelle recherche] ${fields.name.trim()}`,
      body: buildIssueBody(fields),
      labels: ["new-search"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch {
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, reessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test "netlify/functions/*.test.js"`
Expected: all tests pass (15 pass total, 0 fail)

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/create-search.js netlify/functions/create-search.test.js
git commit -m "feat: add create-search Netlify Function"
```

---

### Task 3: `confirm-email.js` Netlify Function

**Files:**
- Create: `netlify/functions/confirm-email.js`
- Test: `netlify/functions/confirm-email.test.js`

**Interfaces:**
- Consumes: `isHoneypotFilled`, `createRateLimiter`, `createGithubIssue`, `clientIp` from `./_github` (Task 1).
- Produces: `handler(event) -> Promise<{ statusCode, body }>`, `buildIssueBody(code: string) -> string`, exported via `module.exports` from `netlify/functions/confirm-email.js`.

- [ ] **Step 1: Write the failing tests**

Create `netlify/functions/confirm-email.test.js`:
```js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { handler } = require("./confirm-email");

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

  const result = await handler(makeEvent({ code: "abc123", website: "spam" }, "203.0.113.11"));

  assert.equal(result.statusCode, 200);
  assert.equal(called, false);
});

test("missing code returns 400", async () => {
  const result = await handler(makeEvent({ code: "" }, "203.0.113.12"));
  assert.equal(result.statusCode, 400);
});

test("valid code creates a GitHub issue matching the Issue Form contract", async (t) => {
  const originalFetch = global.fetch;
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ html_url: "https://github.com/o/r/issues/2" }) };
  };
  process.env.GITHUB_REPOSITORY = "o/r";
  process.env.GITHUB_PAT = "tok";
  t.after(() => {
    global.fetch = originalFetch;
    process.env.GITHUB_REPOSITORY = originalRepo;
    process.env.GITHUB_PAT = originalToken;
  });

  const result = await handler(makeEvent({ code: "abc123" }, "203.0.113.13"));

  assert.equal(result.statusCode, 200);
  assert.deepEqual(JSON.parse(result.body), { issueUrl: "https://github.com/o/r/issues/2" });
  const sentBody = JSON.parse(calls[0].options.body);
  assert.equal(sentBody.title, "[Confirmation email]");
  assert.deepEqual(sentBody.labels, ["confirm-email"]);
  assert.equal(sentBody.body, "### Code de confirmation\n\nabc123\n");
});

test("GitHub API failure returns 502", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 500, text: async () => "boom" });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(makeEvent({ code: "abc123" }, "203.0.113.14"));
  assert.equal(result.statusCode, 502);
});

test("rate limit trips after 5 requests from the same IP within the window", async (t) => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ html_url: "https://github.com/o/r/issues/2" }),
  });
  t.after(() => {
    global.fetch = originalFetch;
  });

  const ip = "203.0.113.15";
  for (let i = 0; i < 5; i++) {
    const result = await handler(makeEvent({ code: "abc123" }, ip));
    assert.equal(result.statusCode, 200);
  }
  const sixth = await handler(makeEvent({ code: "abc123" }, ip));
  assert.equal(sixth.statusCode, 429);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test "netlify/functions/*.test.js"`
Expected: FAIL — `Error: Cannot find module './confirm-email'`

- [ ] **Step 3: Implement `confirm-email.js`**

Create `netlify/functions/confirm-email.js`:
```js
"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

function buildIssueBody(code) {
  return `### Code de confirmation\n\n${code.trim()}\n`;
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

  if (!fields.code || !fields.code.trim()) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le code de confirmation est obligatoire." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: "[Confirmation email]",
      body: buildIssueBody(fields.code),
      labels: ["confirm-email"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch {
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, reessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test "netlify/functions/*.test.js"`
Expected: all tests pass (21 pass total, 0 fail)

- [ ] **Step 5: Commit**

```bash
git add netlify/functions/confirm-email.js netlify/functions/confirm-email.test.js
git commit -m "feat: add confirm-email Netlify Function"
```

---

### Task 4: Static pages

**Files:**
- Create: `public/nouvelle-recherche.html`
- Create: `public/confirmer.html`

**Interfaces:**
- Consumes: `POST /.netlify/functions/create-search` and `POST /.netlify/functions/confirm-email` (Tasks 2-3), both returning `{ issueUrl: string | null }` on 200 or `{ error: string }` on 4xx/5xx.

- [ ] **Step 1: Create `public/nouvelle-recherche.html`**

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nouvelle recherche - Alerte logement CROUS</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
  label { display: block; margin-top: 1rem; font-weight: 600; }
  input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; }
  button { margin-top: 1.5rem; padding: 0.6rem 1.2rem; }
  #result { margin-top: 1.5rem; padding: 1rem; border-radius: 4px; }
  #result.success { background: #e6f4ea; }
  #result.error { background: #fce8e6; }
  #result.hidden { display: none; }
  .honeypot { position: absolute; left: -9999px; top: -9999px; }
</style>
</head>
<body>
<h1>Nouvelle recherche</h1>
<p>Surveille une ville sur trouverunlogement.lescrous.fr et recois un email des qu'un logement apparait.</p>
<form id="search-form">
  <label for="name">Nom de la recherche</label>
  <input id="name" name="name" required placeholder="Brest">

  <label for="city">Ville</label>
  <input id="city" name="city" required placeholder="Brest 29200">

  <label for="keywords">Mots-cles (residence, type de logement...) - optionnel</label>
  <input id="keywords" name="keywords" placeholder="Kergoat, studio">

  <label for="emails">Email(s) de notification - optionnel (max 3, separes par des virgules)</label>
  <input id="emails" name="emails" placeholder="toi@example.com">

  <div class="honeypot" aria-hidden="true">
    <label for="website">Laisse ce champ vide</label>
    <input id="website" name="website" tabindex="-1" autocomplete="off">
  </div>

  <button type="submit">Creer la recherche</button>
</form>
<div id="result" class="hidden"></div>

<script>
  const form = document.getElementById("search-form");
  const result = document.getElementById("result");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    result.className = "hidden";

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
        result.className = "error";
        return;
      }

      result.innerHTML = data.issueUrl
        ? 'Recherche soumise. <a href="' + data.issueUrl + '" target="_blank" rel="noopener">Suivre le traitement ici</a>.'
        : "Recherche soumise.";
      result.className = "success";
      form.reset();
    } catch (err) {
      result.textContent = "Une erreur est survenue, reessaie dans quelques minutes.";
      result.className = "error";
    }
  });
</script>
</body>
</html>
```

- [ ] **Step 2: Create `public/confirmer.html`**

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Confirmer mon email - Alerte logement CROUS</title>
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
<h1>Confirmer mon email</h1>
<p>Clique sur le bouton ci-dessous pour confirmer que tu acceptes de recevoir des alertes logement a cette adresse.</p>

<div class="honeypot" aria-hidden="true">
  <label for="website">Laisse ce champ vide</label>
  <input id="website" tabindex="-1" autocomplete="off">
</div>

<button id="confirm-button" type="button">Confirmer mon email</button>
<div id="result" class="hidden"></div>

<script>
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const button = document.getElementById("confirm-button");
  const result = document.getElementById("result");
  const website = document.getElementById("website");

  if (!code) {
    button.disabled = true;
    result.textContent = "Lien invalide : aucun code de confirmation trouve dans l'URL.";
    result.className = "error";
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    result.className = "hidden";

    try {
      const response = await fetch("/.netlify/functions/confirm-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, website: website.value }),
      });
      const data = await response.json();

      if (!response.ok) {
        result.textContent = data.error || "Une erreur est survenue.";
        result.className = "error";
        button.disabled = false;
        return;
      }

      result.innerHTML = data.issueUrl
        ? 'Confirmation envoyee. <a href="' + data.issueUrl + '" target="_blank" rel="noopener">Suivre le traitement ici</a>.'
        : "Confirmation envoyee.";
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

- [ ] **Step 3: Manually verify both pages render**

Open `public/nouvelle-recherche.html` and `public/confirmer.html?code=test123` directly in a browser
(`file://` path is fine for this check). Expected: both pages render with correct French labels, the
honeypot field is not visually present, and submitting shows a network-error message (there is no local
functions server yet — that's expected and confirms the fetch wiring runs).

- [ ] **Step 4: Commit**

```bash
git add public/nouvelle-recherche.html public/confirmer.html
git commit -m "feat: add public Netlify pages for search creation and email confirmation"
```

---

### Task 5: `add_search.py` — configurable confirmation URL

**Files:**
- Modify: `add_search.py:125-141` (`build_confirmation_url`, `build_confirmation_email_body`)
- Test: `tests/test_add_search.py`

**Interfaces:**
- Consumes: `os.environ.get("CONFIRMATION_BASE_URL")` (new), `os.environ.get("GITHUB_REPOSITORY")` (existing).
- Produces: `build_confirmation_url(token: str) -> str` — unchanged signature, new fallback behavior.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_add_search.py` (near the other standalone function tests, e.g. after
`test_build_search_url_contains_bounds_and_tool_id`):
```python
def test_build_confirmation_url_falls_back_to_github_when_base_url_unset(monkeypatch):
    monkeypatch.delenv("CONFIRMATION_BASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")

    url = mod.build_confirmation_url("abc123")

    assert url == (
        "https://github.com/LZ-Aissam/logement-crous-alert/issues/new"
        "?template=confirm-email.yml&code=abc123"
    )


def test_build_confirmation_url_uses_confirmation_base_url_when_set(monkeypatch):
    monkeypatch.setenv("CONFIRMATION_BASE_URL", "https://example.netlify.app/confirmer.html")

    url = mod.build_confirmation_url("abc123")

    assert url == "https://example.netlify.app/confirmer.html?code=abc123"


def test_build_confirmation_email_body_does_not_mention_github_account():
    body = mod.build_confirmation_email_body("Brest", "https://example.com/confirm?code=x")

    assert "compte GitHub" not in body
    assert "https://example.com/confirm?code=x" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_add_search.py -k "confirmation_url or confirmation_email_body" -v`
Expected: `test_build_confirmation_url_uses_confirmation_base_url_when_set` FAILS (returns the GitHub URL,
ignoring `CONFIRMATION_BASE_URL`); `test_build_confirmation_email_body_does_not_mention_github_account`
FAILS (current text contains "compte GitHub").

- [ ] **Step 3: Update `add_search.py`**

Replace lines 125-141 in `add_search.py`:
```python
def build_confirmation_url(token: str) -> str:
    base_url = os.environ.get("CONFIRMATION_BASE_URL")
    if base_url:
        return f"{base_url}?code={urllib.parse.quote(token)}"
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    return (
        f"https://github.com/{repo}/issues/new"
        f"?template=confirm-email.yml&code={urllib.parse.quote(token)}"
    )


def build_confirmation_email_body(search_name: str, confirmation_url: str) -> str:
    return (
        "Quelqu'un a demande a recevoir des alertes de logement CROUS a cette adresse "
        f"email, pour la recherche {search_name!r}.\n\n"
        "Si c'est bien toi, confirme en cliquant sur ce lien :\n"
        f"{confirmation_url}\n\n"
        "Si tu n'es pas a l'origine de cette demande, ignore simplement cet email -- "
        "rien ne sera active sans ta confirmation."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q`
Expected: all tests pass (80 passed)

- [ ] **Step 5: Commit**

```bash
git add add_search.py tests/test_add_search.py
git commit -m "feat: point confirmation emails at CONFIRMATION_BASE_URL when configured"
```

---

### Task 6: Wire `CONFIRMATION_BASE_URL` into the workflow

**Files:**
- Modify: `.github/workflows/add-search.yml`

**Interfaces:**
- Consumes: GitHub Actions repo secret `CONFIRMATION_BASE_URL` (configured manually by the repo owner, documented in Task 7).

- [ ] **Step 1: Add the env var**

In `.github/workflows/add-search.yml`, in the `Process new search request` step's `env:` block, add one
line so it reads:
```yaml
        env:
          ISSUE_BODY: ${{ github.event.issue.body }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          CONFIRMATION_BASE_URL: ${{ secrets.CONFIRMATION_BASE_URL }}
```

- [ ] **Step 2: Verify the change**

Run: `git diff .github/workflows/add-search.yml`
Expected: a single added line, `CONFIRMATION_BASE_URL: ${{ secrets.CONFIRMATION_BASE_URL }}`, inside the
existing `env:` block — nothing else changed. If the secret is unset in the repo, GitHub Actions passes an
empty string, and `add_search.py`'s `os.environ.get("CONFIRMATION_BASE_URL")` treats `""` as falsy, so the
fallback to the GitHub URL still applies (confirmed by Task 5's test).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/add-search.yml
git commit -m "feat: pass CONFIRMATION_BASE_URL secret into add-search workflow"
```

---

### Task 7: README — document the Netlify deployment

**Files:**
- Modify: `README.md:107-110` (remove the "necessite un compte GitHub" claim, which becomes conditionally
  false)
- Modify: `README.md` (insert new section before `## Développement local`, currently at line 132)

**Interfaces:** none (documentation only).

- [ ] **Step 1: Fix the now-conditional claim**

In `README.md`, replace (currently lines 107-110):
```
Un email de confirmation est envoyé à chaque adresse renseignée, avec un lien vers un
second formulaire ("Confirmer mon email"). Ce lien ouvre une nouvelle Issue
pré-remplie avec un code de confirmation unique ; soumettre cette issue nécessite un
compte GitHub (gratuit).
```
with:
```
Un email de confirmation est envoyé à chaque adresse renseignée, avec un lien à
cliquer pour confirmer. Par défaut ce lien ouvre une nouvelle Issue GitHub
pré-remplie avec un code de confirmation unique (nécessite un compte GitHub,
gratuit) — sauf si le formulaire public Netlify est configuré (voir plus bas), auquel
cas le lien ouvre une simple page web, sans compte requis.
```

- [ ] **Step 2: Insert the new section**

In `README.md`, immediately before `## Développement local` (currently line 132), insert:
```markdown
## Formulaire public sans compte GitHub (optionnel, via Netlify)

Par défaut, créer une recherche ou confirmer un email nécessite un compte GitHub (pour
soumettre les Issue Forms ci-dessus). Pour ouvrir ça à n'importe qui sans compte, tu
peux déployer les pages `public/nouvelle-recherche.html` et `public/confirmer.html` sur
Netlify — elles créent les mêmes Issues GitHub à ta place, via deux Netlify Functions
(`netlify/functions/create-search.js` et `confirm-email.js`). Le backend Python et les
workflows GitHub Actions ne changent pas : ils traitent ces Issues exactement comme si
elles avaient été soumises à la main.

1. Crée un compte Netlify et lie-le à ce dépôt GitHub (Netlify détecte automatiquement
   `netlify.toml` : `public/` comme dossier publié, `netlify/functions/` comme dossier
   de fonctions).
2. Crée un token GitHub *fine-grained* (Settings > Developer settings > Personal access
   tokens > Fine-grained tokens), limité à **ce seul dépôt**, avec la permission
   **Issues: Read and write** uniquement (rien d'autre).
3. Dans les paramètres du site Netlify (Site configuration > Environment variables),
   ajoute :
   - `GITHUB_PAT` : le token créé à l'étape 2
   - `GITHUB_REPOSITORY` : `LZ-Aissam/logement-crous-alert`
4. Ajoute un secret sur le dépôt GitHub (Settings > Secrets and variables > Actions) :
   - `CONFIRMATION_BASE_URL` : l'URL de la page de confirmation sur ton site Netlify,
     ex. `https://ton-site.netlify.app/confirmer.html`

   Sans ce secret, les liens de confirmation continuent de pointer vers GitHub comme
   avant — rien ne casse si tu ne déploies jamais Netlify.
5. Le formulaire GitHub direct (section ci-dessus) continue de fonctionner en
   parallèle : c'est une alternative, pas un remplacement.

**Limite assumée** : la protection anti-abus (champ honeypot + limite de 5
requêtes/heure par IP) est faite au mieux, sans garantie forte — suffisante contre le
spam basique, pas contre un attaquant déterminé. Comme pour le formulaire GitHub actuel,
il n'y a pas de compte utilisateur ni de tableau de bord pour gérer ses propres
recherches après coup.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the optional Netlify public form deployment"
```
