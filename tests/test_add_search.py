import pytest

import add_search as mod


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
