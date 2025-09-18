# API 명세서

Google Cloud Billing 플러그인의 상세 API 명세를 설명합니다. v2.0 업데이트로 통합된 source 파라미터, Credits Detail 기능, 그리고 향상된 성능 최적화를 포함합니다.

## 🚨 SpaceONE JSON 응답 형식 제약사항

### 과학적 표기법 사용 금지 **[CRITICAL]**

모든 API 응답에서 **과학적 표기법은 절대 사용할 수 없습니다**. SpaceONE 플랫폼은 JSON 응답에서 과학적 표기법을 지원하지 않습니다.

#### ❌ 금지된 표기법
```json
{
  "cost": 1.23e-6,        // 과학적 표기법 금지
  "usage_quantity": 4.56E+3,  // 대문자 E도 금지
  "listed_price": 7.89e-12    // 매우 작은 값도 금지
}
```

#### ✅ 허용된 표기법
```json
{
  "cost": 0.00000123,         // 🚨 CRITICAL: 최상위 필드, 절대 누락 금지
  "usage_quantity": 4560.0,   // 정수도 소수점 포함 권장
  "data": {
    "cost": 0.00000123,       // data 필드 내의 cost (별도)
    "listed_price": 0.0       // 매우 작은 값은 0.0으로 처리
  }
}
```

#### SpaceONE 빌링 응답 필수 구조 요구사항

**🚨 CRITICAL: 최상위 `cost` 필드는 SpaceONE 빌링 응답의 필수 항목입니다.**

모든 빌링 응답에서 다음 구조를 **반드시** 준수해야 합니다:

```json
{
  "results": [
    {
      "cost": 123.45,                    // 🚨 CRITICAL: 최상위 필수 필드, 절대 누락 금지
      "usage_quantity": 1000.0,          // 필수: 사용량
      "provider": "google_cloud",        // 필수: 프로바이더
      "region_code": "us-central1",      // 필수: 리전 코드
      "product": "BigQuery",             // 필수: 제품명
      "usage_type": "Active Storage",    // 필수: 사용 유형
      "resource": "project-123",         // 필수: 리소스 식별자
      "currency": "KRW",                 // 🆕 필수: 통화 (최상위 필드)
      "billed_date": "2025-09-10",       // 필수: 청구 날짜 (YYYY-MM-DD)
      "tags": {},                        // 필수: 태그 (빈 객체 허용)
      "additional_info": {},             // 필수: 추가 정보 (빈 객체 허용)
      "data": {                          // 필수: SpaceONE 프레임워크 요구사항
        "cost": 123.45,                  // data 필드 내의 cost (별도)
        "listed_price": 123.45,
        "currency_conversion_rate": 1354.59
      }
    }
  ]
}
```

### 실제 BigQuery 응답 예시 (완전한 구조 - 확장됨)

다음은 실제 Google Cloud BigQuery에서 생성되는 완전한 SpaceONE 응답 예시입니다 (추가 필드 포함):

```json
{
  "results": [
    {
      "cost": 0.0,                       // 🚨 CRITICAL: 최상위 필수 필드
      "usage_unit": "hour",
      "usage_quantity": 0.0,
      "provider": "google_cloud",
      "region_code": "global",
      "product": "Compute Engine",
      "usage_type": "Licensing Fee for Google Cloud Dataproc (GPU cost)",
      "resource": "mkkang-project",
      "currency": "USD",
      "tags": {},
      "additional_info": {
        "Billing Account ID": "01FD8E-B4DDC1-EAB69F",
        "Cost After Credits": 0,
        "Cost At List": 0,
        "Cost Type": "regular",
        "Credits Detail": [],
        "Invoice Month": "202509",
        "Project ID": "mkkang-project",
        "Project Name": "mkkang-project",
        "Resource Tags": {}
      },
      "data": {
        "cost": "0.0",
        "listed_price": "0.0"
      },
      "billed_date": "2025-09-15"
    }
  ]
}
```

