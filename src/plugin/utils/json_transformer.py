"""
JSON 변환 유틸리티
FieldMapper 리팩토링의 일부
"""

import json
import logging
from typing import Any, Dict

_LOGGER = logging.getLogger("spaceone")


class JsonTransformer:
    """JSON 변환 클래스"""

    def parse(self, value: Any) -> Dict[str, Any]:
        """값을 JSON으로 파싱"""
        if not value:
            return {}

        # 문자열로 변환
        json_str = str(value).strip()

        # 빈 문자열이거나 None인 경우
        if not json_str or json_str.lower() in ("none", "null", ""):
            return {}

        # 이미 딕셔너리인 경우 그대로 반환
        if isinstance(value, dict):
            return value

        # JSON 파싱 시도
        try:
            parsed = json.loads(json_str)
            # 파싱된 결과가 딕셔너리가 아닌 경우 빈 딕셔너리 반환
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            # JSON 파싱 실패 시 문자열을 단일 키-값으로 처리 시도
            return self._parse_key_value_pairs(json_str)

    def _parse_key_value_pairs(self, text: str) -> Dict[str, Any]:
        """key=value 형태의 문자열을 딕셔너리로 파싱"""
        if "=" not in text:
            return {}

        try:
            pairs = {}
            for pair in text.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    pairs[k.strip()] = v.strip()
            return pairs
        except Exception as e:
            _LOGGER.warning(f"[JsonTransformer] Failed to parse key-value pairs: {e}")
            return {}

    def stringify(self, value: Any) -> str:
        """값을 JSON 문자열로 변환"""
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            _LOGGER.warning(f"[JsonTransformer] Failed to stringify: {e}")
            return str(value)
