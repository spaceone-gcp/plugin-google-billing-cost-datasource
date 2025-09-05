# Google Cloud Billing 비용 데이터 소스 플러그인

SpaceONE용 Google Cloud Billing 데이터 수집 플러그인 문서입니다.

## 📖 문서 구조

### 사용자 가이드
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./user-guide/Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - BigQuery 내보내기 개요 및 활용 가이드 ⭐ **NEW**
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./user-guide/BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드 ⭐ **NEW**
- **[📊 BigQuery의 Cloud Billing 데이터 테이블 이해하기](./user-guide/BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - 테이블 구조 개요 ⭐ **NEW**
- **[📈 표준 데이터 내보내기의 구조](./user-guide/표준%20데이터%20내보내기의%20구조.md)** - 표준 데이터 스키마 ⭐ **NEW**
- **[📋 자세한 데이터 내보내기의 구조](./user-guide/자세한%20데이터%20내보내기의%20구조.md)** - 상세 데이터 스키마 ⭐ **NEW**
- **[💰 가격 책정 데이터 내보내기의 구조](./user-guide/가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 데이터 스키마 ⭐ **NEW**
- **[🔍 Cloud Billing 데이터 내보내기의 쿼리 예시](./user-guide/Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - 실용적인 쿼리 모음 ⭐ **NEW**
- **[Google Cloud Billing Export 설정 가이드](./user-guide/billing-export-setup.md)** - Billing Export 설정 방법
- **[Google Cloud Billing 통합 가이드](./user-guide/integration-guide.md)** - 플러그인 설정 및 사용법  
- **[Google Cloud Billing 데이터 분석 가이드](./user-guide/data-analysis-guide.md)** - 데이터 구조 및 분석 방법
- **[Google Cloud Pricing Data Export 가이드](./user-guide/pricing-data-export-guide.md)** - 가격 정보 분석 및 활용 방법 ⭐ **NEW**
- **[크레딧 및 할인 분석 가이드](./user-guide/credits-and-discounts-analysis.md)** - 크레딧과 할인 상세 분석

### 개발자 문서
- **[프로젝트 요구사항 명세서 (PRD)](./development/prd.md)** - HTTP 파일 통합 기능 PRD
- **[구현 로드맵](./development/implementation-roadmap.md)** - 단계별 구현 계획
- **[Field Mapper 개발 가이드](./development/field-mapper-guide.md)** - Field Mapper 구현 방법
- **[register_datasource.yaml 분석 보고서](./development/register-datasource-analysis.md)** - 설정 파일 상세 분석 ⭐ **NEW**
- **[보안 모범 사례](./development/security-best-practices.md)** - 보안 설정 및 운영 가이드 ⭐ **NEW**

### 기술 명세서
- **[아키텍처 설계](./technical/architecture.md)** - 전체 시스템 아키텍처
- **[API 명세서](./technical/api-specifications.md)** - 상세 API 문서
- **[데이터 모델](./technical/data-models.md)** - 데이터 구조 정의

## 🚀 빠른 시작

1. **신규 사용자**: [🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./user-guide/Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)로 개요를 파악하세요
2. **설정 시작**: [⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./user-guide/BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)으로 단계별 설정을 진행하세요
3. **기존 사용자**: [Billing Export 설정 가이드](./user-guide/billing-export-setup.md)로 세부 설정을 확인하세요
4. **플러그인 설정**: [통합 가이드](./user-guide/integration-guide.md)로 SpaceONE 연동을 완료하세요
5. **데이터 분석**: [데이터 분석 가이드](./user-guide/data-analysis-guide.md)와 [크레딧 분석 가이드](./user-guide/credits-and-discounts-analysis.md)를 활용하세요
6. **개발자**: [PRD](./development/prd.md)와 [로드맵](./development/implementation-roadmap.md)을 확인하세요
7. **아키텍트**: [아키텍처 설계](./technical/architecture.md)를 참고하세요

## 📋 지원 기능

### 데이터 소스
- ✅ **BigQuery**: 실시간 쿼리 기반 (프로덕션 준비 완료)
  - 표준 청구 데이터 (Standard Billing Export)
  - 상세 사용량 데이터 (Detailed Usage Export)
- ✅ **HTTP 파일**: GCS 파일 직접 처리 (프로덕션 준비 완료)
  - 스트리밍 처리로 대용량 파일 지원
  - 자동 압축 해제 및 형식 감지
- ✅ **Pricing Data Export**: 가격 정보 분석 (완전 구현됨) ⭐ **NEW**
  - 실제 비용 vs 정가 비교
  - 할인율 자동 계산
  - 서비스별 가격 분석

### 파일 형식 지원
- **파일 형식**: CSV, JSON, Parquet
- **압축 형식**: .gz, .snappy, .zstd, .zst
- **스트리밍 처리**: 메모리 효율적 대용량 파일 처리

### 핵심 기능
- ✅ **이중 데이터 소스**: BigQuery + HTTP 파일 동시 지원
- ✅ **유연한 Field Mapper**: 커스터마이징 가능한 필드 매핑
- ✅ **크레딧 및 할인 분석**: 상세한 비용 최적화 분석
- ✅ **AmortizedCost 지원**: 크레딧 절대값 기반 비용 분석 ⭐ **NEW**
- ✅ **라벨/태그 기반 추적**: 프로젝트/리소스별 비용 추적
- ✅ **보안 강화**: 환경변수 기반 설정 및 자동 검증 도구 ⭐ **NEW**
- ✅ **가격 분석**: 실제 비용 vs 정가 비교 및 할인율 계산 ⭐ **NEW**
- ✅ **자동화 도구**: 설정 검증 및 보안 검사 스크립트 ⭐ **NEW**
- ✅ **동시성 제어**: 파일별 락 관리 및 세션 캐싱 (30-50% 성능 향상) ⭐ **NEW**
- ✅ **중복 처리 방지**: 동일 요청 자동 감지 및 스킵으로 리소스 절약 ⭐ **NEW**
- ✅ **gRPC 최적화**: 16MB 메시지 크기 지원으로 대용량 데이터 처리 ⭐ **NEW**
- ✅ **스키마 준수**: SpaceONE Job 스키마 자동 검증 및 필드 길이 제한 ⭐ **NEW**
- ✅ **오류 처리 강화**: ValidationError 방지 및 향상된 오류 관리 ⭐ **NEW**

## 📚 상세 문서

### 사용자 가이드
- **[통합 가이드](./user-guide/integration-guide.md)** - 전체 설정 및 사용 방법
- **[Billing Export 설정](./user-guide/billing-export-setup.md)** - Google Cloud 설정 방법
- **[데이터 분석 가이드](./user-guide/data-analysis-guide.md)** - 비용 데이터 활용법

### 개발자 문서
- **[PRD](./development/prd.md)** - 제품 요구사항 명세서
- **[구현 로드맵](./development/implementation-roadmap.md)** - 단계별 구현 계획
- **[동시성 관리](./development/concurrency-management.md)** - 성능 최적화 시스템 ⭐ **NEW**
- **[Field Mapper 가이드](./development/field-mapper-guide.md)** - 필드 매핑 구현

### 기술 문서
- **[아키텍처 설계](./technical/architecture.md)** - 시스템 구조 및 설계
- **[API 명세서](./technical/api-specifications.md)** - 상세 API 문서
- **[데이터 모델](./technical/data-models.md)** - 데이터 구조 정의
