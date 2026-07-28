"use strict";

const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

async function verifyTurnstile(token, remoteip) {
  const secret = process.env.TURNSTILE_SECRET_KEY;
  if (!secret) {
    throw new Error("TURNSTILE_SECRET_KEY is not configured");
  }
  if (!token) return false;

  const body = new URLSearchParams({ secret, response: token });
  if (remoteip && remoteip !== "unknown") {
    body.set("remoteip", remoteip);
  }

  try {
    const response = await fetch(VERIFY_URL, { method: "POST", body });
    if (!response.ok) return false;
    const data = await response.json();
    return Boolean(data && data.success);
  } catch (err) {
    // A captcha we cannot verify is a captcha we must not trust.
    console.error("turnstile: verification call failed", err);
    return false;
  }
}

module.exports = { verifyTurnstile };
