import logging
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


from .manager.cost_manager import CostManager
from .manager.data_source_manager import DataSourceManager
from .manager.job_manager import JobManager

_LOGGER = logging.getLogger("spaceone")

app = DataSourcePluginServer()


# 실제 비즈니스 로직 함수들 (테스트 가능)
def _data_source_init_logic(params: dict) -> dict:
    """init plugin by options - 실제 로직"""
    _LOGGER.info(
        "[_data_source_init_logic] Starting data source initialization process"
    )
    _LOGGER.debug(f"[_data_source_init_logic] Input parameters: {list(params.keys())}")

    try:
        # 파라미터 추출 및 검증
        options = params["options"]
        _LOGGER.debug(
            f"[_data_source_init_logic] Options extracted: {list(options.keys())}"
        )

        # DataSourceManager 인스턴스 생성
        _LOGGER.debug("[_data_source_init_logic] Creating DataSourceManager instance")
        data_source_mgr = DataSourceManager()
        _LOGGER.debug(
            "[_data_source_init_logic] DataSourceManager created successfully"
        )

        # 초기화 응답 생성
        _LOGGER.info("[_data_source_init_logic] Generating initialization response")
        result = data_source_mgr.init_response(options)

        _LOGGER.info(
            "[_data_source_init_logic] Data source initialization completed successfully"
        )
        _LOGGER.debug(
            f"[_data_source_init_logic] Result keys: {list(result.keys()) if result else 'None'}"
        )

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
    _LOGGER.info("[data_source_init] API endpoint called - DataSource.init")
    _LOGGER.debug(
        f"[data_source_init] Request received with parameters: {list(params.keys()) if params else 'None'}"
    )

    try:
        # 파라미터 기본 검증
        if not params:
            _LOGGER.error("[data_source_init] No parameters provided")
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            _LOGGER.error(
                f"[data_source_init] Missing required parameters: {missing_params}"
            )
            raise ValueError(f"Missing required parameters: {missing_params}")

        _LOGGER.debug(
            "[data_source_init] All required parameters present, delegating to logic function"
        )

        result = _data_source_init_logic(params)

        _LOGGER.info("[data_source_init] API endpoint completed successfully")
        _LOGGER.debug(
            f"[data_source_init] Response structure: {list(result.keys()) if result else 'None'}"
        )

        return result

    except Exception as e:
        _LOGGER.error(f"[data_source_init] API endpoint failed: {e}")
        raise

# 데이터 소스 검증
def _data_source_verify_logic(params: dict) -> None:
    """verify plugin - 실제 로직"""
    _LOGGER.info(
        "[_data_source_verify_logic] Starting data source verification process"
    )
    _LOGGER.debug(
        f"[_data_source_verify_logic] Input parameters: {list(params.keys())}"
    )

    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params.get("secret_data", {})
        _LOGGER.debug(
            f"[_data_source_verify_logic] Options keys: {list(options.keys())}"
        )
        _LOGGER.debug(
            f"[_data_source_verify_logic] Secret data keys: {list(secret_data.keys()) if secret_data else 'None'}"
        )

        # 선택적 파라미터 추출
        domain_id = params.get("domain_id")
        schema = params.get("schema")
        _LOGGER.debug(
            f"[_data_source_verify_logic] Optional parameters - "
            f"Domain ID: {domain_id}, Schema: {schema}"
        )

        # DataSourceManager 인스턴스 생성 및 검증 수행
        _LOGGER.debug("[_data_source_verify_logic] Creating DataSourceManager instance")
        data_source_mgr = DataSourceManager()
        _LOGGER.debug(
            "[_data_source_verify_logic] DataSourceManager created successfully"
        )

        _LOGGER.info("[_data_source_verify_logic] Starting plugin verification")
        data_source_mgr.verify_plugin(options, secret_data, domain_id, schema)

        _LOGGER.info(
            "[_data_source_verify_logic] Data source verification completed successfully"
        )

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
    _LOGGER.info("[data_source_verify] API endpoint called - DataSource.verify")
    _LOGGER.debug(
        f"[data_source_verify] Request received with parameters: {list(params.keys()) if params else 'None'}"
    )

    try:
        # 파라미터 기본 검증
        if not params:
            _LOGGER.error("[data_source_verify] No parameters provided")
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            _LOGGER.error(
                f"[data_source_verify] Missing required parameters: {missing_params}"
            )
            raise ValueError(f"Missing required parameters: {missing_params}")

        _LOGGER.debug(
            "[data_source_verify] All required parameters present, delegating to logic function"
        )

        _data_source_verify_logic(params)

        _LOGGER.info("[data_source_verify] API endpoint completed successfully")

    except Exception as e:
        _LOGGER.error(f"[data_source_verify] API endpoint failed: {e}")
        raise

