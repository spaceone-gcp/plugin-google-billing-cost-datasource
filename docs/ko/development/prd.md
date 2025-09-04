# Google Cloud Billing HTTP 파일 통합 기능 PRD

## 1. 개요

### 1.1. 기능명
Google Cloud Billing HTTP 파일 데이터 소스 통합

### 1.2. 목적
현재 BigQuery 기반 Google Cloud Billing 데이터 수집 플러그인에 HTTP 파일 기반 데이터 소스 지원을 추가하여, Google Cloud Storage에 저장된 Billing Export 파일(CSV, JSON, Parquet)을 직접 처리할 수 있도록 확장합니다.

### 1.3. 사용자 스토리
- **As a** SpaceONE 사용자
- **I want to** Google Cloud Storage에 저장된 Billing Export 파일을 직접 읽어와 비용 데이터를 분석하고
- **So that** BigQuery 설정 없이도 Google Cloud 비용 데이터를 SpaceONE에서 활용할 수 있습니다.

### 1.4. 비즈니스 가치
- BigQuery 설정이 복잡한 고객을 위한 대안 제공
- 다양한 파일 형식(CSV, JSON, Parquet) 지원으로 유연성 증대
- 압축 파일 지원으로 네트워크 효율성 향상
- Field Mapper를 통한 커스터마이징 가능한 데이터 매핑

## 2. 기능 요구사항

### 2.1. 핵심 기능

#### 2.1.1. HTTP 파일 커넥터
- **목적**: Google Cloud Storage에서 Billing Export 파일을 HTTP(S)로 다운로드
- **지원 형식**: CSV, JSON, Parquet
- **지원 압축**: .gz, .snappy, .zstd
- **인증**: Google Cloud Service Account 키 기반

#### 2.1.2. Field Mapper 구현
- **목적**: 원본 데이터 필드를 SpaceONE 표준 필드로 매핑
- **자동 매핑**: `provider: google_cloud` 설정 시 기본 필드 자동 매핑
- **커스터마이징**: `additional_info` 필드를 통한 추가 정보 매핑
- **기본값 설정**: `default_vars`를 통한 누락 필드 기본값 제공

#### 2.1.3. 데이터 처리 엔진
- **스트리밍 처리**: 대용량 파일을 메모리 효율적으로 처리
- **데이터 검증**: 필수 필드 존재 여부 및 데이터 타입 검증
- **에러 복구**: 개별 레코드 오류가 전체 처리에 영향을 주지 않도록 격리

### 2.2. 기술 요구사항

#### 2.2.1. 아키텍처 확장
- **기존 구조 유지**: Service → Manager → Connector 3계층 아키텍처
- **커넥터 추가**: `HttpFileConnector` 클래스 신규 생성
- **매니저 확장**: `CostManager`에 파일 처리 로직 추가
- **설정 분리**: HTTP 파일 관련 설정을 별도 모듈로 관리

#### 2.2.2. 데이터 모델 예시
```json
{
  "options": {
    "data_source_type": "http_file",
    "provider": "google_cloud",
    "bucket_name": "billing-export-bucket",
    "field_mapper": {
      "cost": "cost",
      "billed_date": "usage_start_time",
      "currency": "currency",
      "additional_info": {
        "cost_at_list": "cost_at_list",
        "credits": "credits",
        "project_id": "project.id"
      }
    },
    "default_vars": {
      "provider": "google_cloud"
    }
  }
}
```

#### 2.2.3. 파일 처리 플로우
1. **파일 발견**: GCS 버킷에서 패턴 매칭으로 파일 목록 조회
2. **파일 다운로드**: HTTP(S)를 통한 스트리밍 다운로드
3. **압축 해제**: 지원하는 압축 형식 자동 감지 및 해제
4. **데이터 파싱**: 파일 형식별 파서를 통한 데이터 추출
5. **필드 매핑**: Field Mapper를 통한 SpaceONE 형식 변환
6. **데이터 검증**: 필수 필드 및 데이터 타입 검증
7. **결과 반환**: Generator를 통한 스트리밍 응답

### 2.3. 성능 요구사항
- **처리 속도**: 100MB 파일 기준 5분 이내 처리
- **메모리 사용량**: 파일 크기에 관계없이 최대 512MB 이내
- **동시 처리**: 최대 3개 파일 병렬 처리
- **재시도 정책**: 네트워크 오류 시 최대 3회 재시도

