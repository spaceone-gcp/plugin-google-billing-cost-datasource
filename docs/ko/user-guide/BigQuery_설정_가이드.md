# BigQuery 빌링 데이터 설정 완전 가이드

##  개요

Google Cloud Billing 데이터를 BigQuery로 내보내고 SpaceONE 플랫폼에서 활용하기 위한 완전 가이드입니다.

**대상 사용자**: 시스템 관리자, 클라우드 엔지니어, 재무 담당자

---

##  1단계: Cloud Billing 데이터 내보내기 설정

### 1.1 BigQuery 데이터세트 생성

```bash
# Google Cloud CLI를 사용한 데이터세트 생성
bq mk --dataset --location=US your-project-id:billing_export
```

**Console에서 생성:**
1. BigQuery 콘솔 → 프로젝트 선택
2. "데이터세트 만들기" 클릭
3. 데이터세트 ID: `billing_export`
4. 위치: `US` (권장)

### 1.2 Cloud Billing 내보내기 설정

**Cloud Console에서 설정:**
1. **Cloud Console → Billing → Billing export**
2. **BigQuery export** 탭 선택
3. **Projects** 드롭다운에서 BigQuery 프로젝트 선택
4. **Billing export dataset** 선택: `billing_export`
5. **Enable** 클릭

### 1.3 내보내기 유형별 설정

#### 표준 사용량 비용 데이터 (Standard Usage Cost Data)
- **테이블명**: `gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
- **데이터 포함**: 기본 비용 및 사용량 정보
- **업데이트**: 일 3-4회
- **권장 용도**: 기본 비용 분석

#### 자세한 사용량 비용 데이터 (Detailed Usage Cost Data)  
- **테이블명**: `gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX`
- **데이터 포함**: 리소스 레벨 상세 정보
- **업데이트**: 일 3-4회  
- **권장 용도**: 상세한 리소스 분석

#### 가격 책정 데이터 (Pricing Data)
- **테이블명**: `cloud_pricing_export`
- **데이터 포함**: 서비스별 가격 정보
- **업데이트**: 주간
- **권장 용도**: 가격 비교 및 예산 계획

---

##  2단계: BigQuery 테이블 구조 이해

### 2.1 표준 데이터 내보내기 스키마

#### 핵심 필드
```sql
-- 비용 정보
cost FLOAT64                    -- 총 비용 (크레딧 포함)
currency STRING                 -- 통화 (USD, KRW 등)
cost_at_list FLOAT64           -- 정가 (크레딧 제외)

-- 사용량 정보  
usage_amount FLOAT64           -- 사용량
usage_unit STRING              -- 사용량 단위
usage_amount_in_pricing_units FLOAT64

-- 시간 정보
usage_start_time TIMESTAMP     -- 사용 시작 시간
usage_end_time TIMESTAMP       -- 사용 종료 시간
export_time TIMESTAMP          -- 내보내기 시간

-- 프로젝트 정보
project STRUCT<
  id STRING,                   -- 프로젝트 ID  
  name STRING,                 -- 프로젝트 이름
  ancestry_numbers STRING      -- 프로젝트 계층
>

-- 서비스 정보
service STRUCT<
  id STRING,                   -- 서비스 ID
  description STRING           -- 서비스 이름 (Compute Engine 등)
>

-- SKU 정보
sku STRUCT<
  id STRING,                   -- SKU ID
  description STRING           -- SKU 설명
>

-- 위치 정보
location STRUCT<
  location STRING,             -- 위치 (us-central1 등)
  country STRING,              -- 국가
  region STRING,               -- 리전
  zone STRING                  -- 존
>

-- 레이블 및 태그
labels ARRAY<STRUCT<
  key STRING,
  value STRING
>>

-- 크레딧 정보
credits ARRAY<STRUCT<
  name STRING,                 -- 크레딧 이름
  amount FLOAT64,              -- 크레딧 금액
  type STRING                  -- 크레딧 유형
>>
```

### 2.2 자세한 사용량 데이터 추가 필드

```sql
-- 리소스 정보 (자세한 데이터에만 포함)
resource STRUCT<
  name STRING,                 -- 리소스 이름
  global_name STRING           -- 글로벌 리소스 이름
>

-- 시스템 레이블
system_labels ARRAY<STRUCT<
  key STRING,
  value STRING
>>
```

### 2.3 가격 책정 데이터 스키마

```sql
-- 가격 정보
list_price STRUCT<
  currency_code STRING,        -- 통화
  units FLOAT64,              -- 단위당 가격
  nanos INT64                 -- 나노 단위 가격
>

-- 계층형 가격 (사용량에 따른 가격 차등)
tiered_rates ARRAY<STRUCT<
  start_usage_amount FLOAT64,  -- 시작 사용량
  unit_price STRUCT<
    currency_code STRING,
    units FLOAT64,
    nanos INT64
  >
