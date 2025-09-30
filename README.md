# Google Cloud Billing Cost Datasource Plugin

SpaceONE plugin for collecting Google Cloud Billing data with support for multiple data sources including BigQuery, GCS, and HTTP files.

## Features

### SpaceONE Usage Data Type Support (v2.1) **NEW**
-  **Complete Usage Data Type Support**: SpaceONE UI now fully supports Usage-based analysis
-  **GCP Usage Amount Mapping**: Accurate extraction of usage quantities from GCP billing data
  - Networking services: seconds (e.g., 4,812 seconds for Cloud NAT Gateway)
  - Compute Engine: byte-seconds (e.g., 3.15e+14 byte-seconds for 81GB PD storage)
  - Storage services: various units with proper scaling
-  **Dual Extraction System**: Robust fallback system prevents data loss
  - Primary: Enhanced FieldMapper with 4-stage fallback
  - Secondary: Emergency extraction in main.py from additional_info
-  **Large-Scale Usage Support**: Handles massive usage amounts (315+ trillion byte-seconds)
-  **Real Usage Analysis**: Enable resource optimization based on actual usage patterns

### Data Sources (v2.0) **UPDATED**
-  **BigQuery**: Real-time querying and analysis (production ready)
  - Standard Billing Export (service/SKU level cost data)
  - Detailed Usage Export (resource-level granular analysis)
  - Credits Detail Mode for comprehensive credit analysis
-  **GCS Bucket**: Direct processing of billing export files in Cloud Storage (production ready)
  - Streaming processing for large files
  - Automatic compression detection and decompression
  - Date range filtering and batch processing
-  **HTTP File**: Direct URL-based file processing (production ready)
  - Support for public and authenticated URLs
  - Memory-efficient streaming processing
-  **Unified Source Parameter**: Single `source` parameter for all data sources **NEW**
  - `source: "bigquery"` - BigQuery data source
  - `source: "gcs"` - Google Cloud Storage bucket
  - `source: "http"` - HTTP/HTTPS file URLs

### File Format Support
- **File Formats**: CSV, JSON, Parquet
- **Compression**: .gz, .snappy, .zstd, .zst
- **Streaming Processing**: Memory-efficient large file handling
- **Smart Format Detection**: Automatic file format detection based on content

### Key Capabilities
-  **Triple Data Source**: BigQuery + GCS + HTTP unified support **UPDATED**
-  **Credits Detail Analysis**: Complete credit breakdown with individual credit information **NEW**
-  **Flexible Field Mapper**: Customizable field mapping for data transformation
-  **Cost Field Guarantee**: 100% cost field coverage with scientific notation support **NEW**
-  **Label/Tag-Based Tracking**: Project/resource-level cost tracking
-  **Resource-Level Analysis**: Individual VM, disk, network resource tracking
-  **GKE Advanced Support**: Namespace and fleet host project filtering
-  **gRPC Optimization**: Smart chunking for large dataset transmission **NEW**
-  **Modern Python Support**: Python 3.9+ with pyproject.toml configuration **NEW**
-  **Schema Compliance**: Full BigQuery schema compliance with nested field support **NEW**
-  **Error Handling**: Enhanced error management with comprehensive logging **NEW**

## Documentation

 **Complete documentation is available in Korean**: [`docs/ko/README.md`](./docs/ko/README.md)

### Quick Links
- **[ 문서 표준 가이드](./docs/ko/development/문서_표준_가이드.md)** - Documentation standards and management **UPDATED**
- **[ BigQuery_설정_가이드](./docs/ko/user-guide/BigQuery_설정_가이드.md)** - Complete BigQuery billing data setup
- **[ SpaceONE_호환성_가이드](./docs/ko/development/SpaceONE_호환성_가이드.md)** - Platform compatibility guide
- **[ 통합 테스트 가이드](./docs/ko/development/통합_테스트_가이드.md)** - Comprehensive testing guide including Credits Detail **UPDATED**
- **[통합_가이드](./docs/ko/user-guide/통합_가이드.md)** - Plugin configuration and usage
- **[데이터_분석_가이드](./docs/ko/user-guide/데이터_분석_가이드.md)** - Understanding billing data structure
- **[크레딧_및_할인_분석_가이드](./docs/ko/user-guide/크레딧_및_할인_분석_가이드.md)** - Advanced cost optimization analysis
- **[성능_최적화_가이드](./docs/ko/development/성능_최적화_가이드.md)** - Performance optimization and best practices
- **[보안_강화_사항](./docs/ko/보안_강화_사항.md)** - Security policies and improvements

## Quick Start

 **NEW**: Use our automated setup script for the fastest start:

```bash
./quick-start.sh
```

This script will:
-  Check your environment
-  Run security validation
-  Set up environment variables
-  Prepare production configuration
-  Guide you through next steps

### Manual Setup

#### 1. Set up Google Cloud Billing Export
Follow the [Billing Export Setup Guide](./docs/ko/user-guide/billing-export-setup.md) to configure:
- BigQuery export for detailed billing data
- Cloud Storage export for file-based processing

#### 2. Configure Service Account
Create a service account with appropriate permissions:
- **BigQuery mode**: `BigQuery Data Viewer`, `BigQuery Job User`
- **HTTP file mode**: `Storage Object Viewer`

#### 3. Security-Enhanced Configuration **NEW**

** Important**: Use environment variables instead of hardcoding sensitive data!

```bash
# 1. Copy environment template
cp examples/environment-variables-template.env .env

# 2. Edit with your actual values
vim .env

# 3. Set proper permissions
chmod 600 .env

# 4. Use production configuration
cp examples/register_datasource_production.yaml my-config.yaml
```

#### 4. Validate Configuration **NEW**

