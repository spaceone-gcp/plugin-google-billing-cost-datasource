# DataSourceManager 운영 가이드

##  개요

DataSourceManager의 운영 환경 배포 후 모니터링, 장애 대응, 성능 관리를 위한 종합 운영 가이드입니다.

**작성일**: 2025-09-29  
**대상**: 운영팀, DevOps 엔지니어  
**적용 범위**: 프로덕션 환경

---

##  1. 운영 개요

### 1.1 핵심 지표 (KPI)

| 지표 | 목표값 | 경고 임계값 | 위험 임계값 |
|------|---------|-------------|-------------|
| **응답 시간** | < 50ms | > 100ms | > 200ms |
| **성공률** | > 99.9% | < 99% | < 95% |
| **메타데이터 필드 수** | 32개 | < 30개 | < 25개 |
| **메모리 사용량** | < 5KB | > 10KB | > 20KB |
| **에러율** | < 0.1% | > 1% | > 5% |

### 1.2 서비스 수준 협약 (SLA)

- **가용성**: 99.9% (월 43분 이하 다운타임)
- **응답 시간**: 95% 요청이 100ms 이내 처리
- **복구 시간**: 장애 발생 시 5분 이내 복구
- **데이터 일관성**: 100% (메타데이터 필드 누락 없음)

---

##  2. 모니터링 체계

### 2.1 실시간 모니터링

#### A. 성능 모니터링
```bash
# 모니터링 도구 실행
python3 monitoring/data_source_manager_monitoring.py

# 실시간 메트릭 확인
tail -f data_source_manager.log
```

#### B. 헬스 체크
```python
# 헬스 체크 API 호출 시뮬레이션
from monitoring.data_source_manager_monitoring import DataSourceManagerMonitor

monitor = DataSourceManagerMonitor()
health = monitor.health_check()
print(f"서비스 상태: {health['status']}")
```

### 2.2 알림 설정

#### A. 성능 저하 알림
- **조건**: 평균 응답 시간 > 100ms (5분 지속)
- **액션**: Slack 채널 알림, 담당자 이메일 발송

#### B. 에러율 증가 알림
- **조건**: 에러율 > 1% (3분 지속)
- **액션**: 즉시 SMS 알림, 온콜 담당자 호출

#### C. 메타데이터 누락 알림
- **조건**: 필드 수 < 30개
- **액션**: 즉시 알림, 자동 복구 시도

### 2.3 로그 관리

#### A. 로그 레벨별 분류
```bash
# 에러 로그 모니터링
grep "ERROR" data_source_manager.log | tail -20

# 성능 경고 로그
grep "성능 기준 초과" data_source_manager.log

# 성공 요청 통계
grep "init_response 성공" data_source_manager.log | wc -l
```

#### B. 로그 순환 설정
```bash
# logrotate 설정 예시
/var/log/data_source_manager.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    create 0644 app app
}
```

---

##  3. 장애 대응 절차

### 3.1 장애 유형별 대응

#### A. 응답 시간 지연 (> 100ms)

**1단계: 즉시 대응**
```bash
# 시스템 리소스 확인
top -p $(pgrep -f data_source_manager)
free -h
df -h

# 프로세스 상태 확인
ps aux | grep data_source_manager
```

**2단계: 근본 원인 분석**
- CPU 사용률 확인
- 메모리 누수 검사
- 디스크 I/O 상태 확인
- 네트워크 지연 측정

**3단계: 복구 조치**
```bash
# 서비스 재시작 (필요시)
systemctl restart spaceone-plugin

# 캐시 클리어 (해당하는 경우)
redis-cli FLUSHALL
```

#### B. 메타데이터 필드 누락

**1단계: 문제 확인**
```python
# 필드 수 확인
from monitoring.data_source_manager_monitoring import DataSourceManagerMonitor
monitor = DataSourceManagerMonitor()
result = monitor.monitor_init_response({})
field_count = len(result["metadata"]["additional_info"])
print(f"현재 필드 수: {field_count}")
```

