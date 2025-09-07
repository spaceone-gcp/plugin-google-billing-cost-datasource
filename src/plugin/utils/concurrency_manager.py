"""동시성 제어 및 파일 처리 최적화 유틸리티"""

import hashlib
import logging
import threading
import time
from contextlib import contextmanager
from typing import Dict, Optional, Set

_LOGGER = logging.getLogger("spaceone")


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
            self._file_locks: Dict[str, threading.RLock] = {}
            self._processing_files: Set[str] = set()
            self._session_cache: Dict[str, Dict] = {}
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
            _LOGGER.warning(
                f"[ConcurrencyManager] Failed to acquire lock for file: {file_key} within {timeout}s"
            )
            raise TimeoutError(f"Could not acquire lock for file: {file_key}")

        try:
            with self._main_lock:
                # 락 획득 후 다시 한 번 확인 (race condition 방지)
                if file_key in self._processing_files:
                    _LOGGER.info(
                        f"[ConcurrencyManager] File {file_key} is already being processed by another request, skipping"
                    )
                    # 이미 처리 중인 파일은 None을 yield하여 건너뛰기
                    yield None
                    return

                self._processing_files.add(file_key)
                _LOGGER.debug(
                    f"[ConcurrencyManager] Started processing file: {file_key}"
                )

            yield file_key

        finally:
            with self._main_lock:
                self._processing_files.discard(file_key)
                _LOGGER.debug(
                    f"[ConcurrencyManager] Finished processing file: {file_key}"
                )

            file_lock.release()

    def is_file_processing(self, bucket_name: str, file_path: str) -> bool:
        """파일이 현재 처리 중인지 확인"""
        file_key = self._get_file_key(bucket_name, file_path)
        with self._main_lock:
            return file_key in self._processing_files

    def cache_session(self, project_id: str, bucket_name: str, session_data: Dict):
        """GCS 세션 캐싱"""
        session_key = self._get_session_key(project_id, bucket_name)
        with self._main_lock:
            self._session_cache[session_key] = {
                "data": session_data,
                "created_at": time.time(),
            }
            _LOGGER.debug(f"[ConcurrencyManager] Cached session for: {session_key}")

    def get_cached_session(
        self, project_id: str, bucket_name: str, max_age: float = 300.0
    ) -> Optional[Dict]:
        """캐시된 GCS 세션 조회 (기본 5분 TTL)"""
        session_key = self._get_session_key(project_id, bucket_name)
        with self._main_lock:
            if session_key in self._session_cache:
                cache_entry = self._session_cache[session_key]
                age = time.time() - cache_entry["created_at"]

                if age <= max_age:
                    _LOGGER.debug(
                        f"[ConcurrencyManager] Using cached session for: {session_key} (age: {age:.1f}s)"
                    )
                    return cache_entry["data"]
                else:
                    # 만료된 세션 제거
                    del self._session_cache[session_key]
                    _LOGGER.debug(
                        f"[ConcurrencyManager] Expired session removed: {session_key}"
                    )

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
                _LOGGER.debug(f"[ConcurrencyManager] Removed expired session: {key}")

            if expired_keys:
                _LOGGER.info(
                    f"[ConcurrencyManager] Cleaned up {len(expired_keys)} expired sessions"
                )

    def get_processing_stats(self) -> Dict:
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
        self._requests: Dict[str, float] = {}
        self._lock = threading.RLock()

    def generate_request_hash(self, options: Dict, task_options: Dict) -> str:
        """요청의 해시 생성"""
        # 중복 제거를 위한 핵심 파라미터만 사용
        key_data = {
            "bucket_name": options.get("bucket_name"),
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
                age = current_time - self._requests[request_hash]
                _LOGGER.info(
                    f"[RequestDeduplicator] Duplicate request detected: {request_hash} (age: {age:.1f}s)"
                )
                return True

            # 새 요청 등록
            self._requests[request_hash] = current_time
            _LOGGER.debug(
                f"[RequestDeduplicator] New request registered: {request_hash}"
            )
            return False


# 전역 인스턴스
concurrency_manager = ConcurrencyManager()
request_deduplicator = RequestDeduplicator()
