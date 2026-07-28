"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { normalizeCity, criteriaMatch } = require("../_criteria");

const fixturesPath = path.join(__dirname, "..", "..", "..", "tests", "fixtures", "criteria_parity_cases.json");
const fixtures = JSON.parse(fs.readFileSync(fixturesPath, "utf-8"));

test("normalizeCity matches the shared fixture cases", () => {
  for (const { input, expected } of fixtures.normalize_city_cases) {
    assert.equal(normalizeCity(input), expected, input);
  }
});

test("criteriaMatch matches the shared fixture cases", () => {
  for (const { a, b, expected, description } of fixtures.match_cases) {
    assert.equal(criteriaMatch(a, b), expected, description);
  }
});
