# Cloud Billing 데이터를 BigQuery로 내보내기

이 문서는 Google Cloud의 공식 [Cloud Billing 데이터를 BigQuery로 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko) 가이드를 기반으로, SpaceONE 플러그인 사용자를 위한 상세한 설정 및 활용 방법을 안내합니다.

## 📋 개요

**Cloud Billing 데이터를 BigQuery로 내보내기**는 Google Cloud의 상세한 청구 데이터를 자동으로 BigQuery 데이터셋으로 일일 내보내기하는 기능입니다. 이를 통해 사용량, 비용 예상치, 가격 데이터를 포함한 포괄적인 분석과 시각화가 가능합니다.

### 주요 이점

- **자동화된 데이터 수집**: 매일 자동으로 최신 청구 데이터를 BigQuery로 내보내기
- **상세한 분석 가능**: 리소스 수준까지의 세밀한 비용 분석
- **다양한 데이터 유형**: 표준 사용량, 상세 사용량, 리빌링, 가격 데이터 지원
- **재무 관리 지원**: 비용 추세 분석 및 예산 관리 최적화

## 🎯 내보내기 데이터 유형

Google Cloud Billing Export는 다음과 같은 데이터 유형을 제공합니다:

### 1. 표준 사용량 비용 데이터 (Standard Usage Cost Data)
- **테이블명**: `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`
- **용도**: 기본적인 사용량 및 비용 데이터
- **세분화 수준**: 계정, 프로젝트, 서비스, SKU 수준

### 2. 상세 사용량 비용 데이터 (Detailed Usage Cost Data)
- **테이블명**: `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>`
- **용도**: 개별 리소스 수준까지의 상세 분석
- **추가 정보**: 리소스 이름, 글로벌 이름, 상세 라벨 및 태그

### 3. 리빌링 데이터 (Rebilling Data)
- **대상**: 리셀러 계정
- **용도**: 고객별 청구 관리

### 4. 가격 데이터 (Pricing Data)
- **테이블명**: `cloud_pricing_export`
- **용도**: Google Cloud 서비스별 정가 정보 분석

> **💡 권장사항**: **상세 사용량 비용 데이터**를 활성화하면 표준 데이터의 모든 기능을 포함하면서도 리소스 수준의 세밀한 분석이 가능합니다.

## ⚙️ 설정 방법

### 1. Cloud Billing 계정에서 내보내기 활성화

1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동
2. **BigQuery 내보내기** 탭 선택
3. 다음 정보를 입력:
   - **프로젝트 ID**: BigQuery 데이터셋을 생성할 프로젝트
   - **데이터셋 ID**: 데이터를 저장할 데이터셋 이름 (예: `billing_export`)
   - **내보내기 유형**: 
     - ✅ **표준 사용량 비용 데이터** (기본)
     - ✅ **상세 사용량 비용 데이터** (권장)
     - ✅ **가격 데이터** (선택사항)

### 2. BigQuery 데이터셋 생성 및 권한 설정

#### 데이터셋 생성
```bash
# BigQuery CLI를 사용한 데이터셋 생성
bq mk --location=US --dataset PROJECT_ID:billing_export
```

#### 필요 권한
Cloud Billing 내보내기를 위해 다음 서비스 계정에 권한을 부여해야 합니다:

- **서비스 계정**: `billing-export-bigquery@system.gserviceaccount.com`
- **필요 권한**: 
  - `BigQuery Data Editor` 역할
  - `BigQuery Job User` 역할

```bash
# 권한 부여 예시
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:billing-export-bigquery@system.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

### 3. 다중 지역 데이터셋 고려사항

#### 지원되는 데이터셋 위치
- **다중 지역**: `US`, `EU`
- **단일 지역**: 대부분의 BigQuery 지역 지원

#### 데이터 소급 적용 (Backfill)
- **다중 지역 데이터셋**: 이전 달 데이터부터 소급 적용
- **지역별 데이터셋**: 내보내기 활성화 날짜부터만 데이터 포함

> **⚠️ 중요**: 포괄적인 데이터 수집을 위해 **Cloud Billing 계정 생성 시** 내보내기를 활성화하는 것을 권장합니다.

## 🔧 SpaceONE 플러그인 연동 설정

### 1. 데이터소스 등록 설정

```yaml
# register_datasource.yaml 예시
name: "google-cloud-billing-bigquery"
plugin_info:
  plugin_id: "plugin-google-billing-cost-datasource"
  version: "1.0.0"
