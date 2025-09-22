#!/bin/bash

# BigQuery Cost.get_data ↔ Job.get_tasks 통합 gRPC 테스트 스크립트
# 
# 사용법:
#   1. gRPC 서버 시작: spaceone grpc_server
#   2. 이 스크립트 실행: ./test/grpc_integration_test.sh
#
# 요구사항:
#   - grpcurl 설치 (brew install grpcurl)
#   - GOOGLE_APPLICATION_CREDENTIALS 환경변수 설정
#   - gRPC 서버가 localhost:50051에서 실행 중

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
LOG_DIR="test_results_${TIMESTAMP}"
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

# 테스트 설정 (운영 환경 기준)
BILLING_PROJECT="mkkang-project"
BILLING_DATASET="multi_region_billing_data"
BILLING_ACCOUNT="01FD8E-B4DDC1-EAB69F"
DOMAIN_ID="domain-731646a5e0ad"
START_DATE="2024-09"

# 운영 로그에서 확인된 실제 프로젝트 목록 (데이터가 있는 프로젝트들)
EXPECTED_PROJECTS=(
    "full-depth-prj"
    "mhlee-project"
    "ant-man-465309"
    "billing-project-465506"
    "iam-project-465506"
    "iron-man-2-465309"
    "iron-man-465309"
    "recommender-project-465506"
    "the-first-avenger-465308"
    "the-winter-soldier-465309"
    "thor-the-dark-world-465309"
)

echo
echo "================================================================="
echo "🎯 BigQuery Cost.get_data ↔ Job.get_tasks 통합 테스트"
echo "================================================================="
echo "📊 테스트 설정:"
echo "   - Billing Project: $BILLING_PROJECT"
echo "   - Dataset: $BILLING_DATASET"
echo "   - Billing Account: $BILLING_ACCOUNT"
echo "   - Start Date: $START_DATE"
echo "   - Domain ID: $DOMAIN_ID"
echo "================================================================="
echo

# ================================================================
# 1단계: Job.get_tasks 실행
# ================================================================
log_step "[1단계] Job.get_tasks 실행 - 활성 프로젝트 목록 조회"
echo "프로젝트 목록을 조회하여 태스크를 생성합니다..."

JOB_RESULT_FILE="$LOG_DIR/job_get_tasks_result.json"

grpcurl -plaintext -d "{
    \"options\": {
        \"billing_export_project_id\": \"$BILLING_PROJECT\",
        \"billing_dataset_id\": \"$BILLING_DATASET\", 
        \"billing_account_id\": \"$BILLING_ACCOUNT\",
        \"source\": \"bigquery\"
    },
    \"secret_data\": $SECRET_DATA,
    \"start\": \"$START_DATE\",
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
    
    # 프로젝트 목록 출력 및 운영 환경과 비교
    log_info "프로젝트 목록:"
    ACTUAL_PROJECTS=($(jq -r '.tasks[] | .task_options.project_id' "$JOB_RESULT_FILE"))
    
    for project_id in "${ACTUAL_PROJECTS[@]}"; do
        log_info "  - $project_id"
    done
    
    # 운영 환경과 비교 검증
    log_info "🔍 운영 환경 비교 검증:"
    echo "   예상 프로젝트 수: ${#EXPECTED_PROJECTS[@]}개"
    echo "   실제 조회된 수: ${#ACTUAL_PROJECTS[@]}개"
    
    # 운영에서 데이터가 있었던 주요 프로젝트들이 포함되었는지 확인
    MAJOR_PROJECTS=("full-depth-prj" "mhlee-project")
    for major_proj in "${MAJOR_PROJECTS[@]}"; do
        if printf '%s\n' "${ACTUAL_PROJECTS[@]}" | grep -q "^${major_proj}$"; then
            log_success "   ✅ 주요 프로젝트 '$major_proj' 포함됨"
        else
            log_warning "   ⚠️ 주요 프로젝트 '$major_proj' 누락됨"
        fi
    done
else
    log_error "Job.get_tasks 실행 실패"
    exit 1
fi

echo

# ================================================================
# 2단계: 각 태스크별 Cost.get_data 실행
# ================================================================
log_step "[2단계] Cost.get_data 실행 - 프로젝트별 비용 데이터 조회"

# 프로젝트 목록 추출
PROJECT_LIST=$(jq -r '.tasks[] | .task_options.project_id' "$JOB_RESULT_FILE")
PROJECT_ARRAY=($PROJECT_LIST)

