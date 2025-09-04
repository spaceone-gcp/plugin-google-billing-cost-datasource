# Google Cloud Billing Pricing Data Export 가이드

이 문서는 Google Cloud Billing의 Pricing Data Export 기능을 상세히 설명하고, 이를 활용한 고급 비용 분석 방법을 안내합니다.

## 📋 개요

**Pricing Data Export**는 Google Cloud의 모든 서비스와 SKU(Stock Keeping Unit)에 대한 정가 정보를 BigQuery로 내보내는 기능입니다. 이를 통해 실제 청구 데이터와 별도로 가격 정보를 분석하고, 비용 최적화를 위한 인사이트를 얻을 수 있습니다.

## 🆚 Billing Data Export vs Pricing Data Export

| 구분 | Billing Data Export | Pricing Data Export |
|:---|:---|:---|
| **데이터 유형** | 실제 사용량 및 청구 데이터 | 서비스별 정가 정보 |
| **테이블명** | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | `cloud_pricing_export` |
| **업데이트 주기** | 일 1-2회 (사용량 기반) | 일 1회 (가격 변동 시) |
| **데이터 범위** | 특정 청구 계정의 실제 비용 | 모든 GCP 서비스의 공개 정가 |
| **주요 용도** | 실제 비용 추적 및 분석 | 가격 비교 및 예산 계획 |

## 🔧 Pricing Data Export 설정

### 1. 내보내기 활성화

1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동
2. **Pricing 내보내기** 탭 선택
3. 다음 정보를 입력:
   - **프로젝트 ID**: BigQuery 데이터셋을 생성할 프로젝트
   - **데이터셋 ID**: `pricing_export` (권장)

### 2. 생성되는 테이블

```
프로젝트ID.데이터셋ID.cloud_pricing_export
```

**예시**: `my-project.pricing_export.cloud_pricing_export`

### 3. 권한 설정

Pricing Data Export를 사용하는 서비스 계정에 다음 역할을 부여:

- `BigQuery Data Viewer`: 데이터 읽기 권한
- `BigQuery Job User`: 쿼리 실행 권한

## 📊 Pricing Data 스키마

### 주요 필드 설명

| 필드명 | 타입 | 설명 |
|:---|:---|:---|
| `export_time` | Timestamp | 데이터 내보내기 처리 시간 |
| `pricing_as_of_time` | Timestamp | 가격 데이터 생성 일시 |
| `billing_account_id` | String | 청구 계정 ID |
| `service.id` | String | Google Cloud 서비스 ID |
| `service.description` | String | 서비스 설명 |
| `sku.id` | String | SKU(Stock Keeping Unit) ID |
| `sku.description` | String | SKU 설명 |
| `product_taxonomy` | Record | 제품 분류 정보 (베타) |
| `geo_taxonomy` | Record | 지역 분류 정보 (베타) |
| `list_price` | Record | 공개 정가 정보 |
| `billing_account_price` | Record | 청구 계정별 할인 적용 가격 |

### 가격 정보 구조

#### `list_price` 필드
```json
{
  "aggregation_info": {
    "aggregation_level": "ACCOUNT",
    "aggregation_interval": "MONTHLY"
  },
  "tiered_rates": [
    {
      "pricing_unit_quantity": 1000000,
      "start_usage_amount": 0,
      "usd_amount": 0.0,
      "account_currency_amount": 0.0
    },
    {
      "pricing_unit_quantity": 1000000,
      "start_usage_amount": 2000000,
      "usd_amount": 0.4,
      "account_currency_amount": 0.4
    }
  ]
}
```

#### 계층별 요금제 (Tiered Pricing)
- **`pricing_unit_quantity`**: 가격 책정 단위 수량
- **`start_usage_amount`**: 해당 계층 시작 사용량
- **`usd_amount`**: USD 기준 단위 가격
- **`account_currency_amount`**: 청구 계정 통화 기준 단위 가격

