import json
import requests
import pytest
from email import message_from_string

import check_logement as mod


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def test_fetch_html_returns_text_on_200(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert "example.com" in url
        return _FakeResponse(200, "<html>ok</html>")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_html("https://example.com/search") == "<html>ok</html>"


def test_fetch_html_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse(500, ""))
    with pytest.raises(mod.SearchFetchError):
        mod.fetch_html("https://example.com/search")


def test_fetch_html_raises_on_network_error(monkeypatch):
    def fake_get(*a, **k):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    with pytest.raises(mod.SearchFetchError):
        mod.fetch_html("https://example.com/search")


def _make_fixture_html(total, items):
    body_obj = {
        "results": {
            "total": {"value": total, "relation": "eq"},
            "page": 0,
            "pageSize": 24,
            "items": items,
        }
    }
    outer = {
        "status": 200,
        "statusText": "OK",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body_obj),
    }
    return (
        '<html><body><script type="application/json" data-sveltekit-fetched '
        f'data-url="/api/fr/search/47" data-hash="abc">{json.dumps(outer)}</script>'
        "</body></html>"
    )


def test_parse_search_results_extracts_items():
    html = _make_fixture_html(2, [{"id": 1}, {"id": 2}])
    results = mod.parse_search_results(html)
    assert results["total"]["value"] == 2
    assert [item["id"] for item in results["items"]] == [1, 2]


def test_parse_search_results_raises_when_block_missing():
    with pytest.raises(mod.SearchFetchError):
        mod.parse_search_results("<html><body>nothing here</body></html>")


def test_parse_search_results_raises_on_malformed_json():
    broken = (
        '<html><body><script type="application/json" data-sveltekit-fetched '
        'data-url="/api/fr/search/47" data-hash="abc">{not json}</script></body></html>'
    )
    with pytest.raises(mod.SearchFetchError):
        mod.parse_search_results(broken)


def test_load_seen_returns_empty_dict_when_missing(tmp_path):
    missing = tmp_path / "seen.json"
    assert mod.load_seen(missing) == {}


def test_save_then_load_seen_round_trips(tmp_path):
    path = tmp_path / "seen.json"
    mod.save_seen({"Brest": ["1", "2"]}, path)
    assert mod.load_seen(path) == {"Brest": ["1", "2"]}


def test_load_seen_returns_empty_dict_on_corrupt_json(tmp_path, capsys):
    path = tmp_path / "seen.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert mod.load_seen(path) == {}
    # Verify error message was printed to stderr
    captured = capsys.readouterr()
    assert captured.err
    assert "corrupt JSON" in captured.err
    assert str(path) in captured.err


def test_load_seen_returns_empty_dict_on_wrong_shape(tmp_path, capsys):
    path = tmp_path / "seen.json"
    path.write_text("[]", encoding="utf-8")
    assert mod.load_seen(path) == {}
    captured = capsys.readouterr()
    assert captured.err
    assert str(path) in captured.err


def test_find_new_items_first_run_all_new():
    items = [{"id": 1}, {"id": 2}]
    new_items, all_ids = mod.find_new_items(items, [])
    assert new_items == items
    assert all_ids == ["1", "2"]


def test_find_new_items_only_returns_unseen():
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    new_items, all_ids = mod.find_new_items(items, ["1", "2"])
    assert new_items == [{"id": 3}]
    assert all_ids == ["1", "2", "3"]


def test_find_new_items_no_items_no_new():
    new_items, all_ids = mod.find_new_items([], ["1"])
    assert new_items == []
    assert all_ids == []


