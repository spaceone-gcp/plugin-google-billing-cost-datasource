import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from spaceone.core.error import ERROR_INVALID_ARGUMENT

_LOGGER = logging.getLogger("spaceone")


class FieldMapper:
    """SpaceONE 비용 데이터 형식으로 필드 매핑을 수행하는 클래스"""

    def __init__(self, mapping_config: dict, provider: str = None):
        """
        Args:
            mapping_config: 필드 매핑 설정
            provider: 클라우드 프로바이더 (aws, gcp, azure 등)
        """
        self.mapping_config = mapping_config or {}
        self.provider = provider or "unknown"
        self.compiled_mappings = {}
        self._compile_mappings()

    def map_record(self, source_data: dict) -> dict:
        """단일 레코드를 SpaceONE 형식으로 변환

        Args:
            source_data: 원본 데이터 레코드

        Returns:
            SpaceONE 형식으로 변환된 데이터
        """
        try:
            mapped_data = {
                "cost": self._map_field("cost", source_data, 0.0),
                "usage_quantity": self._map_field("usage_quantity", source_data, 0.0),
                "usage_unit": self._map_field("usage_unit", source_data, ""),
                "provider": self.provider,
                "region_code": self._map_field("region_code", source_data, "global"),
                "product": self._map_field("product", source_data, ""),
                "usage_type": self._map_field("usage_type", source_data, ""),
                "resource": self._map_field("resource", source_data, ""),
                "billed_date": self._map_field("billed_date", source_data, ""),
                "tags": self._map_tags_field(source_data),
                "additional_info": self._map_field("additional_info", source_data, {}),
            }

            # 비용 데이터는 Decimal로 변환하여 정확성 보장
            mapped_data["cost"] = self._ensure_decimal(mapped_data["cost"])
            mapped_data["usage_quantity"] = self._ensure_decimal(
                mapped_data["usage_quantity"]
            )

            # JSON 직렬화를 위해 Decimal을 float로 변환
            mapped_data["cost"] = float(mapped_data["cost"])
            mapped_data["usage_quantity"] = float(mapped_data["usage_quantity"])

            return mapped_data

        except Exception as e:
            _LOGGER.error(f"[FieldMapper] Failed to map record: {e}")
            raise ERROR_INVALID_ARGUMENT(key=f"field_mapping_error: {str(e)}")

    def _map_tags_field(self, source_data: dict) -> dict:
        """tags 필드 특별 처리 - 문자열인 경우 JSON 파싱"""
        tags_value = self._map_field("tags", source_data, {})

        # 이미 딕셔너리인 경우 그대로 반환
        if isinstance(tags_value, dict):
            return tags_value

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(tags_value, str) and tags_value.strip():
            try:
                import json

                parsed_tags = json.loads(tags_value)
                # 파싱된 결과가 딕셔너리인지 확인
                if isinstance(parsed_tags, dict):
                    return parsed_tags
                else:
                    _LOGGER.warning(
                        f"[FieldMapper] Parsed tags is not a dict: {type(parsed_tags)}"
                    )
                    return {}
            except (json.JSONDecodeError, ValueError) as e:
                _LOGGER.warning(f"[FieldMapper] Failed to parse tags JSON: {e}")
                return {}

        # 기타 모든 경우 빈 딕셔너리 반환
        return {}

    def _compile_mappings(self):
        """매핑 설정을 컴파일하여 실행 가능한 형태로 변환"""
        default_mapping = self._get_default_mapping(self.provider)

        # 기본 매핑에 사용자 정의 매핑 오버라이드
        final_mapping = {**default_mapping, **self.mapping_config}

        for field_name, mapping_rule in final_mapping.items():
            self.compiled_mappings[field_name] = self._compile_single_mapping(
                mapping_rule
            )

    def _compile_single_mapping(self, mapping_rule) -> Callable:
        """단일 매핑 규칙을 컴파일"""
        if isinstance(mapping_rule, str):
            # 단순 필드 매핑: "source_field_name"
            return lambda data, rule=mapping_rule: data.get(rule, "")

        elif isinstance(mapping_rule, dict):
            if "field" in mapping_rule:
                # 필드 매핑 + 변환: {"field": "source_field", "transform": "function_name"}
                field_name = mapping_rule["field"]
                transform = mapping_rule.get("transform")
                default_value = mapping_rule.get("default", "")

                return (
                    lambda data,
                    field=field_name,
                    trans=transform,
                    default=default_value: self._apply_transform(
                        data.get(field, default), trans
                    )
                )

            elif "expression" in mapping_rule:
                # 표현식 매핑: {"expression": "field1 + field2"}
                expression = mapping_rule["expression"]
                return lambda data, expr=expression: self._evaluate_expression(
                    expr, data
                )

            elif "constant" in mapping_rule:
                # 상수 값: {"constant": "fixed_value"}
                constant_value = mapping_rule["constant"]
                return lambda data, const=constant_value: const

        elif callable(mapping_rule):
            # 함수 매핑
            return mapping_rule

        # 기본값 반환
        return lambda data: mapping_rule

    def _map_field(
        self, field_name: str, source_data: dict, default_value: Any = None
    ) -> Any:
        """필드 매핑 실행"""
        if field_name in self.compiled_mappings:
            try:
                result = self.compiled_mappings[field_name](source_data)
                # 결과가 빈 문자열이고 default_value가 있으면 default_value 사용
                if result == "" and default_value is not None and default_value != "":
                    return default_value
                return result
            except Exception as e:
                _LOGGER.warning(f"[FieldMapper] Failed to map field {field_name}: {e}")
                return default_value

        # 매핑 규칙이 없으면 동일한 필드명으로 시도
        return source_data.get(field_name, default_value)

    def _apply_transform(self, value: Any, transform: Optional[str]) -> Any:
        """값 변환 함수 적용"""
        if not transform or value is None:
            return value

        try:
            if transform == "upper":
                return str(value).upper()
            elif transform == "lower":
                return str(value).lower()
            elif transform == "decimal":
                return self._ensure_decimal(value)
            elif transform == "date_format":
                return self._format_date(value)
            elif transform == "json_parse":
                import json

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
                    if "=" in json_str:
                        # key=value 형태 처리
                        try:
                            pairs = {}
                            for pair in json_str.split(","):
                                if "=" in pair:
                                    k, v = pair.split("=", 1)
                                    pairs[k.strip()] = v.strip()
                            return pairs
                        except Exception:
                            return {}
                    return {}
            else:
                _LOGGER.warning(f"[FieldMapper] Unknown transform: {transform}")
                return value

        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Transform failed: {transform}, error: {e}")
            return value

    def _evaluate_expression(self, expression: str, data: dict) -> Any:
        """간단한 표현식 평가 (보안상 제한적으로 구현)"""
        # TODO: 보안을 고려한 표현식 평가 구현
        # 현재는 단순한 필드 참조만 지원
        if expression in data:
            return data[expression]
        return ""

    def _ensure_decimal(self, value: Any) -> Decimal:
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
                f"[FieldMapper] Failed to convert to Decimal: {value}, error: {e}"
            )
            return Decimal("0")

    def _format_date(self, value: Any) -> str:
        """날짜 형식 변환"""
        if not value:
            return ""

        try:
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d")
            elif isinstance(value, str):
                # 다양한 날짜 형식 파싱 시도
                date_formats = [
                    "%Y-%m-%d",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y/%m/%d",
                    "%m/%d/%Y",
                ]

                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(value, fmt)
                        return parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        continue

                # 파싱 실패 시 원본 반환
                return str(value)
            else:
                return str(value)

        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Date format failed: {value}, error: {e}")
            return str(value)

    def _get_default_mapping(self, provider: str) -> dict:
        """프로바이더별 기본 매핑 반환"""
        if provider == "google_cloud" or provider == "gcp":
            return {
                "cost": "cost",
                "usage_quantity": "usage_quantity",
                "usage_unit": "pricing_unit",
                "region_code": "region_code",
                "product": "service_description",
                "usage_type": "sku_description",
                "resource": "project_id",
                "currency": "currency",
                "billed_date": {"field": "billed_at", "transform": "date_format"},
                "tags": {"field": "labels", "transform": "json_parse"},
                "additional_info": {
                    "cost_at_list": "cost_at_list",
                    "cost_after_credits": "cost_after_credits",
                    "credits": {"field": "credits_detail", "transform": "json_parse"},
                    "resource_tags": {
                        "field": "resource_tags",
                        "transform": "json_parse",
                    },
                    "billing_account_id": "billing_account_id",
                    "invoice_month": "invoice_month",
                    "cost_type": "cost_type",
                    "project_name": "project_name",
                },
            }

        elif provider == "aws":
            return {
                "cost": "blended_cost",
                "usage_quantity": "usage_amount",
                "usage_unit": "usage_unit",
                "region_code": "availability_zone",
                "product": "product_name",
                "usage_type": "usage_type",
                "resource": "resource_id",
                "billed_date": {
                    "field": "usage_start_date",
                    "transform": "date_format",
                },
                "tags": "resource_tags",
                "additional_info": "line_item_description",
            }

        elif provider == "azure":
            return {
                "cost": "cost",
                "usage_quantity": "quantity",
                "usage_unit": "unit_of_measure",
                "region_code": "resource_location",
                "product": "service_name",
                "usage_type": "meter_name",
                "resource": "resource_guid",
                "billed_date": {"field": "date", "transform": "date_format"},
                "tags": "tags",
                "additional_info": "additional_info",
            }

        else:
            # 기본 매핑 (필드명이 동일한 경우)
            return {
                "cost": "cost",
                "usage_quantity": "usage_quantity",
                "usage_unit": "usage_unit",
                "region_code": "region_code",
                "product": "product",
                "usage_type": "usage_type",
                "resource": "resource",
                "billed_date": "billed_date",
                "tags": "tags",
                "additional_info": "additional_info",
            }
