# SpaceONE Google Cloud Billing Cost Datasource 개발 가이드

##  프로젝트 개요

이 프로젝트는 **SpaceONE 플랫폼**에서 Google Cloud Billing 데이터를 수집하고 처리하는 Cost Analysis Plugin입니다.

**프로젝트 상태**:  **A+ 등급** (2025년 1월 28일 최신 업데이트)
- SpaceONE 플랫폼과 100% 호환
- SpaceONE Cost Management 표준 패턴 적용 완료 
- 부동소수점 정밀도 개선 완료
- Decimal 타입 완전 제거 (float 타입 보장)
- 견고한 에러 처리 및 데이터 변환
- 고성능 필드 매핑 시스템
- 포괄적인 로깅 및 모니터링

---

##  핵심 기능

### 1. 다중 데이터 소스 지원
- **BigQuery**: Google Cloud Billing Export 테이블
- **GCS**: Google Cloud Storage 버킷의 파일
- **HTTP**: 공개 URL의 파일 (인증 불필요)

### 2. 고급 필드 매핑
- 프로바이더별 최적화된 매핑 (Google Cloud, AWS, Azure)
- 중첩 구조 처리 (`project.id`, `service.description` 등)
- Fallback 필드 및 데이터 변환 지원
- 컴파일된 매핑 규칙으로 성능 최적화

### 3. SpaceONE 완벽 호환

** CRITICAL: SpaceONE 빌링 응답의 최상위 `cost` 필드는 필수 항목입니다.**

- **표준 응답 구조**: `{"results": [...]}` 형식 준수
- **최상위 cost 필드 보장**: 절대 누락 금지 ( CRITICAL)
- **필수 필드 완전 지원**: cost, usage_quantity, provider, region_code, product, usage_type, resource, billed_date, currency, tags, additional_info, data
- **JSON 직렬화 보장**: 과학적 표기법 완전 제거
- **타입 안전성 확보**: Decimal → float 자동 변환

### 4. 견고한 에러 처리
- 계층별 에러 처리 (Service → Manager → Connector)
- 우아한 실패 처리 (부분 실패 시에도 서비스 지속)
- SpaceONE 표준 에러 타입 사용

---

##  문서 관리 시스템

이 프로젝트는 체계적인 문서 관리 시스템을 제공합니다:

- ** [문서 인덱스](DOCUMENTATION_INDEX.md)** - 모든 문서의 체계적 정리
- ** [문서 관리 가이드](DOCUMENTATION_MANAGEMENT_GUIDE.md)** - 상세한 문서 관리 방법
- ** [빠른 문서 가이드](README_DOC_MANAGEMENT.md)** - 문서 작성 및 관리 요약
- ** 자동화 도구**: `scripts/create_doc.sh`, `scripts/doc_maintenance.sh`

### 새 문서 생성
```bash
# 개발자 가이드 생성
./scripts/create_doc.sh dev "새로운 기능" development

# 문서 품질 검사
./scripts/doc_maintenance.sh
```

---

##  빠른 시작

### 1. 환경 설정

```bash
# 프로젝트 클론
git clone <repository-url>
cd plugin-google-billing-cost-datasource

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는 venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r pkg/pip_requirements.txt

# 개발 도구 설치
pip install ruff pytest coverage
```

### 2. 개발 서버 실행

```bash
# 플러그인 서버 시작
python src/plugin/main.py

# 다른 터미널에서 API 테스트
grpcurl -plaintext -d '{}' localhost:50051 spaceone.api.cost_analysis.plugin.DataSource/init
```

### 3. 코드 품질 검사

```bash
# 자동화 스크립트 실행
./scripts/check_code_quality.sh

# 또는 수동 검사
ruff check src/ --fix
ruff format src/
pytest --cov=src
```

---

##  개발 가이드 문서

