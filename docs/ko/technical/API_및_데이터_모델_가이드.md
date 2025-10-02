# API 및 데이터 모델 가이드

## 📋 개요

Google Cloud Billing 플러그인의 **API 명세, 데이터 모델, Job API 응답 형식**에 대한 통합 가이드입니다.

**기반**: v1.0.9 - 통합 source 파라미터, Credits Detail 기능, Cost 필드 보장 시스템 포함

---

## 🚨 SpaceONE JSON 응답 형식 제약사항

### 과학적 표기법 사용 금지 **[CRITICAL]**

모든 API 응답에서 **과학적 표기법은 절대 사용할 수 없습니다**. SpaceONE 플랫폼은 JSON 응답에서 과학적 표기법을 지원하지 않습니다.

#### ❌ 금지된 표기법
```json
{
  "cost": 1.23e-6,        // 과학적 표기법 금지
  "usage_quantity": 4.56E+3,  // 대문자 E도 금지
  "list_price": 7.89e-12    // 매우 작은 값도 금지
}
```

#### ✅ 허용된 표기법
```json
{
  "cost": 0.00000123,         // CRITICAL: 최상위 필드, 절대 누락 금지
  "usage_quantity": 4560.0,   // 정수도 소수점 포함 권장
  "data": {
    "cost": 0.00000123,       // data 필드 내의 cost (별도)
    "list_price": 0.0         // 매우 작은 값은 0.0으로 처리
  }
}
```

---

## 📡 API 명세

### 1. DataSource.init

플러그인 초기화 API

#### 요청 형식
```json
{
  "options": {
    "source": "bigquery|gcs|http",  // 통합 source 파라미터
    "billing_export_project_id": "string",
    "billing_dataset_id": "string",
    "billing_account_id": "string",
    "provider": "google_cloud"
  },
  "domain_id": "string"
}
```

#### 응답 형식
```json
{
  "metadata": {
    "supported_features": ["cost_data", "linked_accounts"],
    "supported_schedules": ["hours", "interval"],
    "options_schema": {
      "type": "object",
      "properties": {
        "source": {
          "type": "string",
          "enum": ["bigquery", "gcs", "http"]
        }
      }
    }
  }
}
```

### 2. DataSource.verify

데이터 소스 설정 검증 API

#### 요청 형식
```json
{
  "options": {
    "source": "bigquery",
    "billing_export_project_id": "your-project-id",
    "billing_dataset_id": "billing_export",
    "billing_account_id": "123456-789012-345678"
  },
  "secret_data": {
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "service-account@your-project.iam.gserviceaccount.com"
  },
  "domain_id": "string"
}
```

#### 응답 형식
```json
// 성공 시: 빈 응답 (HTTP 200)
// 실패 시: 에러 메시지와 함께 예외 발생
```

### 3. Job.get_tasks

작업 태스크 생성 API

#### 요청 형식
```json
{
  "options": {
    "source": "bigquery",
    "billing_export_project_id": "your-project-id",
    "billing_dataset_id": "billing_export",
    "billing_account_id": "123456-789012-345678"
  },
  "secret_data": {
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "service-account@your-project.iam.gserviceaccount.com"
  },
  "start": "2024-01",
  "domain_id": "string"
}
```

#### 응답 형식
```json
{
  "tasks": [
    {
      "task_options": {
        "start": "2024-01",
        "project_id": "project-1"
      }
    },
    {
      "task_options": {
        "start": "2024-01", 
        "project_id": "project-2"
      }
    }
  ],
  "changed": []
}
```

#### start time 결정 로직

Job.get_tasks API에서 start 파라미터 처리 방식:

1. **명시적 start 제공**: 요청에 start가 있으면 그대로 사용
2. **자동 계산**: start가 없으면 현재 시점에서 5년 전으로 설정
3. **프로젝트별 분할**: 각 프로젝트마다 별도 태스크 생성

```python
def _get_start_month(self) -> str:
    """start 파라미터가 없을 때 기본값 계산"""
    current_date = datetime.now()
    start_date = current_date - relativedelta(years=5)  # 5년 전
    return start_date.strftime("%Y-%m")
```

### 4. Cost.get_data

비용 데이터 조회 API

#### 요청 형식
```json
{
  "options": {
    "source": "bigquery",
    "billing_export_project_id": "your-project-id",
    "billing_dataset_id": "billing_export", 
    "billing_account_id": "123456-789012-345678"
  },
  "secret_data": {
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "service-account@your-project.iam.gserviceaccount.com"
  },
  "task_options": {
    "start": "2024-01",
    "project_id": "specific-project",
    "credits_detail_mode": false,
    "credits_detail_limit": 100
  },
  "domain_id": "string"
}
```

