import csv
import logging
from collections.abc import Generator
from io import TextIOWrapper
from typing import IO

from ..error.cost import ERROR_FILE_PARSING_FAILED
from ..manager.field_mapper import FieldMapper
from .base_parser import BaseParser

_LOGGER = logging.getLogger("spaceone")


class CSVParser(BaseParser):
    """CSV 파일 파서"""

    def parse_stream(
        self, stream: IO, field_mapper: FieldMapper, **kwargs
    ) -> Generator[dict, None, None]:
        """CSV 스트림을 파싱하여 매핑된 데이터 반환

        Args:
            stream: CSV 파일 스트림
            field_mapper: 필드 매핑 객체
            **kwargs: 추가 파싱 옵션
                - delimiter: CSV 구분자 (기본값: ',')
                - encoding: 문자 인코딩 (기본값: 'utf-8')
                - has_header: 헤더 행 존재 여부 (기본값: True)

        Yields:
            매핑된 비용 데이터 레코드
        """
        delimiter = kwargs.get("delimiter", ",")
        encoding = kwargs.get("encoding", "utf-8")
        has_header = kwargs.get("has_header", True)

        try:
            # 바이트 스트림을 텍스트 스트림으로 변환
            # BytesIO 객체이거나 바이너리 모드인 경우 텍스트로 변환
            if (hasattr(stream, "mode") and "b" in stream.mode) or (
                hasattr(stream, "read") and isinstance(stream.read(0), bytes)
            ):
                # 스트림 위치를 처음으로 되돌림
                if hasattr(stream, "seek"):
                    stream.seek(0)
                text_stream = TextIOWrapper(stream, encoding=encoding)
            else:
                text_stream = stream

            csv_reader = (
                csv.DictReader(text_stream, delimiter=delimiter)
                if has_header
                else csv.reader(text_stream, delimiter=delimiter)
            )

            processed_count = 0
            batch_records = []

            if has_header:
                # DictReader 사용 (헤더가 있는 경우)
                for row in csv_reader:
                    try:
                        mapped_record = field_mapper.map_record(row)
                        batch_records.append(mapped_record)
                        processed_count += 1

                        # 배치 단위로 yield
                        if len(batch_records) >= self.chunk_size:
                            # 페이징 단위 처리 로깅
                            self._log_batch_processing(
                                len(batch_records), processed_count, "csv_stream"
                            )
                            # 동적 청크 크기 조정
                            self._adjust_chunk_size_dynamically(
                                len(batch_records), batch_records
                            )
                            yield self._create_batch_result(batch_records)
                            batch_records = []
                            self._log_parsing_progress(processed_count, "csv_stream")

                    except Exception as e:
                        _LOGGER.warning(
                            f"[CSVParser] Failed to process row {processed_count + 1}: {e}"
                        )
                        continue
            else:
                # 일반 reader 사용 (헤더가 없는 경우)
                headers = kwargs.get("headers", [])
                if not headers:
                    raise ERROR_FILE_PARSING_FAILED(
                        file_path="csv_stream",
                        reason="Headers required when has_header=False",
                    )

                for row in csv_reader:
                    try:
                        # 리스트를 딕셔너리로 변환
                        row_dict = {}
                        for i, value in enumerate(row):
                            if i < len(headers):
                                row_dict[headers[i]] = value

                        mapped_record = field_mapper.map_record(row_dict)
                        batch_records.append(mapped_record)
                        processed_count += 1

                        # 배치 단위로 yield
                        if len(batch_records) >= self.chunk_size:
                            # 페이징 단위 처리 로깅
                            self._log_batch_processing(
                                len(batch_records), processed_count, "csv_stream"
                            )
                            # 동적 청크 크기 조정
                            self._adjust_chunk_size_dynamically(
                                len(batch_records), batch_records
                            )
                            yield self._create_batch_result(batch_records)
                            batch_records = []
                            self._log_parsing_progress(processed_count, "csv_stream")

                    except Exception as e:
                        _LOGGER.warning(
                            f"[CSVParser] Failed to process row {processed_count + 1}: {e}"
                        )
                        continue

            # 남은 레코드 처리
            if batch_records:
                self._log_batch_processing(
                    len(batch_records), processed_count, "csv_stream"
                )
                yield self._create_batch_result(batch_records)


        except Exception as e:
            _LOGGER.error(f"[CSVParser] Failed to parse CSV stream: {e}")
            raise ERROR_FILE_PARSING_FAILED(file_path="csv_stream", reason=str(e))
        finally:
            # TextIOWrapper 정리 (원본 스트림은 닫지 않음)
            if hasattr(text_stream, "detach"):
                try:
                    text_stream.detach()
                except Exception:
                    pass

    def detect_delimiter(self, sample_data: str) -> str:
        """CSV 구분자 자동 감지"""
        try:
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample_data[:1024]).delimiter
            return delimiter
        except Exception:
            return ","

    def detect_encoding(self, sample_bytes: bytes) -> str:
        """문자 인코딩 자동 감지"""
        try:
            import chardet

            result = chardet.detect(sample_bytes[:10240])  # 첫 10KB 샘플링
            encoding = result.get("encoding", "utf-8")
            confidence = result.get("confidence", 0)

            if confidence > 0.7:
                return encoding
            else:
                return "utf-8"
        except ImportError:
            return "utf-8"
        except Exception:
            return "utf-8"