#### 구현 요구사항
- [ ] **최상위 `cost` 필드 절대 보장** (data.cost와 별개의 필수 필드)
- [ ] **필수 필드 누락 방지**: cost, usage_quantity, provider, region_code, product, usage_type, resource, billed_date, currency, tags, additional_info, data
- [ ] 모든 숫자 필드에 `decimal_json_encoder` 적용
- [ ] 응답 전 과학적 표기법 패턴 검증
- [ ] `1e-15` 미만 값은 `0.0`으로 처리
- [ ] JSON 직렬화 전 완전한 과학적 표기법 제거

## 통합 Source 파라미터 API (v2.0) ⭐ **NEW**

### Source 기반 데이터 조회
```python
def get_data(
    self,
    options: dict,
    secret_data: dict,
    task_options: dict,
    schema: str = None
) -> Generator[dict, None, None]:
    """
    통합된 source 파라미터를 기반으로 데이터를 조회합니다.
    
    Args:
        options: 데이터 소스 옵션
            - source: "bigquery" | "gcs" | "http" (필수)
        secret_data: 인증 정보 (source에 따라 선택적)
        task_options: 작업 옵션
        schema: 스키마 정보
        
    Yields:
        SpaceONE 형식의 빌링 데이터
        
    Raises:
        ERROR_REQUIRED_PARAMETER: source 파라미터 누락 또는 잘못된 값
    """
```

### Source 값 검증
```python
def _get_source_value(self, options: dict) -> str:
    """
    source 값을 추출하고 검증합니다.
    
    Args:
        options: 데이터 소스 옵션
        
    Returns:
        검증된 source 타입 ("bigquery", "gcs", "http")
        
    Raises:
        ERROR_REQUIRED_PARAMETER: source 값이 없거나 지원하지 않는 값
    """
```

## Credits Detail API (v2.0) ⭐ **NEW**

### Credits Detail 모드
```python
def _get_data_from_bigquery(
    self,
    options: dict,
    secret_data: dict,
    task_options: dict,
    schema: str = None
) -> Generator[dict, None, None]:
    """
    BigQuery에서 Credits Detail 정보를 포함한 데이터 조회
    
    Args:
        task_options:
            - credits_detail_mode: bool (선택사항, 기본값: False)
            - credits_detail_limit: int (선택사항, 기본값: 1000)
            
    Features:
        - 기본 모드: GROUP BY 집계로 최적화된 성능
        - Credits Detail 모드: 원본 데이터로 완전한 크레딧 정보
        - 스마트 청킹: gRPC 메시지 크기 제한 대응
    """
```

### Credits 처리
```python
def _process_credits_detail(self, row) -> list:
    """
    Credits 배열 데이터 처리 (BigQuery 스키마 준수)
    
    Args:
        row: 데이터 행
        
    Returns:
        처리된 크레딧 상세 리스트
        [
            {
                "name": str,
                "amount": float,
                "full_name": str,
                "id": str,
                "type": str  # DISCOUNT, FREE_TIER, etc.
            }
        ]
    """
```

## BigQuery Connector API

### 세션 생성 (향상된 인증 처리)
```python
def create_session(
    self,
    options: dict,
    secret_data: dict,
    schema: str
) -> None:
    """
    BigQuery 클라이언트 세션을 생성합니다.
    
    Args:
        options: 설정 옵션
        secret_data: 서비스 계정 인증 정보 (선택사항)
        schema: 스키마 정보
        
    Features:
        - 향상된 private_key 검증 및 자동 정리
        - 상세한 인증 오류 진단 메시지
        
    Raises:
        ValueError: private_key 형식 오류
        AuthenticationError: 서비스 계정 인증 실패
    """
```

