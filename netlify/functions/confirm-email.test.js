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
