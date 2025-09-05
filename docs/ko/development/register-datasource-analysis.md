# register_datasource.yaml 파일 분석 보고서

이 문서는 현재 프로젝트의 `register_datasource.yaml` 파일을 상세히 분석하고, Google Cloud Billing Pricing Data Export와의 연계 가능성을 검토합니다.

## 📋 현재 설정 분석

### 1. 기본 구성

```yaml
name: Google Cloud Billing1                        # 데이터 소스 표시 이름
data_source_type: EXTERNAL                         # 외부 데이터 소스 유형
provider: google_cloud                             # 클라우드 제공자
secret_type: MANUAL                                # 시크릿 관리 방식
```

**분석 결과**: ✅ **적절함** - 표준적인 외부 데이터 소스 설정으로 올바르게 구성됨

### 2. 플러그인 정보

```yaml
plugin_info:
  plugin_id: plugin-billing-cost-datasource-mkkang1  # 플러그인 고유 ID
  version: 0.0.1                                   # 플러그인 버전
```

**분석 결과**: ⚠️ **개선 필요** 
- 플러그인 ID가 개발자 특정 이름(`mkkang1`)을 포함하고 있어 프로덕션 환경에서 부적절
- 권장: `plugin-google-billing-cost-datasource`와 같은 일반적인 이름 사용

### 3. 인증 정보 (Service Account)

```yaml
secret_data:
  auth_provider_x509_cert_url: https://www.googleapis.com/oauth2/v1/certs
  auth_uri: https://accounts.google.com/o/oauth2/auth
  client_email: mkkang-project-sa@mkkang-project.iam.gserviceaccount.com
  client_id: '111819857503166648281'
  private_key: '-----BEGIN PRIVATE KEY----- ...'  # 실제 개인 키 포함
  private_key_id: 45624b7fa3fa03061d56b1cf56d1194ba324a0af
  project_id: mkkang-project
  token_uri: https://oauth2.googleapis.com/token
  type: service_account
  universe_domain: googleapis.com
```

**분석 결과**: 🚨 **보안 위험** 
- **심각한 보안 문제**: 실제 서비스 계정 개인 키가 평문으로 노출됨
- **즉시 조치 필요**: 해당 서비스 계정 키 폐기 및 재생성 필요
- **권장 방법**: 환경변수 또는 시크릿 관리 시스템 사용

### 4. 메타데이터 설정

```yaml
metadata:
  currency: KRW                                   # 기본 통화 설정
  
  data_source_rules:
  - actions:
      match_workspace:                            # 워크스페이스 매칭 액션
        source: additional_info.project_id        # 소스 필드
        target: data.project_id                   # 타겟 필드
    conditions_policy: ALWAYS                     # 조건 정책
    name: match_workspace                         # 규칙 이름
    options:
      stop_processing: true                       # 매칭 후 처리 중단
    resource_group: DOMAIN                        # 리소스 그룹
```

**분석 결과**: ✅ **잘 구성됨**
- 워크스페이스 매칭 규칙이 올바르게 설정됨
- `additional_info.project_id`를 통한 프로젝트 기반 매칭이 적절함
- 현재 구현 코드와 일치함 (확인됨)

### 5. 플러그인 실행 옵션

```yaml
options:
  source: gcs                                     # 데이터 소스
  bucket_name: spaceone-dev-billing-data          # GCS 버킷 이름
  account_id: aramco                              # 계정 ID
  select_cost: list_price                         # 비용 선택 기준
  
  field_mapper:
    cost: "cost"                                  # 비용 필드 매핑
    billed_date: "usage_start_time"               # 청구일 필드 매핑
    currency: "currency"                          # 통화 필드 매핑
  
  default_vars:
    provider: "google_cloud"                      # 기본 제공자
    currency: "KRW"                               # 기본 통화
```

**분석 결과**: ✅ **적절함** - HTTP 파일 모드로 올바르게 설정됨

#### 5.1. select_cost 옵션 상세 분석

`select_cost: list_price` 설정은 Google Cloud Billing 데이터에서 어떤 비용 필드를 사용할지 결정합니다.

**지원하는 비용 타입**:

