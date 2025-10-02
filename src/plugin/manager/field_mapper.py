import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional

from spaceone.core.error import ERROR_INVALID_ARGUMENT

_LOGGER = logging.getLogger("spaceone")


class FieldMapper:
    """SpaceONE 비용 데이터 형식으로 필드 매핑을 수행하는 클래스

    CRITICAL: SpaceONE 빌링 응답의 최상위 cost 필드는 필수 항목입니다.

    모든 매핑 결과는 SpaceONE 표준 응답 구조를 준수해야 합니다:
    - cost: 최상위 필수 필드, 절대 누락 금지
    - usage_quantity, provider, region_code, product, usage_type, resource: 필수
    - billed_date, currency, tags, additional_info, data: 필수
    """

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

        # 일별 카운트 추적을 위한 딕셔너리
        self.daily_count_tracker = {}
        self.total_processed_count = 0

        _LOGGER.info(
            f"[FieldMapper] Initialized - Provider: {self.provider}, "
            f"SelectCost: {self.select_cost}, CostMetric: {self.cost_metric}"
        )

    def map_record(self, source_data: dict) -> dict:
        """단일 레코드를 SpaceONE 형식으로 변환

        Args:
            source_data: 원본 데이터 레코드

        Returns:
            SpaceONE 형식으로 변환된 데이터
        """
        try:
            # 기본 필드 매핑
            cost_value = self._get_cost_by_option(source_data)
            # cost 값 빈 값 처리: "", None, "null" -> 기본값 0
            if (
                cost_value is None
                or cost_value == ""
                or (isinstance(cost_value, str) and cost_value.lower() == "null")
            ):
                _LOGGER.debug(
                    "[FieldMapper] Cost value is None/empty/null, setting to default value 0"
                )
                cost_value = 0
            # NaN이나 inf 체크 (원본 보존)
            try:
                if isinstance(cost_value, float) and (
                    cost_value != cost_value
                ):  # NaN 체크
                    _LOGGER.warning(
                        "[FieldMapper] Cost value is NaN, preserving as NaN"
                    )
            except Exception as e:
                _LOGGER.warning(
                    f"[FieldMapper] Cost value check failed, preserving original: {cost_value}, error: {e}"
                )
            usage_quantity_value = self._safe_get_usage_quantity(source_data)
            usage_unit_value = self._safe_get_usage_unit(source_data)
            billed_date_value = self._process_billed_date(source_data)

            # additional_info 필드 병합 처리
            final_additional_info = self._merge_additional_info(source_data)

            # 주요 필드들 매핑
            mapped_fields = self._map_core_fields(source_data)

            # 응답 생성 직전 최종 체크 (이미 위에서 빈 값 처리됨)
            final_cost = cost_value

            # 매핑된 데이터 구성
            mapped_data = {
                "cost": final_cost,
                "usage_quantity": usage_quantity_value,
                "usage_unit": usage_unit_value,
                "provider": self.provider,
                "region_code": source_data.get("region_code", "global"),
                "product": mapped_fields["product"],
                "usage_type": mapped_fields["usage_type"],
                "resource": mapped_fields["resource"],
                "billed_date": billed_date_value,
                "tags": self._map_tags_field(source_data),
                "data": self._create_spaceone_billing_data(
                    source_data,
                    {"additional_info": final_additional_info},
                    self._get_list_price_from_source(source_data),
                ),
            }

            # additional_info는 메인 레코드 값들을 재사용하여 생성
            mapped_data["additional_info"] = (
                self._get_metadata_additional_info_from_mapped_data(
                    mapped_data, source_data
                )
            )

            # SpaceONE 응답 형식 보장 - Decimal을 float로 변환
            result = self._ensure_spaceone_response_types(mapped_data)

            # 필수 필드 보장 (usage_quantity가 누락되지 않도록)
            result = self._ensure_required_fields(result)

            # Project Ancestry Numbers 후처리 (배열 형식으로 변환)
            if "additional_info" in result and isinstance(
                result["additional_info"], dict
            ):
                if "Project Ancestry Numbers" in result["additional_info"]:
                    ancestry_value = result["additional_info"][
                        "Project Ancestry Numbers"
                    ]
                    if (
                        isinstance(ancestry_value, str)
                        and ancestry_value.startswith("/")
                        and ancestry_value.endswith("/")
                    ):
                        # "/219641957767/" -> ["219641957767"]
                        import json

                        parts = [
                            part.strip()
                            for part in ancestry_value.split("/")
                            if part.strip()
                        ]
                        result["additional_info"]["Project Ancestry Numbers"] = (
                            json.dumps(parts)
                        )
                        _LOGGER.error(
                            f"[DEBUG] Post-processed Project Ancestry Numbers: {result['additional_info']['Project Ancestry Numbers']}"
                        )

            if "cost" not in result:
                _LOGGER.warning(
                    f"[FieldMapper] Cost field missing from result! Keys: {list(result.keys())}"
                )
                result["cost"] = None  # None으로 보존
            else:
                # _LOGGER.debug(f"[FieldMapper] map_record result has cost: {result['cost']}")
                pass

            # 일별 카운트 추적 (map_record에서도 호출)
            self._track_daily_count(result.get("billed_date", "unknown"))

            # DEBUG: 최종 결과에서 cost 필드 확인
            # _LOGGER.debug(
            #     f"[FieldMapper] Final result cost field: {result.get('cost', 'MISSING')}"
            # )

            return result

        except Exception as e:
            _LOGGER.error(f"[FieldMapper] Failed to map record: {e}")
            _LOGGER.error(
                f"[FieldMapper] Source data keys: {list(source_data.keys()) if isinstance(source_data, dict) else 'Not a dict'}"
            )
            _LOGGER.error(f"[FieldMapper] Error type: {type(e).__name__}")
            import traceback

            _LOGGER.error(f"[FieldMapper] Full traceback: {traceback.format_exc()}")
            raise ERROR_INVALID_ARGUMENT(key=f"field_mapper_error: {str(e)}") from e

    def _ensure_spaceone_response_types(self, data: dict) -> dict:
        """SpaceONE 응답 형식에 맞게 데이터 타입을 보장 (Decimal -> float 변환)

        Args:
            data: 매핑된 데이터

        Returns:
            SpaceONE 호환 타입으로 변환된 데이터
        """

        def convert_value(value):
            """개별 값을 SpaceONE 호환 타입으로 변환"""
            if isinstance(value, Decimal):
                # Decimal -> float (적절한 정밀도로 반올림 후 변환)
                return self._decimal_to_clean_float(value)
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 처리
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                # 리스트/튜플 재귀 처리
                return [convert_value(item) for item in value]
            else:
                return value

        # 전체 데이터 변환
        converted_data = {}
        for key, value in data.items():
            converted_data[key] = convert_value(value)

        return converted_data

    def _ensure_required_fields(self, data: dict) -> dict:
        """SpaceONE 필수 필드가 누락되지 않도록 보장

        CRITICAL: SpaceONE 빌링 응답의 최상위 cost 필드는 필수 항목입니다.

        Args:
            data: 변환된 데이터

        Returns:
            필수 필드가 보장된 데이터
        """
        # SpaceONE 빌링 응답 표준 구조의 모든 필수 필드들
        # 문서 가이드라인에 따른 완전한 필수 필드 목록
        required_fields = {
            "cost": 0.0,
            "usage_quantity": 0.0,  # 필수: 사용량 (기본값 0.0)
            "usage_unit": "",  # 선택적: 사용량 단위
            "provider": self.provider,  # 필수: 프로바이더
            "region_code": "global",  # 필수: 리전 코드 (빈 문자열 허용, 기본값 "global")
            "product": "",  # 필수: 제품명
            "usage_type": "",  # 필수: 사용 유형
            "resource": "",  # 필수: 리소스 식별자
            "currency": "USD",  #  필수: 통화 (최상위 필드로 승격)
            "billed_date": None,  # 필수: 청구 날짜 (YYYY-MM-DD 형식, 데이터 없으면 None)
            "tags": {},  # 필수: 태그 (빈 딕셔너리 허용)
            "additional_info": {},  # 필수: 추가 정보 (빈 딕셔너리 허용)
            "data": {},  # 필수: SpaceONE 프레임워크 요구사항
        }

        # 누락된 필드를 기본값으로 채움
        for field, default_value in required_fields.items():
            if field not in data or data[field] is None:
                data[field] = default_value
                # _LOGGER.debug(
                #     f"[FieldMapper] Added missing required field '{field}' with default value: {default_value}"
                # )

        return data

    def _decimal_to_clean_float(self, decimal_value):
        """금액 데이터는 원본 그대로 보존 (반올림 및 변환 없음)"""
        # 금액 관련 데이터는 어떠한 변경도 없이 순수한 원본 데이터 사용
        return decimal_value

    def _log_debug_info_once(self, source_data: dict):
        """디버깅 정보를 첫 번째 레코드에서만 로깅"""
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

    def _process_billed_date(self, source_data: dict) -> str:
        """billed_date 필드 처리 - 실제 청구 관련 날짜만 사용"""
        # 1순위: 매핑된 billed_date 필드
        billed_date_value = self._map_field("billed_date", source_data, "")

        # 디버깅: billed_date 매핑 과정 로깅 (더 자세히)
        if not hasattr(self, "_debug_billed_date_count"):
            self._debug_billed_date_count = 0

        # 처음 20개 레코드에 대해서만 상세 로깅
        if self._debug_billed_date_count < 20:
            self._debug_billed_date_count += 1

        if billed_date_value and billed_date_value != "":
            # 유효한 날짜 값이 있으면 형식 변환
            return self._format_date(billed_date_value)

        # 2순위: usage_start_time 확인 (실제 사용 시작 날짜)
        usage_start_time = source_data.get("usage_start_time") or source_data.get(
            "Usage Start Time"
        )
        if usage_start_time:
            formatted_date = self._format_date(usage_start_time)
            if formatted_date:
                _LOGGER.debug(
                    f"[FieldMapper] Using usage_start_time for billed_date: {formatted_date}"
                )
                return formatted_date

        # 3순위: invoice_month를 날짜로 변환 (월말로 설정)
        invoice_month = source_data.get("invoice_month") or source_data.get(
            "Invoice Month"
        )
        if (
            invoice_month and isinstance(invoice_month, str) and len(invoice_month) == 6
        ):  # YYYYMM 형식
            try:
                year = invoice_month[:4]
                month = invoice_month[4:6]
                # 해당 월의 마지막 날로 설정
                import calendar

                last_day = calendar.monthrange(int(year), int(month))[1]
                formatted_date = f"{year}-{month}-{last_day:02d}"
                _LOGGER.debug(
                    f"[FieldMapper] Using invoice_month for billed_date: {formatted_date}"
                )
                return formatted_date
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    f"[FieldMapper] Failed to parse invoice_month {invoice_month}: {e}"
                )

        # 모든 날짜 필드가 없으면 None 반환 (현재 날짜 사용하지 않음)
        _LOGGER.warning(
            "[FieldMapper] No valid date fields found for billed_date, returning None"
        )
        return None

    def _get_nested_value(self, data: dict, path: str, default=""):
        """중첩된 딕셔너리에서 점 표기법으로 값 추출"""
        try:
            if not path:
                return default

            # 점으로 구분된 경로를 분할
            keys = path.split(".")
            current = data

            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default

            return current if current is not None else default
        except Exception:
            return default

    def _merge_additional_info(self, source_data: dict) -> dict:
        """additional_info 필드 병합 처리"""
        # 기본 additional_info 매핑 수행
        try:
            # 기존 additional_info 가져오기
            existing_additional_info = source_data.get("additional_info", {})
            if not isinstance(existing_additional_info, dict):
                existing_additional_info = {}

            # 매핑 규칙에서 additional_info 생성
            mapping_rules = self._get_default_mapping(self.provider).get(
                "additional_info", {}
            )
            mapped_additional_info = {}

            for key, rule in mapping_rules.items():
                try:
                    if isinstance(rule, str):
                        # 단순 문자열 매핑
                        value = self._get_nested_value(source_data, rule, "")
                        if value is not None and value != "":
                            mapped_additional_info[key] = str(value)
                    elif isinstance(rule, dict):
                        # 복잡한 매핑 규칙
                        field_path = rule.get("field", "")
                        fallback_path = rule.get("fallback", "")
                        transform = rule.get("transform", "")

                        value = ""
                        if field_path:
                            value = self._get_nested_value(source_data, field_path, "")
                        if not value and fallback_path:
                            value = self._get_nested_value(
                                source_data, fallback_path, ""
                            )

                        if value is not None and value != "":
                            # transform 적용
                            if transform:
                                transformed_value = self._apply_transform(
                                    value, transform
                                )
                                # transform 결과가 dict나 list인 경우 그대로 저장, 아니면 문자열로 변환
                                if isinstance(transformed_value, (dict, list)):
                                    mapped_additional_info[key] = transformed_value
                                else:
                                    mapped_additional_info[key] = str(transformed_value)
                            else:
                                mapped_additional_info[key] = str(value)
                except Exception as e:
                    _LOGGER.warning(
                        f"[FieldMapper] Failed to map additional_info field {key}: {e}"
                    )
                    continue

            # 기존과 매핑된 정보 병합
            final_additional_info = {}
            final_additional_info.update(existing_additional_info)
            final_additional_info.update(mapped_additional_info)

            # dict 타입 보장
            if not isinstance(final_additional_info, dict):
                _LOGGER.warning(
                    f"[FieldMapper] additional_info is not dict: {type(final_additional_info)}"
                )
                return {}

            # 모든 키를 Title Case로 변환
            title_case_additional_info = self._convert_keys_to_title_case(
                final_additional_info
            )

            return title_case_additional_info

        except Exception as e:
            _LOGGER.error(f"[FieldMapper] Error in _merge_additional_info: {e}")
            return {}

    def _map_additional_info_with_title_case(self, source_data: dict) -> dict:
        """additional_info 매핑 시 Title Case 키 유지"""
        additional_info_config = self.compiled_mappings.get("additional_info")
        if not additional_info_config:
            return {}

        result = {}

        # additional_info 매핑 규칙에서 직접 처리
        mapping_rules = self._get_default_mapping(self.provider).get(
            "additional_info", {}
        )

        for title_case_key, mapping_rule in mapping_rules.items():
            try:
                if isinstance(mapping_rule, str):
                    # 단순 문자열 매핑: "Project ID": "Project ID" 형태
                    if mapping_rule == title_case_key:
                        # Title Case 키 유지
                        value = self._get_nested_value(source_data, mapping_rule, "")
                        if value is not None and value != "":
                            result[title_case_key] = value
                    else:
                        # snake_case -> Title Case 변환
                        value = self._get_nested_value(source_data, mapping_rule, "")
                        if value is not None and value != "":
                            result[title_case_key] = value

                elif isinstance(mapping_rule, dict):
                    # 복잡한 매핑 규칙
                    output_key = mapping_rule.get("output_key", title_case_key)
                    field_path = mapping_rule.get("field")
                    fallback_path = mapping_rule.get("fallback")

                    value = ""
                    if field_path:
                        value = self._get_nested_value(source_data, field_path, "")
                    if not value and fallback_path:
                        value = self._get_nested_value(source_data, fallback_path, "")

                    if value is not None and value != "":
                        result[output_key] = value

            except Exception as e:
                _LOGGER.warning(
                    f"[FieldMapper] Failed to map additional_info field {title_case_key}: {e}"
                )
                continue

        return result

    def _map_core_fields(self, source_data: dict) -> dict:
        """핵심 필드들 매핑"""
        product_value = self._map_field("product", source_data, "")
        usage_type_value = self._map_field("usage_type", source_data, "")
        resource_value = self._map_field("resource", source_data, "")

        # 첫 번째 레코드만 매핑 결과 확인 (간소화)
        if not hasattr(self, "_debug_mapping_logged"):
            _LOGGER.debug(
                f"[FieldMapper] Mapping results - product: {product_value[:50] if product_value else 'None'}..., "
                f"usage_type: {usage_type_value[:50] if usage_type_value else 'None'}..., "
                f"resource: {resource_value[:50] if resource_value else 'None'}..."
            )
            self._debug_mapping_logged = True

        return {
            "product": product_value,
            "usage_type": usage_type_value,
            "resource": resource_value,
        }

    def _finalize_mapped_data(self, mapped_data: dict, source_data: dict) -> dict:
        """매핑된 데이터 최종 후처리"""
        # billed_date 필드 강제 보장
        if not mapped_data.get("billed_date") or mapped_data["billed_date"] == "":
            # billed_date가 없으면 None으로 설정 (현재 날짜 사용하지 않음)
            mapped_data["billed_date"] = None
            _LOGGER.warning(
                "[FieldMapper] CRITICAL: billed_date is missing, set to None"
            )

        # 디버깅: 최종 매핑 결과 확인 (첫 번째 레코드만)
        if not hasattr(self, "_debug_final_result_logged"):
            self._debug_final_result_logged = True

        # 연산이 필요한 경우에만 Decimal로 변환하여 정확성 보장 후 원본 타입으로 복원
        mapped_data["cost"] = self._process_numeric_field(mapped_data["cost"])
        mapped_data["usage_quantity"] = self._process_numeric_field(
            mapped_data["usage_quantity"]
        )

        # 모든 Pandas 객체를 JSON 직렬화 가능한 타입으로 변환
        mapped_data = self._sanitize_for_serialization(mapped_data)

        # cost 필드 검증 (0으로 강제 처리 제거)
        if "cost" not in mapped_data:
            _LOGGER.warning(
                "[FieldMapper] Cost field was missing in mapped_data, preserving as None"
            )
            mapped_data["cost"] = None
        elif mapped_data["cost"] is None:
            _LOGGER.info(
                "[FieldMapper] Cost field is None in mapped_data, preserving None value"
            )

        # data 필드는 이미 위에서 생성됨 (중복 제거)

        # 일별 카운트 추적
        self._track_daily_count(mapped_data.get("billed_date", "unknown"))

        # 궁극적 보장 시스템 적용
        # from ..utils.cost_field_guardian import guarantee_cost_fields  # 삭제된 모듈
        from ..utils.decimal_json_encoder import ensure_no_scientific_notation

        mapped_data = ensure_no_scientific_notation(mapped_data)

        return mapped_data

    def _get_list_price_from_source(self, source_data: dict):
        """다양한 소스에서 list_price(정가) 정보를 추출

        Google Cloud Billing 데이터에서 정가 정보는 다음 순서로 확인:
        1. cost_at_list (최상위 레벨) - 0이 아닌 값만
        2. price.list_price (중첩 구조) - cost_at_list가 0일 때 중요한 대체 소스
        3. price.list_price_consumption_model (소비 모델 기준 정가)
        4. cost (정가 정보가 없는 경우 실제 비용 사용)
        """
        # 1. 최상위 레벨의 cost_at_list 필드 확인 (0이 아닌 값만)
        cost_at_list = source_data.get("cost_at_list")
        if cost_at_list is not None and cost_at_list != "" and cost_at_list != 0:
            return cost_at_list

        # 2. price.list_price 중첩 구조 확인 (cost_at_list가 0일 때 중요한 대체 소스)
        price_info = source_data.get("price", {})
        if isinstance(price_info, dict):
            list_price = price_info.get("list_price")
            if list_price is not None and list_price != "" and list_price != 0:
                # 문자열인 경우 숫자로 변환 시도
                try:
                    return (
                        float(list_price) if isinstance(list_price, str) else list_price
                    )
                except (ValueError, TypeError):
                    pass

            # 3. 소비 모델 기준 정가 확인
            list_price_consumption = price_info.get("list_price_consumption_model")
            if (
                list_price_consumption is not None
                and list_price_consumption != ""
                and list_price_consumption != 0
            ):
                try:
                    return (
                        float(list_price_consumption)
                        if isinstance(list_price_consumption, str)
                        else list_price_consumption
                    )
                except (ValueError, TypeError):
                    pass

        # 4. FieldMapper를 통한 매핑 시도
        mapped_value = self._map_field("cost_at_list", source_data, None)
        if mapped_value is not None and mapped_value != "" and mapped_value != 0:
            return mapped_value

        # 5. 정가 정보가 없는 경우 실제 비용 사용 (fallback)
        cost_value = source_data.get("cost")
        if cost_value is not None and cost_value != "":
            return cost_value

        # 6. 모든 시도가 실패한 경우 빈 문자열 반환
        return ""

    def _create_spaceone_billing_data(
        self, source_data: dict, mapped_data: dict, list_price
    ) -> dict:
        """SpaceONE 빌링 표준에 맞는 data 필드 구조 생성 (4개 핵심 필드 포함)"""

        # 핵심 4개 필드 추출
        data_structure = {
            "List Price": self._convert_to_numeric(list_price),
            "Credits Total Amount": self._get_credits_total_amount(
                source_data, mapped_data
            ),
            "Usage Amount": self._get_usage_amount(source_data, mapped_data),
            "Usage Amount in Pricing Units": self._get_usage_amount_in_pricing_units(
                source_data, mapped_data
            ),
        }

        # null 값 제거 및 SpaceONE 응답 형식 보장
        cleaned_structure = {k: v for k, v in data_structure.items() if v is not None}
        return self._ensure_spaceone_response_types(cleaned_structure)

    def _get_credits_total_amount(self, source_data: dict, mapped_data: dict):
        """크레딧 총합 금액 추출"""
        # additional_info에서 Credits Total Amount 찾기
        additional_info = mapped_data.get("additional_info", {})
        credits_total = additional_info.get("Credits Total Amount")

        if credits_total is not None:
            return self._convert_to_numeric(credits_total)

        # credits 배열에서 계산
        credits_detail = additional_info.get("Credits Detail", [])
        if credits_detail and isinstance(credits_detail, list):
            total = sum(
                credit.get("amount", 0)
                for credit in credits_detail
                if isinstance(credit, dict)
            )
            return self._convert_to_numeric(total) if total != 0 else None

        return None

    def _get_usage_amount(self, source_data: dict, mapped_data: dict):
        """사용량 추출"""
        # additional_info에서 Usage Amount 찾기
        additional_info = mapped_data.get("additional_info", {})
        usage_amount = additional_info.get("Usage Amount")

        if usage_amount is not None:
            return self._convert_to_numeric(usage_amount)

        # 소스 데이터에서 직접 찾기
        if "usage" in source_data and isinstance(source_data["usage"], dict):
            amount = source_data["usage"].get("amount")
            if amount is not None:
                return self._convert_to_numeric(amount)

        return None

    def _get_usage_amount_in_pricing_units(self, source_data: dict, mapped_data: dict):
        """가격 단위 사용량 추출"""
        # additional_info에서 Usage Amount in Pricing Units 찾기
        additional_info = mapped_data.get("additional_info", {})
        usage_pricing_amount = additional_info.get("Usage Amount in Pricing Units")

        if usage_pricing_amount is not None:
            return self._convert_to_numeric(usage_pricing_amount)

        # 소스 데이터에서 직접 찾기
        if "usage" in source_data and isinstance(source_data["usage"], dict):
            amount_in_pricing_units = source_data["usage"].get(
                "amount_in_pricing_units"
            )
            if amount_in_pricing_units is not None:
                return self._convert_to_numeric(amount_in_pricing_units)

        return None

    def _get_metadata_additional_info(self, source_data: dict) -> dict:
        """메타데이터 필드만 포함하는 additional_info 생성 (33개 필드 완전 구현)

        Cost_Management_플러그인_호환성_적용_가이드.md의 33개 메타데이터 필드 구성에 따라
        빈 값도 <NA>로 처리하여 모든 필드를 포함
        """
        # 33개 필드 완전 구현 (문서 순서대로)
        metadata_fields = {
            # SpaceONE UI 기본 필수 항목 (6개)
            "Project": source_data.get("project_name", ""),
            "Provider": "Google Cloud",  # 고정값
            "Service Account": source_data.get("billing_account_id", ""),
            "Product": source_data.get("service_description", ""),
            "Region": source_data.get("region_code", ""),
            "Usage Type": source_data.get("sku_description", ""),
            # 조정 정보 (4개)
            "Adjustment Info Description": self._get_adjustment_info_field(
                source_data, "description"
            ),
            "Adjustment Info ID": self._get_adjustment_info_field(source_data, "id"),
            "Adjustment Info Mode": self._get_adjustment_info_field(
                source_data, "mode"
            ),
            "Adjustment Info Type": self._get_adjustment_info_field(
                source_data, "type"
            ),
            # 청구 관련 정보 (2개)
            "Billing Account ID": source_data.get("billing_account_id", ""),
            "Invoice Month": self._get_invoice_month(source_data),
            # 소비 모델 정보 (2개)
            "Consumption Model Description": self._get_consumption_model_field(
                source_data, "description"
            ),
            "Consumption Model ID": self._get_consumption_model_field(
                source_data, "id"
            ),
            # 기술적 메타데이터 (4개)
            "Cost Type": source_data.get("cost_type", ""),
            "Currency": source_data.get("currency", ""),
            "Transaction Type": source_data.get("transaction_type", ""),
            "Seller Name": source_data.get("seller_name", ""),
            # 지역 관련 정보 (4개)
            "Location Country": source_data.get("location_country", ""),
            "Location Location": source_data.get("location_location", ""),
            "Location Region": source_data.get("location_region", ""),
            "Location Zone": source_data.get("location_zone", ""),
            # 가격 정보 (2개)
            "Price Unit": self._get_price_field(source_data, "unit"),
            "Pricing Unit": self._get_pricing_unit_field(source_data),
            # 프로젝트 세부 정보 (3개)
            "Project ID": source_data.get("project_id", ""),
            "Project Name": source_data.get("project_name", ""),
            "Project Number": source_data.get("project_number", ""),
            # 발행자 정보 (1개)
            "Publisher Type": self._get_publisher_type(source_data),
            # 서비스 세부 정보 (4개)
            "SKU Description": source_data.get("sku_description", ""),
            "SKU ID": source_data.get("sku_id", ""),
            "Service Description": source_data.get("service_description", ""),
            "Service ID": source_data.get("service_id", ""),
            # 사용량 정보 (1개)
            "Usage Unit": source_data.get("usage_unit", ""),
        }

        # 필수 고정 항목 (6개)는 빈 값이어도 포함 (SpaceONE UI 기준)
        REQUIRED_FIELDS = {
            "Project",
            "Provider",
            "Service Account",
            "Product",
            "Region",
            "Usage Type",
        }

        # 모든 필드를 포함 (33개 필드 전체)
        cleaned_metadata = {}
        for k, v in metadata_fields.items():
            if k in REQUIRED_FIELDS:
                # 필수 필드는 빈 값이어도 포함 (기본값 설정)
                if v is None or v == "" or v == "<NA>":
                    cleaned_metadata[k] = "Unknown"
                else:
                    cleaned_metadata[k] = str(v).strip()
            else:
                # 모든 필드를 포함하되, 빈 값이나 null은 빈 문자열로 처리
                if v is None or str(v).strip() in ["", "<NA>", "None", "null"]:
                    cleaned_metadata[k] = ""
                else:
                    cleaned_metadata[k] = str(v).strip()

        return cleaned_metadata

    def _get_metadata_additional_info_from_mapped_data(
        self, mapped_data: dict, source_data: dict
    ) -> dict:
        """매핑된 데이터의 값들을 재사용하여 additional_info 생성 (FieldMapper용)"""
        # 메인 레코드에서 이미 올바르게 처리된 값들을 재사용
        metadata_fields = {
            # SpaceONE UI 기본 필수 항목 (6개) - 메인 레코드 값 재사용
            "Project": str(
                self._get_nested_value(source_data, "project.name", "")
                or self._get_nested_value(source_data, "project_name", "")
                or mapped_data.get("resource", "Unknown")
            ).strip(),  # 프로젝트 이름 우선, 없으면 resource(프로젝트 ID) 사용
            "Provider": "Google Cloud",
            "Service Account": str(
                self._get_nested_value(source_data, "billing_account_id", "")
            ).strip(),
            "Product": mapped_data.get("product", "Unknown"),  # 메인 레코드 값 재사용
            "Region": mapped_data.get("region_code", "global"),  # 메인 레코드 값 재사용
            "Usage Type": mapped_data.get(
                "usage_type", "Unknown"
            ),  # 메인 레코드 값 재사용
            # 조정 정보 (4개)
            "Adjustment Info Description": self._get_adjustment_info_field(
                source_data, "description"
            ),
            "Adjustment Info ID": self._get_adjustment_info_field(source_data, "id"),
            "Adjustment Info Mode": self._get_adjustment_info_field(
                source_data, "mode"
            ),
            "Adjustment Info Type": self._get_adjustment_info_field(
                source_data, "type"
            ),
            # 청구 관련 정보 (2개)
            "Billing Account ID": str(
                self._get_nested_value(source_data, "billing_account_id", "")
            ).strip(),
            "Invoice Month": self._get_invoice_month(source_data),
            # 소비 모델 정보 (2개)
            "Consumption Model Description": self._get_consumption_model_field(
                source_data, "description"
            ),
            "Consumption Model ID": self._get_consumption_model_field(
                source_data, "id"
            ),
            # 기술적 메타데이터 (4개)
            "Cost Type": str(
                self._get_nested_value(source_data, "cost_type", "regular")
            ).strip(),
            "Currency": str(
                self._get_nested_value(source_data, "currency", "USD")
            ).strip(),
            "Transaction Type": str(
                self._get_nested_value(source_data, "transaction_type", "")
            ).strip(),
            "Seller Name": str(
                self._get_nested_value(source_data, "seller_name", "")
            ).strip(),
            # 지역 관련 정보 (4개) - 중첩 구조 우선 매핑
            "Location Country": str(
                self._get_nested_value(source_data, "location.country", "")
                or self._get_nested_value(source_data, "location_country", "")
            ).strip(),
            "Location Location": str(
                self._get_nested_value(source_data, "location.location", "")
                or self._get_nested_value(source_data, "location_location", "")
            ).strip(),
            "Location Region": str(
                self._get_nested_value(source_data, "location.region", "")
                or self._get_nested_value(source_data, "location_region", "")
            ).strip(),
            "Location Zone": str(
                self._get_nested_value(source_data, "location.zone", "")
                or self._get_nested_value(source_data, "location_zone", "")
            ).strip(),
            # 가격 정보 (2개)
            "Price Unit": self._get_price_field(source_data, "unit"),
            "Pricing Unit": self._get_pricing_unit_field(source_data),
            # 프로젝트 세부 정보 (3개) - 중첩 구조 우선 매핑
            "Project ID": str(
                self._get_nested_value(source_data, "project.id", "")
                or self._get_nested_value(source_data, "project_id", "")
            ).strip(),
            "Project Name": str(
                self._get_nested_value(source_data, "project.name", "")
                or self._get_nested_value(source_data, "project_name", "")
            ).strip(),
            "Project Number": str(
                self._get_nested_value(source_data, "project.number", "")
                or self._get_nested_value(source_data, "project_number", "")
            ).strip(),
            # 발행자 정보 (1개)
            "Publisher Type": self._get_publisher_type(source_data),
            # 서비스 세부 정보 (4개) - 중첩 구조 우선 매핑
            "SKU Description": str(
                self._get_nested_value(source_data, "sku.description", "")
                or self._get_nested_value(source_data, "sku_description", "")
            ).strip(),
            "SKU ID": str(
                self._get_nested_value(source_data, "sku.id", "")
                or self._get_nested_value(source_data, "sku_id", "")
            ).strip(),
            "Service Description": str(
                self._get_nested_value(source_data, "service.description", "")
                or self._get_nested_value(source_data, "service_description", "")
            ).strip(),
            "Service ID": str(
                self._get_nested_value(source_data, "service.id", "")
                or self._get_nested_value(source_data, "service_id", "")
            ).strip(),
            # 사용량 정보 (1개) - 중첩 구조와 직접 필드 모두 확인
            "Usage Unit": str(
                self._get_usage_unit_field(source_data)
                or mapped_data.get("usage_unit", "")
            ).strip(),
        }

        # 필수 고정 항목 (6개)는 빈 값이어도 포함 (SpaceONE UI 기준)
        REQUIRED_FIELDS = {
            "Project",
            "Provider",
            "Service Account",
            "Product",
            "Region",
            "Usage Type",
        }

        cleaned_metadata = {}
        for k, v in metadata_fields.items():
            if k in REQUIRED_FIELDS:
                # 필수 필드는 항상 포함 (이미 기본값이 설정되어 있음)
                cleaned_metadata[k] = str(v).strip() if v else "Unknown"
            else:
                # 모든 필드를 포함하되, 빈 값이나 null은 빈 문자열로 처리
                if v is None or str(v).strip() in ["", "<NA>", "None", "null"]:
                    cleaned_metadata[k] = ""
                else:
                    cleaned_metadata[k] = str(v).strip()

        return cleaned_metadata

    def _get_invoice_month(self, source_data: dict) -> str:
        """청구서 월 추출"""
        invoice = source_data.get("invoice", {})
        if isinstance(invoice, dict):
            return invoice.get("month", "")
        return ""

    def _get_publisher_type(self, source_data: dict) -> str:
        """발행자 유형 추출"""
        invoice = source_data.get("invoice", {})
        if isinstance(invoice, dict):
            return invoice.get("publisher_type", "")
        return ""

    def _get_adjustment_info_field(self, source_data: dict, field: str) -> str:
        """조정 정보 필드 추출"""
        adjustment_info = source_data.get("adjustment_info", {})
        if isinstance(adjustment_info, dict):
            return adjustment_info.get(field, "")
        return ""

    def _get_consumption_model_field(self, source_data: dict, field: str) -> str:
        """소비 모델 필드 추출"""
        consumption_model = source_data.get("consumption_model", {})
        if isinstance(consumption_model, dict):
            return consumption_model.get(field, "")
        return ""

    def _get_price_field(self, source_data: dict, field: str) -> str:
        """가격 필드 추출"""
        price = source_data.get("price", {})
        if isinstance(price, dict):
            return price.get(field, "")
        return ""

    def _get_pricing_unit_field(self, source_data: dict) -> str:
        """가격 책정 단위 필드 추출"""
        # usage.pricing_unit에서 추출
        usage = source_data.get("usage", {})
        if isinstance(usage, dict):
            return usage.get("pricing_unit", "")
        return ""

    def _get_usage_unit_field(self, source_data: dict) -> str:
        """사용량 단위 필드 추출"""
        # usage.unit에서 추출
        usage = source_data.get("usage", {})
        if isinstance(usage, dict):
            return usage.get("unit", "")
        # 직접 필드에서도 확인
        return source_data.get("usage_unit", "")

    def _convert_to_numeric(self, value):
        """값을 적절한 숫자 타입으로 변환 (부동소수점 정밀도 개선 포함)"""
        if value is None or value == "":
            return 0.0

        try:
            from decimal import Decimal

            # 이미 숫자인 경우 Decimal을 통해 정밀도 개선
            if isinstance(value, (int, float)):
                if isinstance(value, int):
                    return float(value)  # int는 그대로
                else:
                    # float는 Decimal을 통해 정밀도 개선
                    decimal_value = Decimal(str(value))
                    return self._decimal_to_clean_float(decimal_value)

            # Decimal인 경우 정밀도 개선 적용
            if isinstance(value, Decimal):
                return self._decimal_to_clean_float(value)

            # 문자열인 경우 숫자로 변환
            if isinstance(value, str):
                cleaned_value = value.strip()
                if not cleaned_value:
                    return 0.0
                decimal_value = Decimal(cleaned_value)
                return self._decimal_to_clean_float(decimal_value)

            # 기타 타입은 float로 변환 시도
            decimal_value = Decimal(str(value))
            return self._decimal_to_clean_float(decimal_value)

        except (ValueError, TypeError, Exception):
            return 0.0

    def _add_billing_cost_info(self, data_structure: dict, source_data: dict):
        """빌링 비용 관련 정보 추가"""
        # 크레딧 적용 후 비용
        cost_after_credits = source_data.get("cost_after_credits")
        if cost_after_credits is not None and cost_after_credits != "":
            data_structure["cost_after_credits"] = self._convert_to_numeric(
                cost_after_credits
            )

        # 크레딧 정보
        credits = source_data.get("credits", [])
        if credits and isinstance(credits, list) and len(credits) > 0:
            total_credits = sum(
                float(credit.get("amount", 0))
                for credit in credits
                if isinstance(credit, dict)
            )
            if total_credits != 0:
                data_structure["total_credits"] = total_credits

        # 환율 정보
        currency_conversion_rate = source_data.get("currency_conversion_rate")
        if (
            currency_conversion_rate is not None
            and currency_conversion_rate != ""
            and currency_conversion_rate != 1
        ):
            data_structure["currency_conversion_rate"] = self._convert_to_numeric(
                currency_conversion_rate
            )

    def _add_usage_and_price_info(self, data_structure: dict, source_data: dict):
        """사용량 및 가격 정보 추가"""
        # 사용량 정보 (중첩 구조 처리)
        usage_info = source_data.get("usage", {})
        if isinstance(usage_info, dict):
            usage_amount = usage_info.get("amount")
            if usage_amount is not None and usage_amount != "":
                data_structure["usage_amount"] = self._convert_to_numeric(usage_amount)

            usage_unit = usage_info.get("unit")
            if usage_unit and usage_unit != "":
                data_structure["usage_unit"] = str(usage_unit)

        # 가격 정보 (중첩 구조 처리)
        price_info = source_data.get("price", {})
        if isinstance(price_info, dict):
            effective_price = price_info.get("effective_price")
            if (
                effective_price is not None
                and effective_price != ""
                and effective_price != 0
            ):
                data_structure["effective_price"] = self._convert_to_numeric(
                    effective_price
                )

    def _add_identifier_info(self, data_structure: dict, source_data: dict):
        """핵심 식별자 정보 추가"""
        # 프로젝트 정보
        project_info = source_data.get("project", {})
        if isinstance(project_info, dict):
            project_id = project_info.get("id")
            if project_id and project_id != "":
                data_structure["project_id"] = str(project_id)

            project_name = project_info.get("name")
            if project_name and project_name != "":
                data_structure["project_name"] = str(project_name)

            project_number = project_info.get("number")
            if project_number and project_number != "":
                data_structure["project_number"] = str(project_number)

        # 서비스 정보
        service_info = source_data.get("service", {})
        if isinstance(service_info, dict):
            service_id = service_info.get("id")
            if service_id and service_id != "":
                data_structure["service_id"] = str(service_id)

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
            return self._convert_single_value(value, pd, np, datetime, date, Decimal)

        # 전체 데이터 변환
        sanitized_data = {}
        for key, value in data.items():
            sanitized_data[key] = self._sanitize_single_field(key, value, convert_value)

        # cost 필드 검증 (원본 값 보존)
        if "cost" not in sanitized_data:
            sanitized_data["cost"] = None
            _LOGGER.warning(
                "[FieldMapper] Cost field was removed during sanitization, set to None"
            )
        elif sanitized_data["cost"] is None:
            _LOGGER.debug(
                "[FieldMapper] Cost field is None after sanitization, preserving None value"
            )

        return sanitized_data

    def _convert_single_value(self, value, pd, np, datetime, date, decimal_type):
        """개별 값을 직렬화 가능한 타입으로 변환"""
        # None 체크를 먼저 수행 (하지만 cost 필드는 예외)
        if value is None:
            return None

        # Pandas NA 체크는 안전하게 수행 (하지만 cost 필드는 예외)
        if self._is_pandas_na(value, pd):
            return None

        return self._convert_value_by_type(value, pd, np, datetime, date, decimal_type)

    def _is_pandas_na(self, value, pd) -> bool:
        """Pandas NA 값인지 안전하게 확인"""
        try:
            return pd.isna(value)
        except (TypeError, ValueError):
            # pd.isna()가 실패하면 False 반환
            return False

    def _convert_value_by_type(self, value, pd, np, datetime, date, decimal_type):
        """타입별 값 변환"""
        if isinstance(value, (pd.Timestamp, pd.Timedelta)):
            # Pandas Timestamp/Timedelta -> 문자열
            return str(value)
        elif isinstance(value, (np.integer, np.floating)):
            # Numpy 숫자 타입 -> Python 기본 타입
            return value.item()
        elif isinstance(value, np.ndarray):
            # Numpy 배열 -> 리스트
            return [
                self._convert_single_value(item, pd, np, datetime, date, decimal_type)
                for item in value
            ]
        elif isinstance(value, (datetime, date)):
            # Python datetime -> 문자열
            return value.isoformat()
        elif isinstance(value, decimal_type):
            # Decimal -> float (이미 _process_numeric_field에서 처리되지만 안전장치)
            return float(value)
        elif isinstance(value, dict):
            # 중첩 딕셔너리 재귀 처리
            return {
                k: self._convert_single_value(v, pd, np, datetime, date, decimal_type)
                for k, v in value.items()
            }
        elif isinstance(value, (list, tuple)):
            # 리스트/튜플 재귀 처리
            return [
                self._convert_single_value(item, pd, np, datetime, date, decimal_type)
                for item in value
            ]
        else:
            return value

    def _sanitize_single_field(self, key: str, value, convert_value_func):
        """단일 필드를 직렬화 가능한 타입으로 변환"""
        try:
            sanitized_value = convert_value_func(value)

            # SpaceONE 필수 필드 절대 보장
            if key == "cost":
                # cost 필드 원본 값 보존
                if sanitized_value is None:
                    _LOGGER.debug(
                        "[FieldMapper] Cost field is None, preserving None value"
                    )
                # 숫자 변환 시도 (실패해도 원본 보존)
                elif not isinstance(sanitized_value, (int, float)):
                    try:
                        sanitized_value = float(sanitized_value)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            f"[FieldMapper] Cost value conversion failed, preserving original: {value}"
                        )
                return sanitized_value

            # SpaceONE 프레임워크 요구사항 준수
            # data 필드는 SpaceONE에서 필수로 요구하므로 빈 딕셔너리로 설정
            if key == "data":
                return self._handle_data_field(sanitized_value)

            return sanitized_value

        except Exception as e:
            return self._handle_sanitization_error(key, value, e)

    def _handle_data_field(self, sanitized_value):
        """data 필드 특별 처리"""
        # data 필드가 dict가 아니면 빈 딕셔너리로 강제 설정
        if not isinstance(sanitized_value, dict):
            _LOGGER.debug(
                f"[_sanitize_for_serialization] Force-set data field to empty dict (was {type(sanitized_value)})"
            )
            return {}
        else:
            return sanitized_value

    def _handle_sanitization_error(self, key: str, value, error: Exception):
        """직렬화 오류 처리"""
        _LOGGER.warning(
            f"[FieldMapper] Failed to sanitize field {key}: {error}, keeping original value"
        )
        if key == "data":
            # SpaceONE 프레임워크 요구사항 준수
            # data 필드는 SpaceONE에서 필수로 요구하므로 빈 딕셔너리로 설정
            _LOGGER.debug(
                "[FieldMapper] Force-set data field to empty dict due to sanitization error"
            )
            return {}  # 에러 발생 시에도 빈 딕셔너리로 설정
        else:
            return str(value)  # 실패 시 문자열로 변환

    def _safe_get_usage_quantity(self, source_data: dict):
        """usage_quantity 필드를 안전하게 추출하고 기본값 처리

        GCP 빌링 데이터에서 Usage Amount 필드를 우선적으로 사용하고,
        fallback으로 기존 필드들을 확인합니다.

        Args:
            source_data: 원본 데이터

        Returns:
            usage_quantity 값 (없으면 0)
        """
        # 1단계: GCP additional_info에서 Usage Amount 추출 (최우선)
        additional_info = source_data.get("additional_info", {})
        # _LOGGER.debug(f"[FieldMapper] DEBUG: additional_info type: {type(additional_info)}, keys: {list(additional_info.keys()) if isinstance(additional_info, dict) else 'not dict'}")

        if isinstance(additional_info, dict):
            # GCP 빌링 데이터의 Usage Amount 필드 확인
            usage_amount = additional_info.get("Usage Amount")
            # _LOGGER.debug(f"[FieldMapper] DEBUG: Usage Amount value: {usage_amount}")
            # 빈 값 처리: "", None, "null" -> 기본값 0
            if (
                usage_amount is not None
                and usage_amount != ""
                and not (
                    isinstance(usage_amount, str) and usage_amount.lower() == "null"
                )
            ):
                try:
                    usage_value = float(usage_amount)
                    # _LOGGER.debug(f"[FieldMapper] Found Usage Amount in additional_info: {usage_value}")
                    return usage_value
                except (ValueError, TypeError):
                    # _LOGGER.warning(f"[FieldMapper] Invalid Usage Amount value: {usage_amount}")
                    pass

            # Usage Amount In Pricing Units도 확인
            usage_pricing_amount = additional_info.get("Usage Amount In Pricing Units")
            # 빈 값 처리: "", None, "null" -> 기본값 0
            if (
                usage_pricing_amount is not None
                and usage_pricing_amount != ""
                and not (
                    isinstance(usage_pricing_amount, str)
                    and usage_pricing_amount.lower() == "null"
                )
            ):
                try:
                    usage_value = float(usage_pricing_amount)
                    # _LOGGER.debug(f"[FieldMapper] Found Usage Amount In Pricing Units: {usage_value}")
                    return usage_value
                except (ValueError, TypeError):
                    # _LOGGER.warning(f"[FieldMapper] Invalid Usage Amount In Pricing Units: {usage_pricing_amount}")
                    pass
        # 2단계: 기존 usage_quantity 필드 확인 (fallback)
        usage_quantity = source_data.get("usage_quantity")
        # 빈 값 처리: "", None, "null" -> 기본값 0
        if (
            usage_quantity is not None
            and usage_quantity != ""
            and not (
                isinstance(usage_quantity, str)
                and usage_quantity.lower() in ("null", "nan")
            )
        ):
            try:
                usage_value = float(usage_quantity)
                # _LOGGER.debug(f"[FieldMapper] Found usage_quantity field: {usage_value}")
                return usage_value
            except (ValueError, TypeError):
                # _LOGGER.warning(f"[FieldMapper] Invalid usage_quantity value: {usage_quantity}")
                pass
        # 3단계: usage_amount 필드 확인 (추가 fallback)
        usage_amount_field = source_data.get("usage_amount")
        # 빈 값 처리: "", None, "null" -> 기본값 0
        if (
            usage_amount_field is not None
            and usage_amount_field != ""
            and not (
                isinstance(usage_amount_field, str)
                and usage_amount_field.lower() == "null"
            )
        ):
            try:
                usage_value = float(usage_amount_field)
                # _LOGGER.debug(f"[FieldMapper] Found usage_amount field: {usage_value}")
                return usage_value
            except (ValueError, TypeError):
                # _LOGGER.warning(f"[FieldMapper] Invalid usage_amount value: {usage_amount_field}")
                pass
        # 4단계: 최후의 수단 - 전체 source_data에서 Usage Amount 검색
        # _LOGGER.debug("[FieldMapper] DEBUG: Searching entire source_data for Usage Amount patterns")

        # 전체 데이터를 문자열로 변환해서 Usage Amount 찾기
        data_str = str(source_data)
        if "Usage Amount" in data_str:
            # _LOGGER.warning(f"[FieldMapper] FOUND Usage Amount in source_data but couldn't access it properly!")
            # _LOGGER.warning(f"[FieldMapper] source_data keys: {list(source_data.keys()) if isinstance(source_data, dict) else 'not dict'}")
            pass
            # 직접 검색 시도
            try:
                import re

                usage_pattern = r'"Usage Amount":\s*"([^"]+)"'
                match = re.search(usage_pattern, data_str)
                if match:
                    usage_value = float(match.group(1))
                    # _LOGGER.warning(f"[FieldMapper] EMERGENCY: Found Usage Amount via regex: {usage_value}")
                    return usage_value
            except Exception:
                # _LOGGER.error(f"[FieldMapper] Emergency search failed: {e}")
                pass
        # 5단계: 모든 방법이 실패한 경우 0 반환
        # _LOGGER.debug("[FieldMapper] No valid usage quantity found, returning 0")
        return 0

    def _safe_get_usage_unit(self, source_data: dict):
        """usage_unit 필드를 안전하게 추출하고 기본값 처리

        GCP 빌링 데이터에서 Usage Unit 필드를 우선적으로 사용하고,
        fallback으로 기존 필드들을 확인합니다.

        Args:
            source_data: 원본 데이터

        Returns:
            usage_unit 값 (없으면 빈 문자열)
        """
        # 1단계: GCP additional_info에서 Usage Unit 추출 (최우선)
        additional_info = source_data.get("additional_info", {})
        # _LOGGER.debug(f"[FieldMapper] DEBUG: usage_unit additional_info keys: {list(additional_info.keys()) if isinstance(additional_info, dict) else 'not dict'}")

        if isinstance(additional_info, dict):
            # GCP 빌링 데이터의 Usage Unit 필드 확인
            usage_unit = additional_info.get("Usage Unit")
            # _LOGGER.debug(f"[FieldMapper] DEBUG: Usage Unit value: {usage_unit}")
            if usage_unit is not None and usage_unit != "":
                _LOGGER.debug(
                    f"[FieldMapper] Found Usage Unit in additional_info: {usage_unit}"
                )
                return str(usage_unit)

            # Usage Pricing Unit도 확인
            usage_pricing_unit = additional_info.get("Usage Pricing Unit")
            if usage_pricing_unit is not None and usage_pricing_unit != "":
                # _LOGGER.debug(f"[FieldMapper] Found Usage Pricing Unit: {usage_pricing_unit}")
                return str(usage_pricing_unit)

        # 2단계: 기존 usage_unit 필드 확인 (fallback)
        usage_unit_field = source_data.get("usage_unit")
        if usage_unit_field is not None and usage_unit_field != "":
            # _LOGGER.debug(f"[FieldMapper] Found usage_unit field: {usage_unit_field}")
            return str(usage_unit_field)

        # 3단계: pricing_unit 필드 확인 (추가 fallback)
        pricing_unit = source_data.get("pricing_unit")
        if pricing_unit is not None and pricing_unit != "":
            # _LOGGER.debug(f"[FieldMapper] Found pricing_unit field: {pricing_unit}")
            return str(pricing_unit)

        # 4단계: 모든 방법이 실패한 경우 빈 문자열 반환
        # _LOGGER.debug("[FieldMapper] No valid usage unit found, returning empty string")
        return ""

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
            return cost_value

        # 기존 select_cost 로직
        if self.select_cost == "list_price":
            # 정가 관련 필드들을 시도
            cost_value = (
                self._map_field("cost_at_list", source_data, 0)
                or self._map_field("list_price", source_data, 0)
                or self._map_field("list_price_total", source_data, 0)
            )
            return cost_value
        elif self.select_cost == "after_credits":
            # 크레딧 적용 후 비용
            cost_value = self._map_field("cost_after_credits", source_data, 0)
            return cost_value
        elif self.select_cost == "net_cost":
            # 순 비용 (기본 cost와 동일)
            cost_value = self._map_field("cost", source_data, 0)
            return cost_value
        else:
            # 기본값: cost
            cost_value = self._map_field("cost", source_data, 0)
            return cost_value

    def _map_tags_field(self, source_data: dict) -> dict:
        """tags 필드 특별 처리 - Google Cloud labels 배열을 딕셔너리로 변환"""
        tags_value = self._map_field("tags", source_data, {})

        # 이미 딕셔너리인 경우 키를 snake_case로 변환하여 반환
        if isinstance(tags_value, dict):
            result_dict = {}
            for key, val in tags_value.items():
                snake_case_key = self._to_snake_case(key)
                result_dict[snake_case_key] = val
            return result_dict

        # Google Cloud labels 배열 형태 처리
        if isinstance(tags_value, list):
            return self._process_labels_array(tags_value)

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(tags_value, str) and tags_value.strip():
            return self._process_tags_string(tags_value)

        # 기타 모든 경우 빈 딕셔너리 반환
        return {}

    def _process_labels_array(self, labels_array: list) -> dict:
        """Google Cloud labels 배열을 딕셔너리로 변환 (null 값을 빈 문자열로 처리, 키를 snake_case로 변환)"""
        try:
            result_dict = {}
            for item in labels_array:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    # 키를 snake_case로 변환
                    snake_case_key = self._to_snake_case(item["key"])
                    # null 값을 빈 문자열로 변환
                    value = item["value"]
                    if value is None:
                        value = ""
                    result_dict[snake_case_key] = value
            return result_dict
        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Failed to process labels array: {e}")
            return {}

    def _process_system_labels_data(self, system_labels_data) -> dict:
        """System Labels 데이터를 구조적 딕셔너리로 변환 (labels와 동일한 로직 사용)"""
        # labels와 동일한 처리 로직 적용
        if isinstance(system_labels_data, list):
            return self._process_labels_array(system_labels_data)
        elif isinstance(system_labels_data, dict):
            return system_labels_data
        else:
            _LOGGER.warning(
                f"[FieldMapper] Unexpected system_labels data type: {type(system_labels_data)}"
            )
            return {}

    def _process_ancestors_data(self, ancestors_data) -> list:
        """Project Ancestors 데이터를 리스트로 처리"""
        try:
            if not ancestors_data:
                return []

            if isinstance(ancestors_data, list):
                # 이미 리스트인 경우 그대로 반환
                return ancestors_data
            elif isinstance(ancestors_data, str):
                # 문자열인 경우 쉼표로 분리
                return [
                    item.strip() for item in ancestors_data.split(",") if item.strip()
                ]
            else:
                _LOGGER.warning(
                    f"[FieldMapper] Unexpected ancestors data type: {type(ancestors_data)}"
                )
                return []
        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Failed to process ancestors data: {e}")
            return []

    def _process_tags_data(self, tags_data) -> dict:
        """Tags 데이터를 구조적 딕셔너리로 변환 (labels와 유사한 로직 사용)"""
        try:
            if not tags_data:
                return {}

            if isinstance(tags_data, list):
                # 리스트인 경우 labels와 같은 방식으로 처리
                return self._process_labels_array(tags_data)
            elif isinstance(tags_data, dict):
                # 이미 딕셔너리인 경우 그대로 반환
                return tags_data
            elif isinstance(tags_data, str):
                # 문자열인 경우 기존 문자열 처리 메서드 사용
                return self._process_tags_string(tags_data)
            else:
                _LOGGER.warning(
                    f"[FieldMapper] Unexpected tags data type: {type(tags_data)}"
                )
                return {}
        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Failed to process tags data: {e}")
            return {}

    def _process_tags_string(self, tags_value: str) -> dict:
        """문자열 형태의 tags를 딕셔너리로 변환"""
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

        # JSON 파싱 시도
        json_result = self._try_parse_json_tags(tags_value)
        if json_result is not None:
            return json_result

        # JSON 파싱 실패 시 key=value 형태 파싱 시도
        return self._parse_key_value_pairs(tags_value)

    def _try_parse_json_tags(self, tags_value: str) -> dict:
        """JSON 형태의 tags 파싱 시도"""
        try:
            import json

            parsed_tags = json.loads(tags_value)

            # 파싱된 결과가 딕셔너리인 경우
            if isinstance(parsed_tags, dict):
                return parsed_tags

            # 파싱된 결과가 Google Cloud labels 배열인 경우
            elif isinstance(parsed_tags, list):
                return self._process_labels_array(parsed_tags)
            else:
                _LOGGER.warning(
                    f"[FieldMapper] Parsed tags is not a dict or labels array: {type(parsed_tags)}"
                )
                return {}

        except (json.JSONDecodeError, ValueError) as e:
            return self._handle_json_parse_error(tags_value, e)

    def _handle_json_parse_error(self, tags_value: str, error: Exception) -> dict:
        """JSON 파싱 오류 처리"""
        # 잘린 JSON 문자열인지 확인
        if self._is_truncated_json(tags_value):
            # 잘린 문자열로 보이는 경우 - 캐시에 추가하고 빈 딕셔너리 반환
            if hasattr(self, "_truncated_cache"):
                tags_hash = hash(tags_value[:100])
                self._truncated_cache.add(tags_hash)
            return {}

        # 로깅 빈도 제한 - 같은 오류는 최대 5번만 로깅
        self._log_json_error_limited(error, tags_value)

        # 일반적인 잘못된 JSON 형식들을 수정 시도
        return self._try_fix_and_parse_json(tags_value)

    def _is_truncated_json(self, tags_value: str) -> bool:
        """JSON 문자열이 잘렸는지 확인"""
        truncated_patterns = [
            "', 'value': '",  # 잘린 key-value 패턴
            "'key':",  # 시작만 있는 패턴
            '"key":',  # 시작만 있는 패턴
            "'value': '",  # value만 있는 패턴
            '"value": "',  # value만 있는 패턴
        ]

        return (
            len(tags_value) > 50
            and not tags_value.strip().endswith(("}", "]", '"', "'"))
        ) or any(pattern in tags_value[:50] for pattern in truncated_patterns)

    def _log_json_error_limited(self, error: Exception, tags_value: str):
        """JSON 오류 로깅 (빈도 제한)"""
        if not hasattr(self, "_json_error_count"):
            self._json_error_count = {}
        error_key = str(error)[:50]  # 오류 메시지의 처음 50자로 키 생성
        if self._json_error_count.get(error_key, 0) < 5:
            self._json_error_count[error_key] = (
                self._json_error_count.get(error_key, 0) + 1
            )
            _LOGGER.debug(
                f"[FieldMapper] JSON parsing failed for: {repr(tags_value[:50])}, error: {error}"
            )

    def _try_fix_and_parse_json(self, tags_value: str) -> dict:
        """잘못된 JSON 형식을 수정하고 다시 파싱 시도"""
        cleaned_value = self._try_fix_malformed_json(tags_value)
        if cleaned_value != tags_value:
            try:
                import json

                parsed_tags = json.loads(cleaned_value)
                if isinstance(parsed_tags, dict):
                    return parsed_tags
                elif isinstance(parsed_tags, list):
                    return self._process_labels_array(parsed_tags)
            except (json.JSONDecodeError, ValueError):
                pass
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
            return self._compile_dict_mapping(mapping_rule)

        elif callable(mapping_rule):
            # 함수 매핑
            return mapping_rule

        # 기본값 반환
        return lambda data: mapping_rule

    def _compile_dict_mapping(self, mapping_rule: dict) -> Callable:
        """딕셔너리 형태의 매핑 규칙을 컴파일"""
        if "field" in mapping_rule:
            return self._compile_field_mapping(mapping_rule)
        elif "expression" in mapping_rule:
            return self._compile_expression_mapping(mapping_rule)
        elif "constant" in mapping_rule:
            return self._compile_constant_mapping(mapping_rule)
        else:
            return self._compile_complex_dict_mapping(mapping_rule)

    def _compile_field_mapping(self, mapping_rule: dict) -> Callable:
        """필드 매핑 + 변환 규칙을 컴파일"""
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

    def _compile_expression_mapping(self, mapping_rule: dict) -> Callable:
        """표현식 매핑 규칙을 컴파일"""
        expression = mapping_rule["expression"]
        return lambda data, expr=expression: self._evaluate_expression(expr, data)

    def _compile_constant_mapping(self, mapping_rule: dict) -> Callable:
        """상수 값 매핑 규칙을 컴파일"""
        constant_value = mapping_rule["constant"]
        return lambda data, const=constant_value: const

    def _compile_complex_dict_mapping(self, mapping_rule: dict) -> Callable:
        """복합 딕셔너리 매핑 규칙을 컴파일"""

        def map_dict_fields(data, rules=mapping_rule):
            result = {}

            for target_field, source_config in rules.items():
                result[target_field] = self._process_dict_field_mapping(
                    data, target_field, source_config
                )
            return result

        return map_dict_fields

    def _process_dict_field_mapping(
        self, data: dict, target_field: str, source_config
    ) -> str:
        """딕셔너리 매핑에서 개별 필드 처리"""
        if isinstance(source_config, str):
            # 단순 필드 매핑 (중첩 경로 지원)
            value = self._get_nested_value(data, source_config, "")

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

            return value

        elif isinstance(source_config, dict) and "field" in source_config:
            # 변환이 포함된 필드 매핑 (중첩 경로 지원)
            field_name = source_config["field"]
            transform = source_config.get("transform")
            value = self._get_nested_value(data, field_name, "")
            return self._apply_transform(value, transform)
        else:
            return ""

    def _map_field(
        self, field_name: str, source_data: dict, default_value: Any = None
    ) -> Any:
        """필드 매핑 실행"""
        if field_name in self.compiled_mappings:
            try:
                result = self.compiled_mappings[field_name](source_data)

                # billed_date 필드에 대한 특별 디버깅 (간소화)
                if field_name == "billed_date" and not hasattr(
                    self, "_debug_billed_date_mapping_logged"
                ):
                    _LOGGER.debug(f"[FieldMapper] billed_date mapping: {result}")
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
            _LOGGER.debug("[FieldMapper] billed_date fallback mapping used")
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
                return self._process_nested_path(data, path, default_value)
            else:
                # 단순 필드명
                return data.get(path, default_value)

        except Exception as e:
            _LOGGER.warning(
                f"[FieldMapper] Failed to get nested value for path '{path}': {e}"
            )
            return default_value

    def _process_nested_path(self, data: dict, path: str, default_value: Any) -> Any:
        """중첩 경로 처리"""
        keys = path.split(".")
        current_value = data

        for i, key in enumerate(keys):
            current_value = self._process_single_key(
                current_value, key, path, i, len(keys), data
            )
            if current_value is None:
                return default_value

        # 결과 검증 및 로깅
        result = current_value if current_value is not None else default_value
        self._log_nested_result(path, result)
        return result

    def _process_single_key(
        self,
        current_value,
        key: str,
        path: str,
        step: int,
        total_steps: int,
        original_data: dict,
    ):
        """단일 키 처리"""
        if isinstance(current_value, dict):
            value = current_value.get(key)
            if value is None:
                self._log_nested_failure(path, key, step, total_steps, original_data)
            return value
        elif isinstance(current_value, str):
            return self._parse_json_for_key(current_value, key)
        else:
            self._log_type_mismatch(path, key, current_value)
            return None

    def _log_nested_failure(
        self, path: str, key: str, step: int, total_steps: int, original_data: dict
    ):
        """중첩 경로 실패 로깅"""
        if path in ["project.id", "service.id", "sku.id"]:
            _LOGGER.debug(
                f"[FieldMapper] Nested path '{path}' failed at key '{key}' (step {step + 1}/{total_steps})"
            )
            _LOGGER.debug(
                f"[FieldMapper] Available keys at this level: {list(original_data.keys()) if step == 0 else 'N/A'}"
            )

    def _parse_json_for_key(self, json_str: str, key: str):
        """JSON 문자열에서 키 값 추출"""
        try:
            import json

            parsed_value = json.loads(json_str)
            if isinstance(parsed_value, dict):
                return parsed_value.get(key)
            else:
                return None
        except (json.JSONDecodeError, ValueError):
            return None

    def _log_type_mismatch(self, path: str, key: str, current_value):
        """타입 불일치 로깅"""
        if path in ["project.id", "service.id", "sku.id"]:
            _LOGGER.debug(
                f"[FieldMapper] Nested path '{path}' expected dict but got {type(current_value)} at key '{key}'"
            )

    def _log_nested_result(self, path: str, result):
        """중첩 경로 결과 로깅"""
        important_paths = [
            "project.id",
            "service.id",
            "sku.id",
            "service.description",
            "sku.description",
            "project.name",
            "invoice.month",
        ]

        if path in important_paths:
            log_key = f"_nested_log_{path.replace('.', '_')}"
            if not hasattr(self, log_key):
                _LOGGER.debug(f"[FieldMapper] Nested '{path}': {str(result)[:100]}...")
                setattr(self, log_key, True)

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
                return self._apply_json_parse_transform(value)
            elif transform == "json_parse_array":
                return self._apply_json_parse_array_transform(value)
            elif transform == "array_parse":
                return self._apply_array_parse_transform(value)
            else:
                _LOGGER.warning(f"[FieldMapper] Unknown transform: {transform}")
                return value

        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Transform failed: {transform}, error: {e}")
            return value

    def _apply_json_parse_transform(self, value: Any) -> dict:
        """JSON 파싱 변환 적용 - Google Cloud labels 배열 지원 (null 값을 빈 문자열로 처리)"""
        import json

        if not value:
            return {}

        # 이미 딕셔너리인 경우 null 값을 빈 문자열로 변환하여 반환
        if isinstance(value, dict):
            return self._convert_dict_nulls_to_empty_strings(value)

        # Google Cloud labels 배열인 경우 직접 처리
        if isinstance(value, list):
            return self._process_labels_array(value)

        # 문자열로 변환
        json_str = str(value).strip()

        # 빈 문자열이거나 None인 경우
        if not json_str or json_str.lower() in ("none", "null", ""):
            return {}

        # JSON 파싱 시도
        try:
            parsed = json.loads(json_str)

            # 파싱된 결과가 딕셔너리인 경우 null 값을 빈 문자열로 변환하여 반환
            if isinstance(parsed, dict):
                return self._convert_dict_nulls_to_empty_strings(parsed)

            # 파싱된 결과가 Google Cloud labels 배열인 경우 처리
            elif isinstance(parsed, list):
                return self._process_labels_array(parsed)

            # 기타 타입인 경우 빈 딕셔너리 반환
            else:
                return {}
        except (json.JSONDecodeError, ValueError):
            return self._parse_json_fallback(json_str)

    def _apply_json_parse_array_transform(self, value: Any) -> list:
        """JSON 배열 파싱 변환 적용 - Credits Detail 등을 위한 배열 반환 (null 값을 빈 문자열로 처리)"""
        import json

        if not value:
            return []

        # 이미 리스트인 경우 null 값을 빈 문자열로 변환하여 반환
        if isinstance(value, list):
            return self._convert_list_nulls_to_empty_strings(value)

        # 문자열로 변환
        json_str = str(value).strip()

        # 빈 문자열이거나 None인 경우
        if not json_str or json_str.lower() in ("none", "null", ""):
            return []

        # JSON 파싱 시도
        try:
            parsed = json.loads(json_str)
            # 파싱된 결과가 배열인 경우 null 값을 빈 문자열로 변환하여 반환
            if isinstance(parsed, list):
                return self._convert_list_nulls_to_empty_strings(parsed)
            # 파싱된 결과가 단일 객체인 경우 배열로 감싸서 반환
            else:
                if parsed is None:
                    return [""]
                return [parsed]
        except (json.JSONDecodeError, ValueError):
            # 파싱 실패 시 빈 배열 반환
            return []

    def _apply_array_parse_transform(self, value: Any) -> list:
        """배열 파싱 변환 적용 - 새로운 스키마 구조 지원"""
        if not value:
            return []

        # 이미 리스트인 경우 그대로 반환
        if isinstance(value, list):
            return value

        # pandas NaN 체크
        try:
            import pandas as pd

            if pd.isna(value):
                return []
        except (TypeError, ValueError, ImportError):
            pass

        # 문자열 처리
        str_value = str(value).strip()
        if not str_value or str_value.lower() in ("none", "null", "", "nan"):
            return []

        try:
            # 슬래시로 구분된 문자열에서 빈 문자열 제거 (예: "/219641957767/" -> ["219641957767"])
            if str_value.startswith("/") and str_value.endswith("/"):
                array_items = [
                    item.strip() for item in str_value.split("/") if item.strip()
                ]
                return array_items

            # JSON 배열 파싱 시도
            import json

            parsed = json.loads(str_value)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            # 파싱 실패 시 단일 항목 배열로 반환
            return [str_value]

    def _parse_json_fallback(self, json_str: str) -> dict:
        """JSON 파싱 실패 시 대안 처리"""
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

    def _convert_dict_nulls_to_empty_strings(self, data: dict) -> dict:
        """딕셔너리 내의 null 값을 빈 문자열로 변환"""
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = ""
            elif isinstance(value, dict):
                result[key] = self._convert_dict_nulls_to_empty_strings(value)
            elif isinstance(value, list):
                result[key] = self._convert_list_nulls_to_empty_strings(value)
            else:
                result[key] = value
        return result

    def _convert_list_nulls_to_empty_strings(self, data: list) -> list:
        """리스트 내의 null 값을 빈 문자열로 변환"""
        if not isinstance(data, list):
            return data

        result = []
        for item in data:
            if item is None:
                result.append("")
            elif isinstance(item, dict):
                result.append(self._convert_dict_nulls_to_empty_strings(item))
            elif isinstance(item, list):
                result.append(self._convert_list_nulls_to_empty_strings(item))
            else:
                result.append(item)
        return result

    def _convert_keys_to_title_case(self, data: dict) -> dict:
        """딕셔너리의 모든 키를 Title Case로 변환 (재귀적 처리)"""
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            # 키를 Title Case로 변환
            title_case_key = self._to_title_case(key)

            # 값이 딕셔너리인 경우 재귀적으로 처리
            if isinstance(value, dict):
                result[title_case_key] = self._convert_keys_to_title_case(value)
            # 값이 리스트인 경우 리스트 내 딕셔너리들도 처리
            elif isinstance(value, list):
                result[title_case_key] = self._convert_list_keys_to_title_case(value)
            else:
                result[title_case_key] = value

        return result

    def _convert_list_keys_to_title_case(self, data: list) -> list:
        """리스트 내 딕셔너리들의 키를 Title Case로 변환"""
        if not isinstance(data, list):
            return data

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(self._convert_keys_to_title_case(item))
            elif isinstance(item, list):
                result.append(self._convert_list_keys_to_title_case(item))
            else:
                result.append(item)
        return result

    def _to_title_case(self, text: str) -> str:
        """문자열을 Title Case로 변환 (특수 문자 처리 포함)"""
        if not isinstance(text, str):
            return str(text)

        # 이미 Title Case인 경우 그대로 반환 (예: "Project ID", "SKU Description")
        if text and text[0].isupper() and any(c.isupper() for c in text[1:]):
            return text

        # 하이픈이나 언더스코어로 구분된 단어들을 Title Case로 변환
        # 예: "goog-gke-node" -> "Goog Gke Node"
        if "-" in text or "_" in text:
            # 하이픈과 언더스코어를 공백으로 치환하고 각 단어를 Title Case로
            words = text.replace("-", " ").replace("_", " ").split()
            return " ".join(word.capitalize() for word in words)

        # 일반적인 경우 첫 글자만 대문자로
        return text.capitalize()

    def _to_snake_case(self, text: str) -> str:
        """문자열을 snake_case로 변환 (하이픈을 언더스코어로 변환)"""
        if not isinstance(text, str):
            return str(text)

        # 하이픈을 언더스코어로 변환
        # 예: "goog-gke-node" -> "goog_gke_node"
        return text.replace("-", "_")

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
        # 디버깅 로깅 (처음 10개만)
        self._log_date_debug_info(value)

        # 빈 값 처리 (None 반환 - 현재 날짜 사용하지 않음)
        if self._is_empty_or_today(value):
            _LOGGER.debug(
                "[FieldMapper] DEBUG: _format_date received empty value, returning None"
            )
            return None

        try:
            # Invoice Month 형태 (YYYYMM) 처리
            if isinstance(value, str) and len(value) == 6 and value.isdigit():
                year = value[:4]
                month = value[4:6]
                import calendar

                last_day = calendar.monthrange(int(year), int(month))[1]
                result = f"{year}-{month}-{last_day:02d}"
                _LOGGER.debug(
                    f"[FieldMapper] Converted invoice_month {value} to {result}"
                )
                return result

            return self._parse_date_value(value)
        except Exception as e:
            _LOGGER.warning(f"[FieldMapper] Date format failed: {value}, error: {e}")
            # 예외 발생 시에도 None 반환 (현재 날짜 사용하지 않음)
            return None

    def _log_date_debug_info(self, value: Any):
        """날짜 변환 디버깅 정보 로깅"""
        if not hasattr(self, "_debug_format_date_count"):
            self._debug_format_date_count = 0

        # 처음 10개 레코드에 대해서만 상세 로깅
        if self._debug_format_date_count < 10:
            self._debug_format_date_count += 1

    def _is_empty_or_today(self, value: Any) -> bool:
        """빈 값인지 확인 (today는 더 이상 사용하지 않음)"""
        return not value or str(value).strip() == ""

    def _parse_date_value(self, value: Any) -> str:
        """날짜 값 파싱"""
        # pandas.Timestamp 객체 처리
        if hasattr(value, "to_pydatetime"):
            result = value.to_pydatetime().strftime("%Y-%m-%d")
            if self._debug_format_date_count <= 10:
                pass
            return result
        elif isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        elif isinstance(value, str):
            return self._parse_string_date(value)
        else:
            # 기타 타입은 None 반환 (현재 날짜 사용하지 않음)
            _LOGGER.warning(
                f"[FieldMapper] Unsupported date type: {type(value)}, value: {value}, returning None"
            )
            return None

    def _parse_string_date(self, value: str) -> str:
        """문자열 형태의 날짜 파싱"""
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

        # 파싱 실패 시 None 반환 (현재 날짜 사용하지 않음)
        _LOGGER.warning(f"[FieldMapper] Failed to parse date: {value}, returning None")
        return None

    def _get_default_mapping(self, provider: str) -> dict:
        """프로바이더별 기본 매핑 반환"""
        if provider == "google_cloud" or provider == "gcp":
            return {
                "cost": "cost",
                "usage_quantity": {
                    "field": "additional_info.Usage Amount",
                    "fallback": "additional_info.Usage Amount In Pricing Units",
                    "fallback2": "usage_quantity",
                },
                "usage_unit": {
                    "field": "additional_info.Usage Unit",
                    "fallback": "additional_info.Usage Pricing Unit",
                    "fallback2": "usage_unit",
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
                    "fallback": "invoice_month",
                    "default": None,
                },
                "tags": {"field": "labels", "transform": "json_parse"},
                "additional_info": {
                    #  비용 관련 필드들 (BigQuery 스타일) - Title Case 유지
                    "Cost At List": "Cost At List",
                    "Cost After Credits": "Cost After Credits",
                    "Cost At Effective Price Default": "Cost At Effective Price Default",
                    "Cost At List Consumption Model": "Cost At List Consumption Model",
                    "Credits Amount": "Credits Amount",  # AmortizedCost용
                    "Credits Detail": {
                        "field": "credits_detail",
                        "transform": "json_parse_array",
                        "output_key": "Credits Detail",
                    },
                    "Currency Conversion Rate": "Currency Conversion Rate",
                    #  계정 및 청구 정보 - Title Case 유지
                    "Billing Account ID": "Billing Account ID",
                    "Invoice Month": {
                        "field": "invoice.month",
                        "fallback": "invoice_month",
                        "output_key": "Invoice Month",
                    },
                    "Invoice Publisher Type": {
                        "field": "invoice.publisher_type",
                        "fallback": "invoice_publisher_type",
                        "output_key": "Invoice Publisher Type",
                    },
                    "Cost Type": "Cost Type",
                    "Transaction Type": "Transaction Type",
                    "Seller Name": "Seller Name",
                    # ️ 프로젝트 정보 (BigQuery 중첩 구조) - Title Case 유지
                    "Project ID": {
                        "field": "project.id",
                        "fallback": "project_id",
                        "output_key": "Project ID",
                    },
                    "Project Name": {
                        "field": "project.name",
                        "fallback": "project_name",
                        "output_key": "Project Name",
                    },
                    "Project Number": {
                        "field": "project.number",
                        "fallback": "project_number",
                        "output_key": "Project Number",
                    },
                    "Project Ancestry Numbers": {
                        "field": "project.ancestry_numbers",
                        "fallback": "project_ancestry_numbers",
                        "transform": "array_parse",
                        "output_key": "Project Ancestry Numbers",
                    },
                    # 서비스 정보 (BigQuery 중첩 구조) - Title Case 유지
                    "Service ID": {
                        "field": "service.id",
                        "fallback": "service_id",
                        "output_key": "Service ID",
                    },
                    "Service Description": {
                        "field": "service.description",
                        "fallback": "service_description",
                        "output_key": "Service Description",
                    },
                    #  SKU 정보 (BigQuery 중첩 구조) - Title Case 유지
                    "SKU ID": {
                        "field": "sku.id",
                        "fallback": "sku_id",
                        "output_key": "SKU ID",
                    },
                    "SKU Description": {
                        "field": "sku.description",
                        "fallback": "sku_description",
                        "output_key": "SKU Description",
                    },
                    #  위치 정보 (BigQuery 중첩 구조)
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
                    # 사용량 정보 (BigQuery 중첩 구조)
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
                    #  가격 정보 (BigQuery price 중첩 구조)
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
                    # ️ 라벨 및 태그 (BigQuery 배열 구조)
                    "System Labels": {
                        "field": "system_labels",
                        "transform": "json_parse",
                    },
                    "Resource Tags": {"field": "tags", "transform": "json_parse"},
                    # 소비 모델 정보
                    "Consumption Model ID": {
                        "field": "consumption_model.id",
                        "fallback": "consumption_model_id",
                    },
                    "Consumption Model Description": {
                        "field": "consumption_model.description",
                        "fallback": "consumption_model_description",
                    },
                    # 메타데이터
                    "Export Time": "export_time",
                    "Adjustment Info": {
                        "field": "adjustment_info",
                        "transform": "json_parse",
                    },
                    #  리소스 식별 필드 (상세 사용량 데이터용)
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

    def _track_daily_count(self, billed_date: str):
        """일별 카운트 추적 및 주기적 로깅"""
        if not billed_date or billed_date == "unknown":
            billed_date = "unknown_date"

        # 카운트 증가
        self.daily_count_tracker[billed_date] = (
            self.daily_count_tracker.get(billed_date, 0) + 1
        )
        self.total_processed_count += 1

        # 100개마다 중간 요약 로깅
        if self.total_processed_count % 100 == 0:
            self._log_daily_count_summary(is_intermediate=True)

        # 1000개마다 상세 로깅
        if self.total_processed_count % 1000 == 0:
            self._log_daily_count_summary(is_intermediate=False)

    def _log_daily_count_summary(self, is_intermediate: bool = False):
        """일별 카운트 요약 로깅"""
        if not self.daily_count_tracker:
            return

        # log_type = "중간" if is_intermediate else "상세"

        # 날짜순으로 정렬하여 로깅 (주석 처리됨)
        # sorted_dates = sorted(self.daily_count_tracker.items())
        # for date, count in sorted_dates:
        #     percentage = (count / self.total_processed_count) * 100 if self.total_processed_count > 0 else 0

    def log_final_daily_count_summary(self):
        """최종 일별 카운트 요약 로깅 (외부에서 호출 가능)"""
        _LOGGER.info("[FieldMapper] === 최종 일별 카운트 요약 ===")
        _LOGGER.info(f"[FieldMapper] 총 처리 레코드: {self.total_processed_count:,}개")

        if self.daily_count_tracker:
            _LOGGER.info(
                f"[FieldMapper] 처리 기간: {min(self.daily_count_tracker.keys())} ~ {max(self.daily_count_tracker.keys())}"
            )
            _LOGGER.info(
                f"[FieldMapper] 고유 날짜 수: {len(self.daily_count_tracker)}개"
            )

            # 날짜별 상세 정보
            sorted_dates = sorted(self.daily_count_tracker.items())
            for date, count in sorted_dates:
                percentage = (count / self.total_processed_count) * 100
                _LOGGER.info(
                    f"[FieldMapper] {date}: {count:,}개 레코드 ({percentage:.2f}%)"
                )
        else:
            _LOGGER.warning("[FieldMapper] 처리된 데이터가 없습니다")

        _LOGGER.info("[FieldMapper] === 일별 카운트 요약 완료 ===")

    def reset_daily_count_tracker(self):
        """일별 카운트 추적기 초기화"""
        self.daily_count_tracker.clear()
        self.total_processed_count = 0
        _LOGGER.info("[FieldMapper] 일별 카운트 추적기가 초기화되었습니다")

    def _process_repeated_field(self, value: Any, field_name: str) -> list:
        """REPEATED 모드 필드를 배열로 처리"""
        if not value:
            return []

        # pandas NaN 체크
        try:
            import pandas as pd

            if pd.isna(value):
                return []
        except (TypeError, ValueError, ImportError):
            pass

        # 이미 리스트인 경우
        if isinstance(value, list):
            return self._clean_repeated_array(value)

        # 문자열인 경우 JSON 파싱 시도
        if isinstance(value, str):
            str_value = value.strip()
            if not str_value or str_value.lower() in ("none", "null", "", "nan"):
                return []

            try:
                import json

                parsed = json.loads(str_value)
                if isinstance(parsed, list):
                    return self._clean_repeated_array(parsed)
                elif isinstance(parsed, dict):
                    return [parsed]  # 단일 객체를 배열로 감쌈
                else:
                    return [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                # JSON이 아닌 경우 단일 항목으로 처리
                return [str_value]

        # 딕셔너리인 경우 단일 항목 배열로 변환
        if isinstance(value, dict):
            return [value]

        # 기타 타입은 문자열로 변환 후 단일 항목 배열
        return [str(value)]

    def _clean_repeated_array(self, array: list) -> list:
        """REPEATED 배열의 각 항목을 정리"""
        cleaned = []
        for item in array:
            if item is None:
                continue

            # pandas NaN 체크
            try:
                import pandas as pd

                if pd.isna(item):
                    continue
            except (TypeError, ValueError, ImportError):
                pass

            # 빈 문자열이나 null 값 제거
            if isinstance(item, str) and item.strip().lower() in (
                "",
                "none",
                "null",
                "nan",
            ):
                continue

            cleaned.append(item)

        return cleaned

    def _process_project_labels(self, project_data: dict) -> list:
        """project.labels REPEATED 필드 처리"""
        if not isinstance(project_data, dict):
            return []

        labels_data = project_data.get("labels")
        return self._process_repeated_field(labels_data, "project.labels")

    def _process_project_ancestors(self, project_data: dict) -> list:
        """project.ancestors REPEATED 필드 처리"""
        if not isinstance(project_data, dict):
            return []

        ancestors_data = project_data.get("ancestors")
        return self._process_repeated_field(ancestors_data, "project.ancestors")

    def _process_labels_array(self, labels_data: Any) -> list:
        """labels REPEATED 필드 처리"""
        return self._process_repeated_field(labels_data, "labels")

    def _process_system_labels_array(self, system_labels_data: Any) -> list:
        """system_labels REPEATED 필드 처리"""
        return self._process_repeated_field(system_labels_data, "system_labels")

    def _process_tags_array(self, tags_data: Any) -> list:
        """tags REPEATED 필드 처리"""
        return self._process_repeated_field(tags_data, "tags")

    def _process_credits_array(self, credits_data: Any) -> list:
        """credits REPEATED 필드 처리"""
        return self._process_repeated_field(credits_data, "credits")
