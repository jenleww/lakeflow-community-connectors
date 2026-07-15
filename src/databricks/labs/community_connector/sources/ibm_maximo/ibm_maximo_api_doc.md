# IBM Maximo REST API — Connector Reference

IBM Maximo Asset Management (on-premises 7.6.x) and IBM Maximo Application Suite (MAS) Manage expose a REST API over OSLC (Open Services for Lifecycle Collaboration). Data is modeled as **Object Structures** — named integration objects that surface Maximo business objects (MBOs) as RESTful resources. The connector reads data from these object structures.

---

## Authorization

### Preferred Method: API Key (`apikey` header)

Maximo 7.6.0.2+ and MAS Manage both support API-key authentication. The key is passed either in the `apikey` request header (recommended) or as a query parameter.

```
GET /maximo/oslc/os/mxapiwodetail?lean=1&oslc.pageSize=50
apikey: <api_key_value>
```

**For deployments using app-server-based security (MAS Manage with SAML/OIDC)**, use the `/maximo/api` route (note: `/api` instead of `/oslc`) and set the `x-public-uri` header so that `href` links in responses point to the correct servlet:

```
GET /maximo/api/os/mxapiwodetail?lean=1&oslc.pageSize=50
apikey: <api_key_value>
x-public-uri: https://<host>/maximo/api
```

**Creating an API key (admin creates for a named user):**

```
POST /maximo/oslc/os/mxapiapikey
Content-Type: application/json
<session/MAXAUTH credentials>

{
  "expiration": -1,
  "userid": "WILSON"
}
```

Response includes the key value. An `expiration` of `-1` means the key never expires. Only one API key per user is permitted.

**Creating a key as the logged-in user:**

```
POST /maximo/oslc/apitoken/create
Content-Type: application/json

{ "expiration": -1 }
```

### Alternative Method: MAXAUTH (native Maximo auth, on-premises only)

Used for classic on-premises Maximo without app-server security. Not supported for MAS Manage.

```
POST /maximo/oslc/login
maxauth: <base64(userid:password)>
```

A successful login returns `Set-Cookie` headers containing the `JSESSIONID` and (on WebSphere) LTPA token. Replay these cookies on all subsequent requests.

### Alternative Method: HTTP Basic (LDAP)

```
POST /maximo/oslc/login
Authorization: Basic <base64(userid:password)>
```

Returns session cookies that must be replayed. Not supported for MAS Manage.

### Notes

- For analytics/batch ingestion, **API key is the recommended approach** — it is stateless (no session cookie management required), compatible with all deployment types, and supported from Maximo 7.6.0.2+.
- The `lean=1` parameter should be appended to the login endpoint as well when using session-based auth so that subsequent requests default to lean mode: `POST /maximo/oslc/login?lean=1`.
- All requests must include `Content-Type: application/json` for non-GET calls.

---

## Base URL Structure

```
https://<host>/maximo/oslc/os/{osname}        # OSLC servlet (classic and MAS, session/MAXAUTH)
https://<host>/maximo/api/os/{osname}          # API servlet (MAS, apikey / app-server auth)
```

The `/maximo/oslc/os/{osname}` and `/maximo/api/os/{osname}` routes are functionally equivalent for GET operations. Use `/api` for MAS deployments with external IdP authentication; use `/oslc` for on-premises with MAXAUTH/BASIC.

**Schema endpoint (discover fields for an object structure):**
```
GET /maximo/oslc/jsonschemas/{osname}
```

**List all API-eligible object structures:**
```
GET /maximo/oslc/apimeta?lean=1
```

**System information:**
```
GET /maximo/oslc/systeminfo
```

**Swagger / OpenAPI 3.0:**
```
GET /maximo/oslc/oas?lean=1&os=MXAPIWODETAIL
```

---

## Object List

The set of object structures is **static** (configured by Maximo admins). The standard, out-of-the-box REST-enabled object structures relevant to analytics ingestion are listed below. All are accessible via:

```
GET /maximo/oslc/os/{osname}?lean=1
```

