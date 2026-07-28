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
