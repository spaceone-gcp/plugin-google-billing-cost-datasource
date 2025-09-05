# 구현 로드맵

기존 BigQuery 기반 Google Cloud Billing 플러그인에 HTTP 파일 처리 기능을 추가하는 구현 로드맵입니다. 기존 기능을 최대한 보존하면서 새로운 기능을 안전하게 추가하는 것이 목표입니다.

## 현재 상태 분석

### 기존 아키텍처
```
Service Layer (main.py)
├── DataSourceManager (init/verify)
├── JobManager (get_tasks)  
└── CostManager (get_data/get_linked_accounts)
    └── BigqueryConnector
```

### 기존 기능
- BigQuery 기반 billing 데이터 조회
- 프로젝트별 작업 분할
- 고정된 스키마 기반 데이터 변환
- Service Account 인증

## 구현 단계별 계획

### Phase 1: 기반 구조 확장 (1-2주)

#### 1.1. 설정 구조 확장
```python
# src/plugin/conf/cost_conf.py 확장
DATA_SOURCE_TYPES = {
    'bigquery': 'bigquery',
    'http_file': 'http_file'
}

HTTP_FILE_CONFIG = {
    'supported_formats': ['csv', 'json', 'parquet'],
    'supported_compressions': ['gz', 'snappy', 'zstd'],
    'default_chunk_size': 10000,
    'max_file_size': 1024 * 1024 * 1024,  # 1GB
    'download_timeout': 300  # 5분
}
```

#### 1.2. 새로운 커넥터 추가
```python
# src/plugin/connector/http_file_connector.py 신규 생성
class HttpFileConnector(BaseConnector):
    def __init__(self):
        super().__init__()
        self.gcs_client = None
        self.credentials = None
    
    def create_session(self, options: dict, secret_data: dict, schema: str):
        """GCS 클라이언트 세션 생성"""
    
    def list_files(self, bucket_name: str, pattern: str = None) -> List[dict]:
        """버킷에서 파일 목록 조회"""
    
    def download_file_stream(self, bucket_name: str, file_path: str) -> IO:
        """파일을 스트림으로 다운로드"""
```

#### 1.3. Field Mapper 기본 구조
```python
# src/plugin/manager/field_mapper.py 신규 생성
class FieldMapper:
    def __init__(self, mapping_config: dict, provider: str = None):
        self.mapping_config = mapping_config
        self.provider = provider
        self._compile_mappings()
    
    def map_record(self, source_data: dict) -> dict:
        """단일 레코드를 SpaceONE 형식으로 변환"""
    
    def _get_default_mapping(self, provider: str) -> dict:
        """프로바이더별 기본 매핑 반환"""
```

### Phase 2: 파일 처리 엔진 구현 (2-3주)

#### 2.1. 파일 파서 구현
```python
# src/plugin/parser/ 디렉토리 생성
# src/plugin/parser/base_parser.py
class BaseParser(ABC):
    @abstractmethod
    def parse_stream(self, stream: IO, field_mapper: FieldMapper) -> Generator[dict, None, None]:
        """스트림을 파싱하여 매핑된 데이터 반환"""

# src/plugin/parser/csv_parser.py
class CSVParser(BaseParser):
    def parse_stream(self, stream: IO, field_mapper: FieldMapper) -> Generator[dict, None, None]:
        """CSV 파일 파싱"""

# src/plugin/parser/json_parser.py  
class JSONParser(BaseParser):
    def parse_stream(self, stream: IO, field_mapper: FieldMapper) -> Generator[dict, None, None]:
        """JSON 파일 파싱 (스트리밍)"""

# src/plugin/parser/parquet_parser.py
class ParquetParser(BaseParser):
    def parse_stream(self, stream: IO, field_mapper: FieldMapper) -> Generator[dict, None, None]:
        """Parquet 파일 파싱"""
```

#### 2.2. 압축 처리 구현
```python
# src/plugin/utils/compression.py 신규 생성
class CompressionHandler:
    @staticmethod
    def detect_compression(file_name: str) -> Optional[str]:
        """파일명으로 압축 형식 감지"""
    
    @staticmethod
    def decompress_stream(stream: IO, compression_type: str) -> IO:
        """압축 스트림 해제"""
```