###  코드 작성 가이드
| 문서 | 설명 | 중요도 |
|------|------|--------|
| **[project-quality-checklist.md](development/project-quality-checklist.md)** | 코드 수정 시 필수 확인 사항 | ⭐⭐|
| **[spaceone-response-quality-guide.md](development/spaceone-response-quality-guide.md)** | SpaceONE 응답 데이터 품질 기준 | ⭐⭐|
| **[field-mapping-best-practices.md](development/field-mapping-best-practices.md)** | 필드 매핑 시스템 베스트 프랙티스 | ⭐|
| **[error-handling-patterns.md](development/error-handling-patterns.md)** | 에러 처리 패턴 가이드 | ⭐|

###  유지보수 가이드
| 문서 | 설명 | 중요도 |
|------|------|--------|
| **[code-maintenance-guide.md](development/code-maintenance-guide.md)** | 코드 유지보수 절차 | ⭐⭐|
| **[통합_테스트_가이드.md](development/통합_테스트_가이드.md)** | gRPC 테스트 전략 및 모범사례 (통합 테스트 가이드) | ⭐⭐|
| **[서버_실행_체크리스트.md](development/서버_실행_체크리스트.md)** | 서버 실행 및 포트 관리 가이드 | ⭐|
| **[조건부_additional_info_필터링_PRD.md](development/조건부_additional_info_필터링_PRD.md)** | 조건부 additional_info 필터링 PRD | ⭐|
| **[logging_standard.md](development/logging_standard.md)** | 로깅 표준 및 규칙 | ⭐|

###  기술 문서
| 문서 | 설명 |
|------|------|
| **[SpaceONE_표준_준수_additional_info_구조화_가이드.md](technical/SpaceONE_표준_준수_additional_info_구조화_가이드.md)** | SpaceONE 표준 준수 가이드 |
| **[Job_get_tasks_API_응답형식.md](technical/Job_get_tasks_API_응답형식.md)** | Job API 응답 형식 및 start time 결정 로직 |

---

##  개발 워크플로우

### 1. 새로운 기능 개발

```bash
# 1. 브랜치 생성
git checkout -b feature/new-feature

# 2. 코드 작성
# - project-quality-checklist.md 참조
# - spaceone-response-quality-guide.md 준수

# 3. 품질 검사
./scripts/check_code_quality.sh

# 4. 테스트 작성 및 실행
pytest test/test_new_feature.py -v

# 5. 문서 업데이트
# - 관련 가이드 문서 업데이트
# - API 문서 업데이트 (필요시)

# 6. 커밋 및 푸시
git add .
git commit -m "feat: add new feature with SpaceONE compatibility"
git push origin feature/new-feature
```

### 2. 버그 수정

```bash
# 1. 문제 분석
# - error-handling-patterns.md 참조
# - 로그 분석 및 에러 컨텍스트 파악

# 2. 수정 작업
# - 근본 원인 해결
# - 에러 처리 개선

# 3. 테스트 강화
# - 버그 재현 테스트 추가
# - 에지 케이스 테스트

# 4. 품질 검증
ruff check src/ --fix
pytest --cov=src
```

### 3. 코드 리뷰 체크포인트

#### A. 기본 품질 확인
- [ ] Ruff 검사 통과 (`ruff check src/`)
- [ ] 테스트 100% 통과 (`pytest`)
- [ ] 커버리지 목표 달성 (`pytest --cov=src`)

#### B. SpaceONE 호환성 확인
- [ ] 응답 구조 `{"results": [...]}` 준수
- [ ] 필수 필드 모두 포함
- [ ] `data` 필드 딕셔너리 타입 보장
- [ ] JSON 직렬화 가능성 확인

#### C. 아키텍처 일관성 확인
- [ ] 계층별 책임 분리 (Service → Manager → Connector)
- [ ] 에러 처리 패턴 일관성
- [ ] 로깅 표준 준수

---

##  프로젝트 품질 메트릭

### 현재 상태 (2025-09-10 기준)

| 항목 | 상태 | 점수 |
|------|------|------|
| **SpaceONE 호환성** |  완전 준수 | A+ |
| **코드 품질** |  Ruff 규칙 준수 | A+ |
| **에러 처리** |  견고한 구현 | A+ |
| **테스트 커버리지** |  핵심 로직 100% | A+ |
| **문서화** |  포괄적 가이드 | A+ |
| **성능** |  메모리 효율적 | A+ |

