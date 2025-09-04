# `grpcurl`을 이용한 gRPC API 테스트 가이드

## 📋 개요

이 문서는 `test/grpc/test_grpcurl_batch.py` 스크립트를 사용하여 플러그인의 gRPC API를 테스트하는 방법을 안내합니다. 이 스크립트는 `grpcurl`을 사용하여 다양한 시나리오에 대한 API 호출을 자동화하고 결과를 요약해줍니다.

직접 `grpcurl` 명령어를 사용하는 것은 복잡한 JSON 페이로드와 인증 정보 때문에 번거롭습니다. 따라서 이 스크립트를 사용하는 것을 적극 권장합니다.

## ⚙️ 사전 준비

1.  **gRPC 서버 실행**: 플러그인 gRPC 서버가 로컬에서 실행 중이어야 합니다. 다음 명령어를 사용하여 서버를 시작하세요.
    ```bash
    spaceone grpc_server
    ```
    서버는 기본적으로 `localhost:50051`에서 실행됩니다.

2.  **`grpcurl` 설치**: `grpcurl`이 시스템에 설치되어 있어야 합니다.
    ```bash
    # macOS (Homebrew)
    brew install grpcurl

    # 다른 시스템의 경우 아래 공식 문서를 참고하세요.
    # https://github.com/fullstorydev/grpcurl?tab=readme-ov-file#installation
    ```

3.  **(선택) 로컬 웹 서버**: 로컬 파일(e.g., `http://localhost:8080/...`)을 테스트하려면, 프로젝트 루트에서 간단한 웹 서버를 실행할 수 있습니다.
    ```bash
    # Python 3
    python -m http.server 8080
    ```

## ▶️ 테스트 실행

프로젝트 루트 디렉토리에서 다음 명령어를 실행하여 전체 테스트를 시작합니다.

```bash
python test/grpc/test_grpcurl_batch.py
```

스크립트는 정의된 모든 테스트 케이스를 순차적으로 실행하고, 각 테스트의 성공 여부와 최종 요약 정보를 터미널에 출력합니다.

## 🧪 테스트 케이스 상세

`test_grpcurl_batch.py` 스크립트는 다음과 같은 주요 API와 데이터 소스 조합을 테스트합니다.

### 1. `Cost.get_data`
- **GitHub Raw URL (CSV)**: 원격 CSV 파일 처리 기능 테스트
- **로컬 서버 URL (JSON.GZ)**: 압축된 JSON 파일 처리 기능 테스트
- **Google Storage (일반)**: Google Cloud Storage의 파일 처리 기능 테스트
- **Google Cloud Billing**: `provider: google_cloud` 옵션과 상세 `field_mapper`를 사용하여 Google Cloud Billing 데이터 처리 기능을 중점적으로 테스트

### 2. `DataSource.init`
- **HTTP 파일**: `base_url`을 사용한 초기화 테스트
- **Google Storage**: `bucket_name`을 사용한 초기화 테스트

### 3. `DataSource.verify`
- **HTTP 파일**: `base_url`과 `secret_data`를 사용한 연결 검증 테스트
- **Google Storage**: `bucket_name`과 `secret_data`를 사용한 연결 검증 테스트

### 4. `Job.get_tasks`
- **Google Storage**: 동기화 작업을 위한 태스크 생성 기능 테스트

## 📊 예상 출력 결과 (예시)

테스트가 성공적으로 실행되면 다음과 유사한 출력을 볼 수 있습니다.

```
🚀 gRPC API 배치 테스트 시작
gRPC 서버가 localhost:50051에서 실행 중인지 확인하세요.

============================================================
테스트: Cost.get_data - GitHub Raw URL (CSV)
테스트 타입: http_file, API 타입: get_data
Base URL: https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/cost_example.csv
============================================================
...
실행 시간: 1.23초
종료 코드: 0
표준 출력:
{
  "result": {
    "cost": 500.0,
    ...
  }
}
✅ 테스트 성공!

... (다른 테스트 실행) ...

============================================================
📊 테스트 결과 요약
============================================================
Cost.get_data - GitHub Raw URL (CSV): ✅ 성공
Cost.get_data - Local Server (JSON.GZ): ✅ 성공
Cost.get_data - Google Storage (Generic): ✅ 성공
Cost.get_data - Google Cloud Billing: ✅ 성공
DataSource.init - HTTP File: ✅ 성공
DataSource.init - Google Storage: ✅ 성공
DataSource.verify - HTTP File: ✅ 성공
DataSource.verify - Google Storage: ✅ 성공
Job.get_tasks - Google Storage: ✅ 성공

총 테스트: 9
성공: 9
실패: 0

🎉 모든 테스트가 성공했습니다!
```

## 💡 문제 해결

- **`Connection refused` 오류**: gRPC 서버가 `localhost:50051`에서 실행 중인지 확인하세요.
- **`grpcurl: command not found` 오류**: `grpcurl`이 올바르게 설치되었는지 확인하세요.
- **테스트 실패**: 실패한 테스트의 "표준 오류" 출력을 확인하여 원인을 파악하세요. 대부분의 경우 요청 데이터나 플러그인 로직의 문제일 수 있습니다.