| 옵션 값 | 대상 필드 | 설명 | 사용 시나리오 |
|:--------|:----------|:-----|:-------------|
| `cost` (기본값) | `cost` | 크레딧을 포함한 최종 실제 비용 | 실제 청구 금액 분석 |
| `list_price` | `cost_at_list` | 정가 (크레딧 적용 전 원가) | 할인 효과 분석, 예산 계획 |
| `after_credits` | `cost_after_credits` | 크레딧 적용 후 비용 | 크레딧 사용량 분석 |
| `net_cost` | `cost` | 순 비용 (기본 cost와 동일) | 회계 목적 순비용 분석 |

**현재 설정의 의미**:
- `select_cost: list_price` → 할인이나 크레딧 적용 전 정가를 기준으로 비용 데이터 수집
- 이는 비용 절감 효과 측정이나 예산 계획 수립에 유용함
- 실제 청구 금액과는 다를 수 있음 (할인/크레딧 미적용)

**구현 확인**:
```python
# src/plugin/manager/cost_manager.py:386-420
def _get_cost_field_by_option(self, row) -> float:
    """select_cost 옵션에 따라 적절한 비용 필드를 선택"""
    select_cost = self.select_cost_option or "cost"
    
    if select_cost == "list_price":
        return getattr(row, "cost_at_list", 0.0)  # 정가 사용
    elif select_cost == "after_credits":
        return getattr(row, "cost_after_credits", 0.0)
    # ... 기타 옵션들
```

**결과**: ✅ **정상 구현됨** - 모든 비용 타입이 올바르게 지원됨

### 6. 스케줄 설정

```yaml
schedule:
  state: ENABLED                                  # 스케줄 상태
  hour: 16                                        # 실행 시간 (16시 UTC)
```

**분석 결과**: ✅ **적절함** - 일일 자동 실행 스케줄이 올바르게 설정됨

## 🔍 현재 구현과의 호환성 검증

### 1. 워크스페이스 매칭 구현 상태

**설정값**: `source: additional_info.project_id`

**구현 확인**:
```python
# src/plugin/manager/cost_manager.py:336-340
"additional_info": {
    "Project ID": getattr(row, "id", ""),
    "Project Name": getattr(row, "project_name", ""),
    # ...
}
```

**결과**: ✅ **정상 동작** - 설정과 구현이 일치함

### 2. Field Mapper 호환성

**설정값**:
- `cost: "cost"`
- `billed_date: "usage_start_time"`
- `currency: "currency"`

**구현 확인**:
```python
# src/plugin/manager/field_mapper.py 에서 지원되는 필드들과 일치
```

**결과**: ✅ **정상 동작** - 모든 필드 매핑이 구현과 호환됨

### 3. 데이터 소스 타입 지원

**설정값**: `source: gcs` (HTTP 파일 모드)

**구현 확인**:
```python
# src/plugin/manager/cost_manager.py:79-86
if data_source_type == DATA_SOURCE_TYPES["http_file"]:
    yield from self._get_data_from_http_file(...)
else:
    yield from self._get_data_from_bigquery(...)
```

**결과**: ✅ **정상 동작** - HTTP 파일 모드가 완전히 구현됨

## ⚠️ 발견된 문제점 및 개선사항

### 1. 보안 문제 (긴급)

**문제**: 실제 서비스 계정 개인 키가 평문으로 노출됨

**해결방안**:
```yaml
# 보안 강화된 설정 예시
secret_data:
  type: service_account
  project_id: "${GCP_PROJECT_ID}"
  private_key: "${GCP_PRIVATE_KEY}"
  client_email: "${GCP_CLIENT_EMAIL}"
  # 기타 필요한 필드들도 환경변수로 처리
```

### 2. 플러그인 ID 명명 규칙

**문제**: 개발자 특정 이름이 포함됨

**해결방안**:
```yaml
plugin_info:
  plugin_id: plugin-google-billing-cost-datasource  # 표준 명명 규칙
  version: 1.0.0  # 의미 있는 버전 번호
```

### 3. 누락된 고급 기능 설정

**문제**: Pricing Data Export 관련 설정 부재

