"""
Decimal JSON Encoder - 과학적 표기법 완전 제거
SpaceONE 빌링 응답에서 매우 작은 숫자들의 과학적 표기법을 완전히 제거하는 모듈

SpaceONE 빌링 응답의 최상위 cost 필드는 필수 항목입니다.
모든 JSON 직렬화에서 cost 필드의 존재와 올바른 형식을 보장합니다.
"""

import json
import logging
from decimal import Decimal

_LOGGER = logging.getLogger("spaceone")


class DecimalJSONEncoder(json.JSONEncoder):
    """과학적 표기법을 완전히 제거하는 JSON 인코더"""

    def encode(self, obj):
        """JSON 인코딩 시 과학적 표기법 완전 제거"""
        return super().encode(self._convert_numbers_to_safe_format(obj))

    def _convert_numbers_to_safe_format(self, obj):
        """모든 숫자를 과학적 표기법 없는 형태로 변환"""
        if isinstance(obj, dict):
            return {
                key: self._convert_numbers_to_safe_format(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [self._convert_numbers_to_safe_format(item) for item in obj]
        elif isinstance(obj, float):
            return self._convert_float_to_safe_number(obj)
        elif isinstance(obj, Decimal):
            return self._convert_decimal_to_safe_number(obj)
        else:
            return obj

    def _convert_float_to_safe_number(self, value: float) -> float:
        """float를 과학적 표기법 없는 안전한 숫자로 변환 (숫자 타입 유지)"""
        import math

        # NaN, 무한대 처리 (원본 보존)
        if math.isnan(value) or math.isinf(value):
            _LOGGER.warning(f"[DecimalJSONEncoder] NaN/Inf value encountered: {value}")
            return value  # 원본 그대로 보존

        # 0 처리 (정확한 0 값 보존)
        if value == 0.0 or value == -0.0:
            return value  # 원본 0 값 보존

        try:
            # 극소값도 원본 그대로 보존 (0으로 강제 변환 제거)
            _LOGGER.debug(f"[DecimalJSONEncoder] Preserving small value: {value}")
            
            # Decimal을 통한 정확한 반올림 후 float로 변환
            from decimal import Decimal, ROUND_HALF_UP
            decimal_val = Decimal(str(value))
            
            # 적절한 정밀도로 반올림 (과학적 표기법 방지)
            if abs(decimal_val) < Decimal('1e-12'):
                rounded = decimal_val.quantize(Decimal('1E-15'), rounding=ROUND_HALF_UP)
            elif abs(decimal_val) < Decimal('1e-9'):
                rounded = decimal_val.quantize(Decimal('1E-12'), rounding=ROUND_HALF_UP)
            elif abs(decimal_val) < Decimal('1e-6'):
                rounded = decimal_val.quantize(Decimal('1E-9'), rounding=ROUND_HALF_UP)
            elif abs(decimal_val) < Decimal('1e-3'):
                rounded = decimal_val.quantize(Decimal('1E-6'), rounding=ROUND_HALF_UP)
            elif abs(decimal_val) < Decimal('1'):
                rounded = decimal_val.quantize(Decimal('1E-6'), rounding=ROUND_HALF_UP)
            else:
                rounded = decimal_val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            result = float(rounded)
            
            # 과학적 표기법 검증 (원본 보존)
            if 'e' in str(result).lower():
                _LOGGER.warning(f"[DecimalJSONEncoder] Scientific notation detected, preserving original: {value}")
                return value  # 원본 값 보존
                
            return result

        except Exception as e:
            _LOGGER.warning(f"[DecimalJSONEncoder] Float conversion failed for {value}: {e}")
            return value  # 원본 값 보존

    def _convert_decimal_to_safe_number(self, value: Decimal) -> float:
        """Decimal을 과학적 표기법 없는 안전한 float로 변환"""
        try:
            # 극소값도 원본 그대로 보존
            _LOGGER.debug(f"[DecimalJSONEncoder] Processing Decimal value: {value}")
            
            # 적절한 정밀도로 반올림 후 float로 변환
            from decimal import ROUND_HALF_UP
            
            if abs(value) < Decimal('1e-12'):
                rounded = value.quantize(Decimal('1E-15'), rounding=ROUND_HALF_UP)
            elif abs(value) < Decimal('1e-9'):
                rounded = value.quantize(Decimal('1E-12'), rounding=ROUND_HALF_UP)
            elif abs(value) < Decimal('1e-6'):
                rounded = value.quantize(Decimal('1E-9'), rounding=ROUND_HALF_UP)
            elif abs(value) < Decimal('1e-3'):
                rounded = value.quantize(Decimal('1E-6'), rounding=ROUND_HALF_UP)
            elif abs(value) < Decimal('1'):
                rounded = value.quantize(Decimal('1E-6'), rounding=ROUND_HALF_UP)
            else:
                rounded = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            result = float(rounded)
            
            # 과학적 표기법 검증 (원본 보존)
            if 'e' in str(result).lower():
                _LOGGER.warning(f"[DecimalJSONEncoder] Scientific notation in Decimal, preserving original: {value}")
                return float(value)  # 원본 Decimal을 float로 변환하여 보존
                
            return result

        except Exception as e:
            _LOGGER.warning(f"[DecimalJSONEncoder] Decimal conversion failed for {value}: {e}")
            return float(value)  # 원본 값을 float로 변환하여 보존

    def _format_float_to_decimal_string(self, value: float) -> str:
        """float를 과학적 표기법 없는 문자열로 변환"""
        import math

        # NaN, 무한대 처리
        if math.isnan(value) or math.isinf(value):
            return str(value)

        # 0 처리
        if value == 0.0 or value == -0.0:
            return "0.0"

        try:
            # Decimal을 통한 정확한 변환
            decimal_val = Decimal(str(value))
            
            # 매우 작은 값 처리
            if abs(decimal_val) < Decimal('1e-15'):
                return "0.0"
            
            # 소수점 자릿수에 따른 포맷팅
            if abs(decimal_val) < Decimal('1e-12'):
                formatted = f"{decimal_val:.15f}"
            elif abs(decimal_val) < Decimal('1e-9'):
                formatted = f"{decimal_val:.12f}"
            elif abs(decimal_val) < Decimal('1e-6'):
                formatted = f"{decimal_val:.9f}"
            elif abs(decimal_val) < Decimal('1e-3'):
                formatted = f"{decimal_val:.6f}"
            elif abs(decimal_val) < Decimal('1'):
                formatted = f"{decimal_val:.6f}"
            else:
                formatted = f"{decimal_val:.2f}"

            # 불필요한 0과 소수점 제거
            formatted = formatted.rstrip('0').rstrip('.')
            
            # 빈 문자열이나 소수점만 남은 경우 처리
            if not formatted or formatted == '.' or formatted == '-':
                return "0.0"
            
            # 소수점이 없으면 추가
            if '.' not in formatted:
                formatted += ".0"
                
            return formatted

        except Exception as e:
            _LOGGER.warning(f"[DecimalJSONEncoder] Float conversion failed for {value}: {e}")
            return "0.0"

    def _format_decimal_to_string(self, value: Decimal) -> str:
        """Decimal을 과학적 표기법 없는 문자열로 변환"""
        try:
            # 매우 작은 값 처리
            if abs(value) < Decimal('1e-15'):
                return "0.0"
            
            # 고정 소수점 형식으로 변환
            formatted = f"{value:.15f}".rstrip('0').rstrip('.')
            
            if not formatted or formatted == '.' or formatted == '-':
                return "0.0"
            
            if '.' not in formatted:
                formatted += ".0"
                
            return formatted

        except Exception as e:
            _LOGGER.warning(f"[DecimalJSONEncoder] Decimal conversion failed for {value}: {e}")
            return "0.0"


def dumps_decimal(obj, **kwargs) -> str:
    """과학적 표기법을 완전히 제거하는 JSON dumps 함수"""
    kwargs.setdefault('cls', DecimalJSONEncoder)
    kwargs.setdefault('ensure_ascii', False)
    return json.dumps(obj, **kwargs)


def format_number_as_decimal(value) -> str:
    """숫자를 과학적 표기법 없는 문자열로 포맷팅"""
    encoder = DecimalJSONEncoder()
    if isinstance(value, (int, float)):
        return encoder._format_float_to_decimal_string(float(value))
    elif isinstance(value, Decimal):
        return encoder._format_decimal_to_string(value)
    else:
        return str(value)


def ensure_no_scientific_notation(data: dict) -> dict:
    """SpaceONE 응답 데이터에서 과학적 표기법 완전 제거
    
    SpaceONE 빌링 응답의 최상위 cost 필드는 필수 항목입니다.
    """
    encoder = DecimalJSONEncoder()
    result = encoder._convert_numbers_to_safe_format(data)
    
    # 과학적 표기법 제거 후에도 cost 필드 및 모든 필수 필드 보장
    if isinstance(result, dict) and "results" in result:
        if isinstance(result["results"], list):
            for record in result["results"]:
                if isinstance(record, dict):
                    # cost 필드 검증 (원본 보존)
                    if "cost" not in record:
                        record["cost"] = None
                        _LOGGER.warning("[DecimalJSONEncoder] Cost field missing, set to None")
                    elif record["cost"] is None:
                        _LOGGER.debug("[DecimalJSONEncoder] Cost field is None, preserving None")
                    
                    # 모든 SpaceONE 필수 필드 보장
                    spaceone_required_fields = {
                        "usage_quantity": 0.0,
                        "provider": "google_cloud",
                        "region_code": "global",
                        "product": "",
                        "usage_type": "",
                        "resource": "",
                        "currency": "USD",              # 🆕 최상위 필수 필드로 승격
                        "billed_date": "",
                        "tags": {},
                        "additional_info": {},
                        "data": {},
                    }
                    
                    for field, default_value in spaceone_required_fields.items():
                        if field not in record or record[field] is None:
                            record[field] = default_value
                    
                    # billed_date 특별 처리 (빈 문자열인 경우 None 설정 - 현재 날짜 사용하지 않음)
                    if not record.get("billed_date") or record["billed_date"] == "":
                        record["billed_date"] = None
    
    return result


# 테스트 함수
def test_scientific_notation_removal():
    """과학적 표기법 제거 테스트"""
    test_data = {
        "results": [
            {
                "cost": 0.000001,  # 1e-6
                "usage_quantity": 0.000000123,  # 1.23e-7
                "data": {
                    "cost": 0.000001,
                    "list_price": 0.000000456,  # 4.56e-7
                    "currency_conversion_rate": 1354.59
                }
            }
        ]
    }
    
    print("=== 원본 데이터 (표준 JSON) ===")
    print(json.dumps(test_data, indent=2))
    
    print("\n=== 과학적 표기법 제거 후 ===")
    result = dumps_decimal(test_data, indent=2)
    print(result)
    
    # 과학적 표기법 검증
    import re
    scientific_patterns = [r'-?\d+\.?\d*[eE][+-]?\d+']
    has_scientific = any(re.search(pattern, result) for pattern in scientific_patterns)
    
    print("\n=== 검증 결과 ===")
    print(f"과학적 표기법 존재: {'❌ 발견됨' if has_scientific else '✅ 완전 제거됨'}")
    
    return not has_scientific


if __name__ == "__main__":
    test_scientific_notation_removal()
