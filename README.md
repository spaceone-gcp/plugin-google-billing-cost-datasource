# Google Cloud Billing Cost Datasource Plugin

SpaceONE plugin for collecting Google Cloud Billing data with support for both BigQuery and HTTP file data sources.

## Features

### Data Sources
- ✅ **BigQuery**: Real-time querying and analysis (production ready)
- ✅ **HTTP File**: Direct processing of GCS billing export files (production ready)

### File Format Support
- CSV, JSON, Parquet formats
- Compressed files (.gz, .snappy, .zstd)

### Key Capabilities
- Dual data source support
- Flexible Field Mapper for data transformation
- Credits and discount analysis
- Label/tag-based cost tracking

## Documentation

📖 **Complete documentation is available in Korean**: [`docs/ko/README.md`](./docs/ko/README.md)

### Quick Links
- **[Billing Export Setup Guide](./docs/ko/user-guide/billing-export-setup.md)** - How to set up Google Cloud Billing Export
- **[Integration Guide](./docs/ko/user-guide/integration-guide.md)** - Plugin configuration and usage
- **[Data Analysis Guide](./docs/ko/user-guide/data-analysis-guide.md)** - Understanding billing data structure
- **[Credits & Discounts Analysis](./docs/ko/user-guide/credits-and-discounts-analysis.md)** - Advanced cost optimization analysis

## Quick Start

### 1. Set up Google Cloud Billing Export
Follow the [Billing Export Setup Guide](./docs/ko/user-guide/billing-export-setup.md) to configure:
- BigQuery export for detailed billing data
- Cloud Storage export for file-based processing

### 2. Configure Service Account
Create a service account with appropriate permissions:
- **BigQuery mode**: `BigQuery Data Viewer`, `BigQuery Job User`
- **HTTP file mode**: `Storage Object Viewer`

### 3. SpaceONE Plugin Configuration

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

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## Support

For detailed documentation and support, please refer to the Korean documentation in [`docs/ko/`](./docs/ko/) directory.