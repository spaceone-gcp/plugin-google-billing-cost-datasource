# Field Mapper 설정 가이드

## 개요

`field_mapper`는 원본 데이터의 필드명을 SpaceONE에서 요구하는 표준 필드명으로 변환하는 설정입니다. 원본 데이터의 필드명이 표준과 다를 때 이를 매핑하여 올바른 데이터 처리를 보장합니다.

## 필수 필드

SpaceONE 비용 데이터 처리를 위한 필수 필드는 다음과 같습니다:

- `cost`: 비용 금액
- `currency`: 통화 (예: USD, KRW)
- `billed_date`: 청구 날짜 (YYYY-MM-DD 형식)

## 기본 설정 예제

### 1. 간단한 필드 매핑

원본 데이터에 `amount`, `curr`, `date` 필드가 있는 경우:

```json
{
  "field_mapper": {
    "cost": "amount",
    "currency": "curr", 
    "billed_date": "date"
  }
}
```

### 2. CSV 데이터 매핑 예제

CSV 파일의 헤더가 다음과 같은 경우:
```csv
date,amount,service_name,cloud_provider
2024-01-01,100.50,EC2,aws
```

field_mapper 설정:
```json
{
  "field_mapper": {
    "cost": "amount",
    "currency": "USD",
    "billed_date": "date",
    "product": "service_name",
    "provider": "cloud_provider"
  }
}
```

### 3. 복잡한 매핑 (additional_info 활용)

```json
{
  "field_mapper": {
    "cost": "billing_amount",
    "currency": "currency_code",
    "billed_date": "usage_date",
    "additional_info": {
      "Account ID": "account_id",
      "Project": "project_name",
      "Region": "region_code"
    }
  }
}
```

## default_vars와 함께 사용

일부 필드가 고정값인 경우 `default_vars`를 함께 사용할 수 있습니다:

```json
{
  "field_mapper": {
    "cost": "amount",
    "billed_date": "date"
  },
  "default_vars": {
    "currency": "USD",
    "provider": "aws"
  }
}
```

## 일반적인 원본 데이터 필드명 매핑

| 표준 필드명 | 일반적인 원본 필드명 |
|------------|-------------------|
| cost | amount, price, billing_amount, charge |
| currency | curr, currency_code, billing_currency |
| billed_date | date, usage_date, billing_date, timestamp |
| product | service, service_name, product_name |
| provider | cloud_provider, vendor, provider_name |
| region_code | region, location, availability_zone |

## 문제 해결

### 1. "Required parameter. (key = cost)" 에러

이 에러는 `cost` 필드가 누락되었을 때 발생합니다.

**해결 방법:**
1. 원본 데이터에서 비용 정보가 들어있는 필드를 확인
2. `field_mapper`에 해당 필드를 `cost`로 매핑 추가

```json
{
  "field_mapper": {
    "cost": "amount"  // 이 부분이 누락되었을 수 있음
  }
}
```

### 2. "field_mapper에 설정된 원본 필드가 데이터에 존재하지 않습니다" 경고

이 경고는 매핑 설정에서 지정한 원본 필드가 실제 데이터에 없을 때 발생합니다.

**해결 방법:**
1. 원본 데이터의 실제 필드명 확인
2. `field_mapper` 설정에서 올바른 필드명으로 수정

### 3. 날짜 형식 오류

`billed_date` 필드가 올바르게 처리되지 않는 경우:

**지원되는 날짜 형식:**
- 기존 `billed_date` 필드
- `usage_start_time` 필드 (ISO 형식)
- `invoice.month` 필드 (YYYYMM 형식)
- `year`, `month` 필드 조합

## 검증 기능

시스템에서 자동으로 다음 사항들을 검증합니다:

1. **필수 필드 매핑 완성도**: 모든 필수 필드가 매핑되었는지 확인
2. **매핑 일치성**: 매핑 설정의 원본 필드가 실제 데이터에 존재하는지 확인
3. **에러 메시지**: 문제 발생 시 구체적인 해결 방안 제시

## 모범 사례

1. **단계적 접근**: 먼저 필수 필드만 매핑하고, 점진적으로 추가 필드 매핑
2. **테스트**: 작은 데이터 샘플로 먼저 테스트 후 전체 데이터 처리
3. **로그 확인**: 경고 메시지를 통해 매핑 설정 문제점 파악
4. **문서화**: 프로젝트별 매핑 설정을 문서화하여 유지보수 용이성 확보

## 예제 데이터별 설정

### AWS 빌링 데이터
```json
{
  "field_mapper": {
    "cost": "LineItem/BlendedCost",
    "currency": "LineItem/CurrencyCode", 
    "billed_date": "LineItem/UsageStartDate",
    "product": "Product/ProductName",
    "additional_info": {
      "Account ID": "LineItem/UsageAccountId",
      "Resource ID": "LineItem/ResourceId"
    }
  }
}
```

### GCP 빌링 데이터
```json
{
  "field_mapper": {
    "cost": "cost",
    "currency": "currency",
    "billed_date": "usage_start_time",
    "product": "service.description",
    "region_code": "location.region",
    "additional_info": {
      "cost_at_list": "cost_at_list",
      "project_id": "project.id",
      "credits": "credits"
    }
  }
}
```

### 사용자 정의 CSV
```json
{
  "field_mapper": {
    "cost": "amount",
    "billed_date": "date"
  },
  "default_vars": {
    "currency": "USD",
    "provider": "custom"
  }
}
```
