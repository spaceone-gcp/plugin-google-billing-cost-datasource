import logging
import os
from collections.abc import Generator

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.cost_analysis.plugin.data_source.lib.server import (
        DataSourcePluginServer,
    )
except ImportError:
    # Mock for local development
    class DataSourcePluginServer:
        """Mock DataSourcePluginServer for local development"""

        def route(self, path):
            def decorator(func):
                return func

            return decorator


from plugin.manager.cost_manager import CostManager
from plugin.manager.data_source_manager import DataSourceManager
from plugin.manager.job_manager import JobManager

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

    # 디버깅 모드 상태 로깅
    if debug_mode:
        spaceone_logger.info("[MAIN] DEBUG 모드가 활성화되었습니다.")
        spaceone_logger.debug("[MAIN] 디버그 로깅이 작동 중입니다.")
    else:
        spaceone_logger.info("[MAIN] 프로덕션 모드로 실행 중입니다.")


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
        _LOGGER.error(f"[_data_source_init_logic] Failed to initialize data source: {e}")
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
    _LOGGER.info("[job_get_tasks] API endpoint called")

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
        _LOGGER.info(f"[job_get_tasks] Completed - {len(result.get('tasks', []))} tasks")

        return result

    except Exception as e:
        _LOGGER.error(f"[job_get_tasks] API endpoint failed: {e}")
        raise


def _cost_get_data_logic(params: dict) -> Generator[dict, None, None]:
    """get cost data - 실제 로직"""
    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params["secret_data"]

        # 선택적 파라미터 추출
        task_options = params.get("task_options", {})
        schema = params.get("schema")

        # CostManager 인스턴스 생성
        cost_mgr = CostManager()

        result_generator = cost_mgr.get_data(options, secret_data, task_options, schema)

        return result_generator

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

        result_generator = _cost_get_data_logic(params)

        # 🚨 CRITICAL: 스트리밍 방식으로 각 배치를 개별적으로 yield
        # gRPC 메시지 크기 제한 문제 해결을 위해 배치별로 전송
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

                        # 각 배치를 개별적으로 yield (메시지 크기 제한 해결)
                        batch_results = spaceone_formatted["results"]
                        total_records += len(batch_results)
                        
                        _LOGGER.info(f"[cost_get_data] Yielding batch {batch_count}: {len(batch_results)} records")
                        yield spaceone_formatted

            except Exception as e:
                _LOGGER.error(f"[cost_get_data] Failed to process batch {batch_count}: {e}")
                # 에러가 발생해도 다음 배치 처리 계속

        _LOGGER.info(f"[cost_get_data] Completed processing {batch_count} batches, {total_records} total records")

    except Exception as e:
        _LOGGER.error(f"[cost_get_data] API endpoint failed: {e}")
        raise


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
                spaceone_record = _ensure_spaceone_record_format(record)
                if spaceone_record:  # 유효한 레코드만 추가
                    # 🚨 CRITICAL: cost 필드를 딕셔너리의 첫 번째 위치로 강제 이동
                    if "cost" in spaceone_record:
                        cost_value = spaceone_record.pop("cost")
                        record_copy = spaceone_record.copy()
                        spaceone_record.clear()
                        spaceone_record["cost"] = cost_value  # 첫 번째 위치에 cost 필드 배치
                        spaceone_record.update(record_copy)
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
        # 🚨 CRITICAL: cost 필드가 최상위에 반드시 존재해야 함
        # 원본 레코드에서 cost 필드 추출 및 검증
        cost_value = record.get("cost")
        if cost_value is None:
            # cost 필드가 누락된 경우 0.0으로 설정하고 에러 로그
            cost_value = 0.0
            _LOGGER.error(f"[_ensure_spaceone_record_format] CRITICAL: cost field missing in record, setting to 0.0")
        
        # 🚨 CRITICAL: currency 필드 추출 및 보장
        currency_value = record.get("currency")
        if currency_value is None or currency_value == "":
            # additional_info에서 Currency 필드 추출 시도
            currency_value = record.get("additional_info", {}).get("Currency", "USD")
            if currency_value != "USD":
                _LOGGER.debug(f"[_ensure_spaceone_record_format] Currency extracted from additional_info: {currency_value}")
            else:
                _LOGGER.info(f"[_ensure_spaceone_record_format] Currency field missing, defaulting to USD")
        
        # SpaceONE 필수 필드 정의 (필수 필드들을 정확한 순서로 배치)
        spaceone_record = {
            "cost": _safe_numeric_convert(cost_value),  # 🚨 최상위 필수 필드 #1
            "currency": _safe_string_convert(currency_value),  # 🚨 최상위 필수 필드 #2
            "usage_quantity": _safe_numeric_convert(record.get("usage_quantity", 0.0)),
            "usage_unit": _safe_string_convert(record.get("usage_unit", "")),
            "provider": _safe_string_convert(record.get("provider", "google_cloud")),
            "region_code": _safe_string_convert(record.get("region_code", "global")),
            "product": _safe_string_convert(record.get("product", "Unknown")),
            "usage_type": _safe_string_convert(record.get("usage_type", "")),
            "resource": _safe_string_convert(record.get("resource", "")),
            "billed_date": _safe_string_convert(record.get("billed_date", "")),
            "tags": _safe_dict_convert(record.get("tags", {})),
            "additional_info": _safe_dict_convert(record.get("additional_info", {})),
            "data": _safe_dict_convert(record.get("data", {})),
        }

        # cost 필드 특별 처리 (절대 None이나 빈 값이 될 수 없음)
        if spaceone_record["cost"] is None or spaceone_record["cost"] == "":
            spaceone_record["cost"] = 0.0

        # billed_date 특별 처리 (빈 값인 경우 현재 날짜)
        if not spaceone_record["billed_date"]:
            from datetime import datetime

            spaceone_record["billed_date"] = datetime.now().strftime("%Y-%m-%d")

        return spaceone_record

    except Exception as e:
        _LOGGER.error(f"[_ensure_spaceone_record_format] Failed to format record: {e}")
        return None


def _safe_numeric_convert(value):
    """안전한 숫자 변환"""
    if value is None:
        return 0.0
    try:
        if isinstance(value, (int, float)):
            return float(value) if abs(float(value)) >= 1e-10 else 0.0
        elif isinstance(value, str):
            if value.lower() in ("", "null", "none", "nan"):
                return 0.0
            return float(value)
        else:
            return 0.0
    except (ValueError, TypeError):
        return 0.0


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
        _LOGGER.error(f"[_cost_get_linked_accounts_logic] Failed to get linked accounts: {e}")
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
