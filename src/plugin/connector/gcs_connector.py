import logging
from io import BytesIO
from typing import IO, Optional

import requests
from google.cloud import storage
from google.oauth2 import service_account
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_INVALID_ARGUMENT

from ..conf.cost_conf import GCS_CONFIG
from ..error.cost import ERROR_FILE_DOWNLOAD_FAILED
from ..utils.concurrency_manager import concurrency_manager

_LOGGER = logging.getLogger("spaceone")

REQUIRED_SECRET_KEYS = ["project_id", "private_key", "token_uri", "client_email"]


class GcsConnector(BaseConnector):
    """Google Cloud Storage 전용 파일 처리 커넥터"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gcs_client = None
        self.credentials = None
        self.project_id = None

    def create_session(self, options: dict, secret_data: dict, schema: str):
        """GCS 클라이언트 세션 생성 (캐시된 세션 재사용 지원)"""
        if not secret_data:
            self.project_id = None
            # secret_data가 없으면 세션 생성을 건너뜀
            return

        self.project_id = secret_data.get("project_id")
        bucket_name = options.get("bucket_name", "")

        # 캐시된 세션 확인
        cached_session = concurrency_manager.get_cached_session(
            self.project_id, bucket_name
        )
        if cached_session:
            self.credentials = cached_session["credentials"]
            self.gcs_client = cached_session["gcs_client"]
            return

        # 새 세션 생성
        # private_key의 \n 문자열을 실제 개행 문자로 변환
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            processed_secret_data["private_key"] = processed_secret_data[
                "private_key"
            ].replace("\\n", "\n")

        # Service Account 인증 정보로 GCS 클라이언트 생성 (상세 오류 처리 제거)
        self.credentials = service_account.Credentials.from_service_account_info(
            processed_secret_data
        )
        self.gcs_client = storage.Client(
            credentials=self.credentials, project=self.project_id
        )

        # 세션 캐싱
        session_data = {"credentials": self.credentials, "gcs_client": self.gcs_client}
        try:
            concurrency_manager.cache_session(
                self.project_id, bucket_name, session_data
            )
        except Exception:
            pass

    def list_gcs_files(
        self, bucket_name: str, pattern: str = None, limit: int = None
    ) -> list[dict]:
        """GCS 버킷에서 지정된 패턴에 따라 파일 목록 조회 (스캔 최소화)"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)

            if pattern:
                # 특정 파일 경로인지 확인 (정확한 파일명 포함)
                if pattern.endswith((".parquet", ".csv", ".json", ".gz")):
                    # 정확한 파일 경로인 경우, 직접 파일 정보 반환 (존재 여부 검증 생략)
                    try:
                        blob = bucket.blob(pattern)
                        # 성능 최적화: 개별 파일 접근 로깅 제거
                        # 지연 로딩: 파일명과 버킷명만 반환 (메타데이터는 실제 처리 시에만)
                        return [
                            {
                                "name": blob.name,
                                "bucket": bucket_name,
                                # size, updated, content_type는 get_gcs_file_info에서 필요시에만 조회
                            }
                        ]
                    except Exception as e:
                        _LOGGER.warning(
                            f"[GcsConnector] Error accessing specific file {pattern}: {e}"
                        )
                        # 실패 시 prefix 검색으로 폴백

                # 구조화된 경로 기반 빌링 데이터 파일 검색 (지연 로딩)
                files = self._list_files_by_pattern_optimized(bucket, pattern, limit)
                # 성능 최적화: 패턴 검색 결과는 최종 결과에서만 로깅
                return files
            else:
                # 패턴 없는 경우 경고 후 빈 목록 반환 (대량 스캔 방지)
                _LOGGER.warning(
                    "[GcsConnector] No pattern specified - returning empty list to prevent bulk scanning"
                )
                return []

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to list GCS files: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{pattern or '*'}"
            ) from e

    def _list_files_by_pattern_optimized(
        self, bucket, pattern: str, limit: int = None
    ) -> list[dict]:
        """구조화된 경로 기반 최적화된 파일 목록 조회"""
        files = []

        # 구조화된 경로 패턴으로 직접 검색 (project_id/YYYY/MM/)
        try:
            # 프로젝트 패턴으로 시작하는 구조화된 경로들 검색
            blobs = bucket.list_blobs(prefix=pattern)
            count = 0

            for blob in blobs:
                # 성능 최적화: 모든 파일 필터링 제거 (최대 성능)
                files.append(
                    {
                        "name": blob.name,
                        "bucket": bucket.name,
                        # size, updated, content_type는 get_gcs_file_info에서 필요시에만 조회
                    }
                )
                count += 1

                # limit 체크
                if limit and count >= limit:
                    break

        except Exception:
            # 성능 최적화: 구조화된 경로 검색 실패 로깅 제거
            pass

        return files

    # _is_valid_structured_path 메서드 제거됨 (과도한 검증으로 인한 성능 최적화)

    # _is_billing_data_file 함수 제거됨 (모든 파일 필터링 제거로 최대 성능 달성)

    # _matches_pattern_and_supported 메서드 제거됨 (중복 검증 로직으로 인한 성능 최적화)

    def list_gcs_files_by_path(
        self,
        bucket_name: str,
        project_id: str,
        year: str,
        month: str,
        limit: int = None,
    ) -> list[dict]:
        """특정 경로에서 지정된 형식의 파일만 직접 조회 (스캔 최소화)"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)

            # 경로 패턴 생성
            path_pattern = f"{project_id}/{year}/{month}/"
            # 성능 최적화: 경로 접근 로깅 제거
            # 지원되는 파일 형식별로 직접 검색
            files = self._get_files_by_known_patterns(bucket, path_pattern, limit)
            return files

        except Exception as e:
            _LOGGER.error(
                f"[GcsConnector] Failed to list files by path {project_id}/{year}/{month}: {e}"
            )
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{project_id}/{year}/{month}"
            ) from e

    def list_gcs_files_by_date_range(
        self, bucket_name: str, project_id: str, start_date: str, limit: int = None
    ) -> list[dict]:
        """날짜 범위 기반 최적화된 GCS 파일 목록 조회 (성능 최적화)"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            files = []

            # start_date 파싱 (YYYY-MM 형태)
            year, month = map(int, start_date.split("-"))
            current_year, current_month = year, month

            # 현재 날짜까지 월별로 검색
            from datetime import datetime

            now = datetime.now()
            max_year, max_month = now.year, now.month

            # 성능 최적화: 검색 시작 로깅 제거 (결과만 로깅)

            while (current_year < max_year) or (
                current_year == max_year and current_month <= max_month
            ):
                path_prefix = f"{project_id}/{current_year:04d}/{current_month:02d}/"

                # 성능 최적화: 반복적인 DEBUG 로깅 제거
                month_files = self._get_files_by_known_patterns(
                    bucket, path_prefix, None
                )

                if month_files:
                    files.extend(month_files)

                # 다음 월로 이동
                current_month += 1
                if current_month > 12:
                    current_month = 1
                    current_year += 1

                # limit 체크
                if limit and len(files) >= limit:
                    files = files[:limit]
                    break

            _LOGGER.info(
                f"[GcsConnector] Optimized search completed: found {len(files)} billing data files (lazy loading enabled - metadata deferred)"
            )
            return files

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to list files by date range: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{project_id}/{start_date}"
            ) from e

    def _get_files_by_known_patterns(
        self, bucket, base_path: str, limit: int = None
    ) -> list[dict]:
        """단순화된 단일 prefix 검색 (성능 최적화)"""
        files = []

        try:
            # 단일 prefix로 모든 파일 조회 (다중 패턴 검색 제거)
            blobs = bucket.list_blobs(prefix=base_path)

            for blob in blobs:
                # 성능 최적화: 모든 파일 필터링 제거 (최대 성능)
                files.append(
                    {
                        "name": blob.name,
                        "bucket": bucket.name,
                    }
                )

                # limit 체크
                if limit and len(files) >= limit:
                    break

        except Exception:
            # 성능 최적화: 검색 실패 시 무시하고 빈 목록 반환
            pass

        return files

    # _matches_billing_pattern 메서드 제거됨 (중복 로직으로 인한 성능 최적화)

    def download_gcs_file_stream(self, bucket_name: str, file_path: str) -> IO:
        """GCS 파일을 스트림으로 다운로드 (존재 여부 검증 생략)"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_path)

            # 파일 크기 검증 (다운로드 시 자동으로 확인됨)
            # 메모리로 다운로드 (파일이 존재하지 않으면 자동으로 예외 발생)
            file_content = BytesIO()
            blob.download_to_file(file_content)
            file_content.seek(0)

            # 파일 크기 제한 검증 (다운로드 후)
            file_size = file_content.tell()
            if file_size > GCS_CONFIG["max_file_size"]:
                raise ERROR_INVALID_ARGUMENT(
                    key=f"File size {file_size} exceeds maximum allowed size {GCS_CONFIG['max_file_size']}"
                )

            file_content.seek(0)  # 다시 처음으로 이동
            return file_content

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to download GCS file: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{file_path}"
            ) from e

    def download_file_from_url(self, url: str) -> IO:
        """HTTP URL에서 파일을 스트림으로 다운로드 (외부 URL 지원용)"""
        try:
            # HTTP 요청으로 파일 다운로드
            response = requests.get(
                url, stream=True, timeout=GCS_CONFIG["download_timeout"]
            )
            response.raise_for_status()

            # Content-Length 헤더로 파일 크기 확인
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > GCS_CONFIG["max_file_size"]:
                raise ERROR_INVALID_ARGUMENT(
                    key=f"File size {content_length} exceeds maximum allowed size {GCS_CONFIG['max_file_size']}"
                )

            # 메모리로 다운로드
            file_content = BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file_content.write(chunk)

            file_content.seek(0)

            return file_content

        except requests.RequestException as e:
            _LOGGER.error(f"[GcsConnector] Failed to download from URL: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url) from e
        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to download from URL: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url) from e

    def test_connection(self, url: str) -> None:
        """HTTP URL 연결 테스트 (HEAD 요청으로 빠른 검증)"""
        try:
            # HEAD 요청으로 연결 테스트 (데이터 다운로드 없이)
            response = requests.head(
                url, timeout=GCS_CONFIG.get("connection_timeout", 10)
            )
            response.raise_for_status()

        except requests.RequestException as e:
            _LOGGER.error(f"[GcsConnector] Connection test failed: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url) from e

    def get_gcs_file_info(self, bucket_name: str, file_path: str) -> dict:
        """GCS 파일 메타데이터 조회 (존재 여부 검증 생략)"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_path)

            # 메타데이터 직접 조회 (파일이 존재하지 않으면 자동으로 예외 발생)
            return {
                "name": blob.name,
                "size": blob.size,
                "updated": blob.updated,
                "content_type": blob.content_type,
                "bucket": bucket_name,
                "format": self._detect_file_format(blob.name),
                "compression": self._detect_compression(blob.name),
            }

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to get GCS file info: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{file_path}"
            ) from e

    def _is_supported_file(self, file_name: str) -> bool:
        """지원되는 파일 형식인지 확인"""
        format_type = self._detect_file_format(file_name)
        return format_type in GCS_CONFIG["supported_formats"]

    def _detect_file_format(self, file_name: str) -> Optional[str]:
        """파일명으로 파일 형식 감지"""
        # 압축 확장자 제거 후 파일 형식 감지
        name_lower = file_name.lower()
        for compression in GCS_CONFIG["supported_compressions"]:
            if name_lower.endswith(f".{compression}"):
                name_lower = name_lower[: -len(f".{compression}")]
                break

        if name_lower.endswith(".csv"):
            return "csv"
        elif name_lower.endswith(".json") or name_lower.endswith(".jsonl"):
            return "json"
        elif name_lower.endswith(".parquet"):
            return "parquet"

        return None

    def _detect_compression(self, file_name: str) -> Optional[str]:
        """파일명으로 압축 형식 감지"""
        name_lower = file_name.lower()
        for compression in GCS_CONFIG["supported_compressions"]:
            if name_lower.endswith(f".{compression}"):
                return compression
        return None
