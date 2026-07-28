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
