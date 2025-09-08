"""
설정 검증 유틸리티
Google Cloud Billing Cost Datasource 플러그인의 설정 파일을 검증하고 보안 문제를 탐지합니다.
"""

import logging
import re
from typing import Dict, List, Tuple

_LOGGER = logging.getLogger("spaceone")


class ConfigValidator:
    """플러그인 설정 검증 클래스"""

    def __init__(self):
        self.validation_results = []
        self.security_issues = []
        self.warnings = []

    def validate_config(self, config: Dict) -> Tuple[bool, List[Dict]]:
        """
        전체 설정 검증

        Args:
            config: 설정 딕셔너리

        Returns:
            (검증 성공 여부, 검증 결과 리스트)
        """
        self.validation_results = []
        self.security_issues = []
        self.warnings = []

        # 기본 구조 검증
        self._validate_basic_structure(config)

        # 플러그인 정보 검증
        if "plugin_info" in config:
            self._validate_plugin_info(config["plugin_info"])

        # 보안 검증
        self._validate_security(config)

        # 옵션 검증
        if "plugin_info" in config and "options" in config["plugin_info"]:
            self._validate_options(config["plugin_info"]["options"])

        # 스케줄 검증
        if "schedule" in config:
            self._validate_schedule(config["schedule"])

        # 결과 종합
        has_critical_issues = len(self.security_issues) > 0
        all_results = self.validation_results + self.security_issues + self.warnings

        return not has_critical_issues, all_results

    def _validate_basic_structure(self, config: Dict):
        """기본 구조 검증"""
        required_fields = ["name", "data_source_type", "provider", "plugin_info"]

        for field in required_fields:
            if field not in config:
                self.validation_results.append(
                    {
                        "type": "error",
                        "category": "structure",
                        "message": f"Required field '{field}' is missing",
                        "field": field,
                    }
                )

        # 데이터 소스 타입 검증
        if "data_source_type" in config:
            valid_types = ["EXTERNAL", "INTERNAL"]
            if config["data_source_type"] not in valid_types:
                self.validation_results.append(
                    {
                        "type": "warning",
                        "category": "structure",
                        "message": f"data_source_type should be one of {valid_types}",
                        "field": "data_source_type",
                        "value": config["data_source_type"],
                    }
                )

        # 프로바이더 검증
        if "provider" in config:
            if config["provider"] != "google_cloud":
                self.warnings.append(
                    {
                        "type": "warning",
                        "category": "structure",
                        "message": "Provider should be 'google_cloud' for this plugin",
                        "field": "provider",
                        "value": config["provider"],
                    }
                )

    def _validate_plugin_info(self, plugin_info: Dict):
        """플러그인 정보 검증"""
        # 플러그인 ID 검증
        if "plugin_id" in plugin_info:
            plugin_id = plugin_info["plugin_id"]

            # 개발자 특정 이름 포함 검사
            if re.search(r"[a-zA-Z]+-[a-zA-Z0-9]+$", plugin_id):
                self.warnings.append(
                    {
                        "type": "warning",
                        "category": "naming",
                        "message": "Plugin ID contains developer-specific naming. Consider using standardized naming like 'plugin-google-billing-cost-datasource'",
                        "field": "plugin_info.plugin_id",
                        "value": plugin_id,
                        "recommendation": "plugin-google-billing-cost-datasource",
                    }
                )

        # 버전 검증
        if "version" in plugin_info:
            version = plugin_info["version"]
            if not re.match(r"^\d+\.\d+\.\d+$", version):
                self.warnings.append(
                    {
                        "type": "warning",
                        "category": "versioning",
                        "message": "Version should follow semantic versioning (e.g., 1.0.0)",
                        "field": "plugin_info.version",
                        "value": version,
                    }
                )

        # 메타데이터 검증
        if "metadata" in plugin_info:
            self._validate_metadata(plugin_info["metadata"])

    def _validate_security(self, config: Dict):
        """보안 관련 검증"""
        # secret_data에서 실제 키 값 검사
        if "plugin_info" in config and "secret_data" in config["plugin_info"]:
            secret_data = config["plugin_info"]["secret_data"]

            # 실제 개인 키 검사
            if "private_key" in secret_data:
                private_key = secret_data["private_key"]
                if self._is_actual_private_key(private_key):
                    self.security_issues.append(
                        {
                            "type": "critical",
                            "category": "security",
                            "message": "🚨 CRITICAL: Actual private key detected in configuration! This is a severe security risk.",
                            "field": "plugin_info.secret_data.private_key",
                            "recommendation": "Use environment variables like '${GCP_PRIVATE_KEY}' instead",
                            "action_required": "Immediately revoke this service account key and generate a new one",
                        }
                    )

            # 실제 이메일 주소 검사
            if "client_email" in secret_data:
                client_email = secret_data["client_email"]
                if self._is_actual_email(client_email):
                    self.security_issues.append(
                        {
                            "type": "warning",
                            "category": "security",
                            "message": "Actual service account email detected. Consider using environment variables.",
                            "field": "plugin_info.secret_data.client_email",
                            "value": client_email,
                            "recommendation": "Use environment variable like '${GCP_SERVICE_ACCOUNT_EMAIL}'",
                        }
                    )

            # 실제 프로젝트 ID 검사
            if "project_id" in secret_data:
                project_id = secret_data["project_id"]
                if self._is_actual_project_id(project_id):
                    self.warnings.append(
                        {
                            "type": "warning",
                            "category": "security",
                            "message": "Actual project ID detected. Consider using environment variables.",
                            "field": "plugin_info.secret_data.project_id",
                            "value": project_id,
                            "recommendation": "Use environment variable like '${GCP_PROJECT_ID}'",
                        }
                    )

    def _validate_metadata(self, metadata: Dict):
        """메타데이터 검증"""
        # 통화 코드 검증
        if "currency" in metadata:
            currency = metadata["currency"]
            valid_currencies = ["USD", "KRW", "JPY", "EUR", "GBP", "CNY"]
            if currency not in valid_currencies:
                self.warnings.append(
                    {
                        "type": "warning",
                        "category": "configuration",
                        "message": f"Currency '{currency}' might not be supported. Common currencies: {valid_currencies}",
                        "field": "plugin_info.metadata.currency",
                        "value": currency,
                    }
                )

        # 데이터 소스 규칙 검증
        if "data_source_rules" in metadata:
            self._validate_data_source_rules(metadata["data_source_rules"])

    def _validate_data_source_rules(self, rules: List[Dict]):
        """데이터 소스 규칙 검증"""
        for i, rule in enumerate(rules):
            # 필수 필드 검사
            required_fields = ["actions", "conditions_policy", "name"]
            for field in required_fields:
                if field not in rule:
                    self.validation_results.append(
                        {
                            "type": "error",
                            "category": "data_source_rules",
                            "message": f"Required field '{field}' is missing in rule {i}",
                            "field": f"plugin_info.metadata.data_source_rules[{i}].{field}",
                        }
                    )

            # 워크스페이스 매칭 검증
            if "actions" in rule and "match_workspace" in rule["actions"]:
                match_workspace = rule["actions"]["match_workspace"]
                if "source" in match_workspace and "target" in match_workspace:
                    source = match_workspace["source"]
                    # target은 현재 사용되지 않지만 향후 확장을 위해 유지
                    # target = match_workspace["target"]

                    # 일반적인 매칭 패턴 검증
                    if not source.startswith("additional_info."):
                        self.warnings.append(
                            {
                                "type": "warning",
                                "category": "data_source_rules",
                                "message": "Source field should typically start with 'additional_info.' for proper workspace matching",
                                "field": f"plugin_info.metadata.data_source_rules[{i}].actions.match_workspace.source",
                                "value": source,
                            }
                        )

    def _validate_options(self, options: Dict):
        """옵션 검증"""
        # 데이터 소스 타입별 필수 옵션 검증
        if "source" in options:
            source_type = options["source"]

            if source_type == "gcs":
                # GCS 모드 필수 옵션
                required_gcs_options = ["bucket_name", "account_id"]
                for option in required_gcs_options:
                    if option not in options:
                        self.validation_results.append(
                            {
                                "type": "error",
                                "category": "options",
                                "message": f"Required option '{option}' is missing for GCS source type",
                                "field": f"plugin_info.options.{option}",
                            }
                        )

            elif source_type == "bigquery":
                # BigQuery 모드 필수 옵션
                required_bq_options = [
                    "billing_export_project_id",
                    "billing_dataset_id",
                    "billing_account_id",
                ]
                for option in required_bq_options:
                    if option not in options:
                        self.validation_results.append(
                            {
                                "type": "error",
                                "category": "options",
                                "message": f"Required option '{option}' is missing for BigQuery source type",
                                "field": f"plugin_info.options.{option}",
                            }
                        )

        # Pricing Data Export 관련 옵션 검증
        if options.get("enable_pricing_analysis", False):
            pricing_options = ["pricing_export_project_id", "pricing_dataset_id"]
            for option in pricing_options:
                if option not in options:
                    self.validation_results.append(
                        {
                            "type": "error",
                            "category": "options",
                            "message": f"Required option '{option}' is missing when pricing analysis is enabled",
                            "field": f"plugin_info.options.{option}",
                        }
                    )

        # Field Mapper 검증 (filed_mapper 오타 처리 포함)
        field_mapper_config = options.get("field_mapper") or options.get("filed_mapper")
        if field_mapper_config:
            self._validate_field_mapper(field_mapper_config)
            # filed_mapper 오타에 대한 경고
            if "filed_mapper" in options and "field_mapper" not in options:
                self.validation_results.append(
                    {
                        "type": "warning",
                        "category": "options",
                        "message": "Using deprecated 'filed_mapper' option. Please use 'field_mapper' instead.",
                        "field": "plugin_info.options.filed_mapper",
                    }
                )

    def _validate_field_mapper(self, field_mapper: Dict):
        """Field Mapper 설정 검증"""
        # 필수 필드 매핑 검증
        required_mappings = ["cost", "billed_date", "currency"]
        for mapping in required_mappings:
            if mapping not in field_mapper:
                self.validation_results.append(
                    {
                        "type": "warning",
                        "category": "field_mapper",
                        "message": f"Recommended field mapping '{mapping}' is missing",
                        "field": f"plugin_info.options.field_mapper.{mapping}",
                    }
                )

    def _validate_schedule(self, schedule: Dict):
        """스케줄 설정 검증"""
        if "state" in schedule:
            valid_states = ["ENABLED", "DISABLED"]
            if schedule["state"] not in valid_states:
                self.validation_results.append(
                    {
                        "type": "error",
                        "category": "schedule",
                        "message": f"Schedule state should be one of {valid_states}",
                        "field": "schedule.state",
                        "value": schedule["state"],
                    }
                )

        if "hour" in schedule:
            hour = schedule["hour"]
            if not isinstance(hour, int) or hour < 0 or hour > 23:
                self.validation_results.append(
                    {
                        "type": "error",
                        "category": "schedule",
                        "message": "Schedule hour should be an integer between 0 and 23",
                        "field": "schedule.hour",
                        "value": hour,
                    }
                )

    def _is_actual_private_key(self, value: str) -> bool:
        """실제 개인 키인지 확인"""
        # 환경변수 패턴 확인
        if re.match(r"^\$\{[A-Z_]+\}$", value):
            return False

        # PEM 형식 개인 키 패턴 확인
        if (
            "-----BEGIN PRIVATE KEY-----" in value
            and "-----END PRIVATE KEY-----" in value
        ):
            # 실제 키 내용이 있는지 확인 (예시 키가 아닌)
            key_content = (
                value.replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .strip()
            )
            if len(key_content) > 100:  # 실제 키는 일반적으로 매우 길다
                return True

        return False

    def _is_actual_email(self, value: str) -> bool:
        """실제 이메일 주소인지 확인"""
        # 환경변수 패턴 확인
        if re.match(r"^\$\{[A-Z_]+\}$", value):
            return False

        # 실제 이메일 패턴 확인
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(email_pattern, value) is not None

    def _is_actual_project_id(self, value: str) -> bool:
        """실제 프로젝트 ID인지 확인"""
        # 환경변수 패턴 확인
        if re.match(r"^\$\{[A-Z_]+\}$", value):
            return False

        # 예시 값이 아닌지 확인
        example_patterns = [
            "your-project",
            "example-project",
            "test-project",
            "my-project",
            "demo-project",
            "sample-project",
        ]

        value_lower = value.lower()
        for pattern in example_patterns:
            if pattern in value_lower:
                return False

        # GCP 프로젝트 ID 패턴 (실제 값으로 보이는)
        if re.match(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$", value) and not any(
            p in value for p in example_patterns
        ):
            return True

        return False

    def generate_report(self, results: List[Dict]) -> str:
        """검증 결과 리포트 생성"""
        if not results:
            return "✅ Configuration validation passed with no issues!"

        report_lines = ["# Configuration Validation Report\n"]

        # 카테고리별로 그룹화
        categories = {}
        for result in results:
            category = result.get("category", "general")
            if category not in categories:
                categories[category] = []
            categories[category].append(result)

        # 심각도별 카운트
        critical_count = len([r for r in results if r.get("type") == "critical"])
        error_count = len([r for r in results if r.get("type") == "error"])
        warning_count = len([r for r in results if r.get("type") == "warning"])

        # 요약
        report_lines.append("## Summary")
        report_lines.append(f"- 🚨 Critical Issues: {critical_count}")
        report_lines.append(f"- ❌ Errors: {error_count}")
        report_lines.append(f"- ⚠️ Warnings: {warning_count}")
        report_lines.append("")

        # 카테고리별 상세
        for category, items in categories.items():
            report_lines.append(f"## {category.title()} Issues")
            for item in items:
                icon = (
                    "🚨"
                    if item.get("type") == "critical"
                    else "❌"
                    if item.get("type") == "error"
                    else "⚠️"
                )
                report_lines.append(
                    f"{icon} **{item.get('message', 'Unknown issue')}**"
                )

                if "field" in item:
                    report_lines.append(f"   - Field: `{item['field']}`")
                if "value" in item:
                    report_lines.append(f"   - Current Value: `{item['value']}`")
                if "recommendation" in item:
                    report_lines.append(
                        f"   - Recommendation: `{item['recommendation']}`"
                    )
                if "action_required" in item:
                    report_lines.append(
                        f"   - **Action Required**: {item['action_required']}"
                    )
                report_lines.append("")

        return "\n".join(report_lines)