| OS Name          | MBO/Table    | Description                        | Notes                                    |
|------------------|--------------|------------------------------------|------------------------------------------|
| `mxapiwodetail`  | WORKORDER    | Work Orders (full detail)          | Preferred over `mxwo`; has more fields   |
| `mxapiasset`     | ASSET        | Assets                             |                                          |
| `mxapipo`        | PO           | Purchase Orders                    |                                          |
| `mxapiinventory` | INVENTORY    | Inventory master (storeroom items) |                                          |
| `mxapiinvbal`    | INVBALANCES  | Inventory balances by storeroom    |                                          |
| `mxapisr`        | SR / TICKET  | Service Requests                   |                                          |
| `mxapiperson`    | PERSON       | People (personnel)                 |                                          |
| `mxapilocations` | LOCATIONS    | Locations                          |                                          |
| `mxapiitem`      | ITEM         | Item master (catalog)              |                                          |
| `mxapiperuser`   | MAXUSER/PERSON | Users (Maximo users)             | User+person linked                       |

To enumerate all API-eligible object structures at runtime:
```
GET /maximo/oslc/apimeta?lean=1&oslc.select=osname,description
```

Response shape:
```json
{
  "member": [
    {
      "osname": "MXAPIWODETAIL",
      "description": "Work Order Details",
      "href": "https://<host>/maximo/oslc/os/mxapiwodetail"
    }
  ],
  "responseInfo": { "href": "...", "totalCount": 120 }
}
```

---

## Object Schema

### Runtime Schema Discovery

Retrieve the JSON Schema for any object structure:

```
GET /maximo/oslc/jsonschemas/{osname}?lean=1
```

Example:
```
GET /maximo/oslc/jsonschemas/mxapiwodetail?lean=1
```

Response: a JSON Schema object (Draft 4) describing all attributes and child objects. Each attribute includes Maximo-specific extensions (type, persistent, required, etc.).

**Get schema inline with data** (single round-trip):
```
GET /maximo/oslc/os/mxapiwodetail?lean=1&oslc.pageSize=1&addschema=1
```
Appends schema information to the `responseInfo` property of the data response.

**Schema for related child objects:**
```
GET /maximo/oslc/jsonschemas/mxapiwodetail?oslc.select=wonum,status,wplabor{*}
```

### Static Field References (Key Objects)

#### mxapiwodetail — Work Order

| Field           | Type      | Description                                         |
|-----------------|-----------|-----------------------------------------------------|
| `wonum`         | string    | Work order number (PK)                              |
| `siteid`        | string    | Site identifier (composite PK with `wonum`)         |
| `orgid`         | string    | Organization identifier                             |
| `description`   | string    | Short description                                   |
| `status`        | string    | Current status (e.g., `WAPPR`, `APPR`, `COMP`)     |
| `statusdate`    | datetime  | Date/time status last changed                       |
| `worktype`      | string    | Work type (e.g., `CM`, `PM`, `EM`)                 |
| `priority`      | integer   | Work order priority                                 |
| `reportdate`    | datetime  | Date work order was reported                        |
| `actstart`      | datetime  | Actual start date/time                              |
| `actfinish`     | datetime  | Actual finish date/time                             |
| `schedstart`    | datetime  | Scheduled start date/time                           |
| `schedfinish`   | datetime  | Scheduled finish date/time                          |
| `assetnum`      | string    | Asset number                                        |
| `location`      | string    | Location identifier                                 |
| `reportedby`    | string    | Person who reported                                 |
| `owner`         | string    | Owner (person)                                      |
| `ownerperson`   | string    | Owner person ID                                     |
| `ownergroup`    | string    | Owner group                                         |
| `glaccount`     | string    | GL account                                          |
| `changedate`    | datetime  | Date record was last changed (**incremental cursor**) |
| `changeby`      | string    | Person who last changed the record                  |
| `historyflag`   | boolean   | Whether this WO is in history                       |
| `istask`        | boolean   | Whether this record is a task (child of a WO)       |
| `parent`        | string    | Parent work order number (for tasks)                |
| `wplabor`       | object[]  | Planned labor lines (child)                         |
| `wpmaterial`    | object[]  | Planned material lines (child)                      |
| `wpservice`     | object[]  | Planned service lines (child)                       |
| `actlabor`      | object[]  | Actual labor lines (child)                          |
| `actmaterials`  | object[]  | Actual materials (child)                            |
| `failure`       | object[]  | Failure codes (child)                               |

#### mxapiasset — Asset

