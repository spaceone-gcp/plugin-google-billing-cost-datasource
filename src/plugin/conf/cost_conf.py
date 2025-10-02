# Google Cloud Billing 데이터를 저장할 기본 BigQuery 데이터셋 이름
DEFAULT_BILLING_DATASET = "spaceone_billing_data"

# BigQuery에서 GCP 빌링 데이터 테이블의 기본 접두사
BIGQUERY_TABLE_PREFIX = "gcp_billing_export_v1"

# 상세 사용량 데이터 테이블의 접두사 (리소스별 세부 정보 포함)
DETAILED_USAGE_TABLE_PREFIX = "gcp_billing_export_resource_v1"

# 기본 시크릿 타입 - 수동 인증 방식 사용
SECRET_TYPE_DEFAULT = "MANUAL"

# 비용 데이터 집계 단위 정의 (일별/월별)
GRANULARITY = {"DAILY": "DAILY", "MONTHLY": "MONTHLY"}

# 지원하는 비용 메트릭 타입들 (순비용, 크레딧, 통화, 상각비용)
COST_METRIC = ["net_cost", "credits", "currency", "AmortizedCost"]

# 데이터 소스 타입 설정 - 지원하는 데이터 소스들
DATA_SOURCE_TYPES = {"bigquery": "bigquery", "gcs": "gcs", "http": "http"}

# Google Cloud Storage 관련 설정
GCS_CONFIG = {
    # GCS에서 지원하는 파일 형식들
    "supported_formats": ["csv", "json", "parquet"],
    # 지원하는 압축 형식들
    "supported_compressions": [
        "gz",  # gzip 압축
        "gzip",  # gzip 압축 (확장자)
        "snappy",  # Snappy 압축 (Parquet와 함께 주로 사용)
        "zstd",  # Zstandard 압축
    ],
    # 기본 청크 크기 - gRPC 메시지 크기 제한을 고려하여 더욱 감소
    "default_chunk_size": 500,
    # 최대 청크 크기 제한 - 안전성 확보
    "max_chunk_size": 1000,
    # 최대 파일 크기 제한 (1GB)
    "max_file_size": 1024 * 1024 * 1024,
    # 파일 다운로드 타임아웃 (5분)
    "download_timeout": 300,
    # 배치당 최대 파일 수
    "max_files_per_batch": 10,
    # gRPC 메시지 크기 제한 (3MB, 안전 마진 확보)
    "grpc_message_size_limit": 3 * 1024 * 1024,
    # GCS 연결 타임아웃 (10초)
    "connection_timeout": 10,
}

# 하위 호환성을 위한 기본 데이터 소스 타입
DEFAULT_DATA_SOURCE_TYPE = "bigquery"

# BigQuery 설정 (pyproject.toml 명시 버전: pandas-gbq>=0.29.0)
BIGQUERY_CONFIG = {
    # 쿼리 결과 수 제한 없음 (None으로 설정하여 모든 결과 반환)
    "max_results": None,
    # 프로그레스바 비활성화 (기본값: 'tqdm', None으로 비활성화)
    "progress_bar_type": None,
    # BigQuery 연결 타임아웃 (1분) - 향후 사용 예정
    "connection_timeout": 60,
    # 쿼리 실패 시 재시도 횟수 - 향후 사용 예정
    "retry_attempts": 3,
    # 재시도 간격 (초) - 향후 사용 예정
    "retry_delay": 5,
}

# 성능 최적화 설정
PERFORMANCE_CONFIG = {
    # gRPC 응답 최적화를 위한 배치 크기 설정
    "grpc_response_batch_size": 100,  # gRPC 응답당 최대 레코드 수
    # 동적 배치 크기 조정을 위한 설정
    "min_batch_size": 10,  # 최소 배치 크기
    "max_batch_size": 200,  # 최대 배치 크기
    # 레코드당 평균 크기 추정 (바이트)
    "avg_record_size_bytes": 2048,  # 2KB per record (conservative estimate)
    # gRPC 메시지 크기 제한 (3MB에서 안전 마진 20% 확보)
    "grpc_message_size_limit": int(3 * 1024 * 1024 * 0.8),  # 2.4MB
    # 성능 모니터링을 위한 설정
    "enable_performance_logging": True,
    # 배치 크기 동적 조정 활성화
    "enable_dynamic_batch_sizing": True,
}
