import copy
import logging

from spaceone.core.manager import BaseManager

from ..connector.bigquery_connector import BigqueryConnector

_LOGGER = logging.getLogger("spaceone")


# Google Cloud Billing 데이터의 additional_info 필드 기본 메타데이터 정의
# SpaceONE UI에서 additional_info 필드들의 표시 방식과 그룹화 옵션을 정의합니다.
# Google Cloud Billing 데이터의 주요 필드들에 대한 메타데이터를 제공하여
# 사용자가 데이터를 더 효과적으로 분석할 수 있도록 지원합니다.
_DEFAULT_METADATA_ADDITIONAL_INFO = {
    # SpaceONE UI 기본 필수 항목 (6개) - 항상 최상단에 위치
    "Project": {
        "name": "Project",
        "key": "Project",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    "Provider": {
        "name": "Provider",
        "key": "Provider",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    "Service Account": {
        "name": "Service Account",
        "key": "Service Account",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    "Product": {
        "name": "Product",
        "key": "Product",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    "Region": {
        "name": "Region",
        "key": "Region",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    "Usage Type": {
        "name": "Usage Type",
        "key": "Usage Type",
        "type": "str",
        "options": {
            "is_optional": True,
            "group_by": True,
            "searchable": True,
        },
    },
    # 프로젝트 관련 정보 (추가 세부사항)
    "Project ID": {
        "name": "Project ID",
        "key": "Project ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Project Name": {
        "name": "Project Name",
        "key": "Project Name",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Project Number": {
        "name": "Project Number",
        "key": "Project Number",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 서비스 관련 정보
    "Service Description": {
        "name": "Service Description",
        "key": "Service Description",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Service ID": {
        "name": "Service ID",
        "key": "Service ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "SKU Description": {
        "name": "SKU Description",
        "key": "SKU Description",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "SKU ID": {
        "name": "SKU ID",
        "key": "SKU ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 지역 관련 정보
    "Location Country": {
        "name": "Location Country",
        "key": "Location Country",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Location Region": {
        "name": "Location Region",
        "key": "Location Region",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Location Zone": {
        "name": "Location Zone",
        "key": "Location Zone",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Location Location": {
        "name": "Location Location",
        "key": "Location Location",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 사용량 관련 정보
    "Usage Unit": {
        "name": "Usage Unit",
        "key": "Usage Unit",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Usage Amount": {
        "name": "Usage Amount",
        "key": "Usage Amount",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Usage Start Time": {
        "name": "Usage Start Time",
        "key": "Usage Start Time",
        "type": "datetime",
        "options": {
            "is_optional": False,
            "group_by": False,
            "searchable": False,
        },
    },
    "Usage End Time": {
        "name": "Usage End Time",
        "key": "Usage End Time",
        "type": "datetime",
        "options": {
            "is_optional": False,
            "group_by": False,
            "searchable": False,
        },
    },
    # 리소스 관련 정보
    "Resource Name": {
        "name": "Resource Name",
        "key": "Resource Name",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": False,  # 고유값이 많아 그룹화에 부적합
            "searchable": True,
        },
    },
    "Resource Global Name": {
        "name": "Resource Global Name",
        "key": "Resource Global Name",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": False,  # 고유값이 많아 그룹화에 부적합
            "searchable": True,
        },
    },
    # 청구 관련 정보
    "Billing Account ID": {
        "name": "Billing Account ID",
        "key": "Billing Account ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Invoice Month": {
        "name": "Invoice Month",
        "key": "Invoice Month",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 크레딧 관련 정보
    "Credit Type": {
        "name": "Credit Type",
        "key": "Credit Type",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Credit Name": {
        "name": "Credit Name",
        "key": "Credit Name",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Credits Total Amount": {
        "name": "Credits Total Amount",
        "key": "Credits Total Amount",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Credits Detail": {
        "name": "Credits Detail",
        "key": "Credits Detail",
        "type": "dict",
        "options": {
            "is_optional": False,
            "group_by": False,  # 구조적 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    # 기술적 메타데이터
    "Export Time": {
        "name": "Export Time",
        "key": "Export Time",
        "type": "datetime",
        "options": {
            "is_optional": False,
            "group_by": False,
            "searchable": False,
        },
    },
    "Currency": {
        "name": "Currency",
        "key": "Currency",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Transaction Type": {
        "name": "Transaction Type",
        "key": "Transaction Type",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Cost Type": {
        "name": "Cost Type",
        "key": "Cost Type",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Seller Name": {
        "name": "Seller Name",
        "key": "Seller Name",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 라벨 관련 정보 (구조적 데이터)
    "Labels": {
        "name": "Labels",
        "key": "Labels",
        "type": "dict",
        "options": {
            "is_optional": False,
            "group_by": False,  # 구조적 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "System Labels": {
        "name": "System Labels",
        "key": "System Labels",
        "type": "dict",
        "options": {
            "is_optional": False,
            "group_by": False,  # 구조적 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    # 추가 비용 관련 정보 (계산 필드)
    "Cost After Credits": {
        "name": "Cost After Credits",
        "key": "Cost After Credits",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Cost At List": {
        "name": "Cost At List",
        "key": "Cost At List",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Cost with Credits": {
        "name": "Cost with Credits",
        "key": "Cost with Credits",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Cost at Effective Price Default": {
        "name": "Cost at Effective Price Default",
        "key": "Cost at Effective Price Default",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Cost at List Consumption Model": {
        "name": "Cost at List Consumption Model",
        "key": "Cost at List Consumption Model",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Currency Conversion Rate": {
        "name": "Currency Conversion Rate",
        "key": "Currency Conversion Rate",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    # 사용량 추가 정보
    "Usage Amount in Pricing Units": {
        "name": "Usage Amount in Pricing Units",
        "key": "Usage Amount in Pricing Units",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Pricing Unit": {
        "name": "Pricing Unit",
        "key": "Pricing Unit",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # Price 중첩 구조 필드들
    "Price Effective Price": {
        "name": "Price Effective Price",
        "key": "Price Effective Price",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price List Price": {
        "name": "Price List Price",
        "key": "Price List Price",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price Unit": {
        "name": "Price Unit",
        "key": "Price Unit",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # Consumption Model 중첩 구조 필드들
    "Consumption Model ID": {
        "name": "Consumption Model ID",
        "key": "Consumption Model ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Consumption Model Description": {
        "name": "Consumption Model Description",
        "key": "Consumption Model Description",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # Adjustment Info 중첩 구조 필드들
    "Adjustment Info ID": {
        "name": "Adjustment Info ID",
        "key": "Adjustment Info ID",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Adjustment Info Description": {
        "name": "Adjustment Info Description",
        "key": "Adjustment Info Description",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Adjustment Info Mode": {
        "name": "Adjustment Info Mode",
        "key": "Adjustment Info Mode",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Adjustment Info Type": {
        "name": "Adjustment Info Type",
        "key": "Adjustment Info Type",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    # 기타 필드들
    "Publisher Type": {
        "name": "Publisher Type",
        "key": "Publisher Type",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": True,
            "searchable": True,
        },
    },
    "Ancestry Numbers": {
        "name": "Ancestry Numbers",
        "key": "Ancestry Numbers",
        "type": "str",
        "options": {
            "is_optional": False,
            "group_by": False,  # 고유값이 많아 그룹화에 부적합
            "searchable": True,
        },
    },
    "Resource Tags": {
        "name": "Resource Tags",
        "key": "Resource Tags",
        "type": "dict",
        "options": {
            "is_optional": False,
            "group_by": False,  # 구조적 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price Tier Start Amount": {
        "name": "Price Tier Start Amount",
        "key": "Price Tier Start Amount",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price Pricing Unit Quantity": {
        "name": "Price Pricing Unit Quantity",
        "key": "Price Pricing Unit Quantity",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price Effective Price Default": {
        "name": "Price Effective Price Default",
        "key": "Price Effective Price Default",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
    "Price List Price Consumption Model": {
        "name": "Price List Price Consumption Model",
        "key": "Price List Price Consumption Model",
        "type": "float",
        "options": {
            "is_optional": False,
            "group_by": False,  # 수치 데이터는 그룹화 부적합
            "searchable": False,
        },
    },
}


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
            # additional_info 필드 메타데이터 추가
            "additional_info": copy.deepcopy(_DEFAULT_METADATA_ADDITIONAL_INFO),
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
