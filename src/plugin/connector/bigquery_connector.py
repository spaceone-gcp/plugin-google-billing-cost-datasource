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

        # private_key 기본 처리만 수행 (검증 제거)
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            # 이스케이프된 개행 문자를 실제 개행으로 변환
            if "\\n" in processed_secret_data["private_key"]:
                processed_secret_data["private_key"] = processed_secret_data[
                    "private_key"
                ].replace("\\n", "\n")

        # Google API 인증 정보로 직접 생성 (상세 오류 처리 제거)
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                processed_secret_data
            )
        )
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