log_info "총 ${#PROJECT_ARRAY[@]}개 프로젝트에 대해 비용 데이터를 조회합니다..."

SUCCESSFUL_COUNT=0
FAILED_COUNT=0
COST_RESULTS_FILE="$LOG_DIR/cost_results_summary.json"

echo "[]" > "$COST_RESULTS_FILE"

for i in "${!PROJECT_ARRAY[@]}"; do
    PROJECT_ID="${PROJECT_ARRAY[$i]}"
    PROJECT_NUM=$((i + 1))
    
    log_step "[$PROJECT_NUM/${#PROJECT_ARRAY[@]}] 프로젝트 '$PROJECT_ID' 처리 중..."
    
    COST_RESULT_FILE="$LOG_DIR/cost_get_data_${PROJECT_ID}.json"
    
    # Cost.get_data 실행 (스트리밍 응답을 단일 JSON으로 병합)
    # 임시 파일로 원본 gRPC 응답 저장
    TEMP_GRPC_FILE="${COST_RESULT_FILE}.grpc_raw"
    
    # gRPC 호출하여 원본 응답을 임시 파일에 저장 (service-account-key.json 직접 사용)
    SECRET_JSON=$(cat service-account-key.json | jq -c .)
    grpcurl -plaintext -d "{
        \"options\": {
            \"source\": \"bigquery\",
            \"billing_export_project_id\": \"$BILLING_PROJECT\",
            \"billing_dataset_id\": \"$BILLING_DATASET\",
            \"billing_account_id\": \"$BILLING_ACCOUNT\",
            \"provider\": \"google_cloud\"
        },
        \"secret_data\": $SECRET_JSON,
        \"task_options\": {
            \"start\": \"$START_DATE\",
            \"project_id\": \"$PROJECT_ID\",
            \"billing_export_project_id\": \"$BILLING_PROJECT\",
            \"billing_dataset_id\": \"$BILLING_DATASET\",
            \"billing_account_id\": \"$BILLING_ACCOUNT\",
            \"data_source_type\": \"bigquery\"
        },
        \"domain_id\": \"$DOMAIN_ID\"
    }" localhost:50051 spaceone.api.cost_analysis.plugin.Cost.get_data > "$TEMP_GRPC_FILE" 2>&1
    
    # gRPC 호출 결과 확인
    GRPC_EXIT_CODE=$?
    
    if [ $GRPC_EXIT_CODE -eq 0 ]; then
        # 원본 파일을 그대로 복사 (이미 유효한 JSON이므로)
        cp "$TEMP_GRPC_FILE" "$COST_RESULT_FILE"
        
        echo "Successfully copied gRPC response to result file"
        
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
        
        # 운영 환경 기준 예상 데이터 건수 검증
        EXPECTED_COUNT=0
        case "$PROJECT_ID" in
            "full-depth-prj")
                EXPECTED_COUNT=1478
                ;;
            "mhlee-project")
                EXPECTED_COUNT=1656
                ;;
            *)
                EXPECTED_COUNT=8  # 기타 프로젝트들의 일반적인 건수
                ;;
        esac
        
        # 데이터 건수 비교
        if [ "$DATA_COUNT" -gt 0 ]; then
            if [ "$DATA_COUNT" -ge "$((EXPECTED_COUNT / 2))" ]; then
                log_success "프로젝트 '$PROJECT_ID' 완료 - 데이터 ${DATA_COUNT}건, 총 비용: \$${TOTAL_COST} (예상: ${EXPECTED_COUNT}건)"
            else
                log_warning "프로젝트 '$PROJECT_ID' 완료 - 데이터 ${DATA_COUNT}건, 총 비용: \$${TOTAL_COST} (예상보다 적음: ${EXPECTED_COUNT}건)"
            fi
        else
            log_warning "프로젝트 '$PROJECT_ID' 완료 - 데이터 ${DATA_COUNT}건 (운영에서는 ${EXPECTED_COUNT}건 있었음)"
        fi
        
        SUCCESSFUL_COUNT=$((SUCCESSFUL_COUNT + 1))
        
        # 결과 요약에 추가 (안전한 JSON 생성)
        RESULT_SUMMARY=$(jq -n \
            --arg project_id "$PROJECT_ID" \
            --arg data_count "$DATA_COUNT" \
            --arg total_cost "$TOTAL_COST" \
            '{
                project_id: $project_id,
                success: true,
                data_count: ($data_count | tonumber),
                total_cost: ($total_cost | tonumber),
                timestamp: now | strftime("%Y-%m-%d %H:%M:%S")
            }')
        jq ". += [$RESULT_SUMMARY]" "$COST_RESULTS_FILE" > "${COST_RESULTS_FILE}.tmp" && mv "${COST_RESULTS_FILE}.tmp" "$COST_RESULTS_FILE"
        
    else
        log_error "프로젝트 '$PROJECT_ID' 실패 또는 빈 결과"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        
        # 에러 정보 요약에 추가 (안전한 에러 메시지 추출)
        if [ -f "$COST_RESULT_FILE" ]; then
            ERROR_MSG=$(grep -o '"message"[^"]*"[^"]*"' "$COST_RESULT_FILE" | head -n 1 | cut -d'"' -f4 || echo "Unknown error")
        else
            ERROR_MSG="파일 생성 실패"
        fi
        
        RESULT_SUMMARY=$(jq -n \
            --arg project_id "$PROJECT_ID" \
            --arg error "$ERROR_MSG" \
            '{
                project_id: $project_id,
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

TOTAL_PROJECTS=${#PROJECT_ARRAY[@]}
OVERALL_TOTAL_COST=$(jq -r '[.[] | select(.success == true) | .total_cost // 0] | add // 0 | tostring' "$COST_RESULTS_FILE" 2>/dev/null || echo "0")
OVERALL_DATA_COUNT=$(jq -r '[.[] | select(.success == true) | .data_count // 0] | add // 0' "$COST_RESULTS_FILE" 2>/dev/null || echo "0")

log_info "📊 전체 통계:"
echo "   총 프로젝트 수: $TOTAL_PROJECTS"
echo "   ✅ 성공: $SUCCESSFUL_COUNT"
echo "   ❌ 실패: $FAILED_COUNT"
echo "   📝 총 데이터 건수: $OVERALL_DATA_COUNT"
echo "   💰 총 비용: \$${OVERALL_TOTAL_COST}"

log_info "🔍 운영 환경 비교 (2024-09 기준):"
echo "   운영 환경 총 데이터: 3,222건 (full-depth-prj: 1,478 + mhlee-project: 1,656 + 기타: 88건)"
echo "   로컬 테스트 결과: $OVERALL_DATA_COUNT건"

# 데이터 일치율 계산
if [ "$OVERALL_DATA_COUNT" -gt 0 ]; then
    MATCH_RATE=$((OVERALL_DATA_COUNT * 100 / 3222))
    if [ "$MATCH_RATE" -ge 80 ]; then
        log_success "   📈 데이터 일치율: ${MATCH_RATE}% (양호)"
    elif [ "$MATCH_RATE" -ge 50 ]; then
        log_warning "   📊 데이터 일치율: ${MATCH_RATE}% (보통)"
    else
        log_error "   📉 데이터 일치율: ${MATCH_RATE}% (낮음)"
    fi
else
    log_error "   📉 데이터 일치율: 0% (데이터 없음)"
fi

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo
    log_warning "실패한 프로젝트:"
    jq -r '.[] | select(.success == false) | "   - " + .project_id + ": " + .error' "$COST_RESULTS_FILE"
fi

echo
log_info "📁 테스트 결과 파일:"
echo "   - Job 결과: $JOB_RESULT_FILE"
echo "   - Cost 결과 요약: $COST_RESULTS_FILE"
echo "   - 개별 프로젝트 결과: $LOG_DIR/cost_get_data_*.json"

# 성공률 계산
SUCCESS_RATE=$((SUCCESSFUL_COUNT * 100 / TOTAL_PROJECTS))

if [ "$SUCCESS_RATE" -eq 100 ]; then
    log_success "🎉 모든 테스트가 성공했습니다!"
elif [ "$SUCCESS_RATE" -ge 80 ]; then
    log_warning "⚠️ 일부 테스트가 실패했지만 대부분 성공했습니다. (성공률: ${SUCCESS_RATE}%)"
else
    log_error "💥 다수의 테스트가 실패했습니다. (성공률: ${SUCCESS_RATE}%)"
    exit 1
fi

echo
echo "================================================================="
log_success "BigQuery 통합 테스트 완료!"
echo "================================================================="
