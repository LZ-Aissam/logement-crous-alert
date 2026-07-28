"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

const FIELD_NAME = "Nom de la recherche";
const FIELD_CITY = "Ville";
const FIELD_KEYWORDS = "Mots-clés (résidence, type de logement...) - optionnel";
const FIELD_EMAILS = "Email(s) de notification - optionnel";
const FIELD_EXTENT = "Zone geographique precise (rempli automatiquement) - optionnel";
const FIELD_MAX_PRICE = "Prix maximum - optionnel";
const FIELD_MIN_AREA = "Surface minimum en m2 - optionnel";
const FIELD_OCCUPATION_MODE = "Type de cohabitation (individuel, couple, colocation) - optionnel";
const FIELD_PRM = "Logement adapte PMR - optionnel";

function section(label, value) {
  const trimmed = value && value.trim();
  return `### ${label}\n\n${trimmed || "_No response_"}\n`;
}

function buildIssueBody(fields) {
  return [
    section(FIELD_NAME, fields.name),
    section(FIELD_CITY, fields.city),
    section(FIELD_KEYWORDS, fields.keywords),
    section(FIELD_EMAILS, fields.emails),
    section(FIELD_EXTENT, fields.extent),
    section(FIELD_MAX_PRICE, fields.maxPrice),
    section(FIELD_MIN_AREA, fields.minArea),
    section(FIELD_OCCUPATION_MODE, fields.occupationMode),
    section(FIELD_PRM, fields.prm),
  ].join("\n");
}

async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  let fields;
  try {
    fields = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: "JSON invalide" }) };
  }

  if (isHoneypotFilled(fields)) {
    return { statusCode: 200, body: JSON.stringify({ issueUrl: null }) };
  }

  if (rateLimiter.isRateLimited(clientIp(event))) {
    return {
      statusCode: 429,
      body: JSON.stringify({ error: "Trop de tentatives, reessaie dans une heure." }),
    };
  }

  if (!fields.name || !fields.name.trim() || !fields.city || !fields.city.trim()) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le nom de la recherche et la ville sont obligatoires." }),
    };
  }

  if (fields.maxPrice && fields.maxPrice.trim() && Number.isNaN(Number(fields.maxPrice))) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le prix maximum doit etre un nombre." }),
    };
  }

  if (fields.minArea && fields.minArea.trim() && Number.isNaN(Number(fields.minArea))) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "La surface minimum doit etre un nombre." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: `[Nouvelle recherche] ${fields.name.trim()}`,
      body: buildIssueBody(fields),
      labels: ["new-search"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch (err) {
    console.error("create-search: GitHub API call failed", err);
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, reessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
