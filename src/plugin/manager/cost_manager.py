import logging
from collections.abc import Generator
from datetime import datetime, timedelta

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.error import ERROR_REQUIRED_PARAMETER
    from spaceone.core.manager import BaseManager
except ImportError:
    # Mock for local development
    class MockError:
        def __call__(self, *args, **kwargs):
            return Exception("Mock SpaceONE Error")

    ERROR_REQUIRED_PARAMETER = MockError()

    class BaseManager:
        """Mock BaseManager for local development"""

        pass


from ..conf.cost_conf import (
    BIGQUERY_TABLE_PREFIX,
    DATA_SOURCE_TYPES,
    DETAILED_USAGE_TABLE_PREFIX,
)
from ..connector.bigquery_connector import BigqueryConnector
from ..connector.gcs_connector import GcsConnector
from ..factory.file_processor_factory import FileProcessorFactory
from ..manager.field_mapper import FieldMapper
from ..utils.concurrency_manager import concurrency_manager, request_deduplicator

_LOGGER = logging.getLogger("spaceone")

REQUIRED_TASK_OPTIONS = [
    "start",
    "billing_export_project_id",
    "billing_dataset_id",
    "billing_account_id",
]
REQUIRED_OPTIONS = [
    "billing_export_project_id",
    "billing_dataset_id",
    "billing_account_id",
]
EXCLUSIVE_PRODUCT = ["Invoice"]


class CostManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery_connector = BigqueryConnector()
        self.gcs_connector = GcsConnector()  # 추가
        self.field_mapper = None  # 추가
        self.billing_export_project_id = None
        self.billing_dataset = None
        self.billing_table = None
        self.billing_account_id = None
        self.select_cost_option = None  # select_cost 옵션 저장
        self.cost_metric_option = None  # cost_metric 옵션 저장
        self.is_detailed_usage = False  # 상세 사용량 데이터 여부

    def get_linked_accounts(
        self, options: dict, secret_data: dict, schema: str
    ) -> dict:
        linked_accounts = []
        self.bigquery_connector.create_session(options, secret_data, schema)
        self._check_options(options)

        self.billing_export_project_id = options["billing_export_project_id"]
        self.billing_dataset = self._extract_dataset_id(options["billing_dataset_id"])
        self.billing_account_id = options["billing_account_id"]

        self.billing_table = (
            f"{BIGQUERY_TABLE_PREFIX}_{self.billing_account_id.replace('-', '_')}"
        )
        self._validate_table_exists()

        start_month = self._get_start_month()

        query = self._create_linked_accounts_google_sql(start_month)
        response_stream = self.bigquery_connector.read_df_from_bigquery(query)
        for _, row in response_stream.iterrows():
            if row.id is not None:
                linked_accounts.append({"account_id": row.id, "name": row.project_name})

        return {"results": linked_accounts}

    def get_data(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """데이터 소스 타입에 따라 처리 분기"""
        # 요청 중복 제거를 위한 해시 생성
        import hashlib
        import json

        # source 값 추출 (options에서만)
        source = self._get_source_value(options)

        # secret_data 제외하고 요청 식별을 위한 핵심 데이터만 사용
        request_data = {
            "source": source,  # source 항목 추가
            "project_id": options.get("project_id"),
            "select_cost": options.get("select_cost"),
            "field_mapper": options.get("field_mapper"),
            "bucket_name": options.get("bucket_name"),
            "base_url": options.get("base_url") or task_options.get("base_url"),
            "file_path": task_options.get("file_path"),
            "data_source_type": task_options.get("data_source_type"),
        }
        # 해시 생성 (중복 제거를 위해)
        request_hash = hashlib.md5(
            json.dumps(request_data, sort_keys=True).encode()
        ).hexdigest()

        # 중복 요청 확인
        from ..utils.concurrency_manager import request_deduplicator

        if request_deduplicator.is_duplicate_request(request_hash):
            return

        # source 기반 분기 처리
        if source == "bigquery":
            yield from self._get_data_from_bigquery(
                options, secret_data, task_options, schema
            )
        elif source == "gcs":
            yield from self._get_data_from_gcs(
                options, secret_data, task_options, schema
            )
        elif source == "http":
            yield from self._get_data_from_http(
                options, secret_data, task_options, schema
            )
        else:
            # 지원하지 않는 source 타입에 대한 에러 처리
            raise ERROR_REQUIRED_PARAMETER(
                key=f"source (unsupported value: {source}. Supported values: bigquery, gcs, http)"
            )

    def _get_data_from_bigquery(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """BigQuery에서 데이터 조회 (기존 로직)"""
        self.bigquery_connector.create_session(options, secret_data, schema)

        # options 검증 (항상 실행)
        self._check_options(options)

        # task_options 검증 (항상 실행)
        self._check_bigquery_task_options(task_options)

        # select_cost 옵션 설정 (task_options 우선, options 차순)
        self.select_cost_option = task_options.get("select_cost") or options.get(
            "select_cost", "cost"
        )
        # cost_metric 옵션 설정 (task_options 우선, options 차순)
        self.cost_metric_option = task_options.get("cost_metric") or options.get(
            "cost_metric"
        )

        start = task_options["start"]
        self.billing_export_project_id = task_options["billing_export_project_id"]
        self.billing_dataset = self._extract_dataset_id(
            task_options["billing_dataset_id"]
        )
        self.billing_account_id = task_options["billing_account_id"]
        self.target_project_id = task_options["project_id"]

        self.billing_table = (
            f"{BIGQUERY_TABLE_PREFIX}_{self.billing_account_id.replace('-', '_')}"
        )
        self._validate_table_exists()

        query = self._create_google_sql(start)
        response_stream = self.bigquery_connector.read_df_from_bigquery(query)
        for _, row in response_stream.iterrows():
            yield self._make_cost_data(row)

        # BigQuery 데이터의 경우 빈 results 반환
        yield {"results": []}

    def _get_data_from_gcs(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """GCS 버킷에서 데이터 조회 - 동시성 제어 및 중복 요청 처리"""
        try:
            # 요청 중복 제거 검사
            request_hash = request_deduplicator.generate_request_hash(
                options, task_options
            )
            if request_deduplicator.is_duplicate_request(request_hash):
                return

            # GCS 버킷 처리용 파라미터 검증
            self._check_gcs_task_options(task_options, options, secret_data)

            # select_cost 옵션 설정 (task_options 우선, options 차순)
            self.select_cost_option = task_options.get("select_cost") or options.get(
                "select_cost", "cost"
            )
            # cost_metric 옵션 설정 (task_options 우선, options 차순)
            self.cost_metric_option = task_options.get("cost_metric") or options.get(
                "cost_metric"
            )

            # bucket_name 추출 (task_options 우선)
            bucket_name = task_options.get("bucket_name") or options.get("bucket_name")

            if bucket_name:
                # GCS 버킷 접근을 위해 인증 필요
                self.gcs_connector.create_session(options, secret_data, schema)

                # Field Mapper 초기화 (기본 매핑 사용)
                # filed_mapper 오타 처리 (하위 호환성을 위해)
                field_mapper_config = options.get("field_mapper") or options.get(
                    "filed_mapper", {}
                )
                mapping_config = (
                    task_options.get("field_mapper", {}) or field_mapper_config
                )
                provider = options.get("provider", "google_cloud")

                # 원본 데이터 포함 옵션 처리
                include_raw_data = options.get("include_raw_data", False)
                wrap_as_sample_data = options.get("wrap_as_sample_data", False)

                self.field_mapper = FieldMapper(
                    mapping_config,
                    provider,
                    self.select_cost_option,
                    self.cost_metric_option,
                    include_raw_data,
                    wrap_as_sample_data,
                )

                # 압축 처리를 위한 import는 필요한 곳에서만 사용

                # 경로 패턴 생성: bucket_name/project_id/date_range 구조
                project_id = task_options.get("project_id") or options.get("project_id")
                start_period = task_options.get("start")

                # 파일 목록 가져오기
                files = self._get_gcs_file_list(
                    bucket_name, project_id, start_period, task_options
                )

                if not files:
                    # 파일이 없을 때는 빈 결과를 반환 (에러가 아닌 정상적인 상황일 수 있음)
                    yield {"results": []}
                    return

                # 여러 파일 처리 지원
                max_files = int(
                    task_options.get("max_files", 10)
                )  # 기본값: 최대 10개 파일
                files_to_process = files[:max_files]

                # 각 파일을 순차적으로 처리 (동시성 제어 적용)
                total_files = len(files_to_process)
                _LOGGER.info(
                    f"[CostManager] Starting GCS file processing: {total_files} files to process"
                )

                for file_index, file_info in enumerate(files_to_process, 1):
                    file_name = file_info.get("name", "unknown")
                    _LOGGER.info(
                        f"[CostManager] Processing file {file_index}/{total_files}: {file_name}"
                    )

                    file_processed_count = 0
                    for batch_result in self._process_gcs_file(
                        bucket_name, file_info, task_options
                    ):
                        if batch_result and "results" in batch_result:
                            batch_size = len(batch_result["results"])
                            file_processed_count += batch_size
                            _LOGGER.info(
                                f"[CostManager] File {file_index}/{total_files} ({file_name}): "
                                f"Processed batch of {batch_size:,} records "
                                f"(File total: {file_processed_count:,})"
                            )
                        yield batch_result

                    _LOGGER.info(
                        f"[CostManager] Completed file {file_index}/{total_files} ({file_name}): "
                        f"Total {file_processed_count:,} records processed"
                    )

                _LOGGER.info(
                    f"[CostManager] Completed GCS file processing: {total_files} files processed"
                )

                # 최종 일별 카운트 요약 로깅
                if hasattr(self, "field_mapper") and self.field_mapper:
                    self.field_mapper.log_final_daily_count_summary()

        except Exception as e:
            _LOGGER.error(
                f"[_get_data_from_gcs] Failed to process GCS file: {e}", exc_info=True
            )
            raise e

    def _process_gcs_file(
        self, bucket_name: str, file_info: dict, task_options: dict
    ) -> Generator[dict, None, None]:
        """개별 GCS 파일 처리"""
        file_name = file_info["name"]

        # 파일이 이미 처리 중인지 확인
        if concurrency_manager.is_file_processing(bucket_name, file_name):
            return

        try:
            # 파일 처리 락 획득
            with concurrency_manager.acquire_file_lock(
                bucket_name, file_name, timeout=60.0
            ) as lock_result:
                # 락 획득 실패 시 (이미 처리 중인 파일) 건너뛰기
                if lock_result is None:
                    return

                # 파일 다운로드
                file_stream = self.gcs_connector.download_gcs_file_stream(
                    bucket_name, file_name
                )

                # 파일 내용 샘플 읽기 (파일 형식 감지를 위해)
                file_stream.seek(0)
                content_sample = file_stream.read(1024)  # 처음 1KB 읽기
                file_stream.seek(0)  # 스트림 위치 리셋

                # 파일 형식 감지 (내용 샘플 포함)
                file_format = file_info.get(
                    "format"
                ) or FileProcessorFactory.detect_file_format(file_name, content_sample)

                # 압축 해제 (필요한 경우)
                from ..utils.compression import CompressionHandler

                compression_type = CompressionHandler.detect_compression(
                    file_name, content_sample
                )
                if compression_type:
                    file_stream = CompressionHandler.decompress_stream(
                        file_stream, compression_type
                    )

                # 파서 생성 및 데이터 처리
                parser = FileProcessorFactory.create_parser(file_format)

                # 파싱 옵션 설정
                parsing_options = task_options.get("parsing_options", {})

                # 데이터 스트림 처리 - BigQuery results 구조로 변환
                for batch_result in parser.parse_stream(
                    file_stream, self.field_mapper, **parsing_options
                ):
                    if batch_result and "results" in batch_result:
                        # GCS 응답을 BigQuery results 구조로 변환
                        converted_result = self._convert_to_bigquery_structure(
                            batch_result
                        )
                        yield converted_result

        except Exception as file_error:
            _LOGGER.error(
                f"[_process_gcs_file] Failed to process file {file_name}: {file_error}"
            )
            # 개별 파일 처리 실패 시 다음 파일로 계속 진행

    def _get_gcs_file_list(
        self, bucket_name: str, project_id: str, start_period: str, task_options: dict
    ) -> list[dict]:
        """GCS 버킷에서 파일 목록 가져오기"""
        # 특정 파일 경로가 지정된 경우 해당 파일만 반환
        file_path = task_options.get("file_path")
        if file_path:
            _LOGGER.info(f"[CostManager] Specific file_path provided: {file_path}")
            # 특정 파일만 조회
            specific_files = self.gcs_connector.list_gcs_files(bucket_name, file_path)
            if specific_files:
                _LOGGER.info(
                    f"[CostManager] Found specific file: {specific_files[0]['name']}"
                )
                return specific_files
            else:
                _LOGGER.warning(f"[CostManager] Specified file not found: {file_path}")
                return []

        # 사용자 정의 패턴이 있으면 우선 적용
        custom_pattern = task_options.get("file_pattern")
        if custom_pattern:
            file_pattern = custom_pattern
            return self.gcs_connector.list_gcs_files(bucket_name, file_pattern)
        elif project_id and start_period:
            # start부터 현재 월까지의 날짜 범위로 파일 수집
            all_files = []
            date_patterns = self._generate_date_range_patterns(project_id, start_period)

            for pattern in date_patterns:
                pattern_files = self.gcs_connector.list_gcs_files(
                    bucket_name, pattern
                )
                all_files.extend(pattern_files)

            # 중복 제거 (파일명 기준)
            seen_files = set()
            files = []
            for file_info in all_files:
                if file_info["name"] not in seen_files:
                    files.append(file_info)
                    seen_files.add(file_info["name"])
            return files

        elif project_id:
            file_pattern = f"{project_id}/"
            return self.gcs_connector.list_gcs_files(bucket_name, file_pattern)
        else:
            # 패턴 없이 모든 파일 검색
            return self.gcs_connector.list_gcs_files(bucket_name, None)

    def _get_data_from_http(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """HTTP URL에서 데이터 조회 - 인증 불필요"""
        try:
            # 요청 중복 제거 검사
            request_hash = request_deduplicator.generate_request_hash(
                options, task_options
            )
            if request_deduplicator.is_duplicate_request(request_hash):
                return

            # HTTP URL 처리용 파라미터 검증
            self._check_http_task_options(task_options, options)

            # select_cost 옵션 설정 (task_options 우선, options 차순)
            self.select_cost_option = task_options.get("select_cost") or options.get(
                "select_cost", "cost"
            )
            # cost_metric 옵션 설정 (task_options 우선, options 차순)
            self.cost_metric_option = task_options.get("cost_metric") or options.get(
                "cost_metric"
            )

            # base_url 추출 (task_options 우선)
            base_url = task_options.get("base_url") or options.get("base_url")

            # URL 유효성 검증 및 정리
            if base_url:
                # 잘못된 파일 확장자 수정 (jparquet -> parquet)
                base_url = base_url.replace(".jparquet.", ".parquet.")

                # HTTP URL 처리 - 인증 불필요, GCS 세션 생성 건너뛰기
                file_stream = self.gcs_connector.download_file_from_url(base_url)

                # 파일 내용 샘플 읽기 (파일 형식 감지를 위해)
                file_stream.seek(0)
                content_sample = file_stream.read(1024)  # 처음 1KB 읽기
                file_stream.seek(0)  # 스트림 위치 리셋

                # 파일 형식 감지 (내용 샘플 포함)
                file_format = FileProcessorFactory.detect_file_format(
                    base_url, content_sample
                )

                # 압축 해제 (필요한 경우)
                from ..utils.compression import CompressionHandler

                compression_type = CompressionHandler.detect_compression(
                    base_url, content_sample
                )
                if compression_type:
                    file_stream = CompressionHandler.decompress_stream(
                        file_stream, compression_type
                    )

                # Field Mapper 초기화 (기본 매핑 사용)
                # filed_mapper 오타 처리 (하위 호환성을 위해)
                field_mapper_config = options.get("field_mapper") or options.get(
                    "filed_mapper", {}
                )
                mapping_config = (
                    task_options.get("field_mapper", {}) or field_mapper_config
                )
                provider = options.get("provider", "google_cloud")

                # 원본 데이터 포함 옵션 처리
                include_raw_data = options.get("include_raw_data", False)
                wrap_as_sample_data = options.get("wrap_as_sample_data", False)

                self.field_mapper = FieldMapper(
                    mapping_config,
                    provider,
                    self.select_cost_option,
                    self.cost_metric_option,
                    include_raw_data,
                    wrap_as_sample_data,
                )

                # 파서 생성 및 데이터 처리
                parser = FileProcessorFactory.create_parser(file_format)

                # 파싱 옵션 설정
                parsing_options = task_options.get("parsing_options", {})

                # 데이터 스트림 처리 - BigQuery results 구조로 변환
                _LOGGER.info("[CostManager] Starting HTTP file processing")
                total_processed_count = 0

                for batch_result in parser.parse_stream(
                    file_stream, self.field_mapper, **parsing_options
                ):
                    if batch_result and "results" in batch_result:
                        batch_size = len(batch_result["results"])
                        total_processed_count += batch_size
                        _LOGGER.info(
                            f"[CostManager] HTTP file: Processed batch of {batch_size:,} records "
                            f"(Total: {total_processed_count:,})"
                        )
                        # 응답을 BigQuery results 구조로 변환
                        converted_result = self._convert_to_bigquery_structure(
                            batch_result
                        )
                        yield converted_result

                _LOGGER.info(
                    f"[CostManager] Completed HTTP file processing: "
                    f"Total {total_processed_count:,} records processed"
                )

                # 최종 일별 카운트 요약 로깅
                if hasattr(self, "field_mapper") and self.field_mapper:
                    self.field_mapper.log_final_daily_count_summary()

        except Exception as e:
            _LOGGER.error(
                f"[_get_data_from_http] Failed to process HTTP file: {e}", exc_info=True
            )
            raise e

    def _convert_to_bigquery_structure(self, gcs_result: dict) -> dict:
        """GCS 응답을 BigQuery results 구조로 변환하지 않고 그대로 반환

        BigQuery 구조 변환이 billed_date 누락 문제를 일으키므로,
        SpaceONE 표준 구조를 유지하여 반환합니다.

        Args:
            gcs_result: GCS에서 가져온 결과 ({"results": [...]})

        Returns:
            SpaceONE 표준 구조를 유지한 결과
        """
        if not gcs_result or "results" not in gcs_result:
            return {"results": []}

        # 🚨 FINAL CRITICAL: SpaceONE 프레임워크 요구사항 준수
        # BigQuery 구조 변환 시 billed_date 누락 문제가 발생하므로 원본 SpaceONE 구조를 보존하되,
        # Google Cloud Billing에는 data 필드가 없지만 SpaceONE에서 필수로 요구하므로 빈 딕셔너리 제공
        # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage

        if "results" in gcs_result and isinstance(gcs_result["results"], list):
            for record in gcs_result["results"]:
                if isinstance(record, dict):
                    # data 필드에 SpaceONE 빌링 표준에 맞는 정보 추가
                    listed_price = self._get_listed_price_from_record(record)
                    record["data"] = self._create_spaceone_billing_data(
                        record, listed_price
                    )
        return gcs_result

    def _get_listed_price_from_record(self, record: dict):
        """레코드에서 listed_price(정가) 정보를 추출

        Google Cloud Billing 데이터에서 정가 정보는 다음 순서로 확인:
        1. cost_at_list (최상위 레벨)
        2. price.list_price (중첩 구조)
        3. price.list_price_consumption_model (소비 모델 기준 정가)
        4. cost (정가 정보가 없는 경우 실제 비용 사용)
        """
        # 1. 최상위 레벨의 cost_at_list 필드 확인
        cost_at_list = record.get("cost_at_list")
        if cost_at_list is not None and cost_at_list != "" and cost_at_list != 0:
            return cost_at_list

        # 2. price.list_price 중첩 구조 확인
        price_info = record.get("price", {})
        if isinstance(price_info, dict):
            list_price = price_info.get("list_price")
            if list_price is not None and list_price != "" and list_price != 0:
                # 문자열인 경우 숫자로 변환 시도
                try:
                    return (
                        float(list_price) if isinstance(list_price, str) else list_price
                    )
                except (ValueError, TypeError):
                    pass

            # 3. 소비 모델 기준 정가 확인
            list_price_consumption = price_info.get("list_price_consumption_model")
            if (
                list_price_consumption is not None
                and list_price_consumption != ""
                and list_price_consumption != 0
            ):
                try:
                    return (
                        float(list_price_consumption)
                        if isinstance(list_price_consumption, str)
                        else list_price_consumption
                    )
                except (ValueError, TypeError):
                    pass

        # 4. 정가 정보가 없는 경우 실제 비용 사용 (fallback)
        cost_value = record.get("cost")
        if cost_value is not None and cost_value != "":
            return cost_value

        # 5. 모든 시도가 실패한 경우 빈 문자열 반환
        return ""

    def _create_spaceone_billing_data(self, record: dict, listed_price) -> dict:
        """SpaceONE 빌링 표준에 맞는 data 필드 구조 생성 (간단한 구조: listed_price, cost만)"""
        # 기본 비용 정보만 포함 (숫자 타입으로 처리)
        data_structure = {
            "listed_price": self._convert_to_numeric(listed_price),
            "cost": self._convert_to_numeric(record.get("cost", 0)),
        }

        return data_structure


    def _convert_to_numeric(self, value):
        """값을 적절한 숫자 타입으로 변환"""
        if value is None or value == "":
            return 0.0

        try:
            # 이미 숫자인 경우 그대로 반환
            if isinstance(value, (int, float)):
                return float(value)

            # 문자열인 경우 숫자로 변환
            if isinstance(value, str):
                cleaned_value = value.strip()
                if not cleaned_value:
                    return 0.0
                return float(cleaned_value)

            # 기타 타입은 float로 변환 시도
            return float(value)

        except (ValueError, TypeError):
            return 0.0

    def _make_cost_data(self, row) -> dict:
        """Source Data Model (DataFrame)
        class CostSummaryItem(DataFrame):
            billed_at: str
            billing_account_id: str
            sku_description: str
            id: str
            name: str
            region_code: str
            currency_conversion_rate: float
            pricing_unit: str
            month: str
            cost_type: str
            labels: str(list of dict)
            cost: float
            usage_quantity: float
        """
        costs_data = []

        try:
            if getattr(row, "product", "") not in EXCLUSIVE_PRODUCT:
                # select_cost 옵션에 따라 적절한 비용 필드 선택
                selected_cost = self._get_cost_field_by_option(row)

                data = {
                    "cost": selected_cost,
                    "usage_quantity": getattr(row, "usage_quantity", 0.0),
                    "provider": "google_cloud",
                    "product": getattr(row, "description", "Unknown"),
                    "region_code": getattr(row, "region_code", ""),
                    "usage_type": getattr(row, "sku_description", ""),
                    "usage_unit": getattr(row, "pricing_unit", ""),
                    "billed_date": self._change_datetime_to_string(
                        getattr(row, "billed_at", "")
                    ),
                    "currency": getattr(row, "currency", "USD"),
                    "additional_info": {
                        "Project ID": getattr(row, "id", ""),
                        "Project Name": getattr(
                            row, "project_name", getattr(row, "name", "")
                        ),
                        "Billing Account ID": getattr(row, "billing_account_id", ""),
                        "Cost Type": getattr(row, "cost_type", ""),
                        "Invoice Month": getattr(row, "month", ""),
                        "Cost At List": getattr(row, "cost_at_list", 0.0),
                        "Cost After Credits": getattr(row, "cost_after_credits", 0.0),
                        "Credits Detail": getattr(row, "credits_detail", "[]"),
                        "Resource Tags": getattr(row, "resource_tags", "{}"),
                    },
                    "tags": {},
                }

                # 🚨 CRITICAL: SpaceONE 프레임워크 요구사항 준수 - data 필드 추가
                # BigQuery 소스도 GCS와 동일한 풍부한 data 구조 제공
                listed_price = getattr(row, "cost_at_list", selected_cost)
                data["data"] = self._create_spaceone_billing_data(data, listed_price)

                costs_data.append(data)

        except Exception as e:
            _LOGGER.error(f"[_make_cost_data] make data error: {e}", exc_info=True)
            raise e

        return {"results": costs_data}

    def _get_cost_field_by_option(self, row):
        """select_cost 및 cost_metric 옵션에 따라 적절한 비용 필드를 선택

        Args:
            row: BigQuery 또는 파일에서 읽은 데이터 행

        Returns:
            선택된 비용 값 (원본 타입 유지)
        """
        # cost_metric이 AmortizedCost인 경우 credits_amount 사용
        if self.cost_metric_option == "AmortizedCost":
            cost_value = getattr(row, "credits_amount", 0)
            return cost_value

        # 기존 select_cost 로직
        select_cost = self.select_cost_option or "cost"

        if select_cost == "list_price":
            # 정가 (크레딧 적용 전 원가)
            cost_value = getattr(row, "cost_at_list", 0)
            return cost_value
        elif select_cost == "after_credits":
            # 크레딧 적용 후 비용
            cost_value = getattr(row, "cost_after_credits", 0)
            return cost_value
        elif select_cost == "net_cost":
            # 순 비용 (기본 cost와 동일)
            cost_value = getattr(row, "cost", 0)
            return cost_value
        else:
            # 기본값: cost (크레딧을 포함한 최종 비용)
            cost_value = getattr(row, "cost", 0)
            return cost_value

    @staticmethod
    def _check_bigquery_task_options(task_options):
        """BigQuery 데이터 소스용 필수 파라미터 검증"""
        missing_keys = [key for key in REQUIRED_TASK_OPTIONS if key not in task_options]
        if missing_keys:
            for key in missing_keys:
                raise ERROR_REQUIRED_PARAMETER(key=f"task_options.{key}")

    @staticmethod
    def _check_gcs_task_options(task_options, options, secret_data=None):
        """GCS 버킷 데이터 소스용 필수 파라미터 검증"""
        # bucket_name이 있어야 함
        bucket_name = options.get("bucket_name") or task_options.get("bucket_name")

        if not bucket_name:
            raise ERROR_REQUIRED_PARAMETER(key="bucket_name")

        # GCS 버킷 사용 시 secret_data 검증
        if secret_data:
            from ..connector.gcs_connector import REQUIRED_SECRET_KEYS

            missing_keys = [
                key for key in REQUIRED_SECRET_KEYS if key not in secret_data
            ]
            if missing_keys:
                for key in missing_keys:
                    raise ERROR_REQUIRED_PARAMETER(key=f"secret_data.{key}")

    @staticmethod
    def _check_http_task_options(task_options, options):
        """HTTP URL 데이터 소스용 필수 파라미터 검증"""
        # base_url이 있어야 함
        base_url = options.get("base_url") or task_options.get("base_url")

        if not base_url:
            raise ERROR_REQUIRED_PARAMETER(key="base_url")

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

    @staticmethod
    def _check_options(options):
        """BigQuery options 필드 검증"""
        # options가 비어있으면 통과 (task_options에서 처리)
        if not options:
            return

        # BigQuery 관련 필드가 하나라도 있으면 모든 필수 필드 검증
        has_bigquery_fields = any(key in options for key in REQUIRED_OPTIONS)
        if has_bigquery_fields:
            missing_keys = [key for key in REQUIRED_OPTIONS if key not in options]
            if missing_keys:
                for key in missing_keys:
                    raise ERROR_REQUIRED_PARAMETER(key=f"options.{key}")

        # data_source_type 검증 (있는 경우)
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type not in ["bigquery", "http_file"]:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"options.data_source_type (invalid value: {data_source_type})"
            )

        # provider 검증 (있는 경우)
        provider = options.get("provider")
        if provider and provider != "google_cloud":
            raise ERROR_REQUIRED_PARAMETER(
                key=f"options.provider (invalid value: {provider})"
            )

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

        # 먼저 상세 사용량 테이블 확인
        detailed_table = f"{DETAILED_USAGE_TABLE_PREFIX}_{self.billing_account_id}"
        if detailed_table in bigquery_table_names:
            self.billing_table = detailed_table
            self.is_detailed_usage = True
        elif self.billing_table not in bigquery_table_names:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"Neither detailed table '{detailed_table}' nor standard table '{self.billing_table}' found in dataset. Available tables: {bigquery_table_names}"
            )
        else:
            self.is_detailed_usage = False

    def _create_google_sql(self, start):
        # 날짜 범위 검증 및 안전한 처리
        validated_start = self._validate_and_fix_date_range(start)

        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{validated_start}-01')
        """
        if self.target_project_id != "*":
            where_condition += f" AND project.id = '{self.target_project_id}'"

        # 상세 사용량 데이터인 경우 리소스 정보 포함
        if hasattr(self, "is_detailed_usage") and self.is_detailed_usage:
            resource_fields = """
              resource.name as resource_name,
              resource.global_name as resource_global_name,"""
            group_by_fields = "1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16"
        else:
            resource_fields = """
              NULL as resource_name,
              NULL as resource_global_name,"""
            group_by_fields = "1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16"

        query = f"""
            SELECT
              timestamp_trunc(usage_start_time, DAY) as billed_at,
              billing_account_id,
              service.description,
              sku.description as sku_description,
              project.id,
              project.name as project_name,
              IFNULL((location.region), 'global') as region_code,
              usage.pricing_unit,
              invoice.month,
              cost_type,
              currency,
              TO_JSON_STRING(labels) as labels,
              TO_JSON_STRING(IFNULL(tags, [])) as resource_tags,
              TO_JSON_STRING(credits) as credits_detail,{resource_fields}

              SUM(cost) as cost_after_credits,
              SUM(IFNULL(cost_at_list, cost)) as cost_at_list,
              SUM(cost)
                + SUM(IFNULL((SELECT SUM(c.amount)
                              FROM UNNEST(credits) c), 0))
                AS cost,
              -- AmortizedCost를 위한 credits_amount 계산 (크레딧 총액의 절대값)
              ABS(SUM(IFNULL((SELECT SUM(c.amount)
                              FROM UNNEST(credits) c), 0)))
                AS credits_amount,
              SUM(usage.amount_in_pricing_units) as usage_quantity,
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            GROUP BY {group_by_fields}
            ORDER BY billed_at desc
            ;
        """
        return query

    def _create_linked_accounts_google_sql(self, start):
        # 날짜 범위 검증 및 안전한 처리
        validated_start = self._validate_and_fix_date_range(start)

        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{validated_start}-01')
        """

        query = f"""
            SELECT
            distinct project.id, project.name as project_name
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            ;
        """
        return query

    @staticmethod
    def _change_datetime_to_string(date_time):
        return str(date_time.strftime("%Y-%m-%d"))

    @staticmethod
    def _get_start_month():
        start_time: datetime = datetime.utcnow() - timedelta(days=365)
        start_time = start_time.replace(day=1)

        start_time = start_time.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        return start_time.strftime("%Y-%m")

    @staticmethod
    def _validate_and_fix_date_range(start_date: str) -> str:
        """날짜 범위 검증 및 미래 날짜 보정

        Args:
            start_date: YYYY-MM 형식의 시작 날짜

        Returns:
            str: 검증된 시작 날짜 (미래 날짜인 경우 현재 날짜로 보정)
        """
        try:
            # 현재 날짜
            current_date = datetime.now()
            current_year_month = current_date.strftime("%Y-%m")

            # 입력 날짜 파싱
            if not start_date or len(start_date) != 7:  # YYYY-MM 형식 검증
                return current_year_month

            start_year, start_month = map(int, start_date.split("-"))
            start_datetime = datetime(start_year, start_month, 1)

            # 미래 날짜 검증
            if start_datetime > current_date:
                return current_year_month

            # 너무 과거 날짜 검증 (5년 이전)
            five_years_ago = current_date - timedelta(days=365 * 5)
            if start_datetime < five_years_ago:
                safe_start = five_years_ago.strftime("%Y-%m")
                return safe_start

            return start_date

        except Exception as e:
            _LOGGER.error(f"[_validate_and_fix_date_range] Date validation failed: {e}")
            # 오류 시 안전한 기본값 반환 (현재 월)
            return datetime.now().strftime("%Y-%m")

    def _get_data_source_type(self, options: dict, task_options: dict) -> str:
        """데이터 소스 타입 결정"""
        # task_options에서 우선 확인
        data_source_type = task_options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            return data_source_type

        # options에서 확인
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            return data_source_type

        # base_url 또는 bucket_name이 있으면 http_file 타입으로 자동 감지
        base_url_in_options = options.get("base_url")
        base_url_in_task_options = task_options.get("base_url")
        bucket_name_in_options = options.get("bucket_name")
        bucket_name_in_task_options = task_options.get("bucket_name")

        # HTTP 파일 관련 파라미터가 명확히 있는 경우에만 HTTP 파일로 결정
        has_http_file_params = (
            base_url_in_options
            or base_url_in_task_options
            or bucket_name_in_options
            or bucket_name_in_task_options
        )

        if has_http_file_params:
            return DATA_SOURCE_TYPES["http_file"]

        # BigQuery 필수 파라미터 확인 (task_options에서)
        bigquery_required_in_task = all(
            key in task_options
            for key in REQUIRED_TASK_OPTIONS[1:]  # 'start' 제외
        )
        if bigquery_required_in_task:
            return DATA_SOURCE_TYPES["bigquery"]

        # options에 BigQuery 필수 파라미터 확인
        bigquery_required_in_options = all(key in options for key in REQUIRED_OPTIONS)
        if bigquery_required_in_options:
            return DATA_SOURCE_TYPES["bigquery"]

        # 명시적 데이터 소스 타입이 없고 자동 감지도 실패한 경우 에러
        _LOGGER.error(
            "[_get_data_source_type] Cannot determine data source type - no valid parameters found"
        )
        _LOGGER.error(
            f"[_get_data_source_type] Available options keys: {list(options.keys())}"
        )
        _LOGGER.error(
            f"[_get_data_source_type] Available task_options keys: {list(task_options.keys())}"
        )
        raise ERROR_REQUIRED_PARAMETER(
            key="data_source_type (cannot auto-detect from available parameters)"
        )

    def _generate_date_range_patterns(
        self, project_id: str, start_period: str
    ) -> list[str]:
        """start부터 현재 월까지의 디렉토리 패턴 목록 생성

        Args:
            project_id: 프로젝트 ID
            start_period: 시작 기간 (YYYY-MM 형식)

        Returns:
            list[str]: 디렉토리 패턴 목록 (예: ["project/2024-01", "project/2024-02", ...])
        """
        import re
        from datetime import datetime

        # start_period 형식 검증 및 파싱
        if not start_period or not re.match(r"^\d{4}-\d{2}$", start_period):
            return [f"{project_id}/"]

        try:
            start_year, start_month = map(int, start_period.split("-"))

            # 월 범위 검증
            if not (1 <= start_month <= 12):
                return [f"{project_id}/"]

            current_date = datetime.now()
            current_year = current_date.year
            current_month = current_date.month

            patterns = []

            # start부터 현재 월까지 반복
            year = start_year
            month = start_month

            while (year < current_year) or (
                year == current_year and month <= current_month
            ):
                # 년도/월 형식으로 디렉토리 패턴 생성 (예: mkkang-project/2024/02/)
                # 끝에 /를 추가하여 정확한 디렉토리 매칭 (09-backup 등 방지)
                pattern = f"{project_id}/{year:04d}/{month:02d}/"
                patterns.append(pattern)

                # 다음 달로 이동
                month += 1
                if month > 12:
                    month = 1
                    year += 1

                # 무한 루프 방지 (너무 많은 패턴 생성 방지)
                if len(patterns) > 120:  # 10년치
                    break

            if not patterns:
                return [f"{project_id}/"]

            return patterns

        except Exception as e:
            _LOGGER.error(
                f"[_generate_date_range_patterns] Failed to generate patterns: {e}"
            )
            # 오류 시 기본 project 패턴 반환
            return [f"{project_id}/"]

    def _get_source_value(self, options: dict) -> str:
        """source 값을 추출하고 검증합니다.

        Args:
            options: 데이터 소스 옵션

        Returns:
            str: source 타입 (bigquery, gcs, http)

        Raises:
            ERROR_REQUIRED_PARAMETER: source 값이 없거나 지원하지 않는 값
        """
        # 유효한 source 타입 정의
        valid_sources = ["bigquery", "gcs", "http"]

        # source 값 추출 (options에서만)
        source = options.get("source")

        if not source:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"source (required parameter. Supported values: {', '.join(valid_sources)})"
            )

        if source not in valid_sources:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"source (invalid value: {source}. Supported values: {', '.join(valid_sources)})"
            )

        return source