>>
```

---

##  3단계: 실용적인 쿼리 예시

### 3.1 기본 비용 분석 쿼리

#### 프로젝트별 월간 비용
```sql
SELECT 
  project.id as project_id,
  project.name as project_name,
  service.description as service_name,
  FORMAT_TIMESTAMP('%Y-%m', usage_start_time) as month,
  SUM(cost) as total_cost,
  currency
FROM `your-project.billing_export.gcp_billing_export_v1_*`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 MONTH)
GROUP BY project_id, project_name, service_name, month, currency
ORDER BY month DESC, total_cost DESC
```

#### 서비스별 비용 순위
```sql
SELECT 
  service.description as service_name,
  SUM(cost) as total_cost,
  SUM(cost_at_list) as total_list_cost,
  SUM(cost_at_list) - SUM(cost) as total_credits,
  COUNT(*) as record_count,
  currency
FROM `your-project.billing_export.gcp_billing_export_v1_*`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MONTH)
GROUP BY service_name, currency
HAVING total_cost > 0
ORDER BY total_cost DESC
LIMIT 20
```

### 3.2 크레딧 및 할인 분석

#### 크레딧 상세 분석
```sql
WITH credit_details AS (
  SELECT 
    project.id as project_id,
    service.description as service_name,
    credit.name as credit_name,
    credit.type as credit_type,
    SUM(credit.amount) as credit_amount,
    FORMAT_TIMESTAMP('%Y-%m', usage_start_time) as month
  FROM `your-project.billing_export.gcp_billing_export_v1_*`,
  UNNEST(credits) as credit
  WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 MONTH)
    AND credit.amount < 0  -- 크레딧은 음수로 표시
  GROUP BY project_id, service_name, credit_name, credit_type, month
)
SELECT 
  project_id,
  service_name,
  credit_name,
  credit_type,
  month,
  ABS(credit_amount) as credit_amount,
  ABS(credit_amount) * 1300 as credit_amount_krw  -- USD to KRW 환산 (예시)
FROM credit_details
ORDER BY month DESC, credit_amount ASC
```

### 3.3 리소스 레벨 분석 (자세한 데이터)

#### VM 인스턴스별 비용
```sql
SELECT 
  project.id as project_id,
  resource.name as resource_name,
  location.region as region,
  sku.description as sku_description,
  SUM(usage_amount) as total_usage,
  usage_unit,
  SUM(cost) as total_cost,
  currency,
  FORMAT_TIMESTAMP('%Y-%m-%d', usage_start_time) as date
FROM `your-project.billing_export.gcp_billing_export_resource_v1_*`
WHERE service.description = 'Compute Engine'
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND resource.name IS NOT NULL
GROUP BY project_id, resource_name, region, sku_description, usage_unit, currency, date
HAVING total_cost > 0
ORDER BY date DESC, total_cost DESC
```

### 3.4 라벨 기반 비용 추적

#### 환경별 비용 분석 (라벨 활용)
```sql
SELECT 
  project.id as project_id,
  label.value as environment,
  service.description as service_name,
  SUM(cost) as total_cost,
  currency,
  FORMAT_TIMESTAMP('%Y-%m', usage_start_time) as month
FROM `your-project.billing_export.gcp_billing_export_v1_*`,
UNNEST(labels) as label
WHERE label.key = 'environment'  -- 환경 라벨 필터
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MONTH)
GROUP BY project_id, environment, service_name, currency, month
ORDER BY month DESC, total_cost DESC
```

---

##  4단계: SpaceONE 플러그인 설정

### 4.1 BigQuery 연동 설정

```yaml
# BigQuery 데이터소스 설정
options:
  # 필수 설정
  billing_export_project_id: "your-billing-project"
  billing_dataset_id: "billing_export"
  billing_account_id: "XXXXXX-XXXXXX-XXXXXX"
  
  # 선택적 설정
  data_source_type: "bigquery"
  provider: "google_cloud"
  
  # 테이블 설정 (선택사항)
  standard_table_name: "gcp_billing_export_v1_*"
  detailed_table_name: "gcp_billing_export_resource_v1_*"
  
  # 쿼리 최적화
  date_range_days: 30        # 조회 기간 (일)
  batch_size: 10000         # 배치 크기
  
  # 비용 선택 옵션
  select_cost: "cost"       # cost, list_price, after_credits

# 인증 정보
secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "service-account@your-project.iam.gserviceaccount.com"
  token_uri: "https://oauth2.googleapis.com/token"
```

### 4.2 필드 매핑 설정

```yaml
# 필드 매핑 (선택사항)
field_mapper:
  # 필수 필드
  cost: "cost"
  currency: "currency"  
  billed_date: "usage_start_time"
  
  # 식별 필드
  provider: "google_cloud"
  region_code: "location.region"
  product: "service.description"
  usage_type: "sku.description"
  resource: "project.id"
  
  # 사용량 필드
  usage_quantity: "usage_amount"
  usage_unit: "usage_unit"
  
  # 추가 정보
  additional_info:
    project_id: "project.id"
    project_name: "project.name"
    service_id: "service.id"
    sku_id: "sku.id"
    location: "location.location"
    cost_at_list: "cost_at_list"
    credits: "credits"
