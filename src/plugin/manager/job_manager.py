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
    # 🚀 활성 프로젝트 캐시 (클래스 변수)
    _active_projects_cache = {
        "data": [],
        "last_updated": None,
        "cache_duration_minutes": 30,  # 30분 캐시
    }

    def __init__(self, *args, **kwargs):
        _LOGGER.debug(
            f"[JobManager] Initializing JobManager - Args: {args}, Kwargs: {list(kwargs.keys()) if kwargs else 'None'}"
        )
        super().__init__(*args, **kwargs)

        _LOGGER.debug("[JobManager] Creating connector instances")
        self.bigquery_connector = BigqueryConnector()
        self.gcs_connector = GcsConnector()
        _LOGGER.debug("[JobManager] Connector instances created successfully")

        # 인스턴스 변수 초기화
        self.billing_export_project_id = None
        self.billing_dataset = None
        self.billing_table = None
        self.billing_account_id = None

        _LOGGER.info("[JobManager] JobManager initialized successfully")
        _LOGGER.debug(
            f"[JobManager] Available connectors: BigQuery={type(self.bigquery_connector).__name__}, "
            f"GCS={type(self.gcs_connector).__name__}"
        )

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
        _LOGGER.info(
            f"[JobManager.get_tasks] Starting task generation process for domain: {domain_id}"
        )
        _LOGGER.debug(
            f"[JobManager.get_tasks] Input parameters - "
            f"Schema: {schema}, Start: {start}, Last sync: {last_synchronized_at}"
        )
        _LOGGER.debug(f"[JobManager.get_tasks] Options keys: {list(options.keys())}")

        # filed_mapper 오타 사용 시 경고 (하위 호환성은 유지하지만 경고)
        if "filed_mapper" in options and "field_mapper" not in options:
            _LOGGER.warning(
                "[JobManager.get_tasks] Using deprecated 'filed_mapper' option. "
                "Please use 'field_mapper' instead for better compatibility."
            )

        _LOGGER.debug(
            f"[JobManager.get_tasks] Secret data keys: {list(secret_data.keys()) if secret_data else 'None'}"
        )

        # 데이터 소스 타입 결정
        _LOGGER.debug("[JobManager.get_tasks] Determining data source type")
        data_source_type = self._get_data_source_type(options)
        _LOGGER.info(
            f"[JobManager.get_tasks] Data source type determined: {data_source_type}"
        )

        # 디버깅을 위한 추가 출력 (기존 코드 유지)
        print(
            f"[DEBUG] get_tasks called with data_source_type: {data_source_type}, start: {start}"
        )

        # 에러 핸들러 초기화
        error_handler = GracefulErrorHandler(
            f"JobManager.get_tasks[{data_source_type}]"
        )

        # 데이터 소스 타입별 작업 생성 분기
        try:
            if data_source_type == DATA_SOURCE_TYPES["gcs"]:
                _LOGGER.info(
                    f"[JobManager.get_tasks] Using GCS mode (data_source_type: {data_source_type})"
                )
                result = self._get_http_file_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )
            elif data_source_type == DATA_SOURCE_TYPES["http"]:
                _LOGGER.info(
                    f"[JobManager.get_tasks] Using HTTP file mode (data_source_type: {data_source_type})"
                )
                result = self._get_http_file_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )
            elif data_source_type == DATA_SOURCE_TYPES["bigquery"]:
                _LOGGER.info(
                    f"[JobManager.get_tasks] Using BigQuery mode (data_source_type: {data_source_type})"
                )
                result = self._get_bigquery_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )
            else:
                _LOGGER.warning(
                    f"[JobManager.get_tasks] Unknown data_source_type: {data_source_type}, defaulting to BigQuery"
                )
                result = self._get_bigquery_tasks(
                    domain_id, options, secret_data, schema, start, last_synchronized_at
                )

            # 결과 검증
            if not validate_job_response(result):
                _LOGGER.warning(
                    "[JobManager.get_tasks] Invalid response detected, creating fallback response"
                )
                result = create_empty_job_response("Invalid response structure")

            # 전체 작업 생성 결과 로깅
            task_count = len(result.get("tasks", []))
            changed_count = len(result.get("changed", []))

            _LOGGER.info(
                f"[JobManager.get_tasks] Task generation completed successfully - "
                f"Total tasks: {task_count}, Changed items: {changed_count}, "
                f"Data source type: {data_source_type}"
            )
            _LOGGER.debug(
                f"[JobManager.get_tasks] Result structure: {list(result.keys())}"
            )

            return result

        except Exception as e:
            # 에러 핸들러를 통한 우아한 에러 처리
            if error_handler.handle_error(e, "Task generation"):
                _LOGGER.warning(
                    f"[JobManager.get_tasks] Task generation failed, returning empty response: {e}"
                )
                return create_empty_job_response(
                    f"Task generation failed: {str(e)[:100]}"
                )
            else:
                _LOGGER.error(
                    f"[JobManager.get_tasks] Critical task generation failure for data source type {data_source_type}: {e}"
                )
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
        """BigQuery 기반 작업 생성 (기존 로직)"""
        _LOGGER.info(
            f"[JobManager._get_bigquery_tasks] Starting BigQuery task generation for domain: {domain_id}"
        )
        _LOGGER.debug(
            f"[JobManager._get_bigquery_tasks] Parameters - Schema: {schema}, Start: {start}, "
            f"Last sync: {last_synchronized_at}"
        )

        try:
            # BigQuery 커넥터 세션 생성
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] Creating BigQuery connector session"
            )
            self.bigquery_connector.create_session(options, secret_data, schema)
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] BigQuery session created successfully"
            )

            # 옵션 검증
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] Validating BigQuery options"
            )
            self._check_options(options)
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] Options validation completed"
            )

            # 빌링 정보 설정
            self.billing_export_project_id = options["billing_export_project_id"]
            self.billing_dataset = self._extract_dataset_id(
                options["billing_dataset_id"]
            )
            self.billing_account_id = options["billing_account_id"]

            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] Billing configuration - "
                f"Project: {self.billing_export_project_id}, Dataset: {self.billing_dataset}, "
                f"Account: {self.billing_account_id}"
            )

            # 빌링 테이블 이름 생성
            self.billing_table = (
                f"{BIGQUERY_TABLE_PREFIX}_{self.billing_account_id.replace('-', '_')}"
            )
            _LOGGER.debug(
                f"[JobManager._get_bigquery_tasks] Generated billing table name: {self.billing_table}"
            )

            # 테이블 존재 검증
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] Validating BigQuery table existence"
            )
            self._validate_table_exists()
            _LOGGER.debug("[JobManager._get_bigquery_tasks] Table validation completed")

            # 작업 생성 초기화
            tasks = []
            changed = []

            # 시작 월 계산
            start_month = self._get_start_month(start, last_synchronized_at)
            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] Calculated start month: {start_month}"
            )

            # BigQuery 쿼리 생성 및 실행
            _LOGGER.debug(
                "[JobManager._get_bigquery_tasks] Creating BigQuery SQL query"
            )
            query = self._create_google_sql(start_month)

            # 쿼리 상세 로깅 추가
            _LOGGER.info("=" * 80)
            _LOGGER.info("🔍 [QUERY #1] JobManager - 스마트 프리필터링 프로젝트 조회")
            _LOGGER.info(f"[JobManager._get_bigquery_tasks] 조회 시작일: {start_month}")
            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] 빌링 프로젝트: {self.billing_export_project_id}"
            )
            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] 빌링 데이터셋: {self.billing_dataset}"
            )
            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] 빌링 테이블: {self.billing_table}"
            )
            _LOGGER.info(
                f"[JobManager._get_bigquery_tasks] 빌링 계정: {self.billing_account_id}"
            )
            _LOGGER.info(
                "[JobManager._get_bigquery_tasks] 필터 조건: 비용 > 0 OR 사용량 > 0"
            )
            _LOGGER.info("📝 [실행 쿼리]")
            _LOGGER.info(f"{query}")
            _LOGGER.info("=" * 80)

            # 쿼리 실행 시간 측정
            import time

            start_time = time.time()

            _LOGGER.info("🔄 [쿼리 실행 중] BigQuery에서 데이터 조회를 시작합니다...")
            response_stream = self.bigquery_connector.read_df_from_bigquery(query)
            execution_time = time.time() - start_time

            _LOGGER.info("=" * 80)
            _LOGGER.info("✅ [QUERY #1 완료] 스마트 필터링 쿼리 실행 결과")
            _LOGGER.info(f"📊 조회된 프로젝트 수: {len(response_stream)}개")
            _LOGGER.info(f"⏱️ 쿼리 실행 시간: {execution_time:.2f}초")
            _LOGGER.info(f"📅 조회 기간: {start_month}-01 이후")

            # 🎯 프로젝트 발견 및 태스크 생성 상세 로깅
            if len(response_stream) > 0:
                project_list = [row.id for _, row in response_stream.iterrows()]

                # 🚨 중요: 발견된 프로젝트 수 로깅
                actual_projects = len(project_list)

                _LOGGER.info("🎯 [프로젝트 발견 결과]")
                _LOGGER.info(
                    f"   📊 BigQuery에서 발견된 활성 프로젝트 수: {actual_projects}개"
                )
                _LOGGER.info("   🔍 필터 조건: cost > 0 OR usage.amount > 0")
                _LOGGER.info(f"   📅 조회 기간: {start_month}-01 이후")

                if actual_projects > 0:
                    _LOGGER.info(
                        f"   ✅ {actual_projects}개의 활성 프로젝트가 발견되었습니다!"
                    )
                else:
                    _LOGGER.warning("   ⚠️  활성 프로젝트가 발견되지 않았습니다!")
                    _LOGGER.warning("   💡 빌링 데이터나 필터 조건을 확인하세요.")

                _LOGGER.info(f"🎯 [활성 프로젝트 목록] - 총 {actual_projects}개")
                for i, project_id in enumerate(project_list, 1):
                    _LOGGER.info(f"   {i:2d}. {project_id}")

                # 특정 프로젝트들이 포함되었는지 확인 (누락되기 쉬운 프로젝트들)
                key_projects_to_check = [
                    "mkkang-project",
                    "dev-project-1-465407",
                    "inventory-project-465506",
                    "iron-man-2-465309",
                    "marvels-the-avengers-465309",
                    "the-incredible-hulk-465309",
                    "thor-465309",
                ]

                _LOGGER.info("🔍 [핵심 프로젝트 포함 확인]")
                for key_project in key_projects_to_check:
                    if key_project in project_list:
                        _LOGGER.info(f"   ✅ {key_project} - 포함됨")
                    else:
                        _LOGGER.warning(f"   ❌ {key_project} - 누락됨!")

            else:
                _LOGGER.error("🚨 [심각] 활성 프로젝트가 전혀 발견되지 않았습니다!")
                _LOGGER.error("   💡 문제 해결 체크리스트:")
                _LOGGER.error(
                    "   1. 필터 조건을 확인하세요: cost > 0 OR usage.amount > 0"
                )
                _LOGGER.error(f"   2. 조회 기간을 확인하세요: {start_month}-01 이후")
                _LOGGER.error(
                    f"   3. 테이블 경로를 확인하세요: {self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}"
                )
                _LOGGER.error("   4. BigQuery 테이블에 데이터가 있는지 확인하세요")
                _LOGGER.error("   5. 서비스 계정 권한을 확인하세요")
            _LOGGER.info("=" * 80)
            _LOGGER.debug(
                f"[JobManager._get_bigquery_tasks] Query executed, processing {len(response_stream)} rows"
            )

            # 프로젝트별 작업 생성
            for index, row in response_stream.iterrows():
                project_id = row.id
                _LOGGER.debug(
                    f"[JobManager._get_bigquery_tasks] Creating task for project: {project_id} (row {index + 1})"
                )

                task_options = {
                    "start": start_month,
                    "project_id": project_id,
                    "billing_export_project_id": self.billing_export_project_id,
                    "billing_dataset_id": self.billing_dataset,
                    "billing_account_id": self.billing_account_id,
                    "data_source_type": DATA_SOURCE_TYPES["bigquery"],  # 명시적 설정
                }

                tasks.append({"task_options": task_options})

            # SpaceONE Job 스키마의 start 필드 길이 제한 준수 (YYYY-MM 형식, 7자)
            changed_item = {"start": start_month}
            changed.append(changed_item)

            # 🚀 태스크 생성 완료 및 검증 로깅
            total_execution_time = time.time() - start_time

            _LOGGER.info("=" * 80)
            _LOGGER.info("🎉 [태스크 생성 완료] BigQuery 태스크 생성 최종 결과")
            _LOGGER.info(f"📋 생성된 태스크 수: {len(tasks)}개")
            _LOGGER.info(f"📅 대상 시작월: {start_month}")
            _LOGGER.info(f"⏱️ 총 실행시간: {total_execution_time:.2f}초")
            _LOGGER.info(f"🏷️ 변경된 항목 수: {len(changed)}개")

            # 🎯 태스크 생성 완전성 검증
            actual_tasks = len(tasks)
            discovered_projects = len(
                response_stream
            )  # BigQuery에서 실제 발견된 프로젝트 수

            _LOGGER.info("🔍 [태스크 생성 검증]")
            _LOGGER.info(f"   📊 발견된 프로젝트 수: {discovered_projects}개")
            _LOGGER.info(f"   ✅ 생성된 태스크 수: {actual_tasks}개")

            if actual_tasks == discovered_projects:
                _LOGGER.info(
                    "   🎯 완벽! 발견된 모든 프로젝트에 대한 태스크가 생성되었습니다!"
                )
            elif actual_tasks < discovered_projects:
                missing_tasks = discovered_projects - actual_tasks
                _LOGGER.warning(f"   ⚠️  {missing_tasks}개 태스크 생성 누락!")
                _LOGGER.warning(
                    "   💡 프로젝트 발견과 태스크 생성 간 불일치가 있습니다."
                )
            else:
                _LOGGER.warning(
                    f"   🤔 생성된 태스크가 발견된 프로젝트보다 {actual_tasks - discovered_projects}개 많습니다!"
                )

            # 생성된 태스크의 프로젝트 ID 목록 (검증용)
            task_project_ids = [task["task_options"]["project_id"] for task in tasks]
            _LOGGER.info("📝 [생성된 태스크의 프로젝트 ID 목록]")
            for i, project_id in enumerate(task_project_ids, 1):
                _LOGGER.info(f"   {i:2d}. {project_id}")

            _LOGGER.info("=" * 80)
            _LOGGER.debug(
                f"[JobManager._get_bigquery_tasks] Changed item: {changed_item}"
            )

            return {"tasks": tasks, "changed": changed}

        except Exception as e:
            _LOGGER.error(
                f"[JobManager._get_bigquery_tasks] BigQuery task generation failed: {e}"
            )
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
        _LOGGER.debug(
            f"[JobManager._get_start_month] Input parameters - start: {start}, last_synchronized_at: {last_synchronized_at}"
        )

        if start:
            # 1순위: 사용자 지정 start 시점 사용
            start_time: datetime = self._parse_start_time(start)
            _LOGGER.debug(
                f"[JobManager._get_start_month] Using provided start parameter: {start}"
            )
        elif last_synchronized_at:
            # 2순위: 마지막 동기화에서 10일 이전 (데이터 누락 방지)
            start_time: datetime = last_synchronized_at - timedelta(days=10)
            _LOGGER.info(
                f"[JobManager._get_start_month] Using last_synchronized_at with 10-day buffer: "
                f"{last_synchronized_at.strftime('%Y-%m-%d')} → {start_time.strftime('%Y-%m-%d')}"
            )
        else:
            # 3순위: 현재에서 12개월 이전 (최초 연동)
            current_utc = datetime.utcnow()
            start_time: datetime = current_utc - relativedelta(months=12)
            start_time = start_time.replace(day=1)
            _LOGGER.info(
                f"[JobManager._get_start_month] Using default (12 months ago) - "
                f"current: {current_utc.strftime('%Y-%m-%d')}, calculated: {start_time.strftime('%Y-%m-%d')}"
            )

        # 시간 정보 정규화 (월 단위로 처리하기 위해)
        start_time = start_time.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        result = start_time.strftime("%Y-%m")
        _LOGGER.info(f"[JobManager._get_start_month] Final start month: {result}")
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
        """BigQuery SQL 쿼리 생성 및 로깅"""
        _LOGGER.debug(
            f"[JobManager._create_google_sql] 쿼리 생성 시작 - start: {start}"
        )
        _LOGGER.debug(
            f"[JobManager._create_google_sql] 테이블 정보 - {self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}"
        )

        # 🚀 스마트 프리필터링: 금액이 0이 아닌 프로젝트만 조회
        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{start}-01')
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

        _LOGGER.debug(
            f"[JobManager._create_google_sql] WHERE 조건: {where_condition.strip()}"
        )
        _LOGGER.debug(
            f"[JobManager._create_google_sql] 생성된 쿼리 길이: {len(query)} 문자"
        )
        _LOGGER.debug("[JobManager._create_google_sql] 쿼리 생성 완료")

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

        is_valid = cache_age < max_age
        if is_valid:
            _LOGGER.debug(
                f"[캐시] ✅ 유효한 캐시 사용 (생성시간: {self._active_projects_cache['last_updated']}, 나이: {cache_age})"
            )
        else:
            _LOGGER.debug(
                f"[캐시] ❌ 캐시 만료 (생성시간: {self._active_projects_cache['last_updated']}, 나이: {cache_age})"
            )

        return is_valid

    def _update_cache(self, projects: list):
        """캐시 업데이트"""
        self._active_projects_cache["data"] = projects
        self._active_projects_cache["last_updated"] = datetime.now()
        _LOGGER.info(
            f"[캐시] 🔄 활성 프로젝트 캐시 업데이트: {len(projects)}개 프로젝트"
        )

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
        _LOGGER.info(f"[JobManager._get_http_file_tasks] domain: {domain_id}")
        _LOGGER.debug(
            f"[JobManager._get_http_file_tasks] Parameters - Schema: {schema}, Start: {start}, "
            f"Last sync: {last_synchronized_at}"
        )

        # 디버깅을 위한 추가 출력 (기존 코드 유지)

        try:
            # HTTP 파일 커넥터 세션 생성 - 재시도 로직 추가
            _LOGGER.debug(
                "[JobManager._get_http_file_tasks] Creating HTTP file connector session"
            )
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    self.gcs_connector.create_session(options, secret_data, schema)
                    _LOGGER.debug(
                        "[JobManager._get_http_file_tasks] HTTP file session created successfully"
                    )
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        _LOGGER.error(
                            f"[JobManager._get_http_file_tasks] Failed to create session after {max_retries} attempts: {e}"
                        )
                        raise
                    _LOGGER.warning(
                        f"[JobManager._get_http_file_tasks] Session creation attempt {retry_count} failed: {e}, retrying..."
                    )
                    import time

                    time.sleep(1)  # 1초 대기 후 재시도

            # HTTP 파일 설정 검증
            _LOGGER.debug(
                "[JobManager._get_http_file_tasks] Validating HTTP file options"
            )
            self._check_http_file_options(options)
            _LOGGER.debug(
                "[JobManager._get_http_file_tasks] HTTP file options validation completed"
            )

            # 작업 생성 초기화
            tasks = []
            changed = []

            _LOGGER.debug(
                "[JobManager._get_http_file_tasks] Initialized task containers"
            )

            # 파일 목록 또는 단일 파일 처리
            if "file_list" in options:
                # 여러 파일 처리
                file_list = options["file_list"]
                _LOGGER.info(
                    f"[JobManager._get_http_file_tasks] Processing file list mode with {len(file_list)} files"
                )

                for index, file_info in enumerate(file_list):
                    bucket_name = file_info["bucket_name"]
                    file_path = file_info["file_path"]

                    _LOGGER.debug(
                        f"[JobManager._get_http_file_tasks] Processing file {index + 1}/{len(file_list)}: "
                        f"{bucket_name}/{file_path}"
                    )

                    task_options = {
                        "bucket_name": bucket_name,
                        "file_path": file_path,
                        "data_source_type": DATA_SOURCE_TYPES["http"],
                        "field_mapper": options.get("field_mapper", {}),
                        "parsing_options": file_info.get("parsing_options", {}),
                    }

                    tasks.append({"task_options": task_options})

                _LOGGER.info(
                    f"[JobManager._get_http_file_tasks] File list processing completed - "
                    f"Created {len(tasks)} tasks from file list"
                )

            elif "bucket_name" in options:
                # 버킷에서 파일 목록 자동 생성
                bucket_name = options["bucket_name"]
                project_id = options.get("project_id")

                _LOGGER.info(
                    f"[JobManager._get_http_file_tasks] Processing bucket mode - "
                    f"Bucket: {bucket_name}, Project ID: {project_id or 'Not specified'}"
                )

                # start 파라미터가 있고 project_id가 지정된 경우 직접 경로 접근 사용
                if start and project_id:
                    _LOGGER.info(
                        "[JobManager._get_http_file_tasks] Using direct path access method (optimized)"
                    )
                    validated_start = self._validate_and_fix_date_range(start)
                    year, month = validated_start.split("-")

                    _LOGGER.info(
                        f"[JobManager._get_http_file_tasks] Direct path: {bucket_name}/{project_id}/{year}/{month}/"
                    )

                    # 직접 경로로 파일 목록 조회 - 에러 처리 강화
                    try:
                        files = self.gcs_connector.list_gcs_files_by_path(
                            bucket_name, project_id, year, month
                        )

                        _LOGGER.info(
                            f"[JobManager._get_http_file_tasks] Direct path access result - "
                            f"Found {len(files)} files in {project_id}/{year}/{month}/"
                        )
                    except Exception as e:
                        _LOGGER.error(
                            f"[JobManager._get_http_file_tasks] Failed to list files from direct path "
                            f"{bucket_name}/{project_id}/{year}/{month}/: {e}"
                        )
                        # 빈 파일 목록으로 계속 진행하되, 에러를 기록
                        files = []
                        _LOGGER.warning(
                            "[JobManager._get_http_file_tasks] Continuing with empty file list due to access error"
                        )
                else:
                    # 기존 방식: 전체 파일 목록 조회 후 필터링
                    _LOGGER.info(
                        "[JobManager._get_http_file_tasks] Using legacy file listing method (with filtering)"
                    )
                    file_pattern = options.get("file_pattern")

                    _LOGGER.debug(
                        f"[JobManager._get_http_file_tasks] File pattern: {file_pattern or 'None (all files)'}"
                    )

                    # 파일 목록 조회 - 에러 처리 강화
                    try:
                        files = self.gcs_connector.list_gcs_files(
                            bucket_name, file_pattern
                        )
                    except Exception as e:
                        _LOGGER.error(
                            f"[JobManager._get_http_file_tasks] Failed to list files from bucket {bucket_name}: {e}"
                        )
                        # 빈 파일 목록으로 계속 진행하되, 에러를 기록
                        files = []
                        _LOGGER.warning(
                            "[JobManager._get_http_file_tasks] Continuing with empty file list due to access error"
                        )

                    # start 파라미터 기반 파일 필터링
                    _LOGGER.info(
                        f"[JobManager._get_http_file_tasks] Before filtering: {len(files)} files, "
                        f"Start parameter: {start}"
                    )

                    if start:
                        validated_start = self._validate_and_fix_date_range(start)
                        _LOGGER.info(
                            f"[JobManager._get_http_file_tasks] Validated start date: {validated_start}"
                        )
                        # 날짜 및 프로젝트 ID 기반 필터링
                        original_count = len(files)
                        files = self._filter_files_by_date(
                            files, validated_start, project_id
                        )
                        filter_info = f"date: {validated_start}"
                        if project_id:
                            filter_info += f", project_id: {project_id}"
                        _LOGGER.info(
                            f"[JobManager._get_http_file_tasks] After filtering: {len(files)}/{original_count} "
                            f"files matched ({filter_info})"
                        )
                    elif project_id:
                        # start 파라미터가 없어도 project_id가 있으면 필터링 적용
                        _LOGGER.info(
                            f"[JobManager._get_http_file_tasks] No start parameter provided, but filtering by project_id: {project_id}"
                        )
                        original_count = len(files)
                        files = self._filter_files_by_project_id(files, project_id)
                        _LOGGER.info(
                            f"[JobManager._get_http_file_tasks] After project_id filtering: {len(files)}/{original_count} "
                            f"files matched (project_id: {project_id})"
                        )
                    else:
                        _LOGGER.info(
                            "[JobManager._get_http_file_tasks] No start parameter or project_id provided, using all files"
                        )

                # 파일별 작업 생성
                _LOGGER.debug(
                    f"[JobManager._get_http_file_tasks] Creating tasks from {len(files)} files"
                )

                if not files:
                    _LOGGER.warning(
                        f"[JobManager._get_http_file_tasks] No files found in bucket {bucket_name} "
                        f"with current parameters. This may indicate access issues or empty bucket."
                    )

                for index, file_info in enumerate(files):
                    try:
                        file_path = file_info["name"]
                        # 작업 생성은 처음 3개와 마지막 3개만 로깅 (스팸 방지)
                        if index + 1 <= 3 or index + 1 > len(files) - 3:
                            _LOGGER.debug(
                                f"[JobManager._get_http_file_tasks] Creating task {index + 1}/{len(files)}: "
                                f"{bucket_name}/{file_path}"
                            )

                        task_options = {
                            "bucket_name": bucket_name,
                            "file_path": file_path,
                            "data_source_type": DATA_SOURCE_TYPES["http"],
                            "field_mapper": options.get("field_mapper", {}),
                            "parsing_options": options.get("parsing_options", {}),
                        }

                        tasks.append({"task_options": task_options})
                    except Exception as e:
                        _LOGGER.error(
                            f"[JobManager._get_http_file_tasks] Failed to create task for file {index + 1}: {e}"
                        )
                        # 개별 파일 에러는 로그만 남기고 계속 진행
                        continue

                _LOGGER.info(
                    f"[JobManager._get_http_file_tasks] Bucket processing completed - "
                    f"Created {len(tasks)} tasks from bucket files"
                )

            else:
                # 단일 파일 처리
                bucket_name = options.get("bucket_name")
                file_path = options.get("file_path")

                _LOGGER.info(
                    f"[JobManager._get_http_file_tasks] Processing single file mode - "
                    f"Bucket: {bucket_name}, File: {file_path}"
                )

                if not bucket_name or not file_path:
                    error_msg = "Either 'file_list', 'bucket_name', or both 'bucket_name' and 'file_path' must be provided"
                    _LOGGER.error(f"[JobManager._get_http_file_tasks] {error_msg}")
                    raise ERROR_REQUIRED_PARAMETER(key=error_msg)

                _LOGGER.debug(
                    f"[JobManager._get_http_file_tasks] Creating single task for: {bucket_name}/{file_path}"
                )

                task_options = {
                    "bucket_name": bucket_name,
                    "file_path": file_path,
                    "data_source_type": DATA_SOURCE_TYPES["http"],
                    "field_mapper": options.get("field_mapper", {}),
                    "parsing_options": options.get("parsing_options", {}),
                }

                tasks.append({"task_options": task_options})

                _LOGGER.info(
                    "[JobManager._get_http_file_tasks] Single file processing completed - Created 1 task"
                )

            # 변경 사항 기록 - start 필드 포함 (TasksResponse 스키마 요구사항)
            _LOGGER.debug(
                "[JobManager._get_http_file_tasks] Creating changed items for response"
            )
            current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # start 파라미터 처리 - BigQuery 모드와 동일한 _get_start_month 함수 사용
            start_month = self._get_start_month(start, last_synchronized_at)
            _LOGGER.debug(
                f"[JobManager._get_http_file_tasks] Calculated start month: {start_month}"
            )

            if start:
                start_value = self._validate_and_fix_date_range(start)
                _LOGGER.debug(
                    f"[JobManager._get_http_file_tasks] Using validated start: {start_value}"
                )
            else:
                start_value = (
                    start_month  # _get_start_month에서 계산된 기본값 사용 (1년 전)
                )
                _LOGGER.debug(
                    f"[JobManager._get_http_file_tasks] Using default start from _get_start_month: {start_value}"
                )

            changed_item = {
                "start": start_value,
                "timestamp": current_time,
                "file_count": len(tasks),
            }
            changed.append(changed_item)

            _LOGGER.debug(
                f"[JobManager._get_http_file_tasks] Created changed item: {changed_item}"
            )

            # 작업 생성 결과 검증
            if not tasks:
                _LOGGER.warning(
                    "[JobManager._get_http_file_tasks] No tasks were created. "
                    "This might indicate access issues or no matching files found."
                )
                # 빈 작업 목록도 유효한 결과로 처리 (SpaceONE 요구사항)

            _LOGGER.info(
                f"[JobManager._get_http_file_tasks] HTTP file task generation completed successfully - "
                f"Generated {len(tasks)} tasks, Start: {start_value}"
            )

            return {"tasks": tasks, "changed": changed}

        except Exception as e:
            _LOGGER.error(
                f"[JobManager._get_http_file_tasks] HTTP file task generation failed: {e}"
            )
            # 에러 발생 시에도 빈 결과를 반환하여 전체 프로세스가 중단되지 않도록 함
            _LOGGER.info(
                "[JobManager._get_http_file_tasks] Returning empty task list due to error"
            )
            return {"tasks": [], "changed": []}

    def _get_data_source_type(self, options: dict) -> str:
        """데이터 소스 타입 결정"""
        _LOGGER.debug(
            "[JobManager._get_data_source_type] Starting data source type determination"
        )
        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Available options: {list(options.keys())}"
        )
        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Available data source types: {list(DATA_SOURCE_TYPES.keys())}"
        )

        # 1. 명시적 data_source_type 확인
        data_source_type = options.get("data_source_type")
        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Explicit data_source_type: {data_source_type}"
        )

        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            _LOGGER.info(
                f"[JobManager._get_data_source_type] Using explicit data_source_type: {data_source_type}"
            )
            return data_source_type
        elif data_source_type:
            _LOGGER.warning(
                f"[JobManager._get_data_source_type] Invalid explicit data_source_type: {data_source_type}, "
                f"Valid types: {list(DATA_SOURCE_TYPES.values())}"
            )

        # 2. 'source' 파라미터 지원 (3개 고정 값: bigquery, gcs, http)
        source = options.get("source")
        _LOGGER.debug(f"[JobManager._get_data_source_type] Source parameter: {source}")

        if source == "bigquery":
            _LOGGER.info(
                "[JobManager._get_data_source_type] Using source=bigquery -> bigquery"
            )
            return DATA_SOURCE_TYPES["bigquery"]
        elif source == "gcs":
            _LOGGER.info("[JobManager._get_data_source_type] Using source=gcs -> gcs")
            return DATA_SOURCE_TYPES["gcs"]
        elif source == "http":
            _LOGGER.info("[JobManager._get_data_source_type] Using source=http -> http")
            return DATA_SOURCE_TYPES["http"]
        elif source:
            _LOGGER.warning(
                f"[JobManager._get_data_source_type] Unknown source parameter: {source}, "
                f"Valid sources: bigquery, gcs, http"
            )

        # 3. 파라미터 기반 자동 감지
        _LOGGER.debug(
            "[JobManager._get_data_source_type] Attempting auto-detection based on parameters"
        )

        # HTTP 파일 모드 감지: bucket_name이 있고 BigQuery 필수 파라미터가 없는 경우
        has_bucket = "bucket_name" in options
        has_bigquery_params = all(key in options for key in REQUIRED_OPTIONS)

        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Auto-detection analysis - "
            f"has_bucket: {has_bucket}, has_bigquery_params: {has_bigquery_params}"
        )
        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Required BigQuery options: {REQUIRED_OPTIONS}"
        )
        _LOGGER.debug(
            f"[JobManager._get_data_source_type] Missing BigQuery options: "
            f"{[key for key in REQUIRED_OPTIONS if key not in options]}"
        )

        if has_bucket and not has_bigquery_params:
            _LOGGER.info(
                "[JobManager._get_data_source_type] Auto-detected gcs mode (bucket_name present, BigQuery params missing)"
            )
            return DATA_SOURCE_TYPES["gcs"]
        elif has_bigquery_params:
            _LOGGER.info(
                "[JobManager._get_data_source_type] Auto-detected bigquery mode (all BigQuery params present)"
            )
            return DATA_SOURCE_TYPES["bigquery"]
        elif has_bucket and has_bigquery_params:
            _LOGGER.warning(
                "[JobManager._get_data_source_type] Both bucket_name and BigQuery params present, "
                "preferring BigQuery mode"
            )
            return DATA_SOURCE_TYPES["bigquery"]

        # 4. 기본값 반환 (하위 호환성)
        _LOGGER.warning(
            f"[JobManager._get_data_source_type] No clear data source type detected, "
            f"using default: {DEFAULT_DATA_SOURCE_TYPE}"
        )
        _LOGGER.debug(
            "[JobManager._get_data_source_type] Consider providing explicit 'data_source_type' "
            "or 'source' parameter for better reliability"
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
            _LOGGER.warning(
                "[_filter_files_by_project_id] No project_id provided, returning all files"
            )
            return files

        filtered_files = []

        for file_info in files:
            file_path = file_info.get("name", "")

            # 파일 경로 구조 분석: project_id/year/month/filename
            # 예: mkkang-project/2025/09/billing_data_202509-000000000002.parquet
            path_parts = file_path.split("/")

            if len(path_parts) < 4:  # 최소 4개 부분이 필요 (project/year/month/file)
                _LOGGER.debug(
                    f"[_filter_files_by_project_id] ❌ Invalid path structure: {file_path}"
                )
                continue

            file_project_id = path_parts[0]

            # 프로젝트 ID 매칭 검증
            if file_project_id == project_id:
                filtered_files.append(file_info)
                # 매칭된 파일은 처음 3개만 로깅 (스팸 방지)
                if len(filtered_files) <= 3:
                    _LOGGER.debug(
                        f"[_filter_files_by_project_id] ✅ Matched file: {file_path} (project_id={project_id})"
                    )
            # 스킵된 파일은 로깅하지 않음 (스팸 방지) - 요약 정보만 INFO 레벨로 출력

        _LOGGER.info(
            f"[_filter_files_by_project_id] Filtered {len(filtered_files)}/{len(files)} files for project_id={project_id}"
        )

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
                    _LOGGER.debug(
                        f"[_filter_files_by_date] ❌ Invalid path structure: {file_path}"
                    )
                    continue

                file_project_id = path_parts[0]
                file_year = path_parts[1]
                file_month = path_parts[2]

                # 월 형식 검증: 정확히 2자리 숫자여야 함 (09-backup 등 방지)
                if not (file_month.isdigit() and len(file_month) == 2):
                    _LOGGER.debug(
                        f"[_filter_files_by_date] ❌ Invalid month format: {file_month} in {file_path}"
                    )
                    continue

                # 년도 형식 검증: 정확히 4자리 숫자여야 함
                if not (file_year.isdigit() and len(file_year) == 4):
                    _LOGGER.debug(
                        f"[_filter_files_by_date] ❌ Invalid year format: {file_year} in {file_path}"
                    )
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
                    # 매칭된 파일은 처음 3개만 로깅 (스팸 방지)
                    if len(filtered_files) <= 3:
                        filter_reason = f"date={target_year}/{target_month}"
                        if project_id:
                            filter_reason += f", project_id={project_id}"
                        _LOGGER.debug(
                            f"[_filter_files_by_date] ✅ Matched file: {file_path} ({filter_reason})"
                        )
                # 스킵된 파일은 로깅하지 않음 (스팸 방지) - 요약 정보만 INFO 레벨로 출력

            filter_summary = f"date={start_date}"
            if project_id:
                filter_summary += f", project_id={project_id}"
            _LOGGER.info(
                f"[_filter_files_by_date] Filtered {len(filtered_files)}/{len(files)} files for {filter_summary}"
            )
            return filtered_files

        except Exception as e:
            _LOGGER.error(
                f"[_filter_files_by_date] Failed to filter files for {start_date}: {e}"
            )
            # 오류 시 원본 파일 목록 반환
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
                _LOGGER.warning(
                    "[_validate_and_fix_date_range] Empty date, using current month"
                )
                return current_year_month

            # YYYY-MM-DD 형식인 경우 YYYY-MM로 변환
            if len(start_date) == 10 and start_date.count("-") == 2:
                start_date = start_date[:7]  # YYYY-MM 부분만 추출
            elif len(start_date) != 7:  # YYYY-MM 형식 검증
                _LOGGER.warning(
                    f"[_validate_and_fix_date_range] Invalid date format: {start_date}, using current month"
                )
                return current_year_month

            start_year, start_month = map(int, start_date.split("-"))
            start_datetime = datetime(start_year, start_month, 1)

            # 미래 날짜 검증 (월 단위로 비교)
            current_month_start = datetime(current_date.year, current_date.month, 1)
            if start_datetime > current_month_start:
                _LOGGER.warning(
                    f"[_validate_and_fix_date_range] Future date detected: {start_date}, "
                    f"adjusting to current month: {current_year_month}"
                )
                return current_year_month

            # 너무 과거 날짜 검증 (5년 이전)
            five_years_ago = current_date - timedelta(days=365 * 5)
            if start_datetime < five_years_ago:
                safe_start = five_years_ago.strftime("%Y-%m")
                _LOGGER.warning(
                    f"[_validate_and_fix_date_range] Date too far in past: {start_date}, "
                    f"adjusting to: {safe_start}"
                )
                return safe_start

            # 유효한 날짜인 경우 YYYY-MM 형식으로 반환
            return start_date

        except Exception as e:
            _LOGGER.error(f"[_validate_and_fix_date_range] Date validation failed: {e}")
            # 오류 시 안전한 기본값 반환 (현재 월)
            return datetime.now().strftime("%Y-%m")

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
