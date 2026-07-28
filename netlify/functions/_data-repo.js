"use strict";

const DEFAULT_DATA_REPO = "LZ-Aissam/logement-crous-alert-data";

async function readDataFile(path, fallback) {
  const token = process.env.DATA_REPO_PAT;
  if (!token) {
    throw new Error("DATA_REPO_PAT is not configured");
  }
  const repo = process.env.DATA_REPO || DEFAULT_DATA_REPO;
  const response = await fetch(`https://api.github.com/repos/${repo}/contents/${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      // raw+json returns the file body directly, avoiding a base64 round-trip
      Accept: "application/vnd.github.raw+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (response.status === 404) return fallback;
  if (!response.ok) {
    throw new Error(`GitHub API error ${response.status} reading ${path}`);
  }
  return JSON.parse(await response.text());
}

module.exports = { readDataFile };
