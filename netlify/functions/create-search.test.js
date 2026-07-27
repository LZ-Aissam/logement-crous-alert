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
