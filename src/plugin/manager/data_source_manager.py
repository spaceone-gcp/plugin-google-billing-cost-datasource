import logging

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.manager import BaseManager
except ImportError:
    # Mock for local development
    class BaseManager:
        """Mock BaseManager for local development"""
        pass

from ..connector.bigquery_connector import BigqueryConnector

_LOGGER = logging.getLogger("spaceone")


class DataSourceManager(BaseManager):
    @staticmethod
    def init_response(options: dict) -> dict:
        metadata = {
            "currency": "KRW",
            "supported_secret_types": ["MANUAL"],
            "use_account_routing": False,
            "data_source_rules": [
                {
                    "name": "match_service_account",
                    "conditions_policy": "ALWAYS",
                    "actions": {
                        "match_service_account": {
                            "source": "additional_info.Project ID",
                            "target": "data.project_id",
                        }
                    },
                    "options": {"stop_processing": True},
                }
            ],
        }
        if options.get("use_account_routing", False):
            metadata["use_account_routing"] = True
            if account_match_key := options.get(
                "account_match_key", "additional_info.Project ID"
            ):
                metadata["account_match_key"] = account_match_key

        return {"metadata": metadata}

    @staticmethod
    def verify_plugin(
        options: dict, secret_data: dict, domain_id: str, schema: str = None
    ) -> None:
        """플러그인 검증 - 데이터 소스 타입에 따라 적절한 커넥터로 검증"""
        source = options.get("source", "gcs")

        # 데이터 소스 타입 자동 감지
        if not source or source not in ["bigquery", "gcs"]:
            # BigQuery 필수 파라미터가 있으면 BigQuery로 판단
            bigquery_required = [
                "billing_export_project_id",
                "billing_dataset_id",
                "billing_account_id",
            ]
            if all(key in options for key in bigquery_required):
                source = "bigquery"
            else:
                source = "gcs"

        _LOGGER.info(f"[verify_plugin] Detected source: {source}")

        if source == "bigquery":
            # BigQuery 검증
            bigquery_connector = BigqueryConnector()
            bigquery_connector.create_session(options, secret_data, schema)
            _LOGGER.info("[verify_plugin] BigQuery connection verified successfully")
        else:
            # GCS 검증
            from ..connector.gcs_connector import GcsConnector

            gcs_connector = GcsConnector()
            gcs_connector.create_session(options, secret_data, schema)

            # 기본 연결 테스트 (bucket_name이나 base_url 확인)
            if bucket_name := options.get("bucket_name"):
                # GCS 버킷 접근 테스트
                try:
                    gcs_connector.list_gcs_files(bucket_name, limit=1)
                    _LOGGER.info(
                        f"[verify_plugin] GCS bucket '{bucket_name}' access verified"
                    )
                except Exception as e:
                    _LOGGER.error(f"[verify_plugin] GCS bucket access failed: {e}")
                    raise
            elif base_url := options.get("base_url"):
                # HTTP URL 접근 테스트
                try:
                    gcs_connector.test_connection(base_url)
                    _LOGGER.info(
                        f"[verify_plugin] HTTP URL '{base_url}' access verified"
                    )
                except Exception as e:
                    _LOGGER.error(f"[verify_plugin] HTTP URL access failed: {e}")
                    raise
            else:
                _LOGGER.info(
                    "[verify_plugin] No specific verification target, connection setup verified"
                )
