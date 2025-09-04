# Google Cloud Billing Export 설정 가이드

Google Cloud Billing 데이터를 SpaceONE에서 활용하기 위한 Billing Export 설정 방법을 상세히 안내합니다.

## 개요

Google Cloud는 두 가지 방식으로 Billing 데이터를 내보낼 수 있습니다:

1. **BigQuery 내보내기**: 실시간 쿼리 및 분석 (권장)
2. **파일 내보내기**: Cloud Storage를 통한 파일 기반 처리

## BigQuery 내보내기 설정

### 1. 내보내기 활성화

1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동
2. **BigQuery 내보내기** 탭 선택
3. 다음 정보를 입력:
   - **프로젝트 ID**: BigQuery 데이터셋을 생성할 프로젝트
   - **데이터셋 ID**: `billing_export` (권장)
   - **테이블 접두사**: `gcp_billing_export_v1_` (기본값)

### 2. 데이터 유형 선택

#### 표준 사용량 비용 데이터 vs 상세 사용량 비용 데이터

| 특성 | 표준 사용량 | 상세 사용량 |
|:---|:---|:---|
| **데이터 세분화** | 서비스/SKU 수준 | 개별 리소스 수준 |
| **테이블 크기** | 작음 | 큼 |
| **분석 깊이** | 기본적 | 상세한 |
| **권장 용도** | 간단한 비용 추적 | 정밀한 비용 분석 |

> **⚠️ 권장사항**: **상세 사용량 비용 데이터**를 선택하세요. 표준 데이터의 모든 기능을 포함하면서 더 상세한 분석이 가능합니다.

### 3. 생성되는 테이블 구조

```
프로젝트ID.데이터셋ID.gcp_billing_export_v1_<BILLING_ACCOUNT_ID>
```

**예시**: `my-project.billing_export.gcp_billing_export_v1_01ABCD-234567-EFGHIJ`

### 4. 권한 설정

BigQuery 내보내기를 사용하는 서비스 계정에 다음 역할을 부여:

- `BigQuery Data Viewer`: 데이터 읽기 권한
- `BigQuery Job User`: 쿼리 실행 권한
- `BigQuery Metadata Viewer`: 테이블 메타데이터 조회 권한 (선택사항)

## 파일 내보내기 설정

### 1. Cloud Storage 버킷 준비

1. **Cloud Storage**에서 새 버킷 생성 또는 기존 버킷 사용
2. 버킷 위치는 **비용 최적화**를 위해 가까운 리전 선택
3. **Uniform bucket-level access** 활성화 권장

### 2. 파일 내보내기 활성화

1. **Google Cloud 콘솔**에서 **결제 > 결제 내보내기**로 이동
2. **파일 내보내기** 탭 선택
3. 다음 정보를 입력:
   - **버킷**: 데이터를 저장할 GCS 버킷
   - **보고서 접두사**: `billing-export/` (권장)
   - **파일 형식**: CSV, JSON, Parquet 중 선택

### 3. 파일 형식별 특성

| 형식 | 크기 | 처리 속도 | 압축률 | 권장 용도 |
|:---|:---|:---|:---|:---|
| **CSV** | 큼 | 느림 | 낮음 | 호환성 중시 |
| **JSON** | 매우 큼 | 느림 | 낮음 | 구조화된 데이터 |
| **Parquet** | 작음 | 빠름 | 높음 | **성능 중시** (권장) |

### 4. 생성되는 파일 구조

```
gs://버킷명/보고서접두사/YYYY-MM-DD/gcp_billing_export_v1_<BILLING_ACCOUNT_ID>_YYYYMMDD_HHMMSS.파일확장자
```

**예시**: `gs://my-billing-bucket/billing-export/2024-07-15/gcp_billing_export_v1_01ABCD-234567-EFGHIJ_20240715_120000.parquet.gz`

### 5. 권한 설정

파일 내보내기를 사용하는 서비스 계정에 다음 역할을 부여:

- `Storage Object Viewer`: 파일 읽기 권한
- `Storage Legacy Bucket Reader`: 버킷 목록 조회 권한 (선택사항)

## 내보내기 활성화 후 확인사항

### 1. 데이터 생성 시점

- **첫 데이터 생성**: 활성화 **다음 날**부터 시작
- **데이터 업데이트**: 일 1~2회 (보통 UTC 기준 오전 중)
- **과거 데이터**: 활성화 이전 데이터는 내보내지지 않음

### 2. BigQuery 테이블 확인

```sql
-- 테이블 존재 확인
SELECT 
  table_name,
  creation_time,
  row_count
FROM 
  `프로젝트ID.데이터셋ID.INFORMATION_SCHEMA.TABLES`
WHERE 
  table_name LIKE 'gcp_billing_export_v1_%';

-- 최신 데이터 확인
SELECT 
  MIN(usage_start_time) as earliest_date,
  MAX(usage_start_time) as latest_date,
  COUNT(*) as total_records
FROM 
  `프로젝트ID.데이터셋ID.gcp_billing_export_v1_청구계정ID`;
```

### 3. Cloud Storage 파일 확인

```bash
# gsutil을 사용한 파일 목록 확인
gsutil ls -l gs://버킷명/보고서접두사/

# 최신 파일 내용 샘플 확인 (Parquet의 경우)
gsutil cp gs://버킷명/보고서접두사/최신파일 .
```

## 비용 최적화 팁

### BigQuery 내보내기 비용 절약

1. **쿼리 최적화**: `WHERE` 절로 날짜 범위 제한
2. **파티셔닝 활용**: `usage_start_time` 기준 파티션 쿼리
3. **컬럼 선택**: `SELECT *` 대신 필요한 컬럼만 선택

### Cloud Storage 내보내기 비용 절약

1. **스토리지 클래스**: 자주 접근하지 않는 경우 Coldline/Archive 사용
2. **수명 주기 정책**: 오래된 파일 자동 삭제 설정
3. **압축**: Parquet + gzip 조합 권장

## 문제 해결

### 자주 발생하는 문제

1. **테이블이 생성되지 않음**
   - 내보내기 활성화 후 24-48시간 대기
   - 청구 계정에 실제 비용이 발생했는지 확인

2. **권한 오류**
   - 서비스 계정에 적절한 IAM 역할 부여 확인
   - 프로젝트 레벨 권한 vs 리소스 레벨 권한 구분

3. **데이터가 최신이 아님**
   - Billing 데이터는 1-2일 지연이 정상
   - 실시간 데이터가 아닌 배치 처리임을 이해

### 지원 리소스

- **[Google Cloud Billing Export 공식 문서](https://cloud.google.com/billing/docs/how-to/export-data-bigquery?hl=ko)**
- **[BigQuery 데이터 스키마 상세](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables?hl=ko)**
- **[Cloud Storage 파일 내보내기](https://cloud.google.com/billing/docs/how-to/export-data-file?hl=ko)**

---

> **다음 단계**: Billing Export 설정이 완료되면 [SpaceONE 통합 가이드](./integration-guide.md)를 참고하여 플러그인을 설정하세요.
