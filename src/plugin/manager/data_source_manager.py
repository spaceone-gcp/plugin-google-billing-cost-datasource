"""Google Cloud Billing 데이터 소스 매니저 모듈.

SpaceONE UI에서 additional_info 필드들의 표시 방식과 그룹화 옵션을 정의하는 매니저입니다.
"""

import copy
import logging
from typing import Optional

from spaceone.core.manager import BaseManager

from ..conf.cost_conf import DATA_SOURCE_TYPES

_LOGGER = logging.getLogger(__name__)

# Google Cloud Billing 데이터의 additional_info 필드 기본 메타데이터 정의
# SpaceONE UI에서 additional_info 필드들의 표시 방식과 그룹화 옵션을 정의합니다.
# Google Cloud Billing 데이터의 주요 필드들에 대한 메타데이터를 제공하여
# 사용자가 데이터를 더 효과적으로 분석할 수 있도록 지원합니다.

_DEFAULT_DATA_SOURCE_RULES = [
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
]

# 조건부_additional_info_필터링_PRD.md 문서 기준 33개 필드만 포함
_DEFAULT_METADATA_ADDITIONAL_INFO = {
    # 필수 고정 항목 (6개) - SpaceONE UI 기준 (항상 visible: True)
    "Project": {"name": "Project", "visible": True},
    "Provider": {"name": "Provider", "visible": True},
    "Service Account": {"name": "Service Account", "visible": True},
    "Product": {"name": "Product", "visible": True},
    "Region": {"name": "Region", "visible": True},
    "Usage Type": {"name": "Usage Type", "visible": True},
    # 프로젝트 계층 카테고리 (Project Hierarchy) - PRD 2.1.2 기준
    "Project Name": {"name": "Project Name", "visible": False},
    "Project Number": {"name": "Project Number", "visible": False},
    "Ancestry Numbers": {"name": "Ancestry Numbers", "visible": False},
    # 위치 정보 카테고리 (Location Data) - PRD 2.1.2 기준
    "Location Country": {"name": "Location Country", "visible": False},
    "Location Region": {"name": "Location Region", "visible": False},
    "Location Zone": {"name": "Location Zone", "visible": False},
    "Location Location": {"name": "Location Location", "visible": False},
    # 사용량 분석 카테고리 (Usage Analysis) - PRD 2.1.2 기준
    "Usage Unit": {"name": "Usage Unit", "visible": False},
    # 서비스 메타데이터 카테고리 (Service Metadata) - PRD 2.1.2 기준
    "Service Description": {"name": "Service Description", "visible": False},
    "Service ID": {"name": "Service ID", "visible": False},
    "SKU Description": {"name": "SKU Description", "visible": False},
    "SKU ID": {"name": "SKU ID", "visible": False},
    "Consumption Model Description": {
        "name": "Consumption Model Description",
        "visible": False,
    },
    "Consumption Model ID": {"name": "Consumption Model ID", "visible": False},
    # 가격 정보 카테고리 (Pricing Information) - PRD 2.1.2 기준
    "Price Unit": {"name": "Price Unit", "visible": False},
    "Pricing Unit": {"name": "Pricing Unit", "visible": False},
    # 청구 조정 카테고리 (Billing Adjustments) - PRD 2.1.2 기준
    "Adjustment Info Description": {
        "name": "Adjustment Info Description",
        "visible": False,
    },
    "Adjustment Info ID": {"name": "Adjustment Info ID", "visible": False},
    "Adjustment Info Mode": {"name": "Adjustment Info Mode", "visible": False},
    "Adjustment Info Type": {"name": "Adjustment Info Type", "visible": False},
    # 비용 분석 카테고리 (Cost Analysis) - PRD 2.1.2 기준
    "Credits Detail": {"name": "Credits Detail", "visible": False},
    # 기타 필수 필드들 (PRD 구현 로직에서 언급된 필드들)
    "Billing Account ID": {"name": "Billing Account ID", "visible": False},
    "Invoice Month": {"name": "Invoice Month", "visible": False},
    "Currency": {"name": "Currency", "visible": False},
    "Transaction Type": {
        "name": "Transaction Type",
        "visible": False,
        "enums": ["charge", "refund", "tax", "rounding_error"],
    },
}


