from search_criteria import build_criteria, criteria_match, normalize_city


def test_normalize_city_trims_lowercases_and_collapses_spaces():
    assert normalize_city("  Saint   Denis  ") == "saint denis"
    assert normalize_city(None) == ""


def test_build_criteria_shape():
    criteria = build_criteria(
        city="  Rennes ",
        extent="-1.75_48.16_-1.61_48.05",
        max_price=500,
        min_area=18,
        occupation_modes=["house_sharing", "alone", "alone"],
        prm=True,
    )
    assert criteria == {
        "extent": "-1.75_48.16_-1.61_48.05",
        "city": "rennes",
        "maxPrice": 500,
        "minArea": 18,
        "occupationModes": ["alone", "house_sharing"],
        "prm": True,
    }


def test_build_criteria_defaults_are_null_not_zero():
    criteria = build_criteria(
        city="Brest", extent=None, max_price=None, min_area=None,
        occupation_modes=[], prm=False,
    )
    assert criteria["extent"] == ""
    assert criteria["maxPrice"] is None
    assert criteria["minArea"] is None
    assert criteria["occupationModes"] == []
    assert criteria["prm"] is False


def test_criteria_match_compares_extent_when_both_have_one():
    a = build_criteria(city="Rennes", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="Rennes Villejean", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_falls_back_to_city_when_extent_missing():
    a = build_criteria(city="Brest", extent=None, max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="  brest ", extent=None, max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_rejects_when_a_filter_differs():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=400,
                       min_area=None, occupation_modes=[], prm=False)
    b = build_criteria(city="Brest", extent="1_2_3_4", max_price=500,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, b) is False


def test_criteria_match_ignores_occupation_mode_order():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=None, min_area=None,
                       occupation_modes=["couple", "alone"], prm=False)
    b = build_criteria(city="Brest", extent="1_2_3_4", max_price=None, min_area=None,
                       occupation_modes=["alone", "couple"], prm=False)
    assert criteria_match(a, b) is True


def test_criteria_match_never_matches_missing_criteria():
    a = build_criteria(city="Brest", extent="1_2_3_4", max_price=None,
                       min_area=None, occupation_modes=[], prm=False)
    assert criteria_match(a, None) is False
    assert criteria_match(None, a) is False
    assert criteria_match(a, {}) is False
