# BigQuery로 Cloud Billing 데이터 내보내기 설정

이 문서는 Google Cloud의 공식 [BigQuery로 Cloud Billing 데이터 내보내기 설정](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup?hl=ko) 가이드를 기반으로, Cloud Billing 데이터를 BigQuery로 내보내기 위한 상세한 설정 방법을 단계별로 안내합니다.

## 📋 개요

BigQuery로 Cloud Billing 데이터를 내보내면 비용 및 가격 정보를 포함한 상세한 청구 데이터를 분석할 수 있습니다. 이 가이드는 내보내기 설정에 필요한 모든 단계를 다룹니다.

### 내보내기 가능한 데이터 유형

- **표준 사용량 비용 데이터**: 기본적인 사용량 및 비용 정보
- **상세 사용량 비용 데이터**: 개별 리소스 수준까지의 세밀한 정보
- **가격 데이터**: Google Cloud 서비스의 정가 정보

## 🔐 필수 권한 요구사항

Cloud Billing 데이터 내보내기를 설정하려면 다음 권한이 필요합니다:

### Billing Account 권한
다음 중 **하나 이상**의 역할이 필요합니다:
- **`Billing Account Costs Manager`** (권장)
- **`Billing Account Administrator`**

### BigQuery 권한
다음 중 **하나 이상**의 역할이 필요합니다:
- **`BigQuery User`** (최소 권한)
- **`BigQuery Admin`** (전체 권한)

### 권한 확인 방법

```bash
# 현재 사용자의 Billing 권한 확인
gcloud billing accounts get-iam-policy BILLING_ACCOUNT_ID

# 현재 사용자의 BigQuery 권한 확인
gcloud projects get-iam-policy PROJECT_ID
```

## ⚙️ 단계별 설정 가이드

### 1단계: 프로젝트 준비

#### 1.1 프로젝트 생성 또는 선택
```bash
# 새 프로젝트 생성
gcloud projects create PROJECT_ID --name="Billing Export Project"

# 기존 프로젝트 선택
gcloud config set project PROJECT_ID
```

#### 1.2 프로젝트와 Billing Account 연결
```bash
# Billing Account를 프로젝트에 연결
gcloud billing projects link PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### 2단계: 필수 API 활성화

BigQuery Data Transfer Service API를 활성화해야 합니다:

```bash
# BigQuery Data Transfer Service API 활성화
gcloud services enable bigquerydatatransfer.googleapis.com

# BigQuery API 활성화 (기본적으로 필요)
gcloud services enable bigquery.googleapis.com
```

**Google Cloud 콘솔에서 활성화**:
1. **API 및 서비스 > 라이브러리**로 이동
2. "BigQuery Data Transfer Service"를 검색
3. **사용 설정** 클릭

### 3단계: BigQuery 데이터셋 생성

#### 3.1 데이터셋 생성
```bash
# 데이터셋 생성 (US 다중 지역)
bq mk --location=US --dataset PROJECT_ID:billing_export

# 데이터셋 생성 (EU 다중 지역)
bq mk --location=EU --dataset PROJECT_ID:billing_export

# 데이터셋 생성 (특정 지역)
bq mk --location=us-central1 --dataset PROJECT_ID:billing_export
```

#### 3.2 지원되는 데이터셋 위치

| 위치 유형 | 지원 위치 | 소급 데이터 지원 |
|:---|:---|:---|
| **다중 지역** | `US`, `EU` | ✅ 이전 달부터 |
| **단일 지역** | 대부분의 BigQuery 지역 | ❌ 설정일부터만 |

> **💡 권장사항**: 포괄적인 데이터 수집을 위해 **다중 지역** (`US` 또는 `EU`) 사용을 권장합니다.

### 4단계: Cloud Billing 내보내기 설정

#### 4.1 Google Cloud 콘솔에서 설정

1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동
2. **BigQuery 내보내기** 탭 선택
3. 내보내기 유형 선택:
   - ✅ **표준 사용량 비용 데이터**
   - ✅ **상세 사용량 비용 데이터** (권장)
   - ✅ **가격 데이터** (선택사항)

#### 4.2 내보내기 설정 정보 입력

```yaml
# 설정 예시
프로젝트 ID: "your-billing-project"
데이터셋 ID: "billing_export"
위치: "US" 또는 "EU"
```

#### 4.3 gcloud CLI를 통한 설정

```bash
# 표준 사용량 비용 데이터 내보내기 설정
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_ID \
  --dataset-id=PROJECT_ID.billing_export

# 상세 사용량 비용 데이터 내보내기 설정
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_ID \
  --dataset-id=PROJECT_ID.billing_export \
  --detailed-usage-cost

