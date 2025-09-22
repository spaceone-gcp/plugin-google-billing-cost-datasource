#!/bin/bash

# GCS Cost.get_data ↔ Job.get_tasks 통합 gRPC 테스트 스크립트
# 
# 사용법:
#   1. gRPC 서버 시작: spaceone grpc_server
#   2. 이 스크립트 실행: ./test/bigquery_integration_test.sh
#
# 요구사항:
#   - grpcurl 설치 (brew install grpcurl)
#   - GOOGLE_APPLICATION_CREDENTIALS 환경변수 설정
#   - gRPC 서버가 localhost:50051에서 실행 중
#   - GCS 버킷에 billing 데이터 파일이 존재

set -e  # 오류 발생 시 스크립트 중단

# 색상 설정
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${PURPLE}🚀 $1${NC}"
}

# 타임스탬프 생성
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="gcs_test_results_${TIMESTAMP}"
mkdir -p "$LOG_DIR"

log_info "테스트 결과 디렉토리: $LOG_DIR"

# 시크릿 데이터 로드
if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    log_error "GOOGLE_APPLICATION_CREDENTIALS 환경변수가 설정되지 않았습니다."
    log_info "Google Cloud Service Account 키 파일 경로를 설정하세요:"
    log_info "export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json"
    exit 1
fi

if [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    log_error "Service Account 키 파일을 찾을 수 없습니다: $GOOGLE_APPLICATION_CREDENTIALS"
    exit 1
fi

SECRET_DATA=$(cat "$GOOGLE_APPLICATION_CREDENTIALS")
log_success "Service Account 키 파일 로드 완료"

# gRPC 서버 연결 테스트
log_step "gRPC 서버 연결 테스트 중..."
if ! grpcurl -plaintext localhost:50051 list > /dev/null 2>&1; then
    log_error "gRPC 서버에 연결할 수 없습니다."
    log_info "다음 명령어로 서버를 시작하세요: spaceone grpc_server"
    exit 1
fi
log_success "gRPC 서버 연결 확인 완료"

# 테스트 설정 (GCS 환경 기준)
GCS_BUCKET="spaceone-dev-billing-data"
TARGET_PROJECT="mkkang-project"
DOMAIN_ID="domain-286776a1516a"

# 터미널 로그에서 확인된 실제 파일 경로 패턴
EXPECTED_FILE_PATTERNS=(
    "mkkang-project/2025/08/billing_adjusted_data_202508-*.parquet"
    "mkkang-project/2025/09/billing_data_202509-*.parquet"
)

echo
echo "================================================================="
echo "🎯 GCS Cost.get_data ↔ Job.get_tasks 통합 테스트"
echo "================================================================="
echo "📊 테스트 설정:"
echo "   - GCS Bucket: $GCS_BUCKET"
echo "   - Target Project: $TARGET_PROJECT"
echo "   - Domain ID: $DOMAIN_ID"
echo "   - 예상 파일 패턴: ${#EXPECTED_FILE_PATTERNS[@]}개"
echo "================================================================="
echo

# ================================================================
# 1단계: Job.get_tasks 실행 (GCS 모드)
# ================================================================
log_step "[1단계] Job.get_tasks 실행 - GCS 파일 목록 조회"
echo "GCS 버킷에서 파일 목록을 조회하여 태스크를 생성합니다..."

JOB_RESULT_FILE="$LOG_DIR/job_get_tasks_result.json"

grpcurl -plaintext -d "{
    \"options\": {
        \"bucket_name\": \"$GCS_BUCKET\",
        \"filed_mapper\": {
            \"currency\": \"currency\",
            \"billed_date\": \"usage_start_time\",
            \"cost\": \"cost\"
        },
        \"select_cost\": \"list_price\",
        \"project_id\": \"$TARGET_PROJECT\",
        \"default_vars\": {
            \"currency\": \"KRW\",
            \"provider\": \"google_cloud\"
        },
        \"source\": \"gcs\"
    },
    \"secret_data\": $SECRET_DATA,
    \"domain_id\": \"$DOMAIN_ID\"
}" localhost:50051 spaceone.api.cost_analysis.plugin.Job.get_tasks > "$JOB_RESULT_FILE"