template:
  options:
    # BigQuery 연결 정보
    project_id: "your-billing-project"           # BigQuery 프로젝트 ID
    dataset_id: "billing_export"                 # 내보내기 데이터셋 ID
    table_id: "gcp_billing_export_v1_XXXXXX"    # 테이블 ID
    
    # 인증 정보
    service_account_json_key: |
      {
        "type": "service_account",
        "project_id": "your-project",
        ...
      }
    
    # 데이터 처리 옵션
    enable_detailed_usage: true                   # 상세 사용량 데이터 사용
    enable_pricing_analysis: false               # 가격 데이터 분석 (향후 지원 예정)
    
    # 비용 집계 기준
    cost_aggregation_method: "usage_date"        # usage_date | invoice_month
    
    # 필터링 옵션
    exclude_zero_cost_items: true                # 비용이 0인 항목 제외
    include_credits: true                        # 크레딧 정보 포함
```

### 2. 필드 매핑 설정

플러그인은 BigQuery 스키마를 SpaceONE 비용 데이터 모델로 자동 변환합니다:

```python
# 주요 필드 매핑
FIELD_MAPPING = {
    # 기본 식별 정보
    "billing_account_id": "account_id",
    "project.id": "project_id",
    "project.name": "project_name",
    
    # 서비스 및 리소스 정보
    "service.description": "service_name",
    "sku.description": "resource_type",
    "resource.name": "resource_id",           # 상세 데이터만
    
    # 비용 정보
    "cost": "billed_cost",                    # 최종 청구 금액
    "cost_at_list": "list_cost",             # 정가
    "currency": "currency",
    
    # 시간 정보
    "usage_start_time": "usage_start_time",
    "usage_end_time": "usage_end_time",
    "invoice.month": "invoice_month",
    
    # 위치 및 분류
    "location.region": "region",
    "labels": "tags",                         # 리소스 라벨
    "project.labels": "project_tags",         # 프로젝트 라벨
}
```

## 📊 데이터 활용 및 분석

### 1. 기본 비용 분석

```sql
-- 월별 총 비용 추이
SELECT
  FORMAT_DATE('%Y-%m', DATE(usage_start_time)) as month,
  SUM(cost) as total_cost,
  SUM(cost_at_list) as list_cost,
  ROUND((1 - SUM(cost) / NULLIF(SUM(cost_at_list), 0)) * 100, 2) as discount_rate
FROM `project.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE cost > 0
GROUP BY month
ORDER BY month DESC;
```

### 2. 서비스별 비용 분석

```sql
-- 상위 10개 서비스별 월간 비용
SELECT
  service.description as service_name,
  SUM(cost) as total_cost,
  COUNT(DISTINCT project.id) as project_count,
  AVG(cost) as avg_cost_per_item
FROM `project.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY service_name
ORDER BY total_cost DESC
LIMIT 10;
```

### 3. 프로젝트별 라벨 기반 분석

```sql
-- 환경별(dev/staging/prod) 비용 분석
SELECT
  (SELECT value FROM UNNEST(project.labels) WHERE key = 'environment') as environment,
  (SELECT value FROM UNNEST(project.labels) WHERE key = 'team') as team,
  SUM(cost) as total_cost,
  COUNT(DISTINCT project.id) as project_count
FROM `project.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY environment, team
ORDER BY total_cost DESC;
```

### 4. 크레딧 및 할인 분석

```sql
-- 크레딧 유형별 할인 효과 분석
SELECT
  FORMAT_DATE('%Y-%m', DATE(usage_start_time)) as month,
  c.type as credit_type,
  c.name as credit_name,
  SUM(c.amount) as total_credit_amount,
  COUNT(*) as credit_applications
FROM `project.billing_export.gcp_billing_export_v1_XXXXXX`,
     UNNEST(credits) as c
WHERE c.amount < 0  -- 크레딧은 음수로 표시
GROUP BY month, credit_type, credit_name
ORDER BY month DESC, total_credit_amount ASC;
```

## ⚠️ 제한사항 및 고려사항

### 1. 데이터셋 위치 제한
- 지원되는 위치에서만 내보내기 가능
- 고객 관리 암호화 키(CMEK) 사용 불가

### 2. 리소스 수준 태그 전파 지연
- 태그 변경 사항이 BigQuery 내보내기에 반영되는 데 **최대 1시간** 소요
- 1시간 미만 존재한 리소스의 태그는 누락될 수 있음

#### 태그 지원 리소스
- Compute Engine 인스턴스
- Spanner 인스턴스  
- Cloud Run 서비스
- Artifact Registry 저장소

