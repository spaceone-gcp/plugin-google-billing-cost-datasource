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


def calculate_partition_date_range(start_date: str) -> tuple[str, str]:
    """PARTITIONDATE 범위 계산 (공통 유틸리티 함수)

    시작일: 시작월의 첫째 날 (예: 2025-09-01)
    종료일: 현재월의 마지막 날 (예: 2025-10-31)

    Args:
        start_date: YYYY-MM 형식의 시작 날짜

    Returns:
        tuple[str, str]: (partition_start_date, partition_end_date) YYYY-MM-DD 형식
    """
    try:
        import calendar

        # 시작일 파싱 및 검증
        if not start_date or len(start_date) != 7:  # YYYY-MM 형식 검증
            current_date = datetime.now()
            start_year, start_month = current_date.year, current_date.month
            _LOGGER.warning(
                f"[PARTITIONDATE] Invalid start_date format: {start_date}, using current month: {current_date.strftime('%Y-%m')}"
            )
        else:
            start_year, start_month = map(int, start_date.split("-"))

        # 현재 날짜
        current_date = datetime.now()
        current_year, current_month = current_date.year, current_date.month

        # 시작일: 시작월의 첫째 날
        partition_start_str = f"{start_year}-{start_month:02d}-01"

        # 종료일: 현재월의 마지막 날
        last_day_of_current_month = calendar.monthrange(current_year, current_month)[1]
        partition_end_str = (
            f"{current_year}-{current_month:02d}-{last_day_of_current_month:02d}"
        )

        # PARTITIONDATE 계산 완료 (로그 간소화)

        return partition_start_str, partition_end_str

    except Exception as e:
        _LOGGER.error(f"[PARTITIONDATE] 날짜 계산 실패: {e}")
        # 실패 시 안전한 기본값 반환
        current_date = datetime.now()
        current_year, current_month = current_date.year, current_date.month
        import calendar

        last_day = calendar.monthrange(current_year, current_month)[1]

        # 기본값: 현재월의 첫째 날 ~ 마지막 날
        start_safe = f"{current_year}-{current_month:02d}-01"
        end_safe = f"{current_year}-{current_month:02d}-{last_day:02d}"

        _LOGGER.warning(f"[PARTITIONDATE] 기본값 사용: {start_safe} ~ {end_safe}")
        return start_safe, end_safe
