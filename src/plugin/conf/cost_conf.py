DEFAULT_BILLING_DATASET = "spaceone_billing_data"
BIGQUERY_TABLE_PREFIX = "gcp_billing_export_v1"
DETAILED_USAGE_TABLE_PREFIX = "gcp_billing_export_resource_v1"
SECRET_TYPE_DEFAULT = "MANUAL"

GRANULARITY = {"DAILY": "DAILY", "MONTHLY": "MONTHLY"}

COST_METRIC = ["net_cost", "credits", "currency", "AmortizedCost"]

# Data Source Types Configuration
DATA_SOURCE_TYPES = {"bigquery": "bigquery", "gcs": "gcs", "http": "http"}

GCS_CONFIG = {
    "supported_formats": ["csv", "json", "parquet"],
    "supported_compressions": [
        "gz",
        "gzip",
        "snappy",
        "zstd",
    ],  # zst, sz 제거 (Parquet 파일과 혼동 방지)
    "default_chunk_size": 500,  # gRPC 메시지 크기 제한을 고려하여 더욱 감소
    "max_chunk_size": 1000,  # 최대 청크 크기 제한 - 안전성 확보
    "max_file_size": 1024 * 1024 * 1024,  # 1GB
    "download_timeout": 300,  # 5분
    "max_files_per_batch": 10,  # 배치당 최대 파일 수
    "grpc_message_size_limit": 3 * 1024 * 1024,  # 3MB (안전 마진 확보)
    "connection_timeout": 10,  # 연결 타임아웃
}

# Default data source type for backward compatibility
DEFAULT_DATA_SOURCE_TYPE = "bigquery"

# BigQuery Configuration (pyproject.toml 명시 버전: pandas-gbq>=0.29.0)
BIGQUERY_CONFIG = {
    # "query_timeout": 300,  # pandas-gbq>=0.29.0에서 지원되지 않음
    "max_results": None,  # 결과 수 제한 없음 (지원됨)
    "progress_bar_type": None,  # 프로그레스바 비활성화 (기본값: 'tqdm', None으로 비활성화)
    "connection_timeout": 60,  # 연결 타임아웃 (1분) - 향후 사용
    "retry_attempts": 3,  # 재시도 횟수 - 향후 사용
    "retry_delay": 5,  # 재시도 간격 (초) - 향후 사용
}
