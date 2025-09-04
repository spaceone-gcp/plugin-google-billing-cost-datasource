# Google Cloud Billing 비용 데이터 소스 플러그인

SpaceONE용 Google Cloud Billing 데이터 수집 플러그인 문서입니다.

## 📖 문서 구조

### 사용자 가이드
- **[Google Cloud Billing Export 설정 가이드](./user-guide/billing-export-setup.md)** - Billing Export 설정 방법
- **[Google Cloud Billing 통합 가이드](./user-guide/integration-guide.md)** - 플러그인 설정 및 사용법  
- **[Google Cloud Billing 데이터 분석 가이드](./user-guide/data-analysis-guide.md)** - 데이터 구조 및 분석 방법
- **[크레딧 및 할인 분석 가이드](./user-guide/credits-and-discounts-analysis.md)** - 크레딧과 할인 상세 분석

### 개발자 문서
- **[프로젝트 요구사항 명세서 (PRD)](./development/prd.md)** - HTTP 파일 통합 기능 PRD
- **[구현 로드맵](./development/implementation-roadmap.md)** - 단계별 구현 계획
- **[Field Mapper 개발 가이드](./development/field-mapper-guide.md)** - Field Mapper 구현 방법

### 기술 명세서
- **[아키텍처 설계](./technical/architecture.md)** - 전체 시스템 아키텍처
- **[API 명세서](./technical/api-specifications.md)** - 상세 API 문서
- **[데이터 모델](./technical/data-models.md)** - 데이터 구조 정의

## 🚀 빠른 시작

1. **신규 사용자**: [Billing Export 설정 가이드](./user-guide/billing-export-setup.md)부터 시작하세요
2. **플러그인 설정**: [통합 가이드](./user-guide/integration-guide.md)로 SpaceONE 연동을 완료하세요
3. **데이터 분석**: [데이터 분석 가이드](./user-guide/data-analysis-guide.md)와 [크레딧 분석 가이드](./user-guide/credits-and-discounts-analysis.md)를 활용하세요
4. **개발자**: [PRD](./development/prd.md)와 [로드맵](./development/implementation-roadmap.md)을 확인하세요
5. **아키텍트**: [아키텍처 설계](./technical/architecture.md)를 참고하세요

## 📋 지원 기능

### 데이터 소스
- ✅ **BigQuery**: 실시간 쿼리 기반 (프로덕션 준비 완료)
- ✅ **HTTP 파일**: GCS 파일 직접 처리 (프로덕션 준비 완료)

### 파일 형식
- CSV, JSON, Parquet
- 압축 파일 (.gz, .snappy, .zstd)

### 핵심 기능
- 이중 데이터 소스 지원
- 유연한 Field Mapper
- 크레딧 및 할인 분석
- 라벨/태그 기반 추적
