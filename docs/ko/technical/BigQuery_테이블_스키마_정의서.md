# BigQuery GCP Billing Export 테이블 스키마 정의서

## 개요

이 문서는 `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F` 테이블의 스키마 구조와 각 필드에 대한 상세 정보를 제공합니다.

##  ABSOLUTE PERFECT ULTRA PURE DATA 원칙

### 데이터 순수성 보장
- **모든 NULL 값 보존**: BigQuery에서 NULL인 값은 절대 기본값으로 변환하지 않음
- **원본 데이터 타입 유지**: 숫자, 문자열, 과학적 표기법 등 모든 데이터를 원본 그대로 보존
- **IFNULL 사용 금지**: BigQuery 쿼리에서 `IFNULL(field, default_value)` 사용 절대 금지
- **반올림/변환 금지**: `round()`, `float()`, `Decimal()` 등 데이터 변환 작업 금지
- **기본값 설정 금지**: `getattr(row, "field", 0.0)` 형태의 기본값 설정 금지

### 스키마 일치성 보장
- **필드 완전 일치**: 응답 필드는 이 스키마에 정의된 필드와 100% 일치해야 함
- **중첩 구조 정확 매핑**: RECORD 타입의 중첩 필드는 정확한 경로로 매핑
- **REPEATED 필드 적절 처리**: 배열 필드는 JSON 문자열로 변환하여 처리

## 테이블 정보

- **프로젝트**: `mkkang-project`
- **데이터셋**: `multi_region_billing_data`
- **테이블명**: `gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`
- **테이블 유형**: GCP Billing Export v1
- **데이터 형식**: Google Cloud Billing 내보내기 데이터

## 스키마 구조

### 1. 청구서 정보 (Invoice Information)

#### `invoice` (RECORD, NULLABLE)
청구서 관련 정보를 포함하는 중첩 구조

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `month` | STRING | NULLABLE | 청구서 월 (YYYY-MM 형식) |
| `publisher_type` | STRING | NULLABLE | 게시자 유형 (예: Google, Marketplace) |

#### `cost_type` (STRING, NULLABLE)
비용 유형 구분 (예: regular, tax, adjustment)

#### `adjustment_info` (RECORD, NULLABLE)
조정 정보를 포함하는 중첩 구조

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `id` | STRING | NULLABLE | 조정 ID |
| `description` | STRING | NULLABLE | 조정 설명 |
| `mode` | STRING | NULLABLE | 조정 모드 |
| `type` | STRING | NULLABLE | 조정 유형 |

### 2. 비용 정보 (Cost Information)

#### 비용 관련 필드들
| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `cost_at_list` | FLOAT | NULLABLE | 정가 기준 비용 |
| `cost_at_effective_price_default` | FLOAT | NULLABLE | 기본 유효 가격 기준 비용 |
| `cost_at_list_consumption_model` | FLOAT | NULLABLE | 소비 모델 정가 기준 비용 |

### 3. 소비 모델 정보 (Consumption Model)

#### `consumption_model` (RECORD, NULLABLE)
소비 모델 정보를 포함하는 중첩 구조

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `id` | STRING | NULLABLE | 소비 모델 ID |
| `description` | STRING | NULLABLE | 소비 모델 설명 |

### 4. 계정 및 서비스 정보

#### `billing_account_id` (STRING, NULLABLE)
청구 계정 ID

#### `service` (RECORD, NULLABLE)
서비스 정보를 포함하는 중첩 구조

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `id` | STRING | NULLABLE | 서비스 ID |
| `description` | STRING | NULLABLE | 서비스 설명 |

#### `sku` (RECORD, NULLABLE)
SKU(Stock Keeping Unit) 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `id` | STRING | NULLABLE | SKU ID |
| `description` | STRING | NULLABLE | SKU 설명 |

### 5. 사용 시간 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `usage_start_time` | TIMESTAMP | NULLABLE | 사용 시작 시간 |
| `usage_end_time` | TIMESTAMP | NULLABLE | 사용 종료 시간 |

### 6. 프로젝트 정보

