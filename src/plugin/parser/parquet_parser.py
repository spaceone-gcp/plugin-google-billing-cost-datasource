import logging
from typing import IO, Generator

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
            except ImportError:
                raise ERROR_FILE_PARSING_FAILED(
                    file_path="parquet_stream",
                    reason="pyarrow library is required for Parquet parsing. Install with: pip install pyarrow",
                )

            # 스트림에서 Parquet 파일 읽기
            parquet_file = pq.ParquetFile(stream)

            # 메타데이터 정보 로깅
            metadata = parquet_file.metadata
            _LOGGER.debug(
                f"[ParquetParser] Parquet file info: "
                f"rows={metadata.num_rows}, "
                f"columns={parquet_file.schema.names}"
            )

            # 배치 단위로 데이터 읽기
            processed_count = 0

            # 배치 크기 조정 (Parquet은 일반적으로 큰 배치가 효율적)
            batch_size = max(self.chunk_size, 1000)

            for batch in parquet_file.iter_batches(
                batch_size=batch_size, columns=columns, use_pandas_metadata=True
            ):
                try:
                    # PyArrow Table을 Pandas DataFrame으로 변환
                    df = batch.to_pandas()

                    batch_records = []
                    for _, row in df.iterrows():
                        try:
                            # Series를 dict로 변환
                            row_dict = row.to_dict()

                            # NaN 값을 None으로 변환
                            row_dict = self._clean_nan_values(row_dict)

                            mapped_record = field_mapper.map_record(row_dict)
                            batch_records.append(mapped_record)
                            processed_count += 1

                        except Exception as e:
                            _LOGGER.warning(
                                f"[ParquetParser] Failed to process row {processed_count + 1}: {e}"
                            )
                            continue

                    # 배치 결과 yield
                    if batch_records:
                        # 동적 청크 크기 조정
                        self._adjust_chunk_size_dynamically(
                            len(batch_records), batch_records
                        )
                        yield self._create_batch_result(batch_records)
                        self._log_parsing_progress(processed_count)

                except Exception as e:
                    _LOGGER.error(f"[ParquetParser] Failed to process batch: {e}")
                    continue

            _LOGGER.info(
                f"[ParquetParser] Successfully processed {processed_count} records"
            )

        except Exception as e:
            _LOGGER.error(f"[ParquetParser] Failed to parse Parquet stream: {e}")
            raise ERROR_FILE_PARSING_FAILED(file_path="parquet_stream", reason=str(e))

    def _clean_nan_values(self, row_dict: dict) -> dict:
        """NaN 값을 적절한 기본값으로 변환"""
        import pandas as pd

        cleaned_dict = {}
        for key, value in row_dict.items():
            try:
                # numpy 배열인 경우 처리
                if hasattr(value, "__array__") and hasattr(value, "size"):
                    if value.size == 0:  # 빈 배열
                        cleaned_dict[key] = ""
                        continue
                    elif value.size == 1:  # 단일 값 배열
                        value = value.item()  # 스칼라 값으로 변환
                    else:  # 다중 값 배열
                        cleaned_dict[key] = str(
                            value.tolist()
                        )  # 리스트로 변환 후 문자열화
                        continue

                # pandas의 isna 함수로 NaN 값 체크
                if pd.isna(value):
                    # 타입에 따라 적절한 기본값 설정
                    if isinstance(value, (int, float)) or key.lower() in [
                        "cost",
                        "usage_quantity",
                        "amount",
                    ]:
                        cleaned_dict[key] = 0
                    else:
                        cleaned_dict[key] = ""
                else:
                    cleaned_dict[key] = value

            except Exception as e:
                # 예외 발생 시 기본값으로 처리
                _LOGGER.debug(
                    f"[ParquetParser] Failed to process value for key '{key}': {e}"
                )
                if key.lower() in ["cost", "usage_quantity", "amount"]:
                    cleaned_dict[key] = 0
                else:
                    cleaned_dict[key] = ""

        return cleaned_dict

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

        except Exception as e:
            _LOGGER.warning(f"[ParquetParser] Failed to get column statistics: {e}")
            return {}
