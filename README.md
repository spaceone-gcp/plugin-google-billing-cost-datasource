# Google Cloud Billing Cost Datasource Plugin

SpaceONE plugin for collecting Google Cloud Billing data with support for both BigQuery and HTTP file data sources.

## Features

### Data Sources
- ✅ **BigQuery**: Real-time querying and analysis (production ready)
  - Standard Billing Export (service/SKU level cost data)
  - Detailed Usage Export (resource-level granular analysis)
- ✅ **HTTP File**: Direct processing of GCS billing export files (production ready)
  - Streaming processing for large files
  - Automatic compression detection and decompression
- ✅ **Pricing Data Export**: Price analysis and comparison (fully implemented) ⭐ **NEW**
  - Actual cost vs. list price comparison
  - Automatic discount rate calculation
  - Service-level price analysis

### File Format Support
- **File Formats**: CSV, JSON, Parquet
- **Compression**: .gz, .snappy, .zstd, .zst
- **Streaming Processing**: Memory-efficient large file handling

### Key Capabilities
- ✅ **Dual Data Source**: BigQuery + HTTP file simultaneous support
- ✅ **Flexible Field Mapper**: Customizable field mapping for data transformation
- ✅ **Credits & Discount Analysis**: Detailed cost optimization analysis
- ✅ **Label/Tag-Based Tracking**: Project/resource-level cost tracking
- ✅ **Resource-Level Analysis**: Individual VM, disk, network resource tracking ⭐ **NEW**
- ✅ **GKE Advanced Support**: Namespace and fleet host project filtering ⭐ **NEW**
- ✅ **Security Enhanced**: Environment variable-based configuration with validation tools ⭐ **NEW**
- ✅ **Price Analysis**: Actual cost vs. list price comparison and discount rate calculation ⭐ **NEW**
- ✅ **Automation Tools**: Configuration validation and security check scripts ⭐ **NEW**
- ✅ **Schema Compliance**: SpaceONE Job schema validation with automatic field length restriction ⭐ **NEW**
- ✅ **Error Handling**: Enhanced error management with ValidationError prevention ⭐ **NEW**

## Documentation

📖 **Complete documentation is available in Korean**: [`docs/ko/README.md`](./docs/ko/README.md)

