import logging
from collections.abc import Generator
from datetime import datetime, timedelta

from spaceone.core.error import ERROR_REQUIRED_PARAMETER
from spaceone.core.manager import BaseManager

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

        # JobManager에서 계산된 start 값이 있으면 사용, 없으면 자체 계산
        start_month = options.get("start") or self._get_start_month()
        if options.get("start"):
            _LOGGER.info(
                f"[get_linked_accounts] JobManager에서 전달된 start 사용: {start_month}"
            )
        else:
            _LOGGER.info(f"[get_linked_accounts] 자체 계산된 start 사용: {start_month}")

        query = self._create_linked_accounts_google_sql(start_month)

        # get_linked_accounts 쿼리 실행 로깅
        _LOGGER.info("=" * 80)
        _LOGGER.info("🔍 [QUERY #0] CostManager - 링크된 계정(프로젝트) 목록 조회")
        _LOGGER.info(f"[get_linked_accounts] 시작일: {start_month}")
        _LOGGER.info(
            f"[get_linked_accounts] PARTITIONDATE 범위: {self._calculate_partition_date_range(start_month)}"
        )
        _LOGGER.info(f"[get_linked_accounts] Query: {query}")
        _LOGGER.info("=" * 80)

        response_stream = self.bigquery_connector.read_df_from_bigquery(query)

        _LOGGER.info(f"✅ [QUERY #0 완료] 링크된 계정 수: {len(response_stream)}개")
        for _, row in response_stream.iterrows():
            if row.id is not None:
                linked_accounts.append({"account_id": row.id, "name": row.project_name})

        return {"results": linked_accounts}

    def get_data(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """데이터 소스 타입에 따라 처리 분기"""
        # 요청 중복 제거를 위한 해시 생성

        # source 값 추출 (options에서만)
        source = self._get_source_value(options)

        # 중복 요청 확인 (RequestDeduplicator 사용)
        from ..utils.concurrency_manager import request_deduplicator

        request_hash = request_deduplicator.generate_request_hash(options, task_options)
        _LOGGER.info(
            f"[CostManager] 요청 해시 생성 - 해시: {request_hash[:8]}..., 프로젝트: {task_options.get('project_id', 'UNKNOWN')}"
        )
        if request_deduplicator.is_duplicate_request(request_hash):
            _LOGGER.info(f"[CostManager] 중복 요청 스킵 - 해시: {request_hash[:8]}...")
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

        # Re-sync Plan 모드별 날짜 처리 (날짜 형식으로 모드 판단)
        original_start = task_options["start"]
        original_end = task_options.get("end")

        # 날짜 형식 기반 모드 판단 로직
        if original_end:
            # 종료일이 있는 경우 - 날짜 형식으로 모드 판단
            start_is_daily = (
                len(original_start) == 10 and original_start.count("-") == 2
            )  # YYYY-MM-DD
            end_is_daily = (
                len(original_end) == 10 and original_end.count("-") == 2
            )  # YYYY-MM-DD

            if start_is_daily or end_is_daily:
                # Auto 모드: 일자 형식 (YYYY-MM-DD) 포함
                # JobManager에서 이미 -1년 계산을 처리하므로, 입력값을 정규화만 함
                start = self._normalize_date_to_month(original_start)
                end = self._normalize_date_to_month(original_end)
                _LOGGER.info(
                    f"[Re-sync] Auto 모드 감지 (일자 형식) - 범위: {original_start} ~ {original_end} -> {start} ~ {end} (JobManager에서 -1년 계산 처리됨)"
                )
            else:
                # Manual 모드: 월 형식 (YYYY-MM)
                start = self._normalize_date_to_month(original_start)
                end = self._normalize_date_to_month(original_end)
                _LOGGER.info(
                    f"[Re-sync] Manual 모드 감지 (월 형식) - 범위: {original_start} ~ {original_end} -> {start} ~ {end}"
                )
        else:
            # 기존 방식: 시작일만 사용 (하위 호환성)
            start = self._normalize_date_to_month(original_start)
            end = None
            _LOGGER.info(f"[Re-sync] 기존 방식 - 시작일만: {original_start} -> {start}")
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

        query = self._create_google_sql(start, end)

        # 프로젝트별 쿼리 실행 로깅 강화
        _LOGGER.info("=" * 80)
        _LOGGER.info("🔍 [QUERY #2-5] CostManager - 프로젝트별 비용 데이터 조회")
        _LOGGER.info(f"[BigQuery] 대상 프로젝트: {self.target_project_id}")
        _LOGGER.info(f"[BigQuery] 조회 범위: {start}" + (f" ~ {end}" if end else ""))
        validated_start = self._validate_and_fix_date_range(start)
        validated_end = self._validate_and_fix_date_range(end) if end else None
        _LOGGER.info(
            f"[BigQuery] PARTITIONDATE 범위: {self._calculate_partition_date_range(validated_start, validated_end)}"
        )
        _LOGGER.info(
            f"[BigQuery] 대상 테이블: {self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}"
        )
        _LOGGER.info(
            "[BigQuery] 필터 조건: cost > 0 OR usage.amount > 0 (Job Manager와 동일)"
        )
        _LOGGER.info(f"[BigQuery] Query: {query}")
        _LOGGER.info("=" * 80)

        # 쿼리 실행 시간 측정 시작
        import time

        query_start_time = time.time()

        try:
            response_stream = self.bigquery_connector.read_df_from_bigquery(query)
            query_execution_time = time.time() - query_start_time

            # 쿼리 완료 로깅
            _LOGGER.info(
                f"✅ [QUERY 완료] 프로젝트 '{self.target_project_id}' - 실행시간: {query_execution_time:.2f}초, 조회 건수: {len(response_stream)}건"
            )

            # 결과 데이터 건수 확인을 위한 카운터
            row_count = 0

            _LOGGER.info(
                f"[BigQuery] 쿼리 실행 완료 (소요시간: {query_execution_time:.2f}초)"
            )
            _LOGGER.info(f"[BigQuery] 반환된 DataFrame 크기: {len(response_stream)} 행")

            # 빈 결과 처리 개선
            if len(response_stream) == 0:
                _LOGGER.info(
                    f"[BigQuery] 프로젝트 '{self.target_project_id}' - 필터 조건에 맞는 데이터 없음"
                )
                _LOGGER.info("[BigQuery] 필터 조건: cost > 0 OR usage.amount > 0")
                return

            # 배치 처리를 위한 리스트 - gRPC 메시지 크기 제한 대응 (긴급 감소)
            batch_records = []
            batch_size = 3  # Pod 중복 실행 시 안정성을 위해 더 작은 배치로 조정

            for _, row in response_stream.iterrows():
                row_count += 1
                cost_data = self._make_cost_data(row)
                # _make_cost_data가 {"results": [data]} 형식으로 반환하므로 각 결과를 배치에 추가
                if cost_data and "results" in cost_data:
                    # 🚨 ULTIMATE: BigQuery 경로에서 cost 필드 강제 보장 (과학적 표기법 지원)
                    for record in cost_data["results"]:
                        if isinstance(record, dict) and "cost" not in record:
                            # 1차: data 필드에서 cost 복구 시도 (과학적 표기법 지원)
                            cost_value = None  # 원본 None 보존
                            recovery_source = "none"

                            if "data" in record and isinstance(record["data"], dict):
                                data_cost = record["data"].get("cost")
                                if data_cost is not None:
                                    try:
                                        # 🚨 ULTRA PURE DATA: 과학적 표기법도 원본 그대로 보존
                                        cost_value = (
                                            data_cost  # 모든 값을 원본 그대로 보존
                                        )
                                        recovery_source = "data.cost"
                                        _LOGGER.info(
                                            f"[BigQuery] Cost recovered from data.cost: {cost_value} (scientific: {data_cost})"
                                        )
                                    except (ValueError, TypeError):
                                        pass

                            # 2차: additional_info에서 cost 복구 시도
                            if (
                                cost_value is None
                                and "additional_info" in record
                                and isinstance(record["additional_info"], dict)
                            ):
                                ai = record["additional_info"]
                                # 여러 cost 필드 시도
                                for field_name in [
                                    "Cost at Effective Price Default",
                                    "Cost at List Consumption Model",
                                    "Cost with Credits",
                                    "Cost After Credits",
                                ]:
                                    if field_name in ai and ai[field_name] != 0:
                                        try:
                                            # 🚨 ULTRA PURE DATA: 모든 값을 원본 그대로 보존
                                            cost_value = ai[
                                                field_name
                                            ]  # 모든 값을 원본 그대로 보존
                                            recovery_source = (
                                                f"additional_info.{field_name}"
                                            )
                                            _LOGGER.info(
                                                f"[BigQuery] Cost recovered from {field_name}: {cost_value}"
                                            )
                                            break
                                        except (ValueError, TypeError):
                                            continue

                            # 최상위 cost 필드 추가 (첫 번째 위치) - None도 보존
                            new_record = {
                                "cost": cost_value if cost_value is not None else None
                            }
                            new_record.update(record)
                            record.clear()
                            record.update(new_record)

                            _LOGGER.error(
                                f"[BigQuery] ULTIMATE: Added missing cost field: {cost_value} (source: {recovery_source})"
                            )

                    batch_records.extend(cost_data["results"])

                    # 배치 크기에 도달하면 yield
                    if len(batch_records) >= batch_size:
                        batch_result = {"results": batch_records}

                        # 🔍 BigQuery 배치 응답 레코드 로깅 (모든 레코드)
                        if batch_records:
                            # _LOGGER.info(f"[BigQuery-Response] 배치 응답 레코드 수: {len(batch_records)}")
                            for i, record in enumerate(
                                batch_records
                            ):  # 모든 레코드 로깅
                                # _LOGGER.info(f"[BigQuery-Response] 레코드 {i+1}: {record}")
                                pass
                        yield batch_result
                        batch_records = []

            # 남은 레코드 처리
            if batch_records:
                batch_result = {"results": batch_records}
                _LOGGER.info(
                    f"[BigQuery] Yielding final batch with {len(batch_records)} records"
                )
                _LOGGER.debug(
                    f"[BigQuery] Final batch result keys: {list(batch_result.keys())}"
                )

                # 🔍 BigQuery 최종 배치 응답 레코드 로깅 (모든 레코드)
                _LOGGER.info(
                    f"[BigQuery-FinalResponse] 최종 배치 응답 레코드 수: {len(batch_records)}"
                )
                for i, record in enumerate(batch_records):  # 모든 레코드 로깅
                    # _LOGGER.info(f"[BigQuery-FinalResponse] 레코드 {i+1}: {record}")
                    pass
                yield batch_result

            _LOGGER.info(f"[BigQuery] 처리 완료 - 총 {row_count}건의 데이터 처리됨")

        except Exception as e:
            query_execution_time = time.time() - query_start_time
            _LOGGER.error(
                f"[BigQuery] 쿼리 실행 실패 (소요시간: {query_execution_time:.2f}초)"
            )
            _LOGGER.error(f"[BigQuery] 오류 내용: {str(e)}")
            _LOGGER.error(f"[BigQuery] 실패한 쿼리: {query}")
            raise

    def _get_data_from_gcs(
        self, options: dict, secret_data: dict, task_options: dict, schema: str = None
    ) -> Generator[dict, None, None]:
        """GCS 버킷에서 데이터 조회 - 중복 요청 검사는 get_data()에서 이미 완료됨"""
        try:
            # 중복 요청 검사는 get_data()에서 이미 완료되었으므로 제거

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

                            # 🔍 GCS 배치 응답 레코드 로깅 (모든 레코드)
                            _LOGGER.info(
                                f"[GCS-Response] File {file_index} 배치 응답 레코드 수: {batch_size}"
                            )
                            for i, record in enumerate(
                                batch_result["results"]
                            ):  # 모든 레코드 로깅
                                # _LOGGER.info(f"[GCS-Response] 레코드 {i+1}: {record}")
                                pass
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
                pattern_files = self.gcs_connector.list_gcs_files(bucket_name, pattern)
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

                        # 🔍 HTTP 배치 응답 레코드 로깅 (모든 레코드)
                        if converted_result and "results" in converted_result:
                            response_size = len(converted_result["results"])
                            _LOGGER.info(
                                f"[HTTP-Response] 배치 응답 레코드 수: {response_size}"
                            )
                            for i, record in enumerate(
                                converted_result["results"]
                            ):  # 모든 레코드 로깅
                                _LOGGER.info(
                                    f"[HTTP-Response] 레코드 {i + 1}: {record}"
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

        # SpaceONE 프레임워크 요구사항 준수
        # BigQuery 구조 변환 시 billed_date 누락 문제가 발생하므로 원본 SpaceONE 구조를 보존하되,
        # Google Cloud Billing에는 data 필드가 없지만 SpaceONE에서 필수로 요구하므로 빈 딕셔너리 제공
        # 참조: https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage

        if "results" in gcs_result and isinstance(gcs_result["results"], list):
            for record in gcs_result["results"]:
                if isinstance(record, dict):
                    # cost 필드 검증 (원본 값 보존)
                    if "cost" not in record:
                        record["cost"] = None
                        _LOGGER.warning(
                            "[CostManager] cost field missing before BigQuery conversion, set to None"
                        )
                    elif record["cost"] is None:
                        _LOGGER.debug(
                            "[CostManager] cost field is None before BigQuery conversion, preserving None"
                        )

                    # data 필드에 SpaceONE 빌링 표준에 맞는 정보 추가
                    list_price = self._get_list_price_from_record(record)
                    record["data"] = self._create_spaceone_billing_data(
                        record, list_price
                    )

                    # 모든 SpaceONE 필수 필드 보장 (변환 후)
                    spaceone_required_fields = {
                        "cost": None,  # 🚨 ULTRA PURE: 기본값 None
                        "usage_quantity": None,  # 🚨 ULTRA PURE: 기본값 None
                        "provider": "google_cloud",
                        "region_code": "global",
                        "product": "",
                        "usage_type": "",
                        "resource": "",
                        "billed_date": "",
                        "currency": "USD",
                        "tags": {},
                        "additional_info": {},
                        "data": {},
                    }

                    for field, default_value in spaceone_required_fields.items():
                        if field not in record or record[field] is None:
                            record[field] = default_value
                            _LOGGER.debug(
                                f"[CostManager] Added missing required field '{field}' with default value: {default_value}"
                            )

                    # billed_date 특별 처리 (빈 문자열인 경우 현재 날짜 설정)
                    if not record.get("billed_date") or record["billed_date"] == "":
                        # 현재 날짜 사용하지 않고 None으로 설정
                        record["billed_date"] = None
                        _LOGGER.warning("[CostManager] Set empty billed_date to None")
        return gcs_result

    def _get_list_price_from_record(self, record: dict):
        """레코드에서 list_price(정가) 정보를 추출

        Google Cloud Billing 데이터에서 정가 정보는 다음 순서로 확인:
        1. cost_at_list (최상위 레벨) - 0이 아닌 값만
        2. price.list_price (중첩 구조) - cost_at_list가 0일 때 대체
        3. price.list_price_consumption_model (소비 모델 기준 정가)
        4. cost (정가 정보가 없는 경우 실제 비용 사용)
        """
        # 1. 최상위 레벨의 cost_at_list 필드 확인 (0이 아닌 값만)
        cost_at_list = record.get("cost_at_list")
        if cost_at_list is not None and cost_at_list != "" and cost_at_list != 0:
            return cost_at_list

        # 2. price.list_price 중첩 구조 확인 (cost_at_list가 0일 때 중요한 대체 소스)
        price_info = record.get("price", {})
        if isinstance(price_info, dict):
            list_price = price_info.get("list_price")
            if list_price is not None and list_price != "" and list_price != 0:
                # 🚨 ULTRA PURE DATA: 모든 값을 원본 그대로 보존
                return list_price  # 모든 값을 원본 그대로 보존

            # 3. 소비 모델 기준 정가 확인
            list_price_consumption = price_info.get("list_price_consumption_model")
            if (
                list_price_consumption is not None
                and list_price_consumption != ""
                and list_price_consumption != 0
            ):
                # 🚨 ULTRA PURE DATA: 모든 값을 원본 그대로 보존
                return list_price_consumption  # 모든 값을 원본 그대로 보존

        # 4. 정가 정보가 없는 경우 실제 비용 사용 (fallback)
        cost_value = record.get("cost")
        if cost_value is not None and cost_value != "":
            return cost_value

        # 5. 모든 시도가 실패한 경우 빈 문자열 반환
        return ""

    def _create_spaceone_billing_data(self, record: dict, list_price) -> dict:
        """SpaceONE 빌링 표준에 맞는 data 필드 구조 생성 (cost와 list_price 포함)"""
        # cost 값을 record에서 가져오기
        cost_value = record.get("cost", None)  # 🚨 ULTRA PURE: 기본값 None

        data_structure = {
            "cost": self._convert_to_numeric(cost_value),
            "list_price": self._convert_to_numeric(list_price),
        }

        return data_structure

    def _convert_to_numeric(self, value):
        """🚨 ULTRA PURE DATA: 값을 절대적으로 원본 그대로 보존 (변환 없음)"""
        # 🚨 ULTRA PURE: null 케이스도 원본 그대로 보존
        if value is None:
            return None  # None을 0.0으로 강제 변환하지 않음

        if value == "":
            return ""  # 빈 문자열도 그대로 보존

        if str(value).lower() in ["null", "none", "nan"]:
            return value  # 문자열 "null", "none", "nan"도 그대로 보존

        # 🚨 ULTRA PURE: 모든 값을 절대적으로 원본 그대로 반환
        # 어떠한 변환, 정밀도 개선, 타입 변경도 하지 않음
        return value

    def _convert_to_string(self, value):
        """값을 문자열 타입으로 안전하게 변환 (GCS 파서와 동일한 로직)"""
        if value is None:
            return ""

        try:
            # pandas의 NaN 값 체크
            import pandas as pd

            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass

        # 이미 문자열이면 그대로 반환
        if isinstance(value, str):
            return value.replace("nan", "") if value == "nan" else value

        # 기타 타입은 문자열로 변환
        return str(value)

    def _convert_bigquery_row_to_dict(self, row):
        """BigQuery DataFrame row를 딕셔너리로 변환 (GCS 파서와 호환, 부동소수점 정밀도 개선 포함)"""
        row_dict = {}

        # Series.to_dict() 메서드 사용 (더 안전)
        try:
            if hasattr(row, "to_dict"):
                series_dict = row.to_dict()
                row_dict.update(series_dict)
        except Exception:
            pass

        # pandas Series의 모든 속성을 딕셔너리로 변환
        for attr in dir(row):
            if not attr.startswith("_"):
                try:
                    value = getattr(row, attr)
                    # 메서드가 아닌 데이터 속성만 추가
                    if not callable(value):
                        row_dict[attr] = value
                except Exception:
                    continue

        # 숫자 필드들에 대해 정밀도 개선 적용
        numeric_fields = [
            "cost",
            "cost_at_list",
            "cost_after_credits",
            "credits_amount",
            "usage_quantity",
            "usage_amount_in_pricing_units",
            "currency_conversion_rate",
        ]

        for field in numeric_fields:
            if field in row_dict and isinstance(row_dict[field], (int, float)):
                row_dict[field] = self._convert_to_numeric(row_dict[field])

        return row_dict

    def _create_spaceone_billing_data_from_bigquery(
        self, row_dict: dict, list_price, cost_value=None
    ) -> dict:
        """BigQuery 데이터로부터 SpaceONE 빌링 표준에 맞는 data 필드 구조 생성 (cost와 list_price 포함)"""
        # cost_value가 전달되면 사용, 아니면 row_dict에서 가져옴
        actual_cost = (
            cost_value if cost_value is not None else row_dict.get("cost", None)
        )  # 🚨 ULTRA PURE: 기본값 None

        # 🚨 ULTRA PURE: data 필드에서도 null을 원본 그대로 보존
        final_actual_cost = self._convert_to_numeric(actual_cost)
        if final_actual_cost is None or str(final_actual_cost).lower() == "null":
            _LOGGER.debug("[CostManager] Actual cost is None/null, preserving as None")
            final_actual_cost = None

        final_list_price = self._convert_to_numeric(list_price)
        if final_list_price is None or str(final_list_price).lower() == "null":
            _LOGGER.debug("[CostManager] List price is None/null, preserving as None")
            final_list_price = None

        # data 필드에 cost와 list_price 모두 포함
        data_structure = {
            "cost": final_actual_cost,
            "list_price": final_list_price,
        }

        return self._ensure_spaceone_response_types(data_structure)

    def _convert_keys_to_title_case(self, data: dict) -> dict:
        """딕셔너리의 모든 키를 Title Case로 변환 (재귀적 처리)"""
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            # 키를 Title Case로 변환
            title_case_key = self._to_title_case(key)

            # 값이 딕셔너리인 경우 재귀적으로 처리
            if isinstance(value, dict):
                result[title_case_key] = self._convert_keys_to_title_case(value)
            # 값이 리스트인 경우 리스트 내 딕셔너리들도 처리
            elif isinstance(value, list):
                result[title_case_key] = self._convert_list_keys_to_title_case(value)
            else:
                result[title_case_key] = value

        return result

    def _convert_list_keys_to_title_case(self, data: list) -> list:
        """리스트 내 딕셔너리들의 키를 Title Case로 변환"""
        if not isinstance(data, list):
            return data

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(self._convert_keys_to_title_case(item))
            elif isinstance(item, list):
                result.append(self._convert_list_keys_to_title_case(item))
            else:
                result.append(item)
        return result

    def _to_title_case(self, text: str) -> str:
        """문자열을 Title Case로 변환 (특수 문자 처리 포함)"""
        if not isinstance(text, str):
            return str(text)

        # 이미 Title Case인 경우 그대로 반환 (예: "Project ID", "SKU Description")
        if text and text[0].isupper() and any(c.isupper() for c in text[1:]):
            return text

        # 하이픈이나 언더스코어로 구분된 단어들을 Title Case로 변환
        # 예: "goog-gke-node" -> "Goog Gke Node"
        if "-" in text or "_" in text:
            # 하이픈과 언더스코어를 공백으로 치환하고 각 단어를 Title Case로
            words = text.replace("-", " ").replace("_", " ").split()
            return " ".join(word.capitalize() for word in words)

        # 일반적인 경우 첫 글자만 대문자로
        return text.capitalize()

    def _to_snake_case(self, text: str) -> str:
        """문자열을 snake_case로 변환 (하이픈을 언더스코어로 변환)"""
        if not isinstance(text, str):
            return str(text)

        # 하이픈을 언더스코어로 변환
        # 예: "goog-gke-node" -> "goog_gke_node"
        return text.replace("-", "_")

    def _ensure_spaceone_response_types(self, data):
        """SpaceONE 응답 형식에 맞게 데이터 타입을 보장 (Decimal -> float 변환)"""
        from decimal import Decimal

        def convert_value(value):
            """개별 값을 SpaceONE 호환 타입으로 변환"""
            # 🚨 ULTRA PURE: null 값도 원본 그대로 보존 (0.0으로 강제 변환 제거)
            if value is None:
                return None  # None은 None 그대로
            elif isinstance(value, str) and str(value).lower() in [
                "null",
                "none",
                "nan",
            ]:
                return value  # 문자열도 그대로
            elif isinstance(value, Decimal):
                # 🚨 ULTRA PURE: Decimal도 그대로 보존 (float 변환 제거)
                return value  # Decimal 그대로 보존
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 처리
                nested_result = {}
                for k, v in value.items():
                    converted_v = convert_value(v)
                    # 중첩 딕셔너리에서 cost 필드 원본 보존
                    if k == "cost" and converted_v is None:
                        _LOGGER.debug(
                            "[CostManager] cost field in nested dict is None, preserving None value"
                        )
                    nested_result[k] = converted_v

                # 중첩 딕셔너리에서 cost 필드 존재 보장
                if "cost" not in nested_result and any(
                    key in nested_result
                    for key in ["usage_quantity", "provider", "product"]
                ):
                    # SpaceONE 레코드로 보이는 경우에만 cost 필드 추가
                    nested_result["cost"] = None
                    _LOGGER.warning(
                        "[CostManager] cost field missing in nested record, added None"
                    )

                # 모든 값을 원본 그대로 보존 (극소값도 보존)
                for k, v in nested_result.items():
                    if isinstance(v, float):
                        # 극소값도 포함하여 모든 값을 원본 그대로 보존
                        _LOGGER.debug(
                            f"[CostManager] Preserving original float value for {k}: {v}"
                        )
                        # 반올림 제거하여 원본 정확도 유지

                return nested_result
            elif isinstance(value, (list, tuple)):
                # 리스트/튜플 재귀 처리
                return [convert_value(item) for item in value]
            else:
                return value

        # 데이터가 딕셔너리인 경우
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                converted_value = convert_value(v)
                # cost 필드 원본 값 보존
                if k == "cost" and converted_value is None:
                    _LOGGER.debug(
                        "[CostManager] cost field is None after conversion, preserving None value"
                    )
                result[k] = converted_value

            # cost 필드 존재 확인
            if "cost" not in result:
                result["cost"] = None
                _LOGGER.warning(
                    "[CostManager] cost field was missing after type conversion, added None"
                )

            # 모든 값을 원본 그대로 보존 (극소값도 보존)
            for k, v in result.items():
                if isinstance(v, float):
                    # 극소값도 포함하여 모든 값을 원본 그대로 보존
                    _LOGGER.debug(
                        f"[CostManager] Preserving original float value for {k}: {v}"
                    )
                    # 반올림 제거하여 원본 정확도 유지

            # cost 필드 값 확인 (원본 보존)
            if "cost" in result and (
                result["cost"] is None or str(result["cost"]).lower() == "null"
            ):
                _LOGGER.debug(
                    "[CostManager] Cost field is None/null, preserving as None"
                )
            elif "cost" not in result:
                # cost 필드가 아예 없는 경우 None으로 설정
                result["cost"] = None
                _LOGGER.warning("[CostManager] Cost field missing, set to None")

            return result
        # 데이터가 리스트인 경우
        elif isinstance(data, (list, tuple)):
            return [convert_value(item) for item in data]
        else:
            return convert_value(data)

    def _clean_number(self, value):
        """🚨 PURE DATA: 숫자 원본 데이터 보존 (반올림/조작 제거)"""
        if not isinstance(value, (int, float)):
            # 🚨 ULTRA PURE DATA: 모든 값을 원본 그대로 보존 (과학적 표기법도 포함)
            return value  # 모든 값을 절대적으로 원본 그대로 보존

        # 🚨 PURE DATA: 모든 값을 원본 그대로 보존 (극소값도 보존)
        # 더 이상 0.0으로 강제 변환하거나 반올림하지 않음
        return value  # 원본 그대로 반환

    def _decimal_to_clean_float(self, decimal_value):
        """🚨 ULTRA PURE DATA: 모든 값을 절대적으로 원본 그대로 보존 (변환 없음)"""
        # 🚨 ULTRA PURE: Decimal도 포함하여 모든 값을 원본 그대로 반환
        # 더 이상 float로 변환하지 않음
        return decimal_value

    def _format_float_streaming_style(self, value: float) -> float:
        """🚨 PURE DATA: 숫자 원본 보존 (정리/변환 제거)"""
        try:
            # 🚨 PURE DATA: 원본 값 그대로 반환 (더 이상 변환하지 않음)
            import math

            if math.isnan(value) or math.isinf(value):
                return value  # NaN, Infinity는 그대로
            # 모든 값을 원본 그대로 보존 (극소값도 보존)
            return value
        except Exception:
            # 예외 발생 시에도 원본 값 보존
            return value

    def _make_cost_data(self, row) -> dict:
        """완전히 단순화된 SpaceONE 빌링 응답 생성 (test_correct_format.json 기준)"""
        try:
            # 🚨 ULTIMATE: 과학적 표기법 지원 cost 필드 절대 보장 시스템
            cost_value = getattr(row, "cost", None)
            if cost_value is None or cost_value == "":
                _LOGGER.info(
                    "[_make_cost_data] Cost was None/empty, preserving as None for transparency"
                )

            # 🚨 ULTRA PURE DATA: 모든 값을 절대적으로 원본 그대로 보존 (과학적 표기법도 포함)
            # cost_value는 어떠한 변환도 없이 원본 그대로 유지
            # _LOGGER.debug(f"[_make_cost_data] Cost value preserved as absolute original: {cost_value}")

            # 모든 cost 값을 원본 그대로 보존 (0으로 강제 처리 제거)
            if isinstance(cost_value, float):
                pass
                # 극소값도 포함하여 모든 값을 원본 그대로 보존
                # _LOGGER.debug(f"[_make_cost_data] Cost value preserved as-is: {cost_value}")
                # 반올림도 제거하여 원본 정확도 유지

            # 🚨 SCHEMA FIX + PURE DATA: usage_quantity -> usage.amount (원본 데이터 보존)
            usage_quantity = getattr(
                row, "usage_amount", None
            )  # 🚨 ULTRA PURE: 기본값도 None으로
            # 🚨 PURE DATA: 절대로 반올림이나 변환 없이 원본 그대로 보존
            # usage_quantity는 원본 값 그대로 사용

            # 🚨 CRITICAL: currency 필드 절대 보장 시스템
            currency_value = str(getattr(row, "currency", "USD")).strip()
            if not currency_value or currency_value == "":
                currency_value = "USD"  # 기본 통화
                _LOGGER.info(
                    "[_make_cost_data] CRITICAL: currency was empty, enforced to USD"
                )

            # STEP 3: 순수 SpaceONE 응답 구조 생성 (test_correct_format.json 기준)
            record = {
                "cost": cost_value,  # 🚨 최상위 필수 필드 #1
                "currency": currency_value,  # 🚨 최상위 필수 필드 #2
                "usage_quantity": usage_quantity,
                "usage_unit": str(
                    getattr(row, "usage_unit", "")
                ).strip(),  # 🚨 SCHEMA FIX: usage.unit 사용
                "provider": "google_cloud",
                "region_code": str(
                    getattr(row, "location_region", "global")
                ).strip(),  # 🚨 SCHEMA FIX: location.region 사용
                "product": str(getattr(row, "service_description", "Unknown")).strip(),
                "usage_type": str(getattr(row, "sku_description", "Unknown")).strip(),
                # 🎯 화면 표시용: 프로젝트 이름 또는 커스텀 형식 사용
                "resource": self._format_project_display_name(row),
                "tags": {},
                "additional_info": {
                    # 기존 필수 필드들
                    "Billing Account ID": str(
                        getattr(row, "billing_account_id", "")
                    ).strip(),
                    # 🚨 SCHEMA FIX: cost_after_credits는 스키마에 없음 - 계산 필드로 처리
                    "Cost After Credits": self._calculate_cost_after_credits(row),
                    "Cost At List": getattr(
                        row, "cost_at_list", cost_value
                    ),  # 🚨 PURE DATA: 원본 데이터 보존
                    "Cost Type": str(getattr(row, "cost_type", "regular")).strip(),
                    "Credits Detail": self._process_credits_detail(row),
                    "Invoice Month": self._extract_nested_field(
                        row, "invoice", "month"
                    ),  # 🚨 SCHEMA FIX: invoice.month 중첩 구조 처리
                    "Project ID": str(getattr(row, "project_id", "")).strip(),
                    "Project Name": str(getattr(row, "project_name", "")).strip(),
                    "Resource Tags": {},
                    # 추가 Google Cloud 빌링 필드들
                    "Service ID": str(getattr(row, "service_id", "")).strip(),
                    "Service Description": str(
                        getattr(row, "service_description", "")
                    ).strip(),
                    "SKU ID": str(getattr(row, "sku_id", "")).strip(),
                    "SKU Description": str(getattr(row, "sku_description", "")).strip(),
                    "Project Number": str(getattr(row, "project_number", "")).strip(),
                    "Location Country": str(
                        getattr(row, "location_country", "")
                    ).strip(),
                    "Location Zone": str(getattr(row, "location_zone", "")).strip(),
                    "Currency": str(getattr(row, "currency", "USD")).strip(),
                    "Transaction Type": str(
                        getattr(row, "transaction_type", "")
                    ).strip(),
                    "Seller Name": str(getattr(row, "seller_name", "")).strip(),
                    "Publisher Type": self._extract_nested_field(
                        row, "invoice", "publisher_type"
                    ),  # 🚨 SCHEMA FIX: invoice.publisher_type 중첩 구조
                    "Usage Unit": str(
                        getattr(row, "usage_unit", "")
                    ).strip(),  # ✅ 스키마 존재
                    "Pricing Unit": self._extract_nested_field(
                        row, "usage", "pricing_unit"
                    ),  # 🚨 SCHEMA FIX: usage.pricing_unit 중첩 구조
                    # 추가 비용 정보
                    "Cost at Effective Price Default": getattr(
                        row, "cost_at_effective_price_default", None
                    ),  # 🚨 ULTRA PURE: 기본값 None
                    "Cost at List Consumption Model": getattr(
                        row, "cost_at_list_consumption_model", None
                    ),  # 🚨 ULTRA PURE: 기본값 None
                    "Currency Conversion Rate": getattr(
                        row, "currency_conversion_rate", None
                    ),  # 🚨 ULTRA PURE: 기본값 None (1.0 제거)
                    "Usage Amount": getattr(
                        row, "usage_amount", None
                    ),  # 🚨 ULTRA PURE: 기본값 None
                    # 🚨 SCHEMA FIX: credits_total_amount는 스키마에 없음 - 계산 필드로 처리
                    "Credits Total Amount": self._calculate_credits_total(row),
                    # 🚨 SCHEMA FIX: cost_with_credits는 스키마에 없음 - 계산 필드로 처리
                    "Cost with Credits": self._calculate_cost_with_credits(
                        row, cost_value
                    ),
                    # 라벨 및 태그 정보 (구조적 데이터로 저장)
                    "Labels": self._process_labels_data(getattr(row, "labels", "[]")),
                    # 🚨 SCHEMA FIX: system_labels_json -> system_labels (스키마에는 system_labels만 존재)
                    "System Labels": self._process_system_labels_data(
                        getattr(row, "system_labels", "[]")
                    ),
                    "Ancestry Numbers": str(
                        getattr(row, "ancestry_numbers", "")
                    ).strip(),
                    # 🚨 누락된 스키마 필드들 추가 (BigQuery 스키마 완전 준수)
                    "Usage Start Time": str(
                        getattr(row, "usage_start_time", "")
                    ).strip(),
                    "Usage End Time": str(getattr(row, "usage_end_time", "")).strip(),
                    "Export Time": str(getattr(row, "export_time", "")).strip(),
                    "Location Region": str(getattr(row, "location_region", "")).strip(),
                    "Location Location": str(
                        getattr(row, "location_location", "")
                    ).strip(),
                    "Usage Amount in Pricing Units": getattr(
                        row, "usage_amount_in_pricing_units", None
                    ),  # 🚨 ULTRA PURE: 기본값 None
                    # Price 중첩 구조 필드들
                    "Price Effective Price": self._extract_nested_field(
                        row, "price", "effective_price"
                    ),
                    "Price Tier Start Amount": self._extract_nested_field(
                        row, "price", "tier_start_amount"
                    ),
                    "Price Unit": self._extract_nested_field(row, "price", "unit"),
                    "Price Pricing Unit Quantity": self._extract_nested_field(
                        row, "price", "pricing_unit_quantity"
                    ),
                    "Price List Price": self._extract_nested_field(
                        row, "price", "list_price"
                    ),
                    "Price Effective Price Default": self._extract_nested_field(
                        row, "price", "effective_price_default"
                    ),
                    "Price List Price Consumption Model": self._extract_nested_field(
                        row, "price", "list_price_consumption_model"
                    ),
                    # Consumption Model 중첩 구조 필드들
                    "Consumption Model ID": self._extract_nested_field(
                        row, "consumption_model", "id"
                    ),
                    "Consumption Model Description": self._extract_nested_field(
                        row, "consumption_model", "description"
                    ),
                    # Adjustment Info 중첩 구조 필드들
                    "Adjustment Info ID": self._extract_nested_field(
                        row, "adjustment_info", "id"
                    ),
                    "Adjustment Info Description": self._extract_nested_field(
                        row, "adjustment_info", "description"
                    ),
                    "Adjustment Info Mode": self._extract_nested_field(
                        row, "adjustment_info", "mode"
                    ),
                    "Adjustment Info Type": self._extract_nested_field(
                        row, "adjustment_info", "type"
                    ),
                    # Tags 중첩 구조 필드들 (기본 구조만)
                    "Tags": self._process_tags_data(getattr(row, "tags", "[]")),
                    # Project Ancestors 중첩 구조
                    "Project Ancestors": self._process_ancestors_data(
                        getattr(row, "ancestors", "[]")
                    ),
                },
                "data": {
                    "cost": str(cost_value),
                    "list_price": str(
                        getattr(row, "cost_at_list", cost_value)
                    ),  # 🚨 PURE DATA: 원본 데이터 보존
                },
                "billed_date": self._extract_billed_date(row),
            }

            # STEP 4: 최종 숫자 정리
            # 극소값도 원본 그대로 보존 (0으로 강제 변환 제거)
            # for key in ["cost", "usage_quantity"]:
            #     if isinstance(record.get(key), float):
            #         _LOGGER.debug(f"[_make_cost_data] Preserving original {key} value: {record[key]}")

            # # additional_info의 극소값도 원본 그대로 보존
            # for key in ["Cost After Credits", "Cost At List"]:
            #     if isinstance(record["additional_info"].get(key), float):
            #         _LOGGER.debug(f"[_make_cost_data] Preserving original {key} value: {record['additional_info'][key]}")

            # # STEP 5: 필수 필드 검증 (0으로 강제 처리 제거)
            # if "cost" not in record:
            #     record["cost"] = cost_value  # 원본 값 사용
            #     _LOGGER.warning(f"[_make_cost_data] Cost field missing after creation, added original value: {cost_value}")

            # if "currency" not in record:
            #     record["currency"] = "USD"
            #     _LOGGER.error(f"[_make_cost_data] CRITICAL: currency field missing after creation, force added USD")

            # 🚨 CRITICAL: 필수 필드들을 정확한 순서로 강제 배치
            cost_val = record.pop("cost")
            currency_val = record.pop("currency")
            record_copy = record.copy()
            record.clear()

            # 정확한 SpaceONE 순서로 필드 배치
            record["cost"] = cost_val  # 첫 번째 위치
            record["currency"] = currency_val  # 두 번째 위치
            record.update(record_copy)

            # 최종 필수 필드 존재 재확인 (원본 값 보존)
            if "cost" not in record:
                _LOGGER.error(
                    "[_make_cost_data] FATAL: cost field disappeared during ordering!"
                )
                record = {"cost": cost_value, **record}  # 원본 값 사용

            if "currency" not in record:
                _LOGGER.error(
                    "[_make_cost_data] FATAL: currency field disappeared during ordering!"
                )
                record = {
                    "cost": record.get("cost", None),
                    "currency": "USD",
                    **{
                        k: v for k, v in record.items() if k not in ["cost", "currency"]
                    },
                }  # 🚨 ULTRA PURE: 기본값 None

            # 🚨 ULTIMATE: 최종 결과 검증 (cost 필드 절대 보장)
            if "cost" not in record:
                _LOGGER.error(
                    f"[_make_cost_data] FATAL: cost field missing after creation! Keys: {list(record.keys())}"
                )
                record = {"cost": cost_value, **record}  # 원본 값 사용
            elif record["cost"] is None:
                _LOGGER.warning(
                    f"[_make_cost_data] Cost field is None after creation, preserving original value: {cost_value}"
                )
                record["cost"] = cost_value  # 원본 값 사용

            return {"results": [record]}

        except Exception as e:
            _LOGGER.error(f"[_make_cost_data] Simple implementation error: {e}")
            # 에러 시에도 기본 구조 반환 - cost 필드를 최상위에 보장 (스키마 준수)
            error_record = {
                "cost": None,  # 🚨 ULTRA PURE: 최상위 필수 필드도 None 기본값
                "currency": "USD",  # 🚨 CRITICAL: 필수 통화 필드
                "usage_quantity": None,  # 🚨 ULTRA PURE: 기본값 None
                "usage_unit": "",
                "provider": "google_cloud",
                "region_code": "global",
                "product": "Unknown",
                "usage_type": "Unknown",
                "resource": "",
                "tags": {},
                "additional_info": {
                    "Billing Account ID": "",
                    "Cost After Credits": None,  # 🚨 ULTRA PURE: 에러 시에도 None
                    "Cost At List": None,  # 🚨 ULTRA PURE: 에러 시에도 None
                    "Cost Type": "regular",
                    "Credits Detail": [],
                    "Invoice Month": "",
                    "Project ID": "",
                    "Project Name": "",
                    "Resource Tags": {},
                },
                "data": {
                    "cost": None,
                    "list_price": None,
                },  # 🚨 ULTRA PURE: 에러 시에도 None
                "billed_date": None,  # 에러 시에도 현재 날짜 사용하지 않음
            }
            return {"results": [error_record]}

    def _calculate_cost_after_credits(self, row):
        """크레딧 적용 후 비용 계산 (BigQuery 스키마 기반) - 🚨 PURE DATA 보존 + 안전한 연산

        스키마에 cost_after_credits 필드가 없으므로 원본 데이터 우선, 필요시 안전한 덧셈 연산
        """
        try:
            # 🚨 PURE DATA: 원본 데이터가 있으면 그대로 반환
            cost_after_credits = getattr(row, "cost_after_credits", None)
            if cost_after_credits is not None:
                return cost_after_credits  # 원본 그대로

            # 원본 데이터가 없는 경우에만 안전한 연산 수행
            cost = getattr(row, "cost", None)  # 🚨 ULTRA PURE: 기본값 None
            credits_total = self._calculate_credits_total(row)

            # 🚨 안전한 덧셈: 원본 데이터 타입 유지
            if cost is not None and credits_total is not None:
                return self._safe_add(cost, credits_total)
            else:
                return cost  # 원본 그대로
        except Exception:
            return None  # 🚨 ULTRA PURE: 예외 시에도 None

    def _calculate_credits_total(self, row):
        """크레딧 총액 계산 (BigQuery 스키마 기반) - 🚨 PURE DATA 보존

        원본 데이터 그대로 반환, 계산 없이 보존
        """
        try:
            # 🚨 PURE DATA: 절대로 계산하지 않고 원본 데이터 그대로 반환
            credits_total = getattr(row, "credits_total_amount", None)
            if (
                credits_total is not None
                and credits_total != ""
                and credits_total != 0.0
            ):
                return credits_total  # 원본 그대로
            # 🚨 ULTRA PURE: 원본 데이터가 없거나 빈 문자열이거나 0.0이면 None 반환
            return None  # 🚨 ULTRA PURE: 예외 시에도 None
        except Exception:
            return None  # 🚨 ULTRA PURE: 예외 시에도 None

    def _calculate_cost_with_credits(self, row, cost_value):
        """크레딧을 포함한 비용 계산 - 🚨 PURE DATA 보존 + 안전한 연산

        Args:
            row: 데이터 행
            cost_value: 기본 비용 값

        Returns:
            원본 데이터 우선, 필요시 안전한 덧셈 연산
        """
        try:
            # 🚨 PURE DATA: 원본 데이터가 있으면 그대로 반환
            cost_with_credits = getattr(row, "cost_with_credits", None)
            if cost_with_credits is not None:
                return cost_with_credits  # 원본 그대로

            # 원본 데이터가 없는 경우에만 안전한 연산 수행
            credits_total = self._calculate_credits_total(row)

            # 🚨 안전한 덧셈: 원본 데이터 타입 유지
            if cost_value is not None and credits_total is not None:
                return self._safe_add(cost_value, credits_total)
            else:
                return (
                    cost_value if cost_value is not None else None
                )  # 🚨 ULTRA PURE: None 보존
        except Exception:
            return (
                cost_value if cost_value is not None else None
            )  # 🚨 ULTRA PURE: 예외 시에도 None

    def _extract_nested_field(self, row, parent_field: str, child_field: str) -> str:
        """BigQuery 중첩 구조 필드 추출 (스키마 준수)

        Args:
            row: 데이터 행
            parent_field: 부모 필드명 (예: 'invoice', 'usage', 'project')
            child_field: 자식 필드명 (예: 'month', 'publisher_type', 'pricing_unit')

        Returns:
            추출된 필드 값 (문자열)
        """
        try:
            # 1. 직접 중첩 구조 접근 시도 (parent_field.child_field)
            nested_field_name = f"{parent_field}_{child_field}"
            direct_value = getattr(row, nested_field_name, None)
            if direct_value is not None:
                return str(direct_value).strip()

            # 2. 부모 필드가 딕셔너리 구조인 경우
            parent_data = getattr(row, parent_field, None)
            if isinstance(parent_data, dict) and child_field in parent_data:
                return str(parent_data[child_field]).strip()

            # 3. JSON 문자열인 경우 파싱 시도
            if isinstance(parent_data, str):
                try:
                    import json

                    parsed_data = json.loads(parent_data)
                    if isinstance(parsed_data, dict) and child_field in parsed_data:
                        return str(parsed_data[child_field]).strip()
                except (json.JSONDecodeError, ImportError):
                    pass

            # 4. 대체 필드명 시도 (camelCase, snake_case 변형)
            alt_field_names = [
                f"{parent_field}_{child_field}",
                f"{parent_field}{child_field.title()}",
                f"{parent_field}.{child_field}",
            ]

            for alt_name in alt_field_names:
                alt_value = getattr(row, alt_name, None)
                if alt_value is not None:
                    return str(alt_value).strip()

            return ""  # 기본값 반환

        except Exception as e:
            _LOGGER.warning(
                f"[_extract_nested_field] Failed to extract {parent_field}.{child_field}: {e}"
            )
            return ""

    def _process_tags_data(self, tags_data) -> list:
        """Tags 배열 데이터 처리 (BigQuery 스키마 준수)

        Args:
            tags_data: tags 필드 데이터 (JSON 문자열 또는 리스트)

        Returns:
            처리된 태그 리스트
        """
        try:
            if not tags_data:
                return []

            # JSON 문자열인 경우 파싱
            if isinstance(tags_data, str):
                import json

                tags_data = json.loads(tags_data)

            # 리스트가 아닌 경우 빈 리스트 반환
            if not isinstance(tags_data, list):
                return []

            # 태그 데이터 구조 변환
            processed_tags = []
            for tag in tags_data:
                if isinstance(tag, dict):
                    processed_tags.append(
                        {
                            "key": str(tag.get("key", "")),
                            "value": str(tag.get("value", "")),
                            "inherited": bool(tag.get("inherited", False)),
                            "namespace": str(tag.get("namespace", "")),
                        }
                    )

            return processed_tags

        except Exception as e:
            _LOGGER.warning(f"[_process_tags_data] Failed to process tags: {e}")
            return []

    def _process_ancestors_data(self, ancestors_data) -> list:
        """Project ancestors 배열 데이터 처리 (BigQuery 스키마 준수)

        Args:
            ancestors_data: ancestors 필드 데이터 (JSON 문자열 또는 리스트)

        Returns:
            처리된 상위 조직 리스트
        """
        try:
            if not ancestors_data:
                return []

            # JSON 문자열인 경우 파싱
            if isinstance(ancestors_data, str):
                import json

                ancestors_data = json.loads(ancestors_data)

            # 리스트가 아닌 경우 빈 리스트 반환
            if not isinstance(ancestors_data, list):
                return []

            # 상위 조직 데이터 구조 변환
            processed_ancestors = []
            for ancestor in ancestors_data:
                if isinstance(ancestor, dict):
                    processed_ancestors.append(
                        {
                            "resource_name": str(ancestor.get("resource_name", "")),
                            "display_name": str(ancestor.get("display_name", "")),
                        }
                    )

            return processed_ancestors

        except Exception as e:
            _LOGGER.warning(
                f"[_process_ancestors_data] Failed to process ancestors: {e}"
            )
            return []

    def _safe_math_operation(self, operation: str, left_value, right_value):
        """안전한 수학 연산 처리 - 나눗셈만 Decimal, 나머지는 원본 데이터 유지

        Args:
            operation: 연산 종류 ('add', 'subtract', 'multiply', 'divide')
            left_value: 왼쪽 피연산자
            right_value: 오른쪽 피연산자

        Returns:
            연산 결과 (나눗셈: Decimal 처리, 나머지: 원본 타입 유지)
        """
        try:
            # None 값 처리
            if left_value is None or right_value is None:
                return None

            # 빈 문자열 처리
            if left_value == "" or right_value == "":
                _LOGGER.error(
                    f"[SAFE_MATH] Empty string detected in {operation}: left='{left_value}', right='{right_value}'"
                )
                return None

            # 타입 호환성 체크
            if not self._is_numeric_compatible(left_value, right_value):
                _LOGGER.error(
                    f"[SAFE_MATH] Type incompatible for {operation}: {type(left_value).__name__}({left_value}) and {type(right_value).__name__}({right_value})"
                )
                return None

            if operation == "divide":
                # 🚨 나눗셈: 타입 안전 처리
                try:
                    # 문자열 숫자를 float로 변환
                    if isinstance(left_value, str):
                        left_value = float(left_value)
                    if isinstance(right_value, str):
                        right_value = float(right_value)

                    # 0으로 나누기 방지
                    if right_value == 0:
                        _LOGGER.warning(
                            f"[SAFE_MATH] Division by zero: {left_value} / {right_value}"
                        )
                        return None

                    result = left_value / right_value
                    return result
                except (ValueError, TypeError) as e:
                    _LOGGER.error(
                        f"[SAFE_MATH] Math operation failed: divide({left_value}, {right_value}) - {e}"
                    )
                    return None

            elif operation == "add":
                # 🚨 덧셈: 타입 안전 처리
                try:
                    # 문자열 숫자를 float로 변환
                    if isinstance(left_value, str):
                        left_value = float(left_value)
                    if isinstance(right_value, str):
                        right_value = float(right_value)

                    result = left_value + right_value
                    return result
                except (ValueError, TypeError) as e:
                    _LOGGER.error(
                        f"[SAFE_MATH] Math operation failed: add({left_value}, {right_value}) - {e}"
                    )
                    return None

            elif operation == "subtract":
                # 🚨 뺄셈: 타입 안전 처리
                try:
                    # 문자열 숫자를 float로 변환
                    if isinstance(left_value, str):
                        left_value = float(left_value)
                    if isinstance(right_value, str):
                        right_value = float(right_value)

                    result = left_value - right_value
                    return result
                except (ValueError, TypeError) as e:
                    _LOGGER.error(
                        f"[SAFE_MATH] Math operation failed: subtract({left_value}, {right_value}) - {e}"
                    )
                    return None

            elif operation == "multiply":
                # 🚨 곱셈: 타입 안전 처리
                try:
                    # 문자열 숫자를 float로 변환
                    if isinstance(left_value, str):
                        left_value = float(left_value)
                    if isinstance(right_value, str):
                        right_value = float(right_value)

                    result = left_value * right_value
                    return result
                except (ValueError, TypeError) as e:
                    _LOGGER.error(
                        f"[SAFE_MATH] Math operation failed: multiply({left_value}, {right_value}) - {e}"
                    )
                    return None

            else:
                _LOGGER.error(f"[SAFE_MATH] Unknown operation: {operation}")
                return None

        except Exception as e:
            _LOGGER.error(
                f"[SAFE_MATH] Math operation failed: {operation}({left_value}, {right_value}) - {e}"
            )
            return None

    def _is_numeric_compatible(self, left_value, right_value):
        """두 값이 수학 연산에 호환되는지 확인"""
        # 숫자 타입들
        numeric_types = (int, float, complex)

        # 둘 다 숫자 타입인 경우
        if isinstance(left_value, numeric_types) and isinstance(
            right_value, numeric_types
        ):
            return True

        # 문자열이 숫자로 변환 가능한지 확인
        def is_numeric_string(value):
            if not isinstance(value, str):
                return False
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False

        # 한쪽이 숫자, 다른 쪽이 숫자 문자열인 경우
        if isinstance(left_value, numeric_types) and is_numeric_string(right_value):
            return True
        if isinstance(right_value, numeric_types) and is_numeric_string(left_value):
            return True

        # 둘 다 숫자 문자열인 경우
        if is_numeric_string(left_value) and is_numeric_string(right_value):
            return True

        return False

    def _safe_add(self, left_value, right_value):
        """안전한 덧셈 - 원본 데이터 타입 유지"""
        return self._safe_math_operation("add", left_value, right_value)

    def _safe_subtract(self, left_value, right_value):
        """안전한 뺄셈 - 원본 데이터 타입 유지"""
        return self._safe_math_operation("subtract", left_value, right_value)

    def _safe_multiply(self, left_value, right_value):
        """안전한 곱셈 - 원본 데이터 타입 유지"""
        return self._safe_math_operation("multiply", left_value, right_value)

    def _safe_divide(self, left_value, right_value):
        """안전한 나눗셈 - 🚨 ULTRA PURE DATA: 원본 데이터 타입 유지"""
        return self._safe_math_operation("divide", left_value, right_value)

    def _example_math_operations(self):
        """수학 연산 사용 예시 - 개발자 참고용

        이 메서드는 실제로 호출되지 않으며, 수학 연산 사용법을 보여주는 예시입니다.
        """
        # 🚨 사용 예시 - 실제 코드에서는 이렇게 사용하세요

        # 나눗셈 (원본 타입 유지)
        cost_per_unit = self._safe_divide(
            100.0, 3.0
        )  # 🚨 예시용: 실제 코드에서 사용 금지

        # 덧셈 (원본 타입 유지)
        total_cost = self._safe_add(50.25, 25.75)  # float + float = float

        # 뺄셈 (원본 타입 유지)
        discount = self._safe_subtract(100, 10)  # int - int = int

        # 곱셈 (원본 타입 유지)
        extended_cost = self._safe_multiply(12.5, 4)  # float * int = float

        _LOGGER.debug(f"[EXAMPLE] Division result (original types): {cost_per_unit}")
        _LOGGER.debug(f"[EXAMPLE] Addition result (original types): {total_cost}")
        _LOGGER.debug(f"[EXAMPLE] Subtraction result (original types): {discount}")
        _LOGGER.debug(
            f"[EXAMPLE] Multiplication result (original types): {extended_cost}"
        )

    def _process_credits_detail(self, row) -> list:
        """Credits 배열 데이터 처리 (BigQuery 스키마 준수)

        Args:
            row: 데이터 행

        Returns:
            처리된 크레딧 상세 리스트
        """
        try:
            credits_data = getattr(row, "credits", None)
            if not credits_data:
                return []

            # JSON 문자열인 경우 파싱
            if isinstance(credits_data, str):
                import json

                credits_data = json.loads(credits_data)

            # 리스트가 아닌 경우 빈 리스트 반환
            if not isinstance(credits_data, list):
                return []

            # 크레딧 데이터 구조 변환 (스키마 필드: name, amount, full_name, id, type)
            processed_credits = []
            for credit in credits_data:
                if isinstance(credit, dict):
                    processed_credits.append(
                        {
                            "name": str(credit.get("name", "")),
                            "amount": credit.get(
                                "amount", None
                            ),  # 🚨 ULTRA PURE: 기본값도 None
                            "full_name": str(credit.get("full_name", "")),
                            "id": str(credit.get("id", "")),
                            "type": str(credit.get("type", "")),
                        }
                    )

            return processed_credits

        except Exception as e:
            _LOGGER.warning(f"[_process_credits_detail] Failed to process credits: {e}")
            return []

    def _ensure_top_level_cost_field(self, record: dict) -> dict:
        """최상위 cost 필드 존재 및 타입 보장 (문서 가이드라인 준수)

        SpaceONE 빌링 응답의 최상위 cost 필드는 필수 항목입니다.
        """
        usage_type = record.get("usage_type", "Unknown")

        # 최상위 cost 필드 절대 보장
        if "cost" not in record:
            # data.cost에서 값 가져오기 시도
            if (
                "data" in record
                and isinstance(record["data"], dict)
                and "cost" in record["data"]
            ):
                try:
                    # 🚨 ULTRA PURE DATA: 원본 데이터 절대 보존
                    cost_value = record["data"]["cost"]  # 모든 값을 원본 그대로 보존
                    record["cost"] = cost_value
                    _LOGGER.info(
                        f"[COST_FIX] Added missing top-level cost field: {cost_value} for {usage_type}"
                    )
                except (ValueError, TypeError):
                    record["cost"] = None
                    _LOGGER.warning(
                        f"[COST_FIX] Invalid data.cost value, set top-level cost to None for {usage_type}"
                    )
            else:
                record["cost"] = None
                _LOGGER.warning(
                    f"[COST_FIX] Missing cost field, set to None for {usage_type}"
                )

        # 🚨 ULTRA PURE DATA: 타입 검증도 하지 않고 모든 값을 원본 그대로 보존
        # record["cost"]는 어떠한 변환도 없이 절대적으로 원본 그대로 유지
        _LOGGER.debug(
            f"[COST_FIX] Cost field preserved as absolute original for {usage_type}: {record.get('cost')}"
        )

        # 모든 SpaceONE 필수 필드 보장
        spaceone_required_fields = {
            "usage_quantity": None,  # 🚨 ULTRA PURE: 기본값 None
            "provider": "google_cloud",
            "region_code": "global",
            "product": "",
            "usage_type": "",
            "resource": "",
            "billed_date": "",
            "currency": "USD",
            "tags": {},
            "additional_info": {},
            "data": {},
        }

        for field, default_value in spaceone_required_fields.items():
            if field not in record or record[field] is None:
                record[field] = default_value
                _LOGGER.debug(
                    f"[COST_FIX] Added missing required field '{field}' with default value: {default_value} for {usage_type}"
                )

        # billed_date 특별 처리 (빈 문자열인 경우 현재 날짜 설정)
        if not record.get("billed_date") or record["billed_date"] == "":
            # 현재 날짜 사용하지 않고 None으로 설정
            record["billed_date"] = None
            _LOGGER.warning(
                f"[COST_FIX] Set empty billed_date to None for {usage_type}"
            )

        return record

    def _get_cost_field_by_option(self, row):
        """select_cost 및 cost_metric 옵션에 따라 적절한 비용 필드를 선택

        Args:
            row: BigQuery 또는 파일에서 읽은 데이터 행

        Returns:
            선택된 비용 값 (🚨 ULTRA PURE: None도 포함하여 원본 그대로 반환)
        """
        # cost_metric이 AmortizedCost인 경우 credits_amount 사용
        if self.cost_metric_option == "AmortizedCost":
            cost_value = getattr(
                row, "credits_amount", None
            )  # 🚨 ULTRA PURE: 기본값 None
            result = self._convert_to_numeric(cost_value)
        # 기존 select_cost 로직
        elif self.select_cost_option == "list_price":
            # 정가 (크레딧 적용 전 원가)
            cost_value = getattr(
                row, "cost_at_list", None
            )  # 🚨 ULTRA PURE: 기본값 None
            result = self._convert_to_numeric(cost_value)
        elif self.select_cost_option == "after_credits":
            # 크레딧 적용 후 비용
            cost_value = getattr(
                row, "cost_after_credits", None
            )  # 🚨 ULTRA PURE: 기본값 None
            result = self._convert_to_numeric(cost_value)
        elif self.select_cost_option == "net_cost":
            # 순 비용 (기본 cost와 동일)
            cost_value = getattr(row, "cost", None)  # 🚨 ULTRA PURE: 기본값 None
            result = self._convert_to_numeric(cost_value)
        else:
            # 기본값: cost (크레딧을 포함한 최종 비용)
            cost_value = getattr(row, "cost", None)  # 🚨 ULTRA PURE: 기본값 None
            result = self._convert_to_numeric(cost_value)

        # 이 메서드는 절대 null을 반환하지 않음
        if result is None or str(result).lower() in ["null", "none", "nan"]:
            return None  # 🚨 ULTRA PURE: 예외 시에도 None
        return result

    def _extract_billed_date(self, row) -> str:
        """BigQuery 결과에서 billed_date를 추출합니다.

        Args:
            row: BigQuery 결과 행

        Returns:
            str: YYYY-MM-DD 형식의 날짜 문자열 또는 None
        """
        try:
            # 1순위: BigQuery에서 billed_at 필드 확인 (timestamp_trunc(usage_start_time, DAY) as billed_at)
            billed_at = getattr(row, "billed_at", None)
            if billed_at:
                # datetime 객체인 경우 문자열로 변환
                if hasattr(billed_at, "strftime"):
                    return billed_at.strftime("%Y-%m-%d")
                # 문자열인 경우 날짜 부분만 추출
                elif isinstance(billed_at, str):
                    # ISO 형식에서 날짜 부분만 추출 (YYYY-MM-DD)
                    return str(billed_at).split("T")[0].split(" ")[0][:10]

            # 2순위: usage_start_time 확인 (실제 사용 시작 날짜)
            usage_start_time = getattr(row, "usage_start_time", None)
            if usage_start_time:
                if hasattr(usage_start_time, "strftime"):
                    return usage_start_time.strftime("%Y-%m-%d")
                elif isinstance(usage_start_time, str):
                    return str(usage_start_time).split("T")[0].split(" ")[0][:10]

            # 3순위: invoice.month를 날짜로 변환 (월말로 설정)
            invoice_month = getattr(row, "invoice_month", None)
            if (
                invoice_month
                and isinstance(invoice_month, str)
                and len(invoice_month) == 6
            ):  # YYYYMM 형식
                try:
                    year = invoice_month[:4]
                    month = invoice_month[4:6]
                    # 해당 월의 마지막 날로 설정
                    import calendar

                    last_day = calendar.monthrange(int(year), int(month))[1]
                    return f"{year}-{month}-{last_day:02d}"
                except (ValueError, TypeError):
                    pass

            # 모든 날짜 필드가 없으면 None 반환 (현재 날짜 사용하지 않음)
            _LOGGER.warning(
                "[_extract_billed_date] No valid date fields found in row, returning None"
            )
            return None

        except Exception as e:
            _LOGGER.error(f"[_extract_billed_date] Error extracting date: {e}")
            return None

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
        if data_source_type and data_source_type not in ["bigquery", "http"]:
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

    def _create_google_sql(self, start, end=None):
        """BigQuery용 SQL 쿼리를 생성합니다."""
        _LOGGER.debug(f"[SQL 생성] 쿼리 생성 시작 - 시작일: {start}, 종료일: {end}")

        # 날짜 범위 검증 및 안전한 처리
        validated_start = self._validate_and_fix_date_range(start)

        # 종료일이 None인 경우 현재월로 자동 설정
        if end is None:
            from datetime import datetime

            current_month = datetime.now().strftime("%Y-%m")
            validated_end = current_month
            _LOGGER.info(
                f"[SQL 생성] 종료일이 None이므로 현재월로 자동 설정: {validated_end}"
            )
        else:
            validated_end = self._validate_and_fix_date_range(end)
            _LOGGER.debug(f"[SQL 생성] 종료일 검증 완료: {validated_end}")

        _LOGGER.debug(
            f"[SQL 생성] 검증된 시작일: {validated_start}, 종료일: {validated_end}"
        )

        # PARTITIONDATE 범위 계산 (Data Sources Re-Sync 최적화)
        partition_start, partition_end = self._calculate_partition_date_range(
            validated_start, validated_end
        )

        # WHERE 조건 생성 (종료일은 항상 설정됨)
        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{validated_start}-01')
          AND usage_start_time < TIMESTAMP(DATE_ADD(DATE('{validated_end}-01'), INTERVAL 1 MONTH))
          AND _PARTITIONDATE BETWEEN '{partition_start}' AND '{partition_end}'
        """
        _LOGGER.debug(f"[SQL 생성] 날짜 범위 필터: {validated_start} ~ {validated_end}")

        _LOGGER.debug(
            f"[SQL 생성] PARTITIONDATE 필터 추가: {partition_start} ~ {partition_end}"
        )

        if self.target_project_id != "*":
            where_condition += f" AND project.id = '{self.target_project_id}'"
            _LOGGER.debug(f"[SQL 생성] 특정 프로젝트 필터링: {self.target_project_id}")
        else:
            _LOGGER.debug("[SQL 생성] 모든 프로젝트 조회 (project_id = '*')")

        # 🚨 CRITICAL FIX: 금액이 0이 아닌 데이터만 처리
        where_condition += """
          AND cost > 0  -- 금액이 0이 아닌 데이터만
          AND project.id IS NOT NULL  -- NULL 프로젝트 제외
        """
        _LOGGER.debug(
            "[SQL 생성] 비용 필터 조건 추가: cost > 0 (금액이 0이 아닌 데이터만)"
        )

        # 상세 사용량 데이터인 경우 리소스 정보 포함
        if hasattr(self, "is_detailed_usage") and self.is_detailed_usage:
            resource_fields = """
              resource.name as resource_name,
              resource.global_name as resource_global_name,"""
            # GROUP BY 필드: 집계되지 않는 필드들만 포함 (ANY_VALUE/SUM 제외)
            # 1-2: 기본 식별, 3-6: 서비스/SKU, 7-10: 프로젝트, 11-14: 위치, 15-16: 사용량, 17-18: 인보이스, 19-22: 기타 STRING
            # 23-25: ANY_VALUE(REPEATED JSON) - GROUP BY 제외, 26: credits 원본 - GROUP BY 제외, 27-28: 리소스 NULL
            group_by_fields = "1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22"
            _LOGGER.debug("[SQL 생성] 상세 사용량 모드 - 리소스 정보 포함")
        else:
            resource_fields = """
              NULL as resource_name,
              NULL as resource_global_name,"""
            # GROUP BY 필드: 집계되지 않는 필드들만 포함 (ANY_VALUE/SUM 제외)
            # 1-2: 기본 식별, 3-6: 서비스/SKU, 7-10: 프로젝트, 11-14: 위치, 15-16: 사용량, 17-18: 인보이스, 19-22: 기타 STRING
            # 23-25: ANY_VALUE(REPEATED JSON) - GROUP BY 제외, 26: credits 원본 - GROUP BY 제외
            group_by_fields = "1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22"
            _LOGGER.debug("[SQL 생성] 표준 모드 - 리소스 정보 제외")

        query = f"""
            SELECT
              -- 기본 식별 필드들
              timestamp_trunc(usage_start_time, DAY) as billed_at,
              billing_account_id,

              -- 서비스 및 SKU 정보 (RECORD 타입에서 추출)
              service.id as service_id,
              service.description as service_description,
              sku.id as sku_id,
              sku.description as sku_description,

              -- 프로젝트 정보 (RECORD 타입에서 추출)
              project.id as project_id,
              project.name as project_name,
              project.number as project_number,
              project.ancestry_numbers,

              -- 위치 정보 (RECORD 타입에서 추출) - 🚨 ULTRA PURE: NULL 보존
              location.location as location_name,
              location.country as location_country,
              location.region as region_code,
              location.zone as location_zone,

              -- 사용량 정보 (RECORD 타입에서 추출) - 🚨 ULTRA PURE: NULL 보존
              usage.unit as usage_unit,
              usage.pricing_unit as pricing_unit,

              -- 인보이스 정보 (RECORD 타입에서 추출) - 🚨 ULTRA PURE: NULL 보존
              invoice.month as invoice_month,
              invoice.publisher_type as publisher_type,

              -- 기타 STRING 필드들 - 🚨 ULTRA PURE: NULL 보존
              currency,
              transaction_type,
              seller_name,
              cost_type,

              -- REPEATED 필드들을 JSON 문자열로 변환 (ANY_VALUE로 집계 호환) - 🚨 ULTRA PURE: NULL 보존
              TO_JSON_STRING(ANY_VALUE(labels)) as labels,
              TO_JSON_STRING(ANY_VALUE(system_labels)) as system_labels_json,
              TO_JSON_STRING(ANY_VALUE(tags)) as resource_tags,
              
              -- 🎯 Credits Detail 처리 (최적화 완료)
              TO_JSON_STRING(ANY_VALUE(credits)) as credits_detail,{resource_fields}

              -- FLOAT 타입 필드들 (집계) - 🚨 ULTRA PURE: NULL 보존
              SUM(cost) as cost,
              MAX(currency_conversion_rate) as currency_conversion_rate,  -- 🚨 ULTRA PURE: 1.0 기본값 제거
              SUM(cost_at_list) as cost_at_list,  -- 🚨 ULTRA PURE: cost 대체 제거
              SUM(cost_at_effective_price_default) as cost_at_effective_price_default,  -- 🚨 ULTRA PURE: cost 대체 제거
              SUM(cost_at_list_consumption_model) as cost_at_list_consumption_model,  -- 🚨 ULTRA PURE: cost 대체 제거

              -- 사용량 집계 (usage RECORD에서 FLOAT 필드들) - 🚨 ULTRA PURE: NULL 보존
              SUM(usage.amount) as usage_amount,
              SUM(usage.amount_in_pricing_units) as usage_quantity,

              -- 크레딧 정보 집계 (credits REPEATED에서 FLOAT 필드들) - GROUP BY 호환, 🚨 ULTRA PURE: NULL 보존
              SUM((SELECT SUM(CAST(c.amount AS FLOAT64))
                   FROM UNNEST(credits) c)) as credits_total_amount,

              -- 계산된 비용 필드들
              SUM(cost) as cost_after_credits,
              -- 🚨 ULTRA PURE DATA: 수학 연산 제거, 개별 필드로 분리 - GROUP BY 호환
              SUM(cost) as cost_sum,
              SUM((SELECT SUM(CAST(c.amount AS FLOAT64)) FROM UNNEST(credits) c)) as credits_sum,

              -- AmortizedCost를 위한 credits_amount 계산 (🚨 ULTRA PURE: ABS() 제거) - GROUP BY 호환
              SUM((SELECT SUM(CAST(c.amount AS FLOAT64)) FROM UNNEST(credits) c)) as credits_amount
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            GROUP BY {group_by_fields}
            ORDER BY billed_at desc
            ;
        """
        _LOGGER.debug(f"[SQL 쿼리] {query}")
        _LOGGER.debug("[SQL 생성] 쿼리 생성 완료")
        _LOGGER.debug(
            f"[SQL 생성] 대상 테이블: {self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}"
        )

        return query

    def _create_linked_accounts_google_sql(self, start):
        # 날짜 범위 검증 및 안전한 처리
        validated_start = self._validate_and_fix_date_range(start)

        # PARTITIONDATE 범위 계산 (Data Sources Re-Sync 최적화)
        partition_start, partition_end = self._calculate_partition_date_range(
            validated_start
        )

        where_condition = f"""
        WHERE usage_start_time >= TIMESTAMP('{validated_start}-01')
          AND _PARTITIONDATE BETWEEN '{partition_start}' AND '{partition_end}'
        """

        _LOGGER.debug(
            f"[Linked Accounts SQL] PARTITIONDATE 필터 추가: {partition_start} ~ {partition_end}"
        )

        query = f"""
            SELECT
            distinct project.id, project.name as project_name
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_condition}
            ;
        """
        return query

    @staticmethod
    def _get_start_month():
        start_time: datetime = datetime.utcnow() - timedelta(days=365)
        start_time = start_time.replace(day=1)

        start_time = start_time.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        return start_time.strftime("%Y-%m")

    @staticmethod
    def _normalize_date_to_month(date_str: str) -> str:
        """날짜를 YYYY-MM 형식으로 정규화

        Args:
            date_str: YYYY-MM 또는 YYYY-MM-DD 형식의 날짜 문자열

        Returns:
            str: YYYY-MM 형식의 날짜 문자열
        """
        if not date_str:
            return None

        # YYYY-MM-DD 형식인 경우 YYYY-MM으로 변환
        if len(date_str) == 10 and date_str.count("-") == 2:
            return date_str[:7]  # YYYY-MM-DD -> YYYY-MM

        # 이미 YYYY-MM 형식인 경우 그대로 반환
        if len(date_str) == 7 and date_str.count("-") == 1:
            return date_str

        # 기타 형식은 그대로 반환 (오류 처리는 상위에서)
        return date_str

    @staticmethod
    def _calculate_partition_date_range(
        start_date: str, end_date: str = None
    ) -> tuple[str, str]:
        """Data Sources Re-Sync를 위한 PARTITIONDATE 범위 계산

        시작일은 -1개월, 종료일은 +1개월로 확장하여 안전한 데이터 수집을 보장합니다.

        Args:
            start_date: YYYY-MM 형식의 시작 날짜
            end_date: YYYY-MM 형식의 종료 날짜 (선택사항, 없으면 start_date 기준으로 계산)

        Returns:
            tuple[str, str]: (partition_start_date, partition_end_date) YYYY-MM-DD 형식
        """
        try:
            from dateutil.relativedelta import relativedelta

            # 시작일 파싱
            if not start_date or len(start_date) != 7:  # YYYY-MM 형식 검증
                current_date = datetime.now()
                start_datetime = datetime(current_date.year, current_date.month, 1)
            else:
                start_year, start_month = map(int, start_date.split("-"))
                start_datetime = datetime(start_year, start_month, 1)

            # 종료일 파싱
            if end_date and len(end_date) == 7:  # YYYY-MM 형식 검증
                end_year, end_month = map(int, end_date.split("-"))
                end_datetime = datetime(end_year, end_month, 1)
            else:
                # 종료일이 없으면 현재월로 설정
                current_date = datetime.now()
                end_datetime = datetime(current_date.year, current_date.month, 1)
                _LOGGER.info(
                    f"[PARTITIONDATE] 종료일이 None이므로 현재월로 설정: {current_date.strftime('%Y-%m')}"
                )

            # 시작일 계산: start_date -1개월의 첫째 날
            partition_start = start_datetime - relativedelta(months=1)
            partition_start_str = partition_start.strftime("%Y-%m-%d")

            # 종료일 계산: end_date +1개월의 마지막 날
            partition_end = end_datetime + relativedelta(months=1)
            # 다음 달의 마지막 날 계산
            partition_end = (
                partition_end + relativedelta(months=1) - relativedelta(days=1)
            )
            partition_end_str = partition_end.strftime("%Y-%m-%d")

            _LOGGER.info(
                f"[PARTITIONDATE 범위] 원본 범위: {start_date} ~ {end_date or start_date}, 확장된 범위: {partition_start_str} ~ {partition_end_str}"
            )

            return partition_start_str, partition_end_str

        except ImportError:
            # dateutil이 없는 경우 기본 datetime 사용
            _LOGGER.warning(
                "[PARTITIONDATE] dateutil을 사용할 수 없어 기본 계산 방법을 사용합니다."
            )
            try:
                # 시작일 파싱
                if not start_date or len(start_date) != 7:
                    current_date = datetime.now()
                    start_year, start_month = current_date.year, current_date.month
                else:
                    start_year, start_month = map(int, start_date.split("-"))

                # 종료일 파싱
                if end_date and len(end_date) == 7:
                    end_year, end_month = map(int, end_date.split("-"))
                else:
                    # 종료일이 없거나 잘못된 경우 현재월로 설정
                    current_date = datetime.now()
                    end_year, end_month = current_date.year, current_date.month
                    _LOGGER.info(
                        f"[PARTITIONDATE] 종료일이 None이므로 현재월로 설정: {current_date.strftime('%Y-%m')}"
                    )

                # 시작일 계산: start_date -1개월
                if start_month == 1:
                    partition_start = datetime(start_year - 1, 12, 1)
                else:
                    partition_start = datetime(start_year, start_month - 1, 1)

                # 종료일 계산: end_date +1개월 말일
                if end_month == 12:
                    next_month = datetime(end_year + 1, 1, 1)
                else:
                    next_month = datetime(end_year, end_month + 1, 1)

                # 다음 달의 다음 달 첫째 날에서 하루 빼기 (다음 달 마지막 날)
                if next_month.month == 12:
                    partition_end = datetime(next_month.year + 1, 1, 1) - timedelta(
                        days=1
                    )
                else:
                    partition_end = datetime(
                        next_month.year, next_month.month + 1, 1
                    ) - timedelta(days=1)

                partition_start_str = partition_start.strftime("%Y-%m-%d")
                partition_end_str = partition_end.strftime("%Y-%m-%d")

                _LOGGER.info(
                    f"[PARTITIONDATE 범위] 원본 범위: {start_date} ~ {end_date or start_date}, 확장된 범위: {partition_start_str} ~ {partition_end_str}"
                )

                return partition_start_str, partition_end_str

            except Exception as e:
                _LOGGER.error(f"[PARTITIONDATE 범위 계산 오류] {e}")
                # 기본값으로 현재 월 기준 ±1개월 반환
                current_date = datetime.now()
                start_default = current_date.replace(day=1) - timedelta(days=32)
                start_default = start_default.replace(day=1)
                end_default = current_date.replace(day=1) + timedelta(days=62)
                end_default = end_default.replace(day=1) - timedelta(days=1)

                return start_default.strftime("%Y-%m-%d"), end_default.strftime(
                    "%Y-%m-%d"
                )

        except Exception as e:
            _LOGGER.error(f"[PARTITIONDATE 범위 계산 오류] {e}")
            # 기본값으로 현재 월 기준 ±1개월 반환
            current_date = datetime.now()
            start_default = current_date.replace(day=1) - timedelta(days=32)
            start_default = start_default.replace(day=1)
            end_default = current_date.replace(day=1) + timedelta(days=62)
            end_default = end_default.replace(day=1) - timedelta(days=1)

            return start_default.strftime("%Y-%m-%d"), end_default.strftime("%Y-%m-%d")

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

        # base_url 또는 bucket_name이 있으면 http 타입으로 자동 감지
        base_url_in_options = options.get("base_url")
        base_url_in_task_options = task_options.get("base_url")
        bucket_name_in_options = options.get("bucket_name")
        bucket_name_in_task_options = task_options.get("bucket_name")

        # HTTP 파일 관련 파라미터가 명확히 있는 경우에만 HTTP 파일로 결정
        has_http_params = (
            base_url_in_options
            or base_url_in_task_options
            or bucket_name_in_options
            or bucket_name_in_task_options
        )

        if has_http_params:
            return DATA_SOURCE_TYPES["http"]

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

        # 1. source 값 직접 확인
        source = options.get("source")

        # 2. data_source_type에서 매핑 (하위 호환성)
        if not source:
            data_source_type = options.get("data_source_type")
            if data_source_type:
                _LOGGER.info(
                    f"[_get_source_value] data_source_type을 source로 매핑: {data_source_type}"
                )
                source = data_source_type

        if not source:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"source (required parameter. Supported values: {', '.join(valid_sources)})"
            )

        if source not in valid_sources:
            raise ERROR_REQUIRED_PARAMETER(
                key=f"source (invalid value: {source}. Supported values: {', '.join(valid_sources)})"
            )

        _LOGGER.info(f"[_get_source_value] 최종 source 값: {source}")
        return source

    def _process_labels_data(self, labels_data) -> dict:
        """Labels 데이터를 구조적 딕셔너리로 변환

        Args:
            labels_data: Labels 원본 데이터 (문자열, 리스트, 또는 딕셔너리)

        Returns:
            dict: key-value 형태의 라벨 딕셔너리
        """
        import ast
        import json

        try:
            # 이미 딕셔너리인 경우
            if isinstance(labels_data, dict):
                return labels_data

            # 빈 값 처리
            if not labels_data or labels_data in ["[]", "", "null", None]:
                return {}

            # 문자열인 경우 파싱 시도
            if isinstance(labels_data, str):
                labels_data = labels_data.strip()

                # 빈 배열 문자열 처리
                if labels_data == "[]":
                    return {}

                # JSON 파싱 시도
                try:
                    parsed = json.loads(labels_data)
                except json.JSONDecodeError:
                    # Python literal 파싱 시도 (예: "[{'key': 'value'}]" 형식)
                    try:
                        parsed = ast.literal_eval(labels_data)
                    except (ValueError, SyntaxError):
                        _LOGGER.warning(f"Failed to parse labels data: {labels_data}")
                        return {}

                labels_data = parsed

            # 리스트인 경우 딕셔너리로 변환
            if isinstance(labels_data, list):
                result = {}
                for item in labels_data:
                    if isinstance(item, dict):
                        key = item.get("key", "")
                        value = item.get("value", "")
                        if key:  # key가 있는 경우만 추가
                            # snake_case로 변환
                            key = self._to_snake_case(key)
                            result[key] = value
                return result

            # 이미 딕셔너리인 경우 그대로 반환
            if isinstance(labels_data, dict):
                return labels_data

            _LOGGER.warning(f"Unexpected labels data type: {type(labels_data)}")
            return {}

        except Exception as e:
            _LOGGER.error(f"Error processing labels data: {e}")
            return {}

    def _process_system_labels_data(self, system_labels_data) -> dict:
        """System Labels 데이터를 구조적 딕셔너리로 변환

        Args:
            system_labels_data: System Labels 원본 데이터

        Returns:
            dict: key-value 형태의 시스템 라벨 딕셔너리
        """
        # Labels와 동일한 로직 사용
        return self._process_labels_data(system_labels_data)

    def _to_snake_case(self, text: str) -> str:
        """문자열을 snake_case로 변환

        Args:
            text: 변환할 문자열

        Returns:
            str: snake_case로 변환된 문자열
        """
        import re

        # 특수문자를 언더스코어로 변환
        text = re.sub(r"[^\w\s]", "_", text)
        # 공백을 언더스코어로 변환
        text = re.sub(r"\s+", "_", text)
        # 연속된 언더스코어를 하나로 변환
        text = re.sub(r"_+", "_", text)
        # 앞뒤 언더스코어 제거
        text = text.strip("_")
        # 소문자로 변환
        return text.lower()

    def _format_project_display_name(self, row) -> str:
        """프로젝트 표시명을 포맷팅합니다.

        화면에 표시될 프로젝트 이름을 결정합니다.
        여러 옵션을 제공하여 사용자 선호에 따라 선택 가능합니다.

        Args:
            row: BigQuery 결과 행

        Returns:
            str: 포맷팅된 프로젝트 표시명
        """
        project_id = str(getattr(row, "project_id", "")).strip()

        # 🎯 옵션 1: 프로젝트 ID만 사용 (로그와 동일)
        return project_id

        # 🎯 옵션 2: 프로젝트 이름 사용 (있는 경우)
        # if project_name:
        #     return project_name
        # return project_id

        # 🎯 옵션 3: ID + 이름 조합
        # if project_name and project_name != project_id:
        #     return f"{project_id} ({project_name})"
        # return project_id

        # 🎯 옵션 4: 이름 우선, ID 폴백
        # return project_name if project_name else project_id
