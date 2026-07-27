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
