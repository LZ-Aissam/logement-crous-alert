"""Process a GitHub Issue Form submission confirming an email address for a pending search."""
from __future__ import annotations

import json
import os
import sys

import check_logement as clog
from add_search import (
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

    pending = load_pending_searches()

    for search_name, record in pending.items():
        pending_emails = record.get("pending_emails", {})
        if code not in pending_emails:
            continue

        email = pending_emails.pop(code)

        if clog.SEARCHES_PATH.exists():
            try:
                searches = clog.load_searches()
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                print(f"ERROR: impossible de lire searches.json existant : {exc}")
                return 1
        else:
            searches = []

        existing = next(
            (
                s
                for s in searches
                if s["name"].strip().lower() == search_name.strip().lower()
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
