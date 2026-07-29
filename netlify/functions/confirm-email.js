"use strict";

const { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp } = require("./_github");

const MAX_REQUESTS_PER_WINDOW = 5;
const WINDOW_MS = 60 * 60 * 1000;
const rateLimiter = createRateLimiter(MAX_REQUESTS_PER_WINDOW, WINDOW_MS);

function buildIssueBody(code) {
  return `### Code de confirmation\n\n${code.trim()}\n`;
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

  if (!fields.code || !fields.code.trim()) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: "Le code de confirmation est obligatoire." }),
    };
  }

  try {
    const issue = await createGithubIssue({
      repo: process.env.GITHUB_REPOSITORY,
      token: process.env.GITHUB_PAT,
      title: "[Confirmation email]",
      body: buildIssueBody(fields.code),
      labels: ["confirm-email"],
    });
    return { statusCode: 200, body: JSON.stringify({ issueUrl: issue.url }) };
  } catch (err) {
    console.error("confirm-email: GitHub API call failed", err);
    return {
      statusCode: 502,
      body: JSON.stringify({ error: "Une erreur est survenue, réessaie dans quelques minutes." }),
    };
  }
}

module.exports = { handler, buildIssueBody };