**해결방안**:
```yaml
options:
  # 기존 설정...
  
  # Pricing Data Export 지원 (향후 구현 예정)
  enable_pricing_analysis: false           # 현재는 비활성화
  pricing_export_project_id: ""            # 향후 Pricing Data 프로젝트 ID
  pricing_dataset_id: ""                   # 향후 Pricing Data 데이터셋 ID
  
  # 고급 분석 옵션
  enable_discount_analysis: true           # 할인 분석 활성화
  enable_credit_tracking: true             # 크레딧 추적 활성화
```

## 🎯 Google Cloud Pricing Data Export 연계 방안

### 1. 현재 상태

- ❌ Pricing Data Export 미지원
- ❌ `cloud_pricing_export` 테이블 처리 로직 없음
- ❌ 가격 분석 기능 부재

### 2. 연계를 위한 필수 구현 사항

#### A. 새로운 커넥터 추가
```python
# src/plugin/connector/pricing_connector.py (신규 필요)
class PricingConnector(BaseConnector):
    def get_pricing_data(self, date: str) -> Generator[dict, None, None]:
        """cloud_pricing_export 테이블에서 가격 데이터 조회"""
        pass
```

#### B. 설정 확장
```yaml
# register_datasource.yaml 확장안
options:
  # 기존 billing 관련 설정
  billing_export_project_id: "project-id"
  billing_dataset_id: "billing_export"
  billing_account_id: "123456-ABCDEF-789012"
  
  # 신규 pricing 관련 설정
  pricing_export_project_id: "project-id"      # NEW
  pricing_dataset_id: "pricing_export"         # NEW
  enable_pricing_comparison: true              # NEW
```

#### C. Field Mapper 확장
```yaml
field_mapper:
  # 기존 필드...
  
  # 신규 pricing 관련 필드
  list_price: "list_price"                     # NEW
  discount_rate: "discount_rate"               # NEW
  pricing_tier: "pricing_tier"                 # NEW
```

### 3. 구현 우선순위

1. **Phase 1** (즉시): 보안 문제 해결 및 기본 설정 정리
2. **Phase 2** (단기): Pricing Data Export 기본 연동
3. **Phase 3** (중기): 고급 가격 분석 기능 구현

## 📊 종합 평가

### 현재 구현 상태

| 항목 | 상태 | 점수 | 비고 |
|:---|:---|:---:|:---|
| **기본 설정** | ✅ 양호 | 9/10 | 표준 구성 준수 |
| **보안** | 🚨 심각 | 2/10 | 개인 키 노출 위험 |
| **호환성** | ✅ 우수 | 10/10 | 구현과 완벽 일치 |
| **확장성** | ⚠️ 보통 | 6/10 | Pricing Data 미지원 |
| **유지보수성** | ✅ 양호 | 8/10 | 명확한 구조 |

### 권장 조치사항

#### 즉시 조치 (Critical)
1. **서비스 계정 키 교체**: 현재 노출된 키 즉시 폐기 및 재생성
2. **환경변수 설정**: 모든 민감 정보를 환경변수로 전환
3. **플러그인 ID 정규화**: 표준 명명 규칙 적용

#### 단기 개선 (High Priority)
1. **Pricing Data Export 기본 지원**: 테이블 연동 및 기본 쿼리 구현
2. **설정 검증 로직**: 잘못된 설정에 대한 사전 검증 강화
3. **문서화 개선**: 설정 가이드 및 예시 보완

#### 중장기 개선 (Medium Priority)
1. **고급 분석 기능**: 할인율 계산, 가격 예측 등
2. **다중 데이터 소스**: Billing + Pricing 데이터 통합 분석
3. **자동화 개선**: 설정 템플릿 및 배포 자동화

## 🔗 관련 문서

- **[Pricing Data Export 가이드](../user-guide/pricing-data-export-guide.md)** - 새로 생성된 가이드
- **[워크스페이스 매칭 가이드](../../examples/workspace_matching_guide.md)** - 매칭 규칙 상세 설명
- **[보안 강화 가이드](../SECURITY_ENHANCEMENTS.md)** - 보안 설정 방법

---

> **⚠️ 중요**: 이 보고서에서 식별된 보안 문제는 **즉시 해결**이 필요합니다. 특히 노출된 서비스 계정 키는 악용될 위험이 높으므로 우선적으로 처리하시기 바랍니다.
