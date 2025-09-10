import logging

import google.oauth2.service_account
import pandas_gbq
from googleapiclient.discovery import build

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.connector import BaseConnector
except ImportError:
    # Mock for local development
    class BaseConnector:
        """Mock BaseConnector for local development"""

        def __init__(self, *args, **kwargs):
            pass

_LOGGER = logging.getLogger("spaceone")

REQUIRED_SECRET_KEYS = ["project_id", "private_key", "token_uri", "client_email"]


class BigqueryConnector(BaseConnector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_id = None
        self.credentials = None
        self.google_client = None

    def create_session(self, options: dict, secret_data: dict, schema: str):
        if not secret_data:
            return

        self.project_id = secret_data.get("project_id")

        # private_key 처리 및 검증
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            try:
                private_key = processed_secret_data["private_key"]

                # 1. 이스케이프된 개행 문자를 실제 개행으로 변환
                if "\\n" in private_key:
                    private_key = private_key.replace("\\n", "\n")

                # 2. private_key 형식 검증 및 정리
                private_key = self._validate_and_clean_private_key(private_key)
                processed_secret_data["private_key"] = private_key

            except Exception as e:
                _LOGGER.error(f"[BigqueryConnector] private_key validation failed: {e}")
                raise ValueError(f"Invalid private_key format: {e}")

        try:
            self.credentials = (
                google.oauth2.service_account.Credentials.from_service_account_info(
                    processed_secret_data
                )
            )
        except Exception as e:
            _LOGGER.error(
                f"[BigqueryConnector] Failed to create service account credentials: {e}"
            )
            # 더 구체적인 오류 정보 제공
            error_msg = f"Service account authentication failed: {str(e)}"
            if "InvalidData" in str(e):
                error_msg += (
                    " - The private_key appears to be corrupted or in wrong format"
                )
            elif "Could not deserialize key data" in str(e):
                error_msg += " - The private_key data is invalid or corrupted"
            elif "invalid_grant" in str(e):
                error_msg += " - The service account does not exist or is disabled"

            raise ValueError(error_msg)
        self.google_client = build("bigquery", "v2", credentials=self.credentials)

    def list_tables(self, billing_export_project_id, dataset_id, **query):
        table_list = []

        query.update({"projectId": billing_export_project_id, "datasetId": dataset_id})

        try:
            request = self.google_client.tables().list(**query)
            while request is not None:
                response = request.execute()
                for table in response.get("tables", []):
                    table_list.append(table)
                request = self.google_client.tables().list_next(
                    previous_request=request, previous_response=response
                )
        except Exception as e:
            _LOGGER.error(
                f"[BigqueryConnector] Failed to list tables in dataset {dataset_id}: {e}"
            )
            # 데이터셋이 존재하지 않거나 접근 권한이 없는 경우 빈 리스트 반환
            return []

        return table_list

    def read_df_from_bigquery(self, query):
        return pandas_gbq.read_gbq(
            query, project_id=self.project_id, credentials=self.credentials
        )

    @staticmethod
    def _validate_and_clean_private_key(private_key: str) -> str:
        """private_key 검증 및 정리"""
        import base64
        import re

        if not private_key:
            raise ValueError("private_key is empty")

        # PEM 형식 확인
        if not private_key.strip().startswith("-----BEGIN"):
            raise ValueError("private_key must be in PEM format")

        # 헤더와 푸터 사이의 base64 내용 추출
        pem_pattern = r"-----BEGIN PRIVATE KEY-----\s*([A-Za-z0-9+/\s=]+)\s*-----END PRIVATE KEY-----"
        match = re.search(pem_pattern, private_key, re.DOTALL)

        if not match:
            raise ValueError("Invalid PEM format: could not find private key content")

        base64_content = match.group(1)
        # 공백 제거
        base64_content = re.sub(r"\s+", "", base64_content)

        # base64 패딩 수정
        missing_padding = len(base64_content) % 4
        if missing_padding:
            base64_content += "=" * (4 - missing_padding)

        # base64 디코딩 테스트 - 실패해도 계속 진행 (키가 손상된 경우)
        try:
            base64.b64decode(base64_content)
        except Exception:
            # 키가 손상되었지만 그대로 반환 (Google API에서 처리하도록)
            return private_key

        # 올바른 PEM 형식으로 재구성
        cleaned_key = "-----BEGIN PRIVATE KEY-----\n"
        # 64자씩 줄바꿈
        for i in range(0, len(base64_content), 64):
            cleaned_key += base64_content[i : i + 64] + "\n"
        cleaned_key += "-----END PRIVATE KEY-----\n"

        return cleaned_key

