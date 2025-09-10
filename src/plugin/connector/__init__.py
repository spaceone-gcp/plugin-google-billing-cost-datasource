# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from plugin.connector.bigquery_connector import BigqueryConnector as BigqueryConnector
    __all__ = ["BigqueryConnector"]
except ImportError as e:
    # Mock for local development - spaceone 모듈이 없을 때 처리
    import logging
    _LOGGER = logging.getLogger("spaceone")
    _LOGGER.warning(f"Failed to import BigqueryConnector: {e}")
    
    class BigqueryConnector:
        """Mock BigqueryConnector for local development"""
        def __init__(self, *args, **kwargs):
            pass
    
    __all__ = ["BigqueryConnector"]
