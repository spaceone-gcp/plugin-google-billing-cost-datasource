import logging
import os
from collections.abc import Generator

from spaceone.cost_analysis.plugin.data_source.lib.server import (
    DataSourcePluginServer,
)

from plugin.conf.cost_conf import PERFORMANCE_CONFIG
from plugin.manager.cost_manager import CostManager
from plugin.manager.data_source_manager import DataSourceManager
from plugin.manager.job_manager import JobManager
from plugin.utils.json_log_collector import (
    is_json_logging_active,
    log_json_response,
    start_json_logging,
    stop_json_logging,
)

# 전역 JSON 패치 제거 - BigQuery API 호환성 문제로 인해 제거
# import plugin.utils.json_patch  # BigQuery request_id 변환 문제 발생


# 로깅 설정
def setup_logging():
    """로깅 설정을 초기화합니다."""
    # 환경변수에서 DEBUG 모드 확인
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "DEBUG" if debug_mode else "INFO").upper()

    # 로깅 레벨 설정
    level_mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    log_level_value = level_mapping.get(log_level, logging.INFO)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level_value)

    # SpaceONE 로거 설정
    spaceone_logger = logging.getLogger("spaceone")
    spaceone_logger.setLevel(log_level_value)

    # 콘솔 핸들러가 없으면 추가
    if not spaceone_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level_value)

        # 포맷터 설정
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        spaceone_logger.addHandler(console_handler)
        spaceone_logger.propagate = False  # 중복 로그 방지


# 로깅 설정 초기화
setup_logging()

_LOGGER = logging.getLogger("spaceone")

app = DataSourcePluginServer()


# 실제 비즈니스 로직 함수들 (테스트 가능)
def _data_source_init_logic(params: dict) -> dict:
    """init plugin by options - 실제 로직"""
    try:
        # 파라미터 추출 및 검증
        options = params["options"]

        # DataSourceManager 인스턴스 생성 및 초기화 응답 생성
        data_source_mgr = DataSourceManager()
        result = data_source_mgr.init_response(options)

        return result

    except Exception as e:
        _LOGGER.error(
            f"[_data_source_init_logic] Failed to initialize data source: {e}"
        )
        raise


# 데이터 소스 초기화
@app.route("DataSource.init")
def data_source_init(params: dict) -> dict:
    """init plugin by options

    Args:
        params (DataSourceInitRequest): {
            'options': 'dict',    # Required
            'domain_id': 'str'    # Required
        }

    Returns:
        PluginResponse: {
            'metadata': 'dict'
        }
    """
    _LOGGER.info("[data_source_init] API endpoint called")

    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        result = _data_source_init_logic(params)
        _LOGGER.info("[data_source_init] API endpoint completed successfully")

        return result

    except Exception as e:
        _LOGGER.error(f"[data_source_init] API endpoint failed: {e}")
        raise


# 데이터 소스 검증
def _data_source_verify_logic(params: dict) -> None:
    """verify plugin - 실제 로직"""
    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params.get("secret_data", {})
        domain_id = params.get("domain_id")
        schema = params.get("schema")

        # DataSourceManager 인스턴스 생성 및 검증 수행
        data_source_mgr = DataSourceManager()
        data_source_mgr.verify_plugin(options, secret_data, domain_id, schema)

    except Exception as e:
        _LOGGER.error(f"[_data_source_verify_logic] Failed to verify data source: {e}")
        raise


# 데이터 소스 검증
@app.route("DataSource.verify")
def data_source_verify(params: dict) -> None:
    """Verifying data source plugin

    Args:
        params (CollectorVerifyRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Optional
            'schema': 'str',
            'domain_id': 'str'      # Required
        }

    Returns:
        None
    """
    _LOGGER.info("[data_source_verify] API endpoint called")

    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        _data_source_verify_logic(params)
        _LOGGER.info("[data_source_verify] API endpoint completed successfully")

    except Exception as e:
        _LOGGER.error(f"[data_source_verify] API endpoint failed: {e}")
        raise


# 작업 태스크 생성
def _job_get_tasks_logic(params: dict) -> dict:
    """get tasks - 실제 로직"""
    try:
        # 필수 파라미터 추출
        domain_id = params["domain_id"]
        options = params["options"]
        secret_data = params["secret_data"]
        schema = params.get("schema")
        start = params.get("start")
        last_synchronized_at = params.get("last_synchronized_at")

        # JobManager 인스턴스 생성 및 작업 요청
        job_mgr = JobManager()
        result = job_mgr.get_tasks(
            domain_id, options, secret_data, schema, start, last_synchronized_at
        )

        return result

    except Exception as e:
        _LOGGER.error(f"[_job_get_tasks_logic] Failed to generate job tasks: {e}")
        raise


