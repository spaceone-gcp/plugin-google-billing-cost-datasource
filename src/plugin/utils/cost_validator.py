import logging

_LOGGER = logging.getLogger("spaceone")


class CostCalculationValidator:
    """비용 계산 검증 도구"""

    @staticmethod
    def validate_cost_relationships(record: dict) -> dict:
        """비용 관계식 검증"""
        data_fields = record.get("data", {})

        validation_results = {"is_valid": True, "errors": [], "warnings": []}

        # 기본 값들 추출
        cost = record.get("cost")
        list_price = data_fields.get("List Price")
        credits_total = data_fields.get("Credits Total Amount")
        usage_amount = data_fields.get("Usage Amount")

        # 1. 필수 필드 존재 검증
        if cost is None:
            validation_results["errors"].append("Missing required field: cost")
            validation_results["is_valid"] = False

        if list_price is None:
            validation_results["errors"].append(
                "Missing required field: List Price in data"
            )
            validation_results["is_valid"] = False

        # 2. 크레딧 적용 검증 (크레딧이 있는 경우)
        if all(v is not None for v in [cost, list_price, credits_total]):
            expected_cost = (
                list_price + credits_total
            )  # credits_total은 일반적으로 음수
            if abs(cost - expected_cost) > 0.01:
                validation_results["warnings"].append(
                    f"Credit calculation variance: cost({cost}) vs expected({expected_cost:.6f})"
                )

        # 3. 사용량 데이터 일관성 검증
        if usage_amount is not None and usage_amount < 0:
            validation_results["warnings"].append(
                f"Negative usage amount detected: {usage_amount}"
            )

        return validation_results

    @staticmethod
    def calculate_discount_rate(list_price: float, final_cost: float) -> float:
        """할인율 계산"""
        if list_price == 0:
            return 0.0

        discount_amount = list_price - final_cost
        discount_rate = (discount_amount / list_price) * 100
        return round(discount_rate, 2)

    @staticmethod
    def analyze_cost_breakdown(record: dict) -> dict:
        """비용 구성 분석"""
        data_fields = record.get("data", {})
        additional_info = record.get("additional_info", {})

        analysis = {
            "base_cost": data_fields.get("List Price", 0),
            "final_cost": record.get("cost", 0),
            "credits_applied": data_fields.get("Credits Total Amount", 0),
            "usage_amount": data_fields.get("Usage Amount", 0),
            "discount_amount": 0,
            "discount_rate": 0,
            "currency": additional_info.get("Currency", "USD"),
        }

        # 할인 금액 및 할인율 계산
        if analysis["base_cost"] > 0:
            analysis["discount_amount"] = analysis["base_cost"] - analysis["final_cost"]
            analysis["discount_rate"] = (
                CostCalculationValidator.calculate_discount_rate(
                    analysis["base_cost"], analysis["final_cost"]
                )
            )

        return analysis

    @staticmethod
    def validate_data_field_structure(record: dict) -> dict:
        """data 필드 구조 검증"""
        validation_results = {"is_valid": True, "errors": [], "warnings": []}

        data_fields = record.get("data", {})

        # SpaceONE 표준 필드 검증
        expected_fields = ["List Price", "Usage Amount"]
        optional_fields = ["Credits Total Amount", "Usage Amount in Pricing Units"]

        # 필수 필드 검증
        for field in expected_fields:
            if field not in data_fields:
                validation_results["errors"].append(
                    f"Missing required field in data: {field}"
                )
                validation_results["is_valid"] = False

        # 예상치 못한 필드 검증
        allowed_fields = expected_fields + optional_fields
        for field in data_fields.keys():
            if field not in allowed_fields:
                validation_results["warnings"].append(
                    f"Unexpected field in data: {field}"
                )

        return validation_results