| Field            | Type      | Description                                          |
|------------------|-----------|------------------------------------------------------|
| `assetnum`       | string    | Asset number (PK)                                    |
| `siteid`         | string    | Site identifier (composite PK)                       |
| `orgid`          | string    | Organization identifier                              |
| `description`    | string    | Asset description                                    |
| `status`         | string    | Asset status (e.g., `OPERATING`, `NOT_READY`, `DECOMMISSIONED`) |
| `statusdate`     | datetime  | Date/time status last changed                        |
| `assettype`      | string    | Asset type                                           |
| `location`       | string    | Current location identifier                          |
| `parent`         | string    | Parent asset number                                  |
| `serialnum`      | string    | Serial number                                        |
| `vendor`         | string    | Vendor identifier                                    |
| `manufacturer`   | string    | Manufacturer identifier                              |
| `installdate`    | datetime  | Installation date                                    |
| `warrantyexpdate`| datetime  | Warranty expiry date                                 |
| `totdowntime`    | decimal   | Total downtime (hours)                               |
| `tottimeonsite`  | decimal   | Total time on site (hours)                           |
| `changedate`     | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`       | string    | Person who last changed the record                   |
| `classstructureid` | string  | Classification structure ID                          |
| `priority`       | integer   | Asset criticality/priority                           |
| `assetmeter`     | object[]  | Asset meters (child)                                 |
| `assetspec`      | object[]  | Asset specifications / classification attributes (child) |

#### mxapipo — Purchase Order

| Field           | Type      | Description                                          |
|-----------------|-----------|------------------------------------------------------|
| `ponum`         | string    | Purchase order number (PK)                           |
| `siteid`        | string    | Site identifier (composite PK)                       |
| `orgid`         | string    | Organization identifier                              |
| `description`   | string    | PO description                                       |
| `status`        | string    | PO status (e.g., `WAPPR`, `APPR`, `COMP`, `CLOSE`)  |
| `statusdate`    | datetime  | Date/time status last changed                        |
| `vendor`        | string    | Vendor identifier                                    |
| `vendorname`    | string    | Vendor name                                          |
| `orderdate`     | datetime  | Order date                                           |
| `requireddate`  | datetime  | Required delivery date                               |
| `totalcost`     | decimal   | Total cost of the PO                                 |
| `currency`      | string    | Currency code                                        |
| `fromsiteid`    | string    | Issuing site                                         |
| `tostoreloc`    | string    | Receiving storeroom location                         |
| `changedate`    | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`      | string    | Person who last changed the record                   |
| `poline`        | object[]  | PO lines (child)                                     |
| `poreceipt`     | object[]  | PO receipts (child)                                  |

#### mxapiinventory — Inventory

| Field          | Type      | Description                                          |
|----------------|-----------|------------------------------------------------------|
| `itemnum`      | string    | Item number (PK with siteid/storeloc)                |
| `storeloc`     | string    | Storeroom location (composite PK)                    |
| `siteid`       | string    | Site identifier (composite PK)                       |
| `orgid`        | string    | Organization identifier                              |
| `description`  | string    | Item description (from ITEM)                         |
| `category`     | string    | Inventory category                                   |
| `itemtype`     | string    | Item type (e.g., `ITEM`, `TOOL`, `MATERIAL`)         |
| `vendor`       | string    | Preferred vendor                                     |
| `unitcost`     | decimal   | Unit cost                                            |
| `curbal`       | decimal   | Current balance (quantity on hand)                   |
| `orderqty`     | decimal   | Order quantity                                       |
| `reorderpoint` | decimal   | Reorder point                                        |
| `maxlevel`     | decimal   | Maximum stocking level                               |
| `minlevel`     | decimal   | Minimum stocking level                               |
| `changedate`   | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`     | string    | Person who last changed the record                   |

#### mxapiinvbal — Inventory Balances

| Field          | Type      | Description                                          |
|----------------|-----------|------------------------------------------------------|
| `itemnum`      | string    | Item number (PK)                                     |
| `siteid`       | string    | Site identifier (composite PK)                       |
| `storeloc`     | string    | Storeroom identifier (composite PK)                  |
| `orgid`        | string    | Organization identifier                              |
| `lotnum`       | string    | Lot number (for lot-tracked items; composite PK)     |
| `binnum`       | string    | Bin number                                           |
| `curbal`       | decimal   | Current balance quantity                             |
| `stagingbin`   | boolean   | Whether this is a staging bin                        |
| `changeby`     | string    | Person who last changed                              |
| `changedate`   | datetime  | Date record was last changed (**incremental cursor**)|

#### mxapisr — Service Request

| Field          | Type      | Description                                          |
|----------------|-----------|------------------------------------------------------|
| `ticketid`     | string    | Ticket/SR number (PK)                                |
| `siteid`       | string    | Site identifier (composite PK)                       |
| `orgid`        | string    | Organization identifier                              |
| `summary`      | string    | SR summary / short description                       |
| `description`  | string    | Long description                                     |
| `status`       | string    | SR status (e.g., `NEW`, `QUEUED`, `INPROG`, `RESOLVED`, `CLOSED`) |
| `statusdate`   | datetime  | Date/time status last changed                        |
| `reportdate`   | datetime  | Date SR was reported                                 |
| `reportedby`   | string    | Reporter person identifier                           |
| `affectedperson` | string  | Affected person identifier                           |
| `owner`        | string    | Owner (person)                                       |
| `ownergroup`   | string    | Owner group                                          |
| `assetnum`     | string    | Related asset                                        |
| `location`     | string    | Related location                                     |
| `classstructureid` | string | Classification structure ID                         |
| `changedate`   | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`     | string    | Person who last changed                              |
| `wonum`        | string    | Related work order (if escalated)                    |
| `ticketspec`   | object[]  | SR specification attributes (child)                  |

#### mxapiperson — Person

| Field            | Type      | Description                                          |
|------------------|-----------|------------------------------------------------------|
| `personid`       | string    | Person identifier (PK)                               |
| `firstname`      | string    | First name                                           |
| `lastname`       | string    | Last name                                            |
| `displayname`    | string    | Display name                                         |
| `status`         | string    | Person status (e.g., `ACTIVE`, `INACTIVE`)           |
| `primaryemail`   | string    | Primary email address                                |
| `primaryphone`   | string    | Primary phone number                                 |
| `department`     | string    | Department                                           |
| `locationsite`   | string    | Home site                                            |
| `locationorg`    | string    | Home organization                                    |
| `changedate`     | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`       | string    | Person who last changed                              |
| `sms`            | string    | SMS number                                           |

#### mxapilocations — Location

| Field           | Type      | Description                                          |
|-----------------|-----------|------------------------------------------------------|
| `location`      | string    | Location identifier (PK)                             |
| `siteid`        | string    | Site identifier (composite PK)                       |
| `orgid`         | string    | Organization identifier                              |
| `description`   | string    | Location description                                 |
| `type`          | string    | Location type (e.g., `OPERATING`, `COURIER`, `REPAIR`) |
| `status`        | string    | Location status                                      |
| `statusdate`    | datetime  | Date/time status last changed                        |
| `parent`        | string    | Parent location identifier                           |
| `systemid`      | string    | Location system identifier                           |
| `changedate`    | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`      | string    | Person who last changed                              |

#### mxapiitem — Item Master

| Field           | Type      | Description                                          |
|-----------------|-----------|------------------------------------------------------|
| `itemnum`       | string    | Item number (PK)                                     |
| `orgid`         | string    | Organization identifier (composite PK)               |
| `description`   | string    | Item description                                     |
| `itemtype`      | string    | Item type (e.g., `ITEM`, `TOOL`, `MATERIAL`, `SERVICE`) |
| `status`        | string    | Item status (e.g., `ACTIVE`, `PENDOBS`, `OBSOLETE`)  |
| `unitofmeasure` | string    | Unit of measure                                      |
| `commoditygroup`| string    | Commodity group                                      |
| `commodity`     | string    | Commodity code                                       |
| `rotating`      | boolean   | Whether this is a rotating item                      |
| `lottype`       | string    | Lot type                                             |
| `changedate`    | datetime  | Date record was last changed (**incremental cursor**)|
| `changeby`      | string    | Person who last changed                              |

---

## Get Object Primary Keys

Primary keys are always composite in Maximo (most business objects are site/org-scoped). The schema endpoint confirms the key fields.

| OS Name          | Primary Key Fields                                  |
|------------------|-----------------------------------------------------|
| `mxapiwodetail`  | `wonum` + `siteid`                                  |
| `mxapiasset`     | `assetnum` + `siteid`                               |
| `mxapipo`        | `ponum` + `siteid`                                  |
| `mxapiinventory` | `itemnum` + `storeloc` + `siteid`                   |
| `mxapiinvbal`    | `itemnum` + `storeloc` + `siteid` + `lotnum` + `binnum` |
| `mxapisr`        | `ticketid` + `siteid`                               |
| `mxapiperson`    | `personid`                                          |
| `mxapilocations` | `location` + `siteid`                               |
| `mxapiitem`      | `itemnum` + `orgid`                                 |

