"""Poll CROUS housing searches and email alerts when new listings appear."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import smtplib
import sys
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

SEARCH_DATA_URL = "/api/fr/search/47"
FETCH_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; logement-alert-bot/1.0)"

# HTML email styling -- matches the site's real CROUS Rennes palette
# (public/styles.css) so alerts feel like the same product as the website.
EMAIL_FONT = "'Segoe UI', Helvetica, Arial, sans-serif"
EMAIL_ACCENT = {
    "alert": "#e01020",
    "confirm": "#006a6f",
    "health": "#e01020",
    "recovery": "#34c4b5",
}
EMAIL_FOOTER_NOTE = {
    "alert": "Scanne toutes les 5 minutes, sans cafe ni pause dejeuner.",
    "confirm": "Un clic suffit, aucun mot de passe a retenir ni a oublier.",
    "health": "Un bot qui s'auto-surveille, ca aide a dormir tranquille.",
    "recovery": "Tout est rentre dans l'ordre, le bot peut souffler.",
}

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
SEARCHES_PATH = DATA_DIR / "searches.json"
SEEN_PATH = DATA_DIR / "seen.json"
FAILURES_PATH = DATA_DIR / "failures.json"
INBOX_DIR = DATA_DIR / "inbox"

# Number of consecutive check failures for a search before a health alert email is
# sent to MAINTAINER_EMAIL -- avoids alerting on a single transient network blip.
FAILURE_ALERT_THRESHOLD = 3

_INBOX_REF_RE = re.compile(r"^[0-9a-f]{32}$")


def mask_email(email: str) -> str:
    """Redacts an email for safe inclusion in output that ends up in a public GitHub
    issue comment or Actions log (e.g. "a***@example.com")."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[:1] or '*'}***@{domain}"


def read_inbox_email(ref: str | None) -> str | None:
    """Reads and deletes a one-time email payload staged by a Netlify function in the
    private data repo's inbox/ -- keeps the raw address out of the public issue body
    that triggers this workflow. Returns None if ref is missing/malformed or the file
    doesn't exist/isn't valid JSON."""
    if not ref or not _INBOX_REF_RE.match(ref.strip()):
        return None
    path = INBOX_DIR / f"{ref.strip()}.json"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    email = data.get("email") if isinstance(data, dict) else None
    path.unlink(missing_ok=True)
    return email if isinstance(email, str) and email else None


class SearchFetchError(Exception):
    """Raised when a search page cannot be fetched or parsed."""


def fetch_html(url: str) -> str:
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT
        )
    except requests.RequestException as exc:
        raise SearchFetchError(f"network error fetching {url}: {exc}") from exc
    if response.status_code != 200:
        raise SearchFetchError(
            f"unexpected status {response.status_code} fetching {url}"
        )
    return response.text


_SCRIPT_RE = re.compile(
    r'data-url="' + re.escape(SEARCH_DATA_URL) + r'"[^>]*>(\{.*?\})</script>',
    re.S,
)


