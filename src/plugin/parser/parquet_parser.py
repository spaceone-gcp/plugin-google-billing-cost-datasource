import logging
from collections.abc import Generator
from typing import IO

from ..error.cost import ERROR_FILE_PARSING_FAILED
from ..manager.field_mapper import FieldMapper
from .base_parser import BaseParser

_LOGGER = logging.getLogger("spaceone")


class ParquetParser(BaseParser):
    """Parquet 파일 파서"""

    def parse_stream(
        self, stream: IO, field_mapper: FieldMapper, **kwargs
    ) -> Generator[dict, None, None]:
        """Parquet 스트림을 파싱하여 매핑된 데이터 반환

        Args:
            stream: Parquet 파일 스트림
            field_mapper: 필드 매핑 객체
            **kwargs: 추가 파싱 옵션
                - columns: 읽을 컬럼 목록 (기본값: 모든 컬럼)
                - filters: 필터 조건 (PyArrow 형식)

        Yields:
            매핑된 비용 데이터 레코드
        """
        columns = kwargs.get("columns", None)
        # filters = kwargs.get("filters", None)  # TODO: 향후 필터링 기능 구현 시 사용

        try:
            # pyarrow 동적 임포트 (선택적 의존성)
            try:
                import pyarrow.parquet as pq
                # import pyarrow as pa  # 현재 사용하지 않음
            except ImportError as e:
                raise ERROR_FILE_PARSING_FAILED(
                    file_path="parquet_stream",
                    reason="pyarrow library is required for Parquet parsing. Install with: pip install pyarrow",
                ) from e

            # 스트림에서 Parquet 파일 읽기
            parquet_file = pq.ParquetFile(stream)

            # 메타데이터 정보 (향후 사용을 위해 예비)
            # metadata = parquet_file.metadata

            # 배치 단위로 데이터 읽기
            processed_count = 0

            # 배치 크기 조정 (Parquet은 일반적으로 큰 배치가 효율적)
            batch_size = max(self.chunk_size, 500)

            for batch in parquet_file.iter_batches(
                batch_size=batch_size, columns=columns, use_pandas_metadata=True
            ):
                batch_result = self._process_parquet_batch(
                    batch, field_mapper, processed_count
                )
                if batch_result:
                    processed_count += len(batch_result["results"])
                    yield batch_result

        except Exception as e:
            _LOGGER.error(f"[ParquetParser] Failed to parse Parquet stream: {e}")
            raise ERROR_FILE_PARSING_FAILED(
                file_path="parquet_stream", reason=str(e)
            ) from e

    def _process_parquet_batch(self, batch, field_mapper, processed_count):
        """Parquet 배치를 처리하여 매핑된 레코드 반환"""
        try:
            # PyArrow Table을 Pandas DataFrame으로 변환
            df = batch.to_pandas()

            batch_records = []
            current_count = processed_count

            for _, row in df.iterrows():
                try:
                    # Series를 dict로 변환
                    row_dict = row.to_dict()

                    # NaN 값을 None으로 변환
                    row_dict = self._clean_nan_values(row_dict)

                    mapped_record = field_mapper.map_record(row_dict)

                    if "cost" not in mapped_record:
                        # additional_info에서 cost 복구 시도 (빈 값은 기본값 처리)
                        cost_value = 0  # 기본값
                        if "additional_info" in mapped_record and isinstance(
                            mapped_record["additional_info"], dict
                        ):
                            cost_after_credits = mapped_record["additional_info"].get(
                                "Cost After Credits"
                            )
                            # 빈 값 처리: "", None, "null" -> 기본값 0
                            if (
                                cost_after_credits is None
                                or cost_after_credits == ""
                                or (
                                    isinstance(cost_after_credits, str)
                                    and cost_after_credits.lower() == "null"
                                )
                            ):
                                cost_value = 0
                            else:
                                # 나머지는 원본 데이터 그대로 사용
                                cost_value = cost_after_credits

                        # 최상위 cost 필드 추가 (첫 번째 위치)
                        new_record = {"cost": cost_value}
                        new_record.update(mapped_record)
                        mapped_record = new_record

                        _LOGGER.info(
                            f"[ParquetParser] RECOVERED cost field: {cost_value}"
                        )

                    # SpaceONE 프레임워크 호환성을 위해 data 필드 보장
                    if "data" not in mapped_record or not isinstance(
                        mapped_record["data"], dict
                    ):
                        # data 필드에 cost 정보 포함 (원본 데이터 보존)
                        mapped_record["data"] = {
                            "cost": mapped_record.get("cost"),
                            "list_price": mapped_record.get("cost"),
                        }
                    batch_records.append(mapped_record)
                    current_count += 1

                except Exception as e:
                    _LOGGER.warning(
                        f"[ParquetParser] Failed to process row {current_count + 1}: {e}"
                    )
                    continue

            # 배치 결과 생성
            if batch_records:
                # 페이징 단위 처리 로깅
                self._log_batch_processing(
                    len(batch_records), current_count, "parquet_stream"
                )
                # 동적 청크 크기 조정
                self._adjust_chunk_size_dynamically(len(batch_records), batch_records)
                self._log_parsing_progress(current_count, "parquet_stream")
                return self._create_batch_result(batch_records)

            return None

        except Exception as e:
            _LOGGER.error(f"[ParquetParser] Failed to process batch: {e}")
            return None

    def _clean_nan_values(self, row_dict: dict) -> dict:
        """NaN 값을 적절한 기본값으로 변환 (BigQuery 커넥터와 동일한 로직 적용)"""

        import pandas as pd

        cleaned_dict = {}

        # SpaceONE 빌링 필수 필드들의 데이터 타입 정의
        # 새로운 스키마 기준 필드 분류
        float_fields = [
            "cost",
            "currency_conversion_rate",
            "cost_at_list",
            "cost_at_effective_price_default",
            "cost_at_list_consumption_model",
        ]

        numeric_fields = [
            "effective_price",
            "tier_start_amount",
            "pricing_unit_quantity",
            "list_price",
            "effective_price_default",
            "list_price_consumption_model",
        ]

        usage_float_fields = ["amount", "amount_in_pricing_units"]  # usage 하위 필드
        credits_float_fields = ["amount"]  # credits 배열 내의 amount 필드

        timestamp_fields = ["usage_start_time", "usage_end_time", "export_time"]
        string_fields = [
            "billing_account_id",
            "currency",
            "transaction_type",
            "seller_name",
            "cost_type",
        ]

        # 명시적으로 문자열로 처리해야 하는 필드들 (cost가 포함되어도 float가 아님)
        explicit_string_fields = ["cost_type", "transaction_type", "seller_name"]

        # REPEATED 필드들 (배열로 처리)
        repeated_fields = ["labels", "system_labels", "tags", "credits"]

        # 중첩 구조 필드들 (RECORD 타입)
        record_fields = [
            "service",
            "sku",
            "project",
            "location",
            "price",
            "usage",
            "invoice",
            "adjustment_info",
            "consumption_model",
        ]

        field_types = {
            "float_fields": float_fields,
            "numeric_fields": numeric_fields,
            "usage_float_fields": usage_float_fields,
            "credits_float_fields": credits_float_fields,
            "timestamp_fields": timestamp_fields,
            "string_fields": string_fields,
            "explicit_string_fields": explicit_string_fields,
            "repeated_fields": repeated_fields,
            "record_fields": record_fields,
        }

        for key, value in row_dict.items():
            cleaned_dict[key] = self._process_field_value(key, value, field_types, pd)

        return cleaned_dict

    def _process_field_value(self, key, value, field_types, pd):
        """단일 필드 값을 처리"""
        try:
            # numpy 배열인 경우 처리
            array_result = self._handle_numpy_array(key, value, field_types)
            if array_result is not None:
                return array_result

            # pandas의 isna 함수로 NaN 값 체크
            if pd.isna(value):
                return self._get_nan_default_value(key, field_types)
            else:
                return self._convert_by_field_type(key, value, field_types)

        except Exception:
            return self._get_exception_fallback_value(key, value, field_types)

    def _handle_numpy_array(self, key, value, field_types):
        """numpy 배열 처리"""
        if not (hasattr(value, "__array__") and hasattr(value, "size")):
            return None

        if value.size == 0:  # 빈 배열
            return [] if key in field_types["repeated_fields"] else ""
        elif value.size == 1:  # 단일 값 배열
            return value.item()  # 스칼라 값으로 변환
        else:  # 다중 값 배열
            return value.tolist()  # 리스트로 변환

    def _get_nan_default_value(self, key, field_types):
        """NaN 값에 대한 기본값 반환 - 새로운 스키마 기준"""
        if (
            key in field_types["float_fields"]
            or key in field_types["numeric_fields"]
            or key in field_types["usage_float_fields"]
            or key in field_types["credits_float_fields"]
            or (
                any(
                    field in key.lower()
                    for field in ["cost", "amount", "price", "rate"]
                )
                and key not in field_types["explicit_string_fields"]
            )
        ):
            return 0.0
        elif key in field_types["repeated_fields"]:
            return []
        elif key in field_types["record_fields"]:
            return {}
        else:
            return ""

    def _convert_by_field_type(self, key, value, field_types):
        """필드 타입에 따라 값 변환 - 새로운 스키마 기준"""
        # 명시적 문자열 필드 우선 처리
        if key in field_types["explicit_string_fields"]:
            return self._convert_to_string_safe(value)

        # FLOAT 타입 필드 처리 (명시적 문자열 필드 제외)
        elif (
            key in field_types["float_fields"]
            or key in field_types["usage_float_fields"]
            or key in field_types["credits_float_fields"]
            or (
                any(field in key.lower() for field in ["cost", "rate"])
                and key not in field_types["explicit_string_fields"]
            )
        ):
            return self._convert_to_float_safe(value)

        # NUMERIC 타입 필드 처리 (높은 정밀도)
        elif key in field_types["numeric_fields"] or any(
            field in key.lower() for field in ["price"]
        ):
            return self._convert_to_numeric_safe(value)

        # TIMESTAMP 필드를 문자열로 변환
        elif key in field_types["timestamp_fields"] or any(
            field in key.lower() for field in ["time"]
        ):
            return self._convert_to_datetime_string(value, key)

        # STRING 필드 처리
        elif key in field_types["string_fields"] or any(
            field in key.lower() for field in ["id", "name", "description", "type"]
        ):
            return self._convert_to_string_safe(value)

        # REPEATED 필드 처리 (배열)
        elif key in field_types["repeated_fields"]:
            return self._process_repeated_field_parquet(value)

        # RECORD 타입 필드 처리 (중첩 구조)
        elif key in field_types["record_fields"]:
            return self._normalize_nested_structure_parquet(value)

        # 기타 필드
        else:
            return value

    def _get_exception_fallback_value(self, key, value, field_types):
        """예외 발생 시 안전한 기본값 반환 - 새로운 스키마 기준"""
        if (
            key in field_types["float_fields"]
            or key in field_types["numeric_fields"]
            or key in field_types["usage_float_fields"]
            or key in field_types["credits_float_fields"]
            or key.lower() in ["cost", "usage_quantity", "amount"]
        ):
            return 0.0
        elif key in field_types["repeated_fields"]:
            return []
        elif key in field_types["record_fields"]:
            return {}
        else:
            return str(value) if value is not None else ""

    def _convert_to_numeric_safe(self, value):
        """값을 안전하게 숫자로 변환: 빈 값은 기본값으로, 나머지는 원본 보존"""
        # 빈 값 처리: "", None, "null" -> 기본값 0
        if (
            value is None
            or value == ""
            or (isinstance(value, str) and value.lower() in ("null", "nan"))
        ):
            return 0

        # 나머지는 원본 그대로 보존
        try:
            if isinstance(value, (int, float)):
                return value  # 원본 그대로
            if isinstance(value, str):
                cleaned_value = value.strip()
                if not cleaned_value:
                    return 0
                return float(cleaned_value)  # 문자열 숫자만 변환
            return value  # 원본 그대로
        except (ValueError, TypeError):
            return 0

    def _convert_to_string_safe(self, value):
        """값을 안전하게 문자열로 변환"""
        if value is None:
            return ""

        if isinstance(value, str):
            return value.replace("nan", "") if value == "nan" else value

        return str(value)

    def _convert_to_datetime_string(self, value, field_name):
        """날짜/시간 값을 SpaceONE 표준 문자열 형식으로 변환"""
        if value is None or value == "":
            return ""

        try:
            import pandas as pd

            # 이미 문자열인 경우
            if isinstance(value, str):
                return value

            # pandas Timestamp인 경우
            if isinstance(value, pd.Timestamp):
                if "time" in field_name.lower():
                    return value.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    return value.strftime("%Y-%m-%d")

            # 기타 datetime 객체
            from datetime import date, datetime

            if isinstance(value, (datetime, date)):
                if "time" in field_name.lower():
                    return value.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    return value.strftime("%Y-%m-%d")

            # 기타 타입은 문자열로 변환
            return str(value)

        except Exception:
            return str(value) if value is not None else ""

    def _normalize_nested_structure_parquet(self, value):
        """Parquet의 중첩 구조를 SpaceONE 호환 형태로 변환 (BigQuery와 동일한 로직)"""
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
                if value.strip() == "" or value.lower() == "nan":
                    return {}
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, (dict, list)) else {}
                except (json.JSONDecodeError, ValueError):
                    return value

            # 기타 타입은 문자열로 변환 후 재시도
            str_value = str(value)
            if str_value.lower() in ["nan", "none", ""]:
                return {}

            try:
                parsed = json.loads(str_value)
                return parsed if isinstance(parsed, (dict, list)) else {}
            except (json.JSONDecodeError, ValueError):
                return str_value

        except Exception:
            return {} if value is None else str(value)

    def get_parquet_schema(self, stream: IO) -> dict:
        """Parquet 파일의 스키마 정보 반환"""
        try:
            import pyarrow.parquet as pq

            parquet_file = pq.ParquetFile(stream)
            schema = parquet_file.schema

            schema_info = {
                "columns": [],
                "num_rows": parquet_file.metadata.num_rows,
                "num_row_groups": parquet_file.num_row_groups,
            }

            for i in range(len(schema)):
                field = schema.field(i)
                schema_info["columns"].append(
                    {
                        "name": field.name,
                        "type": str(field.type),
                        "nullable": field.nullable,
                    }
                )

            return schema_info

        except Exception as e:
            _LOGGER.error(f"[ParquetParser] Failed to get schema: {e}")
            return {}

    def get_column_statistics(self, stream: IO, column_name: str) -> dict:
        """특정 컬럼의 통계 정보 반환"""
        try:
            import pyarrow.parquet as pq

            parquet_file = pq.ParquetFile(stream)

            # 컬럼별 통계 정보 수집
            stats = {"min": None, "max": None, "null_count": 0, "distinct_count": None}

            # Row group별 메타데이터에서 통계 정보 추출
            for rg_idx in range(parquet_file.num_row_groups):
                row_group = parquet_file.metadata.row_group(rg_idx)

                for col_idx in range(row_group.num_columns):
                    col_meta = row_group.column(col_idx)

                    if col_meta.path_in_schema == column_name:
                        if col_meta.statistics:
                            if (
                                stats["min"] is None
                                or col_meta.statistics.min < stats["min"]
                            ):
                                stats["min"] = col_meta.statistics.min
                            if (
                                stats["max"] is None
                                or col_meta.statistics.max > stats["max"]
                            ):
                                stats["max"] = col_meta.statistics.max
                            stats["null_count"] += col_meta.statistics.null_count

            return stats

        except Exception:
            return {}

    def _convert_to_float_safe(self, value):
        """값을 안전하게 FLOAT 타입으로 변환"""
        if value is None or value == "":
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
                if value.strip().lower() in ("", "nan", "none", "null"):
                    return 0.0
                # 숫자가 아닌 문자열인 경우 0.0 반환 (예: 'regular', 'usage' 등)
                stripped_value = value.strip()
                try:
                    return float(stripped_value)
                except ValueError:
                    _LOGGER.debug(
                        f"[ParquetParser] Non-numeric string in FLOAT field: '{value}', using 0.0"
                    )
                    return 0.0
            else:
                return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _process_repeated_field_parquet(self, value):
        """REPEATED 필드를 배열로 처리 (Parquet 전용)"""
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
            return self._clean_repeated_array_parquet(value)

        # numpy 배열인 경우
        if hasattr(value, "__array__") and hasattr(value, "size"):
            if value.size == 0:
                return []
            else:
                return value.tolist()

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(value, str):
            str_value = value.strip()
            if not str_value or str_value.lower() in ("none", "null", "", "nan"):
                return []

            try:
                import json

                parsed = json.loads(str_value)
                if isinstance(parsed, list):
                    return self._clean_repeated_array_parquet(parsed)
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

    def _clean_repeated_array_parquet(self, array: list) -> list:
        """REPEATED 배열의 각 항목을 정리 (Parquet 전용)"""
        cleaned = []
        for item in array:
            if item is None:
                continue

            # pandas NaN 체크
            try:
                import pandas as pd

                if pd.isna(item):
                    continue
            except (TypeError, ValueError, ImportError):
                pass

            # 빈 문자열이나 null 값 제거
            if isinstance(item, str) and item.strip().lower() in (
                "",
                "none",
                "null",
                "nan",
            ):
                continue

            cleaned.append(item)

        return cleaned
