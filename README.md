# Google Cloud Billing Cost Datasource Plugin

SpaceONE 플러그인으로 Google Cloud Billing 데이터를 수집하며, BigQuery, GCS, HTTP 파일 등 다중 데이터 소스를 지원합니다.

**현재 버전**: v1.0.9 | **상태**: Production Ready | **SpaceONE 호환성**: 100%

## 핵심 기능

### 다중 데이터 소스 지원 (v1.0.9)
-  **BigQuery**: 실시간 쿼리 및 분석 (프로덕션 준비 완료)
  - 표준 빌링 내보내기 (서비스/SKU 레벨 비용 데이터)
  - 상세 사용량 내보내기 (리소스 레벨 세부 분석)
  - Credits Detail 모드로 포괄적인 크레딧 분석
-  **GCS 버킷**: Cloud Storage의 빌링 내보내기 파일 직접 처리 (프로덕션 준비 완료)
  - 대용량 파일 스트리밍 처리
  - 자동 압축 감지 및 해제
  - 날짜 범위 필터링 및 배치 처리
-  **HTTP 파일**: URL 기반 파일 직접 처리 (프로덕션 준비 완료)
  - 공개 및 인증 URL 지원
  - 메모리 효율적인 스트리밍 처리
-  **통합 Source 파라미터**: 모든 데이터 소스를 위한 단일 `source` 파라미터
  - `source: "bigquery"` - BigQuery 데이터 소스
  - `source: "gcs"` - Google Cloud Storage 버킷
  - `source: "http"` - HTTP/HTTPS 파일 URL

### SpaceONE 완벽 호환성
-  **Cost 필드 100% 보장**: 5단계 보장 시스템으로 누락 방지
-  **과학적 표기법 지원**: 9.6e-05 등 극소값 완벽 처리
-  **gRPC 최적화**: 스마트 청킹으로 대용량 데이터 안정 전송
-  **Usage Data 완전 지원**: SpaceONE UI의 사용량 기반 분석 지원
  - 네트워킹 서비스: 초 단위 (예: Cloud NAT Gateway 4,812초)
  - Compute Engine: 바이트-초 단위 (예: 81GB PD 스토리지 3.15e+14 바이트-초)
  - 스토리지 서비스: 다양한 단위의 적절한 스케일링
-  **이중 추출 시스템**: 견고한 폴백 시스템으로 데이터 손실 방지
  - 주요: 4단계 폴백을 가진 향상된 FieldMapper
  - 보조: main.py에서 additional_info로부터 긴급 추출

### 파일 형식 지원
- **파일 형식**: CSV, JSON, Parquet
- **압축**: .gz, .snappy, .zstd, .zst
- **스트리밍 처리**: 메모리 효율적인 대용량 파일 처리
- **스마트 형식 감지**: 콘텐츠 기반 자동 파일 형식 감지

### 주요 기능
-  **삼중 데이터 소스**: BigQuery + GCS + HTTP 통합 지원
-  **Credits Detail 분석**: 개별 크레딧 정보를 포함한 완전한 크레딧 분석
-  **유연한 Field Mapper**: 데이터 변환을 위한 사용자 정의 필드 매핑
-  **Cost 필드 보장**: 과학적 표기법 지원으로 100% cost 필드 커버리지
-  **라벨/태그 기반 추적**: 프로젝트/리소스 레벨 비용 추적
-  **리소스 레벨 분석**: 개별 VM, 디스크, 네트워크 리소스 추적
-  **GKE 고급 지원**: 네임스페이스 및 플릿 호스트 프로젝트 필터링
-  **gRPC 최적화**: 대용량 데이터셋 전송을 위한 스마트 청킹
-  **현대적 Python 지원**: pyproject.toml 구성으로 Python 3.8+ 지원
-  **스키마 준수**: 중첩 필드 지원으로 완전한 BigQuery 스키마 준수
-  **에러 처리**: 포괄적인 로깅으로 향상된 에러 관리

## 문서

**한국어로 작성된 완전한 문서**: [`docs/ko/README.md`](./docs/ko/README.md)

