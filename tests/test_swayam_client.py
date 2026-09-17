"""Tests for the live SWAYAM CourseSource (src/minsky/swayam_client.py).

Fully offline by default: `urllib.request.urlopen` is mocked everywhere except
the one integration test at the bottom, which is skipped unless
MINSKY_LIVE_TESTS=1 is set (see docs/live-integration.md -- this endpoint is
undocumented/reverse-engineered and must never be a hard dependency of the
default test suite or CI).
"""

from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from minsky.schema import Course, FilterSelection
from minsky.swayam_client import (
    LiveSwayamCourseSource,
    SwayamAPIError,
    SwayamClient,
    _build_args,
    _build_query,
)

_XSSI_PREFIX = ")]}'"


def _canned_response(payload: dict) -> bytes:
    return (_XSSI_PREFIX + "\n" + json.dumps(payload)).encode("utf-8")


def _mock_urlopen(body: bytes, status: int = 200):
    response = MagicMock()
    response.read.return_value = body
    response.getcode.return_value = status
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


# -- (a) query building reflects verified arg mappings -----------------------


def test_build_args_maps_filters_to_verified_live_args():
    filters = FilterSelection(
        national_coordinator="NPTEL",
        course_mode="Self Paced",
        course_duration="12 Weeks",
        course_language="Hindi",
        educational_level="UG-Year 1",
        industry_sector="IT & ITES",
        credits="Yes",
        category="Engineering and Technology",
    )
    args = _build_args(filters, keyword="", status="Upcoming")

    # verified working mappings
    assert args["ncCode"] == "NPTEL"
    assert args["courseLanguage"] == "Hindi"
    assert args["industryOrSector"] == "IT & ITES"
    # duration must be stripped to a bare int -- "12 Weeks" -> "12" (sending
    # "12 Weeks" verified to 400 with "invalid literal for int()")
    assert args["duration"] == "12"
    # category is a verified vocabulary mismatch (internal codes, not our
    # taxonomy) and "all" is verified to NOT be a wildcard for this arg (it is
    # itself a real category code) -- category is therefore never forwarded.
    assert args["category"] == ""
    # forwarded-but-verified-no-op args still carry the literal facet value
    assert args["courseType"] == "Self Paced"
    assert args["ncrfLevel"] == "UG-Year 1"
    assert args["credits"] == "Yes"


def test_build_args_defaults_unset_fields_to_all():
    args = _build_args(FilterSelection(), keyword="", status="Upcoming")
    assert args["ncCode"] == "all"
    assert args["courseType"] == "all"
    assert args["courseLanguage"] == "all"
    assert args["ncrfLevel"] == "all"
    assert args["industryOrSector"] == "all"
    assert args["credits"] == "all"
    assert args["duration"] == "all"
    assert args["category"] == ""


def test_build_query_embeds_args_and_first():
    args = _build_args(FilterSelection(national_coordinator="NPTEL"), keyword="", status="Upcoming")
    query = _build_query(args, first=25)
    assert 'ncCode: "NPTEL"' in query
    assert "first: 25" in query
    assert "courseList(args:" in query
    assert "category { name }" in query


# -- (b) parsing a canned response builds Course objects correctly -----------


def test_fetch_courses_parses_canned_response():
    canned = {
        "data": {
            "courseList": {
                "edges": [
                    {
                        "node": {
                            "id": "Q291cnNlTGlzdDovbmQyX25vdTI2X2dlNjM=",
                            "title": "Data Storytelling & Dashboards with Power BI & Python",
                            "ncCode": "NITTTR",
                            "weeks": 8,
                            "credits": 3,
                            "industryOrSector": "IT & ITES",
                            "ncrfLevel": "",
                            "courseLanguage": "English",
                            "category": [{"name": "Multidisciplinary", "category": None, "parentId": None}],
                            "tags": [{"name": "data analytics"}, {"name": "power bi"}],
                        }
                    },
                    {
                        "node": {
                            "id": "abc123",
                            "title": "Zero-credit self paced course",
                            "ncCode": "AICTE",
                            "weeks": -1,
                            "credits": 0,
                            "industryOrSector": "",
                            "ncrfLevel": "",
                            "courseLanguage": "Hindi",
                            "category": [],
                            "tags": None,
                        }
                    },
                ]
            }
        },
        "errors": [],
    }
    body = _canned_response(canned)

    with patch("minsky.swayam_client.urllib.request.urlopen", return_value=_mock_urlopen(body)):
        client = SwayamClient()
        courses = client.fetch_courses(FilterSelection())

    assert len(courses) == 2

    first = courses[0]
    assert isinstance(first, Course)
    assert first.id == "Q291cnNlTGlzdDovbmQyX25vdTI2X2dlNjM="
    assert first.title == "Data Storytelling & Dashboards with Power BI & Python"
    assert first.provider == "NITTTR"
    assert first.mode == "Unknown"
    assert first.duration_weeks == 8
    assert first.language == "English"
    assert first.educational_level == ""
    assert first.industry_sector == "IT & ITES"
    assert first.credits is True
    assert first.category == "Multidisciplinary"
    assert first.keywords == ["data analytics", "power bi"]

    second = courses[1]
    assert second.duration_weeks == -1
    assert second.credits is False
    assert second.category == ""
    assert second.keywords == []
    assert second.language == "Hindi"