**2단계: 자동 복구 시도**
```bash
# 설정 파일 백업에서 복원
cp /backup/data_source_manager.py.backup src/plugin/manager/data_source_manager.py

# 서비스 재시작
systemctl restart spaceone-plugin
```

**3단계: 수동 복구**
- 코드 검토 및 누락된 필드 확인
- Git에서 최신 안정 버전으로 롤백
- 테스트 환경에서 검증 후 배포

#### C. 완전 서비스 다운

**1단계: 긴급 복구**
```bash
# 서비스 상태 확인
systemctl status spaceone-plugin

# 긴급 재시작
systemctl restart spaceone-plugin

# 로그 확인
journalctl -u spaceone-plugin -f
```

**2단계: 백업 시스템 활성화**
```bash
# 백업 인스턴스로 트래픽 전환
# (로드밸런서 설정에 따라)
nginx -s reload
```

### 3.2 에스컬레이션 절차

#### 레벨 1: 자동 복구
- 모니터링 시스템이 자동 감지
- 자동 재시작 시도
- 기본 복구 스크립트 실행

#### 레벨 2: 온콜 엔지니어
- 5분 내 자동 복구 실패 시
- SMS/전화 알림 발송
- 수동 진단 및 복구 수행

#### 레벨 3: 개발팀 에스컬레이션
- 30분 내 복구 실패 시
- 개발팀 리더 호출
- 코드 레벨 수정 필요 시

---

##  4. 성능 최적화

### 4.1 성능 튜닝 포인트

#### A. 메모리 최적화
```python
# deepcopy 최적화
import copy
from functools import lru_cache

@lru_cache(maxsize=1)
def get_cached_metadata():
    """메타데이터 캐싱으로 deepcopy 최적화"""
    return copy.deepcopy(_DEFAULT_METADATA_ADDITIONAL_INFO)
```

#### B. 응답 시간 최적화
- 상수 딕셔너리 사용 (현재 구현됨)
- 불필요한 로깅 제거
- JSON 직렬화 최적화

#### C. 확장성 개선
```python
# 비동기 처리 도입 (필요시)
import asyncio

async def async_init_response(options: dict, domain_id: str = None):
    """비동기 초기화 응답"""
    # 구현...
    pass
```

### 4.2 리소스 사용량 모니터링

```bash
# 메모리 사용량 추적
ps -o pid,ppid,cmd,%mem,%cpu -p $(pgrep -f data_source_manager)

# 파일 디스크립터 사용량
lsof -p $(pgrep -f data_source_manager) | wc -l
```

---

##  5. 유지보수 절차

### 5.1 정기 점검 (주간)

#### A. 성능 리포트 생성
```bash
# 주간 성능 리포트
python3 -c "
from monitoring.data_source_manager_monitoring import DataSourceManagerMonitor
monitor = DataSourceManagerMonitor()
metrics = monitor.get_metrics_summary()
print('=== 주간 성능 리포트 ===')
for key, value in metrics.items():
    print(f'{key}: {value}')
"
```

#### B. 로그 분석
```bash
# 에러 패턴 분석
awk '/ERROR/ {print $0}' data_source_manager.log | sort | uniq -c | sort -nr

# 응답 시간 분포
grep "응답시간" data_source_manager.log | awk '{print $NF}' | sort -n
```

### 5.2 정기 점검 (월간)

#### A. 용량 계획
- 메타데이터 크기 증가 추이 분석
- 메모리 사용량 예측
- 스토리지 용량 계획

#### B. 보안 점검
- 의존성 보안 업데이트
- 로그 접근 권한 검토
- 인증서 만료일 확인

### 5.3 업데이트 절차

#### A. 코드 업데이트
```bash
# 1. 백업 생성
cp src/plugin/manager/data_source_manager.py /backup/data_source_manager.py.$(date +%Y%m%d)

# 2. 테스트 환경 배포
git checkout feature/update-branch
python3 -m pytest tests/test_data_source_manager.py

# 3. 프로덕션 배포
git checkout main
systemctl stop spaceone-plugin
cp new_version/data_source_manager.py src/plugin/manager/
systemctl start spaceone-plugin

# 4. 검증
python3 monitoring/data_source_manager_monitoring.py
```