The `siteid` and `orgid` fields are nearly always part of the key in Maximo. For upsert operations in the connector, concatenate the key fields with a separator (e.g., `wonum|siteid`) to form a stable row key.

Primary key fields can also be confirmed via the JSON schema endpoint:
```
GET /maximo/oslc/jsonschemas/mxapiwodetail?lean=1
```
Look for attributes with `"keyattribute": true` in the Maximo-specific properties.

---

## Object Ingestion Type

| Object           | Ingestion Type | Notes                                                          |
|------------------|----------------|----------------------------------------------------------------|
| `mxapiwodetail`  | `cdc`          | `changedate` available; no native delete-tracking via REST     |
| `mxapiasset`     | `cdc`          | `changedate` available; no native delete-tracking via REST     |
| `mxapipo`        | `cdc`          | `changedate` available; no native delete-tracking via REST     |
| `mxapiinventory` | `cdc`          | `changedate` available; no native delete-tracking via REST     |
| `mxapiinvbal`    | `snapshot`     | Balances change frequently; `changedate` may not be exposed on all versions — safest as snapshot |
| `mxapisr`        | `cdc`          | `changedate` available; no native delete-tracking via REST     |
| `mxapiperson`    | `cdc`          | `changedate` available                                         |
| `mxapilocations` | `cdc`          | `changedate` available; location master is relatively static   |
| `mxapiitem`      | `cdc`          | `changedate` available; item master is relatively static       |

**Delete tracking**: The Maximo REST API does not expose a native "deleted records" endpoint. Deletes are rare in Maximo (most records are logically deactivated via `status` change), so `cdc` (upserts only) is appropriate for most objects. If hard deletes must be detected, a periodic full snapshot comparison is required.

---

## Read API for Data Retrieval

### Endpoint Pattern

```
GET /maximo/oslc/os/{osname}?lean=1&oslc.pageSize={n}&oslc.select={fields}&oslc.where={filter}&oslc.orderBy={order}
Headers:
  apikey: <api_key_value>
  x-public-uri: https://<host>/maximo/oslc     (or /maximo/api for MAS)
```

### Query Parameters

| Parameter         | Required | Description                                                                       |
|-------------------|----------|-----------------------------------------------------------------------------------|
| `lean`            | Yes      | `lean=1` returns responses without OSLC namespace prefixes. Always set this.     |
| `oslc.select`     | No       | Comma-separated list of attributes to return. Use `*` for all. Default: all.     |
| `oslc.where`      | No       | Filter expression (see below).                                                    |
| `oslc.pageSize`   | No       | Number of records per page. Default: server-configured. Recommended: `100`–`200`. |
| `pageno`          | No       | Explicit page number for non-stable paging (1-based). Follow `nextPage` href instead. |
| `oslc.orderBy`    | No       | Sort expression. Prefix with `+` (asc) or `-` (desc). Example: `+changedate`.   |
| `stablepaging`    | No       | `stablepaging=1` creates in-memory cursor for forward-only paging. Better for large result sets. |
| `collectioncount` | No       | `collectioncount=1` includes `totalCount` and `totalPages` in `responseInfo`.    |
| `ignorecollectionref` | No  | `ignorecollectionref=1` removes child collection `href` references, reducing payload size. |
| `_dropnulls`      | No       | `_dropnulls=0` includes null-valued fields in the response. Default: null fields omitted. |

### Filtering with `oslc.where`

The `oslc.where` syntax is similar to SQL WHERE but uses OSLC operators:

```
oslc.where=status="APPR"
oslc.where=status in ["WAPPR","APPR","INPRG"]
oslc.where=changedate>"2024-01-01T00:00:00+00:00"
oslc.where=changedate>"2024-01-01T00:00:00+00:00" and siteid="BEDFORD"
oslc.where=priority>=1 and priority<=3
```

**Operator reference:**

| Operator | Meaning       | Data type note                      |
|----------|---------------|-------------------------------------|
| `=`      | equals        | Strings/dates in double quotes      |
| `!=`     | not equals    | Strings/dates in double quotes      |
| `>`      | greater than  | Dates in ISO format; numbers unquoted |
| `>=`     | >=            |                                     |
| `<`      | less than     |                                     |
| `<=`     | <=            |                                     |
| `in`     | value in list | `field in ["A","B","C"]`            |

**Null checks:**
- `status="*"` means NOT NULL
- `status!="*"` means IS NULL

**Date format**: ISO 8601 with timezone offset: `"2024-06-15T00:00:00+00:00"` or `"2024-06-15T00:00:00-05:00"`.

### Incremental Reads (Watermark Strategy)

All core objects expose a `changedate` field that Maximo updates whenever a record (including child objects) is modified. Use this as the incremental cursor.

**Pattern:**

1. On full load: read all records with `oslc.orderBy=+changedate`.
2. Track the maximum `changedate` seen.
3. On subsequent runs: filter with `oslc.where=changedate>"<last_watermark>"`.
4. Always use `oslc.orderBy=+changedate` so records arrive in order and partial batches can resume from the last processed `changedate`.

**Lookback**: Apply a short lookback (e.g., subtract 5 minutes from the watermark) to account for in-flight transactions during the previous batch.

**Example incremental request:**

```
GET /maximo/oslc/os/mxapiwodetail?lean=1
  &oslc.pageSize=200
  &oslc.select=wonum,siteid,orgid,description,status,statusdate,worktype,priority,
               assetnum,location,reportdate,actstart,actfinish,schedstart,schedfinish,
               reportedby,owner,ownergroup,glaccount,changedate,changeby,historyflag,
               istask,parent
  &oslc.where=changedate%3E%222024-06-15T00%3A00%3A00%2B00%3A00%22
  &oslc.orderBy=%2Bchangedate

Headers:
  apikey: <api_key>
```

(URL-encoded: `%3E` = `>`, `%22` = `"`, `%2B` = `+`)

### Pagination

Maximo uses page-based pagination with next-page links.

**Request first page:**
```
GET /maximo/oslc/os/mxapiwodetail?lean=1&oslc.pageSize=200&oslc.where=...&oslc.orderBy=%2Bchangedate
```

**Response:**
```json
{
  "member": [
    {
      "wonum": "1001",
      "siteid": "BEDFORD",
      "status": "APPR",
      "changedate": "2024-05-10T14:23:00+00:00",
      ...
    }
  ],
  "responseInfo": {
    "href": "https://<host>/maximo/oslc/os/mxapiwodetail?lean=1&oslc.pageSize=200...",
    "nextPage": {
      "href": "https://<host>/maximo/oslc/os/mxapiwodetail?lean=1&oslc.pageSize=200&pageno=2&..."
    },
    "pagenum": 1,
    "totalCount": 1450,
    "totalPages": 8
  }
}
```

**Fetch next page:** follow `responseInfo.nextPage.href` verbatim. When `responseInfo.nextPage` is absent (or the `member` array is empty), pagination is complete.

**Stable paging** (`stablepaging=1`): The server retains an in-memory MboSet cursor for 5 minutes. The `nextPage.href` contains a `stableId` token. This avoids re-processing the SQL for each page and is more efficient for large result sets, but does not support backward navigation. Session expires after 5 minutes of idle time (`mxe.oslc.idleexiry`).

**Page number paging** (`pageno`): Pass `pageno=N` as a query parameter instead of following the `nextPage.href`. Less reliable for large result sets if records are being written concurrently.

### Example: Full Request and Response

**Request:**
```
GET /maximo/oslc/os/mxapiasset?lean=1&oslc.pageSize=2
  &oslc.select=assetnum,siteid,description,status,location,installdate,changedate
  &oslc.where=changedate%3E%222024-01-01T00%3A00%3A00%2B00%3A00%22
  &oslc.orderBy=%2Bchangedate
  &collectioncount=1
apikey: <api_key>
```

