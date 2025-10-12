"""
변환기 팩토리
FieldMapper 리팩토링의 일부
"""

from typing import Any, Optional

from .date_transformer import DateTransformer
from .json_transformer import JsonTransformer
from .numeric_transformer import NumericTransformer
from .string_transformer import StringTransformer


class TransformFactory:
    """변환기 팩토리 클래스"""

    def __init__(self):
        """팩토리 초기화"""
        self._transformers = {
            "string": StringTransformer(),
            "json": JsonTransformer(),
            "numeric": NumericTransformer(),
            "date": DateTransformer(),
        }

    def get_transformer(self, transform_type: str) -> Any | None:
        """변환기 타입에 따라 적절한 변환기 반환"""
        return self._transformers.get(transform_type)

    def apply_transform(self, value: Any, transform: str) -> Any:
        """통합 변환 적용 메서드"""
        if not transform or value is None:
            return value

        try:
            # 문자열 변환
            if transform == "upper":
                return self._transformers["string"].upper(value)
            elif transform == "lower":
                return self._transformers["string"].lower(value)
            elif transform == "strip":
                return self._transformers["string"].strip(value)
            elif transform == "title":
                return self._transformers["string"].title(value)

            # 숫자 변환
            elif transform == "decimal":
                return self._transformers["numeric"].to_decimal(value)
            elif transform == "int":
                return self._transformers["numeric"].to_int(value)
            elif transform == "float":
                return self._transformers["numeric"].to_float(value)

            # 날짜 변환
            elif transform == "date_format":
                return self._transformers["date"].format_date(value)
            elif transform == "iso_date":
                return self._transformers["date"].to_iso_format(value)
            elif transform == "timestamp":
                return self._transformers["date"].to_timestamp(value)

            # JSON 변환
            elif transform == "json_parse":
                return self._transformers["json"].parse(value)
            elif transform == "json_stringify":
                return self._transformers["json"].stringify(value)

            else:
                # 알 수 없는 변환은 원본 값 반환
                return value

        except Exception:
            # 변환 실패 시 원본 값 반환
            return value
