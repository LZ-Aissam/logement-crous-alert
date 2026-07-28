"""Locks search_criteria.py and netlify/functions/_criteria.js to identical behavior
for city normalization and criteria matching. See _criteria.js's own parity test
for the JavaScript side of this same fixture file.
"""
from __future__ import annotations

import json
from pathlib import Path

from search_criteria import criteria_match, normalize_city

FIXTURES = json.loads(
    Path(__file__).parent.joinpath("fixtures", "criteria_parity_cases.json").read_text(encoding="utf-8")
)


def test_normalize_city_matches_fixture_cases():
    for case in FIXTURES["normalize_city_cases"]:
        assert normalize_city(case["input"]) == case["expected"], case["input"]


def test_criteria_match_matches_fixture_cases():
    for case in FIXTURES["match_cases"]:
        assert criteria_match(case["a"], case["b"]) == case["expected"], case["description"]
