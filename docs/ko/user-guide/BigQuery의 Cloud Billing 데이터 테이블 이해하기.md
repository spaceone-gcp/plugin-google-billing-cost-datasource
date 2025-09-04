# BigQuery의 Cloud Billing 데이터 테이블 이해하기

이 문서는 Google Cloud의 공식 [BigQuery의 Cloud Billing 데이터 테이블 이해](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables?hl=ko) 가이드를 기반으로, BigQuery로 내보낸 Cloud Billing 데이터 테이블의 구조와 스키마를 상세히 설명합니다.

## 📋 개요

Cloud Billing 데이터를 BigQuery로 내보내면 자동으로 생성되는 테이블들의 구조와 각 필드의 의미를 이해하는 것은 효과적인 비용 분석의 첫 걸음입니다. 이 가이드는 각 테이블 유형과 스키마 정보를 제공합니다.

## 📊 Cloud Billing 데이터 테이블 유형

Google Cloud Billing Export는 다음 세 가지 유형의 테이블을 생성합니다:

### 1. 표준 사용량 비용 데이터 테이블
- **테이블명**: `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`
- **용도**: 기본적인 사용량 및 비용 정보
- **세분화 수준**: 계정, 프로젝트, 서비스, SKU 수준
- **생성 조건**: 표준 사용량 비용 데이터 내보내기 활성화

### 2. 상세 사용량 비용 데이터 테이블
- **테이블명**: `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>`
- **용도**: 개별 리소스 수준까지의 상세 분석
- **추가 정보**: 리소스 이름, 글로벌 이름, 상세 라벨 및 태그
- **생성 조건**: 상세 사용량 비용 데이터 내보내기 활성화

### 3. 가격 데이터 테이블
- **테이블명**: `cloud_pricing_export`
- **용도**: Google Cloud 서비스별 정가 정보
- **업데이트**: 가격 변동 시 일 1회
- **생성 조건**: 가격 데이터 내보내기 활성화

## ⏰ 데이터 내보내기 타이밍

### 초기 데이터 내보내기 시간
- **표준/상세 사용량 데이터**: 활성화 후 몇 시간에서 최대 48시간
- **가격 데이터**: 활성화 후 몇 시간에서 최대 48시간
- **소급 데이터**: 다중 지역 설정 시 최대 5일 소요

### 일일 업데이트
- **업데이트 주기**: 하루 1-2회
- **업데이트 시간**: UTC 기준 오전 중
- **데이터 지연**: 실제 사용 시점으로부터 6-24시간

## 🌍 지역 설정 및 소급 데이터

### 다중 지역 (Multi-region)
- **지원 위치**: `US`, `EU`
- **소급 데이터**: ✅ 이전 달 시작부터 데이터 포함
- **권장 이유**: 포괄적인 데이터 수집

### 단일 지역 (Region)
- **지원 위치**: 대부분의 BigQuery 지역
- **소급 데이터**: ❌ 활성화 날짜부터만 데이터 포함
- **제한사항**: 일부 지역은 지원되지 않음

## 📋 테이블 스키마 개요

### 공통 필드 (모든 테이블)

| 필드 그룹 | 주요 필드 | 설명 |
|:---|:---|:---|
| **청구 정보** | `billing_account_id` | 청구 계정 ID |
| | `invoice.month` | 인보이스 월 (YYYYMM) |
| | `cost_type` | 비용 유형 (REGULAR, TAX, ADJUSTMENT) |
| **서비스 정보** | `service.id` | 서비스 ID |
| | `service.description` | 서비스 설명 (예: Compute Engine) |
| | `sku.id` | SKU ID |
| | `sku.description` | SKU 설명 (예: N1 Standard CPU) |
| **프로젝트 정보** | `project.id` | 프로젝트 ID |
| | `project.name` | 프로젝트 이름 |
| | `project.labels` | 프로젝트 라벨 |
| **비용 정보** | `cost` | 실제 청구 금액 (크레딧 적용 후) |
| | `cost_at_list` | 정가 (크레딧 적용 전) |
| | `currency` | 통화 |
| **시간 정보** | `usage_start_time` | 사용 시작 시간 |
| | `usage_end_time` | 사용 종료 시간 |
| **위치 정보** | `location.location` | 위치 |
| | `location.country` | 국가 |
| | `location.region` | 리전 |
| | `location.zone` | 존 |

### 상세 사용량 테이블 추가 필드

| 필드 그룹 | 주요 필드 | 설명 |
|:---|:---|:---|
| **리소스 정보** | `resource.name` | 개별 리소스 이름 |
| | `resource.global_name` | 글로벌 리소스 이름 |
| **라벨 및 태그** | `labels` | 리소스 라벨 (키-값 쌍) |
| | `system_labels` | 시스템 라벨 |
| | `tags` | 리소스 태그 정보 |

### 가격 데이터 테이블 필드

| 필드 그룹 | 주요 필드 | 설명 |
|:---|:---|:---|
| **가격 정보** | `list_price` | 공개 정가 정보 |
| | `billing_account_price` | 계정별 할인 적용 가격 |
| **분류 정보** | `product_taxonomy` | 제품 분류 (베타) |
| | `geo_taxonomy` | 지역 분류 (베타) |
| **시간 정보** | `export_time` | 데이터 내보내기 시간 |
| | `pricing_as_of_time` | 가격 데이터 생성 시간 |

## 🔍 테이블 확인 및 검증

### 테이블 존재 확인

```sql
-- 데이터셋 내 모든 테이블 조회
SELECT 
  table_name,
  table_type,
  creation_time,
  last_modified_time
FROM `PROJECT_ID.DATASET_ID.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%billing%'
ORDER BY creation_time DESC;
```

### 테이블 스키마 확인

```sql
-- 특정 테이블의 스키마 정보 조회
SELECT 
  column_name,
  data_type,
  is_nullable,
  description