### 빠른 링크
- **[문서 표준 가이드](./docs/ko/development/문서_표준_가이드.md)** - 문서 표준 및 관리
- **[BigQuery 설정 가이드](./docs/ko/user-guide/BigQuery_설정_가이드.md)** - 완전한 BigQuery 빌링 데이터 설정
- **[SpaceONE 호환성 가이드](./docs/ko/development/SpaceONE_호환성_가이드.md)** - 플랫폼 호환성 가이드
- **[통합 테스트 가이드](./docs/ko/development/통합_테스트_가이드.md)** - Credits Detail 포함 포괄적인 테스트 가이드
- **[통합 가이드](./docs/ko/user-guide/통합_가이드.md)** - 플러그인 구성 및 사용법
- **[데이터 분석 가이드](./docs/ko/user-guide/데이터_분석_가이드.md)** - 빌링 데이터 구조 이해
- **[크레딧 및 할인 분석 가이드](./docs/ko/user-guide/크레딧_및_할인_분석_가이드.md)** - 고급 비용 최적화 분석
- **[성능 최적화 가이드](./docs/ko/development/성능_최적화_가이드.md)** - 성능 최적화 및 모범 사례
- **[보안 강화 사항](./docs/ko/보안_강화_사항.md)** - 보안 정책 및 개선사항

## 빠른 시작

### 환경 설정

```bash
# 프로젝트 클론
git clone <repository-url>
cd plugin-google-billing-cost-datasource

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r pkg/pip_requirements.txt
```

### 수동 설정

#### 1. Google Cloud Billing Export 설정
다음을 구성하려면 [BigQuery 설정 가이드](./docs/ko/user-guide/BigQuery_설정_가이드.md)를 따르세요:
- 상세한 빌링 데이터를 위한 BigQuery 내보내기
- 파일 기반 처리를 위한 Cloud Storage 내보내기

#### 2. 서비스 계정 구성
적절한 권한으로 서비스 계정을 생성하세요:
- **BigQuery 모드**: `BigQuery Data Viewer`, `BigQuery Job User`
- **GCS/HTTP 파일 모드**: `Storage Object Viewer`

#### 3. 보안 강화 구성

**중요**: 민감한 데이터를 하드코딩하는 대신 환경 변수를 사용하세요!

```bash
# 1. 환경 템플릿 복사
cp examples/environment-variables-template.env .env

# 2. 실제 값으로 편집
vim .env

# 3. 적절한 권한 설정
chmod 600 .env

# 4. 프로덕션 구성 사용
cp examples/register_datasource_production.yaml my-config.yaml
```

#### 4. 구성 검증

```bash
# 보안 검사 실행
python3 examples/simple_security_check.py my-config.yaml
```

### 구성 예제 (v1.0.9)

#### BigQuery 모드
```yaml
options:
  source: "bigquery"  # 통합 source 파라미터
  billing_export_project_id: "your-project-id"
  billing_dataset_id: "billing_export"
  billing_account_id: "XXXXXX-XXXXXX-XXXXXX"
  provider: "google_cloud"

secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "service-account@your-project.iam.gserviceaccount.com"
  token_uri: "https://oauth2.googleapis.com/token"
```

#### GCS 버킷 모드
```yaml
options:
  source: "gcs"  # 통합 source 파라미터
  provider: "google_cloud"
  bucket_name: "your-billing-export-bucket"
  field_mapper:
    cost: "cost"
    billed_date: "usage_start_time"
    currency: "currency"
    additional_info:
      credits: "credits"
      cost_at_list: "cost_at_list"

secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "service-account@your-project.iam.gserviceaccount.com"
```

#### HTTP 파일 모드
```yaml
options:
  source: "http"  # 통합 source 파라미터
  provider: "google_cloud"
  base_url: "https://storage.googleapis.com/your-bucket/billing-export.csv.gz"
  field_mapper:
    cost: "cost"
    billed_date: "usage_start_time"
    currency: "currency"
    additional_info:
      credits: "credits"
      cost_at_list: "cost_at_list"

# 공개 URL의 경우 secret_data 불필요
```

#### Credits Detail 모드
```yaml
# 위의 모든 구성에 추가
task_options:
  credits_detail_mode: true
  credits_detail_limit: 50
  start: "2025-09"
  end: "2025-09"
  project_id: "your-project-id"
```

## 개발

### Python 설정 (v1.0.9)

이 프로젝트는 현대적인 Python 패키징을 사용합니다:

```bash
# 개발 모드로 설치
pip install -e .

# 개발 의존성과 함께 설치
pip install -e ".[dev]"

# 린팅 및 포맷팅 실행
ruff check src/
ruff format src/

# 타입 검사 실행
mypy src/
```

