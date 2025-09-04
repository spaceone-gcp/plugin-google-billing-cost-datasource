"""
숫자 변환 유틸리티
FieldMapper 리팩토링의 일부
"""

import logging
from decimal import Decimal
from typing import Any

_LOGGER = logging.getLogger("spaceone")


class NumericTransformer:
    """숫자 변환 클래스"""

    def to_decimal(self, value: Any) -> Decimal:
        """값을 Decimal 타입으로 변환"""
        if value is None:
            return Decimal("0")

        try:
            if isinstance(value, Decimal):
                return value
            elif isinstance(value, (int, float)):
                return Decimal(str(value))
            elif isinstance(value, str):
                # 빈 문자열이나 숫자가 아닌 문자열 처리
                cleaned_value = value.strip()
                if not cleaned_value or cleaned_value.lower() in [
                    "null",
                    "none",
                    "n/a",
                ]:
                    return Decimal("0")
                return Decimal(cleaned_value)
            else:
                return Decimal("0")

        except Exception as e:
            _LOGGER.warning(
                f"[NumericTransformer] Failed to convert to Decimal: {value}, error: {e}"
            )
            return Decimal("0")

    def to_int(self, value: Any) -> int:
        """값을 정수로 변환"""
        try:
            decimal_value = self.to_decimal(value)
            return int(decimal_value)
        except Exception as e:
            _LOGGER.warning(
                f"[NumericTransformer] Failed to convert to int: {value}, error: {e}"
            )
            return 0

    def to_float(self, value: Any) -> float:
        """값을 실수로 변환"""
        try:
            decimal_value = self.to_decimal(value)
            return float(decimal_value)
        except Exception as e:
            _LOGGER.warning(
                f"[NumericTransformer] Failed to convert to float: {value}, error: {e}"
            )
            return 0.0
