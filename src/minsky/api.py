"""FastAPI HTTP wrapper around Coordinator.

Exposes the intent -> filters -> ranked courses -> rationale pipeline over
HTTP so non-Python clients (the concrete next consumer is a browser
extension's content script calling a local instance of this API) can drive
it without shelling out to the CLI.

SECURITY / DEPLOYMENT CAVEAT: this app is a local/dev convenience tool --
wide-open CORS (`allow_origins=["*"]`), no authentication, and no rate
limiting. That is intentional for a local instance a browser extension talks
to on localhost, but this module must NOT be exposed publicly as-is. See
docs/api.md for what would need to change first (restrict `allow_origins` to
the extension's real origin, add auth, add rate limiting / request size
limits).

Run with: python -m uvicorn minsky.api:app --reload
(a bare `uvicorn ...` may not be on PATH depending on how Python was installed)
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from minsky.agents.constraint_resolver import load_facets
from minsky.agents.intent_parser import RuleBasedIntentParser
from minsky.agents.llm_intent_parser import LLMIntentParser
from minsky.coordinator import Coordinator, SampleCourseSource
from minsky.swayam_client import LiveSwayamCourseSource

app = FastAPI(
    title="minsky",
    description="Intent-driven filter resolution for SWAYAM",
    version="0.1.0",
)

# Local/dev tool only: this API is meant to be called from a browser
# extension's content script running on arbitrary origins, so CORS is wide
# open on purpose. There is no auth and no rate limiting either -- do not
# expose this app publicly without adding all three first.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ResolveRequest(BaseModel):
    intent: str
    top_n: int = Field(default=5, ge=1, le=25)
    parser: Literal["rule_based", "llm"] = "rule_based"
    course_source: Literal["sample", "live"] = "sample"

    @field_validator("intent")
    @classmethod
    def _intent_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("intent must not be empty or whitespace-only")
        return value


def _build_coordinator(request: ResolveRequest) -> Coordinator:
    if request.parser == "llm":
        intent_parser = LLMIntentParser()
    else:
        intent_parser = RuleBasedIntentParser()

    if request.course_source == "live":
        course_source = LiveSwayamCourseSource(fallback=SampleCourseSource())
    else:
        course_source = SampleCourseSource()

    return Coordinator(intent_parser=intent_parser, course_source=course_source)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/facets")
def facets() -> dict:
    return load_facets()


@app.post("/resolve")
def resolve(request: ResolveRequest):
    coordinator = _build_coordinator(request)
    try:
        result = coordinator.solve(request.intent, top_n=request.top_n)
    except Exception as exc:  # noqa: BLE001 -- last-resort safety net, see module docstring
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return dataclasses.asdict(result)
