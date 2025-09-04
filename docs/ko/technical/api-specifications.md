# API 명세서

HTTP 파일 통합 기능의 상세 API 명세를 설명합니다.

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

#### 연결 관련 에러
- `ConnectionError`: GCS 연결 실패
- `AuthenticationError`: 인증 실패
- `PermissionError`: 권한 부족

#### 파일 처리 에러
- `FileNotFoundError`: 파일 없음
- `ParseError`: 파일 파싱 실패
- `CompressionError`: 압축 해제 실패

#### 데이터 변환 에러
- `MappingError`: 필드 매핑 실패
- `ValidationError`: 데이터 검증 실패
- `ConversionError`: 타입 변환 실패

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