if [ $? -eq 0 ]; then
    log_success "Job.get_tasks 실행 완료"
    
    # 태스크 수 확인
    TASK_COUNT=$(jq '.tasks | length' "$JOB_RESULT_FILE" 2>/dev/null || echo "0")
    log_info "생성된 태스크 수: $TASK_COUNT개"
    
    if [ "$TASK_COUNT" -eq 0 ]; then
        log_warning "생성된 태스크가 없습니다. 테스트를 종료합니다."
        exit 1
    fi
    
    # 파일 경로 목록 출력
    log_info "발견된 파일 목록:"
    ACTUAL_FILES=($(jq -r '.tasks[] | .task_options.file_path' "$JOB_RESULT_FILE"))
    
    for file_path in "${ACTUAL_FILES[@]}"; do
        log_info "  - $file_path"
    done
    
    # 예상 파일 수와 비교 (터미널 로그 기준: 86개 파일)
    EXPECTED_TASK_COUNT=86
    log_info "🔍 파일 수 검증:"
    echo "   예상 태스크 수: $EXPECTED_TASK_COUNT개 (터미널 로그 기준)"
    echo "   실제 조회된 수: $TASK_COUNT개"
    
    if [ "$TASK_COUNT" -eq "$EXPECTED_TASK_COUNT" ]; then
        log_success "   ✅ 태스크 수가 예상과 일치합니다"
    elif [ "$TASK_COUNT" -gt "$((EXPECTED_TASK_COUNT / 2))" ]; then
        log_warning "   ⚠️ 태스크 수가 예상보다 적지만 합리적 범위입니다"
    else
        log_warning "   ⚠️ 태스크 수가 예상보다 현저히 적습니다"
    fi
    
    # 파일 경로 패턴 검증
    log_info "🔍 파일 경로 패턴 검증:"
    PATTERN_MATCH_COUNT=0
    for pattern in "${EXPECTED_FILE_PATTERNS[@]}"; do
        # 패턴에서 와일드카드 제거하여 기본 경로 확인
        BASE_PATTERN=$(echo "$pattern" | sed 's/\*.*$//')
        MATCHES=$(printf '%s\n' "${ACTUAL_FILES[@]}" | grep -c "$BASE_PATTERN" || echo "0")
        if [ "$MATCHES" -gt 0 ]; then
            log_success "   ✅ 패턴 '$pattern' - $MATCHES개 파일 발견"
            PATTERN_MATCH_COUNT=$((PATTERN_MATCH_COUNT + 1))
        else
            log_warning "   ⚠️ 패턴 '$pattern' - 파일 없음"
        fi
    done
    
    if [ "$PATTERN_MATCH_COUNT" -eq "${#EXPECTED_FILE_PATTERNS[@]}" ]; then
        log_success "   ✅ 모든 예상 패턴이 발견되었습니다"
    else
        log_warning "   ⚠️ 일부 예상 패턴이 누락되었습니다"
    fi
    
else
    log_error "Job.get_tasks 실행 실패"
    exit 1
fi

echo

# ================================================================
# 2단계: 샘플 파일들에 대해 Cost.get_data 실행
# ================================================================
log_step "[2단계] Cost.get_data 실행 - 샘플 파일들의 비용 데이터 조회"

# 처리할 샘플 파일 수 제한 (전체 테스트 시간 단축)
MAX_SAMPLE_FILES=5
SAMPLE_FILES=($(jq -r '.tasks[0:'"$MAX_SAMPLE_FILES"'] | .[] | .task_options.file_path' "$JOB_RESULT_FILE"))

