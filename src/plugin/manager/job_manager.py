import logging
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
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
from ..connector.gcs_connector import GcsConnector
from ..utils.error_handler import (
    GracefulErrorHandler,
    create_empty_job_response,
    validate_job_response,
)

_LOGGER = logging.getLogger("spaceone")

REQUIRED_OPTIONS = [
    "billing_export_project_id",
    "billing_dataset_id",
    "billing_account_id",
]


class JobManager(BaseManager):
    # 활성 프로젝트 캐시 (클래스 변수)
    _active_projects_cache = {
        "data": [],
        "last_updated": None,
        "cache_duration_minutes": 30,  # 30분 캐시
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery_connector = BigqueryConnector()
        self.gcs_connector = GcsConnector()

        # 인스턴스 변수 초기화
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
        # filed_mapper 오타 사용 시 경고 (하위 호환성은 유지하지만 경고)
        if "filed_mapper" in options and "field_mapper" not in options:
            _LOGGER.warning(
                "Using deprecated 'filed_mapper' option. Please use 'field_mapper' instead."
            )

        data_source_type = self._get_data_source_type(options)

        # 에러 핸들러 초기화
        error_handler = GracefulErrorHandler(
            f"JobManager.get_tasks[{data_source_type}]"
        )

        # 데이터 소스 타입별 작업 생성 분기
        try:
            if data_source_type == DATA_SOURCE_TYPES["gcs"]:
                result = self._get_http_file_tasks(
                    domain_id,
                    options,
                    secret_data,
                    schema,
                    start,
                    last_synchronized_at,
                    data_source_type,
                )
            elif data_source_type == DATA_SOURCE_TYPES["http"]:
                result = self._get_http_file_tasks(
                    domain_id,
                    options,
                    secret_data,
                    schema,
                    start,
                    last_synchronized_at,
                    data_source_type,
                )
            elif data_source_type == DATA_SOURCE_TYPES["bigquery"]:
                result = self._get_bigquery_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )
            else:
                _LOGGER.warning(
                    f"Unknown data_source_type: {data_source_type}, defaulting to BigQuery"
                )
                result = self._get_bigquery_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )

            # 결과 검증
            if not validate_job_response(result):
                _LOGGER.warning("Invalid response detected, creating fallback response")
                result = create_empty_job_response("Invalid response structure")

            # 작업 생성 완료 로깅
            task_count = len(result.get("tasks", []))
            _LOGGER.info(f"Task generation completed - {task_count} tasks created")

            return result

        except Exception as e:
            # 에러 핸들러를 통한 우아한 에러 처리
            if error_handler.handle_error(e, "Task generation"):
                _LOGGER.warning(f"Task generation failed: {e}")
                return create_empty_job_response(
                    f"Task generation failed: {str(e)[:100]}"
                )
            else:
                _LOGGER.error(f"Critical task generation failure: {e}")
                raise

    def _get_bigquery_tasks(
        self,
        domain_id: str,
        options: dict,
        secret_data: dict,
        schema: str = None,
        start: str = None,
        last_synchronized_at: datetime = None,
    ) -> dict:
        """BigQuery 기반 작업 생성"""
        try:
            # BigQuery 커넥터 세션 생성
            self.bigquery_connector.create_session(options, secret_data, schema)

            # 옵션 검증
            self._check_options(options)

            # 빌링 정보 설정
            self.billing_export_project_id = options["billing_export_project_id"]
            self.billing_dataset = self._extract_dataset_id(
                options["billing_dataset_id"]
            )
            self.billing_account_id = options["billing_account_id"]

            # 빌링 테이블 이름 생성
            self.billing_table = (
                f"{BIGQUERY_TABLE_PREFIX}_{self.billing_account_id.replace('-', '_')}"
            )

            # 테이블 존재 검증
            self._validate_table_exists()

            # 작업 생성 초기화
            tasks = []
            changed = []

            # 시작 월 계산
            start_month = self._get_start_month(start, last_synchronized_at)

            # BigQuery 쿼리 생성 및 실행
            query = self._create_google_sql(start_month)
            _LOGGER.info(f"Querying active projects from {start_month}")
            _LOGGER.info(f"[JobManager] Executing BigQuery SQL:\n{query}")

            response_stream = self.bigquery_connector.read_df_from_bigquery(query)
            project_count = len(response_stream)
            _LOGGER.info(f"Found {project_count} active projects")

            # 프로젝트별 작업 생성
            if project_count == 0:
                _LOGGER.warning(
                    "No active projects found - check billing data and filters"
                )

            # 프로젝트별 작업 생성
            for index, row in response_stream.iterrows():
                project_id = row.id

                task_options = {
                    "start": start_month,
                    "project_id": project_id,
                    "billing_export_project_id": self.billing_export_project_id,
                    "billing_dataset_id": self.billing_dataset,
                    "billing_account_id": self.billing_account_id,
                    "data_source_type": DATA_SOURCE_TYPES["bigquery"],
                }

                tasks.append({"task_options": task_options})

            # SpaceONE Job 스키마의 start 필드 길이 제한 준수 (YYYY-MM 형식, 7자)
            changed_item = {"start": start_month}
            changed.append(changed_item)

            return {"tasks": tasks, "changed": changed}

        except Exception as e:
            _LOGGER.error(f"BigQuery task generation failed: {e}")
            raise

    def _get_start_month(self, start, last_synchronized_at=None):
        """
        비용 데이터 수집의 시작 월을 결정합니다.

        우선순위:
        1. start 파라미터가 있으면 start를 기준으로
        2. start가 없고 last_synchronized_at가 있으면 last_synchronized_at에서 10일 이전
        3. 둘 다 없으면 현재에서 12개월 이전

        Args:
            start: 사용자 지정 시작 시점 (YYYY-MM 형식)
            last_synchronized_at: 마지막 동기화 시점

        Returns:
            str: 시작 월 (YYYY-MM 형식)
        """
        if start:
            # 1순위: 사용자 지정 start 시점 사용
            start_time: datetime = self._parse_start_time(start)
        elif last_synchronized_at:
            # 2순위: 마지막 동기화에서 10일 이전 (데이터 누락 방지)
            start_time: datetime = last_synchronized_at - timedelta(days=10)
        else:
            # 3순위: 현재에서 12개월 이전 (최초 연동)
            current_utc = datetime.utcnow()
            start_time: datetime = current_utc - relativedelta(months=12)
            start_time = start_time.replace(day=1)

        # 시간 정보 정규화 (월 단위로 처리하기 위해)
        start_time = start_time.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        result = start_time.strftime("%Y-%m")
        return result

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
        """BigQuery SQL 쿼리 생성"""

        # 날짜 범위 검증
        validated_start = self._validate_and_fix_date_range(start)

        # PARTITIONDATE 범위 계산
        partition_start, partition_end = self._calculate_partition_date_range(
            validated_start
        )

        # 스마트 프리필터링: 금액이 0이 아닌 프로젝트만 조회
        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{validated_start}-01')
          AND _PARTITIONDATE BETWEEN '{partition_start}' AND '{partition_end}'
          AND cost > 0  -- 금액이 0이 아닌 데이터만
          AND project.id IS NOT NULL  -- NULL 프로젝트 제외
        """

        query = f"""
            SELECT
            distinct project.id
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            ORDER BY project.id  -- 일관된 순서 보장
            ;
        """

        return query

    def _is_cache_valid(self) -> bool:
        """캐시가 유효한지 확인"""
        if not self._active_projects_cache["last_updated"]:
            return False

        from datetime import timedelta

        cache_age = datetime.now() - self._active_projects_cache["last_updated"]
        max_age = timedelta(
            minutes=self._active_projects_cache["cache_duration_minutes"]
        )

        return cache_age < max_age

    def _update_cache(self, projects: list):
        """캐시 업데이트"""
        self._active_projects_cache["data"] = projects
        self._active_projects_cache["last_updated"] = datetime.now()

    def _get_http_file_tasks(
        self,
        domain_id: str,
        options: dict,
        secret_data: dict,
        schema: str = None,
        start: str = None,
        last_synchronized_at: datetime = None,
        data_source_type: str = None,
    ) -> dict:
        """HTTP 파일 기반 작업 생성"""
        # data_source_type 기본값 설정 (하위 호환성)
        if data_source_type is None:
            data_source_type = DATA_SOURCE_TYPES["http"]

        try:
            # HTTP 파일 커넥터 세션 생성 - 재시도 로직
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    self.gcs_connector.create_session(options, secret_data, schema)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        _LOGGER.error(
                            f"Failed to create session after {max_retries} attempts: {e}"
                        )
                        raise
                    import time

                    time.sleep(1)  # 1초 대기 후 재시도

            # HTTP 파일 설정 검증
            self._check_http_file_options(options)

            # 작업 생성 초기화
            tasks = []
            changed = []

            # 파일 목록 또는 단일 파일 처리
            if "file_list" in options:
                # 여러 파일 처리
                file_list = options["file_list"]

                for index, file_info in enumerate(file_list):
                    bucket_name = file_info["bucket_name"]
                    file_path = file_info["file_path"]

                    task_options = {
                        "bucket_name": bucket_name,
                        "file_path": file_path,
                        "data_source_type": data_source_type,
                        "field_mapper": options.get("field_mapper", {}),
                        "parsing_options": file_info.get("parsing_options", {}),
                    }

                    tasks.append({"task_options": task_options})

                _LOGGER.info(f"Created {len(tasks)} tasks from file list")

            elif "bucket_name" in options:
                # 버킷에서 파일 목록 자동 생성
                bucket_name = options["bucket_name"]
                project_id = options.get("project_id")

                # start 파라미터가 있고 project_id가 지정된 경우 직접 경로 접근 사용
                if start and project_id:
                    validated_start = self._validate_and_fix_date_range(start)
                    year, month = validated_start.split("-")

                    # 직접 경로로 파일 목록 조회
                    try:
                        files = self.gcs_connector.list_gcs_files_by_path(
                            bucket_name, project_id, year, month
                        )
                        _LOGGER.info(
                            f"Found {len(files)} files in {project_id}/{year}/{month}/"
                        )
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to list files from {bucket_name}/{project_id}/{year}/{month}/: {e}"
                        )
                        files = []
                else:
                    # 기존 방식: 전체 파일 목록 조회 후 필터링
                    file_pattern = options.get("file_pattern")

                    # 파일 목록 조회
                    try:
                        files = self.gcs_connector.list_gcs_files(
                            bucket_name, file_pattern
                        )
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to list files from bucket {bucket_name}: {e}"
                        )
                        files = []

                    # start 파라미터 기반 파일 필터링 (PARTITIONDATE 유사한 확장 범위 적용)
                    original_count = len(files)
                    if start:
                        validated_start = self._validate_and_fix_date_range(start)
                        # PARTITIONDATE 유사한 확장 범위 계산
                        partition_start, partition_end = (
                            self._calculate_partition_date_range(validated_start)
                        )
                        files = self._filter_files_by_date_range(
                            files, partition_start, partition_end, project_id
                        )
                    elif project_id:
                        files = self._filter_files_by_project_id(files, project_id)

                    if original_count != len(files):
                        _LOGGER.info(f"Filtered to {len(files)}/{original_count} files")

                # 파일별 작업 생성
                if not files:
                    _LOGGER.warning(f"No files found in bucket {bucket_name}")

                for index, file_info in enumerate(files):
                    try:
                        file_path = file_info["name"]
                        task_options = {
                            "bucket_name": bucket_name,
                            "file_path": file_path,
                            "data_source_type": data_source_type,
                            "field_mapper": options.get("field_mapper", {}),
                            "parsing_options": options.get("parsing_options", {}),
                        }
                        tasks.append({"task_options": task_options})
                    except Exception as e:
                        _LOGGER.error(
                            f"Failed to create task for file {index + 1}: {e}"
                        )
                        continue

                _LOGGER.info(f"Created {len(tasks)} tasks from bucket files")

            else:
                # 단일 파일 처리
                bucket_name = options.get("bucket_name")
                file_path = options.get("file_path")

                if not bucket_name or not file_path:
                    error_msg = "Either 'file_list', 'bucket_name', or both 'bucket_name' and 'file_path' must be provided"
                    _LOGGER.error(error_msg)
                    raise ERROR_REQUIRED_PARAMETER(key=error_msg)

                task_options = {
                    "bucket_name": bucket_name,
                    "file_path": file_path,
                    "data_source_type": data_source_type,
                    "field_mapper": options.get("field_mapper", {}),
                    "parsing_options": options.get("parsing_options", {}),
                }

                tasks.append({"task_options": task_options})
                _LOGGER.info("Created 1 task for single file")

            # 변경 사항 기록
            current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            start_month = self._get_start_month(start, last_synchronized_at)

            if start:
                start_value = self._validate_and_fix_date_range(start)
            else:
                start_value = start_month

            changed_item = {
                "start": start_value,
                "timestamp": current_time,
                "file_count": len(tasks),
            }
            changed.append(changed_item)

            if not tasks:
                _LOGGER.warning(
                    "No tasks were created - check access or file availability"
                )

            return {"tasks": tasks, "changed": changed}

        except Exception as e:
            _LOGGER.error(f"HTTP file task generation failed: {e}")
            return {"tasks": [], "changed": []}

    def _get_data_source_type(self, options: dict) -> str:
        """데이터 소스 타입 결정"""
        # 1. 명시적 data_source_type 확인
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            return data_source_type
        elif data_source_type:
            _LOGGER.warning(f"Invalid data_source_type: {data_source_type}")

        # 2. 'source' 파라미터 지원
        source = options.get("source")
        if source == "bigquery":
            return DATA_SOURCE_TYPES["bigquery"]
        elif source == "gcs":
            return DATA_SOURCE_TYPES["gcs"]
        elif source == "http":
            return DATA_SOURCE_TYPES["http"]
        elif source:
            _LOGGER.warning(f"Unknown source parameter: {source}")

        # 3. 파라미터 기반 자동 감지
        has_bucket = "bucket_name" in options
        has_bigquery_params = all(key in options for key in REQUIRED_OPTIONS)

        if has_bucket and not has_bigquery_params:
            return DATA_SOURCE_TYPES["gcs"]
        elif has_bigquery_params:
            return DATA_SOURCE_TYPES["bigquery"]
        elif has_bucket and has_bigquery_params:
            _LOGGER.warning(
                "Both bucket_name and BigQuery params present, preferring BigQuery"
            )
            return DATA_SOURCE_TYPES["bigquery"]

        # 4. 기본값 반환
        _LOGGER.warning(
            f"No clear data source type detected, using default: {DEFAULT_DATA_SOURCE_TYPE}"
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
    def _filter_files_by_project_id(files: list[dict], project_id: str) -> list[dict]:
        """project_id를 기반으로 파일 목록 필터링

        Args:
            files: 파일 목록 (각 파일은 'name' 키를 가진 딕셔너리)
            project_id: 필터링할 프로젝트 ID

        Returns:
            List[Dict]: 필터링된 파일 목록
        """
        if not project_id:
            return files

        filtered_files = []

        for file_info in files:
            file_path = file_info.get("name", "")
            path_parts = file_path.split("/")

            if len(path_parts) < 4:  # 최소 4개 부분이 필요 (project/year/month/file)
                continue

            file_project_id = path_parts[0]

            # 프로젝트 ID 매칭 검증
            if file_project_id == project_id:
                filtered_files.append(file_info)

        return filtered_files

    @staticmethod
    def _filter_files_by_date(
        files: list[dict], start_date: str, project_id: str = None
    ) -> list[dict]:
        """start_date와 project_id를 기반으로 파일 목록 필터링

        Note: 이 함수는 레거시 호환성을 위해 유지됩니다.
        새로운 구현에서는 list_files_by_path()를 통한 직접 경로 접근을 권장합니다.

        Args:
            files: 파일 목록 (각 파일은 'name' 키를 가진 딕셔너리)
            start_date: YYYY-MM 형식의 시작 날짜
            project_id: 필터링할 프로젝트 ID (선택사항)

        Returns:
            List[Dict]: 필터링된 파일 목록
        """
        try:
            # YYYY-MM 형식에서 년도와 월 추출
            year, month = start_date.split("-")
            target_year = year
            target_month = month.zfill(2)  # 01, 02, ... 형식으로 변환

            filtered_files = []

            for file_info in files:
                file_path = file_info.get("name", "")

                # 파일 경로 구조 분석: project_id/year/month/filename
                # 예: mkkang-project/2025/09/billing_data_202509-000000000002.parquet
                path_parts = file_path.split("/")

                if (
                    len(path_parts) < 4
                ):  # 최소 4개 부분이 필요 (project/year/month/file)
                    continue

                file_project_id = path_parts[0]
                file_year = path_parts[1]
                file_month = path_parts[2]

                # 월 형식 검증: 정확히 2자리 숫자여야 함
                if not (file_month.isdigit() and len(file_month) == 2):
                    continue

                # 년도 형식 검증: 정확히 4자리 숫자여야 함
                if not (file_year.isdigit() and len(file_year) == 4):
                    continue

                # 날짜 매칭 검증
                date_match = file_year == target_year and file_month == target_month

                # 프로젝트 ID 매칭 검증 (선택사항)
                project_match = True  # 기본값: 프로젝트 필터링 없음
                if project_id:
                    project_match = file_project_id == project_id

                # 날짜와 프로젝트 ID 모두 매치되는 경우만 포함
                if date_match and project_match:
                    filtered_files.append(file_info)
            return filtered_files

        except Exception as e:
            _LOGGER.error(f"Failed to filter files for {start_date}: {e}")
            return files

    @staticmethod
    def _filter_files_by_date_range(
        files: list[dict], start_date: str, end_date: str, project_id: str = None
    ) -> list[dict]:
        """날짜 범위를 기반으로 파일 목록 필터링 (PARTITIONDATE 유사 기능)

        Args:
            files: 파일 목록 (각 파일은 'name' 키를 가진 딕셔너리)
            start_date: YYYY-MM-DD 형식의 시작 날짜
            end_date: YYYY-MM-DD 형식의 종료 날짜
            project_id: 필터링할 프로젝트 ID (선택사항)

        Returns:
            List[Dict]: 필터링된 파일 목록
        """
        try:
            from datetime import datetime

            # 날짜 범위 파싱
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

            filtered_files = []

            for file_info in files:
                file_name = file_info["name"]

                # 프로젝트 ID 필터링 (선택사항)
                if project_id:
                    if f"/{project_id}/" not in file_name and not file_name.startswith(
                        f"{project_id}/"
                    ):
                        continue

                # 파일명에서 날짜 정보 추출
                # 예상 패턴: project_id/YYYY/MM/filename 또는 YYYY/MM/filename
                try:
                    # 경로에서 년도/월 추출
                    path_parts = file_name.split("/")
                    year_part = None
                    month_part = None

                    # YYYY/MM 패턴 찾기
                    for i, part in enumerate(path_parts):
                        if len(part) == 4 and part.isdigit():  # 년도 (YYYY)
                            year_part = part
                            if (
                                i + 1 < len(path_parts)
                                and len(path_parts[i + 1]) == 2
                                and path_parts[i + 1].isdigit()
                            ):
                                month_part = path_parts[i + 1]
                                break

                    if year_part and month_part:
                        # 파일의 날짜를 해당 월의 첫째 날로 설정
                        file_datetime = datetime(int(year_part), int(month_part), 1)

                        # 날짜 범위 내에 있는지 확인
                        if start_datetime <= file_datetime <= end_datetime:
                            filtered_files.append(file_info)
                    else:
                        # 날짜 정보를 찾을 수 없는 파일은 포함 (안전한 처리)
                        _LOGGER.debug(
                            f"No date pattern found in file: {file_name}, including in results"
                        )
                        filtered_files.append(file_info)

                except Exception as file_error:
                    _LOGGER.debug(
                        f"Error parsing date from file {file_name}: {file_error}"
                    )
                    # 파싱 오류가 있는 파일도 포함 (안전한 처리)
                    filtered_files.append(file_info)

            _LOGGER.debug(
                f"Filtered files by date range {start_date}~{end_date}: {len(filtered_files)}/{len(files)} files"
            )

            return filtered_files

        except Exception as e:
            _LOGGER.error(
                f"Failed to filter files by date range {start_date}~{end_date}: {e}"
            )
            return files

    @staticmethod
    def _validate_and_fix_date_range(start_date: str) -> str:
        """날짜 범위 검증 및 미래 날짜 보정

        Args:
            start_date: YYYY-MM 또는 YYYY-MM-DD 형식의 시작 날짜

        Returns:
            str: 검증된 시작 날짜 (미래 날짜인 경우 현재 날짜로 보정)
        """
        try:
            # 현재 날짜
            current_date = datetime.now()
            current_year_month = current_date.strftime("%Y-%m")

            # 입력 날짜 파싱 - YYYY-MM-DD 형식도 지원
            if not start_date:
                return current_year_month

            # YYYY-MM-DD 형식인 경우 YYYY-MM로 변환
            if len(start_date) == 10 and start_date.count("-") == 2:
                start_date = start_date[:7]  # YYYY-MM 부분만 추출
            elif len(start_date) != 7:  # YYYY-MM 형식 검증
                _LOGGER.warning(
                    f"Invalid date format: {start_date}, using current month"
                )
                return current_year_month

            start_year, start_month = map(int, start_date.split("-"))
            start_datetime = datetime(start_year, start_month, 1)

            # 미래 날짜 검증 (월 단위로 비교)
            current_month_start = datetime(current_date.year, current_date.month, 1)
            if start_datetime > current_month_start:
                _LOGGER.warning(
                    f"Future date detected: {start_date}, adjusting to current month"
                )
                return current_year_month

            # 너무 과거 날짜 검증 (5년 이전)
            five_years_ago = current_date - timedelta(days=365 * 5)
            if start_datetime < five_years_ago:
                safe_start = five_years_ago.strftime("%Y-%m")
                _LOGGER.warning(
                    f"Date too far in past: {start_date}, adjusting to: {safe_start}"
                )
                return safe_start

            # 유효한 날짜인 경우 YYYY-MM 형식으로 반환
            return start_date

        except Exception as e:
            _LOGGER.error(f"Date validation failed: {e}")
            return datetime.now().strftime("%Y-%m")

    @staticmethod
    def _calculate_partition_date_range(
        start_date: str, end_date: str = None
    ) -> tuple[str, str]:
        """PARTITIONDATE 범위 계산

        시작월부터 현재월까지의 범위를 설정합니다.

        Args:
            start_date: YYYY-MM 형식의 시작 날짜
            end_date: YYYY-MM 형식의 종료 날짜 (선택사항, 현재는 사용하지 않음)

        Returns:
            tuple[str, str]: (partition_start_date, partition_end_date) YYYY-MM-DD 형식
        """
        try:
            import calendar

            # 현재 날짜
            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month

            # 시작일 파싱
            if not start_date or len(start_date) != 7:  # YYYY-MM 형식 검증
                start_year = current_year
                start_month = current_month
            else:
                start_year, start_month = map(int, start_date.split("-"))

            # 시작월의 첫째 날
            partition_start_str = f"{start_year:04d}-{start_month:02d}-01"

            # 현재월의 마지막 날
            last_day = calendar.monthrange(current_year, current_month)[1]
            partition_end_str = f"{current_year:04d}-{current_month:02d}-{last_day:02d}"

            _LOGGER.debug(
                f"[PARTITIONDATE] {start_date} → {partition_start_str}~{partition_end_str} (시작월~현재월)"
            )

            return partition_start_str, partition_end_str

        except Exception as e:
            _LOGGER.error(f"[PARTITIONDATE] Calculation failed: {e}")
            # 실패 시 안전한 기본값 반환 (현재 월)
            current_date = datetime.now()
            start_str = current_date.strftime("%Y-%m-01")
            # 현재 월의 마지막 날 계산
            try:
                import calendar

                last_day = calendar.monthrange(current_date.year, current_date.month)[1]
                end_str = (
                    f"{current_date.year:04d}-{current_date.month:02d}-{last_day:02d}"
                )
            except Exception:
                end_str = current_date.strftime("%Y-%m-28")  # 안전한 기본값
            return start_str, end_str

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
