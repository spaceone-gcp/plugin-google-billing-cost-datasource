import logging
from io import BytesIO
from typing import IO, Optional

import requests
from google.cloud import storage
from google.oauth2 import service_account

# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.connector import BaseConnector
    from spaceone.core.error import ERROR_INVALID_ARGUMENT
except ImportError:
    # Mock for local development
    class BaseConnector:
        """Mock BaseConnector for local development"""

        def __init__(self, *args, **kwargs):
            pass

    class MockError:
        def __call__(self, *args, **kwargs):
            return Exception("Mock SpaceONE Error")

    ERROR_INVALID_ARGUMENT = MockError()

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
        """GCS 버킷에서 파일 목록 조회"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)

            if pattern:
                # 특정 파일 경로인지 확인 (정확한 파일명 포함)
                if pattern.endswith(('.parquet', '.csv', '.json', '.gz')):
                    # 정확한 파일 경로인 경우, 해당 파일이 존재하는지 확인
                    try:
                        blob = bucket.blob(pattern)
                        if blob.exists():
                            _LOGGER.info(f"[GcsConnector] Found specific file: {pattern}")
                            return [
                                {
                                    "name": blob.name,
                                    "size": blob.size,
                                    "updated": blob.updated,
                                    "content_type": blob.content_type,
                                    "bucket": bucket_name,
                                }
                            ]
                        else:
                            _LOGGER.warning(f"[GcsConnector] Specific file not found: {pattern}")
                            return []
                    except Exception as e:
                        _LOGGER.warning(f"[GcsConnector] Error checking specific file {pattern}: {e}")
                        # 실패 시 prefix 검색으로 폴백
                        
                # 패턴/접두사 검색
                blobs = bucket.list_blobs(prefix=pattern)
            else:
                blobs = bucket.list_blobs()

            files = []
            count = 0
            total_scanned = 0

            for blob in blobs:
                total_scanned += 1
                if self._is_supported_file(blob.name):
                    files.append(
                        {
                            "name": blob.name,
                            "size": blob.size,
                            "updated": blob.updated,
                            "content_type": blob.content_type,
                            "bucket": bucket_name,
                        }
                    )
                    count += 1

                    # limit이 지정된 경우 해당 수만큼만 반환
                    if limit and count >= limit:
                        break

            _LOGGER.info(f"[GcsConnector] Pattern '{pattern}' search result: {len(files)} files found (scanned {total_scanned})")
            return files

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to list GCS files: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{pattern or '*'}"
            ) from e

    def list_gcs_files_by_path(
        self,
        bucket_name: str,
        project_id: str,
        year: str,
        month: str,
        limit: int = None,
    ) -> list[dict]:
        """GCS 버킷의 특정 경로(project_id/year/month/)에서 파일 목록 직접 조회"""
        try:
            # 경로 구성: project_id/year/month/
            path_prefix = f"{project_id}/{year}/{month}/"

            bucket = self.gcs_client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=path_prefix)

            files = []
            count = 0
            total_scanned = 0

            for blob in blobs:
                total_scanned += 1
                # 폴더가 아닌 실제 파일만 처리 (경로가 /로 끝나지 않는 경우)
                if not blob.name.endswith("/") and self._is_supported_file(blob.name):
                    files.append(
                        {
                            "name": blob.name,
                            "size": blob.size,
                            "updated": blob.updated,
                            "content_type": blob.content_type,
                            "bucket": bucket_name,
                        }
                    )
                    count += 1

                    # limit이 지정된 경우 해당 수만큼만 반환
                    if limit and count >= limit:
                        break

            return files

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to list GCS files by path: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{project_id}/{year}/{month}/"
            ) from e

    def download_gcs_file_stream(self, bucket_name: str, file_path: str) -> IO:
        """GCS 파일을 스트림으로 다운로드"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_path)

            if not blob.exists():
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}")

            # 파일 크기 검증
            if blob.size is not None and blob.size > GCS_CONFIG["max_file_size"]:
                raise ERROR_INVALID_ARGUMENT(
                    key=f"File size {blob.size} exceeds maximum allowed size {GCS_CONFIG['max_file_size']}"
                )

            # 메모리로 다운로드
            file_content = BytesIO()
            blob.download_to_file(file_content)
            file_content.seek(0)

            # 실제 다운로드된 크기 확인
            file_content.tell()
            file_content.seek(0)  # 다시 처음으로 이동

            return file_content

        except Exception as e:
            _LOGGER.error(f"[GcsConnector] Failed to download GCS file: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}") from e

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
            if (
                content_length
                and int(content_length) > GCS_CONFIG["max_file_size"]
            ):
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
        """GCS 파일 메타데이터 조회"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_path)

            if not blob.exists():
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}")

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
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}") from e

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