### Quick Links
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./docs/ko/user-guide/Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - BigQuery export overview and guide ⭐ **NEW**
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./docs/ko/user-guide/BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - Step-by-step setup guide ⭐ **NEW**
- **[📊 BigQuery의 Cloud Billing 데이터 테이블 이해하기](./docs/ko/user-guide/BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - Table structure overview ⭐ **NEW**
- **[💰 가격 책정 데이터 내보내기의 구조](./docs/ko/user-guide/가격%20책정%20데이터%20내보내기의%20구조.md)** - Pricing data schema ⭐ **NEW**
- **[🔍 Cloud Billing 데이터 내보내기의 쿼리 예시](./docs/ko/user-guide/Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - Practical query examples ⭐ **NEW**
- **[Billing Export Setup Guide](./docs/ko/user-guide/billing-export-setup.md)** - How to set up Google Cloud Billing Export
- **[Integration Guide](./docs/ko/user-guide/integration-guide.md)** - Plugin configuration and usage
- **[Data Analysis Guide](./docs/ko/user-guide/data-analysis-guide.md)** - Understanding billing data structure
- **[Pricing Data Export Guide](./docs/ko/user-guide/pricing-data-export-guide.md)** - Price analysis and comparison ⭐ **NEW**
- **[Credits & Discounts Analysis](./docs/ko/user-guide/credits-and-discounts-analysis.md)** - Advanced cost optimization analysis
- **[Security Best Practices](./docs/ko/development/security-best-practices.md)** - Security configuration guide ⭐ **NEW**

## Quick Start

🚀 **NEW**: Use our automated setup script for the fastest start:

```bash
./quick-start.sh
```

This script will:
- ✅ Check your environment
- ✅ Run security validation
- ✅ Set up environment variables
- ✅ Prepare production configuration
- ✅ Guide you through next steps

### Manual Setup

#### 1. Set up Google Cloud Billing Export
Follow the [Billing Export Setup Guide](./docs/ko/user-guide/billing-export-setup.md) to configure:
- BigQuery export for detailed billing data
- Cloud Storage export for file-based processing

#### 2. Configure Service Account
Create a service account with appropriate permissions:
- **BigQuery mode**: `BigQuery Data Viewer`, `BigQuery Job User`
- **HTTP file mode**: `Storage Object Viewer`

#### 3. Security-Enhanced Configuration ⭐ **NEW**

**⚠️ Important**: Use environment variables instead of hardcoding sensitive data!

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

#### 4. Validate Configuration ⭐ **NEW**

```bash
# Run security check
python3 examples/simple_security_check.py my-config.yaml
```

### Legacy Configuration (Not Recommended)

#### BigQuery Mode
```yaml
options:
  billing_export_project_id: "your-project-id"
  billing_dataset_id: "billing_export"
  billing_account_id: "XXXXXX-XXXXXX-XXXXXX"

secret_data:
  type: "service_account"
  project_id: "your-project-id"
  private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email: "service-account@your-project.iam.gserviceaccount.com"
  token_uri: "https://oauth2.googleapis.com/token"
```

#### HTTP File Mode
```yaml
options:
  data_source_type: "http_file"
  provider: "google_cloud"
  bucket_name: "your-billing-export-bucket"
  file_pattern: "gcp_billing_export_v1_*.csv.gz"
  field_mapping:
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

## Development

### Project Structure
```
├── src/plugin/
│   ├── connector/          # Data source connectors
│   ├── manager/            # Business logic managers
│   ├── parser/             # File format parsers
│   └── utils/              # Utility functions
├── docs/ko/                # Korean documentation
└── test/                   # Test cases
```

### Development Documentation
- **[PRD](./docs/ko/development/prd.md)** - Product requirements
- **[Implementation Roadmap](./docs/ko/development/implementation-roadmap.md)** - Development phases
- **[Architecture Design](./docs/ko/technical/architecture.md)** - System architecture

### User Documentation
- **[🏗️ Cloud Billing 데이터를 BigQuery로 내보내기](./docs/ko/user-guide/Cloud%20Billing%20데이터를%20BigQuery로%20내보내기.md)** - BigQuery 내보내기 개요 및 활용 가이드
- **[⚙️ BigQuery로 Cloud Billing 데이터 내보내기 설정](./docs/ko/user-guide/BigQuery로%20Cloud%20Billing%20데이터%20내보내기%20설정.md)** - 단계별 설정 가이드
- **[📊 BigQuery의 Cloud Billing 데이터 테이블 이해하기](./docs/ko/user-guide/BigQuery의%20Cloud%20Billing%20데이터%20테이블%20이해하기.md)** - 테이블 구조 개요
- **[📈 표준 데이터 내보내기의 구조](./docs/ko/user-guide/표준%20데이터%20내보내기의%20구조.md)** - 표준 데이터 스키마
- **[📋 자세한 데이터 내보내기의 구조](./docs/ko/user-guide/자세한%20데이터%20내보내기의%20구조.md)** - 상세 데이터 스키마
- **[💰 가격 책정 데이터 내보내기의 구조](./docs/ko/user-guide/가격%20책정%20데이터%20내보내기의%20구조.md)** - 가격 데이터 스키마
- **[🔍 Cloud Billing 데이터 내보내기의 쿼리 예시](./docs/ko/user-guide/Cloud%20Billing%20데이터%20내보내기의%20쿼리%20예시.md)** - 실용적인 쿼리 모음
- **[📊 데이터 분석 가이드](./docs/ko/user-guide/data-analysis-guide.md)** - BigQuery 스키마 및 쿼리 분석
- **[💰 Pricing Data Export 가이드](./docs/ko/user-guide/pricing-data-export-guide.md)** - 가격 데이터 분석

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## Support

For detailed documentation and support, please refer to the Korean documentation in [`docs/ko/`](./docs/ko/) directory.