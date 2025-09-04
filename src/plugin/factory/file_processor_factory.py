import logging
from typing import Optional

from ..conf.cost_conf import HTTP_FILE_CONFIG
from ..error.cost import ERROR_UNSUPPORTED_FILE_FORMAT
from ..parser.base_parser import BaseParser
from ..parser.csv_parser import CSVParser
from ..parser.json_parser import JSONParser
from ..parser.parquet_parser import ParquetParser

_LOGGER = logging.getLogger("spaceone")


class FileProcessorFactory:
    """파일 처리기 팩토리"""

    @staticmethod
    def create_parser(file_format: str) -> BaseParser:
        """파일 형식에 맞는 파서 생성

        Args:
            file_format: 파일 형식 ('csv', 'json', 'parquet')

        Returns:
            해당 형식의 파서 인스턴스

        Raises:
            ERROR_UNSUPPORTED_FILE_FORMAT: 지원하지 않는 파일 형식
        """
        if file_format not in HTTP_FILE_CONFIG["supported_formats"]:
            raise ERROR_UNSUPPORTED_FILE_FORMAT(format=file_format)

        parser_map = {"csv": CSVParser, "json": JSONParser, "parquet": ParquetParser}

        parser_class = parser_map.get(file_format)
        if not parser_class:
            raise ERROR_UNSUPPORTED_FILE_FORMAT(format=file_format)

        parser = parser_class()
        parser.set_chunk_size(HTTP_FILE_CONFIG["default_chunk_size"])

        _LOGGER.debug(f"[FileProcessorFactory] Created {file_format} parser")
        return parser

    @staticmethod
    def detect_file_format(file_name: str, content_sample: bytes = None) -> str:
        """파일 형식 자동 감지

        Args:
            file_name: 파일명
            content_sample: 파일 내용 샘플 (선택적)

        Returns:
            감지된 파일 형식

        Raises:
            ERROR_UNSUPPORTED_FILE_FORMAT: 형식을 감지할 수 없는 경우
        """
        # 압축 확장자 제거 (내용 샘플이 있으면 함께 전달)
        from ..utils.compression import CompressionHandler

        # Parquet 파일인지 먼저 확인 (최우선)
        if (
            content_sample
            and len(content_sample) >= 4
            and content_sample[:4] == b"PAR1"
        ):
            # Parquet 파일인 경우 압축 확장자 제거 없이 원본 파일명 사용
            clean_name = file_name
            _LOGGER.info(
                f"[FileProcessorFactory] Parquet file detected, using original filename: {file_name}"
            )
        else:
            # Parquet이 아닌 경우에만 압축 감지 수행
            compression_type = CompressionHandler.detect_compression(
                file_name, content_sample
            )
            if compression_type:
                # 실제로 압축된 파일인 경우에만 확장자 제거
                clean_name = file_name[: -len(f".{compression_type}")]
            else:
                # 압축되지 않은 파일인 경우 원본 파일명 사용
                clean_name = file_name

        # 파일 확장자로 형식 감지
        name_lower = clean_name.lower()

        if name_lower.endswith(".csv"):
            return "csv"
        elif name_lower.endswith(".json") or name_lower.endswith(".jsonl"):
            return "json"
        elif name_lower.endswith(".parquet"):
            return "parquet"

        # 파일 내용으로 형식 감지 (확장자로 판단할 수 없는 경우)
        if content_sample:
            detected_format = FileProcessorFactory._detect_format_by_content(
                content_sample
            )
            if detected_format:
                _LOGGER.debug(
                    f"[FileProcessorFactory] Format detected by content: {detected_format}"
                )
                return detected_format

        # 감지 실패
        raise ERROR_UNSUPPORTED_FILE_FORMAT(
            format=f"Cannot detect format for file: {file_name}"
        )

    @staticmethod
    def _detect_format_by_content(content_sample: bytes) -> Optional[str]:
        """파일 내용으로 형식 감지"""
        try:
            # 첫 1KB 샘플 사용
            sample = content_sample[:1024]

            # Parquet 매직 넘버 확인 (PAR1)
            if sample.startswith(b"PAR1"):
                return "parquet"

            # 텍스트 형식으로 변환 시도
            try:
                text_sample = sample.decode("utf-8", errors="ignore").strip()
            except Exception:
                return None

            if not text_sample:
                return None

            # JSON 형식 확인
            if FileProcessorFactory._is_json_format(text_sample):
                return "json"

            # CSV 형식 확인
            if FileProcessorFactory._is_csv_format(text_sample):
                return "csv"

            return None

        except Exception as e:
            _LOGGER.debug(f"[FileProcessorFactory] Content detection failed: {e}")
            return None

    @staticmethod
    def _is_json_format(text_sample: str) -> bool:
        """JSON 형식인지 확인"""
        import json

        # JSON 객체/배열로 시작하는지 확인
        if text_sample.startswith(("{", "[")):
            try:
                json.loads(text_sample)
                return True
            except json.JSONDecodeError:
                pass

        # JSON Lines 형식 확인 (각 줄이 JSON 객체)
        lines = text_sample.split("\n")[:5]  # 첫 5줄만 확인
        json_line_count = 0
        non_empty_lines = [line for line in lines if line.strip()]

        for line in lines:
            line = line.strip()
            if line and line.startswith("{") and line.endswith("}"):
                try:
                    json.loads(line)
                    json_line_count += 1
                except json.JSONDecodeError:
                    pass

        # 50% 이상이 JSON 라인이면 JSON Lines 형식
        if non_empty_lines and json_line_count >= len(non_empty_lines) * 0.5:
            return True

        return False

    @staticmethod
    def _is_csv_format(text_sample: str) -> bool:
        """CSV 형식인지 확인"""
        import csv
        from io import StringIO

        # 여러 구분자로 시도
        delimiters = [",", "\t", ";", "|"]

        for delimiter in delimiters:
            try:
                # CSV 파서로 읽기 시도
                sample_io = StringIO(text_sample)
                csv_reader = csv.reader(sample_io, delimiter=delimiter)

                rows = []
                for i, row in enumerate(csv_reader):
                    if i >= 5:  # 최대 5줄만 확인
                        break
                    rows.append(row)

                if not rows:
                    continue

                # CSV 특성 확인
                # 1. 최소 1줄 이상이 있어야 함
                if len(rows) < 1:
                    continue

                # 2. 각 행의 컬럼 수가 비슷해야 함 (더 유연하게)
                column_counts = [len(row) for row in rows if row]  # 빈 행 제외
                if not column_counts:
                    continue

                # 컬럼 수가 1개 이상이고, 대부분 비슷해야 함
                avg_columns = sum(column_counts) / len(column_counts)
                if avg_columns < 1:
                    continue

                # 3. 최소 2개 이상의 컬럼이 있어야 함
                if max(column_counts) < 2:
                    continue

                # 모든 조건을 만족하면 CSV 형식
                return True

            except Exception:
                continue

        # 모든 구분자로 시도했지만 실패
        return False

    @staticmethod
    def get_supported_formats() -> list:
        """지원되는 파일 형식 목록 반환"""
        return HTTP_FILE_CONFIG["supported_formats"].copy()

    @staticmethod
    def is_supported_format(file_format: str) -> bool:
        """파일 형식이 지원되는지 확인"""
        return file_format in HTTP_FILE_CONFIG["supported_formats"]