@app.route("Job.get_tasks")
def job_get_tasks(params: dict) -> dict:
    """Get job tasks

    Args:
        params (JobGetTaskRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Required
            'schema': 'str',
            'start': 'str',
            'last_synchronized_at': 'datetime',
            'domain_id': 'str'      # Required
        }

    Returns:
        TasksResponse: {
            'tasks': 'list',
            'changed': 'list'
        }

    """
    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["domain_id", "options", "secret_data"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        # 작업 태스크 생성
        result = _job_get_tasks_logic(params)

        # 태스크 생성 결과 검증 및 로깅
        actual_tasks = len(result.get("tasks", []))
        _LOGGER.info(f"[job_get_tasks] Created {actual_tasks} tasks for processing")

        return result

    except Exception as e:
        _LOGGER.error(f"[job_get_tasks] API endpoint failed: {e}")
        raise


def _cost_get_data_logic(params: dict) -> Generator[dict, None, None]:
    """get cost data - 실제 로직 (Credits Detail 모드 지원)"""
    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params["secret_data"]

        # 선택적 파라미터 추출
        task_options = params.get("task_options", {})
        schema = params.get("schema")

        # start 파라미터 처리: Job.get_tasks와 동일한 방식으로 최상위 레벨에서도 받을 수 있도록 함
        start_param = params.get("start")
        if start_param and "start" not in task_options:
            task_options["start"] = start_param
            _LOGGER.info(
                f"[_cost_get_data_logic] 최상위 레벨 start 파라미터를 task_options로 이동: {start_param}"
            )

        # Credits Detail 모드 확인
        credits_detail_mode = task_options.get("credits_detail_mode", False)

        if credits_detail_mode:
            # Credits Detail 모드: 원본 데이터 조회
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Credits Detail 모드로 실행")

            from plugin.connector.bigquery_connector import BigqueryConnector
            from plugin.manager.credits_detail_manager import CreditsDetailManager

            # Credits Detail Manager 초기화
            credits_mgr = CreditsDetailManager()

            # BigQuery 커넥터 설정
            bigquery_connector = BigqueryConnector()
            bigquery_connector.create_session(options, secret_data, schema)

            # 빌링 정보 설정
            billing_export_project_id = options.get("billing_export_project_id")
            billing_dataset_id = options.get("billing_dataset_id")
            billing_account_id = options.get("billing_account_id")

            if not billing_export_project_id:
                raise ValueError("billing_export_project_id is required in options")
            if not billing_dataset_id:
                raise ValueError("billing_dataset_id is required in options")
            if not billing_account_id:
                raise ValueError("billing_account_id is required in options")

            # 빌링 테이블 이름 생성
            billing_table = (
                f"gcp_billing_export_v1_{billing_account_id.replace('-', '_')}"
            )

            # Credits Detail Manager 초기화
            credits_mgr.initialize(
                bigquery_connector=bigquery_connector,
                billing_export_project_id=billing_export_project_id,
                billing_dataset=billing_dataset_id,
                billing_table=billing_table,
            )

            # 쿼리 옵션 파싱
            start_date = task_options.get("start")
            end_date = task_options.get("end")
            project_id = task_options.get("project_id")
            limit = int(task_options.get("credits_detail_limit", 100))

            if not start_date:
                raise ValueError("start date is required for credits detail mode")

            # DEBUG 레벨에서만 상세 정보 로깅
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    f"Credits Detail 조회: {start_date} ~ {end_date}, 프로젝트: {project_id}, 제한: {limit}"
                )

            # Credits Detail 조회
            for record in credits_mgr.get_credits_detail(
                start_date=start_date,
                end_date=end_date,
                project_id=project_id,
                billing_account_id=billing_account_id,
                limit=limit,
            ):
                yield record

        else:
            # 기본 모드: 기존 최적화된 집계 데이터 조회

            # CostManager 인스턴스 생성
            cost_mgr = CostManager()

            result_generator = cost_mgr.get_data(
                options, secret_data, task_options, schema
            )

            yield from result_generator

    except Exception as e:
        _LOGGER.error(f"[_cost_get_data_logic] Failed to get cost data: {e}")
        raise


