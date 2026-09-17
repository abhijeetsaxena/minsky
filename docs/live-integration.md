# Live SWAYAM integration

`src/minsky/swayam_client.py` provides `SwayamClient` and `LiveSwayamCourseSource`, a
`CourseSource` (see [architecture.md](architecture.md)'s extension points) backed by
SWAYAM's own, real course data — instead of the static synthetic catalog
(`SampleCourseSource`, the default).

## The endpoint

SWAYAM's public course-catalog page (the Polymer app at `/explorer`, "All Courses") loads
its course list from `GET https://swayam.gov.in/modules/gql/query?q=<GraphQL query>` — a
plain, unauthenticated, cookie-free GET request. This is **not an officially published
API**: it was found by reading the page's own client-side JS
(`course-explorer.html`'s `_getCoursesQuery`), it carries no stability guarantee, and
SWAYAM could change or remove it without notice. For that reason:

- `LiveSwayamCourseSource` is never the `Coordinator`'s default — you opt in explicitly.
- The default `pytest` suite never calls it — `tests/test_swayam_client.py` mocks
  `urllib.request.urlopen` for every test except one, which is skipped unless
  `MINSKY_LIVE_TESTS=1` is set.
- Every call is wrapped so failures degrade gracefully rather than crashing the pipeline
  (see [Fallback behavior](#fallback-behavior)).

The response body is prefixed with an XSSI-protection string (`)]}'`) that must be
stripped before it's valid JSON — a common pattern for endpoints designed to be called
only from the site's own frontend, not as a general-purpose API.

## Verified filter → live-arg mappings

The site's `filter_options` object has more fields than the visible sidebar facets, and
which GraphQL arg actually does something server-side turned out to be **not what the
JS's own naming suggests**. Each mapping below was verified with real requests against
the live endpoint (varying one arg at a time), not inferred from naming:

| `FilterSelection` field | Live GraphQL arg | Status | Evidence |
|---|---|---|---|
| `national_coordinator` | `ncCode` | **Works** | `ncCode: "NPTEL"` returns only courses with `ncCode == "NPTEL"` |
| `industry_sector` | `industryOrSector` | **Works** | `industryOrSector: "IT & ITES"` correctly narrows results |
| `course_language` | `courseLanguage` | **Works** (bonus — not sent by the site's own JS query) | Node exposes a real `courseLanguage` scalar; filtering on it narrows results correctly |
| `course_duration` | `duration` | **Works, but needs conversion** | The taxonomy's own string ("12 Weeks") causes `HTTP 400`: `{"errors": ["invalid literal for int() with base 10: '12 Weeks'"]}`. The arg wants a bare integer — `duration: "12"` — confirmed to narrow returned `weeks` values correctly. `SwayamClient` strips the string down to its leading digits before sending. |
| `course_mode` | `courseType` | **Silent no-op** | Sending `courseType: "Self Paced"` vs `"Regular"` vs `"all"` returns the identical result set every time — the arg is accepted but not wired up server-side. Still forwarded (harmless) in case SWAYAM activates it later. |
| `educational_level` | `ncrfLevel` | **Silent no-op** | Same pattern as `courseType` — accepted, doesn't change results. Still forwarded. |
| `credits` | `credits` | **Silent no-op** | Same pattern — `"Yes"`/`"No"`/`"all"` produce identical result sets. Still forwarded. |
| `category` | `category` | **Never forwarded — vocabulary mismatch + no wildcard** | The visible 13-value "Category" taxonomy (Design, Engineering and Technology, Teacher Education, …) does not correspond to this arg's actual value space, which is internal machine codes (e.g. `TEACHER_EDUCATION`, `SCHOOL`) with no complete/reliable translation table. Worse, `"all"` is **not** a wildcard here — it is itself a real category code, so sending it *narrows* results instead of leaving the facet open. The verified true no-filter value is `""` (empty string), which is what's always sent. |

No live arg exists for `national_coordinator`'s sibling "Program Alignment" or "Course
Exam Date" facets from the case study — those are out of scope for this client (it only
implements the facets `FilterSelection` actually carries).

## Course field mapping

The node selection asks for: `id title url ncCode weeks credits industryOrSector
ncrfLevel courseLanguage category { name } tags { name }` (`url` is the real,
clickable link to the course on `onlinecourses.swayam2.ac.in`, populated directly into
`Course.url` — the synthetic sample catalog leaves this `""`). Two fallback decisions
worth calling out:

- **`Course.mode`** is always `"Unknown"`. The API exposes no mode/course-type scalar at
  all — querying for `mode`, `courseMode`, or `type` on the node returns a GraphQL
  "Cannot query field" error — and since `courseType` is a confirmed no-op filter, there
  is no live signal to reflect. Returning `"Unknown"` was chosen deliberately over
  echoing back the requested filter value, which would misleadingly imply the API had
  actually filtered on it.
- **`category`** comes back as a *list* of `{name, category, parentId}` objects (not a
  single object as the original node-field sketch assumed); the first entry's `name` is
  used, in the API's internal vocabulary (not the `swayam_facets.json` taxonomy).

## Fallback behavior

```python
from minsky.coordinator import Coordinator, SampleCourseSource
from minsky.swayam_client import LiveSwayamCourseSource

coordinator = Coordinator(
    course_source=LiveSwayamCourseSource(fallback=SampleCourseSource()),
)
result = coordinator.solve("I want to become job-ready in data analytics within 3 months")
```

`LiveSwayamCourseSource.get_courses()`:
- On a `SwayamAPIError` (network failure, non-200, malformed body, non-empty GraphQL
  `errors`): logs a warning and returns `fallback.get_courses(filters)` if a fallback was
  given, otherwise re-raises.
- On an empty result set from a live call that otherwise succeeded: same fallback
  behavior, since an empty list is often a sign of an over-narrow filter combination
  rather than "no such courses exist."
- With no `fallback` configured, failures propagate as `SwayamAPIError` — useful for a
  caller (e.g. the HTTP API) that wants to report a clear error rather than silently
  serve stale/sample data.

## Running the live integration test manually

```bash
MINSKY_LIVE_TESTS=1 python -m pytest tests/test_swayam_client.py::test_live_endpoint_returns_real_courses -v
```

Hits the real endpoint once; not part of the default `pytest` run or CI.
