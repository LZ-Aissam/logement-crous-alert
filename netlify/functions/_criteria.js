"use strict";

// Behavioral mirror of search_criteria.py -- any change here must be applied there too.

function normalizeCity(city) {
  return String(city || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function toNumberOrNull(value) {
  const trimmed = String(value == null ? "" : value).trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

function buildCriteria(fields) {
  const modes = String((fields && fields.occupationMode) || "")
    .split(",")
    .map((mode) => mode.trim())
    .filter(Boolean);
  const keywords = String((fields && fields.keywords) || "")
    .split(",")
    .map((kw) => kw.trim().toLowerCase())
    .filter(Boolean);
  return {
    extent: String((fields && fields.extent) || "").trim(),
    city: normalizeCity(fields && fields.city),
    maxPrice: toNumberOrNull(fields && fields.maxPrice),
    minArea: toNumberOrNull(fields && fields.minArea),
    occupationModes: Array.from(new Set(modes)).sort(),
    prm: Boolean(fields && fields.prm && String(fields.prm).trim()),
    keywords: Array.from(new Set(keywords)).sort(),
  };
}

function sameModes(a, b) {
  const left = [...(a || [])].sort();
  const right = [...(b || [])].sort();
  return left.length === right.length && left.every((mode, i) => mode === right[i]);
}

function criteriaMatch(a, b) {
  if (!a || !b) return false;
  // An extent describes the exact search area; two identical extents mean the same
  // zone even when the typed city label differs. Fall back to the city otherwise.
  if (a.extent && b.extent) {
    if (a.extent !== b.extent) return false;
  } else if (a.city !== b.city) {
    // Both sides are already normalized by buildCriteria -- same as search_criteria.py
    return false;
  }
  return (
    (a.maxPrice ?? null) === (b.maxPrice ?? null) &&
    (a.minArea ?? null) === (b.minArea ?? null) &&
    sameModes(a.occupationModes, b.occupationModes) &&
    Boolean(a.prm) === Boolean(b.prm) &&
    sameModes(a.keywords, b.keywords)
  );
}

function findDuplicate({ searches, pending, email, criteria }) {
  const wanted = String(email || "").trim().toLowerCase();
  if (!wanted) return null;

  for (const entry of searches || []) {
    if (!criteriaMatch(entry && entry.criteria, criteria)) continue;
    const emails = (entry && entry.emails) || [];
    if (emails.some((e) => String(e).trim().toLowerCase() === wanted)) return entry.name;
  }

  for (const [name, record] of Object.entries(pending || {})) {
    const search = (record && record.search) || {};
    if (!criteriaMatch(search.criteria, criteria)) continue;
    const emails = Object.values((record && record.pending_emails) || {});
    if (emails.some((e) => String(e).trim().toLowerCase() === wanted)) return name;
  }

  return null;
}

module.exports = { normalizeCity, buildCriteria, criteriaMatch, findDuplicate };
