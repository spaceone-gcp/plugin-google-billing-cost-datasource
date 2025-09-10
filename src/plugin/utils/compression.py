import gzip
import logging
from io import BytesIO
from typing import IO, Optional

from ..conf.cost_conf import HTTP_FILE_CONFIG
from ..error.cost import ERROR_UNSUPPORTED_FILE_FORMAT

_LOGGER = logging.getLogger("spaceone")


class CompressionHandler:
    """파일 압축 처리 유틸리티"""

    @staticmethod
    def detect_compression(
        file_name: str, content_sample: bytes = None
    ) -> Optional[str]:
        """파일명과 내용으로 압축 형식 감지

        Args:
            file_name: 파일명
            content_sample: 파일 내용 샘플 (선택적)

        Returns:
            압축 형식 ('gz', 'snappy', 'zstd') 또는 None
        """
        name_lower = file_name.lower()

        # 내용 기반 검증이 있는 경우 우선 확인 (파일 내용이 최우선)
        if content_sample and len(content_sample) >= 4:
            # Parquet 파일 매직 넘버 확인 (PAR1) - 최우선 처리
            if content_sample[:4] == b"PAR1":
                return None

            # GZIP 매직 넘버 확인 (0x1f, 0x8b)
            if content_sample[:2] == b"\x1f\x8b":
                return "gz"

            # ZSTD 매직 넘버 확인 (0x28, 0xb5, 0x2f, 0xfd)
            if content_sample[:4] == b"\x28\xb5\x2f\xfd":
                return "zstd"

            # Snappy 매직 넘버 확인 (다양한 형태 존재)
            # Snappy framed format: 0xff, 0x06, 0x00, 0x00, 0x73, 0x4e, 0x61, 0x50, 0x70, 0x59
            if (
                len(content_sample) >= 10
                and content_sample[:4] == b"\xff\x06\x00\x00"
                and content_sample[4:10] == b"sNaPpY"
            ):
                return "snappy"

        # Parquet 파일에 대한 특별 처리 - 파일명 기반 압축 감지
        parquet_compression_mappings = {
            ".parquet.gz": "gz",
            ".parquet.gzip": "gz",
            ".parquet.snappy": "snappy",
            ".parquet.zst": "zstd",
            ".parquet.zstd": "zstd",
            ".parquet.sz": "snappy",  # sz는 snappy의 다른 확장자
        }

        for extension, compression_type in parquet_compression_mappings.items():
            if name_lower.endswith(extension):
                # 내용 기반 검증이 있는 경우, 실제 압축 여부 확인
                if content_sample and len(content_sample) >= 4:
                    if content_sample[:4] == b"PAR1":
                        return None
                    else:
                        return compression_type
                else:
                    # 내용 샘플이 없는 경우 파일명만으로 판단
                    return compression_type

        # 일반적인 압축 형식 감지
        compression_mappings = {
            ".gz": "gz",
            ".gzip": "gz",
            ".snappy": "snappy",
            ".zst": "zstd",
            ".zstd": "zstd",
            ".sz": "snappy",  # sz는 snappy의 다른 확장자
        }

        for extension, compression_type in compression_mappings.items():
            if name_lower.endswith(extension):
                return compression_type

        return None

    @staticmethod
    def decompress_stream(stream: IO, compression_type: str) -> IO:
        """압축 스트림 해제

        Args:
            stream: 압축된 파일 스트림
            compression_type: 압축 형식

        Returns:
            압축 해제된 스트림

        Raises:
            ERROR_UNSUPPORTED_FILE_FORMAT: 지원하지 않는 압축 형식
        """

        if compression_type not in HTTP_FILE_CONFIG["supported_compressions"]:
            raise ERROR_UNSUPPORTED_FILE_FORMAT(format=compression_type)

        try:
            if compression_type == "gz":
                return CompressionHandler._decompress_gzip(stream)
            elif compression_type == "snappy":
                return CompressionHandler._decompress_snappy(stream)
            elif compression_type == "zstd":
                return CompressionHandler._decompress_zstd(stream)
            else:
                raise ERROR_UNSUPPORTED_FILE_FORMAT(format=compression_type)

        except Exception as e:
            _LOGGER.error(
                f"[CompressionHandler] Failed to decompress {compression_type}: {e}"
            )
            raise

    @staticmethod
    def _decompress_gzip(stream: IO) -> IO:
        """GZIP 압축 해제"""
        try:
            # 스트림 위치를 처음으로 이동
            stream.seek(0)

            # 파일 시그니처 확인 (처음 4바이트)
            header = stream.read(4)
            stream.seek(0)

            # Parquet 파일 매직 넘버 확인 (PAR1) - 최우선 처리
            if len(header) >= 4 and header[:4] == b"PAR1":
                # Parquet 파일인 경우 압축 해제 없이 원본 스트림 반환
                stream.seek(0)
                return stream

            # GZIP 매직 넘버 확인 (0x1f, 0x8b)
            if len(header) >= 2 and header[0] == 0x1F and header[1] == 0x8B:
                # 실제 GZIP 파일인 경우 압축 해제
                stream.seek(0)
                compressed_data = stream.read()
                decompressed_data = gzip.decompress(compressed_data)
                decompressed_stream = BytesIO(decompressed_data)

                return decompressed_stream
            else:
                # GZIP이 아닌 경우 원본 스트림 반환
                stream.seek(0)
                return stream

        except gzip.BadGzipFile as e:
            try:
                stream.seek(0)
                return stream
            except Exception:
                raise e
        except Exception as e:
            _LOGGER.error(f"[CompressionHandler] GZIP decompression failed: {e}")
            # 압축 해제 실패 시 원본 스트림 반환 시도
            try:
                stream.seek(0)
                return stream
            except Exception:
                raise e

    @staticmethod
    def _decompress_snappy(stream: IO) -> IO:
        """Snappy 압축 해제"""
        try:
            # 스트림 위치를 처음으로 이동
            stream.seek(0)

            # 파일 시그니처 확인 (처음 10바이트로 확장)
            header = stream.read(10)
            stream.seek(0)

            # Parquet 파일 매직 넘버 확인 (PAR1)
            if len(header) >= 4 and header[:4] == b"PAR1":
                # Parquet 파일인 경우 압축 해제 없이 원본 스트림 반환
                stream.seek(0)
                return stream

            # snappy 라이브러리 동적 임포트
            try:
                import snappy
            except ImportError:
                stream.seek(0)
                return stream

            compressed_data = stream.read()

            # Snappy framed format 확인
            if (
                len(header) >= 10
                and header[:4] == b"\xff\x06\x00\x00"
                and header[4:10] == b"sNaPpY"
            ):
                pass

            # Snappy 압축 해제 시도
            try:
                decompressed_data = snappy.decompress(compressed_data)
                decompressed_stream = BytesIO(decompressed_data)

                return decompressed_stream

            except snappy.UncompressError:
                # Snappy 압축이 아닌 경우 원본 스트림 반환
                stream.seek(0)
                return stream

        except Exception as e:
            _LOGGER.error(f"[CompressionHandler] Snappy decompression failed: {e}")
            # 압축 해제 실패 시 원본 스트림 반환 시도
            try:
                stream.seek(0)
                return stream
            except Exception:
                raise e

    @staticmethod
    def _decompress_zstd(stream: IO) -> IO:
        """Zstandard 압축 해제"""
        try:
            # 스트림 위치를 처음으로 이동
            stream.seek(0)

            # 파일 시그니처 확인 (처음 4바이트)
            header = stream.read(4)
            stream.seek(0)

            # Parquet 파일 매직 넘버 확인 (PAR1)
            if len(header) >= 4 and header[:4] == b"PAR1":
                # Parquet 파일인 경우 압축 해제 없이 원본 스트림 반환
                stream.seek(0)
                return stream

            # ZSTD 매직 넘버 확인 (0x28, 0xb5, 0x2f, 0xfd)
            if len(header) >= 4 and header[:4] == b"\x28\xb5\x2f\xfd":
                pass

            # zstandard 라이브러리 동적 임포트
            try:
                import zstandard as zstd
            except ImportError:
                stream.seek(0)
                return stream

            compressed_data = stream.read()

            # ZSTD 압축 해제 시도
            try:
                dctx = zstd.ZstdDecompressor()
                decompressed_data = dctx.decompress(compressed_data)
                decompressed_stream = BytesIO(decompressed_data)

                return decompressed_stream

            except zstd.ZstdError:
                # ZSTD 압축이 아닌 경우 원본 스트림 반환
                stream.seek(0)
                return stream

        except Exception as e:
            _LOGGER.error(f"[CompressionHandler] ZSTD decompression failed: {e}")
            # 압축 해제 실패 시 원본 스트림 반환 시도
            try:
                stream.seek(0)
                return stream
            except Exception:
                raise e

    @staticmethod
    def is_compressed_file(file_name: str, content_sample: bytes = None) -> bool:
        """파일이 압축되어 있는지 확인"""
        return (
            CompressionHandler.detect_compression(file_name, content_sample) is not None
        )

    @staticmethod
    def get_decompressed_filename(file_name: str) -> str:
        """압축 확장자를 제거한 파일명 반환"""
        name_lower = file_name.lower()

        # Parquet 압축 형식들 처리
        parquet_extensions = [
            ".parquet.gz",
            ".parquet.gzip",
            ".parquet.snappy",
            ".parquet.sz",
            ".parquet.zst",
            ".parquet.zstd",
        ]

        for ext in parquet_extensions:
            if name_lower.endswith(ext):
                # .parquet.xxx -> .parquet
                return file_name[: len(file_name) - len(ext) + len(".parquet")]

        # 일반적인 압축 확장자들 처리
        compression_type = CompressionHandler.detect_compression(file_name)
        if compression_type:
            compression_extensions = {
                "gz": [".gz", ".gzip"],
                "snappy": [".snappy", ".sz"],
                "zstd": [".zst", ".zstd"],
            }

            for ext in compression_extensions.get(compression_type, []):
                if name_lower.endswith(ext):
                    return file_name[: -len(ext)]

        return file_name

    @staticmethod
    def estimate_decompression_ratio(compression_type: str) -> float:
        """압축 형식별 예상 압축 해제 비율 반환"""
        ratios = {
            "gz": 3.0,  # GZIP은 보통 3:1 압축률
            "snappy": 2.0,  # Snappy는 보통 2:1 압축률 (속도 중심)
            "zstd": 3.5,  # ZSTD는 보통 3.5:1 압축률 (균형)
        }
        return ratios.get(compression_type, 1.0)