@app.route("Cost.get_data")
def cost_get_data(params: dict) -> Generator[dict, None, None]:
    """Get external cost data

    Args:
        params (CostGetDataRequest): {
            'options': 'dict',      # Required
            'secret_data': 'dict',  # Required
            'schema': 'str',
            'task_options': 'dict',
            'start': 'str',         # Optional: 최상위 레벨에서도 지원 (Job.get_tasks와 동일)
            'domain_id': 'str'      # Required
        }

    Returns:
        Generator[ResourceResponse, None, None]
        {
            'cost': 'float',
            'usage_quantity': 'float',
            'usage_unit': 'str',
            'provider': 'str',
            'region_code': 'str',
            'product': 'str',
            'usage_type': 'str',
            'resource': 'str',
            'tags': 'dict',
            'additional_info': 'dict',
            'data': 'dict',
            'billed_date': 'str'
        }
    """
    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "secret_data", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        # JSON 로깅 시작 (환경변수로 제어) - 간소화
        json_logging_env = os.getenv("ENABLE_JSON_LOGGING", "false")
        if json_logging_env.lower() == "true":
            _LOGGER.debug("[cost_get_data] Starting JSON logging")
            start_json_logging()
        else:
            _LOGGER.debug("[cost_get_data] JSON logging disabled")

        result_generator = _cost_get_data_logic(params)

        # SpaceONE 프레임워크 호환: 개별 레코드 직접 yield 방식
        batch_count = 0
        total_records = 0

        for batch_result in result_generator:
            batch_count += 1

            try:
                # BigQuery 응답을 SpaceONE 표준 형식으로 변환
                spaceone_formatted = _convert_to_spaceone_format(
                    batch_result, batch_count
                )

                if spaceone_formatted and isinstance(spaceone_formatted, dict):
                    if (
                        "results" in spaceone_formatted
                        and len(spaceone_formatted["results"]) > 0
                    ):
                        # 첫 번째 배치 검증
                        if batch_count == 1:
                            _validate_spaceone_response_format(
                                spaceone_formatted["results"][0]
                            )

                        spaceone_formatted = _ultimate_cost_field_verification(
                            spaceone_formatted, batch_count
                        )

                        # 배치 결과를 청크 버퍼에 추가
                        batch_results = spaceone_formatted["results"]

                        # 레코드 전처리 (data.cost 제거 및 JSON 로깅)
                        processed_records = []
                        for record in batch_results:
                            total_records += 1

                            # data.cost 제거 (최상위 cost는 유지)
                            if (
                                isinstance(record.get("data"), dict)
                                and "cost" in record["data"]
                            ):
                                del record["data"]["cost"]

                            # JSON 로깅이 활성화된 경우 수집기에 추가
                            if is_json_logging_active():
                                log_json_response(record)

                            processed_records.append(record)

                        # 성능 최적화: 배치 단위로 yield (gRPC 메시지 크기 제한 고려)
                        if PERFORMANCE_CONFIG["enable_dynamic_batch_sizing"]:
                            # 동적 배치 크기 조정으로 최적화된 yield
                            yield from _create_optimized_batches(processed_records)
                        else:
                            # 기존 방식: 개별 레코드 yield (하위 호환성)
                            for record in processed_records:
                                yield {"results": [record]}

            except Exception as e:
                _LOGGER.error(
                    f"[cost_get_data] Failed to process batch {batch_count}: {e}"
                )
                # 에러가 발생해도 다음 배치 처리 계속

        # 개별 레코드 yield 방식에서는 별도의 최종 응답 불필요
        if total_records == 0:
            _LOGGER.warning("[cost_get_data] No results to yield")
            # 빈 결과도 개별 레코드 형태로 처리하지 않음 (SpaceONE 프레임워크가 자동 처리)

        # 처리 완료 로깅
        task_options = params.get("task_options", {})
        processed_project = task_options.get("project_id", "unknown")

        # 성능 최적화 효과 로깅 (간소화됨)
        if PERFORMANCE_CONFIG["enable_performance_logging"]:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    f"프로젝트 '{processed_project}' 처리 완료: {batch_count}개 배치, {total_records}건"
                )

        # JSON 로깅 중단 및 파일 저장
        if is_json_logging_active():
            stop_json_logging()

    except Exception as e:
        _LOGGER.error(f"[cost_get_data] API endpoint failed: {e}")
        # 예외 발생 시에도 JSON 로깅 중단
        if is_json_logging_active():
            stop_json_logging()
        raise


