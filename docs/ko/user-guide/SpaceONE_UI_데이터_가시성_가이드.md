# SpaceONE UI 데이터 가시성 가이드

##  개요

이 문서는 SpaceONE Cost Analysis UI에서 **mkkang-project 데이터가 보이지 않는 문제**를 해결하기 위한 단계별 가이드입니다.

**문제 상황**: 데이터는 존재하지만 UI에서 보이지 않음
**근본 원인**: UI 필터링 설정 + 최상위 cost 필드 누락
**최신 업데이트**: 2025년 9월 22일 Usage 데이터 타입 지원 완료

---

##  **NEW**: Usage 데이터 타입 지원 (v2.1)

### **SpaceONE UI Data Type 선택 가이드**

SpaceONE Cost Analysis는 이제 **두 가지 데이터 타입**을 완전 지원합니다:

#### ** Cost 데이터 타입 (비용 기반 분석)**
- **설정 방법**: Data Type → "Cost" 선택
- **표시 조건**: `cost > 0`인 데이터만 표시
- **용도**: 비용 최적화, 예산 관리, ROI 분석
- **예시 데이터**: $2.61, $5.59, $8.23 등

#### ** Usage 데이터 타입 (사용량 기반 분석)** ⭐ **NEW**
- **설정 방법**: Data Type → "Usage" 선택  
- **표시 조건**: `usage_quantity > 0`인 데이터만 표시
- **용도**: 리소스 사용량 최적화, 효율성 분석
- **예시 데이터**:
  - Networking: `4,812 seconds`, `10,800 seconds`
  - Compute Engine: `6.889e+12 byte-seconds`, `3.152e+14 byte-seconds`
  - Storage: `81GB PD 스토리지 = 315조 byte-seconds`

#### ** 사용 시나리오별 권장사항**

| **분석 목적** | **권장 Data Type** | **이유** |
|---------------|-------------------|----------|
| 비용 절감 방안 | **Cost** | 실제 지출 금액 기준 분석 |
| 리소스 효율성 | **Usage** | 실제 사용량 기준 최적화 |
| 예산 계획 | **Cost** | 비용 예측 및 관리 |
| 성능 최적화 | **Usage** | 리소스 활용도 분석 |

### **사용량 데이터 해석 가이드**

#### **Networking 서비스**
```
usage_quantity: 4,812
usage_unit: seconds
→ 해석: Cloud NAT Gateway가 4,812초(약 1.34시간) 동안 활성화됨
```

#### **Compute Engine 스토리지**
```
usage_quantity: 3.152505995264e+14
usage_unit: byte-seconds  
→ 해석: 81GB Persistent Disk를 1시간 동안 사용
→ 계산: 315조 byte-seconds ÷ 3600초 = 87.6GB 평균 용량
```

---

##  **즉시 해결 방법 (UI 설정)**

### **1단계: 필터 설정 확인**

#### **Filters 버튼 클릭 → 설정 확인**
```
1. SpaceONE Cost Analysis 화면에서 "Filters" 버튼 클릭
2. 현재 활성화된 필터 확인:
   -  "Cost > 0" 필터가 있다면 → 제거 또는 "Cost >= 0"으로 변경
   -  "Hide zero cost items" 옵션이 활성화되어 있다면 → 비활성화
   -  프로젝트 필터에서 "mkkang-project"가 제외되어 있다면 → 포함시키기
```

#### **권장 필터 설정:**
- **Cost 필터**: "Cost >= 0" (0원 포함)
- **Date Range**: "2025-09-01 ~ 2025-09-30" (명시적 설정)
- **Project**: "All Projects" 또는 "mkkang-project" 포함
- **Data Source**: "Aramco GCP Cloud Bill" 선택 확인

### **2단계: 날짜 범위 설정**

```
Period: Last 6 Months → "Custom Range"로 변경
Start Date: 2025-09-01
End Date: 2025-09-30
```

### **3단계: 데이터 새로고침**