FROM `PROJECT_ID.DATASET_ID.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'gcp_billing_export_v1_BILLING_ACCOUNT_ID'
ORDER BY ordinal_position;
```

### 데이터 품질 확인

```sql
-- 기본 데이터 품질 검사
SELECT
  COUNT(*) as total_records,
  COUNT(DISTINCT billing_account_id) as unique_billing_accounts,
  COUNT(DISTINCT project.id) as unique_projects,
  MIN(usage_start_time) as earliest_usage,
  MAX(usage_start_time) as latest_usage,
  SUM(cost) as total_cost
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY);
```

## 📈 파티셔닝 및 클러스터링

### 자동 파티셔닝
- **파티션 필드**: `usage_start_time` (일 단위)
- **파티션 만료**: 설정하지 않음 (영구 보관)
- **파티션 필터**: 쿼리 성능 최적화를 위해 날짜 필터 사용 권장

### 클러스터링
- **클러스터 필드**: 자동으로 최적화된 클러스터링 적용
- **일반적인 클러스터**: `service.description`, `project.id`

### 쿼리 최적화 예시

```sql
-- 파티션 필터를 사용한 최적화된 쿼리
SELECT
  service.description,
  SUM(cost) as total_cost
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) = '2024-01-15'  -- 파티션 필터
GROUP BY service.description
ORDER BY total_cost DESC;
```

## ⚠️ 테이블 관리 시 주의사항

### 테이블 수정 금지
- **자동 생성 테이블**: Google Cloud에서 자동 생성하는 테이블은 수정하면 안 됩니다
- **스키마 변경**: 테이블 스키마를 임의로 변경하면 데이터 내보내기가 중단될 수 있습니다
- **테이블 삭제**: 실수로 테이블을 삭제하면 데이터 손실이 발생할 수 있습니다

### 암호화 제한사항
- **CMEK 지원 안 함**: 고객 관리 암호화 키(CMEK) 사용 불가
- **Google 관리 키**: Google이 소유한 암호화 키만 사용 가능
- **보안**: Google의 기본 암호화로 충분한 보안 제공

### 접근 제어
```sql
-- 행 수준 보안 설정 예시
CREATE ROW ACCESS POLICY project_filter_policy
ON `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
GRANT TO ('user:analyst@company.com')
FILTER USING (project.id = 'allowed-project-id');
```

## 🔧 테이블 활용 모범 사례

### 1. 효율적인 쿼리 작성
```sql
-- 좋은 예: 파티션 필터 사용
SELECT service.description, SUM(cost)
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE DATE(usage_start_time) BETWEEN '2024-01-01' AND '2024-01-31'
GROUP BY 1;

-- 나쁜 예: 파티션 필터 없음
SELECT service.description, SUM(cost)
FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
WHERE EXTRACT(MONTH FROM usage_start_time) = 1
GROUP BY 1;
```

### 2. 비용 최적화
```sql
-- 쿼리 비용 예측
SELECT
  ROUND(SUM(total_bytes_processed) / POW(10, 12), 2) as tb_processed,
  ROUND(SUM(total_bytes_processed) / POW(10, 12) * 5, 2) as estimated_cost_usd
FROM `PROJECT_ID.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND job_type = 'QUERY'
  AND state = 'DONE';
```

### 3. 데이터 품질 모니터링
```sql
-- 일일 데이터 완성도 확인
WITH daily_stats AS (
  SELECT
    DATE(usage_start_time) as usage_date,
    COUNT(*) as record_count,
    SUM(cost) as daily_cost,
    COUNT(DISTINCT project.id) as project_count
  FROM `PROJECT_ID.DATASET_ID.gcp_billing_export_v1_BILLING_ACCOUNT_ID`
  WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY usage_date
)
SELECT *,
  LAG(record_count) OVER (ORDER BY usage_date) as prev_record_count,
  ROUND((record_count - LAG(record_count) OVER (ORDER BY usage_date)) / 
        LAG(record_count) OVER (ORDER BY usage_date) * 100, 2) as change_pct
FROM daily_stats
ORDER BY usage_date DESC;
```

## 📚 테이블별 상세 가이드

### 표준 사용량 데이터 테이블
- **📊 [표준 데이터 내보내기의 구조](./표준%20데이터%20내보내기의%20구조.md)** - 상세 스키마 및 활용법

### 상세 사용량 데이터 테이블  
- **📋 [자세한 데이터 내보내기의 구조](./자세한%20데이터%20내보내기의%20구조.md)** - 리소스 수준 분석

### 가격 데이터 테이블
- **💰 [가격 책정 데이터 내보내기의 구조](./가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 정보 스키마

## 🔗 관련 리소스

### Google Cloud 공식 문서
- **[BigQuery의 Cloud Billing 데이터 테이블 이해](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables?hl=ko)**
- **[표준 데이터 내보내기 구조](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage?hl=ko)**
- **[상세 데이터 내보내기 구조](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage?hl=ko)**
- **[가격 데이터 내보내기 구조](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data?hl=ko)**

### 프로젝트 내 관련 문서
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - 개요 및 활용 가이드
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드
- **[📊 데이터 분석 가이드](./data-analysis-guide.md)** - 분석 방법 및 쿼리 예시
- **[🔍 Cloud Billing 데이터 내보내기의 쿼리 예시](./Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - 실용적인 쿼리 모음

---

> **💡 팁**: 테이블 구조를 이해한 후에는 각 테이블 유형별 상세 가이드를 참고하여 구체적인 스키마와 활용 방법을 학습하세요. 효율적인 쿼리 작성과 비용 최적화를 위해 파티션 필터를 항상 사용하는 것을 권장합니다.
