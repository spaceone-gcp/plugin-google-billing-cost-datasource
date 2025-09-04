# Field Mapper 개발 가이드

이 문서는 Google Cloud Billing HTTP 파일 통합 기능에서 사용될 Field Mapper 구현에 대한 상세 가이드입니다.

## 목차
1. [개요](#1-개요)
2. [Field Mapper 구조](#2-field-mapper-구조)
3. [기본 매핑 규칙](#3-기본-매핑-규칙)
4. [고급 매핑 기능](#4-고급-매핑-기능)
5. [구현 설계](#5-구현-설계)
6. [사용 예시](#6-사용-예시)
7. [에러 처리](#7-에러-처리)
8. [성능 최적화](#8-성능-최적화)

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

## 4. 고급 매핑 기능

### 4.1. 중첩 필드 매핑
```yaml
field_mapper:
  project_id: "project.id"           # 중첩 객체 접근
  project_name: "project.name"
  location_region: "location.region"
  service_desc: "service.description"
```

### 4.2. 배열 필드 처리
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

### 4.3. 조건부 매핑
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

### 4.4. 계산 필드
```yaml
field_mapper:
  additional_info:
    # 여러 필드를 조합한 계산
    effective_discount_rate:
      formula: "(cost_at_list - cost) / cost_at_list * 100"
      sources: ["cost_at_list", "cost"]
      type: "float"
```

## 5. 구현 설계

### 5.1. FieldMapper 클래스 구조
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

### 5.2. 자동 매핑 로직
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

### 5.3. 데이터 변환 유틸리티
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

## 6. 사용 예시

### 6.1. 기본 사용법
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

### 6.2. 커스터마이징 사용법
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

### 6.3. 기본값 설정
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

## 7. 에러 처리

### 7.1. 필수 필드 누락
```python
try:
    result = field_mapper.map_record(source_data)
    if not field_mapper.validate_required_fields(result):
        raise ValueError("Required fields missing")
except ValueError as e:
    logger.warning(f"Record validation failed: {e}")
    # 해당 레코드 스킵하고 계속 처리
```

### 7.2. 데이터 타입 변환 오류
```python
try:
    converted_value = DataConverter.convert_to_decimal(raw_value)
except (ValueError, TypeError) as e:
    logger.warning(f"Type conversion failed: {e}")
    converted_value = Decimal('0')  # 기본값 사용
```

## 8. 성능 최적화

### 8.1. 매핑 성능 최적화
- 매핑 규칙 사전 컴파일
- 중첩 필드 접근 경로 캐싱
- 정규식 패턴 재사용

### 8.2. 메모리 효율성
- 스트리밍 방식으로 레코드별 처리
- 불필요한 데이터 복사 최소화
- 가비지 컬렉션 고려한 객체 관리

### 8.3. 성능 측정 및 모니터링
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
