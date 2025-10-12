"""
에러 처리 및 복구 유틸리티 모듈

이 모듈은 Job.get_tasks 및 기타 작업에서 발생할 수 있는
일시적 에러들을 처리하고 복구하는 기능을 제공합니다.
"""

import logging
import time
from functools import wraps
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[Exception, ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """
    함수 실행 실패 시 재시도하는 데코레이터

    Args:
        max_retries: 최대 재시도 횟수
        delay: 초기 지연 시간 (초)
        backoff_factor: 지연 시간 증가 배수
        exceptions: 재시도할 예외 타입들
        on_retry: 재시도 시 호출할 콜백 함수

    Returns:
        데코레이터 함수
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        _LOGGER.error(
                            f"[retry_on_failure] Function {func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise

                    _LOGGER.warning(
                        f"[retry_on_failure] Function {func.__name__} attempt {attempt + 1} failed: {e}, "
                        f"retrying in {current_delay}s..."
                    )

                    if on_retry:
                        on_retry(attempt + 1, e)

                    time.sleep(current_delay)
                    current_delay *= backoff_factor

            # 이 지점에 도달하면 안되지만, 안전장치
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def safe_execute(
    func: Callable, *args, default_return: Any = None, log_errors: bool = True, **kwargs
) -> tuple[bool, Any]:
    """
    함수를 안전하게 실행하고 에러 발생 시 기본값을 반환

    Args:
        func: 실행할 함수
        *args: 함수 인자
        default_return: 에러 발생 시 반환할 기본값
        log_errors: 에러 로깅 여부
        **kwargs: 함수 키워드 인자

    Returns:
        (성공 여부, 결과값) 튜플
    """
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        if log_errors:
            _LOGGER.error(f"[safe_execute] Function {func.__name__} failed: {e}")
        return False, default_return


class GracefulErrorHandler:
    """
    작업 실패 시 우아한 복구를 위한 에러 핸들러
    """

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.error_count = 0
        self.last_error = None

    def handle_error(self, error: Exception, context: str = "") -> bool:
        """
        에러를 처리하고 계속 진행할지 결정

        Args:
            error: 발생한 예외
            context: 에러 발생 컨텍스트

        Returns:
            계속 진행할지 여부
        """
        self.error_count += 1
        self.last_error = error

        error_info = f"{context}: {error}" if context else str(error)

        _LOGGER.warning(
            f"[GracefulErrorHandler] {self.operation_name} - Error #{self.error_count}: {error_info}"
        )

        # 특정 에러 타입에 따른 처리
        if "permission" in str(error).lower() or "access" in str(error).lower():
            _LOGGER.info(
                f"[GracefulErrorHandler] {self.operation_name} - Access/permission error detected, "
                f"continuing with partial results"
            )
            return True  # 권한 에러는 계속 진행

        elif "timeout" in str(error).lower() or "connection" in str(error).lower():
            _LOGGER.info(
                f"[GracefulErrorHandler] {self.operation_name} - Network error detected, "
                f"continuing with partial results"
            )
            return True  # 네트워크 에러는 계속 진행

        elif self.error_count < 5:  # 최대 5개 에러까지 허용
            return True

        else:
            _LOGGER.error(
                f"[GracefulErrorHandler] {self.operation_name} - Too many errors ({self.error_count}), "
                f"stopping operation"
            )
            return False

    def get_summary(self) -> dict:
        """에러 처리 요약 정보 반환"""
        return {
            "operation_name": self.operation_name,
            "error_count": self.error_count,
            "last_error": str(self.last_error) if self.last_error else None,
            "status": "completed_with_errors" if self.error_count > 0 else "success",
        }


def validate_job_response(response: dict) -> bool:
    """
    Job 응답이 유효한지 검증

    Args:
        response: Job.get_tasks 응답

    Returns:
        응답 유효성 여부
    """
    if not isinstance(response, dict):
        _LOGGER.error("[validate_job_response] Response is not a dictionary")
        return False

    required_fields = ["tasks", "changed"]
    missing_fields = [field for field in required_fields if field not in response]

    if missing_fields:
        _LOGGER.error(
            f"[validate_job_response] Missing required fields: {missing_fields}"
        )
        return False

    if not isinstance(response["tasks"], list):
        _LOGGER.error("[validate_job_response] 'tasks' field is not a list")
        return False

    if not isinstance(response["changed"], list):
        _LOGGER.error("[validate_job_response] 'changed' field is not a list")
        return False

    for changed_item in response["changed"]:
        if isinstance(changed_item, dict) and "start" in changed_item:
            start_value = changed_item["start"]
            if isinstance(start_value, str) and len(start_value) > 7:
                _LOGGER.error(
                    f"[validate_job_response] 'start' field too long: '{start_value}' "
                    f"({len(start_value)} chars, max 7 allowed)"
                )
                return False

    _LOGGER.debug(
        f"[validate_job_response] Valid response: {len(response['tasks'])} tasks, "
        f"{len(response['changed'])} changed items"
    )
    return True


def create_empty_job_response(reason: str = "No data available") -> dict:
    """
    빈 Job 응답을 생성 (에러 발생 시 fallback)

    Args:
        reason: 빈 응답 생성 이유

    Returns:
        빈 Job 응답
    """
    _LOGGER.info(f"[create_empty_job_response] Creating empty response: {reason}")

    return {
        "tasks": [],
        "changed": [
            {
                "start": time.strftime("%Y-%m"),  # 현재 연월 (7자 이하)
                "reason": reason,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        ],
    }
