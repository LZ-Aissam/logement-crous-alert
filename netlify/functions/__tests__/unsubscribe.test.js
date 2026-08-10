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

function stubEnv(t) {
  const saved = {
    DATA_REPO_PAT: process.env.DATA_REPO_PAT,
    DATA_REPO: process.env.DATA_REPO,
  };
  process.env.DATA_REPO_PAT = "tok";
  process.env.DATA_REPO = "o/data";
  t.after(() => {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
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
  stubEnv(t);
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
  const inboxCall = calls.find((c) => String(c.url).includes("/contents/inbox/"));
  assert.ok(inboxCall, "expected a write to the private data repo's inbox/");
  const inboxContent = JSON.parse(
    Buffer.from(JSON.parse(inboxCall.options.body).content, "base64").toString("utf-8")
  );
  assert.equal(inboxContent.email, "a@example.com");
  const issueCall = calls.find((c) => String(c.url).includes("api.github.com/repos/o/r/issues"));
  assert.ok(issueCall, "expected a call to the GitHub issues API");
  const sentBody = JSON.parse(issueCall.options.body);
  assert.equal(sentBody.title, "[Désinscription]");
  assert.deepEqual(sentBody.labels, ["unsubscribe"]);
  assert.doesNotMatch(sentBody.body, /a@example\.com/);
  assert.match(
    sentBody.body,
    /### Nom de la recherche\n\nBrest\n\n### Référence email \(dépôt privé\)\n\n[0-9a-f]{32}\n\n### Jeton\n\nabc123\n/
  );
});

test("GitHub API failure returns 502", async (t) => {
  stubEnv(t);
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (String(url).includes("/contents/inbox/")) {
      return { ok: true, status: 201, text: async () => "{}" };
    }
    return { ok: false, status: 500, text: async () => "boom" };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(
    makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, "203.0.113.24")
  );
  assert.equal(result.statusCode, 502);
});

test("a failed inbox write returns 502 and never creates the public issue", async (t) => {
  stubEnv(t);
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push({ url, options });
    if (String(url).includes("/contents/inbox/")) {
      return { ok: false, status: 500, text: async () => "boom" };
    }
    return { ok: true, json: async () => ({ html_url: "unused" }) };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(
    makeEvent({ search: "Brest", email: "a@example.com", token: "abc123" }, "203.0.113.26")
  );

  assert.equal(result.statusCode, 502);
  assert.equal(calls.some((c) => String(c.url).includes("/issues") && !String(c.url).includes("/contents/")), false);
});

test("rate limit trips after 5 requests from the same IP within the window", async (t) => {
  stubEnv(t);
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
