import logging

import google.oauth2.service_account
import pandas_gbq
from googleapiclient.discovery import build

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.connector import BaseConnector
except ImportError:
    # Mock for local development
    class BaseConnector:
        """Mock BaseConnector for local development"""

        def __init__(self, *args, **kwargs):
            pass


_LOGGER = logging.getLogger("spaceone")

REQUIRED_SECRET_KEYS = ["project_id", "private_key", "token_uri", "client_email"]


class BigqueryConnector(BaseConnector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_id = None
        self.credentials = None
        self.google_client = None

    def create_session(self, options: dict, secret_data: dict, schema: str):
        if not secret_data:
            return

        self.project_id = secret_data.get("project_id")

        # private_key 기본 처리만 수행 (검증 제거)
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            # 이스케이프된 개행 문자를 실제 개행으로 변환
            if "\\n" in processed_secret_data["private_key"]:
                processed_secret_data["private_key"] = processed_secret_data[
                    "private_key"
                ].replace("\\n", "\n")

        # Google API 인증 정보로 직접 생성 (상세 오류 처리 제거)
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                processed_secret_data
            )
        )
        self.google_client = build("bigquery", "v2", credentials=self.credentials)

    def list_tables(self, billing_export_project_id, dataset_id, **query):
        table_list = []

        query.update({"projectId": billing_export_project_id, "datasetId": dataset_id})

        try:
            request = self.google_client.tables().list(**query)
            while request is not None:
                response = request.execute()
                for table in response.get("tables", []):
                    table_list.append(table)
                request = self.google_client.tables().list_next(
                    previous_request=request, previous_response=response
                )
        except Exception as e:
            _LOGGER.error(
                f"[BigqueryConnector] Failed to list tables in dataset {dataset_id}: {e}"
            )
            # 데이터셋이 존재하지 않거나 접근 권한이 없는 경우 빈 리스트 반환
            return []

        return table_list

    def read_df_from_bigquery(self, query):
        """BigQuery에서 DataFrame으로 데이터를 읽어옵니다."""
        _LOGGER.debug("[BigqueryConnector] 쿼리 실행 시작")
        _LOGGER.debug(f"[BigqueryConnector] 프로젝트 ID: {self.project_id}")

        try:
            result_df = pandas_gbq.read_gbq(
                query, project_id=self.project_id, credentials=self.credentials
            )
            _LOGGER.debug(f"[BigqueryConnector] 쿼리 실행 성공 - DataFrame 크기: {len(result_df)} 행, {len(result_df.columns)} 열")

            # GCS 파서와 동일한 데이터 타입으로 변환
            standardized_df = self._standardize_dataframe_types(result_df)
            return standardized_df

        except Exception as e:
            _LOGGER.error(f"[BigqueryConnector] 쿼리 실행 실패: {str(e)}")
            _LOGGER.error(f"[BigqueryConnector] 프로젝트 ID: {self.project_id}")
            raise

    def _standardize_dataframe_types(self, df):
        """DataFrame의 데이터 타입을 GCS 파서와 일치하도록 표준화"""

        import pandas as pd

        standardized_df = df.copy()

        # SpaceONE 빌링 필수 필드들의 데이터 타입 표준화
        cost_fields = ['cost', 'cost_at_list', 'cost_after_credits', 'usage_amount',
                      'usage_amount_in_pricing_units', 'currency_conversion_rate']

        date_fields = ['usage_start_time', 'usage_end_time', 'export_time']
        string_fields = ['billing_account_id', 'project_id', 'project_name', 'service_description',
                        'sku_description', 'location_region', 'location_zone', 'currency', 'invoice_month']

        for col in standardized_df.columns:
            try:
                # 비용 및 사용량 관련 필드를 정밀도 개선된 float 타입으로 변환
                if any(field in col.lower() for field in ['cost', 'amount', 'price', 'rate', 'usage_quantity']):
                    standardized_df[col] = pd.to_numeric(standardized_df[col], errors='coerce').fillna(0.0)
                    # 부동소수점 정밀도 개선 적용
                    standardized_df[col] = standardized_df[col].apply(self._clean_float_precision)

                # 날짜/시간 필드를 문자열로 변환 (SpaceONE 표준 형식)
                elif any(field in col.lower() for field in ['time', 'date']):
                    if col in date_fields or 'time' in col.lower():
                        standardized_df[col] = pd.to_datetime(standardized_df[col], errors='coerce')
                        # TIMESTAMP를 ISO 형식 문자열로 변환
                        standardized_df[col] = standardized_df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                        standardized_df[col] = standardized_df[col].fillna('')
                    else:
                        # billed_date 같은 날짜만 있는 필드는 YYYY-MM-DD 형식으로
                        standardized_df[col] = pd.to_datetime(standardized_df[col], errors='coerce')
                        standardized_df[col] = standardized_df[col].dt.strftime('%Y-%m-%d')
                        standardized_df[col] = standardized_df[col].fillna('')

                # 문자열 필드 처리
                elif col in string_fields or any(field in col.lower() for field in ['id', 'name', 'description', 'type']):
                    standardized_df[col] = standardized_df[col].astype(str).fillna('')
                    # 'nan' 문자열을 빈 문자열로 변환
                    standardized_df[col] = standardized_df[col].replace('nan', '')

                # 중첩 구조 필드들 (ARRAY<RECORD>, RECORD 타입 처리)
                elif col in ['project', 'service', 'sku', 'location', 'usage', 'labels', 'credits', 'invoice', 'price']:
                    # BigQuery의 중첩 구조를 SpaceONE 호환 형태로 변환
                    standardized_df[col] = standardized_df[col].apply(self._normalize_nested_structure)

                # NaN 값들을 적절한 기본값으로 변환 (GCS 파서의 _clean_nan_values와 동일한 로직)
                standardized_df[col] = standardized_df[col].where(pd.notnull(standardized_df[col]),
                                                               0 if col in cost_fields else '')

            except Exception as e:
                _LOGGER.warning(f"[BigqueryConnector] Failed to standardize column {col}: {e}")
                # 실패한 경우 원본 값 유지
                continue

        _LOGGER.debug(f"[BigqueryConnector] 데이터 타입 표준화 완료 - {len(standardized_df)} 행")
        return standardized_df

    def _clean_float_precision(self, value):
        """부동소수점 정밀도를 개선하여 깔끔한 float 값으로 변환"""
        from decimal import ROUND_HALF_UP, Decimal

        if value is None or value == 0:
            return 0.0

        try:
            # float를 Decimal로 변환하여 정밀도 개선
            decimal_value = Decimal(str(value))

            # 값의 크기에 따라 적절한 정밀도 결정
            abs_value = abs(decimal_value)

            if abs_value == 0:
                return 0.0
            elif abs_value >= 1000:
                # 큰 값: 소수점 2자리까지
                precision = 2
            elif abs_value >= 1:
                # 중간 값: 소수점 6자리까지
                precision = 6
            elif abs_value >= 0.001:
                # 작은 값: 소수점 9자리까지
                precision = 9
            else:
                # 매우 작은 값: 소수점 12자리까지
                precision = 12

            # 지정된 정밀도로 반올림
            quantize_exp = Decimal('0.1') ** precision
            rounded_decimal = decimal_value.quantize(quantize_exp, rounding=ROUND_HALF_UP)

            # float로 변환
            return float(rounded_decimal)

        except Exception:
            # 변환 실패 시 원본 값 반환
            return float(value) if value is not None else 0.0

    def _normalize_nested_structure(self, value):
        """BigQuery의 중첩 구조(ARRAY<RECORD>, RECORD)를 SpaceONE 호환 형태로 변환"""
        import json

        if value is None:
            return {}

        try:
            # 이미 딕셔너리나 리스트인 경우
            if isinstance(value, (dict, list)):
                return value

            # pandas의 NaN 체크
            import pandas as pd
            if pd.isna(value):
                return {}

            # 문자열인 경우 JSON 파싱 시도
            if isinstance(value, str):
                if value.strip() == '' or value.lower() == 'nan':
                    return {}
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, (dict, list)) else {}
                except (json.JSONDecodeError, ValueError):
                    # JSON이 아닌 문자열인 경우 그대로 반환
                    return value

            # 기타 타입은 문자열로 변환 후 재시도
            str_value = str(value)
            if str_value.lower() in ['nan', 'none', '']:
                return {}

            try:
                parsed = json.loads(str_value)
                return parsed if isinstance(parsed, (dict, list)) else {}
            except (json.JSONDecodeError, ValueError):
                return str_value

        except Exception as e:
            _LOGGER.warning(f"[BigqueryConnector] Failed to normalize nested structure: {e}")
            return {} if value is None else str(value)
