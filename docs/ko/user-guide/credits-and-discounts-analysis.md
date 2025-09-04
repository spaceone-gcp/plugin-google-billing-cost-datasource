# Google Cloud 크레딧 및 할인 분석 가이드

Google Cloud Billing 데이터의 크레딧(Credits)과 할인(Discounts) 정보를 활용한 상세 분석 방법을 안내합니다.

## 개요

Google Cloud는 다양한 형태의 크레딧과 할인을 제공하여 비용을 절감할 수 있도록 지원합니다. 이 문서는 SpaceONE에서 이러한 정보를 효과적으로 분석하는 방법을 설명합니다.

## 크레딧(Credits) 분석

### 크레딧 데이터 구조

Billing Export 데이터의 `credits` 필드는 다음과 같은 구조를 가집니다:

```json
{
  "credits": [
    {
      "name": "Sustained Use Discount",
      "amount": -12.34,
      "type": "SUSTAINED_USAGE_DISCOUNT",
      "id": "credit-id-12345"
    },
    {
      "name": "Free Trial Credit",
      "amount": -100.00,
      "type": "FREE_TRIAL",
      "id": "credit-id-67890"
    }
  ]
}
```

### 주요 크레딧 유형

#### 1. 자동 적용 할인

| 크레딧 유형 | Type 값 | 설명 | 적용 조건 |
|:---|:---|:---|:---|
| **지속 사용 할인** | `SUSTAINED_USAGE_DISCOUNT` | 월간 25% 이상 사용 시 자동 할인 | Compute Engine, GKE 등 |
| **약정 사용 할인** | `COMMITTED_USAGE_DISCOUNT` | 1년/3년 약정 기반 할인 | 사전 약정 필요 |
| **리소스 기반 CUD** | `COMMITTED_USAGE_DISCOUNT_DOLLAR_BASE` | 특정 리소스 약정 할인 | vCPU, 메모리 등 |

#### 2. 프로모션 크레딧

| 크레딧 유형 | Type 값 | 설명 | 사용 기간 |
|:---|:---|:---|:---|
| **무료 체험** | `FREE_TRIAL` | 신규 계정 $300 크레딧 | 90일 또는 소진 시까지 |
| **프로모션 크레딧** | `PROMOTION` | 마케팅 캠페인 크레딧 | 캠페인별 상이 |
| **교육 크레딧** | `EDUCATION_GRANT` | 교육 기관 지원 크레딧 | 학기별/연도별 |

### SpaceONE에서 크레딧 분석 활용

#### Field Mapper 설정

```yaml
field_mapper:
  cost: "cost"
  billed_date: "usage_start_time"
  currency: "currency"
  additional_info:
    # 크레딧 정보 매핑
    credits: "credits"
    cost_at_list: "cost_at_list"
    
    # 상세 분석을 위한 추가 필드
    service_description: "service.description"
    sku_description: "sku.description"
    project_id: "project.id"
    project_name: "project.name"
```

#### 크레딧 분석 활용 사례

1. **크레딧 유형별 절감액 추적**
   - `additional_info.credits.type`으로 그룹화
   - 각 크레딧 유형의 월별 절감 효과 측정

2. **프로모션 크레딧 소진 모니터링**
   - `FREE_TRIAL`, `PROMOTION` 타입 크레딧 추적
   - 잔여 크레딧 및 소진 예상일 계산

3. **자동 할인 효과 분석**
   - SUD, CUD 할인의 실제 절감 효과 측정
   - 워크로드 패턴 최적화 기회 식별

## 유효 할인(Effective Discount) 분석

### 유효 할인율 계산

정가(`cost_at_list`)와 실제 청구 비용(`cost`) 간의 차이로 전체 할인 효과를 측정합니다.

```
유효 할인율 = (정가 - 실제 비용) / 정가 × 100
```

### Field Mapper에서 할인 분석 설정

```yaml
field_mapper:
  cost: "cost"                    # 최종 청구 금액
  additional_info:
    cost_at_list: "cost_at_list"  # 정가 (할인 전)
    credits: "credits"            # 크레딧 상세 내역
    
    # 할인 효과 분석을 위한 추가 정보
    invoice_month: "invoice.month"
    service_description: "service.description"
    project_labels: "project.labels"
```

### 할인 분석 활용 방안

#### 1. 계약 기반 할인 검증
- 맞춤 가격 계약의 실제 할인율 확인
- 계약 조건 대비 실제 절감 효과 측정

#### 2. 서비스별 할인 효과 분석
- 서비스별로 어떤 할인이 가장 효과적인지 파악
- 할인 혜택이 큰 서비스 우선 사용 전략 수립

