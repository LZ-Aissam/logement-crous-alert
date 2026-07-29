"""Process a GitHub Issue Form submission confirming an email address for a pending search."""
from __future__ import annotations

import json
import os
import sys

import check_logement as clog
from add_search import (
    PENDING_EXPIRY_MINUTES,
    PENDING_SEARCHES_PATH,
    hash_token,
    is_pending_expired,
    load_pending_searches,
    parse_issue_form_body,
    save_pending_searches,
)

FIELD_CODE = "Code de confirmation"


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)
    code = fields.get(FIELD_CODE)

    if not code:
        print("ERROR: code de confirmation manquant")
        return 1

    if PENDING_SEARCHES_PATH.exists():
        try:
            pending = load_pending_searches()
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: impossible de lire pending_searches.json existant : {exc}")
            return 1
    else:
        pending = {}
    code_hash = hash_token(code)

    for search_name, record in pending.items():
        pending_emails = record.get("pending_emails", {})
        if code_hash not in pending_emails:
            continue

        if is_pending_expired(record):
            del pending[search_name]
            save_pending_searches(pending)
            print(
                f"ERROR: ce lien de confirmation a expire ({PENDING_EXPIRY_MINUTES} minutes), "
                "resoumets une nouvelle demande."
            )
            return 1

        email = pending_emails.pop(code_hash)

        if clog.SEARCHES_PATH.exists():
            try:
                searches = clog.load_searches()
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                print(f"ERROR: impossible de lire searches.json existant : {exc}")
                return 1
        else:
            searches = []

        pending_url = record["search"]["url"]
        existing = next(
            (
                s
                for s in searches
                if s["name"].strip().lower() == search_name.strip().lower()
                and s["url"] == pending_url
            ),
            None,
        )
        if existing is not None:
            emails_list = existing.setdefault("emails", [])
            if email not in emails_list:
                emails_list.append(email)
        else:
            entry = dict(record["search"])
            entry["emails"] = [email]
            searches.append(entry)

        clog.save_searches(searches)

        if pending_emails:
            pending[search_name]["pending_emails"] = pending_emails
        else:
            del pending[search_name]
        save_pending_searches(pending)

        print(
            f"OK: email {email!r} confirme pour la recherche {search_name!r}. "
            "Cette recherche est maintenant active."
        )
        return 0

    print("ERROR: code de confirmation invalide ou deja utilise")
    return 1


if __name__ == "__main__":
    sys.exit(main())