def _remove_data_cost_from_response(response: dict) -> dict:
    """최종 응답에서 data.cost 필드만 제거 (내부 연산은 유지)

    Args:
        response: 응답 딕셔너리 {"results": [record1, record2, ...]}

    Returns:
        data.cost가 제거된 응답 딕셔너리
    """
    if not isinstance(response.get("results"), list):
        return response

    removed_count = 0
    for record in response["results"]:
        if isinstance(record, dict) and "data" in record:
            if isinstance(record["data"], dict) and "cost" in record["data"]:
                del record["data"]["cost"]
                removed_count += 1

    if removed_count > 0:
        _LOGGER.debug(
            f"[main] Removed data.cost from {removed_count} records in final response"
        )

    return response


def _convert_to_spaceone_format(batch_result, batch_count):
    """BigQuery 응답을 SpaceONE 표준 형식으로 변환"""
    try:
        if not batch_result:
            return {"results": []}

        # 이미 SpaceONE 형식인 경우 필수 필드만 보장
        if isinstance(batch_result, dict) and "results" in batch_result:
            results = batch_result["results"]
            if not isinstance(results, list):
                results = [results] if results else []
        else:
            # 단일 레코드인 경우 리스트로 변환
            results = [batch_result] if batch_result else []

        # 각 레코드를 SpaceONE 표준 형식으로 변환
        spaceone_results = []
        for record in results:
            if isinstance(record, dict):
                if "cost" not in record:
                    cost_value = 0.0
                    if "additional_info" in record and isinstance(
                        record["additional_info"], dict
                    ):
                        cost_after_credits = record["additional_info"].get(
                            "Cost After Credits", 0
                        )
                        try:
                            cost_value = float(cost_after_credits)
                        except (ValueError, TypeError):
                            cost_value = 0.0

                    # 최상위 cost 필드 추가 (첫 번째 위치)
                    new_record = {"cost": cost_value}
                    new_record.update(record)
                    record = new_record

                    _LOGGER.error(
                        f"[_convert_to_spaceone_format] ULTIMATE: Added missing cost field: {cost_value}"
                    )

                spaceone_record = _ensure_spaceone_record_format(record)
                if spaceone_record:  # 유효한 레코드만 추가
                    # cost 필드 최종 보장 (재배치 로직 제거로 단순화)
                    if "cost" not in spaceone_record or spaceone_record["cost"] is None:
                        spaceone_record["cost"] = 0.0
                        _LOGGER.error(
                            "[_convert_to_spaceone_format] ULTIMATE: Force-added cost field to spaceone_record"
                        )

                    spaceone_results.append(spaceone_record)

        # SpaceONE 표준 응답 구조로 래핑
        spaceone_response = {"results": spaceone_results}

        return spaceone_response

    except Exception as e:
        _LOGGER.error(
            f"[_convert_to_spaceone_format] Conversion failed for batch {batch_count}: {e}"
        )
        return {"results": []}