#### 3. 프로젝트별 비용 최적화
- 프로젝트별 할인율 비교
- 라벨 기반 팀별/환경별 할인 효과 분석

## BigQuery 쿼리 예시

### 1. 크레딧 유형별 월간 절감액

```sql
SELECT
  invoice.month,
  c.type as credit_type,
  c.name as credit_name,
  COUNT(*) as credit_applications,
  SUM(c.amount) as total_credit_amount,
  ROUND(SUM(c.amount), 2) as total_savings
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(credits) AS c
WHERE
  c.amount < 0  -- 크레딧은 음수로 표시
GROUP BY 1, 2, 3
ORDER BY 1, total_savings ASC;
```

### 2. 서비스별 유효 할인율 분석

```sql
SELECT
  service.description,
  SUM(cost_at_list) as total_list_cost,
  SUM(cost) as total_actual_cost,
  SUM(cost_at_list) - SUM(cost) as total_discount,
  ROUND(
    (SUM(cost_at_list) - SUM(cost)) / NULLIF(SUM(cost_at_list), 0) * 100, 
    2
  ) as effective_discount_percentage
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE
  cost_at_list > 0
  AND invoice.month = '202407'  -- 특정 월 분석
GROUP BY 1
HAVING total_list_cost > 10  -- $10 이상 서비스만
ORDER BY effective_discount_percentage DESC;
```

### 3. 프로모션 크레딧 소진 추적

```sql
SELECT
  DATE(usage_start_time) as usage_date,
  c.type as credit_type,
  SUM(c.amount) as daily_credit_usage,
  SUM(SUM(c.amount)) OVER (
    PARTITION BY c.type 
    ORDER BY DATE(usage_start_time)
  ) as cumulative_credit_usage
FROM
  `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`,
  UNNEST(credits) AS c
WHERE
  c.type IN ('FREE_TRIAL', 'PROMOTION')
  AND c.amount < 0
GROUP BY 1, 2
ORDER BY 1, 2;
```

## SpaceONE 대시보드 활용

### 권장 시각화

1. **크레딧 절감액 트렌드**
   - 시계열 차트로 월별 크레딧 절감액 추이
   - 크레딧 유형별 스택 차트

2. **유효 할인율 히트맵**
   - 서비스별 × 월별 할인율 매트릭스
   - 색상으로 할인 효과 구분

3. **프로모션 크레딧 잔액**
   - 게이지 차트로 잔여 크레딧 표시
   - 소진 예상일 알림

### 알림 설정 예시

```yaml
# 프로모션 크레딧 잔액 부족 알림
alert_conditions:
  - name: "프로모션 크레딧 잔액 부족"
    condition: "additional_info.credits.type = 'FREE_TRIAL' AND remaining_credit < 50"
    notification: "프로모션 크레딧이 $50 이하로 감소했습니다."

# 할인율 급감 알림  
  - name: "유효 할인율 급감"
    condition: "effective_discount_rate < 10 AND previous_month_rate > 20"
    notification: "유효 할인율이 전월 대비 크게 감소했습니다."
```

## 비용 최적화 전략

### 1. 자동 할인 최대화

- **지속 사용 할인 (SUD)**
  - 월간 25% 이상 사용량 유지
  - 워크로드 패턴 최적화

- **약정 사용 할인 (CUD)**
  - 1년/3년 약정을 통한 최대 57% 할인
  - 안정적인 워크로드에 적용

### 2. 프로모션 크레딧 활용

- 무료 체험 크레딧의 전략적 사용
- 교육/연구용 크레딧 최대 활용
- 크레딧 소진 전 추가 리소스 프로비저닝

### 3. 계약 협상 지원

- 실제 할인율 데이터를 통한 협상 근거 마련
- 서비스별 할인 효과 분석으로 계약 조건 최적화

## 참고 자료

### Google Cloud 공식 문서
- **[결제 보고서의 크레딧 분석](https://cloud.google.com/billing/docs/how-to/reports?hl=ko#credits)**
- **[가격표 보고서의 유효 할인](https://cloud.google.com/billing/docs/how-to/pricing-table?hl=ko#effective-discount)**
- **[약정 사용 할인 (CUD) 가이드](https://cloud.google.com/docs/cuds?hl=ko)**

### 관련 SpaceONE 문서
- **[Google Cloud Billing 통합 가이드](./integration-guide.md)**
- **[데이터 분석 가이드](./data-analysis-guide.md)**
- **[Field Mapper 개발 가이드](../development/field-mapper-guide.md)**

---

> **💡 팁**: 크레딧과 할인 분석은 정기적으로 수행하여 비용 최적화 기회를 놓치지 마세요. SpaceONE의 예산 및 알림 기능을 활용하면 더욱 효과적인 비용 관리가 가능합니다.
