import json
from pathlib import Path

import pytest
import yaml

import add_search as mod
import check_logement as clog


def _stub_network_and_smtp(monkeypatch):
    """Neutralise le reseau et l'envoi SMTP pour les tests de main()."""
    monkeypatch.setattr(mod.clog, "fetch_html", lambda url: "<html></html>")
    monkeypatch.setattr(mod.clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(mod.clog, "send_email", lambda **kwargs: None)
    for var, value in (
        ("SMTP_HOST", "x"), ("SMTP_PORT", "1"), ("SMTP_USER", "x"),
        ("SMTP_PASSWORD", "x"), ("FROM_EMAIL", "x@example.com"),
    ):
        monkeypatch.setenv(var, value)


def test_parse_issue_form_body_all_fields_filled():
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest 29200\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat, studio\n\n"
        "### Email de notification\n\na@example.com, b@example.com\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Brest"
    assert fields["Ville"] == "Brest 29200"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] == "Kergoat, studio"
    assert fields["Email de notification"] == "a@example.com, b@example.com"


def test_parse_issue_form_body_empty_optional_fields():
    body = (
        "### Nom de la recherche\n\nRennes\n\n"
        "### Ville\n\nRennes\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Rennes"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] is None
    assert fields["Email de notification"] is None


def test_geocode_city_returns_lon_lat(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"features": [{"geometry": {"coordinates": [0.631041, 44.202304]}}]}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    lon, lat = mod.geocode_city("Agen")
    assert lon == 0.631041
    assert lat == 44.202304


def test_geocode_city_raises_when_not_found(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"features": []}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("VilleImaginaireQuiNExistePas")


def test_geocode_city_raises_on_network_error(monkeypatch):
    def fake_get(*a, **k):
        raise mod.requests.ConnectionError("boom")

    monkeypatch.setattr(mod.requests, "get", fake_get)
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("Agen")


def test_geocode_city_raises_on_non_200_status(monkeypatch):
    class _FakeResponse:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("Agen")


def test_geocode_city_raises_on_malformed_response(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"features": [{"geometry": {}}]}  # missing "coordinates"

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _FakeResponse())
    with pytest.raises(mod.GeocodeError):
        mod.geocode_city("Agen")


def test_build_search_url_contains_bounds_and_tool_id():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=")
    assert "locationName=" in url


def test_build_search_url_uses_extent_when_valid():
    url = mod.build_search_url(
        None, None, "Brest", extent="-4.5689169_48.4595521_-4.4278311_48.3572972"
    )
    assert url == (
        "https://trouverunlogement.lescrous.fr/tools/47/search"
        "?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest"
    )


def test_build_search_url_falls_back_when_extent_invalid():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", extent="not-a-valid-extent")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=0.56")


def test_build_search_url_falls_back_when_extent_missing():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000")
    assert url.startswith("https://trouverunlogement.lescrous.fr/tools/47/search?bounds=0.56")


def test_build_search_url_appends_max_price():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", max_price=400)
    assert "&maxPrice=400" in url


def test_build_search_url_appends_min_area():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", min_area=15)
    assert "&minArea=15" in url


def test_build_search_url_appends_occupation_modes():
    url = mod.build_search_url(
        0.631041, 44.202304, "Agen 47000", occupation_modes=["alone", "house_sharing"]
    )
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url


def test_build_search_url_ignores_invalid_occupation_mode():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", occupation_modes=["alone", "bogus"])
    assert "&occupationMode=alone" in url
    assert "bogus" not in url


def test_build_search_url_appends_prm():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", prm=True)
    assert "&prm=true" in url


def test_build_search_url_omits_prm_when_false():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", prm=False)
    assert "prm" not in url


def test_build_search_url_appends_equipments():
    url = mod.build_search_url(
        0.631041, 44.202304, "Agen 47000", equipments=["Douche", "Evier + plaque"]
    )
    assert "&equipments=Douche" in url
    assert "&equipments=Evier%20%2B%20plaque" in url


