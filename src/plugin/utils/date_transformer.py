"""
날짜 변환 유틸리티
FieldMapper 리팩토링의 일부
"""

import logging
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger("spaceone")


class DateTransformer:
    """날짜 변환 클래스"""

    def format_date(self, value: Any, format_str: str = "%Y-%m-%d") -> str:
        """날짜 형식 변환"""
        if not value:
            return ""

        try:
            # 문자열인 경우 파싱 시도
            if isinstance(value, str):
                # 이미 올바른 형식인지 확인
                if self._is_valid_date_format(value, format_str):
                    return value

                # 다양한 날짜 형식 시도
                date_formats = [
                    "%Y-%m-%d",
                    "%Y/%m/%d",
                    "%d-%m-%Y",
                    "%d/%m/%Y",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                ]

                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(value, fmt)
                        return parsed_date.strftime(format_str)
                    except ValueError:
                        continue

                # 파싱 실패 시 원본 반환
                return value

            # datetime 객체인 경우
            elif isinstance(value, datetime):
                return value.strftime(format_str)

            # 기타 타입인 경우 문자열로 변환 후 재시도
            else:
                return self.format_date(str(value), format_str)

        except Exception as e:
            _LOGGER.warning(
                f"[DateTransformer] Date formatting failed: {value}, error: {e}"
            )
            return str(value) if value else ""

    def _is_valid_date_format(self, date_str: str, format_str: str) -> bool:
        """날짜 문자열이 지정된 형식에 맞는지 확인"""
        try:
            datetime.strptime(date_str, format_str)
            return True
        except ValueError:
            return False

    def to_iso_format(self, value: Any) -> str:
        """날짜를 ISO 형식(YYYY-MM-DD)으로 변환"""
        return self.format_date(value, "%Y-%m-%d")

    def to_timestamp(self, value: Any) -> str:
        """날짜를 타임스탬프 형식으로 변환"""
        return self.format_date(value, "%Y-%m-%d %H:%M:%S")