### 3. VPC 서비스 제어
VPC 서비스 제어를 사용하는 경우 BigQuery 내보내기가 차단될 수 있습니다. 이 경우 수동으로 VPC를 제외해야 합니다.

### 4. 행 수준 액세스 정책
행 수준 보안을 사용하는 경우, Cloud Billing 서비스 계정에 적절한 액세스 권한을 부여해야 합니다:

```sql
-- 행 수준 액세스 정책 생성 예시
CREATE ROW ACCESS POLICY cloud_billing_export_policy
ON `project_id.dataset_id.table_id`
GRANT TO ('serviceAccount:billing-export-bigquery@system.gserviceaccount.com')
FILTER USING (TRUE);
```

## 🔄 데이터 업데이트 주기 및 지연시간

### 업데이트 주기
- **일반적인 업데이트**: 하루 1-2회
- **업데이트 시간**: 보통 UTC 기준 오전 중
- **데이터 지연**: 실제 사용 시점으로부터 6-24시간

### 데이터 완성도
- **당일 데이터**: 부분적으로만 제공될 수 있음
- **전날 데이터**: 일반적으로 완전한 데이터 제공
- **월말 조정**: 월 초에 이전 달 데이터의 최종 조정 발생 가능

## 📈 고급 활용 사례

### 1. 비용 이상 탐지
```sql
-- 일일 비용 증가율이 50% 이상인 프로젝트 탐지
WITH daily_costs AS (
  SELECT
    project.id as project_id,
    DATE(usage_start_time) as usage_date,
    SUM(cost) as daily_cost
  FROM `project.billing_export.gcp_billing_export_v1_XXXXXX`
  WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY project_id, usage_date
),
cost_changes AS (
  SELECT
    project_id,
    usage_date,
    daily_cost,
    LAG(daily_cost) OVER (PARTITION BY project_id ORDER BY usage_date) as prev_daily_cost,
    SAFE_DIVIDE(daily_cost - LAG(daily_cost) OVER (PARTITION BY project_id ORDER BY usage_date), 
                LAG(daily_cost) OVER (PARTITION BY project_id ORDER BY usage_date)) * 100 as cost_change_pct
  FROM daily_costs
)
SELECT *
FROM cost_changes
WHERE cost_change_pct > 50 AND prev_daily_cost > 10  -- $10 이상에서 50% 증가
ORDER BY cost_change_pct DESC;
```

### 2. 리소스 효율성 분석
```sql
-- 사용률 대비 비용 효율성이 낮은 Compute Engine 인스턴스 식별
SELECT
  resource.name as instance_name,
  project.id as project_id,
  SUM(cost) as total_cost,
  AVG(usage.amount) as avg_usage,
  SAFE_DIVIDE(SUM(cost), AVG(NULLIF(usage.amount, 0))) as cost_per_usage_unit
FROM `project.billing_export.gcp_billing_export_resource_v1_XXXXXX`
WHERE service.description = 'Compute Engine'
  AND sku.description LIKE '%Instance%'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY instance_name, project_id
HAVING avg_usage > 0
ORDER BY cost_per_usage_unit DESC
LIMIT 20;
```

## 🔗 관련 리소스

### Google Cloud 공식 문서
- **[BigQuery로 Cloud Billing 데이터 내보내기 설정](https://cloud.google.com/billing/docs/how-to/export-data-bigquery#enable-billing-export)**
- **[표준 사용량 데이터 스키마](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage?hl=ko)**
- **[상세 사용량 데이터 스키마](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage?hl=ko)**
- **[Cloud Billing BigQuery 쿼리 예시](https://cloud.google.com/billing/docs/how-to/bq-examples)**

### 프로젝트 내 관련 문서
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드
- **[📊 데이터 분석 가이드](./data-analysis-guide.md)** - BigQuery 스키마 상세 분석
- **[📋 상세 사용량 데이터 활용 가이드](./detailed-usage-export-guide.md)** - 리소스 수준 분석
- **[💰 Pricing Data Export 가이드](./pricing-data-export-guide.md)** - 가격 정보 분석
- **[🎯 크레딧 및 할인 분석](./credits-and-discounts-analysis.md)** - 할인 효과 분석
- **[🔧 통합 가이드](./integration-guide.md)** - SpaceONE 연동 설정

---

> **💡 팁**: Cloud Billing 데이터 내보내기를 활성화한 후, 첫 번째 데이터가 BigQuery에 나타나는 데 최대 24시간이 걸릴 수 있습니다. 설정 후 하루 정도 기다린 후 데이터 확인을 권장합니다.
