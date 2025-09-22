import logging
import os
from collections.abc import Generator
from typing import Set
from threading import Lock

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
from plugin.manager.credits_detail_manager import CreditsDetailManager

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

# 🎯 전역 프로젝트 처리 추적 시스템
_processed_projects: Set[str] = set()
_processing_lock = Lock()
_expected_total_projects = 0  # JobManager에서 실제 생성된 태스크 수 (동적 설정)

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
    _LOGGER.info("🚀 [job_get_tasks] API endpoint called - 태스크 생성 시작")
    
    # 🎯 전역 프로젝트 처리 추적 시스템 초기화
    with _processing_lock:
        _processed_projects.clear()
    _LOGGER.info("🔄 [job_get_tasks] 프로젝트 처리 추적 시스템 초기화 완료")
    
    # 🎯 중요: 프로젝트 태스크 생성 시작 알림
    _LOGGER.info("📊 [job_get_tasks] JobManager가 BigQuery에서 활성 프로젝트를 탐지하여 태스크를 생성합니다...")
    _LOGGER.info("🔍 [job_get_tasks] 스마트 필터링으로 비용/사용량이 있는 프로젝트만 선별합니다...")

    try:
        # 파라미터 기본 검증
        if not params:
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["domain_id", "options", "secret_data"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")
            
        # 요청 파라미터 상세 로깅
        _LOGGER.info(f"📋 [job_get_tasks] 요청 파라미터:")
        _LOGGER.info(f"   - domain_id: {params.get('domain_id')}")
        _LOGGER.info(f"   - start: {params.get('start', 'None')}")
        _LOGGER.info(f"   - options keys: {list(params.get('options', {}).keys())}")
        if 'options' in params:
            options = params['options']
            _LOGGER.info(f"   - billing_export_project_id: {options.get('billing_export_project_id')}")
            _LOGGER.info(f"   - billing_dataset_id: {options.get('billing_dataset_id')}")
            _LOGGER.info(f"   - billing_account_id: {options.get('billing_account_id')}")

        # 작업 태스크 생성
        result = _job_get_tasks_logic(params)
        
        # 🎯 태스크 생성 결과 검증 및 로깅
        actual_tasks = len(result.get('tasks', []))
        
        # 전역 변수에 실제 생성된 태스크 수 저장
        global _expected_total_projects
        with _processing_lock:
            _expected_total_projects = actual_tasks
        
        _LOGGER.info("=" * 80)
        _LOGGER.info("🎉 [job_get_tasks] 태스크 생성 API 완료!")
        _LOGGER.info(f"📊 최종 결과: {actual_tasks}개 태스크 생성")
        _LOGGER.info(f"🔄 전역 추적 시스템에 예상 태스크 수 설정: {actual_tasks}개")
        _LOGGER.info("✅ JobManager가 BigQuery에서 탐지한 모든 활성 프로젝트에 대한 태스크 생성 완료!")
        _LOGGER.info("=" * 80)

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
        
        # 🎯 Credits Detail 모드 확인
        credits_detail_mode = task_options.get("credits_detail_mode", False)
        
        _LOGGER.info(f"[_cost_get_data_logic] Credits Detail 모드: {credits_detail_mode}")
        
        if credits_detail_mode:
            # 🎯 Credits Detail 모드: 원본 데이터 조회
            _LOGGER.info("[_cost_get_data_logic] Credits Detail 모드로 실행")
            
            from plugin.manager.credits_detail_manager import CreditsDetailManager
            from plugin.connector.bigquery_connector import BigqueryConnector
            
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
            billing_table = f"gcp_billing_export_v1_{billing_account_id.replace('-', '_')}"
            
            # Credits Detail Manager 초기화
            credits_mgr.initialize(
                bigquery_connector=bigquery_connector,
                billing_export_project_id=billing_export_project_id,
                billing_dataset=billing_dataset_id,
                billing_table=billing_table
            )
            
            # 쿼리 옵션 파싱
            start_date = task_options.get("start")
            end_date = task_options.get("end")
            project_id = task_options.get("project_id")
            limit = int(task_options.get("credits_detail_limit", 100))
            
            if not start_date:
                raise ValueError("start date is required for credits detail mode")
            
            _LOGGER.info(f"[_cost_get_data_logic] Credits Detail 조회: {start_date} ~ {end_date}, 프로젝트: {project_id}, 제한: {limit}")
            
            # Credits Detail 조회
            for record in credits_mgr.get_credits_detail(
                start_date=start_date,
                end_date=end_date,
                project_id=project_id,
                billing_account_id=billing_account_id,
                limit=limit
            ):
                yield record
            
            _LOGGER.info("[_cost_get_data_logic] Credits Detail 모드 조회 완료")
            
        else:
            # 🚀 기본 모드: 기존 최적화된 집계 데이터 조회
            _LOGGER.info("[_cost_get_data_logic] 기본 모드로 실행")
            
            # CostManager 인스턴스 생성
            cost_mgr = CostManager()

            result_generator = cost_mgr.get_data(options, secret_data, task_options, schema)

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

        # 🚨 ULTIMATE: gRPC 메시지 크기 제한 해결을 위한 스마트 청킹 시스템
        # 4MB 제한을 고려하여 적절한 크기로 응답을 분할하여 전송
        batch_count = 0
        total_records = 0
        chunk_buffer = []  # 현재 청크 버퍼
        MAX_CHUNK_SIZE = 100  # 청크당 최대 레코드 수 (안전한 크기)
        
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

                        # 🚨 ULTIMATE: 최종 응답 검증 및 cost 필드 보장
                        spaceone_formatted = _ultimate_cost_field_verification(spaceone_formatted, batch_count)
                        
                        # 배치 결과를 청크 버퍼에 추가
                        batch_results = spaceone_formatted["results"]
                        
                        for record in batch_results:
                            chunk_buffer.append(record)
                            total_records += 1
                            
                            # 청크 크기에 도달하면 yield
                            if len(chunk_buffer) >= MAX_CHUNK_SIZE:
                                chunk_response = {"results": chunk_buffer}
                                _LOGGER.info(f"[cost_get_data] Yielding chunk: {len(chunk_buffer)} records")
                                yield chunk_response
                                chunk_buffer = []  # 버퍼 초기화

            except Exception as e:
                _LOGGER.error(f"[cost_get_data] Failed to process batch {batch_count}: {e}")
                # 에러가 발생해도 다음 배치 처리 계속
        
        # 🚨 ULTIMATE: 남은 레코드가 있으면 마지막 청크로 전송
        if chunk_buffer:
            final_response = {"results": chunk_buffer}
            _LOGGER.info(f"[cost_get_data] Yielding final chunk: {len(chunk_buffer)} records")
            yield final_response
        elif total_records == 0:
            _LOGGER.warning("[cost_get_data] No results to yield")
            yield {"results": []}

        # 🎯 처리 완료 프로젝트 수 검증 로깅 (JobManager와 동일한 형태)
        task_options = params.get("task_options", {})
        processed_project = task_options.get("project_id", "unknown")
        
        # 전역 처리된 프로젝트 추적 업데이트 (Pod 중복 실행 대응)
        with _processing_lock:
            if processed_project in _processed_projects:
                _LOGGER.warning(f"🔄 [중복 처리 감지] 프로젝트 '{processed_project}'가 이미 처리되었습니다!")
                _LOGGER.warning("💡 Pod 중복 실행으로 인한 중복 처리 가능성이 있습니다.")
                return  # 중복 처리 방지
            
            _processed_projects.add(processed_project)
            current_processed_count = len(_processed_projects)
        
        _LOGGER.info("=" * 80)
        _LOGGER.info("🎉 [cost_get_data] 개별 프로젝트 처리 완료!")
        _LOGGER.info(f"📋 처리된 프로젝트: {processed_project}")
        _LOGGER.info(f"📊 처리된 배치 수: {batch_count}개")
        _LOGGER.info(f"📝 처리된 총 레코드 수: {total_records}개")
        
        # 전체 진행 상황 요약
        _LOGGER.info(f"🔍 [전체 진행 상황]")
        _LOGGER.info(f"   📊 현재까지 처리된 프로젝트 수: {current_processed_count}개")
        _LOGGER.info(f"   🎯 JobManager가 생성한 총 태스크 수: {_expected_total_projects}개")
        
        # 0으로 나누기 방지
        if _expected_total_projects > 0:
            progress_rate = (current_processed_count / _expected_total_projects * 100)
            _LOGGER.info(f"   📈 진행률: {progress_rate:.1f}%")
            
            # 모든 프로젝트 처리 완료 시 최종 요약
            if current_processed_count == _expected_total_projects:
                _LOGGER.info("🎊 [최종 완료] JobManager 태스크와 동일한 수의 프로젝트 처리 완료!")
                _LOGGER.info("📝 [처리된 프로젝트 목록] - JobManager 태스크와 비교")
                sorted_projects = sorted(list(_processed_projects))
                for i, project_id in enumerate(sorted_projects, 1):
                    _LOGGER.info(f"   {i:2d}. {project_id}")
            elif current_processed_count < _expected_total_projects:
                remaining = _expected_total_projects - current_processed_count
                _LOGGER.info(f"⏳ 남은 프로젝트: {remaining}개")
            else:
                extra = current_processed_count - _expected_total_projects
                _LOGGER.warning(f"🤔 예상보다 {extra}개 더 많은 프로젝트가 처리되었습니다!")
        else:
            _LOGGER.warning("⚠️  JobManager에서 생성된 태스크 수가 설정되지 않았습니다!")
            _LOGGER.warning("💡 Job.get_tasks가 먼저 호출되어야 합니다.")
        
        _LOGGER.info("=" * 80)
        
        _LOGGER.info(f"[cost_get_data] Completed processing {batch_count} batches, {total_records} total records")
        
        # Pod 중복 실행 시 안정성을 위한 처리 지연 추가
        import time
        time.sleep(0.1)  # 100ms 지연으로 리소스 경합 방지

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
                # 🚨 ULTIMATE: 원본 레코드에서 cost 필드 강제 보장 (최우선)
                if "cost" not in record:
                    # additional_info에서 cost 복구 시도
                    cost_value = 0.0
                    if "additional_info" in record and isinstance(record["additional_info"], dict):
                        cost_after_credits = record["additional_info"].get("Cost After Credits", 0)
                        try:
                            cost_value = float(cost_after_credits)
                        except (ValueError, TypeError):
                            cost_value = 0.0
                    
                    # 최상위 cost 필드 추가 (첫 번째 위치)
                    new_record = {"cost": cost_value}
                    new_record.update(record)
                    record = new_record
                    
                    _LOGGER.error(f"[_convert_to_spaceone_format] ULTIMATE: Added missing cost field: {cost_value}")
                
                spaceone_record = _ensure_spaceone_record_format(record)
                if spaceone_record:  # 유효한 레코드만 추가
                    # 🚨 CRITICAL: cost 필드를 딕셔너리의 첫 번째 위치로 강제 이동
                    if "cost" in spaceone_record:
                        cost_value = spaceone_record.pop("cost")
                        record_copy = spaceone_record.copy()
                        spaceone_record.clear()
                        spaceone_record["cost"] = cost_value  # 첫 번째 위치에 cost 필드 배치
                        spaceone_record.update(record_copy)
                    else:
                        # cost 필드가 여전히 없으면 강제 추가
                        spaceone_record = {"cost": 0.0, **spaceone_record}
                        _LOGGER.error(f"[_convert_to_spaceone_format] ULTIMATE: Force-added cost field to spaceone_record")
                    
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
            # data.cost에서 값 추출 시도
            if "data" in record and isinstance(record["data"], dict):
                data_cost = record["data"].get("cost")
                if data_cost is not None:
                    try:
                        cost_value = float(data_cost)
                        _LOGGER.info(f"[_ensure_spaceone_record_format] RECOVERED: cost field from data.cost: {cost_value}")
                    except (ValueError, TypeError):
                        cost_value = 0.0
                        _LOGGER.warning(f"[_ensure_spaceone_record_format] INVALID data.cost, using 0.0")
                else:
                    cost_value = 0.0
                    _LOGGER.error(f"[_ensure_spaceone_record_format] CRITICAL: cost field missing completely, setting to 0.0")
            else:
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
        
        # 🚨 EMERGENCY FIX: usage_quantity를 additional_info에서 직접 추출
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
                        # _LOGGER.warning(f"[EMERGENCY] Extracted usage_quantity from additional_info: {usage_quantity_value}")
                    except (ValueError, TypeError):
                        # _LOGGER.error(f"[EMERGENCY] Invalid Usage Amount: {usage_amount}")
                        pass
                
                # Usage Amount In Pricing Units도 시도
                if usage_quantity_value == 0.0:
                    usage_pricing_amount = additional_info.get("Usage Amount In Pricing Units")
                    if usage_pricing_amount:
                        try:
                            usage_quantity_value = float(usage_pricing_amount)
                            # _LOGGER.warning(f"[EMERGENCY] Extracted usage_quantity from Usage Amount In Pricing Units: {usage_quantity_value}")
                            pass
                        except (ValueError, TypeError):
                            # _LOGGER.error(f"[EMERGENCY] Invalid Usage Amount In Pricing Units: {usage_pricing_amount}")
                            pass
        # usage_unit도 마찬가지로 처리
        if usage_unit_value == "":
            additional_info = record.get("additional_info", {})
            if isinstance(additional_info, dict):
                usage_unit = additional_info.get("Usage Unit")
                if usage_unit:
                    usage_unit_value = str(usage_unit)
                    # _LOGGER.warning(f"[EMERGENCY] Extracted usage_unit from additional_info: {usage_unit_value}")
                    pass
        # SpaceONE 필수 필드 정의 (필수 필드들을 정확한 순서로 배치)
        spaceone_record = {
            "cost": _safe_numeric_convert(cost_value),  # 🚨 최상위 필수 필드 #1
            "currency": _safe_string_convert(currency_value),  # 🚨 최상위 필수 필드 #2
            "usage_quantity": _safe_numeric_convert(usage_quantity_value),  # 🚨 EMERGENCY FIX 적용
            "usage_unit": _safe_string_convert(usage_unit_value),  # 🚨 EMERGENCY FIX 적용
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

        # billed_date 특별 처리 (빈 값인 경우 None 유지 - 현재 날짜 사용하지 않음)
        if not spaceone_record["billed_date"]:
            spaceone_record["billed_date"] = None
            _LOGGER.warning("[_ensure_spaceone_record_format] billed_date is empty, keeping as None")

        # 🚨 ULTIMATE: 최종 cost 필드 보장 (이중 검증)
        if "cost" not in spaceone_record or spaceone_record["cost"] is None:
            spaceone_record["cost"] = 0.0
            _LOGGER.error(f"[_ensure_spaceone_record_format] ULTIMATE: Final cost field enforcement applied")

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
                if "data" in record and isinstance(record["data"], dict) and "cost" in record["data"]:
                    try:
                        record["cost"] = float(record["data"]["cost"])
                        fixed_count += 1
                        _LOGGER.info(f"[ULTIMATE] Batch {batch_count}, Record {i}: Recovered cost from data.cost = {record['cost']}")
                    except (ValueError, TypeError):
                        record["cost"] = 0.0
                        missing_cost_count += 1
                        _LOGGER.error(f"[ULTIMATE] Batch {batch_count}, Record {i}: Invalid data.cost, forced to 0.0")
                else:
                    record["cost"] = 0.0
                    missing_cost_count += 1
                    _LOGGER.error(f"[ULTIMATE] Batch {batch_count}, Record {i}: No cost field found, forced to 0.0")
            elif record["cost"] is None:
                record["cost"] = 0.0
                fixed_count += 1
                _LOGGER.warning(f"[ULTIMATE] Batch {batch_count}, Record {i}: None cost converted to 0.0")
            
            # cost 필드를 최상위 첫 번째 위치로 이동 (SpaceONE 호환성)
            if "cost" in record:
                cost_value = record.pop("cost")
                record_copy = record.copy()
                record.clear()
                record["cost"] = cost_value
                record.update(record_copy)
    
    if fixed_count > 0 or missing_cost_count > 0:
        _LOGGER.info(f"[ULTIMATE] Batch {batch_count}: Fixed {fixed_count} records, Missing {missing_cost_count} records")
    
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


# =============================================================================
# 🎯 Credits Detail 기능은 기존 Cost.get_data API에 통합됨
# 
# SpaceONE 프레임워크 제약으로 새로운 엔드포인트 추가 불가
# task_options.credits_detail_mode = true 로 Credits Detail 모드 활성화
# =============================================================================


# =============================================================================
# 🎯 Credits Detail 기능은 기존 Cost.get_data API에 통합됨
# 
# 사용법:
# task_options.credits_detail_mode = true
# task_options.credits_detail_limit = 100 (선택사항)
# =============================================================================
