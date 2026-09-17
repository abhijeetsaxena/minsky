"""SwayamClient / LiveSwayamCourseSource: a live CourseSource backed by SWAYAM's own,
undocumented (but public, unauthenticated) GraphQL-style course-catalog endpoint.

This is a best-effort, optional data source -- see docs/live-integration.md for the
full write-up of how the endpoint was discovered, which FilterSelection facets could
be verified to actually filter server-side (and which turned out to be silent no-ops
or outright mismatched vocabularies), and the fallback contract callers get from
LiveSwayamCourseSource. Nothing here is an officially published/stable API: SWAYAM
could change or remove it without notice, so this module is never wired in as the
Coordinator's default CourseSource and is never exercised by the offline test suite
by default (see tests/test_swayam_client.py).

Only the standard library is used (urllib, json) -- no new dependency is introduced.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from minsky.coordinator import CourseSource
from minsky.schema import Course, FilterSelection

logger = logging.getLogger("minsky.swayam_client")

# The response body is prefixed with this XSSI-protection string; it must be
# stripped before the remainder can be parsed as JSON.
_XSSI_PREFIX = ")]}'"

# The exact node field selection we ask for -- just enough to populate Course.
# See docs/live-integration.md for why each field was chosen (in particular:
# `courseLanguage` is a real scalar field the site's own JS query doesn't
# select but which does exist and does filter correctly; `category` comes
# back as a *list* of {name, category, parentId} objects, not a single
# object).
_NODE_FIELDS = (
    "id title url ncCode weeks credits industryOrSector ncrfLevel courseLanguage "
    "category { name } tags { name }"
)


class SwayamAPIError(Exception):
    """Raised for any network error, HTTP error, malformed response, or
    GraphQL-level error surfaced while talking to the live SWAYAM endpoint.

    Callers should never see a raw urllib/json exception from this module --
    everything is translated into this one exception type with a clear
    message.
    """


def _gql_literal(value: bool | str) -> str:
    """Render a Python bool/str as the equivalent GraphQL argument literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _duration_arg(course_duration: str | None) -> str:
    """FilterSelection.course_duration ("12 Weeks") -> the live `duration` arg.

    VERIFIED: the live endpoint parses `duration` as a bare integer server
    side -- sending the taxonomy's own "12 Weeks" string produces an HTTP 400
    with body `{"errors": ["invalid literal for int() with base 10: '12
    Weeks'"]}`. Sending just "12" filters correctly (checked returned
    `weeks` values narrow to 12). Unset (`None`) uses "all", confirmed to
    behave as a true wildcard for this arg (identical results to "").
    """
    if not course_duration:
        return "all"
    match = re.match(r"\s*(\d+)", course_duration)
    return match.group(1) if match else "all"


def _build_args(filters: FilterSelection, keyword: str, status: str) -> dict[str, bool | str]:
    """Map a resolved FilterSelection onto the live `courseList` GraphQL args.

    See docs/live-integration.md for the evidence behind every one of these
    mappings, in particular:
      - `category` is deliberately NEVER forwarded (always ""): the live arg's
        value space is internal machine codes (e.g. "TEACHER_EDUCATION",
        "SCHOOL", "Domain_7"), not the human-readable 13-value taxonomy in
        swayam_facets.json, and there is no complete/reliable translation
        table between the two. Worse, "all" is *not* a wildcard for this
        specific arg -- it is itself a real category code (the generic
        "All"/uncategorized bucket) -- so sending it would silently narrow
        results instead of leaving the facet unfiltered. "" is the verified
        true no-filter sentinel for `category`.
      - `courseType` (course_mode) and `ncrfLevel` (educational_level) and
        `credits` are forwarded as literal facet values because doing so is a
        harmless no-op (verified: they do not change the result set either
        way), kept for forward-compatibility in case SWAYAM ever wires these
        filters up server-side.
    """
    return {
        "includeClosed": False,
        "filterText": keyword,
        "category": "",
        "status": status,
        "tags": "",
        "duration": _duration_arg(filters.course_duration),
        "examDate": "all",
        "credits": filters.credits or "all",
        "ncCode": filters.national_coordinator or "all",
        "courseType": filters.course_mode or "all",
        "courseLanguage": filters.course_language or "all",
        "ncrfLevel": filters.educational_level or "all",
        "programAlignedTo": "all",
        "industryOrSector": filters.industry_sector or "all",
        "domain": "all",
    }


def _build_query(args: dict[str, bool | str], first: int) -> str:
    args_str = ", ".join(f"{key}: {_gql_literal(value)}" for key, value in args.items())
    return f"{{courseList(args: {{{args_str}}}, first: {first}) {{edges {{node {{{_NODE_FIELDS}}}}}}}}}"