## 3. 비기능 요구사항

### 3.1. 보안 요구사항
- Google Cloud Service Account 키 안전한 저장 및 사용
- 민감정보(API 키, 토큰) 로그 출력 금지
- HTTPS를 통한 안전한 파일 다운로드

### 3.2. 안정성 요구사항
- **부분 실패 허용**: 개별 파일 처리 실패가 전체 작업에 영향 없음
- **타임아웃 관리**: 파일 다운로드 및 처리 시간 제한
- **메모리 관리**: 대용량 파일 처리 시 메모리 누수 방지

### 3.3. 유지보수성 요구사항
- 기존 BigQuery 기능과 독립적인 구조
- 확장 가능한 Field Mapper 설계
- 명확한 에러 메시지 및 로깅

## 4. 구현 방향

### 4.1. 최소 소스 수정 전략

#### 4.1.1. 신규 컴포넌트
- `src/plugin/connector/http_file_connector.py`: HTTP 파일 다운로드 및 처리
- `src/plugin/manager/field_mapper.py`: 필드 매핑 로직
- `src/plugin/conf/http_file_conf.py`: HTTP 파일 관련 설정
- `src/plugin/model/file_data.py`: 파일 데이터 모델

#### 4.1.2. 기존 컴포넌트 수정
- `src/plugin/manager/cost_manager.py`: 파일 처리 로직 추가
- `src/plugin/manager/data_source_manager.py`: 메타데이터 확장
- `src/plugin/main.py`: 라우팅 로직 수정 (최소화)

### 4.2. 호환성 보장
- 기존 BigQuery 기능 완전 유지
- 기존 설정 구조 하위 호환성 보장
- 기존 API 인터페이스 변경 없음

## 5. 테스트 전략

### 5.1. 단위 테스트
- `HttpFileConnector` 클래스 테스트
- `FieldMapper` 로직 테스트
- 파일 형식별 파서 테스트

### 5.2. 통합 테스트
- Google Cloud Storage 연동 테스트 (Mock 사용)
- 전체 데이터 처리 플로우 테스트
- 기존 BigQuery 기능 회귀 테스트

### 5.3. 성능 테스트
- 대용량 파일 처리 성능 측정
- 메모리 사용량 모니터링
- 동시 처리 성능 검증

## 6. 위험 요소 및 대응 방안

### 6.1. 기술적 위험
- **위험**: 대용량 파일 처리 시 메모리 부족
- **대응**: 스트리밍 처리 및 청크 단위 처리 구현

- **위험**: 다양한 파일 형식 지원의 복잡성
- **대응**: 파일 형식별 독립적인 파서 구조 설계

### 6.2. 운영 위험
- **위험**: Google Cloud Storage 접근 권한 문제
- **대응**: 명확한 권한 설정 가이드 및 에러 메시지 제공

- **위험**: 기존 BigQuery 기능 영향
- **대응**: 철저한 회귀 테스트 및 독립적인 구조 설계

## 7. 릴리스 계획

### 7.1. 단계별 개발
1. **Phase 1**: HTTP 파일 커넥터 기본 구현
2. **Phase 2**: Field Mapper 및 데이터 변환 로직
3. **Phase 3**: 압축 파일 지원 및 성능 최적화
4. **Phase 4**: 문서화 및 테스트 보완

### 7.2. 검증 기준
- 모든 단위 테스트 통과
- 기존 BigQuery 기능 회귀 테스트 통과
- 성능 요구사항 만족
- 문서화 완료

## 8. 참고 자료

### 관련 문서
- [Google Cloud Billing 통합 가이드](../user-guide/integration-guide.md)
- [Google Cloud Billing 데이터 분석 가이드](../user-guide/data-analysis-guide.md)
- [아키텍처 설계](../technical/architecture.md)
- [API 명세서](../technical/api-specifications.md)
- [데이터 모델](../technical/data-models.md)
- [구현 로드맵](./implementation-roadmap.md)
- [Field Mapper 개발 가이드](./field-mapper-guide.md)

### 외부 참고 자료
- [SpaceONE 플러그인 개발 가이드](https://spaceone.io/docs/guides/developer/plugin-development/)
- [Google Cloud Storage API 문서](https://cloud.google.com/storage/docs/apis)
