"""동시성 제어 및 파일 처리 최적화 유틸리티"""

import hashlib
import logging
import threading
import time
from contextlib import contextmanager
from typing import Optional

from plugin.conf.cost_conf import DATA_SOURCE_TYPES, DEFAULT_DATA_SOURCE_TYPE

_LOGGER = logging.getLogger("spaceone")

# BigQuery 필수 옵션 (JobManager와 동일)
REQUIRED_OPTIONS = [
    "billing_export_project_id",
    "billing_dataset_id",
    "billing_account_id",
]


class ConcurrencyManager:
    """파일 처리 동시성 제어 및 중복 요청 관리"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """싱글톤 패턴으로 인스턴스 생성"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._file_locks: dict[str, threading.RLock] = {}
            self._processing_files: set[str] = set()
            self._session_cache: dict[str, dict] = {}
            self._main_lock = threading.RLock()
            self._initialized = True

    def _get_file_key(self, bucket_name: str, file_path: str) -> str:
        """파일의 고유 키 생성"""
        return f"{bucket_name}/{file_path}"

    def _get_session_key(self, project_id: str, bucket_name: str) -> str:
        """세션의 고유 키 생성"""
        return f"{project_id}:{bucket_name}"

    @contextmanager
    def acquire_file_lock(
        self, bucket_name: str, file_path: str, timeout: float = 30.0
    ):
        """파일 처리를 위한 락 획득"""
        file_key = self._get_file_key(bucket_name, file_path)

        with self._main_lock:
            # 파일별 락이 없으면 생성
            if file_key not in self._file_locks:
                self._file_locks[file_key] = threading.RLock()
            file_lock = self._file_locks[file_key]

        # 타임아웃과 함께 락 획득 시도
        acquired = file_lock.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock for file: {file_key}")

        try:
            with self._main_lock:
                # 락 획득 후 다시 한 번 확인 (race condition 방지)
                if file_key in self._processing_files:
                    # 이미 처리 중인 파일은 None을 yield하여 건너뛰기
                    yield None
                    return

                self._processing_files.add(file_key)

            yield file_key

        finally:
            with self._main_lock:
                self._processing_files.discard(file_key)

            file_lock.release()

    def is_file_processing(self, bucket_name: str, file_path: str) -> bool:
        """파일이 현재 처리 중인지 확인"""
        file_key = self._get_file_key(bucket_name, file_path)
        with self._main_lock:
            return file_key in self._processing_files

    def cache_session(self, project_id: str, bucket_name: str, session_data: dict):
        """GCS 세션 캐싱"""
        session_key = self._get_session_key(project_id, bucket_name)
        with self._main_lock:
            self._session_cache[session_key] = {
                "data": session_data,
                "created_at": time.time(),
            }

    def get_cached_session(
        self, project_id: str, bucket_name: str, max_age: float = 300.0
    ) -> Optional[dict]:
        """캐시된 GCS 세션 조회 (기본 5분 TTL)"""
        session_key = self._get_session_key(project_id, bucket_name)

        with self._main_lock:
            if session_key in self._session_cache:
                cache_entry = self._session_cache[session_key]
                age = time.time() - cache_entry["created_at"]

                if age <= max_age:
                    return cache_entry["data"]
                else:
                    # 만료된 세션 제거
                    del self._session_cache[session_key]

        return None

    def clear_expired_sessions(self, max_age: float = 300.0):
        """만료된 세션 정리"""
        current_time = time.time()
        with self._main_lock:
            expired_keys = [
                key
                for key, cache_entry in self._session_cache.items()
                if current_time - cache_entry["created_at"] > max_age
            ]

            for key in expired_keys:
                del self._session_cache[key]

    def get_processing_stats(self) -> dict:
        """현재 처리 상태 통계"""
        with self._main_lock:
            return {
                "processing_files_count": len(self._processing_files),
                "cached_sessions_count": len(self._session_cache),
                "file_locks_count": len(self._file_locks),
                "processing_files": list(self._processing_files),
            }


class RequestDeduplicator:
    """요청 중복 제거 관리"""

    def __init__(self, ttl: float = 30.0):
        self.ttl = ttl
        self._requests: dict[str, float] = {}
        self._lock = threading.RLock()

    def _get_data_source_type(self, options: dict) -> str:
        """데이터 소스 타입 결정 (JobManager와 동일한 로직)"""
        # 1. 명시적 data_source_type 확인
        data_source_type = options.get("data_source_type")
        if data_source_type and data_source_type in DATA_SOURCE_TYPES.values():
            return data_source_type

        # 2. 'source' 파라미터 지원 (3개 고정 값: bigquery, gcs, http)
        source = options.get("source")
        if source == "bigquery":
            return DATA_SOURCE_TYPES["bigquery"]
        elif source == "gcs":
            return DATA_SOURCE_TYPES["gcs"]
        elif source == "http":
            return DATA_SOURCE_TYPES["http_file"]

        # 3. 파라미터 기반 자동 감지
        has_bucket = "bucket_name" in options
        has_bigquery_params = all(key in options for key in REQUIRED_OPTIONS)

        if has_bucket and not has_bigquery_params:
            return DATA_SOURCE_TYPES["gcs"]  # GCS로 변경
        elif has_bigquery_params:
            return DATA_SOURCE_TYPES["bigquery"]

        # 4. 기본값 반환
        return DEFAULT_DATA_SOURCE_TYPE

    def generate_request_hash(self, options: dict, task_options: dict) -> str:
        """요청의 해시 생성 - 데이터 소스 타입으로만 식별"""
        # 데이터 소스 타입 결정
        data_source_type = self._get_data_source_type(options)

        # 데이터 소스 타입을 기반으로 한 핵심 파라미터만 사용
        key_data = {
            "data_source_type": data_source_type,
            "file_path": task_options.get("file_path"),
            "project_id": options.get("project_id"),
            "field_mapper": options.get("field_mapper", {}),
            "select_cost": options.get("select_cost"),
        }

        key_str = str(sorted(key_data.items()))
        return hashlib.md5(key_str.encode()).hexdigest()

    def is_duplicate_request(self, request_hash: str) -> bool:
        """중복 요청인지 확인"""
        current_time = time.time()

        with self._lock:
            # 만료된 요청 정리
            expired_hashes = [
                h
                for h, timestamp in self._requests.items()
                if current_time - timestamp > self.ttl
            ]
            for h in expired_hashes:
                del self._requests[h]

            # 중복 요청 확인
            if request_hash in self._requests:
                return True

            # 새 요청 등록
            self._requests[request_hash] = current_time
            return False


# 전역 인스턴스
concurrency_manager = ConcurrencyManager()
request_deduplicator = RequestDeduplicator()
