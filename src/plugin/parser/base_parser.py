import logging
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import IO

from ..conf.cost_conf import GCS_CONFIG
from ..manager.field_mapper import FieldMapper

_LOGGER = logging.getLogger("spaceone")


class BaseParser(ABC):
    """파일 파서 기본 클래스"""

    def __init__(self):
        self.chunk_size = GCS_CONFIG["default_chunk_size"]  # 기본 청크 크기
        self.max_chunk_size = GCS_CONFIG["max_chunk_size"]  # 최대 청크 크기
        self.grpc_message_limit = GCS_CONFIG[
            "grpc_message_size_limit"
        ]  # gRPC 메시지 크기 제한

    @abstractmethod
    def parse_stream(
        self, stream: IO, field_mapper: FieldMapper, **kwargs
    ) -> Generator[dict, None, None]:
        """스트림을 파싱하여 매핑된 데이터 반환

        Args:
            stream: 파일 스트림
            field_mapper: 필드 매핑 객체
            **kwargs: 추가 파싱 옵션

        Yields:
            매핑된 비용 데이터 레코드
        """
        pass

    def set_chunk_size(self, chunk_size: int):
        """청크 크기 설정"""
        self.chunk_size = max(1, min(chunk_size, self.max_chunk_size))

    def _create_batch_result(self, records: list) -> dict:
        """배치 결과 생성 - billed_date 필드 검증 및 직렬화 포함"""
        # 모든 레코드에 billed_date 필드가 있는지 검증
        validated_records = []
        for record in records:
            if not record.get("billed_date"):
                # 현재 날짜 사용하지 않고 None으로 유지
                record["billed_date"] = None

            # 모든 Pandas/Numpy 객체를 직렬화 가능한 타입으로 변환
            sanitized_record = self._sanitize_record_for_serialization(record)

            # SpaceONE 프레임워크 요구사항 준수
            # data 필드에 SpaceONE 빌링 표준에 맞는 정보 추가
            list_price = self._get_list_price_from_record(record)
            sanitized_record["data"] = self._create_spaceone_billing_data(
                record, list_price
            )

            validated_records.append(sanitized_record)

        # SpaceONE 프레임워크 요구사항 최종 확인
        # data 필드에 list_price와 cost 정보가 포함되었는지 최종 확인
        final_results = []
        for record in validated_records:
            # cost 필드 보장 (빈 값은 기본값 처리)
            if "cost" not in record:
                record["cost"] = 0  # 기본값

            # data 필드가 올바르게 설정되었는지 확인하고 보장
            if "data" not in record or not isinstance(record["data"], dict):
                list_price = self._get_list_price_from_record(record)
                record["data"] = self._create_spaceone_billing_data(record, list_price)

            # data 필드에도 cost가 있는지 확인 (원본 데이터 보존)
            if isinstance(record.get("data"), dict):
                if "cost" not in record["data"]:
                    record["data"]["cost"] = record.get("cost")  # 원본 그대로

            final_results.append(record)

        # 궁극적 보장 시스템 적용 - cost 필드 최종 검증
        response = {"results": final_results}

        for record in response["results"]:
            if isinstance(record, dict):
                if "cost" not in record:
                    record["cost"] = 0.0
                    _LOGGER.error(
                        "[BaseParser] CRITICAL: cost field missing, added 0.0"
                    )
                # cost 필드를 딕셔너리의 첫 번째 위치로 이동
                cost_value = record.pop("cost")
                record_copy = record.copy()
                record.clear()
                record["cost"] = cost_value  # 첫 번째 위치에 cost 필드 배치
                record.update(record_copy)

        #  최종 응답에서 data.cost 제거 (내부 연산은 유지됨)
        response = self._remove_data_cost_from_response(response)
        return response

    def _get_list_price_from_record(self, record: dict):
        """레코드에서 list_price(정가) 정보를 추출

        Google Cloud Billing 데이터에서 정가 정보는 다음 순서로 확인:
        1. cost_at_list (최상위 레벨) - 0이 아닌 값만
        2. price.list_price (중첩 구조) - cost_at_list가 0일 때 중요한 대체 소스
        3. price.list_price_consumption_model (소비 모델 기준 정가)
        4. cost (정가 정보가 없는 경우 실제 비용 사용)
        """
        # 1. 최상위 레벨의 cost_at_list 필드 확인 (0이 아닌 값만)
        cost_at_list = record.get("cost_at_list")
        if cost_at_list is not None and cost_at_list != "" and cost_at_list != 0:
            return cost_at_list

        # 2. price.list_price 중첩 구조 확인 (cost_at_list가 0일 때 중요한 대체 소스)
        price_info = record.get("price", {})
        if isinstance(price_info, dict):
            list_price = price_info.get("list_price")
            if list_price is not None and list_price != "" and list_price != 0:
                # 문자열인 경우 숫자로 변환 시도
                try:
                    return (
                        float(list_price) if isinstance(list_price, str) else list_price
                    )
                except (ValueError, TypeError):
                    pass

            # 3. 소비 모델 기준 정가 확인
            list_price_consumption = price_info.get("list_price_consumption_model")
            if (
                list_price_consumption is not None
                and list_price_consumption != ""
                and list_price_consumption != 0
            ):
                try:
                    return (
                        float(list_price_consumption)
                        if isinstance(list_price_consumption, str)
                        else list_price_consumption
                    )
                except (ValueError, TypeError):
                    pass

        # 4. 정가 정보가 없는 경우 실제 비용 사용 (fallback)
        cost_value = record.get("cost")
        if cost_value is not None and cost_value != "":
            return cost_value

        # 5. 모든 시도가 실패한 경우 빈 문자열 반환
        return ""

    def _create_spaceone_billing_data(self, record: dict, list_price) -> dict:
        """SpaceONE 빌링 표준에 맞는 data 필드 구조 생성"""
        # 기본 비용 정보 (숫자 타입으로 처리)
        data_structure = {
            "list_price": self._convert_to_numeric(list_price),
            "cost": self._convert_to_numeric(record.get("cost", 0)),
        }

        cost_after_credits = record.get("cost_after_credits")
        if cost_after_credits is not None and cost_after_credits != "":
            data_structure["cost_after_credits"] = self._convert_to_numeric(
                cost_after_credits
            )

        # 환율 정보
        currency_conversion_rate = record.get("currency_conversion_rate")
        if (
            currency_conversion_rate is not None
            and currency_conversion_rate != ""
            and currency_conversion_rate != 1
        ):
            data_structure["currency_conversion_rate"] = self._convert_to_numeric(
                currency_conversion_rate
            )

        return data_structure

    def _convert_to_numeric(self, value):
        """금액 데이터 처리: 빈 값은 기본값으로, 나머지는 원본 보존"""
        # 빈 값 처리: "", None, "null" -> 숫자 타입 기본값 0
        if (
            value is None
            or value == ""
            or (isinstance(value, str) and value.lower() == "null")
        ):
            return 0

        # 나머지 금액 관련 데이터는 원본 그대로 보존
        return value

    def _sanitize_record_for_serialization(self, record: dict) -> dict:
        """레코드를 JSON 직렬화 가능한 타입으로 변환"""
        from datetime import date, datetime
        from decimal import Decimal

        import numpy as np
        import pandas as pd

        def convert_value(value):
            """개별 값을 직렬화 가능한 타입으로 변환"""
            # None 체크를 먼저 수행
            if value is None:
                return None
            # Pandas NA 체크는 안전하게 수행
            try:
                if pd.isna(value):
                    return None
            except (TypeError, ValueError):
                # pd.isna()가 실패하면 무시하고 계속 진행
                pass

            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                # Pandas Timestamp/Timedelta -> 문자열
                return str(value)
            elif isinstance(value, (np.integer, np.floating)):
                # Numpy 숫자 타입 -> Python 기본 타입
                return value.item()
            elif isinstance(value, np.ndarray):
                # Numpy 배열 -> 리스트
                return [convert_value(item) for item in value]
            elif isinstance(value, (datetime, date)):
                # Python datetime -> 문자열
                return value.isoformat()
            elif isinstance(value, Decimal):
                # Decimal -> float
                return float(value)
            elif isinstance(value, dict):
                # 중첩 딕셔너리 재귀 처리
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                # 리스트/튜플 재귀 처리
                return [convert_value(item) for item in value]
            else:
                return value

        # 전체 레코드 변환
        sanitized_record = {}
        for key, value in record.items():
            try:
                sanitized_record[key] = convert_value(value)
            except Exception as e:
                _LOGGER.warning(
                    f"[BaseParser] Failed to sanitize field {key}: {e}, converting to string"
                )
                sanitized_record[key] = str(value)  # 실패 시 문자열로 변환

        return sanitized_record

    def _estimate_message_size(self, records: list) -> int:
        """메시지 크기 추정 (바이트 단위)"""
        try:
            # 첫 번째 레코드를 기준으로 평균 레코드 크기 추정
            if not records:
                return 0

            # 샘플 레코드의 메모리 사용량 추정
            sample_record = records[0]
            estimated_record_size = len(str(sample_record).encode("utf-8"))

            # 전체 배치 크기 추정 (JSON 직렬화 오버헤드 고려)
            total_size = estimated_record_size * len(records) * 1.5  # 1.5배 여유분
            return int(total_size)
        except Exception as e:
            _LOGGER.warning(f"[BaseParser] Failed to estimate message size: {e}")
            # 안전한 기본값 반환
            return len(records) * 1000  # 레코드당 1KB로 추정

    def _adjust_chunk_size_dynamically(self, current_batch_size: int, records: list):
        """동적 청크 크기 조정 - 더욱 보수적인 접근"""
        estimated_size = self._estimate_message_size(records)

        if (
            estimated_size > self.grpc_message_limit * 0.6
        ):  # 60% 임계값으로 더욱 보수적 접근
            # 청크 크기를 줄여야 함
            new_chunk_size = max(50, int(self.chunk_size * 0.5))  # 더 적극적으로 감소
            if new_chunk_size != self.chunk_size:
                self.chunk_size = new_chunk_size
                _LOGGER.warning(
                    f"[BaseParser] Chunk size reduced to {new_chunk_size} "
                    f"(estimated message size: {estimated_size:,} bytes)"
                )
        elif (
            estimated_size < self.grpc_message_limit * 0.2  # 20%로 더욱 보수적
            and self.chunk_size < self.max_chunk_size
        ):
            # 청크 크기를 늘릴 수 있음 (천천히)
            new_chunk_size = min(
                self.max_chunk_size, int(self.chunk_size * 1.1)
            )  # 10%씩만 증가
            if new_chunk_size != self.chunk_size:
                self.chunk_size = new_chunk_size

    def _log_parsing_progress(self, processed_count: int, file_name: str = ""):
        """파싱 진행 상황 로깅"""
        if processed_count > 0 and processed_count % 1000 == 0:
            file_info = f" in {file_name}" if file_name else ""
            _LOGGER.info(
                f"[{self.__class__.__name__}] Processed {processed_count:,} records{file_info}"
            )

    def _remove_data_cost_from_response(self, response: dict) -> dict:
        """최종 응답에서 data.cost 필드만 제거 (내부 연산은 유지)

        Args:
            response: 응답 딕셔너리 {"results": [record1, record2, ...]}

        Returns:
            data.cost가 제거된 응답 딕셔너리
        """
        if not isinstance(response.get("results"), list):
            return response

        removed_count = 0
        for record in response["results"]:
            if isinstance(record, dict) and "data" in record:
                if isinstance(record["data"], dict) and "cost" in record["data"]:
                    del record["data"]["cost"]
                    removed_count += 1

        if removed_count > 0:
            _LOGGER.debug(
                f"[{self.__class__.__name__}] Removed data.cost from {removed_count} records in response"
            )

        return response

    def _log_batch_processing(
        self, batch_size: int, total_processed: int, file_name: str = ""
    ):
        """배치 처리 로깅 - 페이징 단위 카운트 추가"""
        file_info = f" from {file_name}" if file_name else ""
        _LOGGER.info(
            f"[{self.__class__.__name__}] Processing batch: {batch_size:,} records "
            f"(Total processed: {total_processed:,}){file_info}"
        )
