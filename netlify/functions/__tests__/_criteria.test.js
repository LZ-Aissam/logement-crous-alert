"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { buildCriteria, criteriaMatch, findDuplicate, normalizeCity } = require("../_criteria");

test("normalizeCity trims, lowercases and collapses whitespace", () => {
  assert.equal(normalizeCity("  Saint   Denis  "), "saint denis");
  assert.equal(normalizeCity(undefined), "");
});

test("buildCriteria mirrors the Python shape", () => {
  assert.deepEqual(
    buildCriteria({
      city: "  Rennes ",
      extent: "-1.75_48.16_-1.61_48.05",
      maxPrice: "500",
      minArea: "18",
      occupationMode: "house_sharing,alone,alone",
      prm: "true",
      keywords: "Kergoat, studio",
    }),
    {
      extent: "-1.75_48.16_-1.61_48.05",
      city: "rennes",
      maxPrice: 500,
      minArea: 18,
      occupationModes: ["alone", "house_sharing"],
      prm: true,
      keywords: ["kergoat", "studio"],
    }
  );
});

test("buildCriteria maps empty optional fields to null, not zero", () => {
  const criteria = buildCriteria({ city: "Brest" });
  assert.equal(criteria.extent, "");
  assert.equal(criteria.maxPrice, null);
  assert.equal(criteria.minArea, null);
  assert.deepEqual(criteria.occupationModes, []);
  assert.equal(criteria.prm, false);
  assert.deepEqual(criteria.keywords, []);
});

test("buildCriteria dedupes keywords case-insensitively", () => {
  const criteria = buildCriteria({ city: "Brest", keywords: "Kergoat, kergoat,  Studio " });
  assert.deepEqual(criteria.keywords, ["kergoat", "studio"]);
});

test("criteriaMatch prefers extent over city label", () => {
  const a = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const b = buildCriteria({ city: "Rennes Villejean", extent: "1_2_3_4" });
  assert.equal(criteriaMatch(a, b), true);
});

test("criteriaMatch falls back to city when no extent", () => {
  assert.equal(criteriaMatch(buildCriteria({ city: "Brest" }), buildCriteria({ city: " brest " })), true);
});

test("criteriaMatch rejects a differing filter", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4", maxPrice: "400" });
  const b = buildCriteria({ city: "Brest", extent: "1_2_3_4", maxPrice: "500" });
  assert.equal(criteriaMatch(a, b), false);
});

test("criteriaMatch rejects differing keywords", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4", keywords: "Kergoat" });
  const b = buildCriteria({ city: "Brest", extent: "1_2_3_4", keywords: "Bellevue" });
  assert.equal(criteriaMatch(a, b), false);
});

test("criteriaMatch ignores keyword order and case", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4", keywords: "Kergoat, Studio" });
  const b = buildCriteria({ city: "Brest", extent: "1_2_3_4", keywords: "studio, kergoat" });
  assert.equal(criteriaMatch(a, b), true);
});

test("criteriaMatch never matches a missing criteria block", () => {
  const a = buildCriteria({ city: "Brest", extent: "1_2_3_4" });
  assert.equal(criteriaMatch(a, null), false);
  assert.equal(criteriaMatch(a, undefined), false);
});

test("findDuplicate finds an active search with the same email and criteria", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Rennes", emails: ["A@Example.com"], criteria }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "a@example.com", criteria }), "Rennes");
});

test("findDuplicate finds a pending search awaiting confirmation", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const pending = { Rennes: { search: { criteria }, pending_emails: { abc: "a@example.com" } } };
  assert.equal(findDuplicate({ searches: [], pending, email: "a@example.com", criteria }), "Rennes");
});

test("findDuplicate returns null for a different email", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Rennes", emails: ["a@example.com"], criteria }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "b@example.com", criteria }), null);
});

test("findDuplicate ignores entries without a criteria block", () => {
  const criteria = buildCriteria({ city: "Rennes", extent: "1_2_3_4" });
  const searches = [{ name: "Legacy", emails: ["a@example.com"] }];
  assert.equal(findDuplicate({ searches, pending: {}, email: "a@example.com", criteria }), null);
});
