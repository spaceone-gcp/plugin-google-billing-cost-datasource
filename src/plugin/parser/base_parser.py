import logging
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import IO

from ..conf.cost_conf import HTTP_FILE_CONFIG
from ..manager.field_mapper import FieldMapper

_LOGGER = logging.getLogger("spaceone")


class BaseParser(ABC):
    """파일 파서 기본 클래스"""

    def __init__(self):
        self.chunk_size = HTTP_FILE_CONFIG["default_chunk_size"]  # 기본 청크 크기
        self.max_chunk_size = HTTP_FILE_CONFIG["max_chunk_size"]  # 최대 청크 크기
        self.grpc_message_limit = HTTP_FILE_CONFIG[
            "grpc_message_size_limit"
        ]  # gRPC 메시지 크기 제한

    @abstractmethod
    def parse_stream(
        self, stream: IO, field_mapper: FieldMapper, **kwargs
    ) -> Generator[dict, None, None]:
        """스트림을 파싱하여 매핑된 데이터 반환

        Args:
            stream: 파일 스트림
            field_mapper: 필드 매핑 객체
            **kwargs: 추가 파싱 옵션

        Yields:
            매핑된 비용 데이터 레코드
        """
        pass

    def set_chunk_size(self, chunk_size: int):
        """청크 크기 설정"""
        self.chunk_size = max(1, min(chunk_size, self.max_chunk_size))

    def _create_batch_result(self, records: list) -> dict:
        """배치 결과 생성 - billed_date 필드 검증 및 직렬화 포함"""
        # 🚨 CRITICAL: 모든 레코드에 billed_date 필드가 있는지 검증
        validated_records = []
        for record in records:
            if not record.get("billed_date"):
                from datetime import datetime

                record["billed_date"] = datetime.now().strftime("%Y-%m-%d")

            # 🚨 CRITICAL: 모든 Pandas/Numpy 객체를 직렬화 가능한 타입으로 변환
            sanitized_record = self._sanitize_record_for_serialization(record)

            # 🚨 CRITICAL: SpaceONE 프레임워크 요구사항 준수
            # Google Cloud Billing에는 data 필드가 없지만, SpaceONE에서 필수로 요구함
            # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
            # SpaceONE 검증 오류 해결을 위해 빈 딕셔너리 제공
            sanitized_record["data"] = {}

            validated_records.append(sanitized_record)

        # 🚨 FINAL CRITICAL: SpaceONE 프레임워크 요구사항 최종 확인
        # Google Cloud Billing에는 data 필드가 없지만, SpaceONE에서 필수로 요구함
        # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
        final_results = []
        for record in validated_records:
            # SpaceONE 검증 오류 해결을 위해 data 필드를 빈 딕셔너리로 보장
            if "data" not in record or not isinstance(record["data"], dict):
                record["data"] = {}
            final_results.append(record)

        return {"results": final_results}

    def _sanitize_record_for_serialization(self, record: dict) -> dict:
        """레코드를 JSON 직렬화 가능한 타입으로 변환"""
        from datetime import date, datetime
        from decimal import Decimal

        import numpy as np
        import pandas as pd

        def convert_value(value):
            """개별 값을 직렬화 가능한 타입으로 변환"""
            # 🚨 CRITICAL: None 체크를 먼저 수행
            if value is None:
                return None
            # 🚨 CRITICAL: Pandas NA 체크는 안전하게 수행
            try:
                if pd.isna(value):
                    return None
            except (TypeError, ValueError):
                # pd.isna()가 실패하면 무시하고 계속 진행
                pass

            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                # Pandas Timestamp/Timedelta -> 문자열
                return str(value)
            elif isinstance(value, (np.integer, np.floating)):
                # Numpy 숫자 타입 -> Python 기본 타입
                return value.item()
            elif isinstance(value, np.ndarray):
                # Numpy 배열 -> 리스트
                return [convert_value(item) for item in value]
            elif isinstance(value, (datetime, date)):
                # Python datetime -> 문자열
                return value.isoformat()
            elif isinstance(value, Decimal):
                # Decimal -> float
                return float(value)
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 처리
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                # 리스트/튜플 재귀 처리
                return [convert_value(item) for item in value]
            else:
                return value

        # 전체 레코드 변환
        sanitized_record = {}
        for key, value in record.items():
            try:
                sanitized_record[key] = convert_value(value)
            except Exception as e:
                _LOGGER.warning(
                    f"[BaseParser] Failed to sanitize field {key}: {e}, converting to string"
                )
                sanitized_record[key] = str(value)  # 실패 시 문자열로 변환

        return sanitized_record

    def _estimate_message_size(self, records: list) -> int:
        """메시지 크기 추정 (바이트 단위)"""
        try:
            # 첫 번째 레코드를 기준으로 평균 레코드 크기 추정
            if not records:
                return 0

            # 샘플 레코드의 메모리 사용량 추정
            sample_record = records[0]
            estimated_record_size = len(str(sample_record).encode("utf-8"))

            # 전체 배치 크기 추정 (JSON 직렬화 오버헤드 고려)
            total_size = estimated_record_size * len(records) * 1.5  # 1.5배 여유분
            return int(total_size)
        except Exception as e:
            _LOGGER.warning(f"[BaseParser] Failed to estimate message size: {e}")
            # 안전한 기본값 반환
            return len(records) * 1000  # 레코드당 1KB로 추정

    def _adjust_chunk_size_dynamically(self, current_batch_size: int, records: list):
        """동적 청크 크기 조정"""
        estimated_size = self._estimate_message_size(records)

        if estimated_size > self.grpc_message_limit * 0.8:  # 80% 임계값
            # 청크 크기를 줄여야 함
            new_chunk_size = max(100, int(self.chunk_size * 0.7))
            if new_chunk_size != self.chunk_size:
                self.chunk_size = new_chunk_size
        elif (
            estimated_size < self.grpc_message_limit * 0.3
            and self.chunk_size < self.max_chunk_size
        ):
            # 청크 크기를 늘릴 수 있음
            new_chunk_size = min(self.max_chunk_size, int(self.chunk_size * 1.2))
            if new_chunk_size != self.chunk_size:
                self.chunk_size = new_chunk_size

    def _log_parsing_progress(self, processed_count: int, file_name: str = ""):
        """파싱 진행 상황 로깅"""
        if processed_count > 0 and processed_count % 1000 == 0:
            file_info = f" in {file_name}" if file_name else ""
            _LOGGER.info(f"[{self.__class__.__name__}] Processed {processed_count:,} records{file_info}")

    def _log_batch_processing(self, batch_size: int, total_processed: int, file_name: str = ""):
        """배치 처리 로깅 - 페이징 단위 카운트 추가"""
        file_info = f" from {file_name}" if file_name else ""
        _LOGGER.info(
            f"[{self.__class__.__name__}] Processing batch: {batch_size:,} records "
            f"(Total processed: {total_processed:,}){file_info}"
        )