#### `project` (RECORD, NULLABLE)
프로젝트 관련 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `id` | STRING | NULLABLE | 프로젝트 ID |
| `number` | STRING | NULLABLE | 프로젝트 번호 |
| `name` | STRING | NULLABLE | 프로젝트 이름 |
| `ancestry_numbers` | STRING | NULLABLE | 상위 조직 번호들 |

#### 프로젝트 라벨 및 계층 구조

##### `labels` (RECORD, REPEATED)
프로젝트 라벨 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `key` | STRING | NULLABLE | 라벨 키 |
| `value` | STRING | NULLABLE | 라벨 값 |

##### `ancestors` (RECORD, REPEATED)
프로젝트 상위 계층 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `resource_name` | STRING | NULLABLE | 리소스 이름 |
| `display_name` | STRING | NULLABLE | 표시 이름 |

### 7. 라벨 정보

#### `labels` (RECORD, REPEATED)
리소스 라벨 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `key` | STRING | NULLABLE | 라벨 키 |
| `value` | STRING | NULLABLE | 라벨 값 |

#### `system_labels` (RECORD, REPEATED)
시스템 라벨 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `key` | STRING | NULLABLE | 시스템 라벨 키 |
| `value` | STRING | NULLABLE | 시스템 라벨 값 |

### 8. 위치 정보

#### `location` (RECORD, NULLABLE)
리소스 위치 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `location` | STRING | NULLABLE | 위치 |
| `country` | STRING | NULLABLE | 국가 |
| `region` | STRING | NULLABLE | 지역 |
| `zone` | STRING | NULLABLE | 가용 영역 |

### 9. 태그 정보

#### `tags` (RECORD, REPEATED)
리소스 태그 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `key` | STRING | NULLABLE | 태그 키 |
| `value` | STRING | NULLABLE | 태그 값 |
| `inherited` | BOOLEAN | NULLABLE | 상속 여부 |
| `namespace` | STRING | NULLABLE | 네임스페이스 |

### 10. 가격 정보

#### `price` (RECORD, NULLABLE)
가격 정보를 포함하는 중첩 구조

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `effective_price` | NUMERIC | NULLABLE | 유효 가격 |
| `tier_start_amount` | NUMERIC | NULLABLE | 계층 시작 금액 |
| `unit` | STRING | NULLABLE | 단위 |
| `pricing_unit_quantity` | NUMERIC | NULLABLE | 가격 단위 수량 |
| `list_price` | NUMERIC | NULLABLE | 정가 |
| `effective_price_default` | NUMERIC | NULLABLE | 기본 유효 가격 |
| `list_price_consumption_model` | NUMERIC | NULLABLE | 소비 모델 정가 |

### 11. 거래 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `transaction_type` | STRING | NULLABLE | 거래 유형 |
| `seller_name` | STRING | NULLABLE | 판매자 이름 |
| `export_time` | TIMESTAMP | NULLABLE | 내보내기 시간 |

### 12. 비용 및 통화 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `cost` | FLOAT | NULLABLE | 총 비용 |
| `currency` | STRING | NULLABLE | 통화 코드 (예: USD, KRW) |
| `currency_conversion_rate` | FLOAT | NULLABLE | 환율 |

### 13. 사용량 정보

#### `usage` (RECORD, NULLABLE)
사용량 관련 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `amount` | FLOAT | NULLABLE | 사용량 |
| `unit` | STRING | NULLABLE | 사용량 단위 |
| `amount_in_pricing_units` | FLOAT | NULLABLE | 가격 단위 기준 사용량 |
| `pricing_unit` | STRING | NULLABLE | 가격 단위 |

### 14. 크레딧 정보

#### `credits` (RECORD, REPEATED)
크레딧 및 할인 정보

| 필드명 | 데이터 타입 | 모드 | 설명 |
|--------|-------------|------|------|
| `name` | STRING | NULLABLE | 크레딧 이름 |
| `amount` | FLOAT | NULLABLE | 크레딧 금액 |
| `full_name` | STRING | NULLABLE | 크레딧 전체 이름 |
| `id` | STRING | NULLABLE | 크레딧 ID |
| `type` | STRING | NULLABLE | 크레딧 유형 |

## 주요 특징