## 🔍 활용 사례별 쿼리 예시

### 1. 기본 가격 정보 조회

```sql
-- 특정 서비스의 모든 SKU 가격 조회
SELECT 
  sku.id AS sku_id,
  sku.description AS sku_description,
  service.description AS service_description,
  list_price.tiered_rates
FROM `project.dataset.cloud_pricing_export`
WHERE DATE(_PARTITIONTIME) = "2024-01-15"
  AND service.description = "Compute Engine"
ORDER BY sku.description;
```

### 2. 계층별 요금제 분석

```sql
-- Cloud Run 요청 가격의 계층별 요금제 분석
SELECT 
  sku.id AS sku_id,
  sku.description AS sku_description,
  tier.pricing_unit_quantity,
  tier.start_usage_amount,
  tier.usd_amount,
  tier.account_currency_amount
FROM `project.dataset.cloud_pricing_export` as pricing, 
     UNNEST(pricing.list_price.tiered_rates) as tier
WHERE DATE(_PARTITIONTIME) = "2024-01-15"
  AND sku.id = "2DA5-55D3-E679"  -- Cloud Run Requests
ORDER BY tier.start_usage_amount;
```

### 3. 지역별 가격 비교

```sql
-- Compute Engine 인스턴스의 지역별 가격 비교
SELECT 
  geo_taxonomy.region,
  sku.description,
  tier.usd_amount,
  tier.pricing_unit_quantity
FROM `project.dataset.cloud_pricing_export` as pricing,
     UNNEST(pricing.list_price.tiered_rates) as tier
WHERE DATE(_PARTITIONTIME) = "2024-01-15"
  AND service.description = "Compute Engine"
  AND sku.description LIKE "%Instance Core%"
  AND tier.start_usage_amount = 0
ORDER BY geo_taxonomy.region, tier.usd_amount;
```

### 4. 가격 변동 추적

```sql
-- 특정 SKU의 가격 변동 이력 추적
SELECT 
  DATE(_PARTITIONTIME) as price_date,
  sku.description,
  tier.usd_amount,
  tier.start_usage_amount
FROM `project.dataset.cloud_pricing_export` as pricing,
     UNNEST(pricing.list_price.tiered_rates) as tier
WHERE sku.id = "6F81-5844-456A"  -- 특정 SKU
  AND tier.start_usage_amount = 0
ORDER BY price_date DESC
LIMIT 30;
```

## 🎯 SpaceONE 플러그인과의 연계 활용

### 1. 실제 비용 vs 정가 비교

Pricing Data Export와 현재 플러그인의 Billing Data Export를 결합하여 할인율을 분석할 수 있습니다:

```sql
-- 실제 비용과 정가 비교를 통한 할인율 계산
WITH billing_data AS (
  SELECT 
    service.description,
    sku.description,
    SUM(cost) as actual_cost,
    SUM(usage.amount_in_pricing_units) as usage_amount
  FROM `project.billing_export.gcp_billing_export_v1_ACCOUNT_ID`
  WHERE DATE(usage_start_time) = "2024-01-15"
  GROUP BY 1, 2
),
pricing_data AS (
  SELECT 
    service.description,
    sku.description,
    tier.usd_amount as list_price_per_unit
  FROM `project.pricing_export.cloud_pricing_export` as pricing,
       UNNEST(pricing.list_price.tiered_rates) as tier
  WHERE DATE(_PARTITIONTIME) = "2024-01-15"
    AND tier.start_usage_amount = 0
)
SELECT 
  b.service_description,
  b.sku_description,
  b.actual_cost,
  (b.usage_amount * p.list_price_per_unit) as list_price_cost,
  ROUND((1 - b.actual_cost / (b.usage_amount * p.list_price_per_unit)) * 100, 2) as discount_percentage
FROM billing_data b
JOIN pricing_data p 
  ON b.service_description = p.service_description 
  AND b.sku_description = p.sku_description
WHERE (b.usage_amount * p.list_price_per_unit) > 0
ORDER BY discount_percentage DESC;
```

