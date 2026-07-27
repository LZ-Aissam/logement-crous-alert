import json

import pytest
import yaml

import add_search as mod
import check_logement as clog


def test_parse_issue_form_body_all_fields_filled():
    body = (
        "### Nom de la recherche\n\nBrest\n\n"
        "### Ville\n\nBrest 29200\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat, studio\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com, b@example.com\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Brest"
    assert fields["Ville"] == "Brest 29200"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] == "Kergoat, studio"
    assert fields["Email(s) de notification - optionnel"] == "a@example.com, b@example.com"


def test_parse_issue_form_body_empty_optional_fields():
    body = (
        "### Nom de la recherche\n\nRennes\n\n"
        "### Ville\n\nRennes\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    fields = mod.parse_issue_form_body(body)
    assert fields["Nom de la recherche"] == "Rennes"
    assert fields["Mots-clés (résidence, type de logement...) - optionnel"] is None
    assert fields["Email(s) de notification - optionnel"] is None


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
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nKergoat\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    assert searches[0]["name"] == "Agen"
    assert searches[0]["keywords"] == ["Kergoat"]
    assert "url" in searches[0]
    assert "emails" not in searches[0]
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
        "### Email(s) de notification - optionnel\n\n_No response_\n"
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
        "### Email(s) de notification - optionnel\n\n_No response_\n"
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
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\nTypo123\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(
        clog,
        "parse_search_results",
        lambda html: {"items": [{"label": "T1", "residence": {"label": "Kergoat"}}]},
    )

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
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
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1
    assert (tmp_path / "searches.json").read_text(encoding="utf-8") == original_content


def test_main_still_succeeds_when_discovery_fetch_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text("[]", encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(
        clog, "fetch_html", lambda url: (_ for _ in ()).throw(clog.SearchFetchError("boom"))
    )

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    out = capsys.readouterr().out
    assert "Aucun logement disponible actuellement dans cette zone" in out


def test_main_requires_name_and_city(monkeypatch):
    body = (
        "### Nom de la recherche\n\n_No response_\n\n"
        "### Ville\n\n_No response_\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
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


def test_main_rejects_invalid_email_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\npas-un-email\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))

    exit_code = mod.main()

    assert exit_code == 1
    assert json.loads((tmp_path / "searches.json").read_text(encoding="utf-8")) == []


def test_load_searches_round_trips_through_add_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    assert mod.main() == 0

    loaded = clog.load_searches()
    assert loaded == [{"name": "Agen", "url": loaded[0]["url"]}]


def test_main_creates_pending_entry_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("GITHUB_REPOSITORY", "LZ-Aissam/logement-crous-alert")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})
    sent = []
    monkeypatch.setattr(
        clog,
        "send_email",
        lambda subject, body, to_addrs, smtp_user, smtp_password: sent.append(
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
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)

    exit_code = mod.main()

    assert exit_code == 1


def test_main_requires_gmail_env_when_email_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\na@example.com\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    with pytest.raises(SystemExit):
        mod.main()


def test_main_still_activates_immediately_without_emails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "searches.json").write_text(json.dumps([]), encoding="utf-8")
    body = (
        "### Nom de la recherche\n\nAgen\n\n"
        "### Ville\n\nAgen 47000\n\n"
        "### Mots-clés (résidence, type de logement...) - optionnel\n\n_No response_\n\n"
        "### Email(s) de notification - optionnel\n\n_No response_\n"
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setattr(mod, "geocode_city", lambda city: (0.631041, 44.202304))
    monkeypatch.setattr(clog, "fetch_html", lambda url: "<fake html>")
    monkeypatch.setattr(clog, "parse_search_results", lambda html: {"items": []})

    exit_code = mod.main()

    assert exit_code == 0
    searches = json.loads((tmp_path / "searches.json").read_text(encoding="utf-8"))
    assert len(searches) == 1
    assert not (tmp_path / "pending_searches.json").exists()
