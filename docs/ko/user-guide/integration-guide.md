# Google Cloud Billing 통합 가이드

SpaceONE의 Google Cloud Billing 비용 데이터 소스 플러그인 사용법을 설명합니다. 이 플러그인은 BigQuery와 HTTP 파일 두 가지 데이터 소스를 지원합니다.

## 목차
1. [개요](#1-개요)
2. [사전 준비](#2-사전-준비)
3. [BigQuery 모드 설정](#3-bigquery-모드-설정)
4. [HTTP 파일 모드 설정](#4-http-파일-모드-설정)
5. [Field Mapper 설정](#5-field-mapper-설정)
6. [비용 분석 활용](#6-비용-분석-활용)
7. [고급 설정](#7-고급-설정)
8. [문제 해결](#8-문제-해결)

## 1. 개요

### 지원 데이터 소스
1. **BigQuery**: 실시간 쿼리를 통한 상세한 분석 (기존 기능)
2. **HTTP 파일**: Google Cloud Storage에 저장된 Billing Export 파일 직접 처리 (신규 기능)

### 지원 파일 형식
- CSV, JSON, Parquet
- 압축 파일 (.gz, .snappy, .zstd 등)

### 핵심 기능
- **이중 데이터 소스 지원**: BigQuery와 HTTP 파일 모두 지원
- **유연한 필드 매핑**: Field Mapper를 통한 커스터마이징
- **크레딧, 유효 할인 등 복잡한 비용 구조 분석 지원**
- **라벨, 태그를 활용한 세분화된 비용 추적**

> **[데이터 구조 이해]**  
> 효과적인 사용을 위해 [Google Cloud Billing 데이터 분석 가이드](./data-analysis-guide.md)를 먼저 읽어보시기를 권장합니다.

## 2. 사전 준비

### 2.1. Google Cloud Billing Export 설정

#### BigQuery로 내보내기 설정
1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동합니다.
2. **BigQuery 내보내기** 탭에서 다음과 같이 설정합니다:
   - **프로젝트**: BigQuery 데이터셋을 생성할 프로젝트 선택
   - **데이터셋 ID**: `billing_export` (권장) 또는 원하는 데이터셋명
   - **테이블 접두사**: 기본값 유지 (`gcp_billing_export_v1_`)

> **⚠️ 중요**: **상세 사용량 비용 데이터 내보내기**를 반드시 활성화하세요. 표준 데이터보다 더 상세한 리소스 수준 분석이 가능합니다.

#### 파일로 내보내기 설정 (HTTP 파일 모드용)
1. **파일 내보내기** 탭에서 다음과 같이 설정합니다:
   - **버킷**: 비용 데이터를 저장할 **Google Cloud Storage(GCS) 버킷** 지정
   - **보고서 접두사**: `billing-export/` (권장)
   - **파일 형식**: CSV, JSON, Parquet 중 선택 (Parquet 권장)

#### 내보내기 활성화 후 주의사항
- **데이터 지연**: 내보내기 활성화 후 첫 데이터는 **다음 날**부터 생성됩니다.
- **과거 데이터**: 활성화 이전 데이터는 내보내지지 않습니다.
- **테이블 생성**: BigQuery 테이블은 첫 데이터가 생성될 때 자동으로 만들어집니다.

### 2.2. 서비스 계정 생성 및 권한 설정
1. **IAM 및 관리자 > 서비스 계정**에서 새 서비스 계정을 생성합니다.
2. 필요한 역할을 부여합니다:
   - **BigQuery 모드**: `BigQuery Data Viewer`, `BigQuery Job User`
   - **HTTP 파일 모드**: `Storage Object Viewer`
3. 서비스 계정 키(JSON 형식)를 생성하고 다운로드합니다.

## 3. BigQuery 모드 설정

BigQuery에서 직접 데이터를 조회하는 기존 방식입니다.

```yaml
# options 설정
options:
  billing_export_project_id: "your-project-id"
  billing_dataset_id: "billing_dataset"
  billing_account_id: "XXXXXX-XXXXXX-XXXXXX"

# secret_data 설정
secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "service-account@your-project.iam.gserviceaccount.com"
  token_uri: "https://oauth2.googleapis.com/token"
```

### 고급 설정 (BigQuery)
```yaml
# task_options 설정 예시
task_options:
  start: "2024-07"
  project_id: "*"  # 모든 프로젝트 또는 특정 프로젝트 ID
```

## 4. HTTP 파일 모드 설정

Google Cloud Storage에 저장된 Billing Export 파일을 직접 처리하는 새로운 방식입니다.

```yaml
# options 설정
options:
  data_source_type: "http_file"         # HTTP 파일 모드 활성화
  bucket_name: "your-billing-export-bucket"
  provider: "google_cloud"              # 자동 매핑 활성화
  field_mapper: ...                     # 5. Field Mapper 설정 참고
  default_vars:
    provider: "google_cloud"

# secret_data 설정
secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key_id: "..."
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "..."
  ...
```

### 고급 설정 (HTTP 파일)
```yaml
# task_options 설정 예시
task_options:
  file_pattern: "gcp_billing_export_v1_*_202407.csv"
  max_files: 10
  date_range:
    start_date: "2024-07-01"
    end_date: "2024-07-31"

# 파일 형식별 옵션
options:
  file_format_options:
    csv:
      delimiter: ","
      encoding: "utf-8"
    json:
      json_path: "$.data[*]"
    parquet:
      chunk_size: 10000
```

## 5. Field Mapper 설정

> **주의**: Field Mapper는 **HTTP 파일 모드에서만** 사용됩니다.

### 5.1. 기본 자동 매핑
`provider: google_cloud` 설정으로 기본 필드가 자동 매핑됩니다:

```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  currency: "currency"
  provider: "provider"
```

### 5.2. 추가 정보 매핑
더 상세한 분석을 위한 추가 필드 매핑:

```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  currency: "currency"
  additional_info:
    # 비용 및 할인 관련 (Google Cloud Billing Export 표준 필드)
    cost_at_list: "cost_at_list"                    # 정가 (할인 전)
    cost_after_credits: "cost_after_credits"        # 크레딧 적용 후 비용
    credits: "credits"                              # 크레딧 상세 내역
    
    # 리소스 및 계층 구조
    project_id: "project.id"
    project_name: "project.name"
    service_description: "service.description"
    sku_description: "sku.description"
    billing_account_id: "billing_account_id"
    
    # 위치 및 시간
    location_region: "location.region"
    invoice_month: "invoice.month"
    cost_type: "cost_type"
    
    # 태그 및 라벨 (Google Cloud 표준)
    labels: "labels"                               # 리소스 라벨
    resource_tags: "tags"                          # 리소스 태그
```

> **[상세 가이드]**  
> Field Mapper의 고급 기능은 [Field Mapper 개발 가이드](../development/field-mapper-guide.md)를 참고하세요.

## 6. 비용 분석 활용

### 6.1. 크레딧(Credits) 분석
`credits` 필드 매핑으로 할인 내역을 상세히 분석할 수 있습니다:

```json
"credits": [
  {
    "name": "Sustained Use Discount",
    "amount": -0.123,
    "type": "SUSTAINED_USAGE_DISCOUNT"
  }
]
```

**활용 방안**:
- `additional_info.credits.type`으로 할인 유형별 그룹화
- 특정 프로모션 크레딧 효과 측정

### 6.2. 유효 할인율 분석
`cost`와 `cost_at_list` 필드를 모두 수집하여 실질적인 할인 혜택을 분석:

```yaml
field_mapper:
  cost: "cost"
  additional_info:
    cost_at_list: "cost_at_list"
```

**활용 방안**:
- `(cost_at_list - cost) / cost_at_list × 100` 공식으로 할인율 계산
- 서비스별, 프로젝트별 할인율 비교

### 6.3. 다차원 분석
매핑된 모든 필드를 활용한 유연한 그룹화 및 필터링:
- **그룹화**: `project.name`, `service.description`, `labels.key` 등
- **필터링**: 특정 프로젝트, 라벨, 태그 값으로 비용 필터링

## 7. 고급 설정

### 7.1. 파일 패턴 필터링
```yaml
task_options:
  file_pattern: "gcp_billing_export_v1_01XXXX-XXXXXX-XXXXXX_202407.csv"
```

### 7.2. 날짜 범위 필터링
```yaml
task_options:
  date_range:
    start_date: "2024-07-01"
    end_date: "2024-07-31"
```

### 7.3. 성능 최적화
```yaml
task_options:
  max_files: 10        # 처리할 최대 파일 수
  
options:
  file_format_options:
    parquet:
      chunk_size: 10000  # 청크 크기 조정
```

## 8. 문제 해결

### 8.1. 공통 문제
- **인증 오류**: 서비스 계정 키가 올바른지, 만료되지 않았는지 확인
- **데이터 누락**: Billing Export 활성화 시점 이후 데이터만 수집됨

### 8.2. BigQuery 모드 문제
- **테이블 없음**: BigQuery에 billing export 테이블 생성 확인
- **권한 오류**: `BigQuery Data Viewer`, `BigQuery Job User` 역할 확인
- **쿼리 오류**: `billing_export_project_id`, `billing_dataset_id`, `billing_account_id` 설정 확인

### 8.3. HTTP 파일 모드 문제
- **파일 접근 오류**: `Storage Object Viewer` 역할 확인
- **파일 형식 오류**: 지원 형식(CSV, JSON, Parquet) 확인
- **필드 매핑 오류**: 필수 필드(`cost`, `billed_date`, `currency`) 매핑 확인
- **압축 파일 오류**: 지원 압축 형식(.gz, .snappy, .zstd) 확인
- **메모리 부족**: `max_files` 값 조정

### 8.4. gRPC 메시지 크기 제한 문제
```
ERROR: ResourceExhausted
Message: grpc: received message larger than max (4211270 vs. 4194304)
```

**원인**: 대용량 데이터 배치가 gRPC 메시지 크기 제한(4MB)을 초과

**해결 방법**:

1. **자동 조정 (권장)**: 플러그인이 자동으로 청크 크기를 조정합니다
   - 메시지 크기를 실시간 모니터링
   - 80% 임계값 초과 시 청크 크기 자동 감소
   - 30% 미만 시 청크 크기 점진적 증가

2. **수동 청크 크기 조정**:
   ```json
   {
     "task_options": {
       "parsing_options": {
         "chunk_size": 500
       }
     }
   }
   ```

3. **서버 설정 조정**: `config.yaml`에서 gRPC 메시지 크기 제한 증가:
   ```yaml
   GLOBAL:
     GRPC_MAX_RECEIVE_MESSAGE_LENGTH: 16777216  # 16MB
     GRPC_MAX_SEND_MESSAGE_LENGTH: 16777216     # 16MB
   ```

4. **파일 분할**: 큰 파일을 여러 작은 파일로 분할하여 처리

## 참고 자료

### 관련 문서
- **[Google Cloud Billing Export 설정 가이드](./billing-export-setup.md)** - Billing Export 설정 방법
- **[Google Cloud Billing 데이터 분석 가이드](./data-analysis-guide.md)** - 데이터 구조 및 분석 방법
- **[크레딧 및 할인 분석 가이드](./credits-and-discounts-analysis.md)** - 크레딧과 할인 상세 분석
- **[Field Mapper 개발 가이드](../development/field-mapper-guide.md)** - Field Mapper 구현 방법
- **[프로젝트 요구사항 명세서 (PRD)](../development/prd.md)** - HTTP 파일 통합 기능 PRD
- **[구현 로드맵](../development/implementation-roadmap.md)** - 단계별 구현 계획
- **[아키텍처 설계](../technical/architecture.md)** - 전체 시스템 아키텍처

### Google Cloud 공식 문서
- [BigQuery로 Billing 데이터 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko)
- [Cloud Storage로 Billing 데이터 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-file?hl=ko)
- [Google Cloud Storage API 문서](https://cloud.google.com/storage/docs/apis)

### SpaceONE 문서
- [SpaceONE 플러그인 개발 가이드](https://spaceone.io/docs/guides/developer/plugin-development/)
- [SpaceONE 비용 분석 가이드](https://spaceone.io/docs/guides/cost-analysis/)
