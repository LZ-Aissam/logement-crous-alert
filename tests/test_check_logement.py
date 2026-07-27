import json
import requests
import pytest

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