def test_load_searches_reads_valid_list(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    searches = mod.load_searches(path)
    assert searches == [{"name": "Brest", "url": "https://example.com/brest"}]


def test_load_searches_rejects_entry_missing_name(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(json.dumps([{"url": "https://example.com/brest"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_searches(path)


def test_load_searches_rejects_entry_missing_url(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(json.dumps([{"name": "Brest"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_searches(path)


def test_load_searches_rejects_top_level_object(tmp_path):
    path = tmp_path / "searches.json"
    path.write_text(json.dumps({"name": "Brest", "url": "https://example.com/brest"}), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_searches(path)


def test_save_searches_writes_valid_json_list(tmp_path):
    path = tmp_path / "searches.json"
    entries = [{"name": "Brest", "url": "https://example.com/brest"}]
    mod.save_searches(entries, path)
    assert json.loads(path.read_text(encoding="utf-8")) == entries


def test_format_email_body_includes_listing_details():
    # occupationModes[].rent (cents) is the real monthly rent, verified against the
    # live site: a real Agen listing had rent.min == rent.max == 41555 (415,55 EUR/mois)
    # matching exactly what the site's own listing page displayed as "Individuel".
    new_items = [
        {
            "label": "T1 meuble",
            "residence": {"label": "Residence Foo", "address": "1 rue Test, 29200 Brest"},
            "occupationModes": [{"type": "alone", "rent": {"min": 25000, "max": 25000}}],
        }
    ]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "Brest" in body
    assert "T1 meuble" in body
    assert "Residence Foo" in body
    assert "1 rue Test, 29200 Brest" in body
    assert "250.00" in body
    assert "https://example.com/search" in body


def test_format_email_body_handles_rent_range():
    new_items = [
        {
            "label": "T1",
            "residence": {"label": "R", "address": "A"},
            "occupationModes": [{"type": "alone", "rent": {"min": 25000, "max": 27000}}],
        }
    ]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "250.00 - 270.00 EUR/mois" in body


def test_format_email_body_ignores_booking_data_deposit_not_rent():
    # bookingData.amount is the deductible advance on the first month's rent (a
    # deposit-like figure), NOT the monthly rent -- it must never be shown as "loyer".
    new_items = [
        {
            "label": "T1",
            "residence": {"label": "R", "address": "A"},
            "bookingData": {"amount": 7000},
            "occupationModes": [{"type": "alone", "rent": {"min": 41555, "max": 41555}}],
        }
    ]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "415.55" in body
    assert "70.00" not in body


def test_format_email_body_handles_missing_rent():
    new_items = [{"label": "Chambre", "residence": {"label": "R", "address": "A"}}]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "non pr" in body  # "loyer non précisé"


def test_format_email_body_handles_null_residence_and_booking_data():
    # residence key is present but explicitly null (JSON null -> None), not merely
    # absent -- must not raise AttributeError from calling .get() on None.
    new_items = [{"label": "T1", "residence": None, "occupationModes": None}]
    body = mod.format_email_body("Brest", new_items, "https://example.com/search")
    assert "T1" in body
    assert "non pr" in body  # "loyer non précisé" fallback for missing rent


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent = (from_addr, to_addrs, msg)


def test_send_email_logs_in_and_sends(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP_SSL", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com", "b@example.com"],
        smtp_user="me@gmail.com",
        smtp_password="app-password",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 465
    assert smtp.logged_in == ("me@gmail.com", "app-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "me@gmail.com"
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert "Subject" in msg
    # Decode the message properly to verify actual body content
    msg_obj = message_from_string(msg)
    decoded_body = msg_obj.get_payload(decode=True).decode("utf-8")
    assert "Body text" in decoded_body


def test_main_sends_email_for_new_listings_and_updates_seen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["x@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(
            (subject, to_addrs)
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert sent == [(sent[0][0], ["x@example.com"])]
    assert "Brest" in sent[0][0]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


def test_main_email_send_failure_does_not_block_others_or_mark_seen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Rennes", "url": "https://example.com/rennes"},
                {"name": "Brest", "url": "https://example.com/brest"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )

    def fake_send_email(subject, body, to_addrs, smtp_user, smtp_password):
        if "Rennes" in subject:
            raise mod.smtplib.SMTPException("boom")

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


def test_main_no_new_listings_sends_no_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text(json.dumps({"Brest": ["1"]}), encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    monkeypatch.setattr(
        mod, "send_email", lambda *a, **k: pytest.fail("should not send email")
    )

    assert mod.main() == 0


def test_main_broken_search_does_not_block_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Broken", "url": "https://example.com/broken"},
                {"name": "Brest", "url": "https://example.com/brest"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    def fake_fetch(url):
        if "broken" in url:
            raise mod.SearchFetchError("boom")
        return "<fake html>"

    monkeypatch.setattr(mod, "fetch_html", fake_fetch)
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 0}, "items": []},
    )
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: None)

    assert mod.main() == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": []}


def test_main_shape_drift_isolates_broken_search(tmp_path, monkeypatch):
    # parse_search_results itself succeeds (doesn't raise SearchFetchError), but the
    # data it hands back is malformed for "Broken" (item missing its "id" key), which
    # would previously crash find_new_items/format_email_body and abort the whole run.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Broken", "url": "https://example.com/broken"},
                {"name": "Brest", "url": "https://example.com/brest"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: url)

    def fake_parse(html):
        if "broken" in html:
            return {"total": {"value": 1}, "items": [{"label": "T1"}]}  # missing "id"
        return {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]}

    monkeypatch.setattr(mod, "parse_search_results", fake_parse)
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: None)

    exit_code = mod.main()

    assert exit_code == 0  # Brest still succeeds despite Broken's shape drift
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}
    assert "Broken" not in seen


def test_main_unions_seen_ids_instead_of_replacing(tmp_path, monkeypatch):
    # A previously-seen id ("99") that no longer appears in this run's results (e.g. it
    # scrolled past page 1) must be preserved, unioned with the newly-seen id, not lost.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text(json.dumps({"Brest": ["99"]}), encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: None)

    exit_code = mod.main()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1", "99"]}


def test_main_all_searches_fail_returns_error_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    def fake_fetch(url):
        raise mod.SearchFetchError("boom")

    monkeypatch.setattr(mod, "fetch_html", fake_fetch)
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: pytest.fail("should not send email"))

    assert mod.main() == 1
    assert not (tmp_path / "seen.json").exists() or json.loads(
        (tmp_path / "seen.json").read_text(encoding="utf-8")
    ) == {}


def test_main_malformed_searches_json_returns_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        '[{"name": "Brest", "url": "https://example.com/brest",}]',  # trailing comma
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    assert mod.main() == 1
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "searches.json" in captured.err


def test_main_uses_alert_email_default_when_search_has_no_emails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    captured_to_addrs = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: captured_to_addrs.append(
            to_addrs
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert captured_to_addrs == [["default@example.com"]]


def test_main_missing_env_var_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("ALERT_EMAIL", raising=False)

    with pytest.raises(SystemExit):
        mod.main()


def test_item_matches_keywords_no_keywords_matches_everything():
    assert mod._item_matches_keywords({"label": "T1"}, None) is True
    assert mod._item_matches_keywords({"label": "T1"}, []) is True


def test_item_matches_keywords_matches_residence_label():
    item = {"label": "T1", "residence": {"label": "Kergoat", "address": "1 rue X"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is True


def test_item_matches_keywords_matches_item_label():
    item = {"label": "Studio meuble", "residence": {"label": "R", "address": "A"}}
    assert mod._item_matches_keywords(item, ["studio"]) is True


def test_item_matches_keywords_matches_address():
    item = {"label": "T1", "residence": {"label": "R", "address": "5 rue de Kergoat"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is True


def test_item_matches_keywords_no_match_returns_false():
    item = {"label": "T1", "residence": {"label": "Foo", "address": "Bar"}}
    assert mod._item_matches_keywords(item, ["kergoat"]) is False


def test_item_matches_keywords_case_insensitive_and_any_of_multiple():
    item = {"label": "CHAMBRE", "residence": {"label": "Foo", "address": "Bar"}}
    assert mod._item_matches_keywords(item, ["Kergoat", "chambre"]) is True


def test_main_filters_items_by_keywords(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [{"name": "Brest", "url": "https://example.com/brest", "keywords": ["kergoat"]}]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL", "default@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {
            "total": {"value": 2},
            "items": [
                {"id": 1, "label": "T1", "residence": {"label": "Kergoat", "address": "A"}},
                {"id": 2, "label": "T1", "residence": {"label": "Autre", "address": "B"}},
            ],
        },
    )
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(body),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert len(sent) == 1
    assert "Kergoat" in sent[0]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}