### private_key 검증 및 정리
```python
@staticmethod
def _validate_and_clean_private_key(private_key: str) -> str:
    """
    private_key를 검증하고 올바른 PEM 형식으로 정리합니다.
    
    Args:
        private_key: 원본 private_key 문자열
        
    Returns:
        정리된 PEM 형식의 private_key
        
    Features:
        - 이스케이프된 개행 문자 처리
        - PEM 헤더/푸터 검증
        - Base64 내용 검증 및 패딩 수정
        - 64자 단위 줄바꿈으로 정리
        
    Raises:
        ValueError: 잘못된 PEM 형식
    """
```

## Pricing Connector API (신규)

### 세션 생성
```python
def create_session(
    self,
    options: dict,
    secret_data: dict,
    schema: str
) -> None:
    """
    Pricing 데이터 조회용 BigQuery 세션을 생성합니다.
    
    Args:
        options: 설정 옵션
            - pricing_export_project_id: Pricing Export 프로젝트 ID
            - pricing_dataset_id: Pricing 데이터셋 ID (기본값: pricing_export)
        secret_data: 서비스 계정 인증 정보
        schema: 스키마 정보
    """
```

### 가격 정보 조회
```python
def get_pricing_data(
    self,
    service_id: Optional[str] = None,
    sku_id: Optional[str] = None,
    date: Optional[str] = None,
) -> Generator[Dict, None, None]:
    """
    cloud_pricing_export 테이블에서 가격 정보를 조회합니다.
    
    Args:
        service_id: 특정 서비스 ID로 필터링 (선택사항)
        sku_id: 특정 SKU ID로 필터링 (선택사항)
        date: 특정 날짜의 가격 정보 (YYYY-MM-DD 형식, 선택사항)
        
    Yields:
        가격 정보 딕셔너리
        - service_id, service_description
        - sku_id, sku_description
        - region, tiered_rates
        - base_price_usd
        
    Raises:
        ERROR_INVALID_ARGUMENT: 쿼리 실행 실패
    """
```

### 서비스별 가격 요약
```python
def get_service_pricing_summary(
    self,
    date: Optional[str] = None
) -> Dict[str, List[Dict]]:
    """
    서비스별 가격 정보 요약을 조회합니다.
    
    Args:
        date: 특정 날짜의 가격 정보 (YYYY-MM-DD 형식, 선택사항)
        
    Returns:
        서비스별 가격 정보 요약 딕셔너리
        {
            "서비스명": [
                {
                    "sku_id": "...",
                    "sku_description": "...",
                    "pricing_unit": "...",
                    "base_price_usd": 0.0,
                    "region": "..."
                }
            ]
        }
        
    Raises:
        ERROR_INVALID_ARGUMENT: 쿼리 실행 실패
    """
```

### 청구 데이터와 정가 비교
```python
def compare_billing_vs_pricing(
    self,
    billing_data: Dict,
    pricing_date: Optional[str] = None
) -> Dict:
    """
    실제 청구 데이터와 정가를 비교 분석합니다.
    
    Args:
        billing_data: 실제 청구 데이터
            - service_id, sku_id
            - cost, usage_amount
        pricing_date: 비교할 가격 정보 날짜
        
    Returns:
        비교 분석 결과
        {
            "comparison_available": bool,
            "actual_cost": float,
            "list_price_total": float,
            "discount_amount": float,
            "discount_rate_percent": float,
            "usage_amount": float,
            "list_price_per_unit": float,
            "reason": str  # 비교 불가능한 경우
        }
    """
```

## Concurrency Management API

