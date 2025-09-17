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
        # 클래스 레벨 쿼리 카운터 (없으면 초기화)
        if not hasattr(BigqueryConnector, '_query_counter'):
            BigqueryConnector._query_counter = 0
        
        BigqueryConnector._query_counter += 1
        current_query_num = BigqueryConnector._query_counter
        
        _LOGGER.info(f"🚀 [BigQuery 커넥터] 쿼리 #{current_query_num} 실행 시작")
        _LOGGER.debug(f"[BigqueryConnector] 프로젝트 ID: {self.project_id}")

        try:
            # BigQuery 쿼리 타임아웃 설정 (5분)
            result_df = pandas_gbq.read_gbq(
                query, 
                project_id=self.project_id, 
                credentials=self.credentials,
                timeout=300,  # 5분 타임아웃 설정
                max_results=None,  # 결과 수 제한 없음
                progress_bar=False  # 프로그레스바 비활성화
            )
            _LOGGER.info(f"✅ [BigQuery 커넥터] 쿼리 #{current_query_num} 실행 완료 - {len(result_df)}행 조회")
            _LOGGER.debug(f"[BigqueryConnector] 쿼리 실행 성공 - DataFrame 크기: {len(result_df)} 행, {len(result_df.columns)} 열")

            # GCS 파서와 동일한 데이터 타입으로 변환
            standardized_df = self._standardize_dataframe_types(result_df)
            return standardized_df

        except Exception as e:
            error_msg = str(e)
            _LOGGER.error(f"[BigqueryConnector] 쿼리 실행 실패: {error_msg}")
            _LOGGER.error(f"[BigqueryConnector] 프로젝트 ID: {self.project_id}")
            
            # 타임아웃 관련 에러 상세 로깅
            if "timeout" in error_msg.lower() or "deadline" in error_msg.lower():
                _LOGGER.error(f"[BigqueryConnector] ⏰ 타임아웃 발생 - 쿼리 #{current_query_num}")
                _LOGGER.error(f"[BigqueryConnector] 타임아웃 설정: 300초 (5분)")
            elif "connection" in error_msg.lower():
                _LOGGER.error(f"[BigqueryConnector] 🔌 연결 문제 발생 - 쿼리 #{current_query_num}")
            elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
                _LOGGER.error(f"[BigqueryConnector] 📊 할당량/제한 초과 - 쿼리 #{current_query_num}")
            
            raise

    def _standardize_dataframe_types(self, df):
        """DataFrame의 데이터 타입을 새로운 스키마 구조에 맞게 표준화"""

        import pandas as pd

        standardized_df = df.copy()

        # 새로운 스키마 기준 필드 분류
        float_fields = ['cost', 'currency_conversion_rate', 'cost_at_list',
                       'cost_at_effective_price_default', 'cost_at_list_consumption_model',
                       'credits_total_amount']

        numeric_fields = ['effective_price', 'tier_start_amount', 'pricing_unit_quantity',
                         'list_price', 'effective_price_default', 'list_price_consumption_model']

        timestamp_fields = ['usage_start_time', 'usage_end_time', 'export_time']
        string_fields = ['billing_account_id', 'currency', 'transaction_type', 'seller_name', 'cost_type']

        # 명시적으로 문자열로 처리해야 하는 필드들 (cost가 포함되어도 float가 아님)
        explicit_string_fields = ['cost_type', 'transaction_type', 'seller_name']

        # REPEATED 필드들 (배열로 처리)
        repeated_fields = ['labels', 'system_labels', 'tags', 'credits']

        # 중첩 구조 필드들 (RECORD 타입)
        record_fields = ['service', 'sku', 'project', 'location', 'price', 'usage',
                        'invoice', 'adjustment_info', 'consumption_model']

        for col in standardized_df.columns:
            try:
                # 명시적 문자열 필드 우선 처리
                if col in explicit_string_fields:
                    standardized_df[col] = standardized_df[col].astype(str).fillna('')
                    standardized_df[col] = standardized_df[col].replace('nan', '')

                # FLOAT 타입 필드 처리 (명시적 문자열 필드 제외)
                elif col in float_fields or (any(field in col.lower() for field in ['cost', 'rate']) and col not in explicit_string_fields):
                    standardized_df[col] = standardized_df[col].apply(
                        lambda x, column=col: self._process_float_field(x, column)
                    )

                # NUMERIC 타입 필드 처리 (price 하위 필드들)
                elif col in numeric_fields or (col.startswith('price_') and any(field in col for field in numeric_fields)):
                    standardized_df[col] = standardized_df[col].apply(
                        lambda x, column=col: self._process_numeric_field(x, column)
                    )

                # TIMESTAMP 필드 처리
                elif col in timestamp_fields or any(field in col.lower() for field in ['time']):
                    standardized_df[col] = pd.to_datetime(standardized_df[col], errors='coerce')
                    # TIMESTAMP를 ISO 형식 문자열로 변환
                    standardized_df[col] = standardized_df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                    standardized_df[col] = standardized_df[col].fillna('')

                # STRING 필드 처리
                elif col in string_fields or any(field in col.lower() for field in ['id', 'name', 'description', 'type']):
                    standardized_df[col] = standardized_df[col].astype(str).fillna('')
                    # 'nan' 문자열을 빈 문자열로 변환
                    standardized_df[col] = standardized_df[col].replace('nan', '')

                # REPEATED 필드들 (배열 구조로 처리)
                elif col in repeated_fields:
                    standardized_df[col] = standardized_df[col].apply(self._process_repeated_field)

                # RECORD 타입 필드들 (중첩 구조 처리)
                elif col in record_fields:
                    standardized_df[col] = standardized_df[col].apply(self._normalize_nested_structure)

                # 기타 필드들의 NaN 값 처리
                else:
                    standardized_df[col] = standardized_df[col].where(pd.notnull(standardized_df[col]), '')

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
        """BigQuery의 중첩 구조(ARRAY<RECORD>, RECORD)를 SpaceONE 호환 형태로 변환 - 새로운 스키마 지원"""
        import json

        if value is None:
            return {}

        try:
            # 이미 딕셔너리나 리스트인 경우
            if isinstance(value, (dict, list)):
                return self._clean_nested_structure(value)

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
                    return self._clean_nested_structure(parsed) if isinstance(parsed, (dict, list)) else {}
                except (json.JSONDecodeError, ValueError):
                    # JSON이 아닌 문자열인 경우 그대로 반환
                    return value

            # 기타 타입은 문자열로 변환 후 재시도
            str_value = str(value)
            if str_value.lower() in ['nan', 'none', '']:
                return {}

            try:
                parsed = json.loads(str_value)
                return self._clean_nested_structure(parsed) if isinstance(parsed, (dict, list)) else {}
            except (json.JSONDecodeError, ValueError):
                return str_value

        except Exception as e:
            _LOGGER.warning(f"[BigqueryConnector] Failed to normalize nested structure: {e}")
            return {} if value is None else str(value)

    def _clean_nested_structure(self, data):
        """중첩 구조의 null 값과 NaN 값을 정리"""
        if isinstance(data, dict):
            cleaned = {}
            for key, value in data.items():
                if value is not None:
                    try:
                        import pandas as pd
                        if not pd.isna(value):
                            if isinstance(value, (dict, list)):
                                cleaned[key] = self._clean_nested_structure(value)
                            else:
                                cleaned[key] = value
                    except (TypeError, ValueError, ImportError):
                        if isinstance(value, (dict, list)):
                            cleaned[key] = self._clean_nested_structure(value)
                        else:
                            cleaned[key] = value
            return cleaned
        elif isinstance(data, list):
            cleaned = []
            for item in data:
                if item is not None:
                    try:
                        import pandas as pd
                        if not pd.isna(item):
                            if isinstance(item, (dict, list)):
                                cleaned.append(self._clean_nested_structure(item))
                            else:
                                cleaned.append(item)
                    except (TypeError, ValueError, ImportError):
                        if isinstance(item, (dict, list)):
                            cleaned.append(self._clean_nested_structure(item))
                        else:
                            cleaned.append(item)
            return cleaned
        else:
            return data

    def _process_numeric_field(self, value, field_name: str):
        """NUMERIC 타입 필드 처리 (높은 정밀도 유지)"""
        if value is None:
            return 0

        try:
            import pandas as pd
            if pd.isna(value):
                return 0
        except (TypeError, ValueError, ImportError):
            pass

        try:
            # Decimal을 사용하여 정밀도 유지
            from decimal import Decimal
            if isinstance(value, (int, float)):
                return float(Decimal(str(value)))
            elif isinstance(value, str):
                if value.strip().lower() in ('', 'nan', 'none', 'null'):
                    return 0
                return float(Decimal(value.strip()))
            else:
                return float(Decimal(str(value)))
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"[BigqueryConnector] Failed to process NUMERIC field {field_name}: {e}")
            return 0

    def _process_float_field(self, value, field_name: str):
        """FLOAT 타입 필드 처리"""
        if value is None:
            return 0.0

        try:
            import pandas as pd
            if pd.isna(value):
                return 0.0
        except (TypeError, ValueError, ImportError):
            pass

        try:
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                if value.strip().lower() in ('', 'nan', 'none', 'null'):
                    return 0.0
                # 숫자가 아닌 문자열인 경우 0.0 반환 (예: 'regular', 'usage' 등)
                stripped_value = value.strip()
                # 먼저 float 변환을 시도해보고, 실패하면 0.0 반환
                try:
                    return float(stripped_value)
                except ValueError:
                    _LOGGER.debug(f"[BigqueryConnector] Non-numeric string in FLOAT field {field_name}: '{value}', using 0.0")
                    return 0.0
            else:
                return float(value)
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"[BigqueryConnector] Failed to process FLOAT field {field_name}: {e}")
            return 0.0

    def _process_repeated_field(self, value):
        """REPEATED 필드를 배열로 처리"""
        if value is None:
            return []

        try:
            import pandas as pd
            if pd.isna(value):
                return []
        except (TypeError, ValueError, ImportError):
            pass

        # 이미 리스트인 경우
        if isinstance(value, list):
            return self._clean_nested_structure(value)

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(value, str):
            str_value = value.strip()
            if not str_value or str_value.lower() in ("none", "null", "", "nan"):
                return []

            try:
                import json
                parsed = json.loads(str_value)
                if isinstance(parsed, list):
                    return self._clean_nested_structure(parsed)
                elif isinstance(parsed, dict):
                    return [parsed]  # 단일 객체를 배열로 감쌈
                else:
                    return [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                # JSON이 아닌 경우 단일 항목으로 처리
                return [str_value]

        # 딕셔너리인 경우 단일 항목 배열로 변환
        if isinstance(value, dict):
            return [value]

        # 기타 타입은 문자열로 변환 후 단일 항목 배열
        return [str(value)]