```

---

##  5단계: 권한 및 보안 설정

### 5.1 필요한 IAM 권한

**서비스 계정에 필요한 권한:**
```yaml
# BigQuery 권한
- roles/bigquery.dataViewer      # 데이터 읽기
- roles/bigquery.jobUser         # 쿼리 실행

# Cloud Billing 권한 (선택사항)
- roles/billing.viewer           # 빌링 계정 정보 조회
```

### 5.2 서비스 계정 생성

```bash
# 1. 서비스 계정 생성
gcloud iam service-accounts create spaceone-billing-reader \
  --display-name="SpaceONE Billing Reader"

# 2. 권한 부여
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:spaceone-billing-reader@your-project.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:spaceone-billing-reader@your-project.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# 3. 키 생성
gcloud iam service-accounts keys create spaceone-key.json \
  --iam-account=spaceone-billing-reader@your-project.iam.gserviceaccount.com
```

---

##  6단계: 데이터 검증 및 모니터링

### 6.1 데이터 품질 확인

#### 기본 검증 쿼리
```sql
-- 1. 데이터 존재 여부 확인
SELECT 
  COUNT(*) as total_records,
  MIN(usage_start_time) as earliest_date,
  MAX(usage_start_time) as latest_date,
  COUNT(DISTINCT project.id) as project_count,
  COUNT(DISTINCT service.description) as service_count
FROM `your-project.billing_export.gcp_billing_export_v1_*`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY);

-- 2. 비용 데이터 품질 확인
SELECT 
  COUNT(*) as total_records,
  COUNT(CASE WHEN cost IS NULL THEN 1 END) as null_cost_count,
  COUNT(CASE WHEN cost = 0 THEN 1 END) as zero_cost_count,
  COUNT(CASE WHEN cost > 0 THEN 1 END) as positive_cost_count,
  COUNT(CASE WHEN cost < 0 THEN 1 END) as negative_cost_count
FROM `your-project.billing_export.gcp_billing_export_v1_*`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY);
```

### 6.2 SpaceONE 연동 테스트

```bash
# grpcurl을 통한 연동 테스트
grpcurl -plaintext -d '{
  "options": {
    "billing_export_project_id": "your-project",
    "billing_dataset_id": "billing_export",
    "billing_account_id": "XXXXXX-XXXXXX-XXXXXX"
  },
  "secret_data": {
    "type": "service_account",
    "project_id": "your-project",
    "private_key": "...",
    "client_email": "..."
  }
}' localhost:50051 spaceone.api.cost_analysis.plugin.Cost.get_data
```

---

##  7단계: 문제 해결 및 FAQ

### 7.1 자주 발생하는 문제

#### 문제 1: "Table not found" 오류
**원인**: BigQuery 내보내기가 아직 설정되지 않았거나 데이터가 생성되지 않음
**해결책**: 
1. Cloud Billing 내보내기 설정 확인
2. 24-48시간 대기 (초기 데이터 생성 시간)
3. 테이블명 패턴 확인

#### 문제 2: "Access Denied" 오류
**원인**: 서비스 계정 권한 부족
**해결책**:
1. BigQuery 데이터 뷰어 권한 확인
2. BigQuery 작업 사용자 권한 확인
3. 프로젝트 레벨 권한 확인

#### 문제 3: 데이터가 비어있음
**원인**: 빌링 데이터가 아직 생성되지 않았거나 필터 조건 문제
**해결책**:
1. 실제 GCP 사용량 확인
2. 날짜 범위 확장
3. 프로젝트 필터 조건 확인

### 7.2 성능 최적화

#### 쿼리 최적화 팁
```sql
-- 1. 파티션 필터 활용 (필수)
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)

-- 2. 필요한 컬럼만 선택
SELECT project.id, service.description, cost
FROM `your-project.billing_export.gcp_billing_export_v1_*`

-- 3. 집계 쿼리 활용
SELECT 
  project.id,
  SUM(cost) as total_cost
FROM `your-project.billing_export.gcp_billing_export_v1_*`
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY project.id
```

---

##  결론

이 가이드를 통해 Google Cloud Billing 데이터를 BigQuery로 내보내고 SpaceONE 플랫폼에서 효과적으로 활용할 수 있습니다.

### 핵심 체크리스트
- [ ] BigQuery 데이터세트 생성
- [ ] Cloud Billing 내보내기 설정
- [ ] 서비스 계정 및 권한 설정
- [ ] SpaceONE 플러그인 설정
- [ ] 데이터 검증 및 테스트
- [ ] 모니터링 설정

### 다음 단계
1. [데이터 분석 가이드](./data-analysis-guide.md) - 고급 분석 기법
2. [크레딧 및 할인 분석](./credits-and-discounts-analysis.md) - 비용 최적화
3. [통합 가이드](./integration-guide.md) - SpaceONE 플랫폼 연동

---

**마지막 업데이트**: 2025-09-15  
**버전**: 1.0  
**대상**: BigQuery 빌링 데이터 설정