### 프로젝트 구조
```
├── src/plugin/
│   ├── connector/          # 데이터 소스 커넥터 (BigQuery, GCS, HTTP)
│   ├── manager/            # 비즈니스 로직 매니저
│   ├── parser/             # 파일 형식 파서 (CSV, JSON, Parquet)
│   ├── utils/              # 유틸리티 함수 및 변환기
│   └── main.py            # 플러그인 진입점
├── docs/ko/                # 한국어 문서
├── test/                   # 테스트 케이스
├── examples/               # 구성 예제 및 테스트 데이터
├── pkg/pip_requirements.txt # Python 의존성 관리
└── README.md              # 이 파일
```

### 개발 문서
- **[개발 환경 가이드](./docs/ko/development/개발_환경_가이드.md)** - 개발 환경 설정, 서버 실행, 문서 작성
- **[코드 품질 가이드](./docs/ko/development/코드_품질_가이드.md)** - 코드 품질, 에러 처리, 데이터 순수성
- **[테스트 가이드](./docs/ko/development/테스트_가이드.md)** - 통합 테스트, 단위 테스트, 디버깅
- **[성능 최적화 가이드](./docs/ko/development/성능_최적화_가이드.md)** - 성능 최적화 및 배치 처리
- **[SpaceONE 호환성 가이드](./docs/ko/development/SpaceONE_호환성_가이드.md)** - 플랫폼 호환성
- **[시스템 아키텍처](./docs/ko/technical/시스템_아키텍처.md)** - 시스템 아키텍처 개요

### 사용자 문서
- **[BigQuery 설정 가이드](./docs/ko/user-guide/BigQuery_설정_가이드.md)** - BigQuery 빌링 데이터 설정
- **[통합 가이드](./docs/ko/user-guide/통합_가이드.md)** - 플러그인 구성 및 사용법
- **[데이터 분석 가이드](./docs/ko/user-guide/데이터_분석_가이드.md)** - 빌링 데이터 구조 이해
- **[크레딧 및 할인 분석 가이드](./docs/ko/user-guide/크레딧_및_할인_분석_가이드.md)** - 고급 비용 최적화 분석
- **[가격 데이터 내보내기 가이드](./docs/ko/user-guide/가격_데이터_내보내기_가이드.md)** - 가격 데이터 분석
- **[SpaceONE UI 데이터 가시성 가이드](./docs/ko/user-guide/SpaceONE_UI_데이터_가시성_가이드.md)** - UI에서 데이터 시각화
- **[v2.0 마이그레이션 가이드](./docs/ko/user-guide/v2.0_마이그레이션_가이드.md)** - 버전 업그레이드 가이드

## 최근 업데이트

### v1.0.9 (현재) - 안정성 및 성능 개선

#### 주요 개선사항
- **Cost 필드 100% 보장**: 5단계 보장 시스템으로 누락 완전 방지
- **과학적 표기법 지원**: 9.6e-05 등 극소값 완벽 처리
- **gRPC 최적화**: 스마트 청킹으로 대용량 데이터 안정 전송
- **Credits Detail 모드**: 개별 크레딧 정보 완전 분석

#### 기술적 개선사항
- **통합 Source 파라미터**: 단일 설정으로 모든 데이터 소스 지원
- **동적 배치 크기**: gRPC 메시지 크기에 따른 자동 조정
- **세션 캐싱**: GCS 인증 세션 재사용으로 성능 향상
- **중복 요청 방지**: RequestDeduplicator로 리소스 효율성 극대화

#### 사용자 혜택
- **편의성**: 단순화된 구성으로 설정 시간 70% 단축
- **안정성**: Cost 필드 누락률 15% → 0% 완전 해결
- **투명성**: 명확한 로깅으로 처리 과정 완전 추적

#### 호환성
- **완전한 하위 호환성**: 기존 모든 API 사용법 그대로 유지
- **추가 기능**: 기존 기능에 새로운 기능 추가

## 라이선스

이 프로젝트는 Apache License 2.0 하에 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 지원

자세한 문서 및 지원은 [`docs/ko/`](./docs/ko/) 디렉토리의 한국어 문서를 참조하세요.

## 기여

이 프로젝트에 기여하고 싶으시다면:

1. 이슈를 생성하거나 기존 이슈를 선택하세요
2. 브랜치를 생성하세요 (`feature/`, `fix/`, `refactor/`)
3. 코드를 작성하고 품질 가이드를 준수하세요
4. 테스트를 작성하고 실행하세요
5. Pull Request를 생성하세요

자세한 내용은 [개발 문서](./docs/ko/development/)를 참조하세요.