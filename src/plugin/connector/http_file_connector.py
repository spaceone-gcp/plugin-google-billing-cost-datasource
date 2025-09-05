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

    def create_session(self, options: dict, secret_data: dict, schema: str):
        """GCS 클라이언트 세션 생성 (캐시된 세션 재사용 지원)"""
        if not secret_data:
            raise ERROR_REQUIRED_PARAMETER(key="secret_data")

        self._check_secret_data(secret_data)
        self.project_id = secret_data["project_id"]
        bucket_name = options.get("bucket_name", "")

        # 캐시된 세션 확인
        cached_session = concurrency_manager.get_cached_session(
            self.project_id, bucket_name
        )
        if cached_session:
            self.credentials = cached_session["credentials"]
            self.gcs_client = cached_session["gcs_client"]
            _LOGGER.debug(
                f"[HttpFileConnector] Reusing cached GCS session for project: {self.project_id}"
            )
            return

        # 새 세션 생성
        # private_key의 \n 문자열을 실제 개행 문자로 변환
        processed_secret_data = secret_data.copy()
        if "private_key" in processed_secret_data:
            processed_secret_data["private_key"] = processed_secret_data[
                "private_key"
            ].replace("\\n", "\n")

        # Service Account 인증 정보로 GCS 클라이언트 생성
        self.credentials = service_account.Credentials.from_service_account_info(
            processed_secret_data
        )
        self.gcs_client = storage.Client(
            credentials=self.credentials, project=self.project_id
        )

        # 세션 캐싱
        session_data = {"credentials": self.credentials, "gcs_client": self.gcs_client}
        concurrency_manager.cache_session(self.project_id, bucket_name, session_data)

        _LOGGER.debug(
            f"[HttpFileConnector] New GCS session created and cached for project: {self.project_id}"
        )

    def list_files(self, bucket_name: str, pattern: str = None) -> List[Dict]:
        """버킷에서 파일 목록 조회"""
        try:
            bucket = self.gcs_client.bucket(bucket_name)
            blobs = (
                bucket.list_blobs(prefix=pattern) if pattern else bucket.list_blobs()
            )

            files = []
            for blob in blobs:
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

            _LOGGER.debug(
                f"[HttpFileConnector] Found {len(files)} supported files in bucket: {bucket_name}"
            )
            return files

        except Exception as e:
            _LOGGER.error(f"[HttpFileConnector] Failed to list files: {e}")
            raise ERROR_FILE_DOWNLOAD_FAILED(
                file_path=f"{bucket_name}/{pattern or '*'}"
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

            _LOGGER.debug(
                f"[HttpFileConnector] Downloaded file: {bucket_name}/{file_path} ({blob.size} bytes)"
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
        missing_keys = [key for key in REQUIRED_SECRET_KEYS if key not in secret_data]
        if missing_keys:
            for key in missing_keys:
                raise ERROR_REQUIRED_PARAMETER(key=f"secret_data.{key}")