# 가격 데이터 내보내기 설정
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_ID \
  --dataset-id=PROJECT_ID.billing_export \
  --pricing-data
```

### 5단계: 권한 설정 및 검증

#### 5.1 Cloud Billing 서비스 계정 권한 부여

Cloud Billing 내보내기는 다음 서비스 계정을 사용합니다:
- `billing-export-bigquery@system.gserviceaccount.com`

```bash
# BigQuery Data Editor 역할 부여
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# BigQuery Job User 역할 부여
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

#### 5.2 데이터셋 수준 권한 설정

```bash
# 데이터셋에 직접 권한 부여
bq add-iam-policy-binding \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor" \
  PROJECT_ID:billing_export
```

### 6단계: 설정 검증 및 테스트

#### 6.1 내보내기 상태 확인

```bash
# 현재 내보내기 설정 확인
gcloud billing export bigquery list --billing-account=BILLING_ACCOUNT_ID

# 특정 내보내기 상세 정보 확인
gcloud billing export bigquery describe EXPORT_ID \
  --billing-account=BILLING_ACCOUNT_ID
```

#### 6.2 데이터셋 및 테이블 확인

```bash
# 생성된 데이터셋 확인
bq ls PROJECT_ID:

# 데이터셋 내 테이블 확인 (내보내기 후 24시간 이내)
bq ls PROJECT_ID:billing_export

# 테이블 스키마 확인
bq show PROJECT_ID:billing_export.gcp_billing_export_v1_BILLING_ACCOUNT_ID
```

#### 6.3 첫 번째 데이터 확인

```sql
-- 내보낸 데이터 샘플 확인
SELECT
  billing_account_id,
  service.description as service_name,
  sku.description as sku_name,
  usage_start_time,
  cost,
  currency
FROM `PROJECT_ID.billing_export.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) = CURRENT_DATE() - 1
LIMIT 10;
```

## 🔧 고급 설정 옵션

### 1. 다중 Billing Account 설정

여러 Billing Account의 데이터를 동일한 데이터셋으로 내보내기:

```bash
# 첫 번째 Billing Account
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_1 \
  --dataset-id=PROJECT_ID.consolidated_billing

# 두 번째 Billing Account  
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_2 \
  --dataset-id=PROJECT_ID.consolidated_billing
```

### 2. 조직 수준 권한 설정

조직 전체에 대한 일괄 설정:

```bash
# 조직 수준에서 BigQuery 권한 부여
gcloud organizations add-iam-policy-binding ORGANIZATION_ID \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

### 3. 커스텀 테이블 이름 설정

```bash
# 커스텀 테이블 접두사 사용
gcloud billing export bigquery create \
  --billing-account=BILLING_ACCOUNT_ID \
  --dataset-id=PROJECT_ID.billing_export \
  --table-prefix="custom_billing_"
```

## ⚠️ 주의사항 및 제한사항

### 1. 데이터 지연시간
- **첫 번째 데이터**: 설정 후 최대 24시간
- **일일 업데이트**: UTC 기준 오전 중 (보통 1-2회)
- **완전한 데이터**: 전날 데이터는 일반적으로 완전함

### 2. 지역 제한사항
- **지원되지 않는 지역**: 일부 BigQuery 지역은 지원되지 않음
- **CMEK 지원 안 함**: 고객 관리 암호화 키 사용 불가
- **VPC 서비스 제어**: 활성화된 경우 수동 제외 필요

### 3. 비용 고려사항

```bash
# BigQuery 저장 비용 예상
# 표준 사용량 데이터: ~10-50 MB/월 (소규모 프로젝트)
# 상세 사용량 데이터: ~100-500 MB/월 (중간 규모 프로젝트)
# 대용량 조직: 수 GB/월 가능
```

### 4. 보안 고려사항

#### 행 수준 보안 설정
```sql
-- 프로젝트별 접근 제한 예시
CREATE ROW ACCESS POLICY project_access_policy
ON `PROJECT_ID.billing_export.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
GRANT TO ('user:analyst@company.com')
FILTER USING (project.id = 'allowed-project-id');
```

## 🔍 문제 해결

### 일반적인 오류 및 해결방법

#### 1. 권한 오류
```
ERROR: The caller does not have permission
```

**해결방법**:
```bash
# 현재 사용자 권한 확인
gcloud auth list
gcloud config list

# 필요한 권한 다시 부여
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:your-email@company.com" \
  --role="roles/billing.costsManager"
```

#### 2. API 비활성화 오류
```
ERROR: BigQuery Data Transfer Service API is not enabled
```

**해결방법**:
```bash
# API 활성화 상태 확인
gcloud services list --enabled --filter="name:bigquerydatatransfer"