#### 2.3. 파일 처리 팩토리
```python
# src/plugin/factory/file_processor_factory.py 신규 생성
class FileProcessorFactory:
    @staticmethod
    def create_parser(file_format: str) -> BaseParser:
        """파일 형식에 맞는 파서 생성"""
    
    @staticmethod
    def detect_file_format(file_name: str, content_sample: bytes) -> str:
        """파일 형식 자동 감지"""
```

### Phase 3: Manager 계층 통합 (1-2주)

#### 3.1. CostManager 확장
```python
# src/plugin/manager/cost_manager.py 수정
class CostManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery_connector = BigqueryConnector()
        self.http_file_connector = HttpFileConnector()  # 추가
        self.field_mapper = None  # 추가
    
    def get_data(self, options: dict, secret_data: dict, task_options: dict, schema: str = None) -> Generator[dict, None, None]:
        """데이터 소스 타입에 따라 처리 분기"""
        data_source_type = options.get('data_source_type', 'bigquery')
        
        if data_source_type == 'http_file':
            yield from self._get_data_from_http_file(options, secret_data, task_options, schema)
        else:
            yield from self._get_data_from_bigquery(options, secret_data, task_options, schema)
    
    def _get_data_from_http_file(self, options: dict, secret_data: dict, task_options: dict, schema: str) -> Generator[dict, None, None]:
        """HTTP 파일에서 데이터 조회 (신규)"""
    
    def _get_data_from_bigquery(self, options: dict, secret_data: dict, task_options: dict, schema: str) -> Generator[dict, None, None]:
        """BigQuery에서 데이터 조회 (기존 로직)"""
```

#### 3.2. JobManager 확장
```python
# src/plugin/manager/job_manager.py 수정
class JobManager(BaseManager):
    def get_tasks(self, domain_id: str, options: dict, secret_data: dict, schema: str = None, start: str = None, last_synchronized_at: datetime = None) -> dict:
        """데이터 소스 타입에 따라 작업 생성 분기"""
        data_source_type = options.get('data_source_type', 'bigquery')
        
        if data_source_type == 'http_file':
            return self._get_http_file_tasks(domain_id, options, secret_data, schema, start, last_synchronized_at)
        else:
            return self._get_bigquery_tasks(domain_id, options, secret_data, schema, start, last_synchronized_at)
```

### Phase 4: 에러 처리 및 최적화 (1주)

#### 4.1. 에러 클래스 확장
```python
# src/plugin/error/cost.py 확장
class ERROR_UNSUPPORTED_FILE_FORMAT(ERROR_INVALID_ARGUMENT):
    _message = 'Unsupported file format: {format}'

class ERROR_FILE_DOWNLOAD_FAILED(ERROR_UNKNOWN):
    _message = 'File download failed: {file_path}'

class ERROR_FILE_PARSING_FAILED(ERROR_UNKNOWN):
    _message = 'File parsing failed: {file_path}, reason: {reason}'

class ERROR_FIELD_MAPPING_FAILED(ERROR_INVALID_ARGUMENT):
    _message = 'Field mapping failed: {field}, reason: {reason}'
```

#### 4.2. 성능 최적화
- 스트리밍 처리로 메모리 사용량 최적화
- 파일 다운로드 재시도 로직
- 병렬 파일 처리 (선택적)

### Phase 5: 테스트 및 문서화 (1-2주)

#### 5.1. 단위 테스트
```python
# test/test_http_file_connector.py
# test/test_field_mapper.py  
# test/test_file_parsers.py
# test/test_cost_manager_http_file.py
```

#### 5.2. 통합 테스트
```python
# test/integration/test_http_file_integration.py
# test/integration/test_backward_compatibility.py
```

#### 5.3. 문서 업데이트
- README.md 업데이트
- API 문서 업데이트
- 사용 가이드 작성

## 호환성 보장 전략