### 2. 예산 계획을 위한 가격 예측

```sql
-- 사용량 증가 시나리오별 예상 비용 계산
SELECT 
  service.description,
  sku.description,
  -- 현재 사용량 기준
  1000 as current_usage,
  tier.usd_amount * 1000 as current_cost,
  -- 2배 증가 시나리오
  tier.usd_amount * 2000 as doubled_cost,
  -- 10배 증가 시나리오  
  tier.usd_amount * 10000 as ten_times_cost
FROM `project.dataset.cloud_pricing_export` as pricing,
     UNNEST(pricing.list_price.tiered_rates) as tier
WHERE DATE(_PARTITIONTIME) = "2024-01-15"
  AND service.description IN ("Compute Engine", "Cloud Storage", "BigQuery")
  AND tier.start_usage_amount = 0
ORDER BY current_cost DESC;
```

## ⚠️ 현재 플러그인 구현 상태 분석

### 지원되지 않는 기능

현재 SpaceONE 플러그인은 **Pricing Data Export를 지원하지 않습니다**. 다음과 같은 제한사항이 있습니다:

1. **테이블 지원 부재**: `cloud_pricing_export` 테이블 처리 로직 없음
2. **가격 분석 기능 없음**: 정가 vs 실제 비용 비교 기능 부재
3. **할인율 계산 없음**: 자동 할인율 분석 기능 부재

### 구현 권장사항

#### 1. Pricing Data 커넥터 추가
```python
# src/plugin/connector/pricing_connector.py (신규)
class PricingConnector(BaseConnector):
    def get_pricing_data(self, service_id: str, sku_id: str) -> dict:
        """특정 서비스/SKU의 가격 정보 조회"""
        pass
    
    def compare_pricing_vs_billing(self, billing_data: dict) -> dict:
        """실제 비용과 정가 비교 분석"""
        pass
```

#### 2. 가격 분석 매니저 추가
```python
# src/plugin/manager/pricing_manager.py (신규)
class PricingManager(BaseManager):
    def analyze_discount_rates(self) -> dict:
        """할인율 분석"""
        pass
    
    def forecast_costs(self, usage_scenarios: list) -> dict:
        """사용량 시나리오별 비용 예측"""
        pass
```

#### 3. 설정 옵션 확장
```yaml
# register_datasource.yaml 확장
options:
  # 기존 설정...
  enable_pricing_analysis: true          # 가격 분석 활성화
  pricing_export_project_id: "project"   # Pricing Export 프로젝트
  pricing_dataset_id: "pricing_export"   # Pricing Export 데이터셋
```

## 🔗 관련 리소스

### Google Cloud 공식 문서
- **[Pricing Data Export 설정 가이드](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data)**
- **[Pricing Data 스키마 상세](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data#schema)**
- **[BigQuery 쿼리 예시](https://cloud.google.com/billing/docs/how-to/bq-examples)**

### 프로젝트 내 관련 문서
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - 내보내기 설정 및 연동 가이드
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드
- **[📊 BigQuery의 Cloud Billing 데이터 테이블 이해하기](./BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - 테이블 구조 개요
- **[💰 가격 책정 데이터 내보내기의 구조](./가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 데이터 상세 스키마
- **[🔍 Cloud Billing 데이터 내보내기의 쿼리 예시](./Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - 실용적인 쿼리 모음
- **[Billing Export 설정 가이드](./billing-export-setup.md)**
- **[데이터 분석 가이드](./data-analysis-guide.md)**
- **[통합 가이드](./integration-guide.md)**

---

> **다음 단계**: Pricing Data Export 기능을 현재 플러그인에 통합하려면 [개발 로드맵](../development/implementation-roadmap.md)을 참고하여 단계별 구현을 진행하세요.
