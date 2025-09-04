import logging
from abc import ABC, abstractmethod
from typing import IO, Generator

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
        """배치 결과 생성"""
        return {"results": records}

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
                _LOGGER.info(
                    f"[{self.__class__.__name__}] Reducing chunk size from {self.chunk_size} to {new_chunk_size} "
                    f"(estimated size: {estimated_size / 1024 / 1024:.2f}MB)"
                )
                self.chunk_size = new_chunk_size
        elif (
            estimated_size < self.grpc_message_limit * 0.3
            and self.chunk_size < self.max_chunk_size
        ):
            # 청크 크기를 늘릴 수 있음
            new_chunk_size = min(self.max_chunk_size, int(self.chunk_size * 1.2))
            if new_chunk_size != self.chunk_size:
                _LOGGER.debug(
                    f"[{self.__class__.__name__}] Increasing chunk size from {self.chunk_size} to {new_chunk_size}"
                )
                self.chunk_size = new_chunk_size

    def _log_parsing_progress(self, processed_count: int, file_name: str = ""):
        """파싱 진행 상황 로깅"""
        if processed_count % 10000 == 0:
            _LOGGER.info(
                f"[{self.__class__.__name__}] Processed {processed_count} records from {file_name}"
            )
