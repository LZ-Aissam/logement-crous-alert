import json

import check_logement as clog
import unsubscribe as mod


def _issue_body(search, email, token):
    return (
        f"### Nom de la recherche\n\n{search}\n\n"
        f"### Email\n\n{email}\n\n"
        f"### Jeton\n\n{token}\n"
    )


def test_main_removes_email_and_keeps_search_when_others_remain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Brest",
                    "url": "https://example.com/brest",
                    "emails": ["a@example.com", "b@example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}
    ]


def test_main_removes_search_entirely_when_last_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]},
                {"name": "Rennes", "url": "https://example.com/rennes", "emails": ["c@example.com"]},
            ]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == [
        {"name": "Rennes", "url": "https://example.com/rennes", "emails": ["c@example.com"]}
    ]


def test_main_rejects_invalid_token(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", "not-the-real-token"))

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com"]


def test_main_requires_all_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "_No response_", "sometoken"))

    assert mod.main() == 1


def test_main_requires_unsubscribe_secret_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", "sometoken"))

    assert mod.main() == 1


def test_main_noop_when_search_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_main_noop_when_email_not_subscribed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "stranger@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "stranger@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches[0]["emails"] == ["a@example.com"]


def test_main_deletes_search_when_no_emails_key_alert_email_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "owner@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("Brest", "owner@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []


def test_main_uses_email_ref_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["a@example.com"]}]
        ),
        encoding="utf-8",
    )
    ref = "e" * 32
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / f"{ref}.json").write_text(json.dumps({"email": "a@example.com"}), encoding="utf-8")
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    body = (
        f"### {mod.FIELD_SEARCH}\n\nBrest\n\n"
        f"### {mod.FIELD_EMAIL_REF}\n\n{ref}\n\n"
        f"### {mod.FIELD_TOKEN}\n\n{token}\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 0
    assert not (inbox / f"{ref}.json").exists()
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []


def test_main_rejects_missing_email_ref(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    body = (
        f"### {mod.FIELD_SEARCH}\n\nBrest\n\n"
        f"### {mod.FIELD_EMAIL_REF}\n\n{'f' * 32}\n\n"
        f"### {mod.FIELD_TOKEN}\n\nsometoken\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    assert mod.main() == 1


def test_main_is_case_insensitive_for_search_name_and_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "emails": ["A@Example.com"]}]
        ),
        encoding="utf-8",
    )
    token = clog.compute_unsubscribe_token("Brest", "a@example.com")
    monkeypatch.setenv("ISSUE_BODY", _issue_body("brest", "a@example.com", token))

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []
