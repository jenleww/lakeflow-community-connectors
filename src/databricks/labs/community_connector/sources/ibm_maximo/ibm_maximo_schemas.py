"""Static schema, metadata, and field-selection definitions for the IBM
Maximo (OSLC REST) connector.

Maximo exposes business objects as *Object Structures* (OS) at
``/maximo/oslc/os/{osname}``. In ``lean=1`` mode each record is a flat JSON
object whose keys are the MBO attribute names. We model a curated subset of
scalar attributes per object structure as typed Spark columns based on the
static field references in ``ibm_maximo_api_doc.md``.

Design choices:
  * Scalar attributes only. Child collections (``wplabor``, ``poline``,
    ``assetmeter`` ...) are large nested arrays that require explicit
    ``oslc.select`` expansion and vary widely by deployment; they are left
    out of the projected schema. The connector requests exactly the columns
    declared here via ``oslc.select`` so the response shape stays stable.
  * ``LongType`` over ``IntegerType`` for integer attributes to avoid
    overflow.
  * ``DoubleType`` for decimal / amount / duration attributes.
  * Datetimes are surfaced as ``StringType`` (ISO-8601 with offset, as
    returned by Maximo in lean mode). The framework coerces on ingest.
"""

from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Per-table schemas
# ---------------------------------------------------------------------------