def parse_search_results(html: str) -> dict[str, Any]:
    match = _SCRIPT_RE.search(html)
    if not match:
        raise SearchFetchError(
            f"could not find embedded search data ({SEARCH_DATA_URL}) in page"
        )
    try:
        outer = json.loads(match.group(1))
        body = json.loads(outer["body"])
        return body["results"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise SearchFetchError(f"could not parse embedded search data: {exc}") from exc


def load_seen(path: Path = SEEN_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(
            f"[ERROR] corrupt JSON in {path}, falling back to empty state: {exc}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"[ERROR] unexpected JSON shape in {path} (expected an object), "
            "falling back to empty state",
            file=sys.stderr,
        )
        return {}
    return data


def save_seen(seen: dict[str, list[str]], path: Path = SEEN_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def load_failures(path: Path = FAILURES_PATH) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(
            f"[ERROR] corrupt JSON in {path}, falling back to empty state: {exc}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"[ERROR] unexpected JSON shape in {path} (expected an object), "
            "falling back to empty state",
            file=sys.stderr,
        )
        return {}
    return data


def save_failures(failures: dict[str, int], path: Path = FAILURES_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(failures, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def _send_health_alert(
    to_email: str,
    failing: list[tuple[str, str]],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
) -> None:
    lines = [
        f"{len(failing)} recherche(s) en echec depuis {FAILURE_ALERT_THRESHOLD} "
        "verifications consecutives :",
        "",
    ]
    for name, error in failing:
        lines.append(f"- {name} : {error}")
    lines.append("")
    lines.append("Verifie l'onglet Actions du depot pour plus de details.")
    subject = f"[Logement][ALERTE] {len(failing)} recherche(s) en echec"
    html_lines = [f"{len(failing)} recherche(s) en echec depuis {FAILURE_ALERT_THRESHOLD} verifications consecutives :"]
    html_lines += [f"<strong>{name}</strong> : {error}" for name, error in failing]
    html_lines.append("Verifie l'onglet Actions du depot pour plus de details.")
    html_body = render_email_html("health", "Alerte", _html_paragraphs(html_lines))
    try:
        send_email(
            subject, "\n".join(lines), [to_email], smtp_host, smtp_port, smtp_user, smtp_password, from_email,
            html_body=html_body,
        )
    except Exception as exc:
        print(f"[ERROR] failed to send health alert: {exc}", file=sys.stderr)


def _send_recovery_notice(
    to_email: str,
    recovered: list[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
) -> None:
    lines = [f"{len(recovered)} recherche(s) retablie(s) :", ""]
    for name in recovered:
        lines.append(f"- {name}")
    subject = f"[Logement] {len(recovered)} recherche(s) retablie(s)"
    html_lines = [f"{len(recovered)} recherche(s) retablie(s) :"]
    html_lines += [f"<strong>{name}</strong>" for name in recovered]
    html_body = render_email_html("recovery", "Retour a la normale", _html_paragraphs(html_lines))
    try:
        send_email(
            subject, "\n".join(lines), [to_email], smtp_host, smtp_port, smtp_user, smtp_password, from_email,
            html_body=html_body,
        )
    except Exception as exc:
        print(f"[ERROR] failed to send recovery notice: {exc}", file=sys.stderr)


def compute_unsubscribe_token(search_name: str, email: str) -> str | None:
    secret = os.environ.get("UNSUBSCRIBE_SECRET")
    if not secret:
        return None
    return hmac.new(
        secret.encode("utf-8"),
        f"{search_name}|{email.lower()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_unsubscribe_url(
    search_name: str,
    email: str,
    city: str | None = None,
    keywords: list[str] | None = None,
    max_price: int | None = None,
    min_area: int | None = None,
    occupation_modes: list[str] | None = None,
    prm: bool = False,
    equipments: list[str] | None = None,
) -> str | None:
    token = compute_unsubscribe_token(search_name, email)
    if token is None:
        return None
    query = (
        f"search={urllib.parse.quote(search_name)}"
        f"&email={urllib.parse.quote(email)}"
        f"&token={token}"
    )
    if city:
        query += f"&city={urllib.parse.quote(city)}"
    if keywords:
        query += f"&keywords={urllib.parse.quote(', '.join(keywords))}"
    if max_price:
        query += f"&maxPrice={max_price}"
    if min_area:
        query += f"&minArea={min_area}"
    if occupation_modes:
        query += f"&occupationModes={urllib.parse.quote(','.join(occupation_modes))}"
    if prm:
        query += "&prm=1"
    if equipments:
        query += f"&equipments={urllib.parse.quote(','.join(equipments))}"
    base_url = os.environ.get("UNSUBSCRIBE_BASE_URL")
    if base_url:
        return f"{base_url}?{query}"
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    return f"https://github.com/{repo}/issues/new?template=unsubscribe.yml&{query}"


def find_new_items(
    items: list[dict[str, Any]], seen_ids: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    seen_set = set(seen_ids)
    new_items = [item for item in items if str(item["id"]) not in seen_set]
    all_ids = sorted({str(item["id"]) for item in items})
    return new_items, all_ids


def load_searches(path: Path = SEARCHES_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        searches = json.load(f)
    if not isinstance(searches, list):
        raise ValueError(
            f"{path} must contain a JSON list of search objects, "
            f"got {type(searches).__name__}"
        )
    for search in searches:
        if not isinstance(search, dict) or "name" not in search or "url" not in search:
            raise ValueError(f"invalid search entry, missing name/url: {search}")
    return searches


def save_searches(searches: list[dict[str, Any]], path: Path = SEARCHES_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(searches, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _item_matches_keywords(item: dict[str, Any], keywords: list[str] | None) -> bool:
    if not keywords:
        return True
    residence = item.get("residence") or {}
    haystack = " ".join(
        str(x)
        for x in [
            item.get("label") or "",
            residence.get("label") or "",
            residence.get("address") or "",
        ]
    ).lower()
    return any(kw.strip().lower() in haystack for kw in keywords if kw.strip())


def _format_rent(item: dict[str, Any]) -> str:
    # The monthly rent lives in occupationModes[].rent (cents), not bookingData.amount
    # -- bookingData.amount is the deductible advance on the first month's rent, a
    # different, smaller figure that was mistakenly displayed as "the rent" before.
    modes = item.get("occupationModes") or []
    mode = next((m for m in modes if m.get("type") == "alone"), None)
    if mode is None and modes:
        mode = modes[0]
    rent = (mode or {}).get("rent") or {}
    rent_min = rent.get("min")
    rent_max = rent.get("max")
    if rent_min is None:
        return "loyer non precise"
    if rent_max is not None and rent_max != rent_min:
        return f"{rent_min / 100:.2f} - {rent_max / 100:.2f} EUR/mois"
    return f"{rent_min / 100:.2f} EUR/mois"


def format_email_body(
    search_name: str,
    new_items: list[dict[str, Any]],
    search_url: str,
    unsubscribe_url: str | None = None,
) -> str:
    lines = [
        f'{len(new_items)} nouveau(x) logement(s) pour la recherche "{search_name}" :',
        "",
    ]
    for item in new_items:
        residence = item.get("residence") or {}
        label = item.get("label", "(sans libelle)")
        address = residence.get("address", "(adresse inconnue)")
        rent_str = _format_rent(item)
        lines.append(f"- {label} - {residence.get('label', '')} - {address} - {rent_str}")
    lines.append("")
    lines.append(f"Voir la recherche : {search_url}")
    if unsubscribe_url:
        lines.append("")
        lines.append(f"Pour ne plus recevoir ces alertes : {unsubscribe_url}")
    return "\n".join(lines)


def _html_paragraphs(lines: list[str]) -> str:
    return "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#16191b;">{line}</p>'
        for line in lines
    )


def render_email_html(
    kind: str,
    title: str,
    body_html: str,
    cta_url: str | None = None,
    cta_label: str | None = None,
) -> str:
    """Wrap body_html in the site's branded email shell (table-based layout with
    inline styles, since most email clients strip <style> blocks and webfonts)."""
    accent = EMAIL_ACCENT.get(kind, "#e01020")
    footer_note = EMAIL_FOOTER_NOTE.get(kind, "")
    cta_html = ""
    if cta_url and cta_label:
        cta_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 6px;">'
            f'<tr><td style="border-radius:999px;background:{accent};">'
            f'<a href="{cta_url}" style="display:inline-block;padding:12px 26px;'
            f"font-family:{EMAIL_FONT};font-weight:700;font-size:15px;color:#ffffff;"
            f'text-decoration:none;border-radius:999px;">{cta_label}</a>'
            "</td></tr></table>"
        )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#e8e8e8;font-family:{EMAIL_FONT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8e8e8;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:20px;overflow:hidden;">
<tr><td style="background:{accent};padding:18px 28px;">
<span style="font-family:{EMAIL_FONT};font-weight:700;font-size:18px;color:#ffffff;">Alerte Logement CROUS</span>
</td></tr>
<tr><td style="padding:28px;">
<span style="display:inline-block;border:2px solid {accent};color:{accent};font-family:{EMAIL_FONT};font-weight:700;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;padding:4px 12px;border-radius:999px;margin-bottom:16px;">{title}</span>
{body_html}
{cta_html}
</td></tr>
<tr><td style="padding:16px 28px;background:#f4f4f4;border-top:1px solid #e0e0e0;">
<p style="margin:0;font-size:12px;color:#6b6b6b;line-height:1.5;font-family:{EMAIL_FONT};">{footer_note}</p>
<p style="margin:6px 0 0;font-size:11px;color:#9a9a9a;font-family:{EMAIL_FONT};">Alerte Logement CROUS -- projet independant, non affilie au CROUS.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def format_email_html(
    search_name: str,
    new_items: list[dict[str, Any]],
    search_url: str,
    unsubscribe_url: str | None = None,
) -> str:
    rows = []
    for item in new_items:
        residence = item.get("residence") or {}
        label = item.get("label") or "(sans libelle)"
        residence_label = residence.get("label") or ""
        address = residence.get("address") or "(adresse inconnue)"
        rent_str = _format_rent(item)
        heading = f"{label} - {residence_label}" if residence_label else label
        rows.append(
            '<div style="border:1px solid #e0e0e0;border-radius:12px;padding:12px 16px;margin:0 0 10px;">'
            f'<div style="font-weight:700;font-size:14px;color:#16191b;">{heading}</div>'
            f'<div style="font-size:13px;color:#555555;margin-top:2px;">{address}</div>'
            f'<div style="font-size:13px;color:#e01020;font-weight:600;margin-top:4px;">{rent_str}</div>'
            "</div>"
        )
    intro = _html_paragraphs(
        [f'{len(new_items)} nouveau(x) logement(s) pour la recherche <strong>{search_name}</strong> :']
    )
    outro_lines = [f'<a href="{search_url}" style="color:#006a6f;">Voir la recherche complete</a>']
    if unsubscribe_url:
        outro_lines.append(
            f'<a href="{unsubscribe_url}" style="color:#9a9a9a;font-size:13px;">'
            "Ne plus recevoir ces alertes</a>"
        )
    outro = _html_paragraphs(outro_lines)
    body_html = intro + "".join(rows) + outro
    return render_email_html("alert", f"{len(new_items)} nouveau(x)", body_html)


def send_email(
    subject: str,
    body: str,
    to_addrs: list[str],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
    html_body: str | None = None,
) -> None:
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_addrs)
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=FETCH_TIMEOUT) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_addrs, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=FETCH_TIMEOUT) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, to_addrs, msg.as_string())


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERROR] missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> int:
    smtp_host = _require_env("SMTP_HOST")
    smtp_port = int(_require_env("SMTP_PORT"))
    smtp_user = _require_env("SMTP_USER")
    smtp_password = _require_env("SMTP_PASSWORD")
    from_email = _require_env("FROM_EMAIL")

    try:
        searches = load_searches()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[ERROR] could not load searches.json: {exc}", file=sys.stderr)
        return 1

    seen = load_seen()
    failures = load_failures()
    maintainer_email = os.environ.get("MAINTAINER_EMAIL")
    newly_failing: list[tuple[str, str]] = []
    newly_recovered: list[str] = []
    any_success = False

    for search in searches:
        name = search["name"]
        url = search["url"]
        recipients = search.get("emails") or []
        if not recipients:
            print(
                f"[ERROR] {name}: aucun destinataire, recherche ignoree",
                file=sys.stderr,
            )
            continue

        try:
            html = fetch_html(url)
            results = parse_search_results(html)
            items = results.get("items") or []
            items = [i for i in items if _item_matches_keywords(i, search.get("keywords"))]
            seen_ids = seen.get(name, [])
            new_items, all_ids = find_new_items(items, seen_ids)
            if new_items:
                subject = f"[Logement] {len(new_items)} nouveau(x) pour {name}"
        except (SearchFetchError, KeyError, TypeError, AttributeError) as exc:
            print(f"[ERROR] {name}: {exc}", file=sys.stderr)
            failures[name] = failures.get(name, 0) + 1
            if failures[name] == FAILURE_ALERT_THRESHOLD:
                newly_failing.append((name, str(exc)))
            continue

        any_success = True

        if failures.get(name, 0) >= FAILURE_ALERT_THRESHOLD:
            newly_recovered.append(name)
        failures.pop(name, None)

        if new_items:
            sent_count = 0
            for recipient in recipients:
                criteria = search.get("criteria") or {}
                unsubscribe_url = build_unsubscribe_url(
                    name,
                    recipient,
                    city=criteria.get("city"),
                    keywords=search.get("keywords"),
                    max_price=criteria.get("maxPrice"),
                    min_area=criteria.get("minArea"),
                    occupation_modes=criteria.get("occupationModes"),
                    prm=criteria.get("prm", False),
                    equipments=criteria.get("equipments"),
                )
                try:
                    body = format_email_body(name, new_items, url, unsubscribe_url)
                    html = format_email_html(name, new_items, url, unsubscribe_url)
                    send_email(
                        subject, body, [recipient],
                        smtp_host, smtp_port, smtp_user, smtp_password, from_email,
                        html_body=html,
                    )
                except Exception as exc:
                    print(
                        f"[ERROR] {name}: failed to send email to {mask_email(recipient)}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                sent_count += 1
            if sent_count == 0:
                print(f"[ERROR] {name}: failed to send alert to any recipient", file=sys.stderr)
                continue
            print(f"[OK] {name}: sent alert for {len(new_items)} new listing(s) to {sent_count} recipient(s)")
        else:
            print(f"[OK] {name}: no new listings ({len(items)} total)")

        seen[name] = sorted(set(seen_ids) | set(all_ids))

    if any_success:
        save_seen(seen)
    save_failures(failures)

    if maintainer_email:
        if newly_failing:
            _send_health_alert(maintainer_email, newly_failing, smtp_host, smtp_port, smtp_user, smtp_password, from_email)
        if newly_recovered:
            _send_recovery_notice(maintainer_email, newly_recovered, smtp_host, smtp_port, smtp_user, smtp_password, from_email)

    return 0 if any_success else 1


if __name__ == "__main__":
    sys.exit(main())
