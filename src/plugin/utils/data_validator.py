"""
데이터 검증 및 품질 체크 유틸리티
TDD로 구현된 새로운 기능
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

_LOGGER = logging.getLogger("spaceone")


class ValidationError(Exception):
    """데이터 검증 오류"""

    pass


class DataValidator:
    """데이터 검증 및 품질 체크 클래스"""

    def __init__(self):
        """DataValidator 초기화"""
        self.reset_validation_stats()
        self.required_fields = [
            "cost",
            "usage_quantity",
            "product",
            "region_code",
            "billed_date",
        ]

    def validate_cost_data(self, record: dict[str, Any]) -> dict[str, Any]:
        """비용 데이터 종합 검증

        Args:
            record: 검증할 비용 데이터 레코드

        Returns:
            검증 결과 딕셔너리

        Raises:
            ValidationError: 검증 실패 시
        """
        validation_result = {"is_valid": True, "errors": [], "warnings": []}

        try:
            # 1. 필수 필드 검증
            missing_fields = self._check_required_fields(record)
            if missing_fields:
                validation_result["is_valid"] = False
                validation_result["errors"].append(
                    f"Missing required fields: {missing_fields}"
                )

            # 2. 데이터 타입 검증
            type_errors = self._validate_data_types(record)
            if type_errors:
                validation_result["is_valid"] = False
                validation_result["errors"].extend(type_errors)

            # 3. 비즈니스 규칙 검증
            business_errors = self._validate_business_rules(record)
            if business_errors:
                validation_result["is_valid"] = False
                validation_result["errors"].extend(business_errors)

            # 통계 업데이트
            if validation_result["is_valid"]:
                self.stats["valid_records"] += 1
            else:
                self.stats["invalid_records"] += 1

            self.stats["total_records"] += 1

            return validation_result

        except Exception as e:
            _LOGGER.error(f"[DataValidator] Validation error: {e}")
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Validation exception: {str(e)}")
            self.stats["error_records"] += 1
            self.stats["total_records"] += 1
            return validation_result

    def validate_data_types(self, record: dict[str, Any]) -> dict[str, Any]:
        """데이터 타입 검증

        Args:
            record: 검증할 레코드

        Returns:
            검증 결과
        """
        validation_result = {"is_valid": True, "errors": []}

        type_errors = self._validate_data_types(record)
        if type_errors:
            validation_result["is_valid"] = False
            validation_result["errors"] = type_errors

        return validation_result

    def validate_business_rules(self, record: dict[str, Any]) -> dict[str, Any]:
        """비즈니스 규칙 검증

        Args:
            record: 검증할 레코드

        Returns:
            검증 결과
        """
        validation_result = {"is_valid": True, "errors": []}

        business_errors = self._validate_business_rules(record)
        if business_errors:
            validation_result["is_valid"] = False
            validation_result["errors"] = business_errors

        return validation_result

    def get_validation_summary(self) -> dict[str, Any]:
        """검증 통계 요약 반환

        Returns:
            검증 통계 딕셔너리
        """
        total = self.stats["total_records"]
        valid_rate = (self.stats["valid_records"] / total * 100) if total > 0 else 0

        return {
            "total_records": total,
            "valid_records": self.stats["valid_records"],
            "invalid_records": self.stats["invalid_records"],
            "error_records": self.stats["error_records"],
            "valid_rate_percent": round(valid_rate, 2),
            "validation_errors": self.stats["validation_errors"].copy(),
        }

    def reset_validation_stats(self) -> None:
        """검증 통계 초기화"""
        self.stats = {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "error_records": 0,
            "validation_errors": [],
        }

    def _check_required_fields(self, record: dict[str, Any]) -> list[str]:
        """필수 필드 존재 여부 확인"""
        missing_fields = []
        for field in self.required_fields:
            if field not in record or record[field] is None:
                missing_fields.append(field)
        return missing_fields

    def _validate_data_types(self, record: dict[str, Any]) -> list[str]:
        """데이터 타입 검증"""
        errors = []

        # cost 필드 검증
        if "cost" in record:
            cost = record["cost"]
            if not isinstance(cost, (Decimal, int, float)):
                errors.append("cost must be a numeric type (Decimal, int, or float)")

        # usage_quantity 필드 검증
        if "usage_quantity" in record:
            usage_quantity = record["usage_quantity"]
            if not isinstance(usage_quantity, (Decimal, int, float)):
                errors.append(
                    "usage_quantity must be a numeric type (Decimal, int, or float)"
                )

        # product 필드 검증
        if "product" in record:
            product = record["product"]
            if not isinstance(product, str):
                errors.append("product must be a string")

        # region_code 필드 검증
        if "region_code" in record:
            region_code = record["region_code"]
            if not isinstance(region_code, str):
                errors.append("region_code must be a string")

        # billed_date 필드 검증 - 타입 강제 변환 포함
        if "billed_date" in record:
            billed_date = record["billed_date"]

            # 타입이 문자열이 아닌 경우 강제 변환
            if not isinstance(billed_date, str):
                # 강제로 문자열로 변환
                record["billed_date"] = (
                    str(billed_date) if billed_date is not None else ""
                )
                billed_date = record["billed_date"]

            # 빈 문자열인 경우 None으로 설정 (현재 날짜 사용하지 않음)
            if not billed_date or billed_date.strip() == "":
                record["billed_date"] = None
                billed_date = record["billed_date"]

            # billed_date가 None이 아닌 경우에만 날짜 형식 검증 및 변환
            if billed_date is not None:
                try:
                    # 이미 올바른 형식인지 확인
                    datetime.strptime(billed_date, "%Y-%m-%d")
                except ValueError:
                    # 다른 형식의 날짜를 YYYY-MM-DD로 변환 시도
                    date_formats = [
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                        "%Y-%m-%d %H:%M:%S UTC",
                        "%Y/%m/%d",
                        "%m/%d/%Y",
                        "%d/%m/%Y",
                    ]

                    converted = False
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(billed_date, fmt)
                            record["billed_date"] = parsed_date.strftime("%Y-%m-%d")
                            converted = True
                            break
                        except ValueError:
                            continue

                    # 변환 실패 시 None 유지 (현재 날짜 사용하지 않음)
                    if not converted:
                        record["billed_date"] = None

        return errors

    def _validate_business_rules(self, record: dict[str, Any]) -> list[str]:
        """비즈니스 규칙 검증"""
        errors = []

        # 비용이 음수인지 확인
        if "cost" in record:
            try:
                cost = Decimal(str(record["cost"]))
                if cost < 0:
                    errors.append("cost cannot be negative")
            except (ValueError, TypeError):
                # 타입 검증에서 이미 처리됨
                pass

        # 사용량이 음수인지 확인
        if "usage_quantity" in record:
            try:
                usage_quantity = Decimal(str(record["usage_quantity"]))
                if usage_quantity < 0:
                    errors.append("usage_quantity cannot be negative")
            except (ValueError, TypeError):
                # 타입 검증에서 이미 처리됨
                pass

        # 미래 날짜 확인
        if "billed_date" in record:
            try:
                billed_date = datetime.strptime(record["billed_date"], "%Y-%m-%d")
                today = datetime.now()
                if billed_date.date() > today.date():
                    errors.append("billed_date cannot be in the future")
            except (ValueError, TypeError):
                # 타입 검증에서 이미 처리됨
                pass

        # 제품명이 비어있지 않은지 확인
        if "product" in record:
            product = record["product"]
            if isinstance(product, str) and product.strip() == "":
                errors.append("product cannot be empty")

        # 지역 코드가 비어있지 않은지 확인
        if "region_code" in record:
            region_code = record["region_code"]
            if isinstance(region_code, str) and region_code.strip() == "":
                errors.append("region_code cannot be empty")

        return errors
