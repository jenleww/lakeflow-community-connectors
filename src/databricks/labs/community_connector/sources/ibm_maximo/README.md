# Lakeflow IBM Maximo Community Connector

This documentation describes how to configure and use the **IBM Maximo** Lakeflow community connector to ingest data from IBM Maximo Asset Management (on-premises 7.6.x) and IBM Maximo Application Suite (MAS) Manage into Databricks. The connector reads data over the Maximo REST API (OSLC), which exposes Maximo business objects as **Object Structures**.

## Prerequisites

- **IBM Maximo instance**: Either classic on-premises IBM Maximo Asset Management (7.6.0.2 or later) or IBM Maximo Application Suite (MAS) Manage.
- **API key**: An API key for a Maximo user with read access to the object structures you want to ingest. See [Obtaining the Required Parameters](#obtaining-the-required-parameters).
- **REST-enabled object structures**: The object structures you want to read (for example `mxapiwodetail`, `mxapiasset`) must be enabled for integration on your Maximo instance. The connector targets the standard out-of-the-box object structures, which are enabled by default in most deployments.
- **Network access**: The environment running the connector must be able to reach your Maximo host over HTTPS (for example `https://maximo.example.com`).
- **Lakeflow / Databricks environment**: A workspace where you can register a Lakeflow community connector and run ingestion pipelines.

## Setup

### Required Connection Parameters

Provide the following **connection-level** options when configuring the connector. These correspond to the connection options exposed by the connector.

| Name | Type | Required | Description | Example |
|------|------|----------|-------------|---------|
| `base_url` | string | yes | Base URL (host root) of the Maximo instance. Do **not** include the `/maximo` path suffix. | `https://maximo.example.com` |
| `api_key` | string | yes | API key used for authentication. Sent in the `apikey` request header. This is the primary authentication method for both on-premises Maximo and MAS Manage. | `t2b...` |
| `api_route` | string | no | API route path to use: `oslc` (default) for on-premises Maximo, or `api` for MAS Manage. | `oslc` |
| `x_public_uri` | string | no | Value for the `x-public-uri` request header. Used only with MAS Manage so that `href` links in responses resolve to the correct servlet. Leave empty for on-premises Maximo. | `https://mas-manage.example.com/maximo/api` |
| `page_size` | string | no | Default page size for OSLC queries (`oslc.pageSize`). Defaults to `200`. Can be overridden per table. | `200` |
| `externalOptionsAllowList` | string | yes | Comma-separated list of table-specific option names allowed to be passed through to the connector. This connector supports table-specific options, so this parameter must be set (see below). | `window_seconds,lookback_seconds,page_size,start_timestamp,max_records_per_batch` |

> **Note**: `base_url` may also be supplied under the alias `host`.

This connector supports table-specific options, so `externalOptionsAllowList` is a **required** connection option. The full, definitive list of supported table-specific option names is:

`window_seconds,lookback_seconds,page_size,start_timestamp,max_records_per_batch`

These option names must be included in `externalOptionsAllowList` for the connection to pass them through. The options themselves are set per table (see [Table Configurations](#table-configurations)), not as connection parameters.

### Choosing the API route

Maximo exposes two functionally equivalent routes for read operations:

- **`/maximo/oslc/os/{osname}`** — used by classic on-premises Maximo. Set `api_route` to `oslc` (the default).
- **`/maximo/api/os/{osname}`** — used by MAS Manage and deployments with app-server-based security (SAML / OIDC). Set `api_route` to `api`.

When using the `api` route with MAS Manage, also set `x_public_uri` to the public API base (for example `https://<host>/maximo/api`) so that pagination `href` links returned by the server point to the correct servlet.

### Obtaining the Required Parameters

- **`base_url`**: The host root of your Maximo instance, without the `/maximo` suffix — for example `https://maximo.example.com` or `https://mas-manage.example.com`. The connector appends the `/maximo/{oslc|api}/os/{osname}` path automatically based on `api_route`.
- **`api_key`**: API keys are the recommended authentication method for batch/analytics ingestion because they are stateless (no session cookie management) and supported by all deployment types. Obtain one of the following ways:
  - **Admin creates a key for a named user** (`POST /maximo/oslc/os/mxapiapikey`), specifying the target `userid` and an `expiration` (`-1` means the key never expires). Only one API key per user is permitted.
  - **A logged-in user creates their own key** (`POST /maximo/oslc/apitoken/create`).

  Copy the returned key value and store it securely. Use it as the `api_key` connection option.

### Create a Unity Catalog Connection

A Unity Catalog connection for this connector can be created in two ways via the UI:

1. Follow the **Lakeflow Community Connector** UI flow from the **Add Data** page.
2. Select any existing Lakeflow Community Connector connection for this source or create a new one.
3. Set `externalOptionsAllowList` to `window_seconds,lookback_seconds,page_size,start_timestamp,max_records_per_batch` (required for this connector to pass table-specific options).

The connection can also be created using the standard Unity Catalog API.

## Supported Objects

The IBM Maximo connector exposes a **static list** of object structures. Use the exact lowercase object-structure name as the `source_table`:

- `mxapiwodetail`
- `mxapiasset`
- `mxapipo`
- `mxapiinventory`
- `mxapiinvbal`
- `mxapisr`
- `mxapiperson`
- `mxapilocations`
- `mxapiitem`

### Object summary, primary keys, and ingestion mode

Primary keys in Maximo are composite (most business objects are site- or organization-scoped). Most CDC tables use `changedate` as the incremental cursor — Maximo updates `changedate` whenever a record (including its child objects) is modified. A few object structures (`mxapiinventory`, `mxapiperson`, `mxapiitem`) do not expose `changedate` as a queryable OSLC property, so they use `statusdate` as the cursor instead (see the table below).

| Object structure | Maximo object | Description | Ingestion Type | Primary Key | Incremental Cursor |
|------------------|---------------|-------------|----------------|-------------|--------------------|
| `mxapiwodetail` | WORKORDER | Work Orders (full detail) | `cdc` | `wonum`, `siteid` | `changedate` |
| `mxapiasset` | ASSET | Assets | `cdc` | `assetnum`, `siteid` | `changedate` |
| `mxapipo` | PO | Purchase Orders | `cdc` | `ponum`, `siteid` | `changedate` |
| `mxapiinventory` | INVENTORY | Inventory master (storeroom items) | `cdc` | `itemnum`, `location`, `siteid` | `statusdate` |
| `mxapiinvbal` | INVBALANCES | Inventory balances by storeroom | `snapshot` | `invbalancesid` | n/a |
| `mxapisr` | SR / TICKET | Service Requests | `cdc` | `ticketid` | `changedate` |
| `mxapiperson` | PERSON | People (personnel) | `cdc` | `personid` | `statusdate` |
| `mxapilocations` | LOCATIONS | Locations | `cdc` | `location`, `siteid` | `changedate` |
| `mxapiitem` | ITEM | Item master (catalog) | `cdc` | `itemnum`, `itemsetid` | `statusdate` |

### Incremental sync behavior

- **CDC tables** (8 objects; cursor `changedate`, or `statusdate` for `mxapiinventory`/`mxapiperson`/`mxapiitem`): The connector reads only records whose cursor value falls within the range since the last stored offset. Records are requested in ascending cursor order so partial reads resume deterministically. The connector splits the cursor range into independent time windows that can be read in parallel (see `window_seconds`). A configurable lookback (see `lookback_seconds`, default 5 minutes) is subtracted from the start cursor on each run to safely re-capture in-flight transactions from the previous batch. The lower bound of each window is exclusive and the upper bound inclusive, so back-to-back windows do not overlap or double-read.
  - **First run**: If no offset exists and no `start_timestamp` is set, the connector performs a full backfill of the object. Set `start_timestamp` to limit history to a recent cutoff.
- **Snapshot table** (`mxapiinvbal`): Inventory balances change constantly and `changedate` is not reliably exposed on all Maximo versions, so this object is read as a **full paginated snapshot** on each run rather than incrementally.

**Delete tracking**: The Maximo REST API does not expose a native "deleted records" endpoint. In Maximo, records are typically deactivated logically via a `status` change rather than hard-deleted, so CDC tables are **upsert-only** (no delete synchronization). If detecting hard deletes is required, use a periodic full snapshot comparison.

### Schema highlights

- The connector projects a curated set of **scalar attributes** per object structure (requested explicitly via `oslc.select`). Child collections (for example a work order's `wplabor`, `wpmaterial`, or a PO's `poline`) are large nested arrays that vary by deployment and are **not** included in the projected schema.
- Integer attributes (for example `priority`) are stored as `LongType` to avoid overflow; decimal / amount / duration attributes (for example `totalcost`, `curbal`, `totdowntime`) as `DoubleType`.
- Datetime attributes (including the `changedate` cursor) are surfaced as strings in ISO-8601 format with a timezone offset, as returned by Maximo in lean mode. Downstream processing can cast these to timestamps.

You usually do not need to customize the schema; it is static and driven by the connector implementation.

## Table Configurations

### Source & Destination

These are set directly under each `table` object in the pipeline spec:

| Option | Required | Description |
|---|---|---|
| `source_table` | Yes | Object-structure name in the source system (for example `mxapiwodetail`) |
| `destination_catalog` | No | Target catalog (defaults to pipeline's default) |
| `destination_schema` | No | Target schema (defaults to pipeline's default) |
| `destination_table` | No | Target table name (defaults to `source_table`) |

### Common `table_configuration` options

These are set inside the `table_configuration` map alongside any source-specific options:

| Option | Required | Description |
|---|---|---|
| `scd_type` | No | `SCD_TYPE_1` (default) or `SCD_TYPE_2`. Applicable to CDC and snapshot tables. |
| `primary_keys` | No | List of columns to override the connector's default primary keys |
| `sequence_by` | No | Column used to order records for SCD Type 2 change tracking |
| `cluster_by` | No | List of columns to cluster the destination Delta table by (Liquid Clustering). Consumed by the pipeline; not forwarded to the source. |

### Source-specific `table_configuration` options

All options below are optional. Their names must be listed in the connection's `externalOptionsAllowList` for them to be passed through.

| Option | Applies to | Default | Description |
|---|---|---|---|
| `page_size` | all tables | `200` (or the connection default) | Overrides the `oslc.pageSize` used for this table. |
| `start_timestamp` | CDC tables | none | ISO-8601 lower bound (for example `2024-01-01T00:00:00+00:00`) used for the first read when no stored offset exists yet. Omit to backfill all history. |
| `window_seconds` | CDC tables | `86400` (1 day) | Size, in seconds, of each `changedate` time window when partitioning the range for parallel reads. |
| `lookback_seconds` | CDC tables | `300` (5 minutes) | Lookback subtracted from the start cursor at read time so late-arriving updates are re-captured. |
| `max_records_per_batch` | CDC and snapshot tables | `200000` | Caps the number of records read in a single-driver batch (the non-partitioned fallback / snapshot path). |

## Data Type Mapping

Maximo field types (as returned in `lean=1` mode) are mapped to Spark types as follows:

| Maximo Type | JSON Type (lean=1) | Spark Type | Notes |
|-------------|--------------------|------------|-------|
| ALN / UPPER / LONGALN / CLOB (text) | `string` | `StringType` | Text and long-text fields |
| INTEGER | `integer` | `LongType` | Stored as `LongType` to avoid overflow |
| DECIMAL / AMOUNT / DURATION | `number` | `DoubleType` | Amounts, quantities, durations (hours) |
| YORN (boolean) | `boolean` | `BooleanType` | `true` / `false` in lean mode |
| DATE / DATETIME | `string` | `StringType` | ISO-8601 string with timezone offset (for example `2024-05-10T14:23:00+00:00`); cast downstream as needed |
| GL (account) | `string` | `StringType` | GL account in component format |

**Lean mode note**: The connector always requests `lean=1`, which returns field names without OSLC namespace prefixes and boolean values as native `true`/`false`.

**Datetime timezone**: `DATETIME` fields are returned with the Maximo server's timezone offset. Values are surfaced as ISO-8601 strings; normalize to UTC downstream if required.

## How to Run

### Step 1: Clone/Copy the Source Connector Code

Follow the Lakeflow Community Connector UI, which will guide you through setting up a pipeline using the selected source connector code.

### Step 2: Configure Your Pipeline

1. Update the `pipeline_spec` in the main pipeline file (for example `ingest.py`).
2. Reference the Unity Catalog connection configured with your Maximo `base_url` and `api_key`, and add one or more tables to ingest. Table-specific options go under `table_configuration`.

Example `pipeline_spec`:

```json
{
  "pipeline_spec": {
    "connection_name": "ibm_maximo_connection",
    "object": [
      {
        "table": {
          "source_table": "mxapiwodetail",
          "table_configuration": {
            "start_timestamp": "2024-01-01T00:00:00+00:00",
            "window_seconds": "86400",
            "lookback_seconds": "300"
          }
        }
      },
      {
        "table": {
          "source_table": "mxapiasset",
          "table_configuration": {
            "start_timestamp": "2024-01-01T00:00:00+00:00"
          }
        }
      },
      {
        "table": {
          "source_table": "mxapiinvbal"
        }
      }
    ]
  }
}
```

- `connection_name` must point to the UC connection configured with your Maximo `api_key`, `base_url`, and (for MAS Manage) `api_route` / `x_public_uri`.
- For each `table`, `source_table` must be one of the supported object-structure names listed above.

3. (Optional) Customize the source connector code if needed for special use cases.

### Step 3: Run and Schedule the Pipeline

Run the pipeline using your standard Lakeflow / Databricks orchestration (for example a scheduled job or workflow). For CDC tables:

- On the **first run**, either omit `start_timestamp` to backfill all history (which may be heavy for long-lived objects), or set `start_timestamp` to a recent cutoff to limit history.
- On **subsequent runs**, the connector resumes from the stored `changedate` cursor, minus `lookback_seconds`, to safely pick up late updates.

#### Best Practices

- **Start small**: Begin with a single object structure (for example `mxapiwodetail`) and a recent `start_timestamp` to validate configuration and data shape before backfilling all history.
- **Use incremental sync**: Rely on the CDC `changedate` cursor for the eight incremental objects to minimize load on the Maximo server.
- **Tune page size and windows**: Use a `page_size` of `100`–`500` depending on object complexity — very large pages (1000+) can cause out-of-memory errors on the Maximo server. Adjust `window_seconds` to balance parallelism against the number of requests.
- **Respect server capacity**: Maximo does not publish a fixed external rate limit; effective throughput depends on server sizing and configuration. Avoid overly aggressive concurrency against undersized instances, and stagger schedules if needed.

#### Troubleshooting

**Common Issues:**

- **`401 Unauthorized`**: The `api_key` is invalid, expired, or revoked. Verify the key and that the associated Maximo user is active. Remember that only one API key per user is permitted.
- **`403 Forbidden`**: The Maximo user lacks privileges for the requested object structure. Confirm read access to that object structure.
- **`404 Not Found`**: The object-structure name does not exist or is not REST-enabled on your instance. Verify the `source_table` name and that the object structure is enabled for integration.
- **MAS Manage `href` / pagination issues**: When using MAS Manage, ensure `api_route` is set to `api` and `x_public_uri` is set to the public API base so next-page links resolve correctly.
- **`400 Bad Request`**: Usually indicates an invalid filter or query parameter. Check that any `start_timestamp` value is a valid ISO-8601 timestamp with a timezone offset.
- **`429` / `500` errors**: The connector automatically retries retriable status codes (429, 500, 502, 503, 504) with exponential backoff, honoring the `Retry-After` header when present. Persistent 500s may indicate the Maximo server is undersized for the requested page size — reduce `page_size`.
- **Missing child data**: Child collections (labor lines, PO lines, meters, etc.) are intentionally not ingested. Only scalar attributes are projected. Ingest the related object structure separately if that data is needed.

## References

- Connector implementation: `src/databricks/labs/community_connector/sources/ibm_maximo/ibm_maximo.py`
- Connector schemas and metadata: `src/databricks/labs/community_connector/sources/ibm_maximo/ibm_maximo_schemas.py`
- Connector API reference: `src/databricks/labs/community_connector/sources/ibm_maximo/ibm_maximo_api_doc.md`
- Official IBM Maximo REST API documentation:
  - `https://ibm-maximo-dev.github.io/maximo-restapi-documentation/`
  - `https://ibm-maximo-dev.github.io/maximo-restapi-documentation/authentication/apikey`
  - `https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/filtering`
  - `https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/sort_and_paging`