### 동시성 관리자
```python
class ConcurrencyManager:
    """파일 처리 동시성 제어 및 세션 캐싱"""
    
    def acquire_file_lock(
        self, 
        bucket_name: str, 
        file_path: str, 
        timeout: float = 30.0
    ) -> ContextManager:
        """
        파일 처리를 위한 락 획득 (컨텍스트 매니저)
        
        Args:
            bucket_name: GCS 버킷 이름
            file_path: 파일 경로
            timeout: 락 획득 타임아웃 (초)
            
        Returns:
            컨텍스트 매니저 객체
            
        Raises:
            TimeoutError: 타임아웃 내 락 획득 실패
        """
    
    def cache_session(
        self, 
        project_id: str, 
        bucket_name: str, 
        session_data: Dict
    ) -> None:
        """
        GCS 세션 캐싱
        
        Args:
            project_id: Google Cloud 프로젝트 ID
            bucket_name: GCS 버킷 이름
            session_data: 캐시할 세션 데이터
        """
    
    def get_cached_session(
        self, 
        project_id: str, 
        bucket_name: str, 
        max_age: float = 300.0
    ) -> Optional[Dict]:
        """
        캐시된 GCS 세션 조회
        
        Args:
            project_id: Google Cloud 프로젝트 ID
            bucket_name: GCS 버킷 이름
            max_age: 최대 캐시 유지 시간 (초, 기본 5분)
            
        Returns:
            캐시된 세션 데이터 또는 None
        """
```

### 중복 요청 방지
```python
class RequestDeduplicator:
    """중복 요청 감지 및 방지"""
    
    def generate_request_hash(
        self, 
        options: Dict, 
        task_options: Dict
    ) -> str:
        """
        요청의 고유 해시 생성
        
        Args:
            options: 데이터소스 옵션
            task_options: 작업 옵션
            
        Returns:
            MD5 해시 문자열
        """
    
    def is_duplicate_request(self, request_hash: str) -> bool:
        """
        중복 요청 확인
        
        Args:
            request_hash: 요청 해시
            
        Returns:
            중복 요청 여부
        """
```

## HTTP File Connector API

### 파일 목록 조회
```python
def list_files(
    self,
    bucket_name: str,
    file_pattern: Optional[str] = None,
    max_files: int = 100
) -> List[FileMetadata]:
    """
    GCS 버킷에서 조건에 맞는 파일 목록을 조회합니다.
    
    Args:
        bucket_name: GCS 버킷 이름
        file_pattern: 파일 패턴 (glob 형식)
        max_files: 최대 파일 수
        
    Returns:
        파일 메타데이터 목록
        
    Raises:
        ConnectionError: GCS 연결 실패
        AuthenticationError: 인증 실패
        ValueError: 잘못된 매개변수
    """
```

### 파일 다운로드 및 파싱
```python
def download_and_parse(
    self,
    file_metadata: FileMetadata,
    field_mapper: FieldMapper
) -> Generator[Dict, None, None]:
    """
    파일을 다운로드하고 파싱하여 데이터를 반환합니다.
    
    Args:
        file_metadata: 파일 메타데이터
        field_mapper: 필드 매핑 객체
        
    Yields:
        매핑된 데이터 레코드
        
    Raises:
        DownloadError: 파일 다운로드 실패
        ParseError: 파일 파싱 실패
        MappingError: 필드 매핑 실패
    """
```

## Field Mapper API

### 매핑 규칙 설정
```python
def configure_mapping(
    self,
    mapping_config: Dict[str, Union[str, Dict]],
    provider: str = None
) -> None:
    """
    필드 매핑 규칙을 설정합니다.
    
    Args:
        mapping_config: 매핑 설정
        provider: 프로바이더별 자동 매핑 적용
    """
```

### 데이터 변환
```python
def transform_record(
    self,
    source_record: Dict,
    apply_defaults: bool = True
) -> Dict:
    """
    단일 레코드를 SpaceONE 형식으로 변환합니다.
    
    Args:
        source_record: 원본 데이터 레코드
        apply_defaults: 기본값 적용 여부
        
    Returns:
        변환된 데이터 레코드
        
    Raises:
        ValidationError: 필수 필드 누락
        ConversionError: 데이터 타입 변환 실패
    """
```

## 파일 파서 API

### CSV 파서
```python
class CSVParser:
    """CSV 파일 파서"""
    
    def __init__(self, delimiter: str = ",", encoding: str = "utf-8"):
        self.delimiter = delimiter
        self.encoding = encoding
    
    def parse_stream(
        self,
        file_stream: IO,
        field_mapper: FieldMapper
    ) -> Generator[Dict, None, None]:
        """CSV 스트림을 파싱하여 매핑된 데이터 반환"""
```

