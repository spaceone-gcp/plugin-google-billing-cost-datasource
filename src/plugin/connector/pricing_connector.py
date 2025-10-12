"""
Google Cloud Pricing Data Export 연동을 위한 커넥터
Google Cloud의 cloud_pricing_export 테이블에서 가격 정보를 조회하고 분석하는 기능을 제공합니다.
"""

import logging
from collections.abc import Generator
from decimal import Decimal
from typing import Any

import pandas_gbq
from google.oauth2 import service_account
from googleapiclient.discovery import build
from spaceone.core.connector import BaseConnector

from plugin.error.cost import ERROR_INVALID_ARGUMENT

_LOGGER = logging.getLogger("spaceone")

REQUIRED_SECRET_KEYS = ["project_id", "private_key", "token_uri", "client_email"]


class PricingConnector(BaseConnector):
    """Google Cloud Pricing Data Export 전용 커넥터"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_id = None
        self.credentials = None
        self.google_client = None
        self.pricing_project_id = None
        self.pricing_dataset_id = None

    def create_session(self, options: dict, secret_data: dict, schema: str):
        """BigQuery 세션 생성 및 Pricing 관련 설정 초기화"""
        if not secret_data:
            return

        self.project_id = secret_data.get("project_id")

        # private_key의 \n 문자열을 실제 개행 문자로 변환
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            processed_secret_data["private_key"] = processed_secret_data[
                "private_key"
            ].replace("\\n", "\n")

        # Service Account 인증 정보로 Google API 클라이언트 생성
        self.credentials = service_account.Credentials.from_service_account_info(
            processed_secret_data,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        self.google_client = build("bigquery", "v2", credentials=self.credentials)

        # Pricing Export 관련 설정
        self.pricing_project_id = options.get(
            "pricing_export_project_id", self.project_id
        )
        self.pricing_dataset_id = options.get("pricing_dataset_id", "pricing_export")

    def get_pricing_data(
        self,
        service_id: str | None = None,
        sku_id: str | None = None,
        date: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        cloud_pricing_export 테이블에서 가격 정보 조회

        Args:
            service_id: 특정 서비스 ID로 필터링 (선택사항)
            sku_id: 특정 SKU ID로 필터링 (선택사항)
            date: 특정 날짜의 가격 정보 (YYYY-MM-DD 형식, 선택사항)

        Yields:
            가격 정보 딕셔너리
        """
        try:
            query = self._build_pricing_query(service_id, sku_id, date)
            _LOGGER.debug(f"[PricingConnector] Executing query: {query}")

            response_df = pandas_gbq.read_gbq(
                query,
                project_id=self.project_id,
                credentials=self.credentials,
                # timeout 파라미터는 pandas-gbq>=0.29.0에서 지원되지 않음
                progress_bar_type=None,  # 프로그레스바 비활성화 (기본값: 'tqdm', None으로 비활성화)
            )

            for _, row in response_df.iterrows():
                yield self._transform_pricing_row(row)

        except Exception as e:
            _LOGGER.error(f"[PricingConnector] Error getting pricing data: {str(e)}")
            raise ERROR_INVALID_ARGUMENT(key="pricing_query", value=str(e)) from e

    def get_service_pricing_summary(
        self, date: str | None = None
    ) -> dict[str, list[dict]]:
        """
        서비스별 가격 정보 요약 조회

        Args:
            date: 특정 날짜의 가격 정보 (YYYY-MM-DD 형식, 선택사항)

        Returns:
            서비스별 가격 정보 요약 딕셔너리
        """
        try:
            query = self._build_service_summary_query(date)
            response_df = pandas_gbq.read_gbq(
                query,
                project_id=self.project_id,
                credentials=self.credentials,
                # timeout 파라미터는 pandas-gbq>=0.29.0에서 지원되지 않음
                progress_bar_type=None,  # 프로그레스바 비활성화 (기본값: 'tqdm', None으로 비활성화)
            )

            service_summary = {}
            for _, row in response_df.iterrows():
                service_desc = row.get("service_description", "Unknown")
                if service_desc not in service_summary:
                    service_summary[service_desc] = []

                service_summary[service_desc].append(
                    {
                        "sku_id": row.get("sku_id", ""),
                        "sku_description": row.get("sku_description", ""),
                        "pricing_unit": row.get("pricing_unit", ""),
                        "base_price_usd": float(row.get("base_price_usd", 0)),
                        "region": row.get("region", "global"),
                    }
                )

            return service_summary

        except Exception as e:
            _LOGGER.error(
                f"[PricingConnector] Error getting service pricing summary: {str(e)}"
            )
            raise ERROR_INVALID_ARGUMENT(
                key="service_summary_query", value=str(e)
            ) from e

    def compare_billing_vs_pricing(
        self, billing_data: dict, pricing_date: str | None = None
    ) -> dict:
        """
        실제 청구 데이터와 정가 비교 분석

        Args:
            billing_data: 실제 청구 데이터
            pricing_date: 비교할 가격 정보 날짜

        Returns:
            비교 분석 결과
        """
        try:
            service_id = billing_data.get("service_id", "")
            sku_id = billing_data.get("sku_id", "")
            actual_cost = Decimal(str(billing_data.get("cost", 0)))
            usage_amount = Decimal(str(billing_data.get("usage_amount", 0)))

            # 해당 SKU의 정가 조회
            pricing_data = list(self.get_pricing_data(service_id, sku_id, pricing_date))

            if not pricing_data:
                return {
                    "comparison_available": False,
                    "reason": "No pricing data found for this SKU",
                }

            # 첫 번째 가격 정보 사용 (일반적으로 기본 가격)
            price_info = pricing_data[0]
            list_price_per_unit = Decimal(str(price_info.get("base_price_usd", 0)))

            if usage_amount > 0 and list_price_per_unit > 0:
                list_price_total = usage_amount * list_price_per_unit
                discount_amount = list_price_total - actual_cost
                discount_rate = (
                    (discount_amount / list_price_total * 100)
                    if list_price_total > 0
                    else Decimal(0)
                )

                return {
                    "comparison_available": True,
                    "actual_cost": float(actual_cost),
                    "list_price_total": float(list_price_total),
                    "discount_amount": float(discount_amount),
                    "discount_rate_percent": float(discount_rate),
                    "usage_amount": float(usage_amount),
                    "list_price_per_unit": float(list_price_per_unit),
                }
            else:
                return {
                    "comparison_available": False,
                    "reason": "Insufficient usage or pricing data",
                }

        except Exception as e:
            _LOGGER.error(
                f"[PricingConnector] Error comparing billing vs pricing: {str(e)}"
            )
            return {
                "comparison_available": False,
                "reason": f"Comparison error: {str(e)}",
            }

    def _build_pricing_query(
        self, service_id: str | None, sku_id: str | None, date: str | None
    ) -> str:
        """Pricing Data 조회 쿼리 생성"""

        # 기본 WHERE 조건
        where_conditions = []

        if date:
            where_conditions.append(f"DATE(_PARTITIONTIME) = '{date}'")
        else:
            where_conditions.append(
                f"DATE(_PARTITIONTIME) = (SELECT MAX(DATE(_PARTITIONTIME)) FROM `{self.pricing_project_id}.{self.pricing_dataset_id}.cloud_pricing_export`)"
            )

        if service_id:
            where_conditions.append(f"service.id = '{service_id}'")

        if sku_id:
            where_conditions.append(f"sku.id = '{sku_id}'")

        where_clause = " AND ".join(where_conditions)

        query = f"""
            SELECT
                export_time,
                pricing_as_of_time,
                service.id as service_id,
                service.description as service_description,
                sku.id as sku_id,
                sku.description as sku_description,
                IFNULL(geo_taxonomy.region, 'global') as region,
                list_price.tiered_rates
            FROM `{self.pricing_project_id}.{self.pricing_dataset_id}.cloud_pricing_export`
            WHERE {where_clause}
            ORDER BY service.description, sku.description
        """

        return query

    def _build_service_summary_query(self, date: str | None) -> str:
        """서비스별 가격 요약 쿼리 생성"""

        if date:
            date_condition = f"DATE(_PARTITIONTIME) = '{date}'"
        else:
            date_condition = f"DATE(_PARTITIONTIME) = (SELECT MAX(DATE(_PARTITIONTIME)) FROM `{self.pricing_project_id}.{self.pricing_dataset_id}.cloud_pricing_export`)"

        query = f"""
            SELECT
                service.description as service_description,
                sku.id as sku_id,
                sku.description as sku_description,
                IFNULL(geo_taxonomy.region, 'global') as region,
                -- 첫 번째 가격 계층의 단위 가격 추출
                (SELECT tier.usd_amount
                 FROM UNNEST(list_price.tiered_rates) as tier
                 WHERE tier.start_usage_amount = 0
                 LIMIT 1) as base_price_usd,
                -- 가격 책정 단위 정보
                (SELECT tier.pricing_unit_quantity
                 FROM UNNEST(list_price.tiered_rates) as tier
                 WHERE tier.start_usage_amount = 0
                 LIMIT 1) as pricing_unit
            FROM `{self.pricing_project_id}.{self.pricing_dataset_id}.cloud_pricing_export`
            WHERE {date_condition}
            ORDER BY service.description, sku.description
        """

        return query

    def _transform_pricing_row(self, row) -> dict:
        """Pricing 데이터 행을 표준 형식으로 변환"""

        # tiered_rates 파싱 - 원본 타입 유지
        tiered_rates = []
        if hasattr(row, "tiered_rates") and row.tiered_rates:
            for rate in row.tiered_rates:
                tiered_rates.append(
                    {
                        "pricing_unit_quantity": self._preserve_numeric_type(
                            rate.get("pricing_unit_quantity", 0)
                        ),
                        "start_usage_amount": self._preserve_numeric_type(
                            rate.get("start_usage_amount", 0)
                        ),
                        "usd_amount": self._preserve_numeric_type(
                            rate.get("usd_amount", 0)
                        ),
                        "account_currency_amount": self._preserve_numeric_type(
                            rate.get("account_currency_amount", 0)
                        ),
                    }
                )

        # 기본 가격 (첫 번째 계층) 추출
        base_price_usd = 0
        if tiered_rates:
            base_price_usd = tiered_rates[0].get("usd_amount", 0)

        return {
            "export_time": str(row.get("export_time", "")),
            "pricing_as_of_time": str(row.get("pricing_as_of_time", "")),
            "service_id": row.get("service_id", ""),
            "service_description": row.get("service_description", ""),
            "sku_id": row.get("sku_id", ""),
            "sku_description": row.get("sku_description", ""),
            "region": row.get("region", "global"),
            "tiered_rates": tiered_rates,
            "base_price_usd": base_price_usd,
        }

    def _preserve_numeric_type(self, value: Any) -> Any:
        """숫자 값의 원본 타입을 유지하면서 유효성 검증"""
        if value is None:
            return 0

        # 이미 숫자 타입인 경우 그대로 반환
        if isinstance(value, (int, float)):
            return value

        # 문자열인 경우 숫자로 변환 시도
        if isinstance(value, str):
            try:
                # 정수로 변환 가능한지 확인
                if "." not in value and value.isdigit():
                    return int(value)
                else:
                    return float(value)
            except (ValueError, TypeError):
                return 0

        # 기타 타입은 0으로 처리
        return 0

    def list_pricing_tables(self) -> list[dict]:
        """Pricing Export 데이터셋의 테이블 목록 조회"""
        try:
            query = {
                "projectId": self.pricing_project_id,
                "datasetId": self.pricing_dataset_id,
            }

            response = self.google_client.tables().list(**query).execute()
            tables = response.get("tables", [])

            table_list = []
            for table in tables:
                table_info = {
                    "table_id": table.get("tableReference", {}).get("tableId", ""),
                    "creation_time": table.get("creationTime", ""),
                    "type": table.get("type", ""),
                }
                table_list.append(table_info)

            _LOGGER.info(f"[PricingConnector] Found {len(table_list)} pricing tables")
            return table_list

        except Exception as e:
            _LOGGER.error(f"[PricingConnector] Error listing pricing tables: {str(e)}")
            raise ERROR_INVALID_ARGUMENT(key="list_tables", value=str(e)) from e