class SwayamClient:
    """Thin stdlib-only HTTP client for SWAYAM's undocumented course-catalog
    GraphQL-style endpoint (see module docstring and docs/live-integration.md).
    """

    def __init__(self, base_url: str = "https://swayam.gov.in", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_courses(
        self,
        filters: FilterSelection,
        *,
        keyword: str = "",
        status: str = "Upcoming",
        first: int = 50,
    ) -> list[Course]:
        """Query the live endpoint for courses matching `filters` and return
        them as `Course` objects.

        Raises SwayamAPIError for any network failure, non-200 response,
        malformed/undecodable response body, or a non-empty GraphQL
        `errors` array -- never lets a raw urllib/json exception escape.
        """
        args = _build_args(filters, keyword, status)
        query = _build_query(args, first)
        url = f"{self.base_url}/modules/gql/query?" + urllib.parse.urlencode({"q": query})
        request = urllib.request.Request(url, headers={"Accept": "application/json"})

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read()
                status_code = response.getcode()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:  # pragma: no cover - best-effort only
                logger.debug("Could not read HTTPError body for diagnostic detail", exc_info=True)
            raise SwayamAPIError(
                f"SWAYAM API returned HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SwayamAPIError(f"Failed to reach SWAYAM API: {exc.reason}") from exc
        except OSError as exc:
            raise SwayamAPIError(f"Network error while calling SWAYAM API: {exc}") from exc

        if status_code != 200:
            raise SwayamAPIError(f"SWAYAM API returned unexpected HTTP status {status_code}")

        try:
            text = raw_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SwayamAPIError(f"SWAYAM API returned a non-UTF-8 response: {exc}") from exc

        if text.startswith(_XSSI_PREFIX):
            text = text[len(_XSSI_PREFIX) :].lstrip("\n")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SwayamAPIError(f"SWAYAM API returned malformed JSON: {exc}") from exc

        errors = payload.get("errors") or []
        if errors:
            raise SwayamAPIError(f"SWAYAM API returned GraphQL errors: {errors}")

        data = payload.get("data") or {}
        course_list = data.get("courseList") or {}
        edges = course_list.get("edges") or []
        return [self._to_course(edge.get("node") or {}) for edge in edges]

    @staticmethod
    def _to_course(node: dict) -> Course:
        """Map one raw GraphQL `node` into a `Course`.

        Fallback decisions (see docs/live-integration.md for the full
        rationale):
          - `mode`: the node exposes no mode/course-type scalar at all
            (confirmed via GraphQL's own "Cannot query field" errors for
            `mode`, `courseMode`, `type`), and the `courseType` filter arg is
            a verified no-op, so there is no live signal to reflect -- we use
            the literal fallback "Unknown" rather than echoing back the
            requested filter value, which would misleadingly imply the API
            had actually filtered on it.
          - `language`: unlike the task's assumption, the node *does* expose
            a real `courseLanguage` scalar that filters correctly, so it is
            used directly -- no fallback needed.
          - `category`: comes back as a *list* of {name, category, parentId}
            objects (not a single object); the first entry's `name` is used,
            in the API's own internal-code vocabulary (e.g. "TEACHER_EDUCATION"),
            not the swayam_facets.json taxonomy.
        """
        categories = node.get("category") or []
        category_name = ""
        if categories:
            first_category = categories[0]
            if isinstance(first_category, dict):
                category_name = first_category.get("name") or ""

        tags = node.get("tags") or []
        keywords = [
            tag.get("name", "") for tag in tags if isinstance(tag, dict) and tag.get("name")
        ]

        return Course(
            id=node.get("id") or "",
            title=node.get("title") or "",
            provider=node.get("ncCode") or "",
            mode="Unknown",
            duration_weeks=node.get("weeks") or 0,
            language=node.get("courseLanguage") or "Unknown",
            educational_level=node.get("ncrfLevel") or "",
            industry_sector=node.get("industryOrSector") or "",
            credits=bool(node.get("credits", 0)),
            category=category_name,
            keywords=keywords,
            url=node.get("url") or "",
        )


class LiveSwayamCourseSource:
    """CourseSource backed by the live SwayamClient, with an optional fallback.

    On any SwayamAPIError (network failure, HTTP error, malformed/erroring
    response) -- or an empty result set, when `fallback` is set -- this logs
    a clear one-line warning and delegates to `fallback.get_courses(filters)`
    instead of silently producing a confusing downstream error. Without a
    fallback, the SwayamAPIError is re-raised so callers who want hard
    failures still get them.
    """

    def __init__(
        self,
        client: SwayamClient | None = None,
        fallback: CourseSource | None = None,
        **fetch_kwargs: object,
    ) -> None:
        self.client = client if client is not None else SwayamClient()
        self.fallback = fallback
        self.fetch_kwargs = fetch_kwargs

    def get_courses(self, filters: FilterSelection) -> list[Course]:
        try:
            courses = self.client.fetch_courses(filters, **self.fetch_kwargs)
        except SwayamAPIError as exc:
            if self.fallback is not None:
                logger.warning(
                    "Live SWAYAM API call failed (%s); falling back to %s",
                    exc,
                    type(self.fallback).__name__,
                )
                return self.fallback.get_courses(filters)
            logger.warning("Live SWAYAM API call failed (%s); no fallback configured", exc)
            raise

        if not courses and self.fallback is not None:
            logger.warning(
                "Live SWAYAM API returned no courses for the resolved filters; "
                "falling back to %s",
                type(self.fallback).__name__,
            )
            return self.fallback.get_courses(filters)

        return courses
