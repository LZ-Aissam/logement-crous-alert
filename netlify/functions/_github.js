"use strict";

function isHoneypotFilled(fields) {
  return Boolean(fields && fields.website);
}

function createRateLimiter(maxRequests, windowMs) {
  const hits = new Map();

  return {
    isRateLimited(ip, now = Date.now()) {
      const key = ip || "unknown";
      const entry = hits.get(key);

      if (!entry || now - entry.windowStart >= windowMs) {
        hits.set(key, { windowStart: now, count: 1 });
        return false;
      }

      entry.count += 1;
      return entry.count > maxRequests;
    },
  };
}

async function createGithubIssue({ repo, token, title, body, labels }) {
  const response = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ title, body, labels }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`GitHub API error ${response.status}: ${text}`);
  }

  const issue = await response.json();
  return { url: issue.html_url };
}

function clientIp(event) {
  const headers = event.headers || {};
  const forwarded = headers["x-forwarded-for"] || headers["X-Forwarded-For"];
  if (!forwarded) return "unknown";
  return forwarded.split(",")[0].trim();
}

module.exports = { isHoneypotFilled, createRateLimiter, createGithubIssue, clientIp };