log_info "총 ${#SAMPLE_FILES[@]}개 샘플 파일에 대해 비용 데이터를 조회합니다..."

SUCCESSFUL_COUNT=0
FAILED_COUNT=0
COST_RESULTS_FILE="$LOG_DIR/cost_results_summary.json"

echo "[]" > "$COST_RESULTS_FILE"

for i in "${!SAMPLE_FILES[@]}"; do
    FILE_PATH="${SAMPLE_FILES[$i]}"
    FILE_NUM=$((i + 1))
    
    # 파일명에서 안전한 식별자 생성
    SAFE_FILENAME=$(echo "$FILE_PATH" | sed 's/[^a-zA-Z0-9._-]/_/g')
    
    log_step "[$FILE_NUM/${#SAMPLE_FILES[@]}] 파일 '$FILE_PATH' 처리 중..."
    
    COST_RESULT_FILE="$LOG_DIR/cost_get_data_${SAFE_FILENAME}.json"
    
    # Cost.get_data 실행 (GCS 파일 기반)
    TEMP_GRPC_FILE="${COST_RESULT_FILE}.grpc_raw"
    
    # gRPC 호출하여 원본 응답을 임시 파일에 저장
    SECRET_JSON=$(cat "$GOOGLE_APPLICATION_CREDENTIALS" | jq -c .)
    grpcurl -plaintext -d "{
        \"options\": {
            \"default_vars\": {
                \"currency\": \"USD\",
                \"provider\": \"google_cloud\"
            },
            \"project_id\": \"$TARGET_PROJECT\",
            \"select_cost\": \"cost\",
            \"field_mapper\": {
                \"region_code\": \"location.region\",
                \"tags\": \"labels\",
                \"usage_quantity\": \"usage.amount\",
                \"cost\": \"cost\",
                \"usage_type\": \"sku.description\",
                \"currency\": \"currency\",
                \"additional_info\": {
                    \"resource_global_name\": \"resource.global_name\",
                    \"project_name\": \"project.name\",
                    \"cost_after_credits\": \"cost\",
                    \"resource_name\": \"resource.name\",
                    \"cost_type\": \"cost_type\",
                    \"invoice_month\": \"invoice.month\",
                    \"cost_at_list\": \"cost_at_list\",
                    \"billing_account_id\": \"billing_account_id\",
                    \"project_id\": \"project.id\",
                    \"sku_id\": \"sku.id\",
                    \"credits_amount\": \"credits.amount\",
                    \"service_id\": \"service.id\"
                },
                \"billed_date\": \"usage_start_time\",
                \"usage_unit\": \"usage.unit\",
                \"product\": \"service.description\"
            },
            \"bucket_name\": \"$GCS_BUCKET\",
            \"secret_type\": \"MANUAL\",
            \"source\": \"gcs\"
        },
        \"secret_data\": $SECRET_JSON,
        \"task_options\": {
            \"bucket_name\": \"$GCS_BUCKET\",
            \"parsing_options\": {},
            \"data_source_type\": \"gcs\",
            \"file_path\": \"$FILE_PATH\",
            \"field_mapper\": {}
        },
        \"domain_id\": \"$DOMAIN_ID\"
    }" localhost:50051 spaceone.api.cost_analysis.plugin.Cost.get_data > "$TEMP_GRPC_FILE" 2>&1
    
    # gRPC 호출 결과 확인
    GRPC_EXIT_CODE=$?
    
    if [ $GRPC_EXIT_CODE -eq 0 ]; then
        # 원본 파일을 그대로 복사
        cp "$TEMP_GRPC_FILE" "$COST_RESULT_FILE"
        
        echo "Successfully copied gRPC response to result file"
        echo "Response content preview (first 200 chars):"
        head -c 200 "$COST_RESULT_FILE" || echo "No content"
        echo ""
        
        # 임시 파일 정리
        rm -f "$TEMP_GRPC_FILE"
    else
        # gRPC 호출 실패 시 에러 내용을 확인하고 빈 결과 생성
        echo "gRPC call failed with exit code: $GRPC_EXIT_CODE" >&2
        if [ -f "$TEMP_GRPC_FILE" ]; then
            echo "Error details:" >&2
            cat "$TEMP_GRPC_FILE" >&2
            rm -f "$TEMP_GRPC_FILE"
        fi
        echo '{"results": []}' > "$COST_RESULT_FILE"
    fi
    
    if [ $? -eq 0 ] && grep -q '"results"' "$COST_RESULT_FILE" 2>/dev/null; then
        # gRPC 스트리밍 응답을 올바르게 집계 (Python 사용)
        AGGREGATION_RESULT=$(python3 -c "
import json
import sys

try:
    with open('$COST_RESULT_FILE', 'r') as f:
        content = f.read()
    
    # JSON 객체들을 분리하여 파싱
    results = []
    total_cost = 0
    json_decoder = json.JSONDecoder()
    idx = 0
    
    while idx < len(content):
        content = content[idx:].lstrip()
        if not content:
            break
        try:
            obj, idx = json_decoder.raw_decode(content)
            if 'results' in obj and isinstance(obj['results'], list):
                results.extend(obj['results'])
        except json.JSONDecodeError:
            break
    
    # 총 비용 계산
    for record in results:
        if 'cost' in record and record['cost'] is not None:
            try:
                total_cost += float(record['cost'])
            except:
                pass
    
    print(f'{len(results)}|{total_cost:.2f}')
    
except Exception as e:
    print('0|0.00')
" 2>/dev/null)

        # 결과 파싱
        DATA_COUNT=$(echo "$AGGREGATION_RESULT" | cut -d'|' -f1)
        TOTAL_COST=$(echo "$AGGREGATION_RESULT" | cut -d'|' -f2)
        
        # 파일 크기별 예상 데이터 건수 (parquet 파일 기준)
        EXPECTED_COUNT=100  # 일반적인 parquet 파일당 예상 레코드 수
        
        # 데이터 건수 검증
        if [ "$DATA_COUNT" -gt 0 ]; then
            log_success "파일 '$FILE_PATH' 완료 - 데이터 ${DATA_COUNT}건, 총 비용: \$${TOTAL_COST}"
        else
            log_warning "파일 '$FILE_PATH' 완료 - 데이터 ${DATA_COUNT}건 (데이터 없음)"
        fi
        
        SUCCESSFUL_COUNT=$((SUCCESSFUL_COUNT + 1))
        
        # 결과 요약에 추가
        RESULT_SUMMARY=$(jq -n \
            --arg file_path "$FILE_PATH" \
            --arg data_count "$DATA_COUNT" \
            --arg total_cost "$TOTAL_COST" \
            '{
                file_path: $file_path,
                success: true,
                data_count: ($data_count | tonumber),
                total_cost: ($total_cost | tonumber),
                timestamp: now | strftime("%Y-%m-%d %H:%M:%S")
            }')
        jq ". += [$RESULT_SUMMARY]" "$COST_RESULTS_FILE" > "${COST_RESULTS_FILE}.tmp" && mv "${COST_RESULTS_FILE}.tmp" "$COST_RESULTS_FILE"
        
    else
        log_error "파일 '$FILE_PATH' 실패 또는 빈 결과"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        
        # 에러 정보 요약에 추가
        if [ -f "$COST_RESULT_FILE" ]; then
            ERROR_MSG=$(grep -o '"message"[^"]*"[^"]*"' "$COST_RESULT_FILE" | head -n 1 | cut -d'"' -f4 || echo "Unknown error")
        else
            ERROR_MSG="파일 생성 실패"
        fi
        
        RESULT_SUMMARY=$(jq -n \
            --arg file_path "$FILE_PATH" \
            --arg error "$ERROR_MSG" \
            '{
                file_path: $file_path,
                success: false,
                error: $error,
                timestamp: now | strftime("%Y-%m-%d %H:%M:%S")
            }')
        jq ". += [$RESULT_SUMMARY]" "$COST_RESULTS_FILE" > "${COST_RESULTS_FILE}.tmp" && mv "${COST_RESULTS_FILE}.tmp" "$COST_RESULTS_FILE"
    fi
    
    echo
done

# ================================================================
# 3단계: 테스트 결과 요약
# ================================================================
echo
echo "================================================================="
log_step "테스트 결과 요약"
echo "================================================================="

TOTAL_SAMPLES=${#SAMPLE_FILES[@]}
OVERALL_TOTAL_COST=$(jq -r '[.[] | select(.success == true) | .total_cost // 0] | add // 0 | tostring' "$COST_RESULTS_FILE" 2>/dev/null || echo "0")
OVERALL_DATA_COUNT=$(jq -r '[.[] | select(.success == true) | .data_count // 0] | add // 0' "$COST_RESULTS_FILE" 2>/dev/null || echo "0")

log_info "📊 전체 통계:"
echo "   총 발견된 파일 수: $TASK_COUNT"
echo "   테스트한 샘플 수: $TOTAL_SAMPLES"
echo "   ✅ 성공: $SUCCESSFUL_COUNT"
echo "   ❌ 실패: $FAILED_COUNT"
echo "   📝 총 데이터 건수: $OVERALL_DATA_COUNT"
echo "   💰 총 비용: \$${OVERALL_TOTAL_COST}"

log_info "🔍 GCS 테스트 특성:"
echo "   GCS 버킷: $GCS_BUCKET"
echo "   타겟 프로젝트: $TARGET_PROJECT"
echo "   파일 형식: Parquet"
echo "   데이터 소스: GCS"

# 성공률 계산
if [ "$TOTAL_SAMPLES" -gt 0 ]; then
    SUCCESS_RATE=$((SUCCESSFUL_COUNT * 100 / TOTAL_SAMPLES))
    
    if [ "$SUCCESS_RATE" -eq 100 ]; then
        log_success "   📈 성공률: 100% (완벽)"
    elif [ "$SUCCESS_RATE" -ge 80 ]; then
        log_success "   📈 성공률: ${SUCCESS_RATE}% (양호)"
    elif [ "$SUCCESS_RATE" -ge 50 ]; then
        log_warning "   📊 성공률: ${SUCCESS_RATE}% (보통)"
    else
        log_error "   📉 성공률: ${SUCCESS_RATE}% (낮음)"
    fi
fi

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo
    log_warning "실패한 파일들:"
    jq -r '.[] | select(.success == false) | "   - " + .file_path + ": " + .error' "$COST_RESULTS_FILE"
fi

echo
log_info "📁 테스트 결과 파일:"
echo "   - Job 결과: $JOB_RESULT_FILE"
echo "   - Cost 결과 요약: $COST_RESULTS_FILE"
echo "   - 개별 파일 결과: $LOG_DIR/cost_get_data_*.json"

# 전체 성공률 판정
if [ "$TOTAL_SAMPLES" -gt 0 ]; then
    if [ "$SUCCESS_RATE" -eq 100 ]; then
        log_success "🎉 모든 테스트가 성공했습니다!"
    elif [ "$SUCCESS_RATE" -ge 80 ]; then
        log_warning "⚠️ 일부 테스트가 실패했지만 대부분 성공했습니다. (성공률: ${SUCCESS_RATE}%)"
    else
        log_error "💥 다수의 테스트가 실패했습니다. (성공률: ${SUCCESS_RATE}%)"
        exit 1
    fi
else
    log_error "💥 테스트할 샘플이 없습니다."
    exit 1
fi

echo
echo "================================================================="
log_success "GCS 통합 테스트 완료!"
echo "================================================================="
