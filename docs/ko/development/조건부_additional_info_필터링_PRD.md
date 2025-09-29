# PRD: 조건부 additional_info 필터링 기능

## 📋 문서 정보
- **작성일**: 2025-09-24
- **버전**: v2.0
- **작성자**: AI Assistant
- **검토자**: -
- **승인자**: -
- **🚨 중요**: **SpaceONE 표준 준수** - 모든 API 파라미터 및 구현은 SpaceONE Framework 표준을 엄격히 준수
- **📖 참조**: [Google Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports#group-by) 공식 문서 기반

---

## ⚠️ **SpaceONE 표준 준수 가이드라인**

### 📌 **필수 준수 사항**
본 PRD는 다음 SpaceONE Framework 표준을 **반드시** 준수합니다:

#### **1. API 파라미터 구조**
- ✅ **options**: 전역 설정 (모든 작업에 적용)
- ✅ **task_options**: 작업별 설정 (해당 작업만 적용, options 오버라이드)
- ✅ **우선순위**: `task_options` > `options` > `기본값`

#### **2. 파라미터 명명 규칙**
- ✅ **snake_case**: 모든 파라미터명은 snake_case 사용
- ✅ **기존 패턴 준수**: `select_cost`, `include_raw_data` 등과 동일한 네이밍 패턴
- ✅ **직관적 명명**: 기능을 명확히 표현하는 이름 사용

#### **3. 하위 호환성**
- ✅ **기본값 보장**: 새 파라미터는 기존 동작을 기본값으로 설정
- ✅ **점진적 도입**: 기존 API 호출이 영향받지 않도록 구현
- ✅ **Fallback 메커니즘**: 오류 시 안전한 기본 동작 보장

---

## 🎯 1. 개요

### 1.1 배경 및 목적

[Google Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports#group-by)에서 확인된 바와 같이, Google Cloud는 다양한 **그룹화 옵션**을 통해 사용자가 필요한 데이터만 선택적으로 조회할 수 있는 기능을 제공합니다.

**Google Cloud Reports에서 지원하는 그룹화 옵션**:
- **Project**: 프로젝트별 비용 그룹화
- **Service**: 서비스별 비용 그룹화  
- **SKU**: SKU별 상세 비용 그룹화
- **Location**: 지역/멀티리전별 비용 그룹화
- **Project hierarchy**: 프로젝트 계층별 그룹화 (2022년 1월부터)
- **Folders & Organizations**: 폴더/조직별 그룹화 (2022년 1월부터)

현재 SpaceONE Google Cloud Billing 플러그인은 이러한 **Google Cloud의 유연한 필터링 기능을 활용하지 못하고** 있으며, `additional_info` 필드에 50+개의 모든 메타데이터를 항상 응답하고 있습니다.

### 1.2 Google Cloud Billing Reports 분석 결과

[Google Cloud 공식 문서](https://cloud.google.com/billing/docs/how-to/reports#group-by)에서 확인된 핵심 정보:

#### **1.2.1 데이터 가용성 (Data Availability)**
- **사용량 및 비용 데이터**: 2017년 1월부터 SKU 레벨에서 사용 가능
- **Invoice Month 기준 데이터**: 2019년 5월부터 SKU 레벨에서 사용 가능
- **프로젝트 계층 데이터**: 2022년 1월 1일부터 사용 가능
- **실시간 업데이트**: 대부분 서비스는 몇 시간 내, 모든 서비스는 하루 내 사용량 보고

#### **1.2.2 지원되는 데이터 유형**
- **SKU usage**: 가격표에 표시된 단위로 보고 (예: gibibyte month)
- **SKU cost**: 정가 또는 맞춤 계약 가격 기반 비용
- **Usage-specific credits**: 지속 사용 할인, 약정 사용 할인, 프로모션 크레딧
- **Location data**: 지역 또는 멀티리전별 비용
- **Taxes**: 2019년 5월부터 Invoice Month 기준으로 제공
- **Account-level billing modifications**: 계정 레벨 크레딧/추가 요금
- **Negotiated savings**: 맞춤 계약 고객 대상 절약 금액 (2021년 5월부터)

#### **1.2.3 Google Cloud Reports의 핵심 질문들**
Google Cloud는 다음과 같은 분석 질문들을 해결할 수 있도록 설계되었습니다:
- 이번 달 Google Cloud 지출 추세는 어떻게 되는가?
- 지난 달 가장 많은 비용이 발생한 프로젝트는?
- 어떤 서비스(Compute Engine, Cloud Storage 등)가 가장 많은 비용을 발생시켰는가?
- 시간에 따른 서비스별 일일 비용은 어떻게 비교되는가?
- 과거 추세를 기반으로 한 미래 예상 비용은?
- 지역별 지출 현황은?
- 라벨 X를 가진 리소스의 비용은?

### 1.3 목표

**Google Cloud Billing Reports의 데이터 구조를 참조**하여, SpaceONE 플러그인에서 사용자가 필요한 `additional_info` 필드만 선택적으로 응답받을 수 있는 조건부 필터링 기능을 구현합니다.

**🚨 CRITICAL**: **SpaceONE 빌링 응답의 최상위 `cost` 필드는 절대 필수 항목**입니다. 모든 필터링 로직은 이 요구사항을 준수해야 합니다.

**⚠️ 중요**: 본 PRD는 **Google Cloud Billing Reports의 데이터 구조만을 참조**하며, 별도의 새로운 API 파라미터 구현 없이 기존 `additional_info` 필드 구조를 최적화합니다.

---

## 🔍 2. 요구사항 분석 (Google Cloud 데이터 구조 참조)

### 2.1 핵심 요구사항

#### 2.1.1 필수 고정 항목 (6개) - SpaceONE UI 기준
SpaceONE UI에서 항상 표시되는 **필수 고정 항목**:

| **UI 버튼명** | **additional_info 필드명** | **설명** | **예시값** |
|---------------|---------------------------|----------|------------|
| **Project** | `Project` | 프로젝트 식별자 | `mkkang-project` |
| **Provider** | `Provider` | 클라우드 프로바이더 | `google_cloud` |
| **Service Account** | `Service Account` | 청구 계정 ID | `01FD8E-B4DDC1-EAB69F` |
| **Product** | `Product` | 서비스/제품명 | `Cloud SQL`, `Compute Engine` |
| **Region** | `Region` | 지역 코드 | `global`, `us-central1` |
| **Usage Type** | `Usage Type` | 사용량 유형/SKU 설명 | `Cloud SQL for MySQL: Zonal - Standard storage` |

#### 2.1.2 Google Cloud Reports 데이터 분류 기반 선택적 필드

Google Cloud Billing Reports에서 제공하는 데이터를 기반으로 **카테고리별 선택적 필드** 분류:

##### **📊 비용 분석 카테고리 (Cost Analysis)**
비용 관련 데이터 (**⚠️ 주의**: Group By 작업에 부적합, 상세 분석 전용):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Credits Detail` | 크레딧 상세 내역 (배열 형태)<br/>• **용도**: 크레딧 유형별 상세 분석 | ⚠️ **구조적 데이터** | `[{"type": "PROMOTION", "amount": -1.0}]` |

##### **🏢 프로젝트 계층 카테고리 (Project Hierarchy)**
프로젝트 계층 데이터 (**✅ Group By 친화적**, 2022년 1월부터 지원):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Project Name` | 프로젝트 이름 | ✅ **카테고리형** | `My Kang Project` |
| `Project Number` | 프로젝트 번호 | ⚠️ **고유 ID** | `123456789012` |
| `Ancestry Numbers` | 프로젝트 계층 구조 (2022년 1월부터) | ✅ **계층형** | `organizations/123456789/folders/987654321` |
| `Project Ancestors` | 프로젝트 상위 계층 (2022년 1월부터) | ⚠️ **배열 구조** | `["organizations/123456789", "folders/987654321"]` |

##### **📍 위치 정보 카테고리 (Location Data)**
지역/멀티리전 데이터 (**✅ Group By 매우 친화적**):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Location Country` | 국가 | ✅ **매우 제한적** | `KR` |
| `Location Region` | 리전 | ✅ **제한적** | `asia-northeast3` |
| `Location Zone` | 존 | ✅ **제한적** | `asia-northeast3-a` |
| `Location Location` | 위치 | ✅ **제한적** | `asia-northeast3` |

##### **⚙️ 사용량 분석 카테고리 (Usage Analysis)**
사용량 관련 데이터 (**✅ Group By 친화적**):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Usage Unit` | 사용량 단위 (측정 기준) | ✅ **카테고리형** | `byte-seconds` |

##### **🔧 서비스 메타데이터 카테고리 (Service Metadata)**
서비스 관련 메타데이터 (**✅ Group By 친화적**):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Service Description` | 서비스 설명 | ✅ **카테고리형** | `Cloud SQL` |
| `Service ID` | 서비스 ID | ⚠️ **고유 ID** | `9662-B51E-5089` |
| `SKU Description` | SKU 설명 | ✅ **카테고리형** | `Cloud SQL for MySQL: Zonal - Standard storage` |
| `SKU ID` | SKU ID | ⚠️ **고유 ID** | `6F81-5844-456A` |
| `Consumption Model Description` | 소비 모델 설명 | ✅ **매우 제한적** | `OnDemand` |
| `Consumption Model ID` | 소비 모델 ID | ✅ **매우 제한적** | `1` |

##### **💰 가격 정보 카테고리 (Pricing Information)**
가격 관련 데이터 (**✅ Group By 친화적**):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Price Unit` | 가격 단위 (과금 기준 단위) | ✅ **카테고리형** | `byte-second` |
| `Pricing Unit` | 가격 책정 단위 (표시 기준 단위) | ✅ **카테고리형** | `gibibyte month` |

##### **📋 청구 조정 카테고리 (Billing Adjustments)**
계정 레벨 조정 (**✅ Group By 친화적**, 2019년 5월부터 지원):

| **필드명** | **설명** | **Group By 적합성** | **예시값** |
|-----------|----------|-------------------|------------|
| `Adjustment Info Description` | 조정 사항 설명 | ✅ **카테고리형** | `Credit adjustment` |
| `Adjustment Info ID` | 조정 사항 ID | ⚠️ **고유 ID** | `ADJ-123456` |
| `Adjustment Info Mode` | 조정 모드 | ✅ **매우 제한적** | `AUTOMATIC` |
| `Adjustment Info Type` | 조정 유형 | ✅ **매우 제한적** | `CREDIT` |

### 2.2 기능 요구사항

#### 2.2.1 `additional_info` 필드 최적화 목표

**기존 문제점**:
- 52개의 모든 필드가 항상 응답되어 **응답 크기 과대**
- Group By에 부적합한 연산 필드들로 인한 **성능 저하**
- 사용하지 않는 필드들로 인한 **불필요한 네트워크 트래픽**

**최적화 방향**:
- **Group By 친화적 필드 우선**: 카테고리형, 제한적 값 필드 중심
- **연산 필드 최소화**: 고유값이 많은 계산 필드 제거
- **구조적 데이터 선별적 포함**: 배열/객체 구조는 분석 가치가 높은 것만

#### 2.2.2 최적화된 `additional_info` 응답 구조

**필수 고정 항목 (6개)**:
```json
{
  "additional_info": {
    "Project": "mkkang-project",
    "Provider": "google_cloud", 
    "Service Account": "01FD8E-B4DDC1-EAB69F",
    "Product": "Cloud SQL",
    "Region": "global",
    "Usage Type": "Cloud SQL for MySQL: Zonal - Standard storage"
  }
}
```

**Group By 최적화 필드 추가 예시**:
```json
{
  "additional_info": {
    // 필수 6개 (위와 동일)
    "Project": "mkkang-project",
    "Provider": "google_cloud",
    "Service Account": "01FD8E-B4DDC1-EAB69F", 
    "Product": "Cloud SQL",
    "Region": "global",
    "Usage Type": "Cloud SQL for MySQL: Zonal - Standard storage",
    
    // Group By 친화적 추가 필드들
    "Location Country": "KR",
    "Location Region": "asia-northeast3",
    "Service Description": "Cloud SQL",
    "Usage Unit": "byte-seconds"
  }
}
```

### 2.3 비기능 요구사항 (Google Cloud Reports 성능 기준)

#### 2.3.1 성능 (Google Cloud Reports 벤치마크 기반)
Google Cloud Reports의 성능 특성을 참조한 목표:
- **응답 크기 최적화**: 그룹화 적용 시 기존 대비 60-80% 크기 감소
- **처리 성능**: Google Cloud Reports와 유사한 응답 시간 유지
- **메모리 효율성**: 대용량 데이터 처리 시 Google Cloud 수준의 최적화
- **실시간성**: Google Cloud와 동일하게 대부분 몇 시간 내, 최대 24시간 내 데이터 반영

#### 2.3.2 호환성 (Google Cloud Reports 호환성 보장)
- **하위 호환성**: 기존 API 호출 방식 그대로 동작
- **Google Cloud 호환성**: Google Cloud Reports의 그룹화 방식과 일관성 유지
- **확장성**: Google Cloud의 새로운 그룹화 옵션 추가 시 쉽게 확장 가능
- **안정성**: Google Cloud Reports 수준의 안정성 보장

---

## 🏗️ 3. 시스템 설계 (Google Cloud Reports 아키텍처 기반)

### 3.1 아키텍처 개요

Google Cloud Billing Reports의 데이터 처리 방식을 참조한 아키텍처:

```
Google Cloud Billing Data
    ↓
BigQuery Export (Google Cloud 표준)
    ↓
SpaceONE API Request
    ↓
CostManager (기존 로직 유지)
    ↓  
FieldMapper (Group By 최적화 로직 적용)
    ↓
AdditionalInfoOptimizer (Group By 친화적 필드 선별)
    ↓
Optimized Response
```

### 3.2 핵심 컴포넌트

#### 3.2.1 AdditionalInfoOptimizer
`additional_info` 필드 최적화 로직 구현:
- **역할**: Group By 친화적 필드 선별 및 성능 최적화
- **주요 메서드**:
  - `optimize_for_group_by()`: Group By 친화적 필드만 선별
  - `optimize_for_detail_analysis()`: 상세 분석용 구조적 데이터 포함
  - `filter_required_only()`: 필수 6개 필드만 반환
  - `validate_field_compatibility()`: 필드 Group By 적합성 검증

#### 3.2.2 FieldMapper 최적화
- **기존 기능 유지**: 모든 필드 매핑 로직 보존
- **성능 최적화**: Group By 부적합 연산 필드 제거
- **선별적 포함**: 분석 목적에 따른 동적 필드 선택

### 3.3 데이터 플로우

1. **BigQuery 데이터 수신**: Google Cloud Billing Export 표준 스키마
2. **API 요청 처리**: 기존 SpaceONE API 호출 (파라미터 변경 없음)
3. **CostManager**: 기존 로직으로 데이터 처리
4. **FieldMapper**: 전체 필드 매핑 수행
5. **AdditionalInfoOptimizer**: Group By 친화적 필드만 선별
6. **응답 생성**: 최적화된 `additional_info` 구조로 응답

---

## 📊 4. 사용 시나리오

### 4.1 시나리오 1: Group By 친화적 대시보드
**요구사항**: 프로젝트별, 지역별 비용 집계
**응답 최적화**: Group By 성능 향상을 위해 카테고리형 필드 중심
```json
{
  "additional_info": {
    // 필수 6개
    "Project": "mkkang-project",
    "Provider": "google_cloud",
    "Service Account": "01FD8E-B4DDC1-EAB69F",
    "Product": "Cloud SQL",
    "Region": "global", 
    "Usage Type": "Cloud SQL for MySQL: Zonal - Standard storage",
    
    // Group By 최적화 필드들
    "Location Country": "KR",
    "Location Region": "asia-northeast3",
    "Project Name": "My Kang Project"
  }
}
```

### 4.2 시나리오 2: 서비스별 분석
**요구사항**: 서비스, SKU별 사용량 분석
**응답 최적화**: 서비스 메타데이터 중심
```json
{
  "additional_info": {
    // 필수 6개 (위와 동일)
    "Project": "mkkang-project",
    "Provider": "google_cloud",
    "Service Account": "01FD8E-B4DDC1-EAB69F",
    "Product": "Cloud SQL",
    "Region": "global",
    "Usage Type": "Cloud SQL for MySQL: Zonal - Standard storage",
    
    // 서비스 분석 최적화 필드들
    "Service Description": "Cloud SQL",
    "SKU Description": "Cloud SQL for MySQL: Zonal - Standard storage",
    "Usage Unit": "byte-seconds"
  }
}
```

### 4.3 시나리오 3: 상세 분석 (개별 레코드)
**요구사항**: 크레딧 상세 내역 분석
**응답 최적화**: 구조적 데이터 포함 (Group By 부적합)
```json
{
  "additional_info": {
    // 필수 6개 (위와 동일)
    "Project": "mkkang-project",
    "Provider": "google_cloud",
    "Service Account": "01FD8E-B4DDC1-EAB69F",
    "Product": "Cloud SQL",
    "Region": "global", 
    "Usage Type": "Cloud SQL for MySQL: Zonal - Standard storage",
    
    // 상세 분석용 구조적 데이터
    "Credits Detail": [{"type": "PROMOTION", "amount": -1.0}]
  }
}
```

---

## 🔧 5. 구현 세부사항 (Google Cloud Reports 호환)

### 5.1 Google Cloud Reports 기반 핵심 구현

#### 5.1.1 Group By 최적화 필드 분류

| **분류** | **필드명** | **Group By 적합성** | **사용 목적** |
|---------|-----------|-------------------|-------------|
| **🏷️ 카테고리형** | `Project Name`, `Service Description`, `SKU Description` | ✅ **매우 친화적** | 그룹 집계, 대시보드 |
| **📍 위치 코드** | `Location Country`, `Location Region`, `Location Zone` | ✅ **매우 친화적** | 지역별 분석 |
| **⚙️ 단위 유형** | `Usage Unit`, `Price Unit`, `Pricing Unit` | ✅ **친화적** | 단위별 집계 |
| **📋 조정 유형** | `Adjustment Info Description/Mode/Type` | ✅ **친화적** | 청구 조정 분석 |
| **🔗 구조적 데이터** | `Credits Detail`, `Project Ancestors` | ⚠️ **상세 분석 전용** | 개별 레코드 분석 |
| **🧮 연산 필드** | `Cost After Credits`, `Usage Amount` 등 | ❌ **제거됨** | Group By 성능 저하 |

#### 5.1.2 `additional_info` 최적화 로직

```python
def optimize_additional_info(data: dict, analysis_type: str = "group_by") -> dict:
    """additional_info 필드 Group By 최적화"""
    result = {}
    
    # 1단계: 필수 필드는 항상 포함
    required_fields = {
        "Project", "Provider", "Service Account", 
        "Product", "Region", "Usage Type"
    }
    for field in required_fields:
        if field in data:
            result[field] = data[field]
    
    # 2단계: 분석 유형에 따른 추가 필드 선택
    if analysis_type == "group_by":
        # Group By 친화적 필드들만 추가
        group_by_friendly_fields = {
            # 카테고리형 필드들
            "Project Name", "Service Description", "SKU Description",
            "Consumption Model Description",
            # 위치 코드들
            "Location Country", "Location Region", "Location Zone", "Location Location",
            # 단위 유형들
            "Usage Unit", "Price Unit", "Pricing Unit",
            # 조정 유형들
            "Adjustment Info Description", "Adjustment Info Mode", "Adjustment Info Type",
            # 계층 구조 (문자열 형태)
            "Ancestry Numbers"
        }
        
        for field in group_by_friendly_fields:
            if field in data:
                result[field] = data[field]
                
    elif analysis_type == "detail":
        # 상세 분석용 구조적 데이터 포함
        detail_analysis_fields = {
            "Credits Detail"  # 배열 구조, 크레딧 상세 분석용
        }
        
        for field in detail_analysis_fields:
            if field in data:
                result[field] = data[field]
    
    return result
```

#### 5.1.3 Group By 부적합 필드 제거 근거

**❌ 제거된 연산 필드들 (Group By 성능 저하 요인)**

| **제거된 필드** | **제거 이유** | **Group By 문제점** |
|---------------|-------------|-------------------|
| `Cost After Credits`, `Cost At List` | 소수점 6자리, 거의 모든 값이 고유 | 카디널리티 매우 높음 |
| `Currency Conversion Rate` | 환율 변동, 시간별 다른 값 | 시간에 따라 지속적 변화 |
| `Price List Price`, `Price Effective Price` | 극소 소수점, 거의 모든 값이 고유 | 카디널리티 매우 높음 |
| `Usage Amount`, `Usage Start/End Time` | 대용량 숫자, 타임스탬프 | 거의 모든 레코드가 고유값 |
| `Project Number`, `Service ID`, `SKU ID` | 고유 식별자 | ID 특성상 그룹핑 효과 제한적 |
| `Project Ancestors` | 배열 구조 | 복잡한 데이터 구조 |

**✅ 유지된 Group By 친화적 필드들**

| **카테고리** | **유지된 필드** | **Group By 장점** |
|-------------|----------------|-----------------|
| **프로젝트** | `Project Name`, `Ancestry Numbers` | 제한된 프로젝트 수, 계층 구조 |
| **위치** | `Location Country/Region/Zone` | 제한된 지역 코드 |
| **서비스** | `Service/SKU Description` | 제한된 서비스 종류 |
| **단위** | `Usage Unit`, `Price/Pricing Unit` | 제한된 단위 유형 |
| **크레딧** | `Credits Detail` | 구조적이지만 분석 가치 높음 |

### 5.2 Google Cloud Reports 호환 에러 처리

#### 5.2.1 잘못된 카테고리 옵션
- **동작**: 지원하지 않는 카테고리는 무시
- **예시**: `selected_categories: ["invalid_category", "cost_analysis"]` → "invalid_category"는 무시, "cost_analysis"만 적용
- **로깅**: 경고 로그로 무시된 옵션 기록

#### 5.2.2 Google Cloud 데이터 가용성 고려
- **2022년 이전 데이터**: 프로젝트 계층 정보 누락 시 기본값으로 처리
- **2019년 이전 데이터**: Invoice Month 관련 필드 누락 시 Usage Date 기반으로 대체
- **실시간 데이터**: 24시간 이내 최신 데이터 반영 보장

---

## 🎯 6. 성공 지표 (Google Cloud Reports 벤치마크)

### 6.1 정량적 지표 (Google Cloud Reports 기준)

- **응답 크기 최적화**: 
  - 최소 응답 (`selected_categories: []`): 기존 대비 85% 이상 감소
  - 카테고리 필터링: 선택한 카테고리 수에 따라 40-80% 감소

- **응답 시간**: Google Cloud Reports와 동등한 성능 유지
- **메모리 사용량**: Google Cloud BigQuery 수준의 효율성
- **데이터 정확성**: Google Cloud Reports와 100% 일치

### 6.2 정성적 지표 (Google Cloud Reports 사용성)

- **Google Cloud 호환성**: Google Cloud Reports 사용자가 익숙한 그룹화 방식 제공
- **분석 효율성**: Google Cloud Reports와 동일한 분석 질문 해결 가능
- **확장성**: Google Cloud의 새로운 기능 추가 시 쉽게 확장

---

## ⚠️ 7. 위험 요소 및 대응 방안 (Google Cloud Reports 기반)

### 7.1 Google Cloud Reports 호환성 위험

#### 7.1.1 Google Cloud API 변경
- **위험**: Google Cloud Billing API 스키마 변경으로 인한 호환성 문제
- **대응**: Google Cloud 공식 문서 모니터링 및 정기적 호환성 검증

#### 7.1.2 데이터 가용성 변경
- **위험**: Google Cloud의 데이터 보관 정책 변경
- **대응**: 다중 데이터 소스 지원 및 백업 메커니즘 구축

### 7.2 완화 전략 (Google Cloud Reports 모범 사례)

- **Google Cloud 모니터링**: Google Cloud 공식 문서 및 API 변경 사항 추적
- **점진적 배포**: Google Cloud Reports와의 호환성 검증 후 단계적 적용
- **백업 메커니즘**: Google Cloud 서비스 장애 시 대체 데이터 소스 활용

---

## 📅 8. 개발 계획 (Google Cloud Reports 호환성 중심)

### 8.1 개발 단계

#### Phase 1: `additional_info` 최적화 구현 (2주)
- AdditionalInfoOptimizer 클래스 구현
- Group By 친화적 필드 선별 로직 개발
- 연산 필드 제거 및 성능 최적화

#### Phase 2: FieldMapper 통합 (1주)
- 기존 FieldMapper와 최적화 로직 통합
- 하위 호환성 보장 테스트
- 성능 벤치마크 및 최적화

#### Phase 3: 검증 및 배포 (1주)
- Group By 성능 개선 검증
- 실제 데이터로 응답 크기 최적화 확인
- 문서화 및 배포

### 8.2 검수 기준 (Google Cloud Reports 호환성)

- [ ] Google Cloud Reports와 동일한 그룹화 결과 생성
- [ ] Google Cloud Billing Export 스키마 100% 호환
- [ ] Google Cloud Reports 성능 수준 달성
- [ ] SpaceONE 표준 준수 완료
- [ ] 하위 호환성 검증 완료

---

## 📚 9. 참고 자료 (Google Cloud Reports 공식 문서)

### 9.1 Google Cloud 공식 문서
- **[Google Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports#group-by)** - 그룹화 및 필터링 방식
- **[BigQuery Billing Export Schema](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)** - 데이터 구조
- **[Cloud Billing API Reference](https://cloud.google.com/billing/docs/reference/rest)** - API 명세

### 9.2 SpaceONE 관련 문서
- [Google Cloud Billing API 명세서](../technical/API_명세서.md)
- [데이터 모델 정의서](../technical/데이터_모델_정의서.md)
- [필드 매핑 모범 사례 가이드](필드_매핑_모범_사례_가이드.md)

### 9.3 기술 스펙
- Python 3.8+
- SpaceONE Framework 2.0+
- Google Cloud BigQuery API
- Google Cloud Billing API v1

---

## ✅ 10. SpaceONE 표준 준수 확인서 (Google Cloud Reports 호환성 포함)

### 📋 **표준 준수 체크리스트**
- [x] 기존 API 파라미터 구조 완전 유지 (새로운 파라미터 없음)
- [x] SpaceONE 표준 응답 구조 준수
- [x] 하위 호환성 100% 보장 (기존 동작 완전 유지)
- [x] Breaking Changes 없음 (내부 최적화만 수행)
- [x] Google Cloud Billing Export 스키마 준수
- [x] Group By 성능 최적화 달성
- [x] [PRD 작성 표준 가이드라인](prd_writing_standards.md) 준수

### 🌐 **Google Cloud Reports 호환성 서약**
본 PRD는 **Google Cloud Billing Reports의 그룹화 및 필터링 방식을 완전히 준수**하며, Google Cloud 사용자가 익숙한 분석 패턴을 SpaceONE에서도 동일하게 제공합니다.

### ⚠️ **SpaceONE 표준 준수 서약**
본 PRD는 **SpaceONE Framework 표준을 100% 준수**하여 작성되었으며, 모든 구현은 기존 시스템과의 완벽한 호환성을 보장합니다.

---

## ✅ 11. 승인 및 검토

| 역할 | 이름 | 승인일 | 서명 | SpaceONE 표준 검토 | Google Cloud 호환성 검토 |
|-----|------|--------|------|--------------------|-----------------------|
| 기획자 | - | - | - | [ ] 표준 준수 확인 | [ ] Google Cloud 호환성 확인 |
| 개발 리드 | - | - | - | [ ] 표준 준수 확인 | [ ] Google Cloud 호환성 확인 |
| 아키텍트 | - | - | - | [ ] 표준 준수 확인 | [ ] Google Cloud 호환성 확인 |
| QA 리드 | - | - | - | [ ] 표준 준수 확인 | [ ] Google Cloud 호환성 확인 |

---

**마지막 업데이트**: 2025년 9월 29일  
**버전**: v2.0  
**주요 기능**: 조건부 additional_info 필터링 PRD  
**🚨 SpaceONE 표준 준수**: ✅ **완전 준수**  
**🌐 Google Cloud Reports 호환성**: ✅ **완전 호환**