import json

import pytest

import check_logement as clog
import confirm_email as mod


def test_main_confirms_first_email_and_activates_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Agen": {
                    "search": {"name": "Agen", "url": "https://example.com/agen"},
                    "pending_emails": {"tok123": "a@example.com"},
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
                    "pending_emails": {"tok456": "b@example.com"},
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
                    "pending_emails": {"tok1": "a@example.com", "tok2": "b@example.com"},
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


def test_main_rejects_unknown_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pending_searches.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\nunknown-token\n")

    exit_code = mod.main()

    assert exit_code == 1


def test_main_requires_code(monkeypatch):
    monkeypatch.setenv("ISSUE_BODY", "### Code de confirmation\n\n_No response_\n")

    assert mod.main() == 1
