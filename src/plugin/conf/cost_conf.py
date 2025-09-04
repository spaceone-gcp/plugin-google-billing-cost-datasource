DEFAULT_BILLING_DATASET = "spaceone_billing_data"
BIGQUERY_TABLE_PREFIX = "gcp_billing_export_v1"
SECRET_TYPE_DEFAULT = "MANUAL"

GRANULARITY = {"DAILY": "DAILY", "MONTHLY": "MONTHLY"}

COST_METRIC = ["net_cost", "credits", "currency"]

# HTTP File Processing Configuration
DATA_SOURCE_TYPES = {"bigquery": "bigquery", "http_file": "http_file"}

HTTP_FILE_CONFIG = {
    "supported_formats": ["csv", "json", "parquet"],
    "supported_compressions": [
        "gz",
        "gzip",
        "snappy",
        "zstd",
    ],  # zst, sz 제거 (Parquet 파일과 혼동 방지)
    "default_chunk_size": 1000,  # gRPC 메시지 크기 제한을 고려하여 감소
    "max_chunk_size": 2000,  # 최대 청크 크기 제한
    "max_file_size": 1024 * 1024 * 1024,  # 1GB
    "download_timeout": 300,  # 5분
    "max_files_per_batch": 10,  # 배치당 최대 파일 수
    "grpc_message_size_limit": 4 * 1024 * 1024,  # 4MB (gRPC 기본 제한)
}

# Default data source type for backward compatibility
DEFAULT_DATA_SOURCE_TYPE = "bigquery"
