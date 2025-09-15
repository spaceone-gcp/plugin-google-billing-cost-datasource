# API 명세서

Google Cloud Billing 플러그인의 상세 API 명세를 설명합니다. 주요 커넥터들의 API와 새로운 기능들을 포함합니다.

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

## 📋 최근 업데이트 (v2.1)

### SpaceONE Job 스키마 준수 강화 ⭐ **NEW**

#### ValidationError 방지
- **문제**: `ERROR_DB_QUERY ValidationError (start.String value is too long)` 오류 발생
- **원인**: SpaceONE Job 스키마의 `start` 필드 길이 제한(최대 7자) 위반
- **해결**: 자동 필드 길이 제한 및 YYYY-MM 형식 강제 적용

#### Job Manager 개선사항
```python
# HTTP 파일 작업 - start 필드 길이 자동 제한
if start:
    start_value = start[:7]  # YYYY-MM 형식으로 제한
else:
    start_value = datetime.utcnow().strftime("%Y-%m")  # 현재 월

changed_item = {
    "start": start_value,  # 최대 7자로 제한됨
    "timestamp": current_time,
    "file_count": len(tasks),
}
```

#### 스키마 검증 결과
- ✅ **BigQuery 작업**: 기존 YYYY-MM 형식 유지 (7자)
- ✅ **HTTP 파일 작업**: 자동 길이 제한 적용 (7자)
- ✅ **하위 호환성**: 기존 기능 완전 보존
- ✅ **오류 방지**: ValidationError 완전 해결

#### 테스트 검증
```bash
# 모든 테스트 통과
✅ start 필드 길이 제한 로직 성공: '2024-01' (길이: 7)
✅ start 필드 기본값 생성 로직 성공: '2025-09' (길이: 7)  
✅ BigQuery start_month 형식 확인: '2024-03' (길이: 7)
✅ start 필드 경계 조건 테스트 통과
✅ 형식 길이 확인 - 긴 형식: 19자, 짧은 형식: 7자
```