#### 응답 형식 (SpaceONE 표준)
```json
{
  "results": [
    {
      "cost": 10.50,                    // CRITICAL: 필수 필드
      "usage_quantity": 100.0,          // 사용량
      "usage_unit": "GB",               // 사용량 단위
      "provider": "google_cloud",       // 프로바이더
      "region_code": "us-central1",     // 리전
      "product": "Compute Engine",      // 제품명
      "usage_type": "N1 Standard",      // 사용 유형
      "resource": "instance-1",         // 리소스명
      "tags": {                         // 태그
        "environment": "production"
      },
      "additional_info": {              // 추가 정보
        "Project": "my-project",
        "Service Account": "123456-789012-345678",
        "Currency": "USD"
      },
      "data": {                         // 원본 데이터
        "billing_account_id": "123456-789012-345678",
        "project_id": "my-project",
        "service_description": "Compute Engine"
      },
      "billed_date": "2024-01-15"       // 청구일
    }
  ]
}
```

### 5. Cost.get_linked_accounts

연결된 계정 조회 API

#### 요청 형식
```json
{
  "options": {
    "source": "bigquery",
    "billing_export_project_id": "your-project-id",
    "billing_dataset_id": "billing_export",
    "billing_account_id": "123456-789012-345678"
  },
  "secret_data": {
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "service-account@your-project.iam.gserviceaccount.com"
  },
  "domain_id": "string"
}
```

#### 응답 형식
```json
{
  "results": [
    {
      "account_id": "project-1",
      "name": "Production Project"
    },
    {
      "account_id": "project-2", 
      "name": "Development Project"
    }
  ]
}
```

---

## 🗂️ 데이터 모델 정의

### 데이터 모델 설계 원칙

#### 핵심 원칙
- **Cost 필드 100% 보장**: 5단계 보장 시스템으로 cost 필드 누락 방지
- **과학적 표기법 지원**: 9.6e-05 등 극소값 완벽 처리
- **Credits Detail 완전 지원**: 개별 크레딧 정보 손실 없이 제공
- **통합 Source 기반**: 단일 source 파라미터로 모든 데이터 소스 통합

#### ABSOLUTE PERFECT ULTRA PURE DATA 준수
- **스키마 일치성**: 모든 데이터 모델은 BigQuery 스키마와 100% 일치해야 함
- **NULL 값 허용**: 모든 필드는 NULL을 허용하며, 기본값으로 변환하지 않음
- **원본 타입 보존**: 데이터 타입 변환 없이 원본 그대로 보존
- **중첩 구조 지원**: RECORD 타입의 중첩 필드 정확히 매핑

### 통합 Source 데이터 모델

#### SourceConfig
```python
from typing import Literal, Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class SourceConfig:
    """통합 Source 설정 모델"""
    source: Literal["bigquery", "gcs", "http"]
    
    # BigQuery 전용 필드
    billing_export_project_id: Optional[str] = None
    billing_dataset_id: Optional[str] = None
    billing_account_id: Optional[str] = None
    
    # GCS 전용 필드
    bucket_name: Optional[str] = None
    
    # HTTP 전용 필드
    base_url: Optional[str] = None
    
    # 공통 필드
    provider: str = "google_cloud"
    field_mapper: Optional[Dict[str, Any]] = None
```

#### CostRecord
```python
@dataclass
class CostRecord:
    """SpaceONE 표준 비용 레코드 모델"""
    # 필수 필드
    cost: float                           # CRITICAL: 절대 누락 금지
    usage_quantity: Optional[float] = None
    usage_unit: Optional[str] = None
    provider: Optional[str] = None
    region_code: Optional[str] = None
    product: Optional[str] = None
    usage_type: Optional[str] = None
    resource: Optional[str] = None
    billed_date: str = ""                 # 필수: 빈 문자열 허용
    currency: Optional[str] = None
    tags: Dict[str, Any] = None
    additional_info: Dict[str, Any] = None
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        """필수 필드 기본값 설정"""
        if self.tags is None:
            self.tags = {}
        if self.additional_info is None:
            self.additional_info = {}
        if self.data is None:
            self.data = {}
```

#### CreditsDetailRecord
```python
@dataclass
class CreditsDetailRecord:
    """Credits Detail 모드 전용 레코드"""
    # 기본 비용 정보
    cost: float
    credits_amount: Optional[float] = None
    list_cost: Optional[float] = None
    
    # 크레딧 세부 정보
    credits: Optional[List[Dict[str, Any]]] = None
    
    # 프로젝트 정보
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    
    # 서비스 정보
    service_id: Optional[str] = None
    service_description: Optional[str] = None
    sku_id: Optional[str] = None
    sku_description: Optional[str] = None
    
    # 사용량 정보
    usage_amount: Optional[float] = None
    usage_unit: Optional[str] = None
    
    # 기간 정보
    usage_start_time: Optional[str] = None
    usage_end_time: Optional[str] = None
```

### 필드 매핑 규칙

#### 완전 매핑 원칙
- **BigQuery 스키마의 모든 필드가 응답에 포함되어야 함**
- **중첩 필드는 정확한 경로로 매핑** (예: `service.description`)
- **스키마의 데이터 타입과 응답 데이터 타입 일치**
- **REPEATED 필드는 JSON 문자열로 변환**