### JSON 파서
```python
class JSONParser:
    """JSON 파일 파서"""
    
    def parse_stream(
        self,
        file_stream: IO,
        field_mapper: FieldMapper,
        json_path: Optional[str] = None
    ) -> Generator[Dict, None, None]:
        """
        JSON 스트림을 파싱하여 매핑된 데이터 반환
        
        Args:
            file_stream: 파일 스트림
            field_mapper: 필드 매퍼
            json_path: JSON 배열 경로 (예: "$.data[*]")
        """
```

### Parquet 파서
```python
class ParquetParser:
    """Parquet 파일 파서"""
    
    def parse_stream(
        self,
        file_stream: IO,
        field_mapper: FieldMapper,
        chunk_size: int = 10000
    ) -> Generator[Dict, None, None]:
        """Parquet 스트림을 청크 단위로 파싱하여 데이터 반환"""
```

## 압축 처리 API

### 압축 핸들러
```python
class CompressionHandler:
    """압축 파일 처리"""
    
    @staticmethod
    def detect_compression(file_name: str, content_type: str = None) -> Optional[str]:
        """파일명과 Content-Type으로 압축 형식 감지"""
    
    @staticmethod
    def decompress_stream(
        compressed_stream: IO,
        compression_type: str
    ) -> IO:
        """압축 스트림을 해제하여 일반 스트림 반환"""
```

## 에러 처리

### 에러 분류

#### 인증 관련 에러 (향상됨)
- `AuthenticationError`: 서비스 계정 인증 실패
  - `InvalidData`: private_key 손상 또는 잘못된 형식
  - `Could not deserialize key data`: private_key 데이터 무효
  - `invalid_grant`: 서비스 계정 존재하지 않음 또는 비활성화
- `PermissionError`: 권한 부족

#### 연결 관련 에러
- `ConnectionError`: GCS/BigQuery 연결 실패
- `TimeoutError`: 요청 시간 초과

#### 파일 처리 에러
- `FileNotFoundError`: 파일 없음
- `ParseError`: 파일 파싱 실패
- `CompressionError`: 압축 해제 실패

#### 데이터 변환 에러
- `MappingError`: 필드 매핑 실패
- `ValidationError`: 데이터 검증 실패
- `ConversionError`: 타입 변환 실패

#### Pricing 관련 에러 (신규)
- `ERROR_INVALID_ARGUMENT`: Pricing 쿼리 실행 실패
- `ERROR_REQUIRED_PARAMETER`: 필수 매개변수 누락

### 재시도 로직
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError))
)
def download_file_with_retry(self, file_url: str) -> IO:
    """재시도 로직이 적용된 파일 다운로드"""
```


## 성능 최적화

### 향상된 비용 필드 선택
```python
def _get_cost_field_by_option(self, row) -> float:
    """
    select_cost 및 cost_metric 옵션에 따라 적절한 비용 필드를 선택합니다.
    
    Args:
        row: BigQuery 또는 파일에서 읽은 데이터 행
        
    Returns:
        선택된 비용 값
        
    Options:
        - cost_metric="AmortizedCost": credits_amount 사용
        - select_cost="list_price": cost_at_list 사용
        - select_cost="after_credits": cost_after_credits 사용
        - select_cost="net_cost": cost 사용 (기본값)
    """
```

### 병렬 처리
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ParallelFileProcessor:
    """병렬 파일 처리기"""
    
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def process_files_parallel(
        self,
        file_list: List[FileMetadata]
    ) -> List[ProcessingResult]:
        """여러 파일을 병렬로 처리"""
```

### 모니터링 및 로깅
```python
import logging

# 파일 처리 시작
logger.info(
    "Starting file processing",
    extra={
        "file_name": file_metadata.file_name,
        "file_size": file_metadata.file_size,
        "file_format": file_metadata.file_format
    }
)

# 처리 완료
logger.info(
    "File processing completed",
    extra={
        "file_name": file_metadata.file_name,
        "records_processed": result.records_processed,
        "processing_time": result.processing_time
    }
)
```