def test_build_search_url_ignores_invalid_equipment():
    url = mod.build_search_url(0.631041, 44.202304, "Agen 47000", equipments=["Douche", "bogus"])
    assert "&equipments=Douche" in url
    assert "bogus" not in url


def test_build_confirmation_url_falls_back_to_github_when_base_url_unset(monkeypatch):
    monkeypatch.delenv("CONFIRMATION_BASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")

    url = mod.build_confirmation_url("abc123")

    assert url == (
        "https://github.com/LZ-Aissam/logement-crous-alert/issues/new"
        "?template=confirm-email.yml&code=abc123"
    )


def test_build_confirmation_url_uses_confirmation_base_url_when_set(monkeypatch):
    monkeypatch.setenv("CONFIRMATION_BASE_URL", "https://example.netlify.app/confirmer.html")

    url = mod.build_confirmation_url("abc123")

    assert url == "https://example.netlify.app/confirmer.html?code=abc123"


def test_build_confirmation_email_body_does_not_mention_github_account():
    body = mod.build_confirmation_email_body("Brest", "https://example.com/confirm?code=x")

    assert "compte GitHub" not in body
    assert "https://example.com/confirm?code=x" in body


def test_discover_filters_returns_distinct_sorted_names():
    items = [
        {"label": "T1", "residence": {"label": "Kergoat"}},
        {"label": "Studio", "residence": {"label": "Kergoat"}},
        {"label": "T1", "residence": {"label": "Autre"}},
    ]
    residences, labels = mod.discover_filters(items)
    assert residences == ["Autre", "Kergoat"]
    assert labels == ["Studio", "T1"]


def test_discover_filters_empty_items_returns_empty_lists():
    assert mod.discover_filters([]) == ([], [])


def test_main_adds_search_successfully(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    entry = pending["Agen"]["search"]
    assert entry["name"] == "Agen"
    assert entry["keywords"] == ["Kergoat"]
    assert "url" in entry
    assert "emails" not in entry
    out = capsys.readouterr().out
    assert "OK" in out


def test_main_rejects_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps([{"name": "Brest", "url": "https://example.com"}]), encoding="utf-8"
    )
    body = (
        "### Nom de la recherche\n\nbrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1


def test_main_reports_error_when_city_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nTest\n\n"
        "### Ville\n\nVilleInexistante\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(
        mod, "geocode_city", lambda city: (_ for _ in ()).throw(mod.GeocodeError("not found"))
    )

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []


def test_main_warns_when_keyword_not_found_but_still_adds(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nTypo123\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" in pending
    out = capsys.readouterr().out
    assert "Typo123" in out


def test_main_aborts_on_invalid_existing_searches_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original_content = '{"not": "a list"}'
    (tmp_path / "searches.json").write_text(original_content, encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert (tmp_path / "searches.json").read_text(encoding="utf-8") == original_content


def test_main_still_succeeds_when_discovery_fetch_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(
        clog, "fetch_html", lambda url: (_ for _ in ()).throw(clog.SearchFetchError("boom"))
    )
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" in pending
    out = capsys.readouterr().out
    assert "Aucun logement disponible actuellement dans cette zone" in out


def test_main_requires_name_and_city(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\n_No response_\n\n"
        "### Ville\n\n_No response_\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    assert mod.main() == 1


def test_field_label_constants_match_issue_form_yaml():
    with open(".github/ISSUE_TEMPLATE/new-search.yml", encoding="utf-8") as f:
        form = yaml.safe_load(f)
    labels_by_id = {
        field["id"]: field["attributes"]["label"] for field in form["body"]
    }
    assert labels_by_id["name"] == mod.FIELD_NAME
    assert labels_by_id["city"] == mod.FIELD_CITY
    assert labels_by_id["keywords"] == mod.FIELD_KEYWORDS
    assert labels_by_id["emails"] == mod.FIELD_EMAILS
    assert labels_by_id["extent"] == mod.FIELD_EXTENT
    assert labels_by_id["maxPrice"] == mod.FIELD_MAX_PRICE
    assert labels_by_id["minArea"] == mod.FIELD_MIN_AREA
    assert labels_by_id["occupationMode"] == mod.FIELD_OCCUPATION_MODE
    assert labels_by_id["prm"] == mod.FIELD_PRM
    assert labels_by_id["equipments"] == mod.FIELD_EQUIPMENTS


def test_js_field_labels_match_python_constants():
    js_source = Path("netlify/functions/create-search.js").read_text(encoding="utf-8")
    assert f'const FIELD_NAME = "{mod.FIELD_NAME}";' in js_source
    assert f'const FIELD_CITY = "{mod.FIELD_CITY}";' in js_source
    assert f'const FIELD_KEYWORDS = "{mod.FIELD_KEYWORDS}";' in js_source
    assert f'const FIELD_EMAILS = "{mod.FIELD_EMAILS}";' in js_source
    assert f'const FIELD_EMAIL_REF = "{mod.FIELD_EMAIL_REF}";' in js_source
    assert f'const FIELD_EXTENT = "{mod.FIELD_EXTENT}";' in js_source
    assert f'const FIELD_MAX_PRICE = "{mod.FIELD_MAX_PRICE}";' in js_source
    assert f'const FIELD_MIN_AREA = "{mod.FIELD_MIN_AREA}";' in js_source
    assert f'const FIELD_OCCUPATION_MODE = "{mod.FIELD_OCCUPATION_MODE}";' in js_source
    assert f'const FIELD_PRM = "{mod.FIELD_PRM}";' in js_source
    assert f'const FIELD_EQUIPMENTS = "{mod.FIELD_EQUIPMENTS}";' in js_source


def test_js_confirm_code_label_matches_python_constant():
    from confirm_email import FIELD_CODE

    js_source = Path("netlify/functions/confirm-email.js").read_text(encoding="utf-8")
    assert f"### {FIELD_CODE}" in js_source


def test_unsubscribe_field_label_constants_match_issue_form_yaml():
    import unsubscribe

    with open(".github/ISSUE_TEMPLATE/unsubscribe.yml", encoding="utf-8") as f:
        form = yaml.safe_load(f)
    labels_by_id = {
        field["id"]: field["attributes"]["label"] for field in form["body"]
    }
    assert labels_by_id["search"] == unsubscribe.FIELD_SEARCH
    assert labels_by_id["email"] == unsubscribe.FIELD_EMAIL
    assert labels_by_id["token"] == unsubscribe.FIELD_TOKEN


def test_js_unsubscribe_labels_match_python_constants():
    # unsubscribe.js does not hoist its labels into FIELD_* consts like
    # create-search.js does, nor inline them directly into a "### Label" template
    # literal like confirm-email.js does; it passes them as literal arguments to a
    # shared section(label, value) helper. Assert those literal arguments match the
    # Python constants so the two can't silently drift apart.
    import unsubscribe

    js_source = Path("netlify/functions/unsubscribe.js").read_text(encoding="utf-8")
    assert f'section("{unsubscribe.FIELD_SEARCH}", fields.search)' in js_source
    assert f'section("{unsubscribe.FIELD_EMAIL_REF}", ref)' in js_source
    assert f'section("{unsubscribe.FIELD_TOKEN}", fields.token)' in js_source


def test_main_rejects_invalid_email_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\npas-un-email\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_load_searches_round_trips_through_add_search(tmp_path, monkeypatch):
    # add_search.py no longer writes searches.json itself (confirm_email.py does, once
    # an address confirms) -- verify the "search" entry it stages in pending_searches.json
    # still has the shape check_logement.load_searches() accepts.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    assert mod.main() == 0

    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    entry = pending["Agen"]["search"]
    clog.save_searches([entry])
    loaded = clog.load_searches()
    assert loaded == [entry]


def test_main_creates_pending_entry_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    sent = []
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: sent.append(
            (subject, to_addrs, body)
        ),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Agen" in pending
    assert list(pending["Agen"]["pending_emails"].values()) == ["a@example.com"]
    assert len(sent) == 1
    assert sent[0][1] == ["a@example.com"]
    assert "issues/new?template=confirm-email.yml&code=" in sent[0][2]
    assert "LZ-Aissam/logement-crous-alert" in sent[0][2]


def test_build_confirmation_email_html_includes_search_name_and_cta_link():
    html = mod.build_confirmation_email_html("Agen", "https://example.com/confirmer?code=abc")
    assert "Agen" in html
    assert 'href="https://example.com/confirmer?code=abc"' in html
    assert "Confirmer" in html


def test_main_passes_html_body_for_confirmation_email(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    captured = {}

    def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None):
        captured["html_body"] = html_body

    monkeypatch.setattr(clog, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 0
    assert captured["html_body"] is not None
    assert "<html" in captured["html_body"].lower()
    assert "Agen" in captured["html_body"]


def test_main_rejects_duplicate_name_already_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Brest": {
                    "search": {"name": "Brest", "url": "https://example.com"},
                    "pending_emails": {},
                }
            }
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nbrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1


def test_main_requires_smtp_env_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("FROM_EMAIL", raising=False)
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    with pytest.raises(SystemExit):
        mod.main()


def test_main_reports_error_when_the_confirmation_email_fails_to_send(tmp_path, monkeypatch, capsys):
    # With only one address ever accepted, a failed confirmation send can no longer be
    # offset by another address succeeding -- it must be a hard failure.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    def fake_send_email(subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None):
        raise Exception("smtp boom")

    monkeypatch.setattr(clog, "send_email", fake_send_email)

    exit_code = mod.main()

    assert exit_code == 1
    assert not (tmp_path / "pending_searches.json").exists()
    out = capsys.readouterr().out
    assert "a***@example.com" in out
    assert "a@example.com" not in out


def test_main_aborts_on_invalid_existing_pending_searches_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    original_content = '{"not": "valid pending data"'
    (tmp_path / "pending_searches.json").write_text(original_content, encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert (tmp_path / "pending_searches.json").read_text(encoding="utf-8") == original_content


def test_main_dedupes_case_insensitive_emails_sends_one_confirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n"
        "a@example.com, A@EXAMPLE.com, a@Example.Com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    sent = []
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: sent.append(to_addrs),
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert len(sent) == 1
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert list(pending["Agen"]["pending_emails"].values()) == ["a@example.com"]


def test_main_rejects_multiple_distinct_emails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n"
        "a@example.com, b@example.com, c@example.com, d@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []
    assert not (tmp_path / "pending_searches.json").exists()


def test_main_uses_extent_instead_of_geocoding_when_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nRésidence Kergoat\n\n"
        "### Ville\n\nRésidence Kergoat Brest\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-4.5689169_48.4595521_-4.4278311_48.3572972\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\n_No response_\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    def fail_geocode(city):
        raise AssertionError("geocode_city should not be called when extent is valid")

    monkeypatch.setattr(mod, "geocode_city", fail_geocode)
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    entry = pending["Résidence Kergoat"]["search"]
    assert "bounds=-4.5689169_48.4595521_-4.4278311_48.3572972" in entry["url"]


def test_main_applies_price_area_occupation_prm_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n400\n\n"
        "### Surface minimum en m2 - optionnel\n\n15\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nIndividuel, Colocation\n\n"
        "### Logement adapte PMR - optionnel\n\noui\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    url = pending["Agen"]["search"]["url"]
    assert "&maxPrice=400" in url
    assert "&minArea=15" in url
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url
    assert "&prm=true" in url


def test_main_applies_equipment_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nCorte\n\n"
        "### Ville\n\nCorte 20250\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\n_No response_\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n\n"
        "### Equipements (douche, evier + plaque, frigo, micro-onde, wc) - optionnel\n\nDouche, Frigo\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (9.15, 42.3))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    url = pending["Corte"]["search"]["url"]
    assert "&equipments=Douche" in url
    assert "&equipments=Frigo" in url
    assert pending["Corte"]["search"]["criteria"]["equipments"] == ["Douche", "Frigo"]


def test_main_accepts_english_occupation_mode_values_from_the_public_form(tmp_path, monkeypatch):
    # The public form's checkboxes send API values directly (e.g. "alone,house_sharing"),
    # unlike a manually-typed GitHub Issue which sends French labels -- both must work.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nalone,house_sharing\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    url = pending["Agen"]["search"]["url"]
    assert "&occupationMode=alone" in url
    assert "&occupationMode=house_sharing" in url


def test_main_rejects_non_numeric_max_price(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\npas un nombre\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\n_No response_\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_main_ignores_unrecognized_occupation_mode_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("FROM_EMAIL", "me@example.com")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n_No response_\n\n"
        "### Prix maximum - optionnel\n\n_No response_\n\n"
        "### Surface minimum en m2 - optionnel\n\n_No response_\n\n"
        "### Type de cohabitation (individuel, couple, colocation) - optionnel\n\nBaragouin\n\n"
        "### Logement adapte PMR - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_host, smtp_port, smtp_user, smtp_password, from_email, html_body=None: None,
    )

    exit_code = mod.main()

    assert exit_code == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    url = pending["Agen"]["search"]["url"]
    assert "occupationMode" not in url


def test_main_rejects_missing_email_and_leaves_files_untouched(tmp_path, monkeypatch):
    # Formerly "still activates immediately without emails" -- the ALERT_EMAIL
    # fallback this described is gone now that an address is mandatory; a submission
    # without one must be rejected outright, with no searches.json/pending write.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 1
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert searches == []
    assert not (tmp_path / "pending_searches.json").exists()


def test_missing_email_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Email de notification\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    assert mod.main() == 1


def test_main_uses_email_ref_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    ref = "c" * 32
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / f"{ref}.json").write_text(json.dumps({"email": "a@example.com"}), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        f"### {mod.FIELD_EMAIL_REF}\n\n{ref}\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    _stub_network_and_smtp(monkeypatch)

    exit_code = mod.main()

    assert exit_code == 0
    assert not (inbox / f"{ref}.json").exists()
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert list(pending["Agen"]["pending_emails"].values()) == ["a@example.com"]


def test_main_rejects_missing_email_ref(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        f"### {mod.FIELD_EMAIL_REF}\n\n{'d' * 32}\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_more_than_one_email_is_rejected(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest\n\n"
        "### Email de notification\n\na@example.com, b@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    assert mod.main() == 1


def test_entry_carries_a_criteria_block(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    body = (
        "### Nom de la recherche\n\nRennes\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n\n"
        "### Prix maximum - optionnel\n\n500\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 0

    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    criteria = pending["Rennes"]["search"]["criteria"]
    assert criteria["extent"] == "-1.75_48.16_-1.61_48.05"
    assert criteria["city"] == "rennes"
    assert criteria["maxPrice"] == 500
    assert criteria["prm"] is False


def test_same_email_and_same_criteria_is_refused(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Deja la",
                    "url": "https://example.test/search",
                    "emails": ["a@example.com"],
                    "criteria": {
                        "extent": "-1.75_48.16_-1.61_48.05",
                        "city": "rennes",
                        "maxPrice": None,
                        "minArea": None,
                        "occupationModes": [],
                        "prm": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 1


def test_same_criteria_but_different_email_is_allowed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(
        json.dumps(
            [
                {
                    "name": "Deja la",
                    "url": "https://example.test/search",
                    "emails": ["a@example.com"],
                    "criteria": {
                        "extent": "-1.75_48.16_-1.61_48.05",
                        "city": "rennes",
                        "maxPrice": None,
                        "minArea": None,
                        "occupationModes": [],
                        "prm": False,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\nb@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 0


def test_same_email_and_same_criteria_is_refused_when_pending(monkeypatch, tmp_path):
    # Same scenario as test_same_email_and_same_criteria_is_refused, but the matching
    # criteria/email pair lives in pending_searches.json instead of searches.json --
    # exercises the second duplicate-check branch (record.get("search", {}).get(
    # "criteria") + record["pending_emails"].values()), which no other test reaches.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Deja en attente": {
                    "search": {
                        "name": "Deja en attente",
                        "url": "https://example.test/search",
                        "criteria": {
                            "extent": "-1.75_48.16_-1.61_48.05",
                            "city": "rennes",
                            "maxPrice": None,
                            "minArea": None,
                            "occupationModes": [],
                            "prm": False,
                        },
                    },
                    "pending_emails": {"somehash": "a@example.com"},
                }
            }
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 1


def test_expired_pending_duplicate_no_longer_blocks(monkeypatch, tmp_path):
    # Same fixture as test_same_email_and_same_criteria_is_refused_when_pending, but the
    # pending record is 15 minutes old (past the 10-minute expiry window) -- it must no
    # longer block a fresh submission with the same email/criteria.
    from datetime import datetime, timedelta, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    old_created_at = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Deja en attente": {
                    "search": {
                        "name": "Deja en attente",
                        "url": "https://example.test/search",
                        "criteria": {
                            "extent": "-1.75_48.16_-1.61_48.05",
                            "city": "rennes",
                            "maxPrice": None,
                            "minArea": None,
                            "occupationModes": [],
                            "prm": False,
                        },
                    },
                    "pending_emails": {"somehash": "a@example.com"},
                    "created_at": old_created_at,
                }
            }
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 0
    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    assert "Deja en attente" not in pending, "expired entry should have been pruned"


def test_fresh_pending_duplicate_still_blocks(monkeypatch, tmp_path):
    # Same fixture, but created_at is now (within the window) -- must still block, same
    # as the no-timestamp legacy case already covered elsewhere.
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    fresh_created_at = datetime.now(timezone.utc).isoformat()
    (tmp_path / "pending_searches.json").write_text(
        json.dumps(
            {
                "Deja en attente": {
                    "search": {
                        "name": "Deja en attente",
                        "url": "https://example.test/search",
                        "criteria": {
                            "extent": "-1.75_48.16_-1.61_48.05",
                            "city": "rennes",
                            "maxPrice": None,
                            "minArea": None,
                            "occupationModes": [],
                            "prm": False,
                        },
                    },
                    "pending_emails": {"somehash": "a@example.com"},
                    "created_at": fresh_created_at,
                }
            }
        ),
        encoding="utf-8",
    )
    body = (
        "### Nom de la recherche\n\nAutre nom\n\n"
        "### Ville\n\nRennes\n\n"
        "### Email de notification\n\na@example.com\n\n"
        "### Zone geographique precise (rempli automatiquement) - optionnel\n\n"
        "-1.75_48.16_-1.61_48.05\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    assert mod.main() == 1


def test_main_stamps_new_pending_entry_with_created_at(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Email de notification\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    _stub_network_and_smtp(monkeypatch)

    before = datetime.now(timezone.utc)
    assert mod.main() == 0
    after = datetime.now(timezone.utc)

    pending = json.loads((tmp_path / "pending_searches.json").read_text(encoding="utf-8"))
    created_at = datetime.fromisoformat(pending["Agen"]["created_at"])
    assert before <= created_at <= after


def test_build_confirmation_email_body_mentions_expiry_window():
    body = mod.build_confirmation_email_body("Brest", "https://example.test/confirmer?code=abc")
    assert "10 minutes" in body


def test_pending_searches_path_derives_from_check_logement_data_dir(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "data")
    import importlib

    import check_logement
    import add_search

    importlib.reload(check_logement)
    reloaded = importlib.reload(add_search)
    try:
        assert reloaded.PENDING_SEARCHES_PATH == Path("data/pending_searches.json")
    finally:
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(check_logement)
        importlib.reload(add_search)