### 기존 API 인터페이스 유지
- `main.py`의 라우팅 함수 시그니처 변경 없음
- 기존 `options` 구조 하위 호환성 보장
- 기존 `secret_data` 구조 그대로 지원

### 기본값 설정
```python
# 기존 사용자를 위한 기본값
DEFAULT_DATA_SOURCE_TYPE = 'bigquery'

def get_data_source_type(options: dict) -> str:
    return options.get('data_source_type', DEFAULT_DATA_SOURCE_TYPE)
```

### 점진적 마이그레이션
- 기존 BigQuery 기능 완전 유지
- HTTP 파일 기능은 opt-in 방식
- 충분한 테스트 후 기본값 변경 고려

## 위험 요소 및 완화 방안

### 기술적 위험
| 위험 요소 | 영향도 | 완화 방안 |
|:---------|:------|:---------|
| 기존 기능 영향 | 높음 | 철저한 회귀 테스트, 독립적인 코드 경로 |
| 메모리 사용량 증가 | 중간 | 스트리밍 처리, 청크 단위 처리 |
| 파일 형식 호환성 | 중간 | 파일 형식 자동 감지, 명확한 에러 메시지 |

### 운영 위험
| 위험 요소 | 영향도 | 완화 방안 |
|:---------|:------|:---------|
| 설정 복잡성 증가 | 중간 | 자동 매핑, 명확한 문서화 |
| 디버깅 복잡성 | 중간 | 상세한 로깅, 단계별 에러 메시지 |

## 성공 기준

### 기능적 기준
- [x] HTTP 파일 모드에서 CSV, JSON, Parquet 파일 처리 가능
- [x] 압축 파일(.gz, .snappy, .zstd) 처리 가능  
- [x] Field Mapper를 통한 유연한 필드 매핑
- [x] 기존 BigQuery 기능 완전 유지

### 성능 기준
- [ ] 100MB 파일을 5분 이내 처리
- [ ] 메모리 사용량 512MB 이하 유지
- [ ] 기존 BigQuery 모드 성능 저하 없음

### 품질 기준
- [ ] 단위 테스트 커버리지 80% 이상
- [ ] 모든 회귀 테스트 통과
- [ ] 에러 처리 및 복구 로직 검증

## 일정 및 마일스톤

| Phase | 기간 | 주요 산출물 | 검증 기준 |
|:------|:-----|:----------|:---------|
| Phase 1 | 1-2주 | 기반 구조, 커넥터, Field Mapper | 기본 구조 테스트 통과 |
| Phase 2 | 2-3주 | 파일 파서, 압축 처리 | 파일 형식별 파싱 테스트 통과 |
| Phase 3 | 1-2주 | Manager 통합 | 통합 테스트 통과 |
| Phase 4 | 1주 | 에러 처리, 최적화 | 성능 테스트 통과 |
| Phase 5 | 1-2주 | 테스트, 문서화 | 전체 테스트 통과, 문서 완성 |

**총 예상 기간: 6-10주**

## 구현 우선순위

### High Priority ✅ 완료
1. ✅ HttpFileConnector 기본 구현
2. ✅ CSV 파서 구현
3. ✅ Field Mapper 기본 기능
4. ✅ CostManager 통합

### Medium Priority ✅ 완료
1. ✅ JSON, Parquet 파서
2. ✅ 압축 파일 지원 (gzip, snappy, zstd)
3. ✅ 고급 Field Mapper 기능 (변환, 표현식 지원)
4. ✅ 성능 최적화 (동적 청크 크기 조정)
5. ✅ 동시성 제어 시스템 (ConcurrencyManager)
6. ✅ 세션 캐싱 최적화
7. ✅ 중복 요청 방지 (RequestDeduplicator)

### Low Priority
1. ✅ 파일 처리 동시성 제어 (완료)
2. 고급 필터링 기능
3. ✅ 캐싱 최적화 (완료)
4. 모니터링 기능

이 로드맵을 따라 단계적으로 구현하면, 기존 기능을 보존하면서 새로운 HTTP 파일 처리 기능을 안전하게 추가할 수 있습니다.
