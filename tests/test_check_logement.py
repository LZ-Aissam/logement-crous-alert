import json
import requests
import pytest
from email import message_from_string
from pathlib import Path

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


def test_render_email_html_includes_title_body_and_accent_color():
    html = mod.render_email_html("alert", "3 nouveaux logements", "<p>Ligne un</p>")
    assert "3 nouveaux logements" in html
    assert "Ligne un" in html
    assert mod.EMAIL_ACCENT["alert"] in html


def test_render_email_html_includes_cta_link_when_given():
    html = mod.render_email_html(
        "confirm", "Titre", "<p>Texte</p>",
        cta_url="https://example.com/confirmer", cta_label="Confirmer mon adresse",
    )
    assert 'href="https://example.com/confirmer"' in html
    assert "Confirmer mon adresse" in html


def test_render_email_html_omits_cta_when_not_given():
    html = mod.render_email_html("alert", "Titre", "<p>Texte</p>")
    assert "<a href=" not in html


def test_format_email_html_includes_listing_details():
    new_items = [
        {
            "label": "T1 meuble",
            "residence": {"label": "Residence Foo", "address": "1 rue Test, 29200 Brest"},
            "occupationModes": [{"type": "alone", "rent": {"min": 25000, "max": 25000}}],
        }
    ]
    html = mod.format_email_html("Brest", new_items, "https://example.com/search")
    assert "Brest" in html
    assert "T1 meuble" in html
    assert "Residence Foo" in html
    assert "1 rue Test, 29200 Brest" in html
    assert "250.00" in html
    assert 'href="https://example.com/search"' in html


def test_format_email_html_includes_unsubscribe_link_when_provided():
    new_items = [{"label": "T1", "residence": {"label": "R", "address": "A"}}]
    html = mod.format_email_html(
        "Brest", new_items, "https://example.com/search",
        unsubscribe_url="https://example.com/unsub?token=abc",
    )
    assert 'href="https://example.com/unsub?token=abc"' in html


def test_format_email_html_handles_null_residence_and_missing_rent():
    new_items = [{"label": "T1", "residence": None, "occupationModes": None}]
    html = mod.format_email_html("Brest", new_items, "https://example.com/search")
    assert "T1" in html
    assert "non pr" in html  # "loyer non précisé" fallback for missing rent


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent = None
        self.starttls_called = False
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent = (from_addr, to_addrs, msg)


