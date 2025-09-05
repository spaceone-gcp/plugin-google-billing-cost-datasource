import logging
from datetime import datetime, timedelta

from spaceone.core.error import (
    ERROR_INVALID_PARAMETER,
    ERROR_INVALID_PARAMETER_TYPE,
    ERROR_REQUIRED_PARAMETER,
)
from spaceone.core.manager import BaseManager

from ..conf.cost_conf import (
    BIGQUERY_TABLE_PREFIX,
    DATA_SOURCE_TYPES,
    DEFAULT_DATA_SOURCE_TYPE,
)
from ..connector.bigquery_connector import BigqueryConnector
from ..connector.http_file_connector import HttpFileConnector

_LOGGER = logging.getLogger("spaceone")

REQUIRED_OPTIONS = [
    "billing_export_project_id",
    "billing_dataset_id",
    "billing_account_id",
]


class JobManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery_connector = BigqueryConnector()
        self.http_file_connector = HttpFileConnector()  # 추가
        self.billing_export_project_id = None
        self.billing_dataset = None
        self.billing_table = None
        self.billing_account_id = None

    def get_tasks(
        self,
        domain_id: str,
        options: dict,
        secret_data: dict,
        schema: str = None,
        start: str = None,
        last_synchronized_at: datetime = None,
    ) -> dict:
        """데이터 소스 타입에 따라 작업 생성 분기"""

        data_source_type = self._get_data_source_type(options)

        _LOGGER.debug(f"[get_tasks] data_source_type: {data_source_type}")
        _LOGGER.debug(f"[get_tasks] options keys: {list(options.keys())}")

        # HTTP 파일 모드 강제 실행 (source=gcs인 경우)
        if "source" in options and options["source"] == "gcs":
            _LOGGER.debug("[get_tasks] Executing HTTP file mode for source=gcs")
            return self._get_http_file_tasks(
                domain_id, options, secret_data, schema, start, last_synchronized_at
            )

        if data_source_type == DATA_SOURCE_TYPES["http_file"]:
            return self._get_http_file_tasks(
                domain_id, options, secret_data, schema, start, last_synchronized_at
            )
        else:
            return self._get_bigquery_tasks(
                domain_id, options, secret_data, schema, start, last_synchronized_at
            )

    def _get_bigquery_tasks(
        self,
        domain_id: str,
        options: dict,
        secret_data: dict,
        schema: str = None,
        start: str = None,
        last_synchronized_at: datetime = None,
    ) -> dict:
        """BigQuery 기반 작업 생성 (기존 로직)"""

        self.bigquery_connector.create_session(options, secret_data, schema)
        self._check_options(options)

        self.billing_export_project_id = options["billing_export_project_id"]
        self.billing_dataset = self._extract_dataset_id(options["billing_dataset_id"])
        self.billing_account_id = options["billing_account_id"]

        self.billing_table = (
            f"{BIGQUERY_TABLE_PREFIX}_{self.billing_account_id.replace('-', '_')}"
        )
        self._validate_table_exists()

        tasks = []
        changed = []

        start_month = self._get_start_month(start, last_synchronized_at)

        query = self._create_google_sql(start_month)
        response_stream = self.bigquery_connector.read_df_from_bigquery(query)

        for index, row in response_stream.iterrows():
            tasks.append(
                {
                    "task_options": {
                        "start": start_month,
                        "project_id": row.id,
                        "billing_export_project_id": self.billing_export_project_id,
                        "billing_dataset_id": self.billing_dataset,
                        "billing_account_id": self.billing_account_id,
                        "data_source_type": DATA_SOURCE_TYPES[
                            "bigquery"
                        ],  # 명시적 설정
                    }
                }
            )

        changed.append({"start": start_month})

        return {"tasks": tasks, "changed": changed}

    def _get_start_month(self, start, last_synchronized_at=None):
        if start:
            start_time: datetime = self._parse_start_time(start)
        elif last_synchronized_at:
            start_time: datetime = last_synchronized_at - timedelta(days=7)
            start_time = start_time.replace(day=1)
        else:
            start_time: datetime = datetime.utcnow() - timedelta(days=365)
            start_time = start_time.replace(day=1)

        start_time = start_time.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        return start_time.strftime("%Y-%m")

    @staticmethod
    def _parse_start_time(start_str):
        date_format = "%Y-%m"

        try:
            return datetime.strptime(start_str, date_format)
        except Exception:
            raise ERROR_INVALID_PARAMETER_TYPE(key="start", type=date_format)

    @staticmethod
    def _check_options(options):
        missing_keys = [key for key in REQUIRED_OPTIONS if key not in options]
        if missing_keys:
            for key in missing_keys:
                raise ERROR_REQUIRED_PARAMETER(key=f"options.{key}")

    def _validate_table_exists(self):
        bigquery_tables_info = self.bigquery_connector.list_tables(
            self.billing_export_project_id, self.billing_dataset
        )

        # 데이터셋이 존재하지 않거나 접근할 수 없는 경우
        if not bigquery_tables_info:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"Dataset '{self.billing_dataset}' not found in project '{self.billing_export_project_id}' or access denied"
            )

        bigquery_table_names = [
            table_info["tableReference"]["tableId"]
            for table_info in bigquery_tables_info
        ]

        if self.billing_table not in bigquery_table_names:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"Table '{self.billing_table}' not found in dataset. Available tables: {bigquery_table_names}"
            )

    def _create_google_sql(self, start):
        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{start}-01')
        """

        query = f"""
            SELECT
            distinct project.id
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            ;
        """
        return query

    def _get_http_file_tasks(
        self,
        domain_id: str,
        options: dict,
        secret_data: dict,
        schema: str = None,
        start: str = None,
        last_synchronized_at: datetime = None,
    ) -> dict:
        """HTTP 파일 기반 작업 생성 (신규)"""

        _LOGGER.debug(f"[_get_http_file_tasks] Called with start={start}")

        try:
            # HTTP 파일 커넥터 세션 생성
            self.http_file_connector.create_session(options, secret_data, schema)

            # HTTP 파일 설정 검증
            self._check_http_file_options(options)

            tasks = []
            changed = []

            # 파일 목록 또는 단일 파일 처리
            if "file_list" in options:
                # 여러 파일 처리
                file_list = options["file_list"]
                for file_info in file_list:
                    bucket_name = file_info["bucket_name"]
                    file_path = file_info["file_path"]

                    task_options = {
                        "bucket_name": bucket_name,
                        "file_path": file_path,
                        "data_source_type": DATA_SOURCE_TYPES["http_file"],
                        "field_mapping": options.get("field_mapping", {}),
                        "parsing_options": file_info.get("parsing_options", {}),
                    }

                    tasks.append({"task_options": task_options})

            elif "bucket_name" in options:
                # 버킷에서 파일 목록 자동 생성
                bucket_name = options["bucket_name"]
                file_pattern = options.get("file_pattern")

                files = self.http_file_connector.list_files(bucket_name, file_pattern)

                for file_info in files:
                    task_options = {
                        "bucket_name": bucket_name,
                        "file_path": file_info["name"],
                        "data_source_type": DATA_SOURCE_TYPES["http_file"],
                        "field_mapping": options.get("field_mapping", {}),
                        "parsing_options": options.get("parsing_options", {}),
                    }

                    tasks.append({"task_options": task_options})

            else:
                # 단일 파일 처리
                bucket_name = options.get("bucket_name")
                file_path = options.get("file_path")

                if not bucket_name or not file_path:
                    raise ERROR_REQUIRED_PARAMETER(
                        key="Either 'file_list', 'bucket_name', or both 'bucket_name' and 'file_path' must be provided"
                    )

                task_options = {
                    "bucket_name": bucket_name,
                    "file_path": file_path,
                    "data_source_type": DATA_SOURCE_TYPES["http_file"],
                    "field_mapping": options.get("field_mapping", {}),
                    "parsing_options": options.get("parsing_options", {}),
                }

                tasks.append({"task_options": task_options})

            # 변경 사항 기록 - start 필드 포함 (TasksResponse 스키마 요구사항)
            current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            start_value = (
                start or current_time
            )  # start 파라미터가 없으면 현재 시간 사용

            changed_item = {
                "start": start_value,
                "timestamp": current_time,
                "file_count": len(tasks),
            }
            changed.append(changed_item)

            _LOGGER.debug(
                f"[_get_http_file_tasks] created changed item: {changed_item}"
            )
            _LOGGER.debug(
                f"[_get_http_file_tasks] returning tasks count: {len(tasks)}, changed count: {len(changed)}"
            )

            _LOGGER.info(
                f"[get_http_file_tasks] Generated {len(tasks)} HTTP file tasks"
            )

            return {"tasks": tasks, "changed": changed}

        except Exception as e:
            _LOGGER.error(
                f"[get_http_file_tasks] Failed to generate HTTP file tasks: {e}"
            )
            raise e

    def _get_data_source_type(self, options: dict) -> str:
        """데이터 소스 타입 결정"""
        # 1. 명시적 data_source_type 확인
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            _LOGGER.debug(
                f"[_get_data_source_type] Using explicit data_source_type: {data_source_type}"
            )
            return data_source_type

        # 2. 레거시 'source' 파라미터 지원
        source = options.get("source")
        if source == "gcs":
            _LOGGER.debug("[_get_data_source_type] Using source=gcs -> http_file")
            return DATA_SOURCE_TYPES["http_file"]
        elif source == "bigquery":
            _LOGGER.debug("[_get_data_source_type] Using source=bigquery -> bigquery")
            return DATA_SOURCE_TYPES["bigquery"]

        # 3. 파라미터 기반 자동 감지
        # HTTP 파일 모드 감지: bucket_name이 있고 BigQuery 필수 파라미터가 없는 경우
        has_bucket = "bucket_name" in options
        has_bigquery_params = all(key in options for key in REQUIRED_OPTIONS)

        _LOGGER.debug(
            f"[_get_data_source_type] has_bucket={has_bucket}, has_bigquery_params={has_bigquery_params}"
        )

        if has_bucket and not has_bigquery_params:
            _LOGGER.debug("[_get_data_source_type] Auto-detected http_file mode")
            return DATA_SOURCE_TYPES["http_file"]
        elif has_bigquery_params:
            _LOGGER.debug("[_get_data_source_type] Auto-detected bigquery mode")
            return DATA_SOURCE_TYPES["bigquery"]

        # 4. 기본값 반환 (하위 호환성)
        _LOGGER.debug(
            f"[_get_data_source_type] Using default: {DEFAULT_DATA_SOURCE_TYPE}"
        )
        return DEFAULT_DATA_SOURCE_TYPE

    def _check_http_file_options(self, options: dict):
        """HTTP 파일 처리에 필요한 options 검증"""
        # 최소 하나의 파일 지정 방법이 있어야 함
        has_file_list = "file_list" in options
        has_bucket = "bucket_name" in options

        if not has_file_list and not has_bucket:
            raise ERROR_REQUIRED_PARAMETER(
                key="Either 'file_list' or 'bucket_name' must be provided in options"
            )

        # file_list 검증
        if has_file_list:
            file_list = options["file_list"]
            if not isinstance(file_list, list) or len(file_list) == 0:
                raise ERROR_INVALID_PARAMETER(
                    key="options.file_list must be a non-empty list"
                )

            for i, file_info in enumerate(file_list):
                if not isinstance(file_info, dict):
                    raise ERROR_INVALID_PARAMETER(
                        key=f"options.file_list[{i}] must be a dictionary"
                    )

                if "bucket_name" not in file_info or "file_path" not in file_info:
                    raise ERROR_REQUIRED_PARAMETER(
                        key=f"options.file_list[{i}] must contain 'bucket_name' and 'file_path'"
                    )

        # bucket_name 검증
        if has_bucket:
            bucket_name = options["bucket_name"]
            if not bucket_name or bucket_name.strip() == "":
                raise ERROR_INVALID_PARAMETER(key="options.bucket_name")

    @staticmethod
    def _extract_dataset_id(billing_dataset_id: str) -> str:
        """
        billing_dataset_id에서 실제 데이터셋 ID만 추출합니다.

        Args:
            billing_dataset_id: 'project.dataset' 또는 'dataset' 형식의 문자열

        Returns:
            str: 데이터셋 ID만 포함된 문자열
        """
        if "." in billing_dataset_id:
            # 'project.dataset' 형식인 경우 dataset 부분만 반환
            return billing_dataset_id.split(".")[-1]
        # 이미 dataset만 있는 경우 그대로 반환
        return billing_dataset_id
