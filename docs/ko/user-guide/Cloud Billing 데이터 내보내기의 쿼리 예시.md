# Cloud Billing 데이터 내보내기의 쿼리 예시

이 문서는 Google Cloud의 공식 [Cloud Billing 쿼리 예시](https://cloud.google.com/billing/docs/how-to/bq-examples?hl=ko) 가이드를 기반으로, BigQuery에서 Cloud Billing 데이터를 효과적으로 분석하기 위한 실용적인 쿼리 예시를 제공합니다.

## 📋 개요

Cloud Billing 데이터를 BigQuery로 내보낸 후, 다양한 관점에서 비용을 분석하고 인사이트를 도출할 수 있습니다. 이 가이드는 실무에서 자주 사용되는 쿼리 패턴과 고급 분석 기법을 제공합니다.

### 사전 준비사항
- BigQuery로 Cloud Billing 데이터 내보내기 설정 완료
- 적절한 BigQuery 권한 (BigQuery User 이상)
- 쿼리에서 사용할 테이블명 확인

## 🔍 기본 쿼리 패턴

### 쿼리 작성 시 주의사항

```sql
-- ✅ 좋은 예: 파티션 필터 사용
SELECT service.description, SUM(cost)
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) = '2024-01-15'  -- 파티션 필터
GROUP BY 1;

-- ❌ 나쁜 예: 파티션 필터 없음
SELECT service.description, SUM(cost)
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE cost > 100;  -- 전체 테이블 스캔
```

## 📊 기본 비용 분석 쿼리

### 1. 월별 총 비용 조회

```sql
-- 최근 6개월간 월별 총 비용
SELECT
  FORMAT_DATE('%Y-%m', DATE(usage_start_time)) as billing_month,
  SUM(cost) as total_cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) as total_credits,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) as net_cost
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 6 MONTH)
GROUP BY
  billing_month
ORDER BY
  billing_month DESC;
```

### 2. 서비스별 비용 분석

```sql
-- 서비스별 월간 비용 및 비중
SELECT
  service.description as service_name,
  SUM(cost) as total_cost,
  ROUND(SUM(cost) / SUM(SUM(cost)) OVER() * 100, 2) as cost_percentage,
  COUNT(DISTINCT project.id) as project_count
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0
GROUP BY
  service_name
ORDER BY
  total_cost DESC;
```

### 3. 프로젝트별 비용 분석

```sql
-- 프로젝트별 비용 및 성장률
WITH monthly_project_costs AS (
  SELECT
    project.id as project_id,
    project.name as project_name,
    FORMAT_DATE('%Y-%m', DATE(usage_start_time)) as month,
    SUM(cost) as monthly_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 3 MONTH)
  GROUP BY
    project_id, project_name, month
)
SELECT
  project_id,
  project_name,
  month,
  monthly_cost,
  LAG(monthly_cost) OVER (PARTITION BY project_id ORDER BY month) as prev_month_cost,
  ROUND((monthly_cost - LAG(monthly_cost) OVER (PARTITION BY project_id ORDER BY month)) / 
        NULLIF(LAG(monthly_cost) OVER (PARTITION BY project_id ORDER BY month), 0) * 100, 2) as growth_rate_pct
FROM
  monthly_project_costs
ORDER BY
  project_id, month DESC;
```

## 🏷️ 라벨 기반 비용 분석

### 4. 환경별 비용 분석 (라벨 기반)

```sql
-- 환경(dev/staging/prod)별 비용 분석
SELECT
  (SELECT value FROM UNNEST(project.labels) WHERE key = 'environment') as environment,
  (SELECT value FROM UNNEST(project.labels) WHERE key = 'team') as team,
  service.description as service_name,
  SUM(cost) as total_cost,
  COUNT(DISTINCT project.id) as project_count
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0
GROUP BY
  environment, team, service_name
HAVING
  environment IS NOT NULL
ORDER BY
  environment, total_cost DESC;
```

### 5. 비용 센터별 할당 분석

```sql
-- 비용 센터별 비용 할당 및 예산 대비 분석
WITH cost_center_allocation AS (
  SELECT
    (SELECT value FROM UNNEST(labels) WHERE key = 'cost-center') as cost_center,
    (SELECT value FROM UNNEST(labels) WHERE key = 'application') as application,
    service.description,
    SUM(cost) as allocated_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND cost > 0
  GROUP BY
    cost_center, application, service.description
)
SELECT
  cost_center,
  SUM(allocated_cost) as total_allocated_cost,
  COUNT(DISTINCT application) as application_count,
  -- 가상의 예산과 비교 (실제로는 별도 테이블에서 조인)
  CASE 
    WHEN cost_center = 'ENGINEERING' THEN 10000
    WHEN cost_center = 'MARKETING' THEN 5000
    ELSE 3000
  END as monthly_budget,
  ROUND(SUM(allocated_cost) / 
    CASE 
      WHEN cost_center = 'ENGINEERING' THEN 10000
      WHEN cost_center = 'MARKETING' THEN 5000
      ELSE 3000
    END * 100, 2) as budget_utilization_pct
FROM
  cost_center_allocation
WHERE
  cost_center IS NOT NULL
GROUP BY
  cost_center
ORDER BY
  total_allocated_cost DESC;
```

## 💰 크레딧 및 할인 분석

### 6. 크레딧 유형별 절약 분석

```sql
-- 크레딧 유형별 절약 효과 분석
SELECT
  c.type as credit_type,
  c.name as credit_name,
  COUNT(*) as applications,
  SUM(c.amount) as total_credit_amount,
  COUNT(DISTINCT project.id) as benefited_projects,
  AVG(c.amount) as avg_credit_amount
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`,
  UNNEST(credits) as c
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND c.amount < 0  -- 크레딧은 음수
GROUP BY
  credit_type, credit_name
ORDER BY
  total_credit_amount ASC;  -- 음수이므로 ASC가 큰 절약
```

### 7. 할인율 분석

```sql
-- 서비스별 유효 할인율 분석
SELECT
  service.description as service_name,
  SUM(cost_at_list) as total_list_cost,
  SUM(cost) as total_actual_cost,
  SUM(cost_at_list) - SUM(cost) as total_discount,
  ROUND((1 - SUM(cost) / NULLIF(SUM(cost_at_list), 0)) * 100, 2) as effective_discount_pct,
  COUNT(DISTINCT project.id) as project_count
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost_at_list > 0
GROUP BY
  service_name
HAVING
  total_list_cost > 100  -- $100 이상인 서비스만
ORDER BY
  effective_discount_pct DESC;
```

## 📍 지역별 비용 분석

### 8. 리전별 비용 분포

```sql
-- 리전별 비용 분포 및 서비스 분석
SELECT
  location.region,
  location.country,
  service.description as service_name,
  SUM(cost) as total_cost,
  COUNT(DISTINCT project.id) as project_count,
  ROUND(SUM(cost) / SUM(SUM(cost)) OVER() * 100, 2) as cost_percentage
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0
  AND location.region IS NOT NULL
GROUP BY
  location.region, location.country, service_name
ORDER BY
  total_cost DESC;
```

### 9. 다중 리전 서비스 비용 비교

```sql
-- 다중 리전에서 동일 서비스 비용 비교
WITH regional_service_costs AS (
  SELECT
    location.region,
    service.description,
    sku.description,
    SUM(cost) as total_cost,
    SUM(usage.amount) as total_usage,
    SAFE_DIVIDE(SUM(cost), SUM(usage.amount)) as cost_per_unit
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND service.description = 'Compute Engine'
    AND sku.description LIKE '%Instance Core%'
    AND location.region IS NOT NULL
    AND usage.amount > 0
  GROUP BY
    location.region, service.description, sku.description
)
SELECT
  region,
  sku.description,
  total_cost,
  total_usage,
  cost_per_unit,
  cost_per_unit - MIN(cost_per_unit) OVER (PARTITION BY sku.description) as cost_premium,
  ROUND((cost_per_unit - MIN(cost_per_unit) OVER (PARTITION BY sku.description)) / 
        MIN(cost_per_unit) OVER (PARTITION BY sku.description) * 100, 2) as premium_pct
FROM
  regional_service_costs
ORDER BY
  sku.description, cost_per_unit;
```

## 📈 시간 기반 분석

### 10. 시간대별 사용 패턴 분석

```sql
-- 시간대별 Compute Engine 사용 패턴
SELECT
  EXTRACT(HOUR FROM usage_start_time) as hour_of_day,
  EXTRACT(DAYOFWEEK FROM usage_start_time) as day_of_week,
  CASE EXTRACT(DAYOFWEEK FROM usage_start_time)
    WHEN 1 THEN 'Sunday'
    WHEN 2 THEN 'Monday'
    WHEN 3 THEN 'Tuesday'
    WHEN 4 THEN 'Wednesday'
    WHEN 5 THEN 'Thursday'
    WHEN 6 THEN 'Friday'
    WHEN 7 THEN 'Saturday'
  END as day_name,
  SUM(cost) as hourly_cost,
  SUM(usage.amount) as hourly_usage,
  COUNT(DISTINCT project.id) as active_projects
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND service.description = 'Compute Engine'
  AND sku.description LIKE '%Instance Core%'
GROUP BY
  hour_of_day, day_of_week, day_name
ORDER BY
  day_of_week, hour_of_day;
```

### 11. 주말 vs 평일 비용 분석

```sql
-- 주말 vs 평일 비용 패턴 분석
SELECT
  CASE 
    WHEN EXTRACT(DAYOFWEEK FROM usage_start_time) IN (1, 7) THEN 'Weekend'
    ELSE 'Weekday'
  END as day_type,
  service.description as service_name,
  SUM(cost) as total_cost,
  COUNT(DISTINCT DATE(usage_start_time)) as days,
  ROUND(SUM(cost) / COUNT(DISTINCT DATE(usage_start_time)), 2) as avg_daily_cost,
  COUNT(DISTINCT project.id) as active_projects
FROM
  `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE
  DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND cost > 0
GROUP BY
  day_type, service_name
ORDER BY
  service_name, day_type;
```

## 🚨 비용 이상 탐지

### 12. 일일 비용 급증 탐지

```sql
-- 일일 비용 급증 탐지 (평균 대비 2배 이상)
WITH daily_costs AS (
  SELECT
    DATE(usage_start_time) as usage_date,
    project.id as project_id,
    service.description as service_name,
    SUM(cost) as daily_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  GROUP BY
    usage_date, project_id, service_name
),
cost_with_baseline AS (
  SELECT
    *,
    AVG(daily_cost) OVER (
      PARTITION BY project_id, service_name 
      ORDER BY usage_date 
      ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING
    ) as avg_cost_7days
  FROM
    daily_costs
)
SELECT
  usage_date,
  project_id,
  service_name,
  daily_cost,
  avg_cost_7days,
  daily_cost - avg_cost_7days as cost_spike,
  ROUND((daily_cost - avg_cost_7days) / NULLIF(avg_cost_7days, 0) * 100, 2) as spike_percentage
FROM
  cost_with_baseline
WHERE
  daily_cost > avg_cost_7days * 2  -- 평균의 2배 이상
  AND avg_cost_7days > 10  -- 기준 금액 이상
  AND usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
ORDER BY
  spike_percentage DESC;
```

### 13. 신규 서비스 사용 탐지

```sql
-- 새롭게 사용되기 시작한 서비스 탐지
WITH service_usage_history AS (
  SELECT
    project.id as project_id,
    service.description as service_name,
    MIN(DATE(usage_start_time)) as first_usage_date,
    MAX(DATE(usage_start_time)) as last_usage_date,
    SUM(cost) as total_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND cost > 0
  GROUP BY
    project_id, service_name
)
SELECT
  project_id,
  service_name,
  first_usage_date,
  total_cost,
  DATE_DIFF(CURRENT_DATE(), first_usage_date, DAY) as days_since_first_use
FROM
  service_usage_history
WHERE
  first_usage_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)  -- 최근 30일 내 신규 사용
  AND total_cost > 50  -- $50 이상 사용
ORDER BY
  first_usage_date DESC, total_cost DESC;
```

## 🔍 고급 분석 쿼리

### 14. 리소스 효율성 분석

```sql
-- 비용 대비 사용률이 낮은 리소스 식별
WITH resource_efficiency AS (
  SELECT
    project.id as project_id,
    service.description as service_name,
    sku.description as resource_type,
    SUM(cost) as total_cost,
    SUM(usage.amount) as total_usage,
    COUNT(DISTINCT DATE(usage_start_time)) as active_days,
    -- 가정: 24시간 연속 사용 대비 실제 사용률
    SAFE_DIVIDE(SUM(usage.amount), COUNT(DISTINCT DATE(usage_start_time)) * 24) as avg_utilization_ratio
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND service.description = 'Compute Engine'
    AND sku.description LIKE '%Instance Core%'
    AND cost > 0
  GROUP BY
    project_id, service_name, resource_type
)
SELECT
  project_id,
  service_name,
  resource_type,
  total_cost,
  total_usage,
  active_days,
  ROUND(avg_utilization_ratio, 3) as avg_utilization_ratio,
  ROUND(total_cost / NULLIF(avg_utilization_ratio, 0), 2) as efficiency_cost_ratio
FROM
  resource_efficiency
WHERE
  total_cost > 100  -- $100 이상
  AND avg_utilization_ratio < 0.3  -- 30% 미만 사용률
ORDER BY
  efficiency_cost_ratio DESC;
```

### 15. 비용 예측 모델

```sql
-- 선형 회귀 기반 다음 달 비용 예측
WITH monthly_costs AS (
  SELECT
    DATE_TRUNC(DATE(usage_start_time), MONTH) as month,
    service.description as service_name,
    SUM(cost) as monthly_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 6 MONTH)
    AND cost > 0
  GROUP BY
    month, service_name
),
cost_trends AS (
  SELECT
    service_name,
    COUNT(*) as months_count,
    AVG(monthly_cost) as avg_monthly_cost,
    -- 간단한 선형 추세 계산
    (SUM(monthly_cost * DATE_DIFF(month, DATE('2024-01-01'), MONTH)) - 
     COUNT(*) * AVG(monthly_cost) * AVG(DATE_DIFF(month, DATE('2024-01-01'), MONTH))) /
    NULLIF(SUM(POW(DATE_DIFF(month, DATE('2024-01-01'), MONTH), 2)) - 
           COUNT(*) * POW(AVG(DATE_DIFF(month, DATE('2024-01-01'), MONTH)), 2), 0) as trend_slope
  FROM
    monthly_costs
  GROUP BY
    service_name
  HAVING
    COUNT(*) >= 3  -- 최소 3개월 데이터 필요
)
SELECT
  service_name,
  avg_monthly_cost,
  trend_slope,
  avg_monthly_cost + trend_slope as predicted_next_month_cost,
  ROUND(trend_slope / NULLIF(avg_monthly_cost, 0) * 100, 2) as monthly_growth_rate_pct
FROM
  cost_trends
WHERE
  avg_monthly_cost > 100  -- $100 이상인 서비스만
ORDER BY
  predicted_next_month_cost DESC;
```

## 📊 대시보드용 요약 쿼리

### 16. 경영진 대시보드용 KPI

```sql
-- 경영진 대시보드용 주요 지표
WITH current_month AS (
  SELECT
    SUM(cost) as current_month_cost,
    COUNT(DISTINCT project.id) as active_projects,
    COUNT(DISTINCT service.description) as active_services
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
),
previous_month AS (
  SELECT
    SUM(cost) as previous_month_cost
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE
    DATE(usage_start_time) >= DATE_SUB(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 1 MONTH)
    AND DATE(usage_start_time) < DATE_TRUNC(CURRENT_DATE(), MONTH)
),
credits_summary AS (
  SELECT
    SUM(c.amount) as total_credits
  FROM
    `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`,
    UNNEST(credits) as c
  WHERE
    DATE(usage_start_time) >= DATE_TRUNC(CURRENT_DATE(), MONTH)
    AND c.amount < 0
)
SELECT
  -- 현재 월 비용
  ROUND(c.current_month_cost, 2) as current_month_cost,
  ROUND(p.previous_month_cost, 2) as previous_month_cost,
  ROUND((c.current_month_cost - p.previous_month_cost) / NULLIF(p.previous_month_cost, 0) * 100, 2) as mom_growth_pct,
  
  -- 크레딧 절약
  ROUND(ABS(cs.total_credits), 2) as total_credits_saved,
  ROUND(ABS(cs.total_credits) / NULLIF(c.current_month_cost, 0) * 100, 2) as credit_savings_pct,
  
  -- 활성 리소스
  c.active_projects,
  c.active_services,
  
  -- 예상 월말 비용 (현재까지 일평균 * 월 일수)
  ROUND(c.current_month_cost / EXTRACT(DAY FROM CURRENT_DATE()) * 
        EXTRACT(DAY FROM LAST_DAY(CURRENT_DATE())), 2) as projected_month_end_cost
FROM
  current_month c
CROSS JOIN
  previous_month p
CROSS JOIN
  credits_summary cs;
```

## 🔗 관련 리소스

### Google Cloud 공식 문서
- **[Cloud Billing BigQuery 쿼리 예시](https://cloud.google.com/billing/docs/how-to/bq-examples?hl=ko)**
- **[BigQuery의 Cloud Billing 데이터 테이블 이해](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables?hl=ko)**
- **[BigQuery SQL 참조](https://cloud.google.com/bigquery/docs/reference/standard-sql/)**

### 프로젝트 내 관련 문서
- **[📊 BigQuery의 Cloud Billing 데이터 테이블 이해하기](./BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - 테이블 구조 이해
- **[📈 표준 데이터 내보내기의 구조](./표준%20데이터%20내보내기의%20구조.md)** - 표준 데이터 스키마
- **[📋 자세한 데이터 내보내기의 구조](./자세한%20데이터%20내보내기의%20구조.md)** - 상세 데이터 스키마
- **[💰 가격 책정 데이터 내보내기의 구조](./가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 데이터 스키마
- **[📊 데이터 분석 가이드](./data-analysis-guide.md)** - 종합 분석 방법

---

> **💡 팁**: 모든 쿼리에서 `PROJECT_ID`, `DATASET_ID`, `BILLING_ACCOUNT_ID`를 실제 값으로 교체해야 합니다. 성능 최적화를 위해 항상 `DATE(usage_start_time)` 필터를 사용하여 파티션 프루닝을 활용하세요.
