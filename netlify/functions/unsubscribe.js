"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

function section(label, value) {
  const trimmed = value && value.trim();
  return `### ${label}\n\n${trimmed || "_No response_"}\n`;
}

function buildIssueBody(fields) {
  return [
    section("Nom de la recherche", fields.search),
    section("Email", fields.email),
    section("Jeton", fields.token),
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
      body: JSON.stringify({ error: "Trop de tentatives, réessaie dans une heure." }),
    };
  }

  const missing =
    !fields.search || !fields.search.trim() ||
    !fields.email || !fields.email.trim() ||
    !fields.token || !fields.token.trim();
  if (missing) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "La recherche, l'email et le jeton sont obligatoires." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: "[Désinscription]",
      body: buildIssueBody(fields),
      labels: ["unsubscribe"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch (err) {
    console.error("unsubscribe: GitHub API call failed", err);
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, réessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