def test_fetch_courses_strips_xssi_prefix():
    canned = {"data": {"courseList": {"edges": []}}, "errors": []}
    body = _canned_response(canned)
    with patch("minsky.swayam_client.urllib.request.urlopen", return_value=_mock_urlopen(body)):
        client = SwayamClient()
        courses = client.fetch_courses(FilterSelection())
    assert courses == []


# -- (c) network/GraphQL failures raise SwayamAPIError, and fallback works ---


def test_fetch_courses_raises_swayam_api_error_on_network_failure():
    with patch(
        "minsky.swayam_client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        client = SwayamClient()
        with pytest.raises(SwayamAPIError):
            client.fetch_courses(FilterSelection())


def test_fetch_courses_raises_swayam_api_error_on_graphql_errors():
    canned = {"data": None, "errors": ["Cannot query field 'zzz' on type 'CourseList'."]}
    body = _canned_response(canned)
    with patch("minsky.swayam_client.urllib.request.urlopen", return_value=_mock_urlopen(body)):
        client = SwayamClient()
        with pytest.raises(SwayamAPIError):
            client.fetch_courses(FilterSelection())


def test_fetch_courses_raises_swayam_api_error_on_malformed_json():
    body = (_XSSI_PREFIX + "\nnot json at all").encode("utf-8")
    with patch("minsky.swayam_client.urllib.request.urlopen", return_value=_mock_urlopen(body)):
        client = SwayamClient()
        with pytest.raises(SwayamAPIError):
            client.fetch_courses(FilterSelection())


def test_live_source_reraises_without_fallback():
    with patch(
        "minsky.swayam_client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("boom"),
    ):
        source = LiveSwayamCourseSource()
        with pytest.raises(SwayamAPIError):
            source.get_courses(FilterSelection())


def test_live_source_falls_back_on_api_error():
    fallback_courses = [
        Course(
            id="sample-1",
            title="Sample Fallback Course",
            provider="NPTEL",
            mode="Self Paced",
            duration_weeks=8,
            language="English",
            educational_level="UG-Year 1",
            industry_sector="IT & ITES",
            credits=True,
            category="Engineering and Technology",
            keywords=["python"],
        )
    ]
    fallback = MagicMock()
    fallback.get_courses.return_value = fallback_courses

    with patch(
        "minsky.swayam_client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("boom"),
    ):
        source = LiveSwayamCourseSource(fallback=fallback)
        result = source.get_courses(FilterSelection())

    assert result == fallback_courses
    fallback.get_courses.assert_called_once()


def test_live_source_falls_back_on_empty_result():
    canned = {"data": {"courseList": {"edges": []}}, "errors": []}
    body = _canned_response(canned)
    fallback = MagicMock()
    fallback.get_courses.return_value = ["sentinel"]

    with patch("minsky.swayam_client.urllib.request.urlopen", return_value=_mock_urlopen(body)):
        source = LiveSwayamCourseSource(fallback=fallback)
        result = source.get_courses(FilterSelection())

    assert result == ["sentinel"]
    fallback.get_courses.assert_called_once()


# -- integration test: hits the real, live endpoint ---------------------------


@pytest.mark.skipif(
    os.environ.get("MINSKY_LIVE_TESTS") != "1",
    reason="hits live SWAYAM API",
)
def test_live_endpoint_returns_real_courses():
    client = SwayamClient()
    courses = client.fetch_courses(
        FilterSelection(national_coordinator="NPTEL"), status="all", first=5
    )
    assert isinstance(courses, list)
    for course in courses:
        assert isinstance(course, Course)
        assert course.provider == "NPTEL"
