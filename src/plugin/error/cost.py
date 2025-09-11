# SpaceONE Mock for local development (프로젝트 규칙 13.1 준수)
try:
    from spaceone.core.error import ERROR_INVALID_ARGUMENT, ERROR_UNKNOWN
except ImportError:
    # Mock for local development
    class MockError:
        _message = "Mock SpaceONE Error: {message}"
        
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        
        def __call__(self, *args, **kwargs):
            return Exception(self._message.format(**kwargs))

    ERROR_INVALID_ARGUMENT = MockError
    ERROR_UNKNOWN = MockError


class ERROR_INVALID_SECRET_TYPE(ERROR_INVALID_ARGUMENT):
    _message = "Invalid secret type: {secret_type}"


class ERROR_TOO_MANY_CSV_FILES(ERROR_UNKNOWN):
    _message = "Too many csv files: {target_dir}"


class ERROR_EXCHANGE_RATE_DATA_NOT_FOUND(ERROR_UNKNOWN):
    _message = "Exchange rate data not found"


class ERROR_NOT_FOUND_EXCHANGE_RATE(ERROR_UNKNOWN):
    _message = "Invalid exchange rate: {year}-{month}"


class ERROR_NOT_FOUND_TABLE(ERROR_UNKNOWN):
    _message = "Not found table: {table} / dataset: {dataset}"


class ERROR_NOT_EXIST_TARGET_PROJECT_ID(ERROR_INVALID_ARGUMENT):
    _message = "Not exist target_project_id: {target_project_id}"


# HTTP File Processing Errors
class ERROR_UNSUPPORTED_FILE_FORMAT(ERROR_INVALID_ARGUMENT):
    _message = "Unsupported file format: {format}"


class ERROR_FILE_DOWNLOAD_FAILED(ERROR_UNKNOWN):
    _message = "File download failed: {file_path}"


class ERROR_FILE_PARSING_FAILED(ERROR_UNKNOWN):
    _message = "File parsing failed: {file_path}, reason: {reason}"


class ERROR_FIELD_MAPPING_FAILED(ERROR_INVALID_ARGUMENT):
    _message = "Field mapping failed: {field}, reason: {reason}"


class ERROR_INVALID_GCS_CONFIG(ERROR_INVALID_ARGUMENT):
    _message = "Invalid GCS configuration: {config}"
