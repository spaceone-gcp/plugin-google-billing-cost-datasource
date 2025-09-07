# 아키텍처 설계

Google Cloud Billing 플러그인의 전체 시스템 아키텍처를 설명합니다.

## 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    SpaceONE Core                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Plugin Service Layer                         │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │  DataSource     │  │   Cost Service  │                  │
│  │   Service       │  │                 │                  │
│  └─────────────────┘  └─────────────────┘                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Manager Layer                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ DataSource      │  │  Cost Manager   │  │ Job Manager │  │
│  │  Manager        │  │                 │  │             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│                       │                                     │
│                       ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │            Field Mapper                                 ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Connector Layer                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   BigQuery      │  │  HTTP File      │  │   Pricing   │  │
│  │  Connector      │  │  Connector      │  │  Connector  │  │
│  │                 │  │                 │  │ (신규 추가) │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              File Processing Layer                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ Compression     │  │ File Processor  │  │   Parsers   │  │
│  │   Handler       │  │    Factory      │  │ (CSV/JSON/  │  │
│  │                 │  │                 │  │  Parquet)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 컴포넌트 상세

### Service Layer
- **DataSource Service**: 플러그인 초기화 및 검증
- **Cost Service**: 비용 데이터 조회 및 연결 계정 관리

### Manager Layer
- **DataSourceManager**: 플러그인 메타데이터 관리
- **CostManager**: 비용 데이터 처리 및 변환 로직 (✅ 향상됨)
  - AmortizedCost 메트릭 지원 (credits_amount 기반)
  - 향상된 select_cost 옵션 (list_price, after_credits, net_cost)
  - cost_metric 옵션으로 다양한 비용 계산 방식 지원
  - 상세 사용량 데이터(detailed usage) 자동 감지 및 처리
- **JobManager**: 작업 스케줄링 및 분할
- **FieldMapper**: 데이터 필드 매핑 및 변환 (✅ 확장됨)
  - Pricing 관련 필드 매핑 추가 (service_id, sku_id, list_price 등)
  - AmortizedCost 지원을 위한 credits_amount 매핑
  - 리소스 식별 필드 지원 (resource_name, resource_global_name)
  - 할인율 및 가격 계층 정보 매핑

### Connector Layer
- **BigqueryConnector**: BigQuery 데이터베이스 연동 (기존)
  - 향상된 private_key 검증 및 정리 기능
  - 테스트 모드 지원으로 개발 환경 호환성 개선
  - 상세한 인증 오류 진단 및 메시지 제공
- **HttpFileConnector**: HTTP 파일 다운로드 및 처리 (기존)
  - GCS 버킷 및 HTTP URL 다운로드 지원
  - 파일 크기 제한 및 압축 형식 자동 감지
- **PricingConnector**: Google Cloud Pricing Data Export 연동 (✅ 구현 완료)
  - cloud_pricing_export 테이블 직접 조회
  - 실제 청구 데이터와 정가 비교 분석 (compare_billing_vs_pricing)
  - 서비스별 가격 정보 요약 제공 (get_service_pricing_summary)
  - 계층별 요금제(tiered_rates) 파싱 및 처리
  - 숫자 타입 원본 보존으로 정확한 가격 계산
  - Pricing 테이블 목록 조회 기능 (list_pricing_tables)

### File Processing Layer (신규)
- **CompressionHandler**: 압축 파일 감지 및 해제 (gzip, snappy, zstd)
- **FileProcessorFactory**: 파일 형식 자동 감지 및 파서 생성
- **Parsers**: 파일 형식별 스트리밍 파서
  - **CSVParser**: CSV 파일 파싱
  - **JSONParser**: JSON/JSONL 파일 파싱  
  - **ParquetParser**: Parquet 파일 파싱

### Concurrency Management Layer (신규)
- **ConcurrencyManager**: 파일 처리 동시성 제어 및 세션 캐싱
  - 파일별 락 관리로 중복 처리 방지
  - GCS 세션 캐싱으로 성능 최적화 (TTL 5분)
  - 처리 상태 추적 및 통계 제공
- **RequestDeduplicator**: 중복 요청 감지 및 방지
  - 요청 해시 생성 및 TTL 기반 중복 제거 (기본 60초)
  - 동일 파라미터 요청 방지로 리소스 효율성 향상

## 데이터 플로우

### BigQuery 모드 (표준 청구 데이터)
```
SpaceONE → CostManager → BigqueryConnector → BigQuery → 데이터 반환
```

### HTTP 파일 모드 (파일 기반 청구 데이터)
```
SpaceONE → CostManager → HttpFileConnector (세션 캐싱) → ConcurrencyManager (락 관리) → GCS/HTTP 파일 → CompressionHandler → FileProcessorFactory → Parser → FieldMapper → 데이터 반환
```

### Pricing 데이터 모드 (가격 정보 조회)
```
SpaceONE → CostManager → PricingConnector → cloud_pricing_export 테이블 → 가격 데이터 반환
```

### 비용 비교 분석 플로우
```
SpaceONE → CostManager → BigqueryConnector (청구 데이터) + PricingConnector (정가 데이터) → 비교 분석 → 할인율 계산 → 결과 반환
```

#### 상세 플로우
1. **ConcurrencyManager**: 요청 중복 검사 및 파일 처리 락 획득
2. **HttpFileConnector**: GCS 버킷 또는 HTTP URL에서 파일 다운로드 (캐시된 세션 재사용)
3. **CompressionHandler**: 압축된 파일 자동 감지 및 해제 (gzip, snappy, zstd)
4. **FileProcessorFactory**: 파일 형식 자동 감지 및 적절한 파서 생성
5. **Parser**: CSV, JSON, Parquet 파일을 스트리밍 방식으로 파싱
6. **FieldMapper**: 프로바이더별 필드 매핑 및 SpaceONE 형식으로 변환

## 확장성 고려사항

### 수평 확장
- 파일 단위 병렬 처리 지원
- 커넥터별 독립적인 스케일링
- 다중 데이터 소스 동시 처리 (BigQuery + 파일 + Pricing)

### 수직 확장
- 메모리 효율적인 스트리밍 처리
- 청크 기반 데이터 처리
- 압축 해제 및 파싱 최적화

### 모듈화
- 파일 형식별 독립적인 파서
- 프로바이더별 Field Mapper 확장 가능
- 커넥터 레이어의 플러그인 아키텍처

### 보안 및 신뢰성
- 향상된 인증 키 검증 및 오류 진단
- 테스트 모드를 통한 개발 환경 지원
- 파일 크기 제한 및 타임아웃 관리

### 성능 최적화
- 스트리밍 기반 대용량 파일 처리
- 압축 형식별 최적화된 해제 알고리즘
- 메모리 사용량 최소화를 위한 배치 처리
