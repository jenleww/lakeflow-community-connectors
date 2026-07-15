"""Custom simulator handler for IBM Maximo's OSLC object-structure reads.

The connector issues ``GET /maximo/{oslc|api}/os/{osname}`` with:

  * ``oslc.where`` — a *compound* filter expression in a single query param,
    e.g. ``changedate>"2024-01-01T..." and changedate<="2026-..."``.
  * ``oslc.orderBy=+changedate`` — ascending sort.
  * ``oslc.pageSize`` — page size.
  * pagination by following ``responseInfo.nextPage.href`` verbatim (which
    carries a ``pageno`` query param).

The compound ``oslc.where`` clause and the ``nextPage.href`` pagination
envelope don't fit the simulator's declarative param-role pipeline, so this
handler serves the endpoint directly. It:

  1. Extracts ``osname`` from the URL path and maps it to a corpus.
  2. Parses the ``changedate`` lower/upper bounds out of ``oslc.where`` and
     subsets the corpus by them (parsed as datetimes, so mixed ``Z`` / offset
     formats compare correctly).
  3. Sorts ascending by ``changedate``.
  4. Appends a few future-dated clones so the connector's ``until=<init_time>``
     cap is exercised by the termination test (mirrors the declarative
     ``synthesize_future_records:`` directive).
  5. Paginates via ``oslc.pageSize`` + ``pageno`` and emits a
     ``responseInfo.nextPage.href`` when more pages remain.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from requests.models import PreparedRequest, Response

from databricks.labs.community_connector.source_simulator.cassette import (
    ResponseRecord,
)
from databricks.labs.community_connector.source_simulator.interceptor import (
    response_from_record,
)

_OSNAME_RE = re.compile(r"/maximo/(?:oslc|api)/os/(?P<osname>[^/?]+)")

# Bounds parsed out of the compound oslc.where expression.
_LOWER_RE = re.compile(r'changedate\s*>\s*"(?P<v>[^"]+)"')
_UPPER_RE = re.compile(r'changedate\s*<=\s*"(?P<v>[^"]+)"')

_DEFAULT_PAGE_SIZE = 200
_FUTURE_RECORDS = 3


def read_os(prep: PreparedRequest, spec: Any, corpus: Any) -> Response:  # noqa: ARG001
    parsed = urlsplit(prep.url or "")
    query = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}

    osname_match = _OSNAME_RE.search(parsed.path)
    if not osname_match:
        return _build_response(prep, 404, {"Error": {"message": f"bad path: {parsed.path}"}})
    osname = osname_match.group("osname")

    records = corpus.get(osname) or []
    if not isinstance(records, list):
        records = []

    records = _augment_with_future(records)

    lo, hi = _extract_bounds(query.get("oslc.where"))
    filtered = [r for r in records if _changedate_in_range(r, lo, hi)]

    # Ascending sort by changedate (the connector always requests +changedate).
    filtered = sorted(filtered, key=lambda r: _parse_iso(r.get("changedate")) or datetime.min.replace(tzinfo=timezone.utc))

    page_size = _to_int(query.get("oslc.pageSize"), _DEFAULT_PAGE_SIZE)
    pageno = _to_int(query.get("pageno"), 1)
    if pageno < 1:
        pageno = 1

    start = (pageno - 1) * page_size
    page = filtered[start : start + page_size]

    response_info: dict[str, Any] = {"pagenum": pageno}
    if start + page_size < len(filtered) and page:
        response_info["nextPage"] = {"href": _next_href(prep.url or "", pageno + 1)}

    payload = {"member": page, "responseInfo": response_info}
    return _build_response(prep, 200, payload)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_bounds(where: str | None) -> tuple[str | None, str | None]:
    if not where:
        return None, None
    lo_m = _LOWER_RE.search(where)
    hi_m = _UPPER_RE.search(where)
    return (
        lo_m.group("v") if lo_m else None,
        hi_m.group("v") if hi_m else None,
    )


def _changedate_in_range(record: dict[str, Any], lo: str | None, hi: str | None) -> bool:
    ts = _parse_iso(record.get("changedate"))
    if ts is None:
        # Records without changedate only survive an unbounded query.
        return lo is None and hi is None
    lo_dt = _parse_iso(lo)
    hi_dt = _parse_iso(hi)
    if lo_dt is not None and not ts > lo_dt:
        return False
    if hi_dt is not None and not ts <= hi_dt:
        return False
    return True


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _augment_with_future(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append future-dated clones so cap-validation termination tests bite.

    A correctly-capped connector filters these out via ``changedate<=init``.
    """
    if not records:
        return records
    base = datetime.now(timezone.utc) + timedelta(days=365)
    template = records[-1]
    future = []
    for i in range(_FUTURE_RECORDS):
        clone = copy.deepcopy(template)
        future_ts = (base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        clone["changedate"] = future_ts
        future.append(clone)
    return list(records) + future


def _next_href(request_url: str, next_pageno: int) -> str:
    parts = urlsplit(request_url)
    query = {k: v[-1] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
    query["pageno"] = str(next_pageno)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_response(prep: PreparedRequest, status: int, payload: dict[str, Any]) -> Response:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    rec = ResponseRecord(
        status_code=status,
        headers={"Content-Type": "application/json"},
        body_text=body.decode("utf-8"),
        body_b64=None,
        encoding="utf-8",
        url=prep.url,
    )
    return response_from_record(rec, prep)
