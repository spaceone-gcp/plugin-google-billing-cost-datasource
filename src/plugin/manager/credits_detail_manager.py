"""
Credits Detail 전용 매니저 클래스

현재 최적화된 Cost Manager는 GROUP BY 집계를 통해 성능을 보장하지만,
Credits Detail 정보는 집계 과정에서 손실됩니다.

이 매니저는 Credits Detail이 필요한 특별한 경우에만 사용하여
원본 데이터에서 크레딧 세부 정보를 정확하게 추출합니다.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator

from spaceone.core.manager import BaseManager

_LOGGER = logging.getLogger(__name__)


class CreditsDetailManager(BaseManager):
    """Credits Detail 전용 조회 매니저"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bigquery_connector = None
        self.billing_export_project_id = None
        self.billing_dataset = None
        self.billing_table = None

    def initialize(self, bigquery_connector, billing_export_project_id: str, 
                   billing_dataset: str, billing_table: str):
        """매니저 초기화"""
        self.bigquery_connector = bigquery_connector
        self.billing_export_project_id = billing_export_project_id
        self.billing_dataset = billing_dataset
        self.billing_table = billing_table
        _LOGGER.info(f"[CreditsDetailManager] 초기화 완료 - 테이블: {billing_export_project_id}.{billing_dataset}.{billing_table}")

    def get_credits_detail(self, 
                          start_date: str, 
                          end_date: str = None,
                          project_id: str = None,
                          billing_account_id: str = None,
                          service_id: str = None,
                          limit: int = 1000) -> Generator[Dict[str, Any], None, None]:
        """
        Credits Detail 정보를 원본 데이터에서 조회
        
        Args:
            start_date: 시작 날짜 (YYYY-MM 형식)
            end_date: 종료 날짜 (선택사항, 기본값은 start_date와 동일)
            project_id: 프로젝트 ID 필터 (선택사항)
            billing_account_id: 빌링 계정 ID 필터 (선택사항)
            service_id: 서비스 ID 필터 (선택사항)
            limit: 최대 결과 수 (기본값: 1000)
            
        Yields:
            Credits Detail 정보가 포함된 레코드들
        """
        _LOGGER.info(f"[CreditsDetailManager] Credits Detail 조회 시작 - {start_date} ~ {end_date or start_date}")
        
        try:
            # SQL 쿼리 생성
            query = self._create_credits_detail_sql(
                start_date, end_date, project_id, billing_account_id, service_id, limit
            )
            
            _LOGGER.debug(f"[CreditsDetailManager] 생성된 쿼리: {query}")
            
            # BigQuery 실행
            response_stream = self.bigquery_connector.read_df_from_bigquery(query)
            _LOGGER.info(f"[CreditsDetailManager] 쿼리 실행 완료 - {len(response_stream)} 행 조회")
            
            # 결과 처리 및 반환
            for _, row in response_stream.iterrows():
                record = self._process_credits_row(row)
                if record and record.get('credits_detail'):  # Credits가 있는 레코드만 반환
                    yield record
                    
        except Exception as e:
            _LOGGER.error(f"[CreditsDetailManager] Credits Detail 조회 실패: {str(e)}")
            raise

    def _create_credits_detail_sql(self, 
                                  start_date: str, 
                                  end_date: str = None,
                                  project_id: str = None,
                                  billing_account_id: str = None,
                                  service_id: str = None,
                                  limit: int = 1000) -> str:
        """Credits Detail 조회용 SQL 생성 (GROUP BY 없음)"""
        
        # 날짜 조건 생성
        if not end_date:
            end_date = start_date
            
        date_condition = f"usage_start_time >= '{start_date}-01' AND usage_start_time < '{end_date}-32'"
        
        # 추가 필터 조건들
        where_conditions = [date_condition]
        
        if project_id:
            where_conditions.append(f"project.id = '{project_id}'")
        if billing_account_id:
            where_conditions.append(f"billing_account_id = '{billing_account_id}'")
        if service_id:
            where_conditions.append(f"service.id = '{service_id}'")
            
        # Credits가 있는 레코드만 조회 (성능 최적화)
        where_conditions.append("ARRAY_LENGTH(IFNULL(credits, [])) > 0")
        
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        query = f"""
            SELECT
              -- 기본 식별 정보
              timestamp_trunc(usage_start_time, DAY) as billed_at,
              billing_account_id,
              
              -- 프로젝트 정보
              project.id as project_id,
              project.name as project_name,
              
              -- 서비스 정보
              service.id as service_id,
              service.description as service_description,
              
              -- SKU 정보
              sku.id as sku_id,
              sku.description as sku_description,
              
              -- 위치 정보
              IFNULL(location.location, 'global') as location_name,
              IFNULL(location.country, '') as location_country,
              IFNULL(location.region, 'global') as region_code,
              
              -- 비용 정보
              cost,
              currency,
              IFNULL(currency_conversion_rate, 1.0) as currency_conversion_rate,
              
              -- 🎯 Credits Detail (원본 데이터 그대로)
              TO_JSON_STRING(credits) as credits_detail,
              
              -- Credits 총액 (검증용)
              (SELECT SUM(CAST(c.amount AS FLOAT64)) FROM UNNEST(credits) c) as credits_total_amount,
              
              -- 인보이스 정보
              IFNULL(invoice.month, '') as invoice_month
              
            FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`
            {where_clause}
            ORDER BY usage_start_time DESC, cost DESC
            LIMIT {limit}
        """
        
        return query

    def _process_credits_row(self, row) -> Dict[str, Any]:
        """Credits Detail 행 데이터 처리"""
        try:
            # Credits Detail JSON 파싱
            credits_detail_raw = row.get('credits_detail', '[]')
            credits_detail = []
            
            if credits_detail_raw and credits_detail_raw != '[]':
                import json
                try:
                    credits_detail = json.loads(credits_detail_raw)
                except json.JSONDecodeError:
                    _LOGGER.warning(f"[CreditsDetailManager] Credits Detail JSON 파싱 실패: {credits_detail_raw}")
                    credits_detail = []
            
            # 결과 레코드 구성
            record = {
                'billed_date': row.get('billed_at', '').strftime('%Y-%m-%d') if row.get('billed_at') else '',
                'billing_account_id': row.get('billing_account_id', ''),
                'project_id': row.get('project_id', ''),
                'project_name': row.get('project_name', ''),
                'service_id': row.get('service_id', ''),
                'service_description': row.get('service_description', ''),
                'sku_id': row.get('sku_id', ''),
                'sku_description': row.get('sku_description', ''),
                'location_name': row.get('location_name', ''),
                'location_country': row.get('location_country', ''),
                'region_code': row.get('region_code', ''),
                'cost': float(row.get('cost', 0)),
                'currency': row.get('currency', ''),
                'currency_conversion_rate': float(row.get('currency_conversion_rate', 1.0)),
                'credits_detail': credits_detail,
                'credits_total_amount': float(row.get('credits_total_amount', 0)),
                'invoice_month': row.get('invoice_month', ''),
                'credits_count': len(credits_detail) if credits_detail else 0,
            }
            
            return record
            
        except Exception as e:
            _LOGGER.error(f"[CreditsDetailManager] 행 처리 실패: {str(e)}")
            return None

    def get_credits_summary(self, 
                           start_date: str, 
                           end_date: str = None,
                           project_id: str = None) -> Dict[str, Any]:
        """Credits 요약 정보 조회"""
        _LOGGER.info(f"[CreditsDetailManager] Credits 요약 조회 - {start_date} ~ {end_date or start_date}")
        
        try:
            # 요약 쿼리 생성
            query = self._create_credits_summary_sql(start_date, end_date, project_id)
            
            # BigQuery 실행
            response_stream = self.bigquery_connector.read_df_from_bigquery(query)
            
            if len(response_stream) == 0:
                return {
                    'total_records_with_credits': 0,
                    'total_credits_amount': 0.0,
                    'credits_types': [],
                    'period': f"{start_date} ~ {end_date or start_date}"
                }
            
            row = response_stream.iloc[0]
            
            # Credits 타입별 집계
            credits_types_raw = row.get('credits_types', '[]')
            credits_types = []
            if credits_types_raw and credits_types_raw != '[]':
                import json
                try:
                    credits_types = json.loads(credits_types_raw)
                except json.JSONDecodeError:
                    credits_types = []
            
            summary = {
                'total_records_with_credits': int(row.get('total_records_with_credits', 0)),
                'total_credits_amount': float(row.get('total_credits_amount', 0)),
                'credits_types': credits_types,
                'period': f"{start_date} ~ {end_date or start_date}",
                'project_id': project_id or 'ALL'
            }
            
            _LOGGER.info(f"[CreditsDetailManager] Credits 요약 완료: {summary['total_records_with_credits']}건, 총액 {summary['total_credits_amount']}")
            
            return summary
            
        except Exception as e:
            _LOGGER.error(f"[CreditsDetailManager] Credits 요약 조회 실패: {str(e)}")
            raise

    def _create_credits_summary_sql(self, 
                                   start_date: str, 
                                   end_date: str = None,
                                   project_id: str = None) -> str:
        """Credits 요약 조회용 SQL"""
        
        if not end_date:
            end_date = start_date
            
        date_condition = f"usage_start_time >= '{start_date}-01' AND usage_start_time < '{end_date}-32'"
        
        where_conditions = [date_condition, "ARRAY_LENGTH(IFNULL(credits, [])) > 0"]
        
        if project_id:
            where_conditions.append(f"project.id = '{project_id}'")
            
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        query = f"""
            SELECT
              COUNT(*) as total_records_with_credits,
              SUM((SELECT SUM(CAST(c.amount AS FLOAT64)) FROM UNNEST(credits) c)) as total_credits_amount,
              TO_JSON_STRING(
                ARRAY_AGG(
                  STRUCT(
                    credit_type,
                    credit_count,
                    credit_amount
                  )
                )
              ) as credits_types
            FROM (
              SELECT 
                c.type as credit_type,
                COUNT(*) as credit_count,
                SUM(CAST(c.amount AS FLOAT64)) as credit_amount
              FROM `{self.billing_export_project_id}.{self.billing_dataset}.{self.billing_table}`,
              UNNEST(credits) c
              {where_clause.replace('ARRAY_LENGTH(IFNULL(credits, [])) > 0', 'TRUE')}
              GROUP BY c.type
            )
        """
        
        return query
