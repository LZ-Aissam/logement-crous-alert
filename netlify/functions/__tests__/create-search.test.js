"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { handler } = require("../create-search");

function makeEvent(fields, ip) {
  return {
    httpMethod: "POST",
    headers: { "x-forwarded-for": ip },
    body: JSON.stringify(fields),
  };
}

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
      { name: "Brest", city: "Brest", website: "spam", turnstileToken: "tok" },
      "203.0.113.1"
    )
  );

  assert.equal(result.statusCode, 200);
  assert.equal(called, false);
});

test("missing required fields returns 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent({ name: "", city: "", turnstileToken: "tok" }, "203.0.113.2")
  );
  assert.equal(result.statusCode, 400);
});

test("valid payload creates a GitHub issue matching the Issue Form contract", async (t) => {
  stubEnv(t);
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = stubFetch(t);
  process.env.GITHUB_REPOSITORY = "o/r";
  process.env.GITHUB_PAT = "tok";
  t.after(() => {
    process.env.GITHUB_REPOSITORY = originalRepo;
    process.env.GITHUB_PAT = originalToken;
  });

  const result = await handler(
    makeEvent(
      {
        name: "Brest",
        city: "Brest 29200",
        keywords: "",
        emails: "a@example.com",
        turnstileToken: "tok",
      },
      "203.0.113.3"
    )
  );

  assert.equal(result.statusCode, 200);
  assert.deepEqual(JSON.parse(result.body), { issueUrl: "https://github.com/o/r/issues/1" });
  const issueCall = calls.find((c) => String(c.url).includes("api.github.com/repos/o/r/issues"));
  assert.ok(issueCall, "expected a call to the GitHub issues API");
  const sentBody = JSON.parse(issueCall.options.body);
  assert.equal(sentBody.title, "[Nouvelle recherche] Brest");
  assert.deepEqual(sentBody.labels, ["new-search"]);
  assert.match(sentBody.body, /### Nom de la recherche\n\nBrest\n/);
  assert.match(sentBody.body, /### Ville\n\nBrest 29200\n/);
  assert.match(
    sentBody.body,
    /### Mots-clés \(résidence, type de logement\.\.\.\) - optionnel\n\n_No response_\n/
  );
  assert.match(sentBody.body, /### Email de notification\n\na@example\.com\n/);
});

test("GitHub API failure returns 502", async (t) => {
  stubEnv(t);
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (String(url).includes("challenges.cloudflare.com")) {
      return { ok: true, json: async () => ({ success: true }) };
    }
    if (String(url).includes("/contents/")) {
      return { ok: false, status: 404, text: async () => "not found" };
    }
    return { ok: false, status: 500, text: async () => "boom" };
  };
  t.after(() => {
    global.fetch = originalFetch;
  });

  const result = await handler(
    makeEvent(
      { name: "Brest", city: "Brest", emails: "a@example.com", turnstileToken: "tok" },
      "203.0.113.4"
    )
  );
  assert.equal(result.statusCode, 502);
});

test("rate limit trips after 5 requests from the same IP within the window", async (t) => {
  stubEnv(t);
  stubFetch(t);

  const ip = "203.0.113.5";
  for (let i = 0; i < 5; i++) {
    const result = await handler(
      makeEvent(
        { name: "Brest", city: "Brest", emails: "a@example.com", turnstileToken: "tok" },
        ip
      )
    );
    assert.equal(result.statusCode, 200);
  }
  const sixth = await handler(
    makeEvent({ name: "Brest", city: "Brest", emails: "a@example.com", turnstileToken: "tok" }, ip)
  );
  assert.equal(sixth.statusCode, 429);
});

test("valid payload includes the 5 new optional sections in the issue body", async (t) => {
  stubEnv(t);
  const originalRepo = process.env.GITHUB_REPOSITORY;
  const originalToken = process.env.GITHUB_PAT;
  const calls = stubFetch(t);
  process.env.GITHUB_REPOSITORY = "o/r";
  process.env.GITHUB_PAT = "tok";
  t.after(() => {
    process.env.GITHUB_REPOSITORY = originalRepo;
    process.env.GITHUB_PAT = originalToken;
  });

  const result = await handler(
    makeEvent(
      {
        name: "Brest",
        city: "Brest 29200",
        extent: "-4.5689169_48.4595521_-4.4278311_48.3572972",
        maxPrice: "400",
        minArea: "15",
        occupationMode: "alone,house_sharing",
        prm: "true",
        emails: "a@example.com",
        turnstileToken: "tok",
      },
      "203.0.113.31"
    )
  );

  assert.equal(result.statusCode, 200);
  const issueCall = calls.find((c) => String(c.url).includes("api.github.com/repos/o/r/issues"));
  assert.ok(issueCall, "expected a call to the GitHub issues API");
  const sentBody = JSON.parse(issueCall.options.body);
  assert.match(
    sentBody.body,
    /### Zone geographique precise \(rempli automatiquement\) - optionnel\n\n-4\.5689169_48\.4595521_-4\.4278311_48\.3572972\n/
  );
  assert.match(sentBody.body, /### Prix maximum - optionnel\n\n400\n/);
  assert.match(sentBody.body, /### Surface minimum en m2 - optionnel\n\n15\n/);
  assert.match(
    sentBody.body,
    /### Type de cohabitation \(individuel, couple, colocation\) - optionnel\n\nalone,house_sharing\n/
  );
  assert.match(sentBody.body, /### Logement adapte PMR - optionnel\n\ntrue\n/);
});

test("non-numeric maxPrice returns 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent(
      {
        name: "Brest",
        city: "Brest 29200",
        maxPrice: "gratuit",
        emails: "a@example.com",
        turnstileToken: "tok",
      },
      "203.0.113.32"
    )
  );
  assert.equal(result.statusCode, 400);
});

test("non-numeric minArea returns 400", async (t) => {
  stubEnv(t);
  stubFetch(t);
  const result = await handler(
    makeEvent(
      {
        name: "Brest",
        city: "Brest 29200",
        minArea: "grand",
        emails: "a@example.com",
        turnstileToken: "tok",
      },
      "203.0.113.33"
    )
  );
  assert.equal(result.statusCode, 400);
});

test("missing optional new fields still succeeds (backward compatible)", async (t) => {
  stubEnv(t);
  stubFetch(t);

  const result = await handler(
    makeEvent(
      { name: "Brest", city: "Brest 29200", emails: "a@example.com", turnstileToken: "tok" },
      "203.0.113.34"
    )
  );
  assert.equal(result.statusCode, 200);
});

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
