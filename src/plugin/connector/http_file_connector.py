import logging
from io import BytesIO
from typing import IO, Dict, List, Optional

import requests
from google.cloud import storage
from google.oauth2 import service_account
from spaceone.core.connector import BaseConnector
from spaceone.core.error import ERROR_INVALID_ARGUMENT, ERROR_REQUIRED_PARAMETER

from ..conf.cost_conf import HTTP_FILE_CONFIG
from ..error.cost import ERROR_FILE_DOWNLOAD_FAILED
from ..utils.concurrency_manager import concurrency_manager

_LOGGER = logging.getLogger("spaceone")

REQUIRED_SECRET_KEYS = ["project_id", "private_key", "token_uri", "client_email"]


class HttpFileConnector(BaseConnector):
    """Google Cloud Storage 기반 HTTP 파일 처리 커넥터"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gcs_client = None
        self.credentials = None
        self.project_id = None
        _LOGGER.debug(
            f"[HttpFileConnector] Initialized new HttpFileConnector instance - "
            f"Args: {args}, Kwargs: {list(kwargs.keys()) if kwargs else 'None'}"
        )

    def create_session(self, options: dict, secret_data: dict, schema: str):
        """GCS 클라이언트 세션 생성 (캐시된 세션 재사용 지원)"""
        _LOGGER.info(
            f"[HttpFileConnector] Starting session creation process for schema: {schema}"
        )
        _LOGGER.debug(
            f"[HttpFileConnector] Session creation options: {options}"
        )
        
        if not secret_data:
            _LOGGER.error("[HttpFileConnector] Session creation failed: secret_data is empty or None")
            raise ERROR_REQUIRED_PARAMETER(key="secret_data")

        _LOGGER.debug("[HttpFileConnector] Validating secret_data structure")
        try:
            self._check_secret_data(secret_data)
            _LOGGER.debug("[HttpFileConnector] Secret data validation successful")
        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Secret data validation failed: {e}")
            raise

        self.project_id = secret_data["project_id"]
        bucket_name = options.get("bucket_name", "")
        
        _LOGGER.info(
            f"[HttpFileConnector] Session parameters - Project ID: {self.project_id}, Bucket: {bucket_name or 'Not specified'}"
        )

        # 캐시된 세션 확인
        _LOGGER.debug(
            f"[HttpFileConnector] Checking for cached session - Project: {self.project_id}, Bucket: {bucket_name}"
        )
        cached_session = concurrency_manager.get_cached_session(
            self.project_id, bucket_name
        )
        if cached_session:
            self.credentials = cached_session["credentials"]
            self.gcs_client = cached_session["gcs_client"]
            _LOGGER.info(
                f"[HttpFileConnector] Successfully reused cached GCS session for project: {self.project_id}"
            )
            _LOGGER.debug(
                f"[HttpFileConnector] Cached session details - Credentials type: {type(self.credentials).__name__}, "
                f"GCS client project: {getattr(self.gcs_client, 'project', 'Unknown')}"
            )
            return

        _LOGGER.info(
            f"[HttpFileConnector] No cached session found, creating new GCS session for project: {self.project_id}"
        )

        # 새 세션 생성
        # private_key의 \n 문자열을 실제 개행 문자로 변환
        _LOGGER.debug("[HttpFileConnector] Processing secret data for authentication")
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            original_key_length = len(processed_secret_data["private_key"])
            processed_secret_data["private_key"] = processed_secret_data[
                "private_key"
            ].replace("\\n", "\n")
            new_key_length = len(processed_secret_data["private_key"])
            _LOGGER.debug(
                f"[HttpFileConnector] Private key processed - Original length: {original_key_length}, "
                f"Processed length: {new_key_length}"
            )

        # Service Account 인증 정보로 GCS 클라이언트 생성
        _LOGGER.debug("[HttpFileConnector] Creating Service Account credentials")
        try:
            self.credentials = service_account.Credentials.from_service_account_info(
                processed_secret_data
            )
            _LOGGER.debug(
                f"[HttpFileConnector] Service Account credentials created successfully - "
                f"Service account email: {getattr(self.credentials, 'service_account_email', 'Unknown')}"
            )
        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to create Service Account credentials: {e}")
            raise

        _LOGGER.debug(f"[HttpFileConnector] Creating GCS client for project: {self.project_id}")
        try:
            self.gcs_client = storage.Client(
                credentials=self.credentials, project=self.project_id
            )
            _LOGGER.debug(
                f"[HttpFileConnector] GCS client created successfully - "
                f"Client project: {self.gcs_client.project}"
            )
        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to create GCS client: {e}")
            raise

        # 세션 캐싱
        _LOGGER.debug(
            f"[HttpFileConnector] Caching new session - Project: {self.project_id}, Bucket: {bucket_name}"
        )
        session_data = {"credentials": self.credentials, "gcs_client": self.gcs_client}
        try:
            concurrency_manager.cache_session(self.project_id, bucket_name, session_data)
            _LOGGER.debug("[HttpFileConnector] Session cached successfully")
        except Exception as e:
            _LOGGER.warning(f"[HttpFileConnector] Failed to cache session (continuing anyway): {e}")

        _LOGGER.info(
            f"[HttpFileConnector] New GCS session created and cached successfully for project: {self.project_id}"
        )

    def list_files(
        self, bucket_name: str, pattern: str = None, limit: int = None
    ) -> List[Dict]:
        """버킷에서 파일 목록 조회"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)

            if pattern:
                _LOGGER.info(
                    f"[HttpFileConnector] Listing files with pattern: {pattern}"
                )
                blobs = bucket.list_blobs(prefix=pattern)
            else:
                _LOGGER.info("[HttpFileConnector] Listing all files in bucket")
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

            pattern_info = f" with pattern '{pattern}'" if pattern else ""
            _LOGGER.info(
                f"[HttpFileConnector] Found {len(files)} supported files out of {total_scanned} total files in bucket: {bucket_name}{pattern_info}"
            )
            return files

        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to list files: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{pattern or '*'}"
            )

    def list_files_by_path(
        self,
        bucket_name: str,
        project_id: str,
        year: str,
        month: str,
        limit: int = None,
    ) -> List[Dict]:
        """특정 경로(project_id/year/month/)에서 파일 목록 직접 조회"""
        try:
            # 경로 구성: project_id/year/month/
            path_prefix = f"{project_id}/{year}/{month}/"

            _LOGGER.info(
                f"[HttpFileConnector] Listing files in direct path: {bucket_name}/{path_prefix}"
            )

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

            _LOGGER.info(
                f"[HttpFileConnector] Found {len(files)} supported files out of {total_scanned} total items in path: {bucket_name}/{path_prefix}"
            )
            return files

        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to list files by path: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{project_id}/{year}/{month}/"
            )

    def download_file_stream(self, bucket_name: str, file_path: str) -> IO:
        """파일을 스트림으로 다운로드"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_path)

            if not blob.exists():
                raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}")

            # 파일 크기 검증
            if blob.size is not None and blob.size > HTTP_FILE_CONFIG["max_file_size"]:
                raise ERROR_INVALID_ARGUMENT(
                    key=f"File size {blob.size} exceeds maximum allowed size {HTTP_FILE_CONFIG['max_file_size']}"
                )

            # 메모리로 다운로드
            file_content = BytesIO()
            blob.download_to_file(file_content)
            file_content.seek(0)

            # 실제 다운로드된 크기 확인
            actual_size = file_content.tell()
            file_content.seek(0)  # 다시 처음으로 이동

            # 상세한 디버깅 정보
            blob_size_str = f"{blob.size}" if blob.size is not None else "None"
            _LOGGER.debug(
                f"[HttpFileConnector] Downloaded file: {bucket_name}/{file_path} (expected: {blob_size_str} bytes, actual: {actual_size} bytes)"
            )

            # 크기 불일치 또는 None 경고
            if blob.size is None:
                _LOGGER.warning(
                    f"[HttpFileConnector] Blob size is None for {file_path}, actual downloaded: {actual_size} bytes"
                )
            elif actual_size != blob.size:
                _LOGGER.warning(
                    f"[HttpFileConnector] File size mismatch for {file_path}: expected {blob.size}, got {actual_size}"
                )
            return file_content

        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to download file: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}")

    def download_file_from_url(self, url: str) -> IO:
        """HTTP URL에서 파일을 스트림으로 다운로드"""
        try:
            _LOGGER.debug(f"[HttpFileConnector] Downloading from URL: {url}")

            # HTTP 요청으로 파일 다운로드
            response = requests.get(
                url, stream=True, timeout=HTTP_FILE_CONFIG["download_timeout"]
            )
            response.raise_for_status()

            # Content-Length 헤더로 파일 크기 확인
            content_length = response.headers.get("content-length")
            if (
                content_length
                and int(content_length) > HTTP_FILE_CONFIG["max_file_size"]
            ):
                raise ERROR_INVALID_ARGUMENT(
                    key=f"File size {content_length} exceeds maximum allowed size {HTTP_FILE_CONFIG['max_file_size']}"
                )

            # 메모리로 다운로드
            file_content = BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file_content.write(chunk)

            file_content.seek(0)

            _LOGGER.debug(
                f"[HttpFileConnector] Downloaded file from URL: {url} ({len(file_content.getvalue())} bytes)"
            )
            return file_content

        except requests.RequestException as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to download from URL: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url)
        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to download from URL: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url)

    def test_connection(self, url: str) -> None:
        """HTTP URL 연결 테스트 (HEAD 요청으로 빠른 검증)"""
        try:
            _LOGGER.debug(f"[HttpFileConnector] Testing connection to URL: {url}")

            # HEAD 요청으로 연결 테스트 (데이터 다운로드 없이)
            response = requests.head(
                url, timeout=HTTP_FILE_CONFIG.get("connection_timeout", 10)
            )
            response.raise_for_status()

            _LOGGER.debug(f"[HttpFileConnector] Connection test successful: {url}")

        except requests.RequestException as e:
            _LOGGER.error(f"[HttpFileConnector] Connection test failed: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=url)

    def get_file_info(self, bucket_name: str, file_path: str) -> Dict:
        """파일 메타데이터 조회"""
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
            _LOGGER.error(f"[HttpFileConnector] Failed to get file info: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(file_path=f"{bucket_name}/{file_path}")

    def _is_supported_file(self, file_name: str) -> bool:
        """지원되는 파일 형식인지 확인"""
        format_type = self._detect_file_format(file_name)
        return format_type in HTTP_FILE_CONFIG["supported_formats"]

    def _detect_file_format(self, file_name: str) -> Optional[str]:
        """파일명으로 파일 형식 감지"""
        # 압축 확장자 제거 후 파일 형식 감지
        name_lower = file_name.lower()
        for compression in HTTP_FILE_CONFIG["supported_compressions"]:
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
        for compression in HTTP_FILE_CONFIG["supported_compressions"]:
            if name_lower.endswith(f".{compression}"):
                return compression
        return None

    @staticmethod
    def _check_secret_data(secret_data):
        """Secret 데이터 유효성 검증"""
        _LOGGER.debug(
            f"[HttpFileConnector] Validating secret data keys. Required keys: {REQUIRED_SECRET_KEYS}"
        )
        
        provided_keys = list(secret_data.keys()) if secret_data else []
        _LOGGER.debug(
            f"[HttpFileConnector] Provided secret data keys: {provided_keys}"
        )
        
        missing_keys = [key for key in REQUIRED_SECRET_KEYS if key not in secret_data]
        if missing_keys:
            _LOGGER.error(
                f"[HttpFileConnector] Secret data validation failed - Missing required keys: {missing_keys}"
            )
            for key in missing_keys:
                raise ERROR_REQUIRED_PARAMETER(key=f"secret_data.{key}")
        
        _LOGGER.debug("[HttpFileConnector] All required secret data keys are present")