```bash
# Run security check
python3 examples/simple_security_check.py my-config.yaml
```

### Configuration Examples (v2.0)

#### BigQuery Mode
```yaml
options:
  source: "bigquery"  # NEW: Unified source parameter
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

#### GCS Bucket Mode **NEW**
```yaml
options:
  source: "gcs"  # NEW: Unified source parameter
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

#### HTTP File Mode
```yaml
options:
  source: "http"  # NEW: Unified source parameter
  provider: "google_cloud"
  base_url: "https://storage.googleapis.com/your-bucket/billing-export.csv.gz"
  field_mapper:
    cost: "cost"
    billed_date: "usage_start_time"
    currency: "currency"
    additional_info:
      credits: "credits"
      cost_at_list: "cost_at_list"

# secret_data not required for public URLs
```

#### Credits Detail Mode **NEW**
```yaml
# Add to any configuration above
task_options:
  credits_detail_mode: true
  credits_detail_limit: 50
  start: "2025-09"
  end: "2025-09"
  project_id: "your-project-id"
```

## Development

### Modern Python Setup (v2.0) **NEW**

This project now uses modern Python packaging with `pyproject.toml`:

```bash
# Install in development mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"

# Run linting and formatting
ruff check src/
ruff format src/

# Run type checking
mypy src/
```

### Project Structure
```
├── src/plugin/
│   ├── connector/          # Data source connectors (BigQuery, GCS, HTTP)
│   ├── manager/            # Business logic managers
│   ├── parser/             # File format parsers (CSV, JSON, Parquet)
│   ├── utils/              # Utility functions and transformers
│   └── main.py            # Plugin entry point
├── docs/ko/                # Korean documentation
├── test/                   # Test cases
├── examples/               # Configuration examples and test data
├── pyproject.toml          # Modern Python project configuration NEW
└── README.md              # This file
```

### Development Documentation
- **[ 코드_유지보수_가이드](./docs/ko/development/코드_유지보수_가이드.md)** - Code maintenance and best practices **NEW**
- **[ 성능_최적화_가이드](./docs/ko/development/성능_최적화_가이드.md)** - Performance optimization guide **NEW**
- **[ 에러_처리_패턴_가이드](./docs/ko/development/에러_처리_패턴_가이드.md)** - Error handling patterns **NEW**
- **[ 프로젝트_품질_체크리스트](./docs/ko/development/프로젝트_품질_체크리스트.md)** - Quality assurance checklist **NEW**
- **[ 시스템_아키텍처](./docs/ko/technical/시스템_아키텍처.md)** - System architecture overview

### User Documentation
- **[ Cloud Billing 데이터를 BigQuery로 내보내기](./docs/ko/user-guide/Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - BigQuery 내보내기 개요 및 활용 가이드
- **[ BigQuery로 Cloud Billing 데이터 내보내기 설정](./docs/ko/user-guide/BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드
- **[ BigQuery의 Cloud Billing 데이터 테이블 이해하기](./docs/ko/user-guide/BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - 테이블 구조 개요
- **[ 표준 데이터 내보내기의 구조](./docs/ko/user-guide/표준%20데이터%20내보내기의%20구조.md)** - 표준 데이터 스키마
- **[ 자세한 데이터 내보내기의 구조](./docs/ko/user-guide/자세한%20데이터%20내보내기의%20구조.md)** - 상세 데이터 스키마
- **[ 가격 책정 데이터 내보내기의 구조](./docs/ko/user-guide/가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 데이터 스키마
- **[ Cloud Billing 데이터 내보내기의 쿼리 예시](./docs/ko/user-guide/Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - 실용적인 쿼리 모음
- **[ 데이터 분석 가이드](./docs/ko/user-guide/data-analysis-guide.md)** - BigQuery 스키마 및 쿼리 분석
- **[ Pricing Data Export 가이드](./docs/ko/user-guide/pricing-data-export-guide.md)** - 가격 데이터 분석

## Recent Updates

### v2.0.1 (2025-09-18) - Date Range Enhancement **NEW**

####  Key Improvements
- **Automatic End Date Setting**: When end date is not provided, automatically sets to current month
- **BigQuery SQL Compatibility**: Fixed `TIMESTAMP + INTERVAL` syntax for BigQuery compatibility
- **Enhanced Logging**: Clear logging for date processing and automatic settings

####  Date Processing Features
```python
# Automatic end date setting
task_options = {
    "start": "2024-09"      # End date automatically set to current month (2025-09)
}

# Explicit end date
task_options = {
    "start": "2024-09",
    "end": "2024-12"        # Explicit end date
}
```

####  Technical Improvements
- **SQL Compatibility**: `TIMESTAMP(DATE_ADD(DATE('2025-09-01'), INTERVAL 1 MONTH))` instead of `TIMESTAMP + INTERVAL`
- **Logging Enhancement**: INFO level logging for automatic date settings
- **PARTITIONDATE Optimization**: Automatic range expansion for optimal BigQuery performance

####  Logging Examples
```
[SQL 생성] 종료일이 None이므로 현재월로 자동 설정: 2025-09
[PARTITIONDATE 범위] 원본 범위: 2024-09 ~ 2025-09, 확장된 범위: 2024-08-01 ~ 2025-10-31
[SQL 생성] 날짜 범위 필터: 2024-09 ~ 2025-09
```

####  User Benefits
- **Convenience**: No need to specify end date for current month queries
- **Stability**: Fixed BigQuery SQL execution errors
- **Transparency**: Clear logging shows automatic date processing

####  Compatibility
- **Full Backward Compatibility**: All existing API usage remains unchanged
- **Additional Features**: Enhanced functionality with automatic date handling

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## Support

For detailed documentation and support, please refer to the Korean documentation in [`docs/ko/`](./docs/ko/) directory.