# API 활성화
gcloud services enable bigquerydatatransfer.googleapis.com
```

#### 3. 데이터셋 위치 오류
```
ERROR: Dataset location not supported
```

**해결방법**:
- 지원되는 위치(`US`, `EU`, 또는 특정 지역)로 변경
- 다중 지역 사용을 권장

#### 4. 데이터 지연 문제

**확인 방법**:
```sql
-- 최신 데이터 확인
SELECT
  MAX(usage_start_time) as latest_usage_time,
  MAX(_PARTITIONTIME) as latest_partition_time,
  COUNT(*) as total_records
FROM `PROJECT_ID.billing_export.gcp_billing_export_v1_BILLING_ACCOUNT_ID`;
```

## 🎯 SpaceONE 플러그인 연동 설정

### 설정 완료 후 플러그인 연동

```yaml
# register_datasource.yaml 예시
name: "google-cloud-billing-bigquery"
plugin_info:
  plugin_id: "plugin-google-billing-cost-datasource"
  version: "1.0.0"
template:
  options:
    # 위에서 설정한 정보 사용
    project_id: "your-billing-project"        # 2단계에서 설정한 프로젝트
    dataset_id: "billing_export"              # 3단계에서 생성한 데이터셋
    table_id: "gcp_billing_export_v1_XXXXXX"  # 자동 생성된 테이블
    
    # 데이터 유형 설정
    enable_detailed_usage: true               # 상세 사용량 데이터 사용
    enable_standard_usage: true               # 표준 사용량 데이터 사용
    
    # 인증 정보 (서비스 계정 키)
    service_account_json_key: |
      {
        "type": "service_account",
        "project_id": "your-billing-project",
        "private_key_id": "...",
        "private_key": "-----BEGIN PRIVATE KEY-----\n...",
        "client_email": "billing-reader@your-billing-project.iam.gserviceaccount.com"
      }

secret_data:
  # 민감한 인증 정보는 secret_data에 분리
  type: "service_account"
  project_id: "your-billing-project"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "billing-reader@your-billing-project.iam.gserviceaccount.com"
```

### 플러그인용 서비스 계정 생성

```bash
# 플러그인 전용 서비스 계정 생성
gcloud iam service-accounts create spaceone-billing-reader \
  --display-name="SpaceONE Billing Reader"

# BigQuery 읽기 권한 부여
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:spaceone-billing-reader@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:spaceone-billing-reader@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# 서비스 계정 키 생성
gcloud iam service-accounts keys create spaceone-billing-key.json \
  --iam-account=spaceone-billing-reader@PROJECT_ID.iam.gserviceaccount.com
```

## 📊 설정 완료 후 데이터 확인

### 기본 데이터 확인 쿼리

```sql
-- 테이블 정보 및 최신 데이터 확인
SELECT
  table_name,
  row_count,
  size_bytes,
  TIMESTAMP_MILLIS(last_modified_time) as last_modified
FROM `PROJECT_ID.billing_export.__TABLES__`
WHERE table_id LIKE 'gcp_billing_export%';

-- 최근 7일간 비용 추이
SELECT
  DATE(usage_start_time) as usage_date,
  SUM(cost) as daily_cost,
  COUNT(*) as record_count
FROM `PROJECT_ID.billing_export.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY usage_date
ORDER BY usage_date DESC;
```

## 🔗 관련 리소스

### Google Cloud 공식 문서
- **[BigQuery로 Cloud Billing 데이터 내보내기 개요](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko)**
- **[BigQuery의 Cloud Billing 데이터 테이블 이해](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables?hl=ko)**
- **[Cloud Billing BigQuery 쿼리 예시](https://cloud.google.com/billing/docs/how-to/bq-examples?hl=ko)**
- **[BigQuery Data Transfer Service API](https://cloud.google.com/bigquery/docs/reference/datatransfer/rest)**

### 프로젝트 내 관련 문서
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - 개요 및 활용 가이드
- **[📊 데이터 분석 가이드](./data-analysis-guide.md)** - BigQuery 스키마 및 쿼리 분석
- **[💰 Pricing Data Export 가이드](./pricing-data-export-guide.md)** - 가격 데이터 분석
- **[🔧 통합 가이드](./integration-guide.md)** - SpaceONE 연동 설정

---

> **💡 팁**: 설정이 완료된 후 첫 번째 데이터가 나타나는 데 최대 24시간이 걸릴 수 있습니다. 다중 지역 데이터셋을 사용하면 이전 달의 데이터도 소급 적용되어 더 포괄적인 분석이 가능합니다.
