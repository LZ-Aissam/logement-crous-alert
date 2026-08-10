"""Process a GitHub Issue Form submission unsubscribing an email from a search."""
from __future__ import annotations

import hmac
import json
import os
import sys

import check_logement as clog
from add_search import parse_issue_form_body

FIELD_SEARCH = "Nom de la recherche"
FIELD_EMAIL = "Email"
# Set by the Netlify function instead of FIELD_EMAIL: points to a one-time payload in
# the private data repo's inbox/, keeping the raw address out of this public issue. A
# manually-submitted GitHub Issue has no way to set this and falls back to FIELD_EMAIL
# directly, unavoidably public in that path.
FIELD_EMAIL_REF = "Référence email (dépôt privé)"
FIELD_TOKEN = "Jeton"


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    fields = parse_issue_form_body(issue_body)
    search_name = fields.get(FIELD_SEARCH)
    email_ref = fields.get(FIELD_EMAIL_REF)
    email = clog.read_inbox_email(email_ref) if email_ref else fields.get(FIELD_EMAIL)
    token = fields.get(FIELD_TOKEN)

    if not search_name or not email or not token:
        print("ERROR: nom de la recherche, email et jeton sont obligatoires")
        return 1

    secret = os.environ.get("UNSUBSCRIBE_SECRET")
    if not secret:
        print("ERROR: UNSUBSCRIBE_SECRET n'est pas configure sur ce depot")
        return 1

    if not clog.SEARCHES_PATH.exists():
        print(f"OK: recherche {search_name!r} introuvable, rien a faire")
        return 0

    try:
        searches = clog.load_searches()
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: impossible de lire searches.json existant : {exc}")
        return 1

    target = next(
        (s for s in searches if s["name"].strip().lower() == search_name.strip().lower()),
        None,
    )
    if target is None:
        print(f"OK: recherche {search_name!r} introuvable, deja desinscrite ou supprimee")
        return 0

    # Compute the expected token using the stored search name (for case-insensitive matching)
    expected = clog.compute_unsubscribe_token(target["name"], email)

    if not hmac.compare_digest(expected.encode(), token.strip().encode()):
        print("ERROR: jeton de desinscription invalide")
        return 1

    if not target.get("emails"):
        # No explicit "emails" list. Since every search now requires a recipient, such
        # an entry is a data anomaly rather than a supported case. A valid token proves
        # the requester was a recipient, so removing the whole search is the right cleanup.
        searches = [s for s in searches if s is not target]
        clog.save_searches(searches)
        print(
            f"OK: {clog.mask_email(email)} desinscrit de {search_name!r}. "
            "C'etait le dernier destinataire, la recherche a ete supprimee."
        )
        return 0

    emails = target["emails"]
    remaining = [e for e in emails if e.strip().lower() != email.strip().lower()]

    if len(remaining) == len(emails):
        print(f"OK: {clog.mask_email(email)} n'etait pas destinataire de {search_name!r}, rien a faire")
        return 0

    if remaining:
        target["emails"] = remaining
        clog.save_searches(searches)
        print(
            f"OK: {clog.mask_email(email)} desinscrit de {search_name!r}. "
            "La recherche continue pour les autres destinataires."
        )
    else:
        searches = [s for s in searches if s is not target]
        clog.save_searches(searches)
        print(
            f"OK: {clog.mask_email(email)} desinscrit de {search_name!r}. "
            "C'etait le dernier destinataire, la recherche a ete supprimee."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
