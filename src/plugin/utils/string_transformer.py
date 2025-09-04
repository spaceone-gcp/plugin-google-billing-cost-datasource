"""
문자열 변환 유틸리티
FieldMapper 리팩토링의 일부
"""


class StringTransformer:
    """문자열 변환 클래스"""

    def upper(self, value: str) -> str:
        """문자열을 대문자로 변환"""
        return str(value).upper()

    def lower(self, value: str) -> str:
        """문자열을 소문자로 변환"""
        return str(value).lower()

    def strip(self, value: str) -> str:
        """문자열 양끝 공백 제거"""
        return str(value).strip()

    def title(self, value: str) -> str:
        """문자열을 제목 케이스로 변환"""
        return str(value).title()