## GCS Connector API (v2.0) ⭐ **NEW**

### GCS 버킷 데이터 조회
```python
def _get_data_from_gcs(
    self,
    options: dict,
    secret_data: dict,
    task_options: dict,
    schema: str = None
) -> Generator[dict, None, None]:
    """
    GCS 버킷에서 데이터 조회 - 동시성 제어 및 중복 요청 처리
    
    Args:
        options:
            - bucket_name: str (필수)
            - field_mapper: dict (선택사항)
        task_options:
            - project_id: str (선택사항)
            - start: str (날짜 범위 필터링)
            - file_path: str (특정 파일 지정)
            - max_files: int (최대 파일 수, 기본값: 10)
            
    Features:
        - 날짜 범위 기반 파일 필터링
        - 동시성 제어로 안전한 병렬 처리
        - 압축 파일 자동 해제
        - 스마트 포맷 감지
    """
```

### 파일 목록 조회
```python
def _get_gcs_file_list(
    self,
    bucket_name: str,
    project_id: str,
    start_period: str,
    task_options: dict
) -> list[dict]:
    """
    GCS 버킷에서 파일 목록 가져오기
    
    Args:
        bucket_name: GCS 버킷 이름
        project_id: 프로젝트 ID
        start_period: 시작 기간 (YYYY-MM 형식)
        task_options: 작업 옵션
            - file_path: 특정 파일 경로
            - file_pattern: 커스텀 패턴
            
    Returns:
        파일 메타데이터 리스트
    """
```

## HTTP File Connector API (v2.0) ⭐ **UPDATED**

### HTTP URL 데이터 조회
```python
def _get_data_from_http(
    self,
    options: dict,
    secret_data: dict,
    task_options: dict,
    schema: str = None
) -> Generator[dict, None, None]:
    """
    HTTP URL에서 데이터 조회 - 인증 불필요
    
    Args:
        options:
            - base_url: str (필수)
            - field_mapper: dict (선택사항)
        secret_data: 인증 정보 (공개 URL의 경우 불필요)
        task_options: 작업 옵션
            
    Features:
        - 공개 및 인증된 URL 지원
        - 자동 압축 해제
        - 메모리 효율적 스트리밍 처리
        - URL 유효성 검증 및 정리
    """
```

## 📋 최근 업데이트 (v2.0)

### 통합 Source 파라미터 ⭐ **NEW**
- **기능**: 단일 `source` 파라미터로 모든 데이터 소스 통합
- **값**: `"bigquery"`, `"gcs"`, `"http"`
- **장점**: 설정 단순화, 명확한 데이터 소스 식별

### Credits Detail 기능 ⭐ **NEW**
- **기능**: 개별 크레딧 정보의 완전한 세부사항 제공
- **모드**: `credits_detail_mode: true`로 활성화
- **성능**: Credits가 있는 레코드만 선택적 조회

### gRPC 최적화 ⭐ **NEW**
- **문제**: ResourceExhausted 오류 (4MB 제한)
- **해결**: 스마트 청킹 시스템 (배치 크기 자동 조정)
- **성능**: 대용량 데이터셋 안정적 전송

### Cost 필드 보장 시스템 ⭐ **NEW**
- **기능**: 100% cost 필드 커버리지
- **지원**: 과학적 표기법 (9.6e-05) 완벽 처리
- **안정성**: 5단계 보장 시스템으로 누락 방지

### 현대적 Python 지원 ⭐ **NEW**
- **설정**: pyproject.toml 기반 프로젝트 구성
- **요구사항**: Python 3.9+ 지원
- **도구**: Ruff, mypy 통합 개발 환경

### BigQuery SQL 최적화 ⭐ **NEW**
- **집계**: GROUP BY 최적화로 성능 향상
- **필드**: 모든 BigQuery 스키마 필드 완전 지원
- **중첩**: 중첩 구조 필드 정확한 처리