WODETAIL_SCHEMA = StructType(
    [
        StructField("wonum", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("description", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("worktype", StringType(), True),
        StructField("priority", LongType(), True),
        StructField("reportdate", StringType(), True),
        StructField("actstart", StringType(), True),
        StructField("actfinish", StringType(), True),
        StructField("schedstart", StringType(), True),
        StructField("schedfinish", StringType(), True),
        StructField("assetnum", StringType(), True),
        StructField("location", StringType(), True),
        StructField("reportedby", StringType(), True),
        StructField("owner", StringType(), True),
        StructField("ownerperson", StringType(), True),
        StructField("ownergroup", StringType(), True),
        StructField("glaccount", StringType(), True),
        StructField("changedate", StringType(), True),
        StructField("changeby", StringType(), True),
        StructField("historyflag", BooleanType(), True),
        StructField("istask", BooleanType(), True),
        StructField("parent", StringType(), True),
    ]
)

ASSET_SCHEMA = StructType(
    [
        StructField("assetnum", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("description", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("assettype", StringType(), True),
        StructField("location", StringType(), True),
        StructField("parent", StringType(), True),
        StructField("serialnum", StringType(), True),
        StructField("vendor", StringType(), True),
        StructField("manufacturer", StringType(), True),
        StructField("installdate", StringType(), True),
        StructField("warrantyexpdate", StringType(), True),
        StructField("totdowntime", DoubleType(), True),
        StructField("tottimeonsite", DoubleType(), True),
        StructField("changedate", StringType(), True),
        StructField("changeby", StringType(), True),
        StructField("classstructureid", StringType(), True),
        StructField("priority", LongType(), True),
    ]
)

PO_SCHEMA = StructType(
    [
        StructField("ponum", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("description", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("vendor", StringType(), True),
        StructField("vendorname", StringType(), True),
        StructField("orderdate", StringType(), True),
        StructField("requireddate", StringType(), True),
        StructField("totalcost", DoubleType(), True),
        StructField("currency", StringType(), True),
        StructField("fromsiteid", StringType(), True),
        StructField("tostoreloc", StringType(), True),
        StructField("changedate", StringType(), True),
        StructField("changeby", StringType(), True),
    ]
)

# Inventory is keyed on the storeroom ``location`` (Maximo's INVENTORY MBO
# exposes the storeroom as ``location``, not ``storeloc``). ``changedate`` is
# not a queryable OSLC property on this object structure, so the cursor is
# ``statusdate``; balances/costs are surfaced via the INVBALANCES child and
# ``curbaltotal`` rather than a scalar ``curbal`` here.
INVENTORY_SCHEMA = StructType(
    [
        StructField("itemnum", StringType(), False),
        StructField("location", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("itemsetid", StringType(), True),
        StructField("itemtype", StringType(), True),
        StructField("curbaltotal", DoubleType(), True),
        StructField("avblbalance", DoubleType(), True),
        StructField("orderqty", DoubleType(), True),
        StructField("reorder", BooleanType(), True),
        StructField("maxlevel", DoubleType(), True),
        StructField("minlevel", DoubleType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
    ]
)

# Inventory Balances. ``invbalancesid`` is the stable, unique surrogate key
# (Maximo INVBALANCES). The storeroom is ``location`` (not ``storeloc``);
# ``binnum`` and ``lotnum`` are only populated for bin-/lot-tracked items, so
# they are nullable. There is no ``changedate``/``changeby`` on this MBO.
INVBAL_SCHEMA = StructType(
    [
        StructField("invbalancesid", LongType(), False),
        StructField("itemnum", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("location", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("itemsetid", StringType(), True),
        StructField("itemtype", StringType(), True),
        StructField("lotnum", StringType(), True),
        StructField("binnum", StringType(), True),
        StructField("curbal", DoubleType(), True),
        StructField("physcnt", DoubleType(), True),
        StructField("physcntdate", StringType(), True),
        StructField("stagingbin", BooleanType(), True),
        StructField("reconciled", BooleanType(), True),
    ]
)

SR_SCHEMA = StructType(
    [
        StructField("ticketid", StringType(), False),
        # siteid/orgid are frequently unset on service requests (they may be
        # reported before an owning site/org is assigned), so they are
        # nullable and ticketid alone is the primary key.
        StructField("siteid", StringType(), True),
        StructField("orgid", StringType(), True),
        StructField("summary", StringType(), True),
        StructField("description", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("reportdate", StringType(), True),
        StructField("reportedby", StringType(), True),
        StructField("affectedperson", StringType(), True),
        StructField("owner", StringType(), True),
        StructField("ownergroup", StringType(), True),
        StructField("assetnum", StringType(), True),
        StructField("location", StringType(), True),
        StructField("classstructureid", StringType(), True),
        StructField("changedate", StringType(), True),
        StructField("changeby", StringType(), True),
        StructField("wonum", StringType(), True),
    ]
)

# The PERSON MBO does not expose email/phone/department as scalar attributes
# (they live in child collections) and has no ``changedate``; ``statusdate`` is
# the cursor. Only scalar attributes actually returned in lean mode are kept.
PERSON_SCHEMA = StructType(
    [
        StructField("personid", StringType(), False),
        StructField("firstname", StringType(), True),
        StructField("lastname", StringType(), True),
        StructField("displayname", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("deviceclass", LongType(), True),
        StructField("loctoservreq", BooleanType(), True),
        StructField("languserupdated", BooleanType(), True),
    ]
)

LOCATIONS_SCHEMA = StructType(
    [
        StructField("location", StringType(), False),
        StructField("siteid", StringType(), False),
        StructField("orgid", StringType(), True),
        StructField("description", StringType(), True),
        StructField("type", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("parent", StringType(), True),
        StructField("systemid", StringType(), True),
        StructField("changedate", StringType(), True),
        StructField("changeby", StringType(), True),
    ]
)

# Items are defined at the item-set level, not the org level, so ``orgid`` is
# not populated on the ITEM MBO; ``itemsetid`` is the scoping key. ``changedate``
# is not a queryable OSLC property here, so the cursor is ``statusdate``.
ITEM_SCHEMA = StructType(
    [
        StructField("itemnum", StringType(), False),
        StructField("itemsetid", StringType(), False),
        StructField("description", StringType(), True),
        StructField("itemtype", StringType(), True),
        StructField("status", StringType(), True),
        StructField("statusdate", StringType(), True),
        StructField("commoditygroup", StringType(), True),
        StructField("commodity", StringType(), True),
        StructField("rotating", BooleanType(), True),
        StructField("lottype", StringType(), True),
    ]
)


TABLE_SCHEMAS: dict[str, StructType] = {
    "mxapiwodetail": WODETAIL_SCHEMA,
    "mxapiasset": ASSET_SCHEMA,
    "mxapipo": PO_SCHEMA,
    "mxapiinventory": INVENTORY_SCHEMA,
    "mxapiinvbal": INVBAL_SCHEMA,
    "mxapisr": SR_SCHEMA,
    "mxapiperson": PERSON_SCHEMA,
    "mxapilocations": LOCATIONS_SCHEMA,
    "mxapiitem": ITEM_SCHEMA,
}

SUPPORTED_TABLES: list[str] = list(TABLE_SCHEMAS.keys())


# ---------------------------------------------------------------------------
# Per-table metadata
# ---------------------------------------------------------------------------
#
# All CDC tables share ``changedate`` as the incremental cursor. Maximo has
# no native delete-tracking over REST, so CDC tables are upsert-only ("cdc").
# ``mxapiinvbal`` is a snapshot: balances change constantly and changedate is
# not reliably exposed on all Maximo versions.

TABLE_METADATA: dict[str, dict] = {
    "mxapiwodetail": {
        "primary_keys": ["wonum", "siteid"],
        "cursor_field": "changedate",
        "ingestion_type": "cdc",
    },
    "mxapiasset": {
        "primary_keys": ["assetnum", "siteid"],
        "cursor_field": "changedate",
        "ingestion_type": "cdc",
    },
    "mxapipo": {
        "primary_keys": ["ponum", "siteid"],
        "cursor_field": "changedate",
        "ingestion_type": "cdc",
    },
    "mxapiinventory": {
        "primary_keys": ["itemnum", "location", "siteid"],
        "cursor_field": "statusdate",
        "ingestion_type": "cdc",
    },
    "mxapiinvbal": {
        "primary_keys": ["invbalancesid"],
        "ingestion_type": "snapshot",
    },
    "mxapisr": {
        "primary_keys": ["ticketid"],
        "cursor_field": "changedate",
        "ingestion_type": "cdc",
    },
    "mxapiperson": {
        "primary_keys": ["personid"],
        "cursor_field": "statusdate",
        "ingestion_type": "cdc",
    },
    "mxapilocations": {
        "primary_keys": ["location", "siteid"],
        "cursor_field": "changedate",
        "ingestion_type": "cdc",
    },
    "mxapiitem": {
        "primary_keys": ["itemnum", "itemsetid"],
        "cursor_field": "statusdate",
        "ingestion_type": "cdc",
    },
}


# ---------------------------------------------------------------------------
# oslc.select field lists — derived from the declared schemas so the request
# projection always matches the columns the connector expects to parse.
# ---------------------------------------------------------------------------

TABLE_SELECT_FIELDS: dict[str, list[str]] = {
    table: [f.name for f in schema.fields]
    for table, schema in TABLE_SCHEMAS.items()
}