**Response (200 OK):**
```json
{
  "member": [
    {
      "href": "https://<host>/maximo/oslc/os/mxapiasset/_QkVERk9SRC9BNjAwMg--",
      "assetnum": "A6002",
      "siteid": "BEDFORD",
      "description": "Highway Tractor, Class 8 Truck",
      "status": "NOT_READY",
      "location": "DALTERM",
      "installdate": "2018-03-15T00:00:00+00:00",
      "changedate": "2024-03-22T09:14:33+00:00",
      "_rowstamp": "36654"
    },
    {
      "href": "https://<host>/maximo/oslc/os/mxapiasset/_QkVERk9SRC9BNjAwMw--",
      "assetnum": "A6003",
      "siteid": "BEDFORD",
      "description": "Pump Centrifugal 100HP",
      "status": "OPERATING",
      "location": "PUMP-STATION-1",
      "installdate": "2019-07-01T00:00:00+00:00",
      "changedate": "2024-05-05T11:42:00+00:00",
      "_rowstamp": "36780"
    }
  ],
  "responseInfo": {
    "href": "https://<host>/maximo/oslc/os/mxapiasset?lean=1&oslc.pageSize=2...",
    "nextPage": {
      "href": "https://<host>/maximo/oslc/os/mxapiasset?lean=1&oslc.pageSize=2&pageno=2..."
    },
    "pagenum": 1,
    "totalCount": 3842,
    "totalPages": 1922
  }
}
```

**Last page response (no nextPage):**
```json
{
  "member": [
    { "assetnum": "Z9999", ... }
  ],
  "responseInfo": {
    "href": "...",
    "pagenum": 1922
  }
}
```

### Rate Limits

IBM Maximo does not publish a fixed external rate limit. Effective limits depend on:
- Maximo server hardware and thread pool configuration (`mxe.oslc.maxpagesize` — default max page size)
- Auto-paging thresholds configured per object structure
- Database query performance

**Practical guidance:**
- Use `oslc.pageSize` of `100`–`500` depending on object complexity. Very large pages (1000+) can cause out-of-memory on the server.
- Do not make concurrent parallel requests unless the Maximo instance is sized for it.
- On HTTP 500 errors, apply exponential backoff with jitter, starting at 5 seconds.
- On HTTP 429 (if the instance has throttling enabled), back off according to the `Retry-After` header if present, otherwise use 60-second retry.

### Error Responses

Standard HTTP status codes:

| Status | Meaning                                                          |
|--------|------------------------------------------------------------------|
| 200    | Success                                                          |
| 400    | Bad Request — invalid query parameter or filter syntax           |
| 401    | Unauthorized — invalid or expired API key / session             |
| 403    | Forbidden — insufficient privileges for the requested OS        |
| 404    | Not Found — OS name does not exist or record not found          |
| 500    | Internal Server Error — server-side failure; retry with backoff |

**Error response body (400/500):**
```json
{
  "Error": {
    "statusCode": "400",
    "reasonCode": "BMXAA6819E",
    "message": "BMXAA6819E - The value 'FOO' is not valid for the attribute 'status'.",
    "extendedError": { ... }
  }
}
```

For batch/validation errors (PATCH/POST with `batcherror: 1` header):
```json
{
  "attrerrors": [
    {
      "Error": {
        "errorattrname": "location",
        "errorobjpath": "asset",
        "reasonCode": "BMXAA2661E",
        "message": "BMXAA2661E - Location YES is not a valid location.",
        "statusCode": "400"
      }
    }
  ]
}
```

---

## Field Type Mapping

| Maximo Type    | JSON Type (lean=1)  | Standard Type   | Notes                                                     |
|----------------|---------------------|-----------------|-----------------------------------------------------------|
| ALN (text)     | `string`            | string          |                                                           |
| UPPER (text)   | `string`            | string          | Values stored uppercase                                   |
| INTEGER        | `integer`           | integer         |                                                           |
| DECIMAL        | `number`            | decimal/float   |                                                           |
| AMOUNT         | `number`            | decimal         | Financial amount                                          |
| YORN (boolean) | `boolean`           | boolean         | `true`/`false` in lean mode                               |
| DATE           | `string`            | date            | ISO 8601 date string: `"2024-05-10"`                      |
| DATETIME       | `string`            | timestamp       | ISO 8601 with timezone: `"2024-05-10T14:23:00+00:00"`    |
| DURATION       | `number`            | decimal         | Duration in hours                                         |
| LONGALN        | `string`            | string          | Long text / notes field                                   |
| CLOB           | `string`            | string          | Long text (character large object)                        |
| BLOB           | TBD                 | binary          | Binary data — use attachments API, not direct fields      |
| GL (account)   | `string`            | string          | GL account in component format                            |

**Lean mode note**: Without `lean=1`, all field names are prefixed with the OSLC namespace (`spi:`) and boolean values are returned as `"0"`/`"1"` strings. Always use `lean=1` for connector implementations.

**Datetime timezone**: All `DATETIME` fields are returned with the timezone offset of the Maximo server. The connector should normalize to UTC on ingest.

---

