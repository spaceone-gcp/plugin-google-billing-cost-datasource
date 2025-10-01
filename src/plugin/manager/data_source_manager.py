"""Google Cloud Billing 데이터 소스 매니저 모듈.

SpaceONE UI에서 additional_info 필드들의 표시 방식과 그룹화 옵션을 정의하는 매니저입니다.
"""

import copy
import logging
from typing import Optional

from spaceone.core.manager import BaseManager

_LOGGER = logging.getLogger(__name__)

# Google Cloud Billing 데이터의 additional_info 필드 기본 메타데이터 정의
# SpaceONE UI에서 additional_info 필드들의 표시 방식과 그룹화 옵션을 정의합니다.
# Google Cloud Billing 데이터의 주요 필드들에 대한 메타데이터를 제공하여
# 사용자가 데이터를 더 효과적으로 분석할 수 있도록 지원합니다.

_DEFAULT_DATA_SOURCE_RULES = [
    {
        "actions": {
            "match_workspace": {
                "source": "additional_info.Project ID",
                "target": "data.project_id",
            }
        },
        "options": {"stop_processing": True},
        "name": "match_workspace",
        "conditions_policy": "ALWAYS",
        "resource_group": "DOMAIN",
    }
]

# 조건부_additional_info_필터링_PRD.md 문서 기준 33개 필드만 포함
_DEFAULT_METADATA_ADDITIONAL_INFO = {
    # 필수 고정 항목 (6개) - SpaceONE UI 기준 (항상 visible: True)
    "Project": {"name": "Project", "visible": True},
    "Provider": {"name": "Provider", "visible": True},
    "Service Account": {"name": "Service Account", "visible": True},
    "Product": {"name": "Product", "visible": True},
    "Region": {"name": "Region", "visible": True},
    "Usage Type": {"name": "Usage Type", "visible": True},
    # 프로젝트 계층 카테고리 (Project Hierarchy) - PRD 2.1.2 기준
    "Project Name": {"name": "Project Name", "visible": False},
    "Project Number": {"name": "Project Number", "visible": False},
    "Ancestry Numbers": {"name": "Ancestry Numbers", "visible": False},
    # 위치 정보 카테고리 (Location Data) - PRD 2.1.2 기준
    "Location Country": {"name": "Location Country", "visible": False},
    "Location Region": {"name": "Location Region", "visible": False},
    "Location Zone": {"name": "Location Zone", "visible": False},
    "Location Location": {"name": "Location Location", "visible": False},
    # 사용량 분석 카테고리 (Usage Analysis) - PRD 2.1.2 기준
    "Usage Unit": {"name": "Usage Unit", "visible": False},
    # 서비스 메타데이터 카테고리 (Service Metadata) - PRD 2.1.2 기준
    "Service Description": {"name": "Service Description", "visible": False},
    "Service ID": {"name": "Service ID", "visible": False},
    "SKU Description": {"name": "SKU Description", "visible": False},
    "SKU ID": {"name": "SKU ID", "visible": False},
    "Consumption Model Description": {
        "name": "Consumption Model Description",
        "visible": False,
    },
    "Consumption Model ID": {"name": "Consumption Model ID", "visible": False},
    # 가격 정보 카테고리 (Pricing Information) - PRD 2.1.2 기준
    "Price Unit": {"name": "Price Unit", "visible": False},
    "Pricing Unit": {"name": "Pricing Unit", "visible": False},
    # 청구 조정 카테고리 (Billing Adjustments) - PRD 2.1.2 기준
    "Adjustment Info Description": {
        "name": "Adjustment Info Description",
        "visible": False,
    },
    "Adjustment Info ID": {"name": "Adjustment Info ID", "visible": False},
    "Adjustment Info Mode": {"name": "Adjustment Info Mode", "visible": False},
    "Adjustment Info Type": {"name": "Adjustment Info Type", "visible": False},
    # 비용 분석 카테고리 (Cost Analysis) - PRD 2.1.2 기준
    "Credits Detail": {"name": "Credits Detail", "visible": False},
    # 기타 필수 필드들 (PRD 구현 로직에서 언급된 필드들)
    "Billing Account ID": {"name": "Billing Account ID", "visible": False},
    "Invoice Month": {"name": "Invoice Month", "visible": False},
    "Currency": {"name": "Currency", "visible": False},
    "Transaction Type": {
        "name": "Transaction Type",
        "visible": False,
        "enums": ["charge", "refund", "tax", "rounding_error"],
    },
}


class DataSourceManager(BaseManager):
    """Google Cloud Billing 데이터 소스 관리 매니저.

    SpaceONE 플러그인의 데이터 소스 초기화 및 메타데이터 관리를 담당합니다.
    """

    @staticmethod
    def init_response(options: dict, domain_id: Optional[str] = None) -> dict:
        """데이터 소스 초기화 응답을 생성합니다.

        Args:
            options: 플러그인 옵션 딕셔너리
            domain_id: 도메인 ID (선택사항)

        Returns:
            dict: 플러그인 메타데이터가 포함된 초기화 응답
        """
        plugin_metadata = {
            "data_source_rules": _DEFAULT_DATA_SOURCE_RULES,
            "supported_secret_types": ["MANUAL"],
            "currency": options.get("currency", "USD"),
            "collect_resource_id": True,
            "use_account_routing": False,
            "exclude_license_cost": False,
            "include_credit_cost": False,
            "additional_info": copy.deepcopy(_DEFAULT_METADATA_ADDITIONAL_INFO),
        }

        return {"metadata": plugin_metadata}

    @staticmethod
    def init_cost_data_info() -> dict:
        """비용 데이터의 additional_info 필드에 대한 메타데이터 정보를 반환합니다.

        Returns:
            dict: additional_info 필드들의 메타데이터

        """
        return _DEFAULT_METADATA_ADDITIONAL_INFO