#### 필드 매핑 예시
```python
FIELD_MAPPING = {
    # 기본 필드
    "cost": "cost",
    "currency": "currency", 
    "usage_quantity": "usage.amount",
    "usage_unit": "usage.unit",
    
    # 중첩 필드
    "project_id": "project.id",
    "project_name": "project.name",
    "service_description": "service.description",
    "sku_description": "sku.description",
    
    # 위치 정보
    "region_code": "location.region",
    "zone": "location.zone",
    
    # 크레딧 정보 (Credits Detail 모드)
    "credits": "credits",  # REPEATED 필드 → JSON 문자열
    "credits_amount": "total_credits_amount"
}
```

---

## 🔄 API 처리 플로우

### 전체 처리 흐름

```
1. API 요청 수신
   ↓
2. 파라미터 검증 (source, 필수 필드)
   ↓
3. Source별 분기 처리
   ├─ BigQuery: BigqueryConnector
   ├─ GCS: GcsConnector  
   └─ HTTP: HttpFileConnector
   ↓
4. 데이터 조회 및 처리
   ↓
5. FieldMapper를 통한 SpaceONE 형식 변환
   ↓
6. Cost 필드 5단계 보장 시스템 적용
   ↓
7. gRPC 스마트 청킹으로 응답 전송
```

### Source별 처리 차이점

#### BigQuery 모드
```python
def process_bigquery_request(options, secret_data, task_options):
    # 1. BigQuery 연결 설정
    connector = BigqueryConnector()
    connector.create_session(options, secret_data)
    
    # 2. Credits Detail 모드 확인
    credits_detail = task_options.get("credits_detail_mode", False)
    
    # 3. SQL 쿼리 생성 (GROUP BY vs 원본 데이터)
    if credits_detail:
        query = generate_credits_detail_query()
    else:
        query = generate_aggregated_query()
    
    # 4. 데이터 조회 및 변환
    df = connector.read_df_from_bigquery(query)
    return convert_to_spaceone_format(df)
```

#### GCS 모드
```python
def process_gcs_request(options, secret_data, task_options):
    # 1. GCS 연결 설정
    connector = GcsConnector()
    connector.create_session(options, secret_data)
    
    # 2. 파일 목록 조회 (날짜 필터링)
    files = connector.list_files_with_date_filter(
        bucket_name=options["bucket_name"],
        start_date=task_options.get("start")
    )
    
    # 3. 파일별 처리 (동시성 제어)
    results = []
    for file_path in files:
        with concurrency_manager.acquire_file_lock(file_path):
            data = connector.download_and_parse_file(file_path)
            results.extend(data)
    
    return results
```

#### HTTP 모드
```python
def process_http_request(options, secret_data, task_options):
    # 1. URL 검증
    base_url = options["base_url"]
    validate_url_format(base_url)
    
    # 2. 파일 다운로드 (인증 불필요)
    connector = HttpFileConnector()
    file_content = connector.download_file(base_url)
    
    # 3. 파일 형식 감지 및 파싱
    file_format = detect_file_format(file_content)
    parser = FileProcessorFactory.create_parser(file_format)
    
    return parser.parse(file_content)
```

---

## 🛡️ 에러 처리

### API 레벨 에러 처리

#### 공통 에러 응답
```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Missing required parameter: billing_export_project_id",
    "details": {
      "parameter": "billing_export_project_id",
      "source": "bigquery"
    }
  }
}
```

#### Source별 에러 처리
```python
def handle_source_errors(source: str, error: Exception):
    """Source별 에러 처리"""
    if source == "bigquery":
        if "authentication" in str(error).lower():
            raise AuthenticationError("BigQuery authentication failed")
        elif "quota" in str(error).lower():
            raise QuotaExceededError("BigQuery quota exceeded")
    elif source == "gcs":
        if "access denied" in str(error).lower():
            raise PermissionError("GCS access denied")
    elif source == "http":
        if "404" in str(error):
            raise FileNotFoundError("HTTP file not found")
    
    # 일반 에러
    raise InternalError(f"Unexpected error in {source}: {error}")
```

---

## 📚 참고 자료

### API 문서
- [SpaceONE Cost Analysis Plugin API](https://spaceone-dev.gitbook.io/spaceone-apis/cost-analysis/plugin)
- [gRPC Protocol Documentation](https://grpc.io/docs/)

### 데이터 모델
- [BigQuery 스키마 문서](https://cloud.google.com/bigquery/docs/schemas)
- [Google Cloud Billing Export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)

### 관련 문서
- [스키마 및 필드 정의서](./스키마_및_필드_정의서.md)
- [데이터 소스 처리 가이드](./데이터_소스_처리_가이드.md)
- [시스템 아키텍처](./시스템_아키텍처.md)

---

**마지막 업데이트**: 2025년 10월 2일  
**작성자**: SpaceONE Team  
**버전**: v1.0.9