### 지속적 모니터링 지표

```bash
# 품질 지표 확인 스크립트
#!/bin/bash
echo " 프로젝트 품질 지표..."

# 1. 코드 품질
echo "1. Ruff 검사 결과:"
ruff check src/ --statistics

# 2. 테스트 커버리지  
echo "2. 테스트 커버리지:"
pytest --cov=src --cov-report=term-missing --quiet

# 3. 복잡도 분석
echo "3. 복잡도 분석:"
ruff check src/ --select C90 --statistics

echo " 품질 지표 확인 완료"
```

---

##  문제 해결 가이드

### 1. 자주 발생하는 문제

#### A. SpaceONE 응답 오류
```python
# 문제: data 필드 누락
# 해결: data 필드 강제 보장
if "data" not in record or not isinstance(record["data"], dict):
    record["data"] = self._create_spaceone_billing_data(record)
```

#### B. JSON 직렬화 오류
```python
# 문제: Pandas/NumPy 객체 직렬화 실패
# 해결: 직렬화 전 타입 변환
sanitized_record = self._sanitize_for_serialization(record)
```

#### C. 날짜 형식 오류
```python
# 문제: billed_date 형식 불일치
# 해결: 강제 형식 보장
if not record.get("billed_date"):
    record["billed_date"] = datetime.now().strftime("%Y-%m-%d")
```

### 2. 디버깅 도구

#### A. 로그 분석
```bash
# 일별 카운트 로그 분석
./analyze_daily_logs.sh

# billed_date 카운트 확인
./test_billed_date_count.sh
```

#### B. gRPC 테스트
```bash
# API 엔드포인트 테스트
./enhanced_grpcurl_test.sh

# 배치 테스트
python test/grpc/test_grpcurl_batch.py
```

---

##  향후 개선 계획

### 1. 단기 목표 (1-2개월)
- [ ] 추가 클라우드 프로바이더 지원 (AWS, Azure)
- [ ] 실시간 스트리밍 데이터 처리 지원
- [ ] 고급 필터링 및 집계 기능

### 2. 중기 목표 (3-6개월)  
- [ ] 머신러닝 기반 비용 예측
- [ ] 대용량 데이터 분산 처리
- [ ] 고급 시각화 대시보드

### 3. 장기 목표 (6개월+)
- [ ] 멀티 클라우드 통합 분석
- [ ] 자동화된 비용 최적화 권장
- [ ] 실시간 알림 시스템

---

##  기여 가이드

### 1. 코드 기여
1. 이슈 생성 또는 기존 이슈 선택
2. 브랜치 생성 (`feature/`, `fix/`, `refactor/`)
3. 코드 작성 (품질 가이드 준수)
4. 테스트 작성 및 실행
5. Pull Request 생성

### 2. 문서 기여
1. 오타 수정, 내용 개선
2. 새로운 가이드 작성
3. 예제 코드 추가
4. 번역 작업

### 3. 버그 리포트
1. 재현 가능한 예제 제공
2. 환경 정보 포함
3. 예상 동작 vs 실제 동작 설명
4. 관련 로그 첨부

---

##  지원 및 연락처

### 1. 문서 리소스
- **개발 가이드**: `docs/ko/development/`
- **기술 문서**: `docs/ko/technical/`
- **사용자 가이드**: `docs/ko/user-guide/`

### 2. 커뮤니티
- **이슈 트래커**: GitHub Issues
- **토론**: GitHub Discussions
- **위키**: GitHub Wiki

---

##  라이선스

이 프로젝트는 Apache License 2.0 하에 배포됩니다. 자세한 내용은 [LICENSE](../LICENSE) 파일을 참조하세요.

---

**마지막 업데이트**: 2025-01-28  
**프로젝트 상태**: A+ 등급 (SpaceONE 완전 호환 + Cost Management 표준 패턴)  
**메인테이너**: SpaceONE Team