# 작업 태스크 생성
def _job_get_tasks_logic(params: dict) -> dict:
    """get tasks - 실제 로직"""
    _LOGGER.info("[_job_get_tasks_logic] Starting job task generation process")
    _LOGGER.debug(
        f"[_job_get_tasks_logic] Input parameters keys: {list(params.keys())}"
    )

    # 필수 파라미터 추출 및 검증
    domain_id = params["domain_id"]
    options = params["options"]
    secret_data = params["secret_data"]

    _LOGGER.info(f"[_job_get_tasks_logic] Processing for domain: {domain_id}")
    _LOGGER.debug(f"[_job_get_tasks_logic] Options keys: {list(options.keys())}")
    _LOGGER.debug(
        f"[_job_get_tasks_logic] Secret data keys: {list(secret_data.keys()) if secret_data else 'None'}"
    )

    # 선택적 파라미터 추출
    schema = params.get("schema")
    start = params.get("start")
    last_synchronized_at = params.get("last_synchronized_at")

    _LOGGER.debug(
        f"[_job_get_tasks_logic] Optional parameters - "
        f"Schema: {schema}, Start: {start}, Last synchronized: {last_synchronized_at}"
    )

    # JobManager 인스턴스 생성 및 작업 요청
    _LOGGER.debug("[_job_get_tasks_logic] Creating JobManager instance")
    try:
        job_mgr = JobManager()
        _LOGGER.debug("[_job_get_tasks_logic] JobManager created successfully")

        _LOGGER.info(
            f"[_job_get_tasks_logic] Calling JobManager.get_tasks with domain: {domain_id}, "
            f"start: {start}, schema: {schema}"
        )

        result = job_mgr.get_tasks(
            domain_id, options, secret_data, schema, start, last_synchronized_at
        )

        # 결과 로깅
        task_count = len(result.get("tasks", []))
        changed_count = len(result.get("changed", []))

        _LOGGER.info(
            f"[_job_get_tasks_logic] Job task generation completed successfully - "
            f"Tasks: {task_count}, Changed: {changed_count}"
        )
        _LOGGER.debug(f"[_job_get_tasks_logic] Result structure: {list(result.keys())}")

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
    _LOGGER.info("[job_get_tasks] API endpoint called - Job.get_tasks")
    _LOGGER.debug(
        f"[job_get_tasks] Request received with parameters: {list(params.keys()) if params else 'None'}"
    )

    try:
        # 파라미터 기본 검증
        if not params:
            _LOGGER.error("[job_get_tasks] No parameters provided")
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["domain_id", "options", "secret_data"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            _LOGGER.error(
                f"[job_get_tasks] Missing required parameters: {missing_params}"
            )
            raise ValueError(f"Missing required parameters: {missing_params}")

        _LOGGER.debug(
            "[job_get_tasks] All required parameters present, delegating to logic function"
        )

        # 작업 태스크 생성
        result = _job_get_tasks_logic(params)

        _LOGGER.info(
            f"[job_get_tasks] API endpoint completed successfully - "
            f"Returning {len(result.get('tasks', []))} tasks"
        )

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
            'tags': 'dict'
            'additional_info': 'dict'
            'data': 'dict'
            'billed_date': 'str'
        }
    """
    try:
        # 파라미터 기본 검증
        if not params:
            _LOGGER.error("[cost_get_data] No parameters provided")
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "secret_data", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            _LOGGER.error(
                f"[cost_get_data] Missing required parameters: {missing_params}"
            )
            raise ValueError(f"Missing required parameters: {missing_params}")

        result_generator = _cost_get_data_logic(params)

        return result_generator

    except Exception as e:
        _LOGGER.error(f"[cost_get_data] API endpoint failed: {e}")
        raise


def _cost_get_linked_accounts_logic(params: dict) -> dict:
    """get linked accounts - 실제 로직"""
    _LOGGER.info(
        "[_cost_get_linked_accounts_logic] Starting linked accounts retrieval process"
    )
    _LOGGER.debug(
        f"[_cost_get_linked_accounts_logic] Input parameters: {list(params.keys())}"
    )

    try:
        # 필수 파라미터 추출
        options = params["options"]
        secret_data = params["secret_data"]
        _LOGGER.debug(
            f"[_cost_get_linked_accounts_logic] Options keys: {list(options.keys())}"
        )
        _LOGGER.debug(
            f"[_cost_get_linked_accounts_logic] Secret data keys: {list(secret_data.keys())}"
        )


        # 선택적 파라미터 추출
        schema = params.get("schema")
        _LOGGER.debug(
            f"[_cost_get_linked_accounts_logic] Optional parameters - Schema: {schema}"
        )

        # CostManager 인스턴스 생성
        _LOGGER.debug("[_cost_get_linked_accounts_logic] Creating CostManager instance")
        cost_mgr = CostManager()
        _LOGGER.debug(
            "[_cost_get_linked_accounts_logic] CostManager created successfully"
        )

        _LOGGER.info("[_cost_get_linked_accounts_logic] Retrieving linked accounts")
        result = cost_mgr.get_linked_accounts(options, secret_data, schema)

        _LOGGER.info(
            "[_cost_get_linked_accounts_logic] Linked accounts retrieval completed successfully"
        )
        _LOGGER.debug(
            f"[_cost_get_linked_accounts_logic] Result keys: {list(result.keys()) if result else 'None'}"
        )

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
    _LOGGER.info(
        "[cost_get_linked_accounts] API endpoint called - Cost.get_linked_accounts"
    )
    _LOGGER.debug(
        f"[cost_get_linked_accounts] Request received with parameters: {list(params.keys()) if params else 'None'}"
    )

    try:
        # 파라미터 기본 검증
        if not params:
            _LOGGER.error("[cost_get_linked_accounts] No parameters provided")
            raise ValueError("Parameters are required")

        # 필수 파라미터 확인
        required_params = ["options", "secret_data", "domain_id"]
        missing_params = [param for param in required_params if param not in params]

        if missing_params:
            _LOGGER.error(
                f"[cost_get_linked_accounts] Missing required parameters: {missing_params}"
            )
            raise ValueError(f"Missing required parameters: {missing_params}")

        _LOGGER.debug(
            "[cost_get_linked_accounts] All required parameters present, delegating to logic function"
        )

        result = _cost_get_linked_accounts_logic(params)

        _LOGGER.info("[cost_get_linked_accounts] API endpoint completed successfully")
        _LOGGER.debug(
            f"[cost_get_linked_accounts] Response structure: {list(result.keys()) if result else 'None'}"
        )

        return result

    except Exception as e:
        _LOGGER.error(f"[cost_get_linked_accounts] API endpoint failed: {e}")
        raise


