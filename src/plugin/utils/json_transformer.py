"""
JSON 변환 유틸리티
FieldMapper 리팩토링의 일부
"""

import json
import logging
from typing import Any

_LOGGER = logging.getLogger("spaceone")


class JsonTransformer:
    """JSON 변환 클래스"""

    def parse(self, value: Any) -> dict[str, Any]:
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

    def _parse_key_value_pairs(self, text: str) -> dict[str, Any]:
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
        """값을 JSON 문자열로 변환 (소수점 표기법 전용)"""
        try:
            # JSON 직렬화 전 cost 필드 최종 보장
            if isinstance(value, dict) and "results" in value:
                value = self._ensure_cost_fields_in_response(value)

            # 소수점 표기법만 사용
            from .decimal_json_encoder import dumps_decimal

            return dumps_decimal(value)
        except (TypeError, ValueError) as e:
            _LOGGER.warning(f"[JsonTransformer] Failed to stringify: {e}")
            return str(value)

    def _ensure_cost_fields_in_response(self, response: dict) -> dict:
        """응답의 모든 레코드에 cost 필드가 있는지 최종 보장"""
        if not isinstance(response.get("results"), list):
            return response

        fixed_count = 0
        for record in response["results"]:
            if isinstance(record, dict):
                # 최상위 cost 필드 보장
                if "cost" not in record:
                    record["cost"] = 0.0
                    fixed_count += 1
                elif record["cost"] is None:
                    record["cost"] = 0.0
                    fixed_count += 1

                # data.cost 필드 보장
                if isinstance(record.get("data"), dict):
                    if "cost" not in record["data"]:
                        record["data"]["cost"] = record.get("cost", 0.0)

        if fixed_count > 0:
            print(
                f"[JsonTransformer] ULTIMATE: Fixed {fixed_count} records with missing cost fields"
            )

        return response
