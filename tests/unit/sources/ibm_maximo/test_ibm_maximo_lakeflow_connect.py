"""Tests for the IBM Maximo (OSLC REST) LakeflowConnect connector.

Runs against the in-process source simulator described by
``source_simulator/specs/ibm_maximo/``. The connector issues::

    GET /maximo/oslc/os/{osname}?lean=1&oslc.pageSize=N&oslc.select=...
        &oslc.where=changedate>"..." and changedate<="..."&oslc.orderBy=+changedate

which a custom handler (``handlers/oslc:read_os``) serves from the
per-table corpus (bootstrapped from ``TABLE_SCHEMAS``).

Eight of the nine object structures are CDC tables on the ``changedate``
cursor and use ``SupportsPartitionedStream`` (partitioned reads); the
ninth, ``mxapiinvbal`` (Inventory Balances), is a snapshot table read on
the single-driver ``read_table`` path.

Stand-in credentials below are values of the right shape; the simulator
never validates them. ``page_size`` is pinned small so the 12-record
corpus spans multiple pages and the ``responseInfo.nextPage.href``
pagination path is exercised.
"""

from __future__ import annotations

from databricks.labs.community_connector.sources.ibm_maximo.ibm_maximo import (
    IbmMaximoLakeflowConnect,
)
from tests.unit.sources.test_partition_suite import (
    SupportsPartitionedStreamTests,
)
from tests.unit.sources.test_suite import LakeflowConnectTests


class TestIbmMaximoConnector(LakeflowConnectTests, SupportsPartitionedStreamTests):
    connector_class = IbmMaximoLakeflowConnect
    simulator_source = "ibm_maximo"
    sample_records = 50

    # Stand-in credentials — any values of the right shape work; the
    # simulator does not validate them.
    replay_config = {
        "base_url": "https://maximo.simulator.local",
        "api_key": "simulator-fake-key",
    }

    # Small page size forces the corpus across several pages, exercising the
    # nextPage.href pagination path for every table.
    table_configs = {
        table: {"page_size": "5"}
        for table in (
            "mxapiwodetail",
            "mxapiasset",
            "mxapipo",
            "mxapiinventory",
            "mxapiinvbal",
            "mxapisr",
            "mxapiperson",
            "mxapilocations",
            "mxapiitem",
        )
    }

    # Columns that are valid Maximo MBO attributes (the OSLC API accepts them
    # in oslc.select and returns them) but are simply unpopulated in the trial
    # sandbox this connector was recorded against. The corpus is seeded from
    # that live cassette, so no record exercises these columns and the
    # simulate-mode column-population invariant would otherwise flag them.
    # They remain in the schema because real Maximo deployments populate them.
    allow_null_columns = {
        "mxapiwodetail": {
            "priority",
            "actstart",
            "actfinish",
            "schedstart",
            "schedfinish",
            "ownerperson",
            "ownergroup",
            "glaccount",
        },
        "mxapiasset": {"parent", "warrantyexpdate", "tottimeonsite"},
        "mxapipo": {"vendorname", "currency", "fromsiteid", "tostoreloc"},
        "mxapisr": {"summary", "wonum"},
        "mxapiperson": {"deviceclass"},
        "mxapilocations": {"parent", "systemid"},
    }