## 📅 날짜 범위 처리 (v2.0.1) ⭐ **UPDATED**

### 종료일 자동 설정 기능
종료일(`end`)이 제공되지 않은 경우, 시스템이 자동으로 현재월로 설정합니다.

#### 기본 동작
```python
# task_options에서 종료일 처리
{
    "start": "2024-09",     # 시작일 (필수)
    "end": None             # 종료일 미제공
}

# 자동으로 현재월로 설정됨
{
    "start": "2024-09",     # 시작일
    "end": "2025-09"        # 현재월로 자동 설정 (2025년 9월 기준)
}
```

#### 로깅 메시지
```
[SQL 생성] 종료일이 None이므로 현재월로 자동 설정: 2025-09
[PARTITIONDATE] 종료일이 None이므로 현재월로 설정: 2025-09
[SQL 생성] 검증된 시작일: 2024-09, 종료일: 2025-09
[SQL 생성] 날짜 범위 필터: 2024-09 ~ 2025-09
```

### 월 단위 데이터 조회 정확성
월 단위 입력 시 해당 월의 모든 데이터를 정확히 포함하도록 처리합니다.

#### SQL 쿼리 구문 (BigQuery 호환)
```sql
-- 시작일 조건
WHERE usage_start_time >= TIMESTAMP('2024-09-01')

-- 종료일 조건 (해당 월의 모든 데이터 포함)
AND usage_start_time < TIMESTAMP(DATE_ADD(DATE('2025-09-01'), INTERVAL 1 MONTH))

-- 파티션 필터 (성능 최적화)
AND _PARTITIONDATE BETWEEN '2024-08-01' AND '2025-10-31'
```

#### 날짜 범위 예시
| 입력 | 실제 조회 범위 | 설명 |
|------|---------------|------|
| `start: "2024-09"` | `2024-09-01 00:00:00` ~ `2025-09-30 23:59:59` | 종료일 자동 설정 |
| `start: "2024-09", end: "2024-10"` | `2024-09-01 00:00:00` ~ `2024-10-31 23:59:59` | 명시적 종료일 |
| `start: "2024-12", end: "2025-01"` | `2024-12-01 00:00:00` ~ `2025-01-31 23:59:59` | 연도 경계 처리 |

### PARTITIONDATE 범위 확장
BigQuery 성능 최적화를 위해 파티션 날짜 범위를 자동으로 확장합니다.

#### 확장 로직
- **시작일**: 입력 시작월 -1개월
- **종료일**: 입력 종료월 +1개월

#### 예시
```
원본 범위: 2024-09 ~ 2025-09
확장된 PARTITIONDATE 범위: 2024-08-01 ~ 2025-10-31
```

### 호환성 및 안정성 개선 (v2.0.1)

#### BigQuery SQL 호환성
- **문제**: `TIMESTAMP + INTERVAL 1 MONTH` 구문 오류
- **해결**: `TIMESTAMP(DATE_ADD(DATE(...), INTERVAL 1 MONTH))` 사용
- **효과**: BigQuery 표준 SQL 완전 호환

#### 자동 설정 투명성
- **INFO 레벨**: 종료일 자동 설정 시 명확한 로깅
- **DEBUG 레벨**: 날짜 검증 및 범위 계산 과정 로깅
- **효과**: 디버깅 및 모니터링 향상

### API 호환성
기존 API와 완전 호환되며, 추가 기능으로 사용자 편의성이 향상되었습니다.

#### 기존 사용법 (완전 호환)
```python
# 기존 방식 그대로 사용 가능
task_options = {
    "start": "2024-09",
    "project_id": "my-project"
}
```

#### 새로운 기능 활용
```python
# 종료일 명시적 지정
task_options = {
    "start": "2024-09",
    "end": "2024-12",      # 명시적 종료일
    "project_id": "my-project"
}
```