#### B. 롤백 절차
```bash
# 문제 발생 시 즉시 롤백
systemctl stop spaceone-plugin
cp /backup/data_source_manager.py.latest src/plugin/manager/data_source_manager.py
systemctl start spaceone-plugin

# 롤백 검증
curl -X POST localhost:50051/DataSource.init -d '{"options":{}}'
```

---

##  6. 성능 기준선 및 용량 계획

### 6.1 현재 성능 기준선

| 메트릭 | 현재값 | 목표값 | 여유분 |
|--------|--------|--------|--------|
| 평균 응답 시간 | 0.01ms | < 50ms | 5000% |
| 메모리 사용량 | 3.2KB | < 5KB | 56% |
| 필드 수 | 32개 | 32개 | 100% |
| 성공률 | 100% | > 99.9% | 100% |

### 6.2 확장성 계획

#### A. 트래픽 증가 대응
- **현재 처리량**: 1000 req/sec 예상 가능
- **목표 처리량**: 10000 req/sec
- **확장 방안**: 로드밸런싱, 캐싱 도입

#### B. 메타데이터 확장 대응
- **현재 필드 수**: 32개
- **예상 확장**: 50개까지
- **메모리 영향**: 5KB → 8KB 예상

---

##  7. 연락처 및 에스컬레이션

### 7.1 담당자 연락처

| 역할 | 담당자 | 연락처 | 대응 시간 |
|------|--------|--------|----------|
| **1차 온콜** | DevOps 팀 | +82-10-xxxx-xxxx | 24/7 |
| **개발팀 리더** | Backend 팀장 | +82-10-yyyy-yyyy | 평일 09-18시 |
| **시스템 관리자** | Infrastructure 팀 | +82-10-zzzz-zzzz | 24/7 |

### 7.2 에스컬레이션 매트릭스

| 장애 수준 | 대응 시간 | 담당자 | 알림 방식 |
|-----------|----------|--------|-----------|
| **P1 (Critical)** | 5분 | 온콜 + 팀장 | SMS + 전화 |
| **P2 (High)** | 15분 | 온콜 엔지니어 | SMS |
| **P3 (Medium)** | 1시간 | 담당 개발자 | Email |
| **P4 (Low)** | 1일 | 담당 개발자 | Slack |

### 7.3 외부 의존성

| 서비스 | 담당팀 | 연락처 | SLA |
|--------|--------|--------|-----|
| **SpaceONE Core** | Core 팀 | core-team@company.com | 99.9% |
| **인프라 (K8s)** | Platform 팀 | platform@company.com | 99.95% |
| **모니터링** | SRE 팀 | sre@company.com | 99.9% |

---

##  8. 관련 문서

### 8.1 기술 문서
- [DataSourceManager_PRD.md](../development/DataSourceManager_PRD.md) - 제품 요구사항 정의서
- [API_명세서.md](../technical/API_명세서.md) - API 상세 규격
- [프로젝트_품질_체크리스트.md](../development/프로젝트_품질_체크리스트.md) - 품질 기준

### 8.2 운영 문서
- [배포_가이드.md](./배포_가이드.md) - 배포 절차 및 체크리스트
- [모니터링_설정_가이드.md](./모니터링_설정_가이드.md) - 상세 모니터링 구성
- [장애_대응_플레이북.md](./장애_대응_플레이북.md) - 상황별 대응 절차

### 8.3 도구 및 스크립트
- `monitoring/data_source_manager_monitoring.py` - 모니터링 도구
- `scripts/health_check.sh` - 헬스 체크 스크립트
- `scripts/backup_restore.sh` - 백업 및 복원 스크립트

---

**문서 업데이트**: 2025-09-29  
**다음 검토 예정**: 2025-12-29  
**운영팀 승인**: [ ] 대기중