### 1. 중첩 구조 (Nested Structure)
- 대부분의 복합 정보는 RECORD 타입으로 중첩 구조를 가짐
- 프로젝트, 서비스, 가격 등 관련 정보를 그룹화하여 관리

### 2. 반복 필드 (Repeated Fields)
- `labels`, `system_labels`, `tags`, `credits`, `ancestors` 등은 REPEATED 모드
- 하나의 레코드에 여러 개의 값을 가질 수 있음

### 3. NULL 허용 (Nullable Fields)
- 모든 필드가 NULLABLE 모드로 설정
- 데이터가 없는 경우에도 유연하게 처리 가능

### 4. 데이터 타입 다양성
- STRING: 텍스트 데이터
- FLOAT: 부동소수점 숫자 (비용, 사용량 등)
- NUMERIC: 정밀한 숫자 (가격 정보)
- TIMESTAMP: 시간 정보
- BOOLEAN: 참/거짓 값
- RECORD: 중첩 구조

## 사용 시 주의사항

### 1. 비용 계산
- `cost` 필드는 최종 청구 비용
- 크레딧이 적용된 후의 실제 비용을 나타냄
- 환율 정보(`currency_conversion_rate`)를 통해 다른 통화로 변환 가능

### 2. 시간 정보
- `usage_start_time`과 `usage_end_time`으로 사용 기간 파악
- `export_time`은 데이터 내보내기 시점

### 3. 중첩 필드 접근
- BigQuery에서 중첩 필드는 점(.) 표기법으로 접근
- 예: `project.id`, `service.description`, `price.effective_price`

### 4. 반복 필드 처리
- REPEATED 필드는 배열 형태로 저장
- UNNEST 함수를 사용하여 플래튼화 가능

## 쿼리 예시

### 기본 비용 조회
```sql
SELECT 
    billing_account_id,
    project.id as project_id,
    project.name as project_name,
    service.description as service_name,
    sku.description as sku_name,
    usage_start_time,
    usage_end_time,
    cost,
    currency
FROM `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`
WHERE TRUE
ORDER BY usage_start_time DESC
LIMIT 100;
```

### 서비스별 비용 집계
```sql
SELECT 
    service.description as service_name,
    SUM(cost) as total_cost,
    currency,
    COUNT(*) as record_count
FROM `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`
WHERE TRUE
GROUP BY service.description, currency
ORDER BY total_cost DESC;
```

### 프로젝트별 월간 비용
```sql
SELECT 
    project.name as project_name,
    EXTRACT(YEAR FROM usage_start_time) as year,
    EXTRACT(MONTH FROM usage_start_time) as month,
    SUM(cost) as monthly_cost,
    currency
FROM `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`
WHERE TRUE
GROUP BY project.name, year, month, currency
ORDER BY year DESC, month DESC, monthly_cost DESC;
```

### 라벨별 비용 분석
```sql
SELECT 
    label.key as label_key,
    label.value as label_value,
    SUM(cost) as total_cost,
    currency
FROM `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`,
UNNEST(labels) as label
WHERE TRUE
GROUP BY label.key, label.value, currency
ORDER BY total_cost DESC;
```

### 크레딧 적용 현황
```sql
SELECT 
    project.name as project_name,
    service.description as service_name,
    credit.name as credit_name,
    credit.type as credit_type,
    SUM(credit.amount) as total_credit_amount,
    SUM(cost) as total_cost,
    currency
FROM `mkkang-project.multi_region_billing_data.gcp_billing_export_v1_01FD8E_B4DDC1_EAB69F`,
UNNEST(credits) as credit
WHERE credit.amount != 0
GROUP BY project.name, service.description, credit.name, credit.type, currency
ORDER BY total_credit_amount DESC;
```

## 관련 문서

- [BigQuery 설정 가이드](../user-guide/BigQuery_설정_가이드.md)
- [데이터 분석 가이드](../user-guide/데이터_분석_가이드.md)
- [크레딧 및 할인 분석 가이드](../user-guide/크레딧_및_할인_분석_가이드.md)
- [API 명세서](./API_명세서.md)

## 버전 정보

- **문서 버전**: 1.0
- **최종 업데이트**: 2025-09-16
- **테이블 스키마 버전**: GCP Billing Export v1