## Sources and References

| Source Type   | URL                                                                                       | Confidence | What it confirmed                                        |
|---------------|-------------------------------------------------------------------------------------------|------------|----------------------------------------------------------|
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/                           | High       | Overview, auth methods, query parameters, pagination     |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/authentication/auth        | High       | Auth methods: MAXAUTH, BASIC, FORM, MAS API Key          |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/authentication/apikey      | High       | API key creation, header vs query param, /api route      |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/filtering            | High       | oslc.where syntax, operators, date format (ISO 8601)     |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/sort_and_paging      | High       | oslc.pageSize, oslc.orderBy, stablepaging, responseInfo  |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/selecting            | High       | oslc.select, lean=1, _dropnulls, collectioncount         |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/jsonschema/jsonschema      | High       | /oslc/jsonschemas/{osname} endpoint, addschema=1 param   |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/apihome/apihome            | High       | /oslc vs /api routes, /oslc/apimeta listing              |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/oas                        | High       | OpenAPI/Swagger endpoint at /maximo/oslc/oas             |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/batcherror                 | High       | Error response JSON format, reasonCode, statusCode       |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/performance                | High       | Performance guidance, no published rate limits           |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-nodejs-rest-client (resourceset.js)            | High       | Base path /maximo/oslc/os/, lean param, oslc query params |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-java-rest-client (README)                       | High       | Auth options (maxauth/basic/form), mxwodetail/MXPO/mxsr  |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-nodejs-rest-client (README)                     | High       | Auth cookie flow, MXWODETAIL fields (wonum, status, etc.)|
| Airbyte       | N/A — No IBM Maximo connector found in Airbyte catalog                                    | N/A        | Not available                                            |
| Fivetran      | N/A — No IBM Maximo connector found in Fivetran catalog                                   | N/A        | Not available                                            |

---

## Research Log

| Source Type   | URL                                                                                       | Accessed (UTC) | Confidence | What it confirmed                                   |
|---------------|-------------------------------------------------------------------------------------------|----------------|------------|-----------------------------------------------------|
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/                           | 2026-07-15     | High       | Documentation structure and sections                |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/authentication/auth        | 2026-07-15     | High       | Auth methods: maxauth header, LDAP BASIC, FORM      |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/authentication/apikey      | 2026-07-15     | High       | API key creation endpoint, apikey header usage, /api route |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/filtering            | 2026-07-15     | High       | oslc.where operators, ISO date format, range filtering |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/sort_and_paging      | 2026-07-15     | High       | oslc.pageSize, stablepaging, responseInfo structure |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/selecting            | 2026-07-15     | High       | oslc.select, lean=1, collectioncount, _dropnulls    |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/query/child               | 2026-07-15     | High       | Child object query syntax                           |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/jsonschema/jsonschema      | 2026-07-15     | High       | Schema endpoint /oslc/jsonschemas/{osname}          |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/apihome/apihome            | 2026-07-15     | High       | /api and /oslc routes, /oslc/apimeta catalog        |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/oas                        | 2026-07-15     | High       | OAS3 Swagger at /maximo/oslc/oas                   |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/batcherror                 | 2026-07-15     | High       | Error response format, reasonCode field             |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/performance                | 2026-07-15     | High       | Rate limit guidance (no fixed limit published)      |
| Official Docs | https://ibm-maximo-dev.github.io/maximo-restapi-documentation/hierarchical/hierarchical  | 2026-07-15     | High       | Location hierarchy endpoint patterns                |
| OSS SDK       | https://raw.githubusercontent.com/ibm-maximo-dev/maximo-nodejs-rest-client/master/resources/resourceset.js | 2026-07-15 | High | REST_PATH = '/maximo/oslc/os/', oslc param names |
| OSS SDK       | https://raw.githubusercontent.com/ibm-maximo-dev/maximo-nodejs-rest-client/master/maximofactory.js | 2026-07-15 | High | Auth types: maxauth, form; auth_scheme path |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-java-rest-client README                         | 2026-07-15     | High       | Auth options, mxwodetail/MXPO/mxsr OS names         |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-nodejs-rest-client README                       | 2026-07-15     | High       | MXWODETAIL fields, auth flow, select/where/pagesize |
| OSS SDK       | https://github.com/ibm-maximo-dev/maximo-nodejs-sample README                            | 2026-07-15     | Medium     | CRUD routes, MXWODETAIL as canonical example object |