def _ensure_spaceone_record_format(record):
    """개별 레코드를 SpaceONE 표준 형식으로 변환"""
    try:
        # 원본 레코드에서 cost 필드 추출 및 검증
        cost_value = record.get("cost")
        if cost_value is None:
            # data.cost에서 값 추출 시도
            if "data" in record and isinstance(record["data"], dict):
                data_cost = record["data"].get("cost")
                if data_cost is not None:
                    try:
                        cost_value = float(data_cost)
                        _LOGGER.info(
                            f"[_ensure_spaceone_record_format] RECOVERED: cost field from data.cost: {cost_value}"
                        )
                    except (ValueError, TypeError):
                        cost_value = 0.0
                        _LOGGER.warning(
                            "[_ensure_spaceone_record_format] INVALID data.cost, using 0.0"
                        )
                else:
                    cost_value = 0.0
                    _LOGGER.error(
                        "[_ensure_spaceone_record_format] CRITICAL: cost field missing completely, setting to 0.0"
                    )
            else:
                cost_value = 0.0
                _LOGGER.error(
                    "[_ensure_spaceone_record_format] CRITICAL: cost field missing in record, setting to 0.0"
                )

        currency_value = record.get("currency")
        if currency_value is None or currency_value == "":
            currency_value = record.get("additional_info", {}).get("Currency", "USD")
            if currency_value != "USD":
                _LOGGER.debug(
                    f"[_ensure_spaceone_record_format] Currency extracted from additional_info: {currency_value}"
                )
            else:
                _LOGGER.info(
                    "[_ensure_spaceone_record_format] Currency field missing, defaulting to USD"
                )

        usage_quantity_value = record.get("usage_quantity", 0.0)
        usage_unit_value = record.get("usage_unit", "")

        # FieldMapper에서 전달되지 않은 경우 additional_info에서 직접 추출
        if usage_quantity_value == 0.0:
            additional_info = record.get("additional_info", {})
            if isinstance(additional_info, dict):
                # GCP Usage Amount 추출 시도
                usage_amount = additional_info.get("Usage Amount")
                if usage_amount:
                    try:
                        usage_quantity_value = float(usage_amount)
                    except (ValueError, TypeError):
                        pass

                # Usage Amount In Pricing Units도 시도
                if usage_quantity_value == 0.0:
                    usage_pricing_amount = additional_info.get(
                        "Usage Amount In Pricing Units"
                    )
                    if usage_pricing_amount:
                        try:
                            usage_quantity_value = float(usage_pricing_amount)
                            pass
                        except (ValueError, TypeError):
                            pass
        # usage_unit도 마찬가지로 처리
        if usage_unit_value == "":
            additional_info = record.get("additional_info", {})
            if isinstance(additional_info, dict):
                usage_unit = additional_info.get("Usage Unit")
                if usage_unit:
                    usage_unit_value = str(usage_unit)
                    pass
        # SpaceONE Cost 모델 정확한 순서로 필드 배치 (cost_response.py 기준)
        spaceone_record = {
            "cost": float(_safe_numeric_convert(cost_value)),  # 필수: float 타입
            "usage_quantity": _safe_numeric_convert(
                usage_quantity_value
            ),  # Optional[float]
            "usage_unit": _safe_string_convert(usage_unit_value)
            or None,  # Optional[str]
            "provider": _safe_string_convert(record.get("provider", "google_cloud"))
            or None,  # Optional[str]
            "region_code": _safe_string_convert(record.get("region_code", "global"))
            or None,  # Optional[str]
            "product": _safe_string_convert(record.get("product", "Unknown"))
            or None,  # Optional[str]
            "usage_type": _safe_string_convert(record.get("usage_type", ""))
            or None,  # Optional[str]
            "resource": _safe_string_convert(record.get("resource", ""))
            or None,  # Optional[str]
            "tags": _safe_dict_convert(record.get("tags", {})),  # dict = {}
            "additional_info": _safe_dict_convert(
                record.get("additional_info", {})
            ),  # dict = {}
            "data": _safe_dict_convert(record.get("data", {})),  # dict = {}
            "billed_date": _safe_string_convert(
                record.get("billed_date", "")
            ),  # 필수: str 타입
        }

        # cost 필드 특별 처리 (SpaceONE 호환성을 위해 최소값 보장)
        if (
            spaceone_record["cost"] is None
            or spaceone_record["cost"] == ""
            or spaceone_record["cost"] == 0.0
        ):
            spaceone_record["cost"] = 0.01  # 0 대신 최소 양수값 사용

        # billed_date 특별 처리 (SpaceONE Cost 모델은 str을 요구하므로 빈 문자열로 설정)
        if not spaceone_record["billed_date"]:
            spaceone_record["billed_date"] = ""
            _LOGGER.warning(
                "[_ensure_spaceone_record_format] billed_date is empty, setting to empty string for SpaceONE compatibility"
            )

        if "cost" not in spaceone_record or spaceone_record["cost"] is None:
            spaceone_record["cost"] = 0.0
            _LOGGER.error(
                "[_ensure_spaceone_record_format] ULTIMATE: Final cost field enforcement applied"
            )

        return spaceone_record

    except Exception as e:
        _LOGGER.error(f"[_ensure_spaceone_record_format] Failed to format record: {e}")
        return None


def _safe_numeric_convert(value):
    """안전한 숫자 변환: 빈 값은 기본값으로, 나머지는 원본 보존"""
    # 빈 값 처리: "", None, "null" -> 기본값 0
    if (
        value is None
        or value == ""
        or (isinstance(value, str) and value.lower() in ("null", "none", "nan"))
    ):
        return 0

    # 나머지는 원본 그대로 보존 (극소값도 보존)
    try:
        if isinstance(value, (int, float)):
            return value  # 원본 그대로
        elif isinstance(value, str):
            return float(value)  # 문자열 숫자만 변환
        else:
            return value  # 원본 그대로
    except (ValueError, TypeError):
        return 0


