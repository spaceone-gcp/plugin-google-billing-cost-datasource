# Field Mapper 개발 가이드

이 문서는 Google Cloud Billing HTTP 파일 통합 기능에서 사용될 Field Mapper 구현에 대한 상세 가이드입니다.

## 목차
1. [개요](#1-개요)
2. [Field Mapper 구조](#2-field-mapper-구조)
3. [기본 매핑 규칙](#3-기본-매핑-규칙)
4. [비용 선택 옵션 (select_cost)](#4-비용-선택-옵션-select_cost)
5. [비용 메트릭 옵션 (cost_metric)](#5-비용-메트릭-옵션-cost_metric)
6. [고급 매핑 기능](#6-고급-매핑-기능)
7. [구현 설계](#7-구현-설계)
8. [사용 예시](#8-사용-예시)
9. [에러 처리](#9-에러-처리)
10. [성능 최적화](#10-성능-최적화)

## 1. 개요

Field Mapper는 다양한 형식의 Google Cloud Billing 데이터를 SpaceONE 표준 비용 데이터 형식으로 변환하는 핵심 컴포넌트입니다.

### 1.1. 주요 기능
- 원본 필드명을 SpaceONE 표준 필드명으로 매핑
- 자동 타입 변환 및 데이터 검증
- 기본값 설정 및 누락 필드 처리
- 중첩된 JSON 구조 처리

### 1.2. 지원 데이터 형식
- CSV 파일 (헤더 기반)
- JSON 파일 (중첩 구조 지원)
- Parquet 파일 (스키마 기반)

## 2. Field Mapper 구조

### 2.1. 기본 구조
```yaml
field_mapper:
  # 필수 필드 매핑
  cost: "cost"                    # 실제 비용
  billed_date: "usage_start_time" # 청구일
  currency: "currency"            # 통화
  provider: "provider"            # 클라우드 제공자
  
  # 선택적 필드 매핑
  usage_quantity: "usage.amount_in_pricing_units"
  usage_unit: "usage.pricing_unit"
  product: "service.description"
  usage_type: "sku.description"
  region_code: "location.region"
  
  # 추가 정보 매핑
  additional_info:
    cost_at_list: "cost_at_list"
    credits: "credits"
    project_id: "project.id"
    project_name: "project.name"
    billing_account_id: "billing_account_id"
    invoice_month: "invoice.month"
    
  # 태그 매핑
  tags:
    project_labels: "project.labels"
    resource_labels: "labels"
```

### 2.2. 자동 매핑 설정
```yaml
# provider 설정으로 자동 매핑 활성화
options:
  provider: "google_cloud"  # 기본 매핑 자동 적용
  field_mapper:
    # 추가 커스터마이징만 명시
    additional_info:
      custom_field: "my_custom_field"
```

## 3. 기본 매핑 규칙

### 3.1. SpaceONE 필수 필드
| SpaceONE 필드 | Google Cloud 필드 | 타입 | 설명 |
|:-------------|:-----------------|:-----|:-----|
| `cost` | `cost` | `float` | 크레딧 적용 후 실제 비용 |
| `billed_date` | `usage_start_time` | `string` | 청구 기준일 (YYYY-MM-DD) |
| `currency` | `currency` | `string` | 통화 코드 (USD, KRW 등) |
| `provider` | `"google_cloud"` | `string` | 고정값 또는 매핑 |

### 3.2. SpaceONE 선택적 필드
| SpaceONE 필드 | Google Cloud 필드 | 타입 | 설명 |
|:-------------|:-----------------|:-----|:-----|
| `usage_quantity` | `usage.amount_in_pricing_units` | `float` | 사용량 |
| `usage_unit` | `usage.pricing_unit` | `string` | 사용량 단위 |
| `product` | `service.description` | `string` | 서비스명 |
| `usage_type` | `sku.description` | `string` | SKU 설명 |
| `region_code` | `location.region` | `string` | 리전 코드 |
| `resource` | `project.name` | `string` | 리소스 식별자 |

### 3.3. 데이터 타입 변환 규칙
- **날짜 변환**: `TIMESTAMP` → `YYYY-MM-DD` 문자열
- **숫자 변환**: 문자열 숫자 → `float` 타입
- **JSON 변환**: 중첩 객체 → 평면 구조 또는 JSON 문자열
- **배열 처리**: 배열 필드 → JSON 문자열 또는 첫 번째 값

## 4. 비용 선택 옵션 (select_cost)

Google Cloud Billing 데이터에는 여러 종류의 비용 정보가 포함되어 있습니다. `select_cost` 옵션을 통해 어떤 비용 값을 사용할지 선택할 수 있습니다.

### 4.1. 지원하는 비용 타입

| 옵션 값 | 필드명 | 설명 |
|:--------|:-------|:-----|
| `cost` (기본값) | `cost` | 크레딧을 포함한 최종 실제 비용 |
| `list_price` | `cost_at_list` | 정가 (크레딧 적용 전 원가) |
| `after_credits` | `cost_after_credits` | 크레딧 적용 후 비용 |
| `net_cost` | `cost` | 순 비용 (기본 cost와 동일) |

### 4.2. 설정 방법

#### 4.2.1. options에서 설정
```yaml
options:
  select_cost: "list_price"  # 정가 사용
  # 또는
  select_cost: "after_credits"  # 크레딧 적용 후 비용 사용
```

#### 4.2.2. task_options에서 설정 (우선순위 높음)
```yaml
task_options:
  select_cost: "cost"  # 기본 실제 비용 사용
```

### 4.3. 비용 타입별 사용 시나리오

#### 4.3.1. `cost` (기본값)
- **사용 시나리오**: 실제 청구된 최종 비용을 확인하고 싶을 때
- **특징**: 크레딧, 할인, 프로모션이 모두 적용된 실제 지불 금액
- **권장**: 대부분의 비용 분석 및 리포팅

#### 4.3.2. `list_price`
- **사용 시나리오**: 서비스의 정가를 확인하고 할인 효과를 분석하고 싶을 때
- **특징**: 크레딧이나 할인 적용 전의 원가
- **권장**: 비용 절감 효과 측정, 예산 계획 수립

#### 4.3.3. `after_credits`
- **사용 시나리오**: 크레딧만 적용된 비용을 확인하고 싶을 때
- **특징**: 크레딧은 적용되었지만 다른 할인은 미적용된 비용
- **권장**: 크레딧 사용량 분석

#### 4.3.4. `net_cost`
- **사용 시나리오**: 순 비용 개념으로 분석하고 싶을 때
- **특징**: 현재는 `cost`와 동일하게 처리됨
- **권장**: 회계 목적의 순비용 분석

### 4.4. 구현 예시

```python
# CostManager에서 select_cost 옵션 사용
def _get_cost_field_by_option(self, row) -> float:
    """select_cost 옵션에 따라 적절한 비용 필드를 선택"""
    select_cost = self.select_cost_option or "cost"
    
    if select_cost == "list_price":
        return getattr(row, "cost_at_list", 0.0)
    elif select_cost == "after_credits":
        return getattr(row, "cost_after_credits", 0.0)
    elif select_cost == "net_cost":
        return getattr(row, "cost", 0.0)
    else:  # 기본값: cost
        return getattr(row, "cost", 0.0)
```

### 4.5. 비용 데이터 비교 예시

동일한 리소스에 대한 비용 타입별 값 예시:

```json
{
  "service": "Compute Engine",
  "cost_at_list": 100.00,      # 정가
  "cost_after_credits": 80.00,  # 크레딧 적용 후
  "cost": 72.00,               # 최종 실제 비용 (할인 포함)
  "credits": [
    {"type": "PROMOTION", "amount": -20.00},
    {"type": "SUSTAINED_USE", "amount": -8.00}
  ]
}
```

이 경우 `select_cost` 옵션에 따른 결과:
- `list_price`: 100.00 (정가)
- `after_credits`: 80.00 (프로모션 크레딧 적용 후)
- `cost` 또는 `net_cost`: 72.00 (모든 할인 적용 후 실제 비용)

## 5. 비용 메트릭 옵션 (cost_metric)

`cost_metric` 옵션은 특별한 비용 계산 방식을 지정할 때 사용합니다. 이 옵션이 설정되면 `select_cost` 옵션보다 우선 적용됩니다.

### 5.1. 지원하는 메트릭 타입

| 메트릭 | 필드명 | 설명 |
|:-------|:-------|:-----|
| `AmortizedCost` | `credits_amount` | 크레딧 절대값 기준 비용 |

### 5.2. AmortizedCost 설정

AmortizedCost는 크레딧의 절대값을 비용으로 사용하여, 크레딧 사용량 자체를 분석할 때 유용합니다.

#### 5.2.1. 초기화 시 설정
```python
# FieldMapper 초기화 시 cost_metric 전달
field_mapper = FieldMapper(
    mapping_config=mapping_config,
    provider="google_cloud",
    select_cost="cost",
    cost_metric="AmortizedCost"  # 크레딧 절대값 사용
)
```

#### 5.2.2. 설정 파일에서 설정
```yaml
options:
  cost_metric: "AmortizedCost"  # 크레딧 절대값을 비용으로 사용
  
# 또는 task_options에서 설정 (우선순위 높음)
task_options:
  cost_metric: "AmortizedCost"
```

### 5.3. 우선순위 및 동작 방식

#### 5.3.1. 옵션 우선순위
1. **`cost_metric`** (최우선) - 특별한 비용 계산 방식
2. **`select_cost`** - 일반적인 비용 필드 선택

```python
def _get_cost_by_option(self, source_data: dict) -> float:
    """select_cost 및 cost_metric 옵션에 따라 적절한 비용 필드를 선택"""
    
    # cost_metric이 AmortizedCost인 경우 credits_amount 사용
    if self.cost_metric == "AmortizedCost":
        return self._map_field("credits_amount", source_data, 0.0)
    
    # 기존 select_cost 로직
    if self.select_cost == "list_price":
        return self._map_field("cost_at_list", source_data, 0.0)
    # ... 기타 옵션들
```

#### 5.3.2. 매핑 설정
AmortizedCost 사용 시 `credits_amount` 필드가 기본 매핑에 포함되어야 합니다:

```yaml
field_mapper:
  additional_info:
    credits_amount: "credits_amount"  # AmortizedCost용 필드
    credits: "credits_detail"         # 크레딧 상세 정보
```

### 5.4. 사용 예시

#### 5.4.1. 크레딧 사용량 분석
```python
# 크레딧 사용량을 비용으로 분석하는 설정
field_mapper = FieldMapper(
    mapping_config={
        "cost": "cost",
        "additional_info": {
            "credits_amount": "credits_amount",
            "credits": "credits_detail"
        }
    },
    provider="google_cloud",
    cost_metric="AmortizedCost"
)

# 결과 데이터 예시
result = {
    "cost": 25.00,  # credits_amount 값이 사용됨
    "additional_info": {
        "cost_at_list": 100.00,
        "cost_after_credits": 75.00,
        "credits_amount": 25.00,  # 원본 크레딧 절대값
        "credits": [
            {"type": "PROMOTION", "amount": -15.00},
            {"type": "SUSTAINED_USE", "amount": -10.00}
        ]
    }
}
```

### 5.5. BigQuery vs HTTP 파일 모드

#### 5.5.1. BigQuery 모드
- SQL 쿼리에서 `credits_amount`가 자동으로 계산됨:
  ```sql
  ABS(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))) AS credits_amount
  ```

#### 5.5.2. HTTP 파일 모드
- Field Mapper를 통해 `credits_amount` 필드를 매핑:
  ```yaml
  field_mapper:
    additional_info:
      credits_amount: "credits_amount"
  ```

### 5.6. 주의사항

- **데이터 가용성**: `credits_amount` 필드는 크레딧이 적용된 항목에서만 0이 아닌 값을 가집니다.
- **우선순위**: `cost_metric` 설정 시 `select_cost` 옵션은 완전히 무시됩니다.
- **필드 매핑**: AmortizedCost 사용 시 `credits_amount` 필드가 반드시 매핑되어야 합니다.

## 6. 고급 매핑 기능

### 6.1. 중첩 필드 매핑
```yaml
field_mapper:
  project_id: "project.id"           # 중첩 객체 접근
  project_name: "project.name"
  location_region: "location.region"
  service_desc: "service.description"
```

### 6.2. 배열 필드 처리
```yaml
field_mapper:
  additional_info:
    # 배열을 JSON 문자열로 변환
    credits: "credits"
    labels: "labels"
    
    # 배열의 특정 요소 추출
    first_credit_type: "credits[0].type"
    first_credit_amount: "credits[0].amount"
```

### 6.3. 조건부 매핑
```yaml
field_mapper:
  # 값이 존재할 때만 매핑
  region_code: 
    source: "location.region"
    default: "global"           # 기본값 설정
    
  # 값 변환 규칙
  cost:
    source: "cost"
    type: "decimal"             # Decimal 타입으로 변환
    required: true              # 필수 필드 지정
```

### 5.4. 계산 필드
```yaml
field_mapper:
  additional_info:
    # 여러 필드를 조합한 계산
    effective_discount_rate:
      formula: "(cost_at_list - cost) / cost_at_list * 100"
      sources: ["cost_at_list", "cost"]
      type: "float"
```

## 7. 구현 설계

### 7.1. FieldMapper 클래스 구조
```python
class FieldMapper:
    def __init__(self, mapping_config: dict, provider: str = None):
        """
        Args:
            mapping_config: 필드 매핑 설정
            provider: 자동 매핑을 위한 프로바이더 정보
        """
        
    def map_record(self, source_data: dict) -> dict:
        """단일 레코드를 SpaceONE 형식으로 변환"""
        
    def validate_required_fields(self, mapped_data: dict) -> bool:
        """필수 필드 존재 여부 검증"""
        
    def apply_default_values(self, mapped_data: dict, defaults: dict) -> dict:
        """기본값 적용"""
```

### 6.2. 자동 매핑 로직
```python
def get_default_mapping(provider: str) -> dict:
    """프로바이더별 기본 매핑 반환"""
    if provider == "google_cloud":
        return {
            "cost": "cost",
            "billed_date": "usage_start_time",
            "currency": "currency",
            "provider": "provider",
            # ... 기본 매핑 정의
        }
```

### 6.3. 데이터 변환 유틸리티
```python
class DataConverter:
    @staticmethod
    def convert_timestamp_to_date(timestamp_str: str) -> str:
        """TIMESTAMP를 YYYY-MM-DD 형식으로 변환"""
        
    @staticmethod
    def convert_to_decimal(value: any) -> Decimal:
        """값을 Decimal 타입으로 변환"""
        
    @staticmethod
    def extract_nested_value(data: dict, path: str) -> any:
        """중첩된 객체에서 값 추출 (예: "project.id")"""
```

## 8. 사용 예시

### 8.1. 기본 사용법
```python
# 자동 매핑 사용
field_mapper = FieldMapper(
    mapping_config={},
    provider="google_cloud"
)

# 원본 데이터
source_data = {
    "cost": 12.34,
    "usage_start_time": "2024-01-01T00:00:00Z",
    "currency": "USD",
    "project": {"id": "my-project", "name": "My Project"},
    "service": {"description": "Compute Engine"}
}

# 변환 실행
result = field_mapper.map_record(source_data)
# 결과: SpaceONE 표준 형식의 딕셔너리
```

### 7.2. 커스터마이징 사용법
```python
# 커스터마이징된 매핑
mapping_config = {
    "cost": "total_cost",           # 다른 필드명 사용
    "additional_info": {
        "original_cost": "cost",     # 원본 비용도 추가 정보로 포함
        "discount_amount": "credits[0].amount"
    }
}

field_mapper = FieldMapper(
    mapping_config=mapping_config,
    provider="google_cloud"
)
```

### 7.3. 기본값 설정
```python
# 기본값과 함께 사용
defaults = {
    "provider": "google_cloud",
    "currency": "USD",
    "region_code": "global"
}

result = field_mapper.map_record(source_data)
result = field_mapper.apply_default_values(result, defaults)
```

## 9. 에러 처리

### 9.1. 필수 필드 누락
```python
try:
    result = field_mapper.map_record(source_data)
    if not field_mapper.validate_required_fields(result):
        raise ValueError("Required fields missing")
except ValueError as e:
    logger.warning(f"Record validation failed: {e}")
    # 해당 레코드 스킵하고 계속 처리
```

### 8.2. 데이터 타입 변환 오류
```python
try:
    converted_value = DataConverter.convert_to_decimal(raw_value)
except (ValueError, TypeError) as e:
    logger.warning(f"Type conversion failed: {e}")
    converted_value = Decimal('0')  # 기본값 사용
```

## 10. 성능 최적화

### 10.1. 매핑 성능 최적화
- 매핑 규칙 사전 컴파일
- 중첩 필드 접근 경로 캐싱
- 정규식 패턴 재사용

### 10.2. 메모리 효율성
- 스트리밍 방식으로 레코드별 처리
- 불필요한 데이터 복사 최소화
- 가비지 컬렉션 고려한 객체 관리

### 10.3. 성능 측정 및 모니터링
```python
import time
from functools import wraps

def performance_monitor(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.debug(f"{func.__name__} execution time: {end_time - start_time:.4f}s")
        return result
    return wrapper

class FieldMapper:
    @performance_monitor
    def map_record(self, source_data: dict) -> dict:
        # 매핑 로직
        pass
```

이 가이드를 참고하여 유연하고 확장 가능한 Field Mapper를 구현하시기 바랍니다.
