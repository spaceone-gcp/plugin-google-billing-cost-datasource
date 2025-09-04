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
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │   BigQuery      │  │  HTTP File      │                  │
│  │  Connector      │  │  Connector      │ ← 신규 추가       │
│  └─────────────────┘  └─────────────────┘                  │
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
- **CostManager**: 비용 데이터 처리 및 변환 로직
- **JobManager**: 작업 스케줄링 및 분할
- **FieldMapper**: 데이터 필드 매핑 및 변환

### Connector Layer
- **BigqueryConnector**: BigQuery 데이터베이스 연동 (기존)
- **HttpFileConnector**: HTTP 파일 다운로드 및 처리 (신규)

### File Processing Layer (신규)
- **CompressionHandler**: 압축 파일 감지 및 해제 (gzip, snappy, zstd)
- **FileProcessorFactory**: 파일 형식 자동 감지 및 파서 생성
- **Parsers**: 파일 형식별 스트리밍 파서
  - **CSVParser**: CSV 파일 파싱
  - **JSONParser**: JSON/JSONL 파일 파싱  
  - **ParquetParser**: Parquet 파일 파싱

## 데이터 플로우

### BigQuery 모드
```
SpaceONE → CostManager → BigqueryConnector → BigQuery → 데이터 반환
```

### HTTP 파일 모드
```
SpaceONE → CostManager → HttpFileConnector → GCS/HTTP 파일 → CompressionHandler → FileProcessorFactory → Parser → FieldMapper → 데이터 반환
```

#### 상세 플로우
1. **HttpFileConnector**: GCS 버킷 또는 HTTP URL에서 파일 다운로드
2. **CompressionHandler**: 압축된 파일 자동 감지 및 해제 (gzip, snappy, zstd)
3. **FileProcessorFactory**: 파일 형식 자동 감지 및 적절한 파서 생성
4. **Parser**: CSV, JSON, Parquet 파일을 스트리밍 방식으로 파싱
5. **FieldMapper**: 프로바이더별 필드 매핑 및 SpaceONE 형식으로 변환

## 확장성 고려사항

### 수평 확장
- 파일 단위 병렬 처리 지원
- 커넥터별 독립적인 스케일링

### 수직 확장
- 메모리 효율적인 스트리밍 처리
- 청크 기반 데이터 처리

### 모듈화
- 파일 형식별 독립적인 파서
- 프로바이더별 Field Mapper 확장 가능
