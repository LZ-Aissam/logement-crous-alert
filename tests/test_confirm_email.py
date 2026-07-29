import json

import pytest

import check_logement as clog
import confirm_email as mod
from add_search import hash_token


def test_main_confirms_first_email_and_activates_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {hash_token("tok123"): "a@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Agen", "url": "https://example.com/agen", "emails": ["a@example.com"]}
    ]
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" not in pending


def test_main_confirms_second_email_appends_to_existing_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Agen", "url": "https://example.com/agen", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {hash_token("tok456"): "b@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok456\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com", "b@example.com"]
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" not in pending


def test_main_keeps_pending_entry_when_other_emails_remain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {
                        hash_token("tok1"): "a@example.com",
                        hash_token("tok2"): "b@example.com",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok1\n")

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert list(pending["Agen"]["pending_emails"].values()) == ["b@example.com"]


def test_main_does_not_attach_email_to_same_named_different_url_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # An unrelated "Agen" search already exists in searches.json, with a
    # different URL than the one the pending confirmation was requested for
    # (e.g. the owner created it by hand, or from a totally different request).
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Agen",
                    "url": "https://example.com/agen-OTHER",
                    "emails": ["owner@example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen-PENDING"},
                    "pending_emails": {hash_token("tok123"): "stranger@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    # The pre-existing, unrelated "Agen" entry must be untouched.
    other = next(s for s in searches if s["url"] == "https://example.com/agen-OTHER")
    assert other["emails"] == ["owner@example.com"]
    # A separate entry must have been created for the pending record's own url,
    # instead of silently appending the stranger's email to the wrong search.
    matched = next(s for s in searches if s["url"] == "https://example.com/agen-PENDING")
    assert matched["emails"] == ["stranger@example.com"]


def test_main_rejects_unknown_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pending_searches.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\nunknown-token\n")

    exit_code = mod.main()

    assert exit_code == 1


def test_main_rejects_expired_pending_code(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    old_created_at = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {hash_token("tok123"): "a@example.com"},
                    "created_at": old_created_at,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" not in pending, "expired entry should have been pruned"


def test_main_confirms_within_expiry_window(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    fresh_created_at = datetime.now(timezone.utc).isoformat()
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {hash_token("tok123"): "a@example.com"},
                    "created_at": fresh_created_at,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Agen", "url": "https://example.com/agen", "emails": ["a@example.com"]}
    ]


def test_main_requires_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\n_No response_\n")

    assert mod.main() == 1


def test_main_aborts_on_invalid_existing_pending_searches_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original_content = '{"not": "valid pending data"'
    (tmp_path / "pending_searches.json").write_text(original_content, encoding="utf-8")
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\ntok123\n")

    exit_code = mod.main()

    assert exit_code == 1
    assert (tmp_path / "pending_searches.json").read_text(encoding="utf-8") == original_content


def test_confirmation_requires_original_token_not_stored_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    raw_token = "super-secret-raw-token"
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {hash_token(raw_token): "a@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    # Submitting the STORED HASH (what an attacker could read from the public repo)
    # must NOT work -- only the original raw token does.
    monkeypatch.setenv("ISSUE_BODY", f"### Code de confirmation\n\n{hash_token(raw_token)}\n")
    assert mod.main() == 1

    # Submitting the actual raw token (only known to whoever received the real email)
    # must work.
    monkeypatch.setenv("ISSUE_BODY", f"### Code de confirmation\n\n{raw_token}\n")
    assert mod.main() == 0
