"""IBM Maximo (OSLC REST) connector.

Implements ``LakeflowConnect`` + ``SupportsPartitionedStream`` for a curated
set of Maximo Object Structures (Work Orders, Assets, Purchase Orders,
Inventory, Inventory Balances, Service Requests, People, Locations, Items).

Authentication
--------------
API-key auth (recommended). The key is sent in the ``apikey`` request header.
Works for both classic on-premises Maximo (``/maximo/oslc``) and MAS Manage
(``/maximo/api`` with an ``x-public-uri`` header).

Read path
---------
Maximo's OSLC query surface supports server-side range filtering
(``oslc.where=changedate>"..." and changedate<="..."``), ascending sort
(``oslc.orderBy=+changedate``), page sizing (``oslc.pageSize``) and next-page
links (``responseInfo.nextPage.href``). Because it supports bounded time-range
queries on the ``changedate`` cursor, the connector uses
``SupportsPartitionedStream``: ``latest_offset`` returns a snapshot high-water
mark (capped at init time to guarantee ``Trigger.AvailableNow`` termination),
``get_partitions`` splits the ``(start, end]`` changedate range into
independent time windows, and ``read_partition`` fetches each window in
parallel on Spark executors.

``mxapiinvbal`` (Inventory Balances) is a snapshot table — balances change
constantly and ``changedate`` is not reliably exposed on all Maximo versions.
It opts out of partitioned streaming (``is_partitioned`` returns ``False``)
and is read as a full paginated snapshot on the single-driver path.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Sequence

import requests
from pyspark.sql.types import StructType

from databricks.labs.community_connector.interface.lakeflow_connect import (
    LakeflowConnect,
)
from databricks.labs.community_connector.interface.supports_partition import (
    SupportsPartitionedStream,
)
from databricks.labs.community_connector.sources.ibm_maximo.ibm_maximo_schemas import (
    SUPPORTED_TABLES,
    TABLE_METADATA,
    TABLE_SCHEMAS,
    TABLE_SELECT_FIELDS,
)

# Epoch lower bound for "beginning of time" reads.
EPOCH_ISO = "1970-01-01T00:00:00+00:00"
# A start cursor at or below this threshold is treated as a first run; the
# connector emits a single open-ended partition instead of thousands of tiny
# windows spanning decades.
FIRST_RUN_SENTINEL_THRESHOLD = "2000-01-01T00:00:00+00:00"

DEFAULT_PAGE_SIZE = 200
DEFAULT_WINDOW_SECONDS = 86_400  # 1 day
DEFAULT_LOOKBACK_SECONDS = 300  # 5 minutes

RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
INITIAL_BACKOFF = 5.0
REQUEST_TIMEOUT = 60

_ERROR_BODY_LIMIT = 256


def _redact_body(text: str) -> str:
    """Truncate and flatten a response body for safe inclusion in errors."""
    if not text:
        return ""
    flattened = text.replace("\r", " ").replace("\n", " ")
    if len(flattened) <= _ERROR_BODY_LIMIT:
        return flattened
    return flattened[:_ERROR_BODY_LIMIT] + "...[truncated]"


class IbmMaximoLakeflowConnect(LakeflowConnect, SupportsPartitionedStream):
    """LakeflowConnect implementation for IBM Maximo (OSLC REST API).

    Required connection options:
        base_url (alias: host)   Maximo host root, e.g. https://maximo.example.com
        api_key                  API key sent in the ``apikey`` header.

    Optional connection options:
        api_route                ``oslc`` (default, on-prem) or ``api`` (MAS Manage).
        x_public_uri             Value for the ``x-public-uri`` header (MAS Manage).
        page_size                Default ``oslc.pageSize`` (default 200).

    Per-table options:
        window_seconds           Partition window size in seconds (default 86400).
        lookback_seconds         Lookback subtracted from the start cursor
                                 at read time (default 300).
        page_size                Override ``oslc.pageSize`` for this table.
        start_timestamp          ISO-8601 lower bound for the first read when
                                 no offset exists yet (optional).
        max_records_per_batch    Cap for the single-driver snapshot/fallback
                                 path (default 200000).
    """

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)

        host = options.get("base_url") or options.get("host")
        if not host:
            raise ValueError(
                "IBM Maximo connector requires connection option "
                "'base_url' (or 'host')"
            )
        self._api_key = options.get("api_key")
        if not self._api_key:
            raise ValueError(
                "IBM Maximo connector requires connection option 'api_key'"
            )

        self._host = host.rstrip("/")

        route = (options.get("api_route") or "oslc").strip().lower()
        if route not in ("oslc", "api"):
            raise ValueError(
                f"Unsupported api_route {route!r}; expected 'oslc' or 'api'"
            )
        self._route = route
        self._x_public_uri = options.get("x_public_uri")

        try:
            self._default_page_size = max(
                1, int(options.get("page_size") or DEFAULT_PAGE_SIZE)
            )
        except (TypeError, ValueError):
            self._default_page_size = DEFAULT_PAGE_SIZE

        # Cap cursors at init time so a trigger never chases new data. The
        # next trigger creates a fresh instance with a newer init time.
        self._init_time = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Schema / metadata
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(SUPPORTED_TABLES)

    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    # ------------------------------------------------------------------
    # SupportsPartitionedStream
    # ------------------------------------------------------------------

    def is_partitioned(self, table_name: str) -> bool:
        """Snapshot tables fall back to the single-driver simpleStreamReader."""
        if table_name not in TABLE_METADATA:
            return False
        return TABLE_METADATA[table_name].get("ingestion_type") == "cdc"

    def latest_offset(
        self,
        table_name: str,
        table_options: dict[str, str],
        start_offset: dict | None = None,
    ) -> dict:
        """Return the high-water mark, capped at init time.

        Capping at init time is what makes ``Trigger.AvailableNow`` converge:
        once the stream drains everything up to ``_init_time``, successive
        ``latest_offset`` calls return the same value and the trigger stops.
        """
        self._validate_table(table_name)
        return {"cursor": self._init_time}

    def get_partitions(
        self,
        table_name: str,
        table_options: dict[str, str],
        start_offset: dict | None = None,
        end_offset: dict | None = None,
    ) -> Sequence[dict]:
        """Split the ``(start, end]`` changedate range into time windows."""
        self._validate_table(table_name)

        window_seconds = self._parse_int(
            table_options.get("window_seconds"),
            DEFAULT_WINDOW_SECONDS,
            minimum=1,
        )
        lookback_seconds = self._parse_int(
            table_options.get("lookback_seconds"),
            DEFAULT_LOOKBACK_SECONDS,
            minimum=0,
        )

        if start_offset is None and end_offset is None:
            # Batch mode: partition the entire table.
            start_iso = table_options.get("start_timestamp") or EPOCH_ISO
            end_iso = self._init_time
        else:
            start_iso = (start_offset or {}).get("cursor") or EPOCH_ISO
            end_iso = (end_offset or {}).get("cursor") or self._init_time

        start_dt = self._parse_iso(start_iso)
        end_dt = self._parse_iso(end_iso)
        if start_dt >= end_dt:
            return []

        # First run: one open-ended partition rather than decades of windows.
        if start_dt <= self._parse_iso(FIRST_RUN_SENTINEL_THRESHOLD):
            return [{"since": None, "until": end_iso}]

        if lookback_seconds > 0:
            start_dt = start_dt - timedelta(seconds=lookback_seconds)
            start_iso = self._format_iso(start_dt)
            if start_dt >= end_dt:
                return []

        partitions: list[dict] = []
        cursor_dt = start_dt
        cursor_iso = start_iso
        while cursor_dt < end_dt:
            next_dt = cursor_dt + timedelta(seconds=window_seconds)
            if next_dt > end_dt:
                next_dt = end_dt
                next_iso = end_iso
            else:
                next_iso = self._format_iso(next_dt)
            partitions.append({"since": cursor_iso, "until": next_iso})
            cursor_dt = next_dt
            cursor_iso = next_iso

        return partitions

    def read_partition(
        self,
        table_name: str,
        partition: dict,
        table_options: dict[str, str],
    ) -> Iterator[dict]:
        """Read one ``(since, until]`` cursor window on an executor."""
        self._validate_table(table_name)
        since = partition.get("since")
        until = partition.get("until")
        cursor_field = self._cursor_field(table_name)
        where = self._build_where(cursor_field, since, until)
        yield from self._read_paginated(table_name, table_options, where)

    # ------------------------------------------------------------------
    # LakeflowConnect.read_table — single-driver path
    # ------------------------------------------------------------------

    def read_table(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """Single-driver read: incremental for CDC, full snapshot otherwise."""
        self._validate_table(table_name)
        metadata = TABLE_METADATA[table_name]

        if metadata.get("ingestion_type") == "snapshot":
            return self._read_snapshot(table_name, start_offset, table_options)

        return self._read_incremental(table_name, start_offset, table_options)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def _read_incremental(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """Read all changed records in ``(start, init_time]`` in one batch.

        Fallback path for CDC tables when partitioned streaming is not used.
        The cursor is capped at ``_init_time`` so a trigger terminates.
        """
        since = (start_offset or {}).get("cursor")
        if since and self._parse_iso(since) >= self._parse_iso(self._init_time):
            return iter([]), start_offset

        lookback_seconds = self._parse_int(
            table_options.get("lookback_seconds"),
            DEFAULT_LOOKBACK_SECONDS,
            minimum=0,
        )
        if not since:
            since = table_options.get("start_timestamp")

        query_since = since
        if query_since and lookback_seconds > 0:
            query_since = self._format_iso(
                self._parse_iso(query_since) - timedelta(seconds=lookback_seconds)
            )

        where = self._build_where(
            self._cursor_field(table_name), query_since, self._init_time
        )
        max_records = self._parse_int(
            table_options.get("max_records_per_batch"), 200_000, minimum=1
        )
        records = []
        for rec in self._read_paginated(table_name, table_options, where):
            records.append(rec)
            if len(records) >= max_records:
                break

        end_offset = {"cursor": self._init_time}
        if start_offset and start_offset == end_offset:
            return iter([]), start_offset
        return iter(records), end_offset

    def _read_snapshot(
        self,
        table_name: str,
        start_offset: dict,
        table_options: dict[str, str],
    ) -> tuple[Iterator[dict], dict]:
        """Full-snapshot read for non-incremental tables (mxapiinvbal).

        Uses a ``{"done": True}`` sentinel so a second call within the same
        ``Trigger.AvailableNow`` trigger short-circuits and the trigger
        terminates (end_offset == start_offset).
        """
        if start_offset and start_offset.get("done"):
            return iter([]), start_offset

        records = list(self._read_paginated(table_name, table_options, where=None))
        return iter(records), {"done": True}

    def _read_paginated(
        self,
        table_name: str,
        table_options: dict[str, str],
        where: str | None,
    ) -> Iterator[dict]:
        """Yield projected records for an object structure, following
        ``responseInfo.nextPage.href`` until pagination is exhausted."""
        osname = table_name
        select_fields = TABLE_SELECT_FIELDS[table_name]
        page_size = self._parse_int(
            table_options.get("page_size"), self._default_page_size, minimum=1
        )

        url = f"{self._host}/maximo/{self._route}/os/{osname}"
        params: dict[str, str] | None = {
            "lean": "1",
            "oslc.pageSize": str(page_size),
            "oslc.select": ",".join(select_fields),
        }
        if where:
            params["oslc.where"] = where
        # Ascending sort on the table's cursor field lets partial reads resume
        # deterministically. The cursor field is per-table: most object
        # structures expose ``changedate``, but a few (mxapiperson,
        # mxapiinventory, mxapiitem) do not and use ``statusdate`` instead.
        cursor_field = self._cursor_field(table_name)
        if cursor_field:
            params["oslc.orderBy"] = f"+{cursor_field}"

        while True:
            resp = self._get_with_retry(url, params)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"IBM Maximo read failed for {osname!r}: "
                    f"{resp.status_code} {_redact_body(resp.text)}"
                )
            body = resp.json()
            members = body.get("member") or []
            for raw in members:
                yield self._project(table_name, raw)

            next_href = (
                (body.get("responseInfo") or {}).get("nextPage") or {}
            ).get("href")
            if not next_href or not members:
                return
            # Follow the next-page link verbatim; params already encoded in it.
            url = next_href
            params = None

    def _project(self, table_name: str, raw: dict) -> dict:
        """Project a raw lean record onto the declared schema columns.

        Extra Maximo fields (``href``, ``_rowstamp``, child collections) are
        dropped; declared columns absent from the record default to ``None``.
        """
        return {field: raw.get(field) for field in TABLE_SELECT_FIELDS[table_name]}

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "apikey": self._api_key,
            "Accept": "application/json",
        }
        if self._x_public_uri:
            headers["x-public-uri"] = self._x_public_uri
        return headers

    def _get_with_retry(
        self, url: str, params: dict[str, str] | None
    ) -> requests.Response:
        """GET with exponential backoff on 429/5xx and transient network errors."""
        backoff = INITIAL_BACKOFF
        resp: requests.Response | None = None
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.SSLError,
            ) as exc:
                last_exc = exc
                if attempt >= MAX_RETRIES - 1:
                    raise
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code not in RETRIABLE_STATUS_CODES:
                return resp

            if attempt < MAX_RETRIES - 1:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else backoff
                except (TypeError, ValueError):
                    wait = backoff
                time.sleep(wait)
                backoff *= 2

        if resp is None and last_exc is not None:
            raise last_exc
        return resp  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_table(self, table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported tables: {SUPPORTED_TABLES}"
            )

    @staticmethod
    def _cursor_field(table_name: str) -> str | None:
        """Return the incremental cursor attribute for an object structure.

        Most Maximo object structures expose ``changedate``, but a few
        (mxapiperson, mxapiinventory, mxapiitem) do not surface it as a
        queryable OSLC property; those declare an alternate cursor (e.g.
        ``statusdate``) in ``TABLE_METADATA``.
        """
        return (TABLE_METADATA.get(table_name) or {}).get("cursor_field")

    @staticmethod
    def _build_where(
        cursor_field: str | None, since: str | None, until: str | None
    ) -> str | None:
        """Build an ``oslc.where`` cursor range clause.

        Lower bound is exclusive (``>``) so back-to-back windows are disjoint;
        upper bound is inclusive (``<=``). Returns ``None`` when there is no
        cursor field or neither bound is set (unbounded read).
        """
        if not cursor_field:
            return None
        clauses: list[str] = []
        if since:
            clauses.append(f'{cursor_field}>"{since}"')
        if until:
            clauses.append(f'{cursor_field}<="{until}"')
        if not clauses:
            return None
        return " and ".join(clauses)

    @staticmethod
    def _parse_int(value: Any, default: int, *, minimum: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= minimum else default

    @staticmethod
    def _parse_iso(iso_ts: str) -> datetime:
        normalised = iso_ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalised)
        except ValueError as e:
            raise ValueError(f"Invalid ISO timestamp {iso_ts!r}") from e
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _format_iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()