def test_send_email_uses_ssl_for_port_465(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP_SSL", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com", "b@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=465,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp-relay.brevo.com"
    assert smtp.port == 465
    assert smtp.starttls_called is False
    assert smtp.logged_in == ("brevo-login", "brevo-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "alerts@example.com"
    assert to_addrs == ["a@example.com", "b@example.com"]
    assert "Subject" in msg
    msg_obj = message_from_string(msg)
    assert msg_obj["From"] == "alerts@example.com"
    decoded_body = msg_obj.get_payload(decode=True).decode("utf-8")
    assert "Body text" in decoded_body


def test_send_email_uses_starttls_for_non_ssl_port(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Body text",
        to_addrs=["a@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=587,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
    )

    smtp = _FakeSMTP.instances[0]
    assert smtp.host == "smtp-relay.brevo.com"
    assert smtp.port == 587
    assert smtp.starttls_called is True
    assert smtp.logged_in == ("brevo-login", "brevo-password")
    from_addr, to_addrs, msg = smtp.sent
    assert from_addr == "alerts@example.com"
    assert to_addrs == ["a@example.com"]


def test_send_email_sends_multipart_alternative_when_html_body_given(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Plain body",
        to_addrs=["a@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=587,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
        html_body="<html><body>Rich body</body></html>",
    )

    smtp = _FakeSMTP.instances[0]
    from_addr, to_addrs, msg = smtp.sent
    assert "multipart/alternative" in msg
    msg_obj = message_from_string(msg)
    assert msg_obj["From"] == "alerts@example.com"
    assert msg_obj.is_multipart()
    plain_part, html_part = msg_obj.get_payload()
    assert plain_part.get_payload(decode=True).decode("utf-8") == "Plain body"
    assert "Rich body" in html_part.get_payload(decode=True).decode("utf-8")


def test_send_email_without_html_body_stays_plain_text(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mod.smtplib, "SMTP", _FakeSMTP)

    mod.send_email(
        subject="Subject",
        body="Plain body",
        to_addrs=["a@example.com"],
        smtp_host="smtp-relay.brevo.com",
        smtp_port=587,
        smtp_user="brevo-login",
        smtp_password="brevo-password",
        from_email="alerts@example.com",
    )

    smtp = _FakeSMTP.instances[0]
    from_addr, to_addrs, msg = smtp.sent
    assert "multipart" not in msg


def test_main_passes_html_body_for_new_listing_alert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["x@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )
    captured = {}

    def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None):
        captured["html_body"] = html_body

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 0
    assert captured["html_body"] is not None
    assert "<html" in captured["html_body"].lower()
    assert "T1" in captured["html_body"]
    assert "Brest" in captured["html_body"]


def test_main_sends_email_for_new_listings_and_updates_seen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["x@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: sent.append(
            (subject, to_addrs, smtp_host, smtp_port, smtp_user, from_email)
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert len(sent) == 1
    assert sent[0][1] == ["x@example.com"]
    assert "Brest" in sent[0][0]
    assert sent[0][2:] == ("smtp.example.com", 587, "smtp-user", "me@example.com")
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


def test_main_email_send_failure_does_not_block_others_or_mark_seen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {"name": "Rennes", "url": "https://example.com/rennes", "emails": ["r@example.com"]},
                {"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )

    def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None):
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
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text(json.dumps({"Brest": ["1"]}), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
                {"name": "Broken", "url": "https://example.com/broken", "emails": ["broken@example.com"]},
                {"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
                {"name": "Broken", "url": "https://example.com/broken", "emails": ["broken@example.com"]},
                {"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text(json.dumps({"Brest": ["99"]}), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

    assert mod.main() == 1
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "searches.json" in captured.err


def test_main_missing_env_var_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest"}]),
        encoding="utf-8",
    )
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)

    with pytest.raises(SystemExit):
        mod.main()


def test_search_without_recipients_is_skipped_with_an_error(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Orpheline", "url": "https://example.test/search"}]),
        encoding="utf-8",
    )
    (tmp_path / "seen.json").write_text("{}", encoding="utf-8")
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "FROM_EMAIL"):
        monkeypatch.setenv(var, "1" if var == "SMTP_PORT" else "x")
    monkeypatch.delenv("ALERT_EMAIL", raising=False)

    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    monkeypatch.setattr(reloaded, "fetch_html", lambda url: "<html></html>")
    monkeypatch.setattr(reloaded, "parse_search_results", lambda html: {"items": []})

    reloaded.main()

    captured = capsys.readouterr()
    assert "aucun destinataire" in captured.err


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
            [
                {
                    "name": "Brest",
                    "url": "https://example.com/brest",
                    "keywords": ["kergoat"],
                    "emails": ["b@example.com"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

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
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: sent.append(body),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert len(sent) == 1
    assert "Kergoat" in sent[0]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


import hashlib
import hmac as hmac_module


def test_compute_unsubscribe_token_returns_none_when_secret_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    assert mod.compute_unsubscribe_token("Brest", "x@example.com") is None


def test_compute_unsubscribe_token_matches_expected_hmac(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    token = mod.compute_unsubscribe_token("Brest", "x@example.com")

    expected = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert token == expected


def test_compute_unsubscribe_token_is_case_insensitive_on_email(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    lower = mod.compute_unsubscribe_token("Brest", "x@example.com")
    upper = mod.compute_unsubscribe_token("Brest", "X@EXAMPLE.COM")

    assert lower == upper


def test_compute_unsubscribe_token_differs_per_search_and_email(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")

    token_a = mod.compute_unsubscribe_token("Brest", "x@example.com")
    token_b = mod.compute_unsubscribe_token("Rennes", "x@example.com")
    token_c = mod.compute_unsubscribe_token("Brest", "y@example.com")

    assert len({token_a, token_b, token_c}) == 3


def test_build_unsubscribe_url_returns_none_when_secret_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
    assert mod.build_unsubscribe_url("Brest", "x@example.com") is None


def test_build_unsubscribe_url_uses_base_url_when_set(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url("Brest", "x@example.com")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
    )


def test_build_unsubscribe_url_falls_back_to_github_when_base_url_unset(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.delenv("UNSUBSCRIBE_BASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")

    url = mod.build_unsubscribe_url("Brest", "x@example.com")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://github.com/LZ-Aissam/logement-crous-alert/issues/new"
        f"?template=unsubscribe.yml&search=Brest&email=x%40example.com&token={expected_token}"
    )


def test_build_unsubscribe_url_includes_city_when_provided(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url("Brest", "x@example.com", city="Rennes")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}&city=Rennes"
    )


def test_build_unsubscribe_url_includes_city_and_keywords_when_provided(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url(
        "Brest", "x@example.com", city="Rennes", keywords=["studio", "kergoat"]
    )

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
        "&city=Rennes&keywords=studio%2C%20kergoat"
    )


def test_build_unsubscribe_url_includes_max_price_and_min_area(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url(
        "Brest", "x@example.com", max_price=500, min_area=15
    )

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
        "&maxPrice=500&minArea=15"
    )


def test_build_unsubscribe_url_includes_occupation_modes_when_provided(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url(
        "Brest", "x@example.com", occupation_modes=["alone", "house_sharing"]
    )

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
        "&occupationModes=alone%2Chouse_sharing"
    )


def test_build_unsubscribe_url_includes_prm_only_when_true(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()

    url_true = mod.build_unsubscribe_url("Brest", "x@example.com", prm=True)
    assert url_true == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}&prm=1"
    )

    url_false = mod.build_unsubscribe_url("Brest", "x@example.com", prm=False)
    assert url_false == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
    )


def test_build_unsubscribe_url_includes_equipments_when_provided(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url(
        "Brest", "x@example.com", equipments=["Douche", "Frigo"]
    )

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
        "&equipments=Douche%2CFrigo"
    )


def test_build_unsubscribe_url_includes_all_filters_combined(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

    url = mod.build_unsubscribe_url(
        "Brest",
        "x@example.com",
        city="Rennes",
        keywords=["studio"],
        max_price=500,
        min_area=15,
        occupation_modes=["alone"],
        prm=True,
        equipments=["Douche"],
    )

    expected_token = hmac_module.new(
        b"topsecret", b"Brest|x@example.com", hashlib.sha256
    ).hexdigest()
    assert url == (
        "https://example.netlify.app/desabonnement.html"
        f"?search=Brest&email=x%40example.com&token={expected_token}"
        "&city=Rennes&keywords=studio"
        "&maxPrice=500&minArea=15&occupationModes=alone&prm=1&equipments=Douche"
    )


def test_format_email_body_appends_unsubscribe_link_when_provided():
    new_items = [{"id": 1, "label": "T1", "residence": {"label": "R"}}]

    body = mod.format_email_body(
        "Brest",
        new_items,
        "https://example.com/search",
        unsubscribe_url="https://example.com/unsub?token=abc",
    )

    assert "Pour ne plus recevoir ces alertes : https://example.com/unsub?token=abc" in body


def test_format_email_body_omits_unsubscribe_section_when_none():
    new_items = [{"id": 1, "label": "T1", "residence": {"label": "R"}}]

    body = mod.format_email_body("Brest", new_items, "https://example.com/search")

    assert "Pour ne plus recevoir ces alertes" not in body


def test_main_sends_individual_email_per_recipient_with_personalized_unsubscribe_link(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
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
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "topsecret")
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://example.netlify.app/desabonnement.html")

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
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: sent.append((to_addrs, body)),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert [addrs for addrs, _ in sent] == [["a@example.com"], ["b@example.com"]]
    body_a = next(body for addrs, body in sent if addrs == ["a@example.com"])
    body_b = next(body for addrs, body in sent if addrs == ["b@example.com"])
    assert "email=a%40example.com" in body_a
    assert "email=b%40example.com" in body_b
    token_a = body_a.rsplit("token=", 1)[1]
    token_b = body_b.rsplit("token=", 1)[1]
    assert token_a != token_b


def test_main_marks_seen_when_at_least_one_recipient_succeeds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        mod,
        "parse_search_results",
        lambda html: {"total": {"value": 1}, "items": [{"id": 1, "label": "T1"}]},
    )

    def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None):
        if to_addrs == ["a@example.com"]:
            raise mod.smtplib.SMTPException("boom")

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen == {"Brest": ["1"]}


def test_data_dir_defaults_to_current_directory(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    try:
        assert reloaded.SEARCHES_PATH == Path("searches.json")
        assert reloaded.SEEN_PATH == Path("seen.json")
        assert reloaded.FAILURES_PATH == Path("failures.json")
    finally:
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(check_logement)


def test_data_dir_env_var_relocates_data_files(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "data")
    import importlib

    import check_logement

    reloaded = importlib.reload(check_logement)
    try:
        assert reloaded.SEARCHES_PATH == Path("data/searches.json")
        assert reloaded.SEEN_PATH == Path("data/seen.json")
        assert reloaded.FAILURES_PATH == Path("data/failures.json")
    finally:
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(check_logement)


def test_load_failures_returns_empty_dict_when_missing(tmp_path):
    missing = tmp_path / "failures.json"
    assert mod.load_failures(missing) == {}


def test_save_then_load_failures_round_trips(tmp_path):
    path = tmp_path / "failures.json"
    mod.save_failures({"Brest": 2}, path)
    assert mod.load_failures(path) == {"Brest": 2}


def _setup_single_search(tmp_path, monkeypatch, maintainer_email=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com/brest", "emails": ["b@example.com"]}]),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    if maintainer_email:
        monkeypatch.setenv("MAINTAINER_EMAIL", maintainer_email)
    else:
        monkeypatch.delenv("MAINTAINER_EMAIL", raising=False)


def test_main_sends_health_alert_when_failure_threshold_reached(tmp_path, monkeypatch):
    _setup_single_search(tmp_path, monkeypatch, maintainer_email="admin@example.com")
    monkeypatch.setattr(mod, "fetch_html", lambda url: (_ for _ in ()).throw(mod.SearchFetchError("site changed")))
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, *a, **k: sent.append((subject, body, to_addrs)),
    )

    assert mod.main() == 1
    assert sent == []  # below threshold on run 1
    assert mod.main() == 1
    assert sent == []  # below threshold on run 2
    assert mod.main() == 1
    assert len(sent) == 1  # threshold (3) reached on run 3
    subject, body, to_addrs = sent[0]
    assert to_addrs == ["admin@example.com"]
    assert "Brest" in body
    assert "site changed" in body

    # Further consecutive failures do not re-send the alert.
    assert mod.main() == 1
    assert len(sent) == 1


def test_main_no_health_alert_without_maintainer_email(tmp_path, monkeypatch):
    _setup_single_search(tmp_path, monkeypatch, maintainer_email=None)
    monkeypatch.setattr(mod, "fetch_html", lambda url: (_ for _ in ()).throw(mod.SearchFetchError("boom")))
    monkeypatch.setattr(mod, "send_email", lambda *a, **k: pytest.fail("should not send email"))

    for _ in range(5):
        mod.main()  # must not raise even past the threshold


def test_main_resets_failure_count_on_success_before_threshold(tmp_path, monkeypatch):
    _setup_single_search(tmp_path, monkeypatch, maintainer_email="admin@example.com")
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, *a, **k: sent.append((subject, body, to_addrs)),
    )

    monkeypatch.setattr(mod, "fetch_html", lambda url: (_ for _ in ()).throw(mod.SearchFetchError("boom")))
    mod.main()
    mod.main()
    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(mod, "parse_search_results", lambda html: {"items": []})
    mod.main()

    failures = mod.load_failures()
    assert failures == {}
    assert sent == []  # threshold never reached, no alert


def test_main_sends_recovery_notice_after_alert(tmp_path, monkeypatch):
    _setup_single_search(tmp_path, monkeypatch, maintainer_email="admin@example.com")
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, *a, **k: sent.append((subject, body, to_addrs)),
    )

    monkeypatch.setattr(mod, "fetch_html", lambda url: (_ for _ in ()).throw(mod.SearchFetchError("boom")))
    mod.main()
    mod.main()
    mod.main()
    assert len(sent) == 1  # health alert

    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(mod, "parse_search_results", lambda html: {"items": []})
    mod.main()

    assert len(sent) == 2
    subject, body, to_addrs = sent[1]
    assert "retabli" in subject.lower()
    assert "Brest" in body
    assert to_addrs == ["admin@example.com"]
    assert mod.load_failures() == {}


def test_main_health_and_recovery_emails_include_html_body(tmp_path, monkeypatch):
    _setup_single_search(tmp_path, monkeypatch, maintainer_email="admin@example.com")
    sent = []
    monkeypatch.setattr(
        mod,
        "send_email",
        lambda subject, body, to_addrs, *a, html_body=None, **k: sent.append((subject, html_body)),
    )

    monkeypatch.setattr(mod, "fetch_html", lambda url: (_ for _ in ()).throw(mod.SearchFetchError("boom")))
    mod.main()
    mod.main()
    mod.main()
    monkeypatch.setattr(mod, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(mod, "parse_search_results", lambda html: {"items": []})
    mod.main()

    assert len(sent) == 2
    for _subject, html_body in sent:
        assert html_body is not None
        assert "<html" in html_body.lower()
        assert "Brest" in html_body
