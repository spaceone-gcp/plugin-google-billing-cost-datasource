import json
import logging
from collections.abc import Generator
from io import TextIOWrapper
from typing import IO

from ..error.cost import ERROR_FILE_PARSING_FAILED
from ..manager.field_mapper import FieldMapper
from .base_parser import BaseParser

_LOGGER = logging.getLogger("spaceone")


class JSONParser(BaseParser):
    """JSON 파일 파서 (JSON Lines 및 일반 JSON 배열 지원)"""

    def parse_stream(
        self, stream: IO, field_mapper: FieldMapper, **kwargs
    ) -> Generator[dict, None, None]:
        """JSON 스트림을 파싱하여 매핑된 데이터 반환

        Args:
            stream: JSON 파일 스트림
            field_mapper: 필드 매핑 객체
            **kwargs: 추가 파싱 옵션
                - encoding: 문자 인코딩 (기본값: 'utf-8')
                - json_lines: JSON Lines 형식 여부 (기본값: 자동 감지)
                - root_path: JSON 배열이 위치한 경로 (예: 'data.records')

        Yields:
            매핑된 비용 데이터 레코드
        """
        encoding = kwargs.get("encoding", "utf-8")
        json_lines = kwargs.get("json_lines", None)  # None이면 자동 감지
        root_path = kwargs.get("root_path", None)

        try:
            # 바이트 스트림을 텍스트 스트림으로 변환
            if hasattr(stream, "mode") and "b" in stream.mode:
                text_stream = TextIOWrapper(stream, encoding=encoding)
            else:
                text_stream = stream

            # JSON Lines 형식 자동 감지 또는 명시적 설정
            if json_lines is None:
                json_lines = self._detect_json_lines_format(text_stream)
                text_stream.seek(0)  # 스트림 위치 초기화

            if json_lines:
                yield from self._parse_json_lines(text_stream, field_mapper)
            else:
                yield from self._parse_json_array(text_stream, field_mapper, root_path)

        except Exception as e:
            _LOGGER.error(f"[JSONParser] Failed to parse JSON stream: {e}")
            raise ERROR_FILE_PARSING_FAILED(
                file_path="json_stream", reason=str(e)
            ) from e
        finally:
            # TextIOWrapper 정리 (원본 스트림은 닫지 않음)
            if hasattr(text_stream, "detach"):
                try:
                    text_stream.detach()
                except Exception:
                    pass

    def _parse_json_lines(
        self, text_stream: IO, field_mapper: FieldMapper
    ) -> Generator[dict, None, None]:
        """JSON Lines 형식 파싱"""
        processed_count = 0
        batch_records = []

        for line_num, line in enumerate(text_stream, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
                mapped_record = field_mapper.map_record(record)
                
                # 🚨 CRITICAL: cost 필드 보장 (field_mapper 결과 검증)
                if "cost" not in mapped_record:
                    # additional_info에서 cost 복구 시도
                    cost_value = 0.0
                    if "additional_info" in mapped_record and isinstance(mapped_record["additional_info"], dict):
                        cost_after_credits = mapped_record["additional_info"].get("Cost After Credits", 0)
                        try:
                            cost_value = float(cost_after_credits)
                        except (ValueError, TypeError):
                            cost_value = 0.0
                    
                    # 최상위 cost 필드 추가 (첫 번째 위치)
                    new_record = {"cost": cost_value}
                    new_record.update(mapped_record)
                    mapped_record = new_record
                    
                    _LOGGER.info(f"[JSONParser] RECOVERED cost field: {cost_value}")
                
                batch_records.append(mapped_record)
                processed_count += 1

                # 배치 단위로 yield
                if len(batch_records) >= self.chunk_size:
                    # 페이징 단위 처리 로깅
                    self._log_batch_processing(
                        len(batch_records), processed_count, "json_lines_stream"
                    )
                    # 동적 청크 크기 조정
                    self._adjust_chunk_size_dynamically(
                        len(batch_records), batch_records
                    )
                    yield self._create_batch_result(batch_records)
                    batch_records = []
                    self._log_parsing_progress(processed_count, "json_lines_stream")

            except json.JSONDecodeError as e:
                _LOGGER.warning(f"[JSONParser] Invalid JSON at line {line_num}: {e}")
                continue
            except Exception as e:
                _LOGGER.warning(f"[JSONParser] Failed to process line {line_num}: {e}")
                continue

        # 남은 레코드 처리
        if batch_records:
            self._log_batch_processing(
                len(batch_records), processed_count, "json_lines_stream"
            )
            yield self._create_batch_result(batch_records)

    def _parse_json_array(
        self, text_stream: IO, field_mapper: FieldMapper, root_path: str = None
    ) -> Generator[dict, None, None]:
        """JSON 배열 형식 파싱"""
        try:
            # 전체 JSON 로드 (큰 파일의 경우 메모리 문제 가능성)
            data = json.load(text_stream)

            # root_path가 지정된 경우 해당 경로의 배열 추출
            if root_path:
                data = self._extract_from_path(data, root_path)

            # 배열이 아닌 경우 단일 객체를 배열로 변환
            if not isinstance(data, list):
                data = [data]

            processed_count = 0
            batch_records = []

            for record in data:
                try:
                    mapped_record = field_mapper.map_record(record)
                    batch_records.append(mapped_record)
                    processed_count += 1

                    # 배치 단위로 yield
                    if len(batch_records) >= self.chunk_size:
                        # 페이징 단위 처리 로깅
                        self._log_batch_processing(
                            len(batch_records), processed_count, "json_array_stream"
                        )
                        yield self._create_batch_result(batch_records)
                        batch_records = []
                        self._log_parsing_progress(processed_count, "json_array_stream")

                except Exception as e:
                    _LOGGER.warning(
                        f"[JSONParser] Failed to process record {processed_count + 1}: {e}"
                    )
                    continue

            # 남은 레코드 처리
            if batch_records:
                self._log_batch_processing(
                    len(batch_records), processed_count, "json_array_stream"
                )
                yield self._create_batch_result(batch_records)

        except json.JSONDecodeError as e:
            raise ERROR_FILE_PARSING_FAILED(
                file_path="json_stream", reason=f"Invalid JSON format: {e}"
            )

    def _detect_json_lines_format(self, text_stream: IO) -> bool:
        """JSON Lines 형식 자동 감지"""
        try:
            # 첫 몇 줄을 읽어서 JSON Lines 형식인지 확인
            sample_lines = []
            for _ in range(5):  # 최대 5줄 샘플링
                line = text_stream.readline()
                if not line:
                    break
                sample_lines.append(line.strip())

            if not sample_lines:
                return False

            # 각 줄이 유효한 JSON인지 확인
            valid_json_lines = 0
            for line in sample_lines:
                if line:
                    try:
                        json.loads(line)
                        valid_json_lines += 1
                    except json.JSONDecodeError:
                        pass

            # 50% 이상이 유효한 JSON 라인이면 JSON Lines 형식으로 판단
            is_json_lines = (
                valid_json_lines >= len([line for line in sample_lines if line]) * 0.5
            )

            return is_json_lines

        except Exception:
            return False

    def _extract_from_path(self, data: dict, path: str) -> any:
        """점 표기법 경로에서 데이터 추출 (예: 'data.records')"""
        try:
            current = data
            for key in path.split("."):
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    raise KeyError(f"Path '{path}' not found in JSON data")
            return current
        except Exception:
            return data
