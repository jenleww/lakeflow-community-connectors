"""IBM Maximo (OSLC REST) source connector."""

from databricks.labs.community_connector.sources.ibm_maximo.ibm_maximo import (
    IbmMaximoLakeflowConnect,
)


from databricks.labs.community_connector.sparkpds import LakeflowSource


class IbmMaximoDataSource(LakeflowSource):
    _lakeflow_connect_cls = IbmMaximoLakeflowConnect
    # Override the Spark format name with the source name once this no
    # longer relies on UC connection-option injection. Kept as the default
    # "lakeflow_connect" for now so existing pipelines keep working.
    # _format_name = "ibm_maximo"


__all__ = [
    "IbmMaximoLakeflowConnect",
    "IbmMaximoDataSource",
]