```
1. 설정 변경 후 "Apply" 또는 "Search" 버튼 클릭
2. 브라우저 새로고침 (F5)
3. 데이터가 나타나는지 확인
```

---

##  **예상 결과 데이터**

설정이 올바르게 되면 다음 mkkang-project 데이터가 표시되어야 합니다:

### **비용 발생 항목들:**
| Product | Usage Type | Cost (KRW) | Date |
|---------|------------|------------|------|
| **Compute Engine** | Hyperdisk Balanced Capacity | **1,217.85** | 2025-09-15 |
| **Compute Engine** | 기타 서비스 | **4,284.90** | 2025-09-15 |
| **BigQuery** | Analysis | **382.61** | 2025-09-15 |
| **Cloud Key Management Service** | Active key versions | **1.83** | 2025-09-15 |
| **Artifact Registry** | Storage | **1.25** | 2025-09-15 |

### **무료 사용량 항목들 (0원):**
| Product | Usage Type | Cost | Date |
|---------|------------|------|------|
| **BigQuery** | Active Logical Storage | 0.0 KRW | 2025-09-15 |
| **Cloud Build** | Build time | 0.0 KRW | 2025-09-15 |
| **기타 서비스들** | 다양한 무료 사용량 | 0.0 KRW | 2025-09-15 |

---

##  **고급 해결 방법**

### **UI에서 여전히 안 보이는 경우:**

#### **1. 브라우저 개발자 도구 확인**
```javascript
// 브라우저 콘솔에서 실행
console.log("Current filters:", window.spaceone?.filters);
console.log("Data source:", window.spaceone?.dataSource);
```

#### **2. 데이터 소스 재연결**
```
1. Data Source 설정 페이지로 이동
2. "Aramco GCP Cloud Bill" 데이터 소스 상태 확인
3. "Test Connection" 실행
4. 필요시 재연결
```

#### **3. 권한 확인**
```
1. 현재 사용자가 "mkkang-project" 데이터에 접근 권한이 있는지 확인
2. Cost Analysis 모듈 접근 권한 확인
3. 필요시 관리자에게 권한 요청
```

---

##  **데이터 검증 방법**

### **1. 원시 데이터 확인**
```
1. SpaceONE API 직접 호출로 데이터 존재 확인
2. grpcurl 결과와 UI 표시 결과 비교
3. 로그에서 데이터 처리 상태 확인
```

### **2. 집계 결과 확인**
```
예상 총 비용: ~6,000+ KRW (2025년 9월)
예상 레코드 수: 4,271개 (집계 전), 수백 개 (집계 후)
```

---

##  **최종 체크리스트**

### **UI 설정 체크리스트:**
- [ ] Filters에서 "Cost >= 0" 설정
- [ ] "Hide zero cost" 옵션 비활성화
- [ ] Date Range: 2025-09-01 ~ 2025-09-30
- [ ] Project: "mkkang-project" 포함
- [ ] Data Source: "Aramco GCP Cloud Bill" 선택
- [ ] 브라우저 새로고침 실행

### **예상 결과 체크리스트:**
- [ ] mkkang-project 프로젝트가 목록에 표시됨
- [ ] 9월 데이터가 차트에 표시됨
- [ ] 총 비용 ~6,000+ KRW 표시
- [ ] 주요 서비스 (Compute Engine, BigQuery 등) 표시

---

##  **여전히 문제가 있다면**

### **즉시 연락:**
1. **로그 확인**: 플러그인 로그에서 "ULTIMATE" 키워드 검색
2. **에러 메시지**: cost 필드 관련 에러 메시지 확인  
3. **기술 지원**: 개발팀에 다음 정보 제공:
   - 현재 필터 설정 스크린샷
   - 브라우저 개발자 도구 콘솔 로그
   - 예상 데이터와 실제 표시 데이터 비교

**이 가이드를 따르면 mkkang-project 데이터가 SpaceONE UI에 정상적으로 표시될 것입니다!** 
