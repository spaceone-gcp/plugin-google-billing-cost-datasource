# spaceone.api.cost_analysis.plugin.Job.get_tasks API 응답 형식

## 개요

`spaceone.api.cost_analysis.plugin.Job.get_tasks` API는 SpaceONE 플러그인에서 비용 데이터 수집 작업(Task)을 생성하고 반환하는 핵심 API입니다. 이 문서는 해당 API의 응답 형식과 구조를 상세히 설명합니다.

## 기본 응답 구조

### 1. 전체 응답 스키마

```json
{
  "tasks": [
    {
      "task_options": {
        // 작업별 옵션 정보
      }
    }
  ],
  "changed": [
    {
      "start": "YYYY-MM"
    }
  ]
}
```

### 2. 필수 필드

| 필드명 | 타입 | 필수 여부 | 설명 |
|--------|------|-----------|------|
| `tasks` | Array | 필수 | 생성된 작업 목록 |
| `changed` | Array | 필수 | 변경된 항목 정보 |

## 상세 필드 설명

### 2.1. tasks 필드

각 Task는 다음과 같은 구조를 가집니다:

```json
{
  "task_options": {
    "billing_account_id": "string",
    "billing_dataset_id": "string", 
    "billing_export_project_id": "string",
    "data_source_type": "string",
    "project_id": "string",
    "start": "YYYY-MM"
  }
}
```

#### task_options 필드 상세

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `billing_account_id` | string | Google Cloud 청구 계정 ID | "01FD8E-B4DDC1-EAB69F" |
| `billing_dataset_id` | string | BigQuery 청구 데이터셋 ID | "multi_region_billing_data" |
| `billing_export_project_id` | string | 청구 데이터를 내보낸 프로젝트 ID | "mkkang-project" |
| `data_source_type` | string | 데이터 소스 타입 | "bigquery", "gcs", "http" |
| `project_id` | string | 대상 프로젝트 ID | "full-depth-prj" |
| `start` | string | 시작 날짜 (YYYY-MM 형식) | "2024-09" |

### 2.2. changed 필드

변경된 항목을 나타내는 배열입니다:

```json
[
  {
    "start": "2024-09"
  }
]
```

#### changed 항목 필드

| 필드명 | 타입 | 설명 | 제약사항 |
|--------|------|------|----------|
| `start` | string | 변경 시작 날짜 | 최대 7자 (YYYY-MM 형식) |

## 실제 응답 예시

### 3.1. BigQuery 데이터 소스 응답 예시

```json
{
  "tasks": [
    {
      "task_options": {
        "billing_account_id": "01FD8E-B4DDC1-EAB69F",
        "billing_dataset_id": "multi_region_billing_data",
        "billing_export_project_id": "mkkang-project",
        "data_source_type": "bigquery",
        "project_id": "full-depth-prj",
        "start": "2024-09"
      }
    },
    {
      "task_options": {
        "billing_account_id": "01FD8E-B4DDC1-EAB69F",
        "billing_dataset_id": "multi_region_billing_data",
        "billing_export_project_id": "mkkang-project",
        "data_source_type": "bigquery",
        "project_id": "mhlee-project",
        "start": "2024-09"
      }
    },
    {
      "task_options": {
        "billing_account_id": "01FD8E-B4DDC1-EAB69F",
        "billing_dataset_id": "multi_region_billing_data",
        "billing_export_project_id": "mkkang-project",
        "data_source_type": "bigquery",
        "project_id": "mkkang-project",
        "start": "2024-09"
      }
    },
    {
      "task_options": {
        "billing_account_id": "01FD8E-B4DDC1-EAB69F",
        "billing_dataset_id": "multi_region_billing_data",
        "billing_export_project_id": "mkkang-project",
        "data_source_type": "bigquery",
        "project_id": "spaceone-aramco-project",
        "start": "2024-09"
      }
    }
  ],
  "changed": [
    {
      "start": "2024-09"
    }
  ]
}
```

### 3.2. 빈 응답 (에러 발생 시)

```json
{
  "tasks": [],
  "changed": [
    {
      "start": "2024-12",
      "reason": "No data available",
      "timestamp": "2024-12-25 10:30:45"
    }
  ]
}
```

## 응답 생성 로직

### 4.1. 데이터 소스 타입별 분기

JobManager는 다음과 같은 데이터 소스 타입을 지원합니다:

- **BigQuery**: `data_source_type: "bigquery"`
- **GCS**: `data_source_type: "gcs"`  
- **HTTP**: `data_source_type: "http"`

### 4.2. 프로젝트별 작업 생성

BigQuery 모드에서는 다음과 같은 로직으로 작업을 생성합니다:

1. **프로젝트 발견**: BigQuery에서 청구 데이터가 있는 프로젝트 목록 조회
2. **작업 생성**: 각 프로젝트별로 개별 작업 생성
3. **중복 제거**: 동일한 프로젝트에 대한 중복 작업 방지
4. **검증**: 생성된 작업의 유효성 검증

### 4.3. 날짜 처리 규칙

- **형식**: `YYYY-MM` (예: "2024-09")
- **기본값**: 현재 월 사용
- **검증**: 미래 날짜나 너무 과거 날짜는 자동 조정
- **제한**: `changed.start` 필드는 최대 7자까지만 허용

## 에러 처리

### 5.1. 응답 검증

모든 응답은 다음 조건을 만족해야 합니다:

```python
def validate_job_response(response: dict) -> bool:
    # 1. 딕셔너리 타입 검증
    # 2. 필수 필드 존재 검증 ("tasks", "changed")
    # 3. 필드 타입 검증 (둘 다 list 타입)
    # 4. changed.start 길이 검증 (7자 이하)
```

### 5.2. 에러 시 Fallback 응답

검증 실패나 예외 발생 시 다음과 같은 빈 응답을 반환합니다:

```json
{
  "tasks": [],
  "changed": [
    {
      "start": "2024-12",
      "reason": "Task generation failed: [에러 메시지]",
      "timestamp": "2024-12-25 10:30:45"
    }
  ]
}
```

## 성능 특성

### 6.1. 작업 생성 성능

- **순차 처리**: 안정성을 위해 프로젝트별 순차 처리 방식 채택
- **캐싱**: 활성 프로젝트 목록을 30분간 캐싱하여 성능 최적화
- **배치 처리**: 대량 데이터 처리 시 적절한 배치 크기로 분할

### 6.2. 로깅 및 모니터링

```
[JobManager.get_tasks] Task generation completed successfully - 
Total tasks: 4, Changed items: 1, Data source type: bigquery
```

## 주의사항

### 7.1. 제약사항

- `changed.start` 필드는 SpaceONE 스키마 요구사항에 따라 **최대 7자**로 제한
- 프로젝트 ID는 Google Cloud 프로젝트 명명 규칙을 따라야 함
- 날짜 형식은 반드시 `YYYY-MM` 형식을 사용

### 7.2. 호환성

- SpaceONE Core 2.0+ 호환
- gRPC 프로토콜 기반 통신
- JSON 직렬화 지원

## 관련 파일

- **구현**: `src/plugin/manager/job_manager.py`
- **검증**: `src/plugin/utils/error_handler.py`
- **테스트**: `grpcurl_bigquery_get_tasks.sh`
- **로그**: `server_debug.log`

---

**마지막 업데이트**: 2025년 9월 29일  
**버전**: v2.0  
**주요 기능**: Job get_tasks API 응답 형식 정의