def _safe_string_convert(value):
    """안전한 문자열 변환"""
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            return value.strip()
        else:
            return str(value).strip()
    except Exception:
        return ""


def _safe_dict_convert(value):
    """안전한 딕셔너리 변환"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        if isinstance(value, str) and value.strip():
            import json

            return json.loads(value)
        else:
            return {}
    except Exception:
        return {}


def _validate_spaceone_response_format(sample_record):
    """SpaceONE 응답 형식 검증"""
    # cost 필드 특별 검증
    if "cost" not in sample_record or sample_record["cost"] is None:
        _LOGGER.error("CRITICAL: cost field is missing or None")
    elif not isinstance(sample_record["cost"], (int, float)):
        _LOGGER.warning(f"cost field type issue: {type(sample_record['cost'])}")


def _ultimate_cost_field_verification(response: dict, batch_count: int) -> dict:
    """최종 cost 필드 보장 - SpaceONE UI 호환성 확보"""
    if not isinstance(response.get("results"), list):
        return response

    fixed_count = 0
    missing_cost_count = 0

    for i, record in enumerate(response["results"]):
        if isinstance(record, dict):
            # 최상위 cost 필드 절대 보장
            if "cost" not in record:
                # data.cost에서 복구 시도
                if (
                    "data" in record
                    and isinstance(record["data"], dict)
                    and "cost" in record["data"]
                ):
                    try:
                        record["cost"] = float(record["data"]["cost"])
                        fixed_count += 1
                        _LOGGER.info(
                            f"[ULTIMATE] Batch {batch_count}, Record {i}: Recovered cost from data.cost = {record['cost']}"
                        )
                    except (ValueError, TypeError):
                        record["cost"] = 0.0
                        missing_cost_count += 1
                        _LOGGER.error(
                            f"[ULTIMATE] Batch {batch_count}, Record {i}: Invalid data.cost, forced to 0.0"
                        )
                else:
                    record["cost"] = 0.0
                    missing_cost_count += 1
                    _LOGGER.error(
                        f"[ULTIMATE] Batch {batch_count}, Record {i}: No cost field found, forced to 0.0"
                    )
            elif record["cost"] is None:
                record["cost"] = 0.0
                fixed_count += 1
                _LOGGER.warning(
                    f"[ULTIMATE] Batch {batch_count}, Record {i}: None cost converted to 0.0"
                )

            # cost 필드를 최상위 첫 번째 위치로 이동 (SpaceONE 호환성)
            if "cost" in record:
                cost_value = record.pop("cost")
                record_copy = record.copy()
                record.clear()
                record["cost"] = cost_value
                record.update(record_copy)

    if fixed_count > 0 or missing_cost_count > 0:
        _LOGGER.info(
            f"[ULTIMATE] Batch {batch_count}: Fixed {fixed_count} records, Missing {missing_cost_count} records"
        )

    return response


def _cost_get_linked_accounts_logic(params: dict) -> dict:
    """get linked accounts - 실제 로직"""
    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params["secret_data"]
        schema = params.get("schema")

        # CostManager 인스턴스 생성 및 링크된 계정 조회
        cost_mgr = CostManager()
        result = cost_mgr.get_linked_accounts(options, secret_data, schema)

        return result

    except Exception as e:
        _LOGGER.error(
            f"[_cost_get_linked_accounts_logic] Failed to get linked accounts: {e}"
        )
        raise


@app.route("Cost.get_linked_accounts")
def cost_get_linked_accounts(params: dict) -> dict:
    """get linked accounts

    Args:
        params: (CostGetLinkedAccountsRequest): {
            'options': 'dict'
            'schema': 'str'
            'secret_data': 'dict'
            'domain_id': 'str'
        }

    Returns:
        {
            'account_id': 'str'
            'name': 'str'
        }
    """
    _LOGGER.info("[cost_get_linked_accounts] API endpoint called")

    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "secret_data", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        result = _cost_get_linked_accounts_logic(params)
        _LOGGER.info("[cost_get_linked_accounts] API endpoint completed successfully")

        return result

    except Exception as e:
        _LOGGER.error(f"[cost_get_linked_accounts] API endpoint failed: {e}")
        raise


# =============================================================================
# Credits Detail 기능은 기존 Cost.get_data API에 통합됨
#
# SpaceONE 프레임워크 제약으로 새로운 엔드포인트 추가 불가
# task_options.credits_detail_mode = true 로 Credits Detail 모드 활성화
# =============================================================================


# =============================================================================
# Credits Detail 기능은 기존 Cost.get_data API에 통합됨
#
# 사용법:
# task_options.credits_detail_mode = true
# task_options.credits_detail_limit = 100 (선택사항)


# ============================================================================
# 성능 최적화 함수들
# ============================================================================


def _estimate_records_size(records: list) -> int:
    """레코드 리스트의 예상 크기를 바이트 단위로 계산"""
    if not records:
        return 0

    try:
        # 첫 번째 레코드를 기준으로 크기 추정
        import json

        sample_record = records[0]
        sample_size = len(json.dumps(sample_record, ensure_ascii=False).encode("utf-8"))

        # 전체 크기 추정 (JSON 구조 오버헤드 포함)
        estimated_size = sample_size * len(records)
        estimated_size += 100  # {"results": [...]} 구조 오버헤드

        return estimated_size
    except Exception:
        # 추정 실패 시 보수적인 값 반환
        return len(records) * PERFORMANCE_CONFIG["avg_record_size_bytes"]


def _calculate_optimal_batch_size(records: list) -> int:
    """gRPC 메시지 크기 제한을 고려한 최적 배치 크기 계산"""
    if not records:
        return PERFORMANCE_CONFIG["min_batch_size"]

    max_message_size = PERFORMANCE_CONFIG["grpc_message_size_limit"]
    min_batch_size = PERFORMANCE_CONFIG["min_batch_size"]
    max_batch_size = PERFORMANCE_CONFIG["max_batch_size"]

    # 단일 레코드 크기 추정
    try:
        import json

        sample_record = records[0]
        single_record_size = len(
            json.dumps(sample_record, ensure_ascii=False).encode("utf-8")
        )

        # 안전 마진을 고려한 최적 배치 크기 계산
        optimal_size = max_message_size // (
            single_record_size + 50
        )  # 50바이트 오버헤드

        # 범위 제한 적용
        optimal_size = max(min_batch_size, min(optimal_size, max_batch_size))

        return optimal_size
    except Exception:
        # 계산 실패 시 기본값 반환
        return PERFORMANCE_CONFIG["grpc_response_batch_size"]


def _create_optimized_batches(records: list) -> Generator[dict, None, None]:
    """레코드 리스트를 최적화된 배치로 분할하여 yield"""
    if not records:
        return

    total_records = len(records)
    optimal_batch_size = _calculate_optimal_batch_size(records)

    # 배치 수 계산
    batch_count = (total_records + optimal_batch_size - 1) // optimal_batch_size

    # DEBUG 레벨에서만 성능 정보 로깅
    if PERFORMANCE_CONFIG["enable_performance_logging"] and _LOGGER.isEnabledFor(
        logging.DEBUG
    ):
        _LOGGER.debug(
            f"{total_records}개 레코드를 {batch_count}개 배치로 처리 (배치당 최대 {optimal_batch_size}개)"
        )

    # 배치 단위로 레코드 분할
    for i in range(0, total_records, optimal_batch_size):
        batch_records = records[i : i + optimal_batch_size]
        batch_size = len(batch_records)

        # 메시지 크기 검증
        estimated_size = _estimate_records_size(batch_records)
        max_size = PERFORMANCE_CONFIG["grpc_message_size_limit"]

        if estimated_size > max_size:
            # 배치가 너무 큰 경우 더 작게 분할
            smaller_batch_size = max(1, batch_size // 2)
            _LOGGER.warning(
                f"배치 크기 자동 조정: {batch_size} → {smaller_batch_size}개 "
                f"(메시지 크기: {estimated_size:,} bytes 초과)"
            )

            # 재귀적으로 더 작은 배치 생성
            yield from _create_optimized_batches(batch_records[:smaller_batch_size])
            if len(batch_records) > smaller_batch_size:
                yield from _create_optimized_batches(batch_records[smaller_batch_size:])
        else:
            # 적절한 크기의 배치 생성
            batch_result = {"results": batch_records}
            yield batch_result


# =============================================================================
