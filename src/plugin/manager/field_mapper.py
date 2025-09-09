import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.error import ERROR_INVALID_ARGUMENT
except ImportError:
    # Mock for local development
    class MockError:
        def __call__(self, *args, **kwargs):
            return Exception("Mock SpaceONE Error")

    ERROR_INVALID_ARGUMENT = MockError()

_LOGGER = logging.getLogger("spaceone")


class FieldMapper:
    """SpaceONE 비용 데이터 형식으로 필드 매핑을 수행하는 클래스"""

    def __init__(
        self,
        mapping_config: dict,
        provider: str = None,
        select_cost: str = None,
        cost_metric: str = None,
        include_raw_data: bool = False,
        wrap_as_sample_data: bool = False,
    ):
        """
        Args:
            mapping_config: 필드 매핑 설정
            provider: 클라우드 프로바이더 (aws, gcp, azure 등)
            select_cost: 비용 선택 옵션 (cost, list_price, after_credits, net_cost)
            cost_metric: 비용 메트릭 옵션 (AmortizedCost 등)
            include_raw_data: data 필드에 원본 데이터 포함 여부
            wrap_as_sample_data: sample_data 형태로 래핑 여부
        """
        self.mapping_config = mapping_config or {}
        self.provider = provider or "unknown"
        self.select_cost = select_cost or "cost"
        self.cost_metric = cost_metric
        self.include_raw_data = include_raw_data
        self.wrap_as_sample_data = wrap_as_sample_data
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
            # 디버깅: 첫 번째 레코드에서만 로그 출력 (BigQuery 구조 확인)
            if not hasattr(self, "_debug_record_logged"):
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: BigQuery source data keys: {list(source_data.keys())}"
                )
                # BigQuery 중첩 필드들 확인
                for key in [
                    "service",
                    "sku",
                    "project",
                    "usage",
                    "invoice",
                    "location",
                    "price",
                ]:
                    if key in source_data:
                        _LOGGER.info(
                            f"[FieldMapper] DEBUG: {key} = {repr(source_data[key])}"
                        )
                self._debug_record_logged = True

            # select_cost 옵션에 따라 비용 필드 결정
            cost_value = self._get_cost_by_option(source_data)
            usage_quantity_value = self._map_field("usage_quantity", source_data, 0)

            # billed_date 필드는 반드시 YYYY-MM-DD 형식으로 변환 (필수 필드)
            billed_date_value = self._map_field("billed_date", source_data, "")

            # 디버깅: billed_date 매핑 과정 로깅
            if not hasattr(self, "_debug_billed_date_logged"):
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: billed_date mapping result: {repr(billed_date_value)}"
                )
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: usage_start_time in source: {repr(source_data.get('usage_start_time', 'NOT_FOUND'))}"
                )
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: export_time in source: {repr(source_data.get('export_time', 'NOT_FOUND'))}"
                )
                self._debug_billed_date_logged = True

            if not billed_date_value or billed_date_value == "":
                # billed_date가 없으면 현재 날짜를 기본값으로 사용
                from datetime import datetime

                billed_date_value = datetime.now().strftime("%Y-%m-%d")
                _LOGGER.warning(
                    f"[FieldMapper] billed_date missing, using current date: {billed_date_value}"
                )
            else:
                billed_date_value = self._format_date(billed_date_value)

            # additional_info 필드 특별 처리 - 기존 데이터와 매핑 데이터 병합
            mapped_additional_info = self._map_field("additional_info", source_data, {})
            existing_additional_info = source_data.get("additional_info", {})

            # 기존 additional_info와 매핑된 additional_info 병합
            # 매핑된 값이 우선순위를 가짐
            final_additional_info = {}
            if isinstance(existing_additional_info, dict):
                final_additional_info.update(existing_additional_info)
            if isinstance(mapped_additional_info, dict):
                final_additional_info.update(mapped_additional_info)

            # 중요 필드들 개별 매핑 및 디버깅
            product_value = self._map_field("product", source_data, "")
            usage_type_value = self._map_field("usage_type", source_data, "")
            resource_value = self._map_field("resource", source_data, "")

            # 디버깅: 매핑 결과 확인
            if not hasattr(self, "_debug_mapping_logged"):
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: product mapping result: {repr(product_value)}"
                )
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: usage_type mapping result: {repr(usage_type_value)}"
                )
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: resource mapping result: {repr(resource_value)}"
                )
                self._debug_mapping_logged = True

            mapped_data = {
                "cost": cost_value,
                "usage_quantity": usage_quantity_value,
                "usage_unit": self._map_field("usage_unit", source_data, ""),
                "provider": self.provider,
                "region_code": self._map_field("region_code", source_data, "global"),
                "product": product_value,
                "usage_type": usage_type_value,
                "resource": resource_value,
                "billed_date": billed_date_value,
                "tags": self._map_tags_field(source_data),
                "additional_info": final_additional_info,
            }

            # 🚨 CRITICAL: billed_date 필드 강제 보장
            if not mapped_data.get("billed_date") or mapped_data["billed_date"] == "":
                from datetime import datetime

                mapped_data["billed_date"] = datetime.now().strftime("%Y-%m-%d")
                _LOGGER.warning(
                    f"[FieldMapper] CRITICAL: Force-set billed_date to current date: {mapped_data['billed_date']}"
                )

            # 디버깅: 최종 매핑 결과 확인
            if not hasattr(self, "_debug_final_result_logged"):
                _LOGGER.info(
                    f"[FieldMapper] DEBUG: Final mapped_data billed_date: {repr(mapped_data.get('billed_date'))}"
                )
                self._debug_final_result_logged = True

            # 🚨 CRITICAL: data 필드 생성을 완전히 비활성화하여 검증 오류 방지
            # 원본 데이터 포함 옵션 처리 (현재 비활성화)
            # if self.include_raw_data:
            #     # 🚨 CRITICAL: source_data를 직렬화 가능한 형태로 변환 후 포함
            #     sanitized_source_data = self._sanitize_for_serialization({"temp": source_data})["temp"]
            #
            #     if self.wrap_as_sample_data:
            #         # sample_response_formatted.json 형태로 래핑
            #         mapped_data["data"] = {"sample_data": sanitized_source_data}
            #     else:
            #         # 원본 데이터를 data 필드에 직접 포함
            #         mapped_data["data"] = sanitized_source_data if isinstance(sanitized_source_data, dict) else {}

            # 연산이 필요한 경우에만 Decimal로 변환하여 정확성 보장 후 원본 타입으로 복원
            mapped_data["cost"] = self._process_numeric_field(mapped_data["cost"])
            mapped_data["usage_quantity"] = self._process_numeric_field(
                mapped_data["usage_quantity"]
            )

            # 🚨 CRITICAL: 모든 Pandas 객체를 JSON 직렬화 가능한 타입으로 변환
            mapped_data = self._sanitize_for_serialization(mapped_data)

            # 🚨 CRITICAL: SpaceONE 프레임워크 요구사항 준수
            # Google Cloud Billing에는 data 필드가 없지만, SpaceONE에서 필수로 요구함
            # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
            # SpaceONE 검증 오류 해결을 위해 빈 딕셔너리 제공
            mapped_data["data"] = {}
            _LOGGER.debug(
                "[FieldMapper] Set data field to empty dict for SpaceONE framework compatibility"
            )

            return mapped_data

        except Exception as e:
            _LOGGER.error(f"[FieldMapper] Failed to map record: {e}")
            raise ERROR_INVALID_ARGUMENT(key=f"field_mapper_error: {str(e)}") from e

    def _sanitize_for_serialization(self, data: dict) -> dict:
        """모든 데이터를 JSON 직렬화 가능한 타입으로 변환

        Args:
            data: 변환할 데이터 딕셔너리

        Returns:
            직렬화 가능한 타입으로 변환된 데이터
        """
        from datetime import date, datetime
        from decimal import Decimal

        import numpy as np
        import pandas as pd

        def convert_value(value):
            """개별 값을 직렬화 가능한 타입으로 변환"""
            # 🚨 CRITICAL: None 체크를 먼저 수행
            if value is None:
                return None
            # 🚨 CRITICAL: Pandas NA 체크는 안전하게 수행
            try:
                if pd.isna(value):
                    return None
            except (TypeError, ValueError):
                # pd.isna()가 실패하면 무시하고 계속 진행
                pass

            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                # Pandas Timestamp/Timedelta -> 문자열
                return str(value)
            elif isinstance(value, (np.integer, np.floating)):
                # Numpy 숫자 타입 -> Python 기본 타입
                return value.item()
            elif isinstance(value, np.ndarray):
                # Numpy 배열 -> 리스트
                return [convert_value(item) for item in value]
            elif isinstance(value, (datetime, date)):
                # Python datetime -> 문자열
                return value.isoformat()
            elif isinstance(value, Decimal):
                # Decimal -> float (이미 _process_numeric_field에서 처리되지만 안전장치)
                return float(value)
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 처리
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                # 리스트/튜플 재귀 처리
                return [convert_value(item) for item in value]
            else:
                return value

        # 전체 데이터 변환
        sanitized_data = {}
        for key, value in data.items():
            try:
                sanitized_value = convert_value(value)

                # 🚨 CRITICAL: SpaceONE 프레임워크 요구사항 준수
                # data 필드는 SpaceONE에서 필수로 요구하므로 빈 딕셔너리로 설정
                # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
                if key == "data":
                    # data 필드가 dict가 아니면 빈 딕셔너리로 강제 설정
                    if not isinstance(sanitized_value, dict):
                        sanitized_data[key] = {}
                        _LOGGER.debug(
                            f"[_sanitize_for_serialization] Force-set data field to empty dict (was {type(sanitized_value)})"
                        )
                    else:
                        sanitized_data[key] = sanitized_value
                    continue

                sanitized_data[key] = sanitized_value

            except Exception as e:
                _LOGGER.warning(
                    f"[FieldMapper] Failed to sanitize field {key}: {e}, keeping original value"
                )
                if key == "data":
                    # 🚨 CRITICAL: SpaceONE 프레임워크 요구사항 준수
                    # data 필드는 SpaceONE에서 필수로 요구하므로 빈 딕셔너리로 설정
                    sanitized_data[key] = {}  # 에러 발생 시에도 빈 딕셔너리로 설정
                    _LOGGER.debug(
                        "[FieldMapper] Force-set data field to empty dict due to sanitization error"
                    )
                    continue
                else:
                    sanitized_data[key] = str(value)  # 실패 시 문자열로 변환

        return sanitized_data

    def _get_cost_by_option(self, source_data: dict):
        """select_cost 및 cost_metric 옵션에 따라 적절한 비용 필드를 선택

        Args:
            source_data: 원본 데이터

        Returns:
            선택된 비용 값 (원본 타입 유지)
        """
        # cost_metric이 AmortizedCost인 경우 credits_amount 사용
        if self.cost_metric == "AmortizedCost":
            cost_value = self._map_field("credits_amount", source_data, 0)
            # _LOGGER.debug(f"[FieldMapper] Using AmortizedCost (credits_amount): {cost_value}")
            return cost_value

        # 기존 select_cost 로직
        if self.select_cost == "list_price":
            # 정가 관련 필드들을 시도
            cost_value = (
                self._map_field("cost_at_list", source_data, 0)
                or self._map_field("list_price", source_data, 0)
                or self._map_field("list_price_total", source_data, 0)
            )
            # _LOGGER.debug(f"[FieldMapper] Using list_price: {cost_value}")
            return cost_value
        elif self.select_cost == "after_credits":
            # 크레딧 적용 후 비용
            cost_value = self._map_field("cost_after_credits", source_data, 0)
            # _LOGGER.debug(f"[FieldMapper] Using after_credits: {cost_value}")
            return cost_value
        elif self.select_cost == "net_cost":
            # 순 비용 (기본 cost와 동일)
            cost_value = self._map_field("cost", source_data, 0)
            # _LOGGER.debug(f"[FieldMapper] Using net_cost: {cost_value}")
            return cost_value
        else:
            # 기본값: cost
            cost_value = self._map_field("cost", source_data, 0)
            # _LOGGER.debug(f"[FieldMapper] Using default cost: {cost_value}")
            return cost_value

    def _map_tags_field(self, source_data: dict) -> dict:
        """tags 필드 특별 처리 - Google Cloud labels 배열을 딕셔너리로 변환"""
        tags_value = self._map_field("tags", source_data, {})

        # 이미 딕셔너리인 경우 그대로 반환
        if isinstance(tags_value, dict):
            return tags_value

        # Google Cloud labels 배열 형태 처리 [{"key": "k1", "value": "v1"}, ...]
        if isinstance(tags_value, list):
            try:
                result_dict = {}
                for item in tags_value:
                    if isinstance(item, dict) and "key" in item and "value" in item:
                        result_dict[item["key"]] = item["value"]
                return result_dict
            except Exception as e:
                _LOGGER.warning(f"[FieldMapper] Failed to process labels array: {e}")
                return {}

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(tags_value, str) and tags_value.strip():
            # 이미 처리한 잘린 문자열인지 캐시 확인 (성능 최적화)
            if not hasattr(self, "_truncated_cache"):
                self._truncated_cache = set()

            tags_hash = hash(tags_value[:100])  # 처음 100자로 해시 생성
            if tags_hash in self._truncated_cache:
                return {}  # 이미 잘린 것으로 확인된 문자열

            # 디버깅을 위한 로깅 (처음 몇 개만)
            if not hasattr(self, "_debug_logged"):
                _LOGGER.debug(f"[FieldMapper] Raw tags_value: {repr(tags_value[:100])}")
                self._debug_logged = True

            try:
                import json

                parsed_tags = json.loads(tags_value)

                # 파싱된 결과가 딕셔너리인 경우
                if isinstance(parsed_tags, dict):
                    return parsed_tags

                # 파싱된 결과가 Google Cloud labels 배열인 경우
                elif isinstance(parsed_tags, list):
                    result_dict = {}
                    for item in parsed_tags:
                        if isinstance(item, dict) and "key" in item and "value" in item:
                            result_dict[item["key"]] = item["value"]
                    return result_dict
                else:
                    _LOGGER.warning(
                        f"[FieldMapper] Parsed tags is not a dict or labels array: {type(parsed_tags)}"
                    )
                    return {}
            except (json.JSONDecodeError, ValueError) as e:
                # 잘린 JSON 문자열인 경우 로깅 생략 (스팸 방지)
                truncated_patterns = [
                    "', 'value': '",  # 잘린 key-value 패턴
                    "'key':",  # 시작만 있는 패턴
                    '"key":',  # 시작만 있는 패턴
                    "'value': '",  # value만 있는 패턴
                    '"value": "',  # value만 있는 패턴
                ]

                is_truncated = (
                    len(tags_value) > 50
                    and not tags_value.strip().endswith(("}", "]", '"', "'"))
                ) or any(pattern in tags_value[:50] for pattern in truncated_patterns)

                if is_truncated:
                    # 잘린 문자열로 보이는 경우 - 캐시에 추가하고 빈 딕셔너리 반환
                    if hasattr(self, "_truncated_cache"):
                        self._truncated_cache.add(tags_hash)
                    return {}

                # 로깅 빈도 제한 - 같은 오류는 최대 5번만 로깅
                if not hasattr(self, "_json_error_count"):
                    self._json_error_count = {}
                error_key = str(e)[:50]  # 오류 메시지의 처음 50자로 키 생성
                if self._json_error_count.get(error_key, 0) < 5:
                    self._json_error_count[error_key] = (
                        self._json_error_count.get(error_key, 0) + 1
                    )
                    _LOGGER.debug(
                        f"[FieldMapper] JSON parsing failed for: {repr(tags_value[:50])}, error: {e}"
                    )

                # 일반적인 잘못된 JSON 형식들을 수정 시도
                cleaned_value = self._try_fix_malformed_json(tags_value)
                if cleaned_value != tags_value:
                    try:
                        parsed_tags = json.loads(cleaned_value)
                        if isinstance(parsed_tags, dict):
                            return parsed_tags
                        elif isinstance(parsed_tags, list):
                            result_dict = {}
                            for item in parsed_tags:
                                if (
                                    isinstance(item, dict)
                                    and "key" in item
                                    and "value" in item
                                ):
                                    result_dict[item["key"]] = item["value"]
                            return result_dict
                    except (json.JSONDecodeError, ValueError):
                        pass

                # key=value 형태 파싱 시도
                return self._parse_key_value_pairs(tags_value)

        # 기타 모든 경우 빈 딕셔너리 반환
        return {}

    def _try_fix_malformed_json(self, json_str: str) -> str:
        """잘못된 JSON 형식을 수정 시도"""
        try:
            # 일반적인 문제들 수정
            cleaned = json_str.strip()

            # 잘린 문자열인 경우 조기 반환 (수정 불가능)
            if len(cleaned) > 50 and not cleaned.endswith(("}", "]", '"')):
                return json_str

            # 1. 작은따옴표를 큰따옴표로 변경
            if "'" in cleaned and '"' not in cleaned:
                cleaned = cleaned.replace("'", '"')

            # 2. 키에 따옴표가 없는 경우 추가 (간단한 경우만)
            import re

            # {key: "value"} -> {"key": "value"}
            cleaned = re.sub(r"{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'{"\1":', cleaned)
            cleaned = re.sub(r",\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r', "\1":', cleaned)

            # 3. Python-style True/False를 JSON true/false로 변경
            cleaned = (
                cleaned.replace("True", "true")
                .replace("False", "false")
                .replace("None", "null")
            )

            return cleaned
        except Exception:
            return json_str

    def _parse_key_value_pairs(self, text: str) -> dict:
        """key=value 형태의 문자열을 딕셔너리로 파싱"""
        try:
            result = {}

            # 다양한 구분자 시도
            separators = [",", ";", "&", " "]

            for sep in separators:
                if sep in text:
                    pairs = text.split(sep)
                    for pair in pairs:
                        if "=" in pair:
                            key, value = pair.split("=", 1)
                            result[key.strip()] = value.strip()
                    if result:  # 성공적으로 파싱된 경우
                        return result

            # 단일 key=value 형태
            if "=" in text and len(text.split("=")) == 2:
                key, value = text.split("=", 1)
                return {key.strip(): value.strip()}

            return {}
        except Exception:
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
            # 단순 필드 매핑: "source_field_name" 또는 중첩 경로 "parent.child"
            return lambda data, rule=mapping_rule: self._get_nested_value(data, rule)

        elif isinstance(mapping_rule, dict):
            if "field" in mapping_rule:
                # 필드 매핑 + 변환: {"field": "source_field", "transform": "function_name"}
                field_name = mapping_rule["field"]
                transform = mapping_rule.get("transform")
                default_value = mapping_rule.get("default", "")
                fallback_field = mapping_rule.get("fallback")

                def field_mapper_with_fallback(
                    data,
                    field=field_name,
                    trans=transform,
                    default=default_value,
                    fallback=fallback_field,
                ):
                    # 주 필드 시도 (중첩 경로 지원)
                    value = self._get_nested_value(data, field)
                    # None이 아니고 빈 문자열이 아닌 경우 사용 (빈 딕셔너리 {} 도 유효한 값)
                    if value is not None and value != "":
                        return self._apply_transform(value, trans)

                    # fallback 필드 시도 (중첩 경로 지원)
                    if fallback:
                        fallback_value = self._get_nested_value(data, fallback)
                        if fallback_value is not None and fallback_value != "":
                            return self._apply_transform(fallback_value, trans)

                    # 기본값 사용
                    return self._apply_transform(default, trans) if default else ""

                return field_mapper_with_fallback

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

            else:
                # 딕셔너리 형태의 복합 매핑: {"field1": "source1", "field2": "source2"}
                # additional_info와 같은 복합 필드에 사용
                def map_dict_fields(data, rules=mapping_rule):
                    result = {}
                    # 디버깅: 첫 번째 레코드에서만 로그 출력
                    if not hasattr(self, "_debug_dict_mapping_logged"):
                        _LOGGER.info(
                            f"[FieldMapper] DEBUG: map_dict_fields called with data keys: {list(data.keys())}"
                        )
                        _LOGGER.info(f"[FieldMapper] DEBUG: mapping rules: {rules}")
                        self._debug_dict_mapping_logged = True

                    for target_field, source_config in rules.items():
                        if isinstance(source_config, str):
                            # 단순 필드 매핑 (중첩 경로 지원)
                            value = self._get_nested_value(data, source_config, "")
                            result[target_field] = value

                            # 디버깅: 중요한 필드들만 로그
                            if target_field in [
                                "project_id",
                                "service_id",
                                "sku_id",
                            ] and not hasattr(self, f"_debug_{target_field}_logged"):
                                _LOGGER.info(
                                    f"[FieldMapper] DEBUG: {target_field} = '{source_config}' -> '{value}'"
                                )
                                setattr(self, f"_debug_{target_field}_logged", True)

                        elif (
                            isinstance(source_config, dict) and "field" in source_config
                        ):
                            # 변환이 포함된 필드 매핑 (중첩 경로 지원)
                            field_name = source_config["field"]
                            transform = source_config.get("transform")
                            value = self._get_nested_value(data, field_name, "")
                            result[target_field] = self._apply_transform(
                                value, transform
                            )
                        else:
                            result[target_field] = ""
                    return result

                return map_dict_fields

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

                # billed_date 필드에 대한 특별 디버깅
                if field_name == "billed_date" and not hasattr(
                    self, "_debug_billed_date_mapping_logged"
                ):
                    _LOGGER.info(
                        f"[FieldMapper] DEBUG: billed_date compiled mapping result: {repr(result)}"
                    )
                    self._debug_billed_date_mapping_logged = True

                # 결과가 빈 문자열이고 default_value가 있으면 default_value 사용
                # 하지만 빈 딕셔너리나 빈 리스트는 유효한 값으로 간주
                if result == "" and default_value is not None and default_value != "":
                    return default_value
                return result
            except Exception as e:
                _LOGGER.warning(f"[FieldMapper] Failed to map field {field_name}: {e}")
                if field_name == "billed_date":
                    _LOGGER.error(
                        f"[FieldMapper] billed_date mapping failed with error: {e}",
                        exc_info=True,
                    )
                return default_value

        # 매핑 규칙이 없으면 동일한 필드명으로 시도 (중첩 경로 지원)
        if field_name == "billed_date" and not hasattr(
            self, "_debug_billed_date_fallback_logged"
        ):
            _LOGGER.warning(
                "[FieldMapper] DEBUG: billed_date not in compiled_mappings, using fallback"
            )
            _LOGGER.info(
                f"[FieldMapper] DEBUG: available compiled mappings: {list(self.compiled_mappings.keys())}"
            )
            self._debug_billed_date_fallback_logged = True

        return self._get_nested_value(source_data, field_name, default_value)

    def _get_nested_value(self, data: dict, path: str, default_value: Any = "") -> Any:
        """중첩 객체 경로를 처리하여 값을 추출

        Args:
            data: 원본 데이터 딕셔너리
            path: 필드 경로 (예: "project.id", "service.description")
            default_value: 기본값

        Returns:
            추출된 값 또는 기본값
        """
        if not path:
            return default_value

        try:
            # 점(.)으로 구분된 경로 처리
            if "." in path:
                keys = path.split(".")
                current_value = data

                for i, key in enumerate(keys):
                    if isinstance(current_value, dict):
                        current_value = current_value.get(key)
                        if current_value is None:
                            # 디버깅을 위한 상세 로그 (중요 필드만)
                            if path in ["project.id", "service.id", "sku.id"]:
                                _LOGGER.debug(
                                    f"[FieldMapper] Nested path '{path}' failed at key '{key}' (step {i + 1}/{len(keys)})"
                                )
                                _LOGGER.debug(
                                    f"[FieldMapper] Available keys at this level: {list(data.keys()) if i == 0 else 'N/A'}"
                                )
                            return default_value
                    elif isinstance(current_value, str):
                        # 문자열인 경우 JSON 파싱 시도
                        try:
                            import json

                            parsed_value = json.loads(current_value)
                            if isinstance(parsed_value, dict):
                                current_value = parsed_value.get(key)
                                if current_value is None:
                                    return default_value
                            else:
                                return default_value
                        except (json.JSONDecodeError, ValueError):
                            return default_value
                    else:
                        # 중요한 필드들에 대해서만 로그 출력
                        if path in ["project.id", "service.id", "sku.id"]:
                            _LOGGER.debug(
                                f"[FieldMapper] Nested path '{path}' expected dict but got {type(current_value)} at key '{key}'"
                            )
                        return default_value

                # 결과 검증 및 로깅
                result = current_value if current_value is not None else default_value

                # 중요한 필드들에 대해 결과 로깅 (처음 몇 번만)
                if path in [
                    "project.id",
                    "service.id",
                    "sku.id",
                    "service.description",
                    "sku.description",
                    "project.name",
                    "invoice.month",
                ]:
                    log_key = f"_nested_log_{path.replace('.', '_')}"
                    if not hasattr(self, log_key):
                        _LOGGER.info(
                            f"[FieldMapper] DEBUG: Nested path '{path}' resolved to: {repr(result)}"
                        )
                        setattr(self, log_key, True)

                return result
            else:
                # 단순 필드명
                return data.get(path, default_value)

        except Exception as e:
            _LOGGER.warning(
                f"[FieldMapper] Failed to get nested value for path '{path}': {e}"
            )
            return default_value

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

    def _process_numeric_field(self, value: Any) -> Any:
        """숫자 필드를 처리하여 연산 시에만 Decimal 사용하고 원본 타입으로 반환

        Args:
            value: 처리할 숫자 값

        Returns:
            원본 데이터 타입을 유지한 숫자 값
        """
        if value is None:
            return 0

        # 원본 타입 저장
        original_type = type(value)

        try:
            # 연산을 위해 Decimal로 변환
            decimal_value = self._ensure_decimal(value)

            # 원본 타입에 따라 적절한 타입으로 변환하여 반환
            if original_type is int:
                return int(decimal_value)
            elif original_type is float:
                return float(decimal_value)
            elif isinstance(value, str):
                # 문자열인 경우 숫자로 변환 가능하면 float, 아니면 0
                try:
                    return float(decimal_value)
                except (ValueError, TypeError, ArithmeticError):
                    return 0
            else:
                # 기본적으로 float 반환
                return float(decimal_value)

        except Exception as e:
            _LOGGER.warning(
                f"[FieldMapper] Failed to process numeric field: {value}, error: {e}"
            )
            return 0

    def _ensure_decimal(self, value: Any) -> Decimal:
        """값을 Decimal 타입으로 변환 (내부 연산용)"""
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
        # 디버깅: 날짜 변환 과정 로깅
        if not hasattr(self, "_debug_format_date_logged"):
            _LOGGER.info(
                f"[FieldMapper] DEBUG: _format_date called with value: {repr(value)} (type: {type(value)})"
            )
            self._debug_format_date_logged = True

        if not value or str(value).strip() == "" or str(value) == "today":
            # 빈 값이거나 "today"일 경우 현재 날짜를 기본값으로 사용
            result = datetime.now().strftime("%Y-%m-%d")
            _LOGGER.info(
                f"[FieldMapper] DEBUG: _format_date returning default date: {result}"
            )
            return result

        try:
            # pandas.Timestamp 객체 처리 (Parquet 파일에서 읽어온 날짜)
            if hasattr(value, "to_pydatetime"):
                # pandas.Timestamp를 Python datetime으로 변환 후 포맷팅
                return value.to_pydatetime().strftime("%Y-%m-%d")
            elif isinstance(value, datetime):
                return value.strftime("%Y-%m-%d")
            elif isinstance(value, str):
                # 이미 올바른 형식인지 확인
                if len(value) == 10 and value.count("-") == 2:
                    try:
                        # YYYY-MM-DD 형식 검증
                        datetime.strptime(value, "%Y-%m-%d")
                        return value
                    except ValueError:
                        pass

                # 다양한 날짜 형식 파싱 시도
                date_formats = [
                    "%Y-%m-%d",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 with Z suffix
                    "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO 8601 with microseconds
                    "%Y-%m-%d %H:%M:%S UTC",  # Google Cloud usage_start_time 형식
                    "%Y-%m-%d %H:%M:%S.%f UTC",  # Google Cloud export_time 형식
                    "%Y/%m/%d",
                    "%m/%d/%Y",
                    "%d/%m/%Y",
                ]

                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(value, fmt)
                        return parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        continue

                # 파싱 실패 시 현재 날짜를 기본값으로 사용
                _LOGGER.warning(
                    f"[FieldMapper] Failed to parse date: {value}, using current date"
                )
                return datetime.now().strftime("%Y-%m-%d")
            else:
                # 기타 타입은 현재 날짜를 기본값으로 사용
                _LOGGER.warning(
                    f"[FieldMapper] Unsupported date type: {type(value)}, value: {value}, using current date"
                )
                return datetime.now().strftime("%Y-%m-%d")

        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Date format failed: {value}, error: {e}")
            # 예외 발생 시에도 올바른 YYYY-MM-DD 형식으로 반환
            return datetime.now().strftime("%Y-%m-%d")

    def _get_default_mapping(self, provider: str) -> dict:
        """프로바이더별 기본 매핑 반환"""
        if provider == "google_cloud" or provider == "gcp":
            return {
                "cost": "cost",
                "usage_quantity": {
                    "field": "usage.amount_in_pricing_units",
                    "fallback": "usage_quantity",
                },
                "usage_unit": {
                    "field": "usage.pricing_unit",
                    "fallback": "pricing_unit",
                },
                "region_code": {
                    "field": "location.region",
                    "fallback": "region_code",
                    "default": "global",
                },
                "product": {
                    "field": "service.description",
                    "fallback": "service_description",
                },
                "usage_type": {
                    "field": "sku.description",
                    "fallback": "sku_description",
                },
                "resource": {
                    "field": "project.id",
                    "fallback": "project_id",
                },
                "currency": "currency",
                "billed_date": {
                    "field": "usage_start_time",
                    "transform": "date_format",
                    "fallback": "export_time",
                    "default": "today",
                },
                "tags": {"field": "labels", "transform": "json_parse"},
                "additional_info": {
                    # 💰 비용 관련 필드들 (BigQuery 스타일)
                    "Cost At List": "cost_at_list",
                    "Cost After Credits": "cost_after_credits",
                    "Cost At Effective Price Default": "cost_at_effective_price_default",
                    "Cost At List Consumption Model": "cost_at_list_consumption_model",
                    "Credits Amount": "credits_amount",  # AmortizedCost용
                    "Credits Detail": {"field": "credits", "transform": "json_parse"},
                    "Currency Conversion Rate": "currency_conversion_rate",
                    # 🏢 계정 및 청구 정보
                    "Billing Account ID": "billing_account_id",
                    "Invoice Month": {
                        "field": "invoice.month",
                        "fallback": "invoice_month",
                    },
                    "Invoice Publisher Type": {
                        "field": "invoice.publisher_type",
                        "fallback": "invoice_publisher_type",
                    },
                    "Cost Type": "cost_type",
                    "Transaction Type": "transaction_type",
                    "Seller Name": "seller_name",
                    # 🏗️ 프로젝트 정보 (BigQuery 중첩 구조)
                    "Project ID": {
                        "field": "project.id",
                        "fallback": "project_id",
                    },
                    "Project Name": {
                        "field": "project.name",
                        "fallback": "project_name",
                    },
                    "Project Number": {
                        "field": "project.number",
                        "fallback": "project_number",
                    },
                    "Project Ancestry Numbers": {
                        "field": "project.ancestry_numbers",
                        "fallback": "project_ancestry_numbers",
                    },
                    # 🔧 서비스 정보 (BigQuery 중첩 구조)
                    "Service ID": {
                        "field": "service.id",
                        "fallback": "service_id",
                    },
                    "Service Description": {
                        "field": "service.description",
                        "fallback": "service_description",
                    },
                    # 📦 SKU 정보 (BigQuery 중첩 구조)
                    "SKU ID": {
                        "field": "sku.id",
                        "fallback": "sku_id",
                    },
                    "SKU Description": {
                        "field": "sku.description",
                        "fallback": "sku_description",
                    },
                    # 🌍 위치 정보 (BigQuery 중첩 구조)
                    "Location": {
                        "field": "location.location",
                        "fallback": "location_location",
                    },
                    "Location Country": {
                        "field": "location.country",
                        "fallback": "location_country",
                    },
                    "Location Region": {
                        "field": "location.region",
                        "fallback": "location_region",
                    },
                    "Location Zone": {
                        "field": "location.zone",
                        "fallback": "location_zone",
                    },
                    # 📊 사용량 정보 (BigQuery 중첩 구조)
                    "Usage Start Time": "usage_start_time",
                    "Usage End Time": "usage_end_time",
                    "Usage Amount": {
                        "field": "usage.amount",
                        "fallback": "usage_amount",
                    },
                    "Usage Unit": {
                        "field": "usage.unit",
                        "fallback": "usage_unit",
                    },
                    "Usage Amount In Pricing Units": {
                        "field": "usage.amount_in_pricing_units",
                        "fallback": "usage_amount_in_pricing_units",
                    },
                    "Usage Pricing Unit": {
                        "field": "usage.pricing_unit",
                        "fallback": "usage_pricing_unit",
                    },
                    # 💲 가격 정보 (BigQuery price 중첩 구조)
                    "Price Effective Price": {
                        "field": "price.effective_price",
                        "fallback": "price_effective_price",
                    },
                    "Price Tier Start Amount": {
                        "field": "price.tier_start_amount",
                        "fallback": "price_tier_start_amount",
                    },
                    "Price Unit": {
                        "field": "price.unit",
                        "fallback": "price_unit",
                    },
                    "Price Pricing Unit Quantity": {
                        "field": "price.pricing_unit_quantity",
                        "fallback": "price_pricing_unit_quantity",
                    },
                    "Price List Price": {
                        "field": "price.list_price",
                        "fallback": "price_list_price",
                    },
                    "Price Effective Price Default": {
                        "field": "price.effective_price_default",
                        "fallback": "price_effective_price_default",
                    },
                    "Price List Price Consumption Model": {
                        "field": "price.list_price_consumption_model",
                        "fallback": "price_list_price_consumption_model",
                    },
                    # 🏷️ 라벨 및 태그 (BigQuery 배열 구조)
                    "System Labels": {
                        "field": "system_labels",
                        "transform": "json_parse",
                    },
                    "Resource Tags": {"field": "tags", "transform": "json_parse"},
                    # 📈 소비 모델 정보
                    "Consumption Model ID": {
                        "field": "consumption_model.id",
                        "fallback": "consumption_model_id",
                    },
                    "Consumption Model Description": {
                        "field": "consumption_model.description",
                        "fallback": "consumption_model_description",
                    },
                    # 🔍 메타데이터
                    "Export Time": "export_time",
                    "Adjustment Info": {
                        "field": "adjustment_info",
                        "transform": "json_parse",
                    },
                    # 🆕 리소스 식별 필드 (상세 사용량 데이터용)
                    "Resource Name": "resource_name",
                    "Resource Global Name": "resource_global_name",
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