class DataSourceManager(BaseManager):
    """Google Cloud Billing 데이터 소스 관리 매니저.

    SpaceONE 플러그인의 데이터 소스 초기화 및 메타데이터 관리를 담당합니다.
    """

    @staticmethod
    def init_response(options: dict, domain_id: Optional[str] = None) -> dict:
        """데이터 소스 초기화 응답을 생성합니다.

        Args:
            options: 플러그인 옵션 딕셔너리
            domain_id: 도메인 ID (선택사항)

        Returns:
            dict: 플러그인 메타데이터가 포함된 초기화 응답
        """
        metadata = {
            "currency": options.get("currency", "USD"),
            "supported_secret_types": ["MANUAL"],
            "use_account_routing": False,
            "data_source_rules": _DEFAULT_DATA_SOURCE_RULES,
            # "collect_resource_id": True,
            # "exclude_license_cost": False,
            # "include_credit_cost": False,
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
        options: dict,
        secret_data: dict,
        domain_id: str,
        schema: str = None,
    ) -> None:
        """데이터 소스 플러그인의 설정을 검증합니다.

        Args:
            options: 플러그인 옵션 딕셔너리
            secret_data: 시크릿 데이터 딕셔너리
            domain_id: 도메인 ID
            schema: 스키마 정보 (선택사항)

        Raises:
            ValueError: 필수 파라미터가 누락되거나 잘못된 경우
            Exception: 검증 과정에서 오류가 발생한 경우
        """

        try:
            # 1. 기본 파라미터 검증
            if not isinstance(options, dict):
                raise ValueError("Options must be a dictionary")

            if not isinstance(secret_data, dict):
                raise ValueError("Secret data must be a dictionary")

            if not domain_id:
                raise ValueError("Domain ID is required")

            # 2. 데이터 소스 타입별 검증
            data_source_type = DataSourceManager._determine_data_source_type(options)
            _LOGGER.info(
                f"[DataSourceManager.verify_plugin] Verifying data source type: {data_source_type}"
            )

            if data_source_type == DATA_SOURCE_TYPES["bigquery"]:
                DataSourceManager._verify_bigquery_config(options, secret_data)
            elif data_source_type == DATA_SOURCE_TYPES["http"]:
                DataSourceManager._verify_http_file_config(options, secret_data)
            else:
                raise ValueError(f"Unsupported data source type: {data_source_type}")

            # 3. 공통 옵션 검증
            DataSourceManager._verify_common_options(options)

            _LOGGER.info(
                "[DataSourceManager.verify_plugin] Plugin verification completed successfully"
            )

        except Exception as e:
            _LOGGER.error(
                f"[DataSourceManager.verify_plugin] Plugin verification failed: {e}"
            )
            raise

    @staticmethod
    def _determine_data_source_type(options: dict) -> str:
        """데이터 소스 타입을 자동으로 결정합니다."""

        # 1. 명시적 data_source_type 확인
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            # GCS 타입은 내부적으로 HTTP 타입으로 처리
            if data_source_type == "gcs":
                return DATA_SOURCE_TYPES["http"]
            return data_source_type

        # 2. source 파라미터 확인 (3개 고정 값: bigquery, gcs, http)
        source = options.get("source")
        if source == "bigquery":
            return DATA_SOURCE_TYPES["bigquery"]
        elif source == "gcs":
            return DATA_SOURCE_TYPES["http"]  # GCS는 http 타입으로 분류
        elif source == "http":
            return DATA_SOURCE_TYPES["http"]
        elif source:
            _LOGGER.warning(
                f"[DataSourceManager._determine_data_source_type] Unknown source parameter: {source}, "
                f"Valid sources: bigquery, gcs, http"
            )

        # 3. 파라미터 기반 자동 감지
        has_bucket = "bucket_name" in options
        has_base_url = "base_url" in options
        has_bigquery_params = all(
            key in options
            for key in [
                "billing_export_project_id",
                "billing_dataset_id",
                "billing_account_id",
            ]
        )

        if has_bucket or has_base_url:
            return DATA_SOURCE_TYPES["http"]
        elif has_bigquery_params:
            return DATA_SOURCE_TYPES["bigquery"]

        # 4. 기본값
        _LOGGER.info(
            "[DataSourceManager._determine_data_source_type] No clear data source type detected, defaulting to BigQuery"
        )
        return DATA_SOURCE_TYPES["bigquery"]

    @staticmethod
    def _verify_bigquery_config(options: dict, secret_data: dict) -> None:
        """BigQuery 데이터 소스 설정 검증"""
        # 실제 코드에서 사용하는 필드명으로 수정
        # billing_table은 billing_account_id로부터 자동 생성되므로 검증에서 제외
        required_options = [
            "billing_export_project_id",
            "billing_dataset_id",  # billing_dataset -> billing_dataset_id로 수정
            "billing_account_id",
        ]

        missing_options = [opt for opt in required_options if not options.get(opt)]
        if missing_options:
            raise ValueError(f"Missing required BigQuery options: {missing_options}")

        # 하위 호환성을 위해 billing_dataset도 확인 (선택사항)
        if not options.get("billing_dataset_id") and not options.get("billing_dataset"):
            raise ValueError(
                "Either 'billing_dataset_id' or 'billing_dataset' is required"
            )

        # billing_table 자동 생성 및 options에 추가 (방법 1 구현)
        if not options.get("billing_table"):
            billing_account_id = options.get("billing_account_id")
            if billing_account_id:
                # billing_table 자동 생성: gcp_billing_export_v1_{billing_account_id를 언더스코어로 변환}
                billing_table = (
                    f"gcp_billing_export_v1_{billing_account_id.replace('-', '_')}"
                )
                options["billing_table"] = billing_table
                _LOGGER.info(
                    f"[DataSourceManager._verify_bigquery_config] Auto-generated billing_table: {billing_table}"
                )

        # billing_dataset 자동 생성 (하위 호환성)
        if not options.get("billing_dataset") and options.get("billing_dataset_id"):
            # billing_dataset_id에서 실제 데이터셋 ID만 추출
            billing_dataset_id = options.get("billing_dataset_id")
            if "." in billing_dataset_id:
                # 'project.dataset' 형식인 경우 dataset 부분만 반환
                billing_dataset = billing_dataset_id.split(".")[-1]
            else:
                # 이미 dataset만 있는 경우 그대로 사용
                billing_dataset = billing_dataset_id

            options["billing_dataset"] = billing_dataset
            _LOGGER.info(
                f"[DataSourceManager._verify_bigquery_config] Auto-generated billing_dataset: {billing_dataset}"
            )

        # Service Account 키 검증
        if not secret_data.get("service_account_json_object"):
            # service_account_json_object가 없으면 개별 필드들로 검증
            required_sa_fields = ["type", "project_id", "private_key", "client_email"]
            missing_sa_fields = [
                field for field in required_sa_fields if not secret_data.get(field)
            ]

            if missing_sa_fields:
                raise ValueError(
                    f"Either 'service_account_json_object' or individual service account fields are required. "
                    f"Missing fields: {missing_sa_fields}"
                )

            _LOGGER.info(
                "[DataSourceManager._verify_bigquery_config] Using individual service account fields instead of JSON object"
            )

        _LOGGER.debug(
            "[DataSourceManager._verify_bigquery_config] BigQuery configuration verified"
        )

    @staticmethod
    def _verify_http_file_config(options: dict, secret_data: dict) -> None:
        """HTTP File 데이터 소스 설정 검증"""
        # base_url 또는 bucket_name 중 하나는 필수
        has_base_url = bool(options.get("base_url"))
        has_bucket_name = bool(options.get("bucket_name"))

        if not (has_base_url or has_bucket_name):
            raise ValueError(
                "Either 'base_url' or 'bucket_name' is required for HTTP file data source"
            )

        # filed_mapper 오타 자동 수정 (방법 2 구현)
        if "filed_mapper" in options and "field_mapper" not in options:
            options["field_mapper"] = options["filed_mapper"]
            _LOGGER.warning(
                "[DataSourceManager._verify_http_file_config] Auto-corrected 'filed_mapper' to 'field_mapper'"
            )

        # billing_account_id 자동 추가 (GCS 사용 시 권장)
        if has_bucket_name and not options.get("billing_account_id"):
            # project_id에서 billing_account_id 추론 시도
            project_id = options.get("project_id")
            if project_id:
                # 일반적으로 billing_account_id는 별도로 설정되어야 하지만,
                # 기본값으로 project_id를 사용할 수 있도록 로깅만 수행
                _LOGGER.info(
                    f"[DataSourceManager._verify_http_file_config] billing_account_id not provided. "
                    f"Consider adding it for better cost tracking. Project ID: {project_id}"
                )

        # GCS 사용 시 Service Account 키 검증
        if has_bucket_name and not secret_data.get("service_account_json_object"):
            # service_account_json_object가 없으면 개별 필드들로 검증
            required_sa_fields = ["type", "project_id", "private_key", "client_email"]
            missing_sa_fields = [
                field for field in required_sa_fields if not secret_data.get(field)
            ]

            if missing_sa_fields:
                raise ValueError(
                    f"Either 'service_account_json_object' or individual service account fields are required for GCS access. "
                    f"Missing fields: {missing_sa_fields}"
                )

            _LOGGER.info(
                "[DataSourceManager._verify_http_file_config] Using individual service account fields instead of JSON object"
            )

        _LOGGER.debug(
            "[DataSourceManager._verify_http_file_config] HTTP file configuration verified"
        )

    @staticmethod
    def _verify_common_options(options: dict) -> None:
        """공통 옵션 검증"""
        # 통화 코드 검증
        currency = options.get("currency", "USD")
        if not isinstance(currency, str) or len(currency) != 3:
            raise ValueError(
                f"Invalid currency code: {currency}. Must be a 3-letter currency code."
            )

        # 날짜 형식 검증 (선택사항)
        date_format = options.get("date_format")
        if date_format and not isinstance(date_format, str):
            raise ValueError("Date format must be a string")

        _LOGGER.debug(
            "[DataSourceManager._verify_common_options] Common options verified"
        )

    @staticmethod
    def init_cost_data_info() -> dict:
        """비용 데이터의 additional_info 필드에 대한 메타데이터 정보를 반환합니다.

        Returns:
            dict: additional_info 필드들의 메타데이터

        """
        return _DEFAULT_METADATA_ADDITIONAL_INFO
