"""
Google Cloud Pricing Data 분석을 위한 매니저
실제 청구 데이터와 정가 데이터를 비교하여 할인율 분석, 비용 예측 등의 고급 분석 기능을 제공합니다.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from spaceone.core.manager import BaseManager

from plugin.connector.bigquery_connector import BigqueryConnector
from plugin.connector.pricing_connector import PricingConnector
from plugin.error.cost import ERROR_INVALID_ARGUMENT, ERROR_REQUIRED_PARAMETER

_LOGGER = logging.getLogger("spaceone")

REQUIRED_OPTIONS = [
    "pricing_export_project_id",
    "pricing_dataset_id",
]


class PricingManager(BaseManager):
    """Google Cloud Pricing Data 분석 매니저"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pricing_connector = PricingConnector()
        self.billing_connector = BigqueryConnector()
        self.pricing_project_id = None
        self.pricing_dataset_id = None

    def analyze_discount_rates(
        self, options: dict, secret_data: dict, task_options: dict
    ) -> Dict:
        """
        실제 청구 데이터와 정가를 비교하여 할인율 분석

        Args:
            options: 플러그인 옵션
            secret_data: 인증 정보
            task_options: 작업 옵션 (start, project_id 등)

        Returns:
            할인율 분석 결과
        """
        try:
            self._initialize_connectors(options, secret_data)

            start_date = task_options.get("start", "")
            project_id = task_options.get("project_id", "*")

            _LOGGER.info(
                f"[PricingManager] Starting discount analysis for {start_date}"
            )

            # 실제 청구 데이터 조회
            billing_data = self._get_billing_data(task_options)

            # 가격 데이터와 비교 분석
            analysis_results = []
            total_actual_cost = Decimal(0)
            total_list_price = Decimal(0)

            for billing_row in billing_data:
                comparison = self.pricing_connector.compare_billing_vs_pricing(
                    billing_row, start_date
                )

                if comparison.get("comparison_available", False):
                    analysis_results.append(
                        {
                            "service_description": billing_row.get(
                                "service_description", ""
                            ),
                            "sku_description": billing_row.get("sku_description", ""),
                            "project_id": billing_row.get("project_id", ""),
                            "actual_cost": comparison["actual_cost"],
                            "list_price_total": comparison["list_price_total"],
                            "discount_amount": comparison["discount_amount"],
                            "discount_rate_percent": comparison[
                                "discount_rate_percent"
                            ],
                            "usage_amount": comparison["usage_amount"],
                        }
                    )

                    total_actual_cost += Decimal(str(comparison["actual_cost"]))
                    total_list_price += Decimal(str(comparison["list_price_total"]))

            # 전체 할인율 계산
            overall_discount_rate = 0
            if total_list_price > 0:
                overall_discount_rate = float(
                    (total_list_price - total_actual_cost) / total_list_price * 100
                )

            return {
                "analysis_date": datetime.now().isoformat(),
                "period": start_date,
                "project_id": project_id,
                "summary": {
                    "total_actual_cost": float(total_actual_cost),
                    "total_list_price": float(total_list_price),
                    "total_discount_amount": float(
                        total_list_price - total_actual_cost
                    ),
                    "overall_discount_rate_percent": overall_discount_rate,
                    "analyzed_items_count": len(analysis_results),
                },
                "detailed_analysis": analysis_results[:100],  # 상위 100개 항목만 반환
            }

        except Exception as e:
            _LOGGER.error(f"[PricingManager] Error in discount analysis: {str(e)}")
            raise ERROR_INVALID_ARGUMENT(key="discount_analysis", value=str(e))

    def forecast_costs(
        self, options: dict, secret_data: dict, usage_scenarios: List[Dict]
    ) -> Dict:
        """
        사용량 시나리오별 비용 예측

        Args:
            options: 플러그인 옵션
            secret_data: 인증 정보
            usage_scenarios: 사용량 시나리오 목록
                예: [{"service_id": "...", "sku_id": "...", "usage_amount": 1000}]

        Returns:
            시나리오별 예상 비용
        """
        try:
            self._initialize_connectors(options, secret_data)

            _LOGGER.info(
                f"[PricingManager] Starting cost forecasting for {len(usage_scenarios)} scenarios"
            )

            forecast_results = []

            for scenario in usage_scenarios:
                service_id = scenario.get("service_id", "")
                sku_id = scenario.get("sku_id", "")
                usage_amount = Decimal(str(scenario.get("usage_amount", 0)))
                scenario_name = scenario.get(
                    "name", f"Scenario_{len(forecast_results) + 1}"
                )

                # 해당 SKU의 가격 정보 조회
                pricing_data = list(
                    self.pricing_connector.get_pricing_data(service_id, sku_id)
                )

                if pricing_data:
                    price_info = pricing_data[0]

                    # 계층별 가격 계산
                    estimated_cost = self._calculate_tiered_cost(
                        usage_amount, price_info.get("tiered_rates", [])
                    )

                    forecast_results.append(
                        {
                            "scenario_name": scenario_name,
                            "service_id": service_id,
                            "service_description": price_info.get(
                                "service_description", ""
                            ),
                            "sku_id": sku_id,
                            "sku_description": price_info.get("sku_description", ""),
                            "usage_amount": float(usage_amount),
                            "estimated_cost_usd": float(estimated_cost),
                            "pricing_available": True,
                        }
                    )
                else:
                    forecast_results.append(
                        {
                            "scenario_name": scenario_name,
                            "service_id": service_id,
                            "sku_id": sku_id,
                            "usage_amount": float(usage_amount),
                            "estimated_cost_usd": 0,
                            "pricing_available": False,
                            "error": "Pricing data not found",
                        }
                    )

            total_estimated_cost = sum(
                result["estimated_cost_usd"]
                for result in forecast_results
                if result.get("pricing_available", False)
            )

            return {
                "forecast_date": datetime.now().isoformat(),
                "total_scenarios": len(usage_scenarios),
                "total_estimated_cost_usd": total_estimated_cost,
                "scenarios": forecast_results,
            }

        except Exception as e:
            _LOGGER.error(f"[PricingManager] Error in cost forecasting: {str(e)}")
            raise ERROR_INVALID_ARGUMENT(key="cost_forecasting", value=str(e))

    def get_service_pricing_report(
        self, options: dict, secret_data: dict, service_filter: Optional[str] = None
    ) -> Dict:
        """
        서비스별 가격 정보 리포트 생성

        Args:
            options: 플러그인 옵션
            secret_data: 인증 정보
            service_filter: 특정 서비스로 필터링 (선택사항)

        Returns:
            서비스별 가격 정보 리포트
        """
        try:
            self._initialize_connectors(options, secret_data)

            _LOGGER.info("[PricingManager] Generating service pricing report")

            # 서비스별 가격 요약 조회
            service_summary = self.pricing_connector.get_service_pricing_summary()

            # 필터링 적용
            if service_filter:
                filtered_summary = {}
                for service_name, skus in service_summary.items():
                    if service_filter.lower() in service_name.lower():
                        filtered_summary[service_name] = skus
                service_summary = filtered_summary

            # 통계 계산
            total_services = len(service_summary)
            total_skus = sum(len(skus) for skus in service_summary.values())

            # 가격 범위 분석
            all_prices = []
            for skus in service_summary.values():
                for sku in skus:
                    if sku.get("base_price_usd", 0) > 0:
                        all_prices.append(sku["base_price_usd"])

            price_stats = {}
            if all_prices:
                price_stats = {
                    "min_price": min(all_prices),
                    "max_price": max(all_prices),
                    "avg_price": sum(all_prices) / len(all_prices),
                    "price_count": len(all_prices),
                }

            return {
                "report_date": datetime.now().isoformat(),
                "filter_applied": service_filter or "None",
                "summary": {
                    "total_services": total_services,
                    "total_skus": total_skus,
                    "price_statistics": price_stats,
                },
                "services": service_summary,
            }

        except Exception as e:
            _LOGGER.error(f"[PricingManager] Error generating pricing report: {str(e)}")
            raise ERROR_INVALID_ARGUMENT(key="pricing_report", value=str(e))

    def _initialize_connectors(self, options: dict, secret_data: dict):
        """커넥터 초기화"""
        # 필수 옵션 확인
        for option in REQUIRED_OPTIONS:
            if option not in options:
                raise ERROR_REQUIRED_PARAMETER(key=option)

        # Pricing 커넥터 초기화
        self.pricing_connector.create_session(options, secret_data, None)

        # Billing 커넥터 초기화 (비교 분석용)
        self.billing_connector.create_session(options, secret_data, None)

        self.pricing_project_id = options["pricing_export_project_id"]
        self.pricing_dataset_id = options["pricing_dataset_id"]

    def _get_billing_data(self, task_options: dict) -> List[Dict]:
        """실제 청구 데이터 조회 (간단한 형태)"""
        # 실제 구현에서는 BigQuery에서 청구 데이터를 조회하여 반환
        # 여기서는 예시 데이터 구조만 제공
        return [
            {
                "service_id": "6F81-5844-456A",
                "service_description": "Compute Engine",
                "sku_id": "2D1C-F75B-ED84",
                "sku_description": "N1 Predefined Instance Core running in Virginia",
                "project_id": task_options.get("project_id", ""),
                "cost": 100.50,
                "usage_amount": 744,  # 시간
                "currency": "USD",
            }
        ]

    def _calculate_tiered_cost(
        self, usage_amount: Decimal, tiered_rates: List[Dict]
    ) -> Decimal:
        """계층별 요금제를 적용한 비용 계산"""
        if not tiered_rates:
            return Decimal(0)

        # 계층을 시작 사용량 기준으로 정렬
        sorted_tiers = sorted(
            tiered_rates, key=lambda x: x.get("start_usage_amount", 0)
        )

        total_cost = Decimal(0)
        remaining_usage = usage_amount

        for i, tier in enumerate(sorted_tiers):
            tier_start = Decimal(str(tier.get("start_usage_amount", 0)))
            tier_price = Decimal(str(tier.get("usd_amount", 0)))
            tier_unit = Decimal(str(tier.get("pricing_unit_quantity", 1)))

            # 다음 계층이 있는 경우 해당 계층의 사용량 범위 계산
            if i + 1 < len(sorted_tiers):
                next_tier_start = Decimal(
                    str(sorted_tiers[i + 1].get("start_usage_amount", 0))
                )
                tier_usage = min(remaining_usage, next_tier_start - tier_start)
            else:
                tier_usage = remaining_usage

            if tier_usage > 0:
                # 해당 계층의 비용 계산
                tier_cost = (tier_usage / tier_unit) * tier_price
                total_cost += tier_cost
                remaining_usage -= tier_usage

            if remaining_usage <= 0:
                break

        return total_cost
