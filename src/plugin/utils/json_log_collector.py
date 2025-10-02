"""
JSON 로그 수집기 - server_log.json 형식 문제 해결
SpaceONE 프레임워크의 개별 JSON 출력을 올바른 JSON 배열로 변환
"""

import json
import logging
import threading
from typing import List

_LOGGER = logging.getLogger("spaceone")


class JSONLogCollector:
    """JSON 응답을 수집하여 올바른 JSON 배열 형식으로 출력하는 클래스"""

    def __init__(self, output_file: str = "server_log.json"):
        """
        Args:
            output_file: 출력할 JSON 파일 경로
        """
        self.output_file = output_file
        self.collected_responses: List[dict] = []
        self.lock = threading.Lock()
        self.is_collecting = False

    def start_collection(self):
        """JSON 수집 시작"""
        with self.lock:
            self.collected_responses = []
            self.is_collecting = True
            _LOGGER.info(
                f"[JSONLogCollector] Started collecting JSON responses to {self.output_file}"
            )

    def add_response(self, response: dict):
        """응답 추가

        Args:
            response: 추가할 응답 딕셔너리
        """
        if not self.is_collecting:
            return

        with self.lock:
            if isinstance(response, dict):
                # results 배열이 있는 경우 개별 레코드들을 추출
                if "results" in response and isinstance(response["results"], list):
                    for record in response["results"]:
                        if isinstance(record, dict):
                            self.collected_responses.append(record)
                else:
                    # 단일 레코드인 경우
                    self.collected_responses.append(response)

    def stop_collection_and_save(self):
        """수집 중단하고 JSON 배열로 저장"""
        if not self.is_collecting:
            return

        with self.lock:
            self.is_collecting = False

            try:
                # 올바른 JSON 배열 형식으로 저장
                output_data = {
                    "results": self.collected_responses,
                    "total_count": len(self.collected_responses),
                }

                with open(self.output_file, "w", encoding="utf-8") as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)

                _LOGGER.info(
                    f"[JSONLogCollector] Saved {len(self.collected_responses)} responses "
                    f"to {self.output_file} in valid JSON array format"
                )

            except Exception as e:
                _LOGGER.error(f"[JSONLogCollector] Failed to save JSON log: {e}")
            finally:
                self.collected_responses = []

    def get_collected_count(self) -> int:
        """수집된 응답 수 반환"""
        with self.lock:
            return len(self.collected_responses)


# 전역 JSON 로그 수집기 인스턴스
_json_log_collector = JSONLogCollector()


def start_json_logging():
    """JSON 로깅 시작"""
    _json_log_collector.start_collection()


def log_json_response(response: dict):
    """JSON 응답 로깅

    Args:
        response: 로깅할 응답 딕셔너리
    """
    _json_log_collector.add_response(response)


def stop_json_logging():
    """JSON 로깅 중단 및 파일 저장"""
    _json_log_collector.stop_collection_and_save()


def get_logged_count() -> int:
    """로깅된 응답 수 반환"""
    return _json_log_collector.get_collected_count()


def is_json_logging_active() -> bool:
    """JSON 로깅 활성 상태 확인"""
    return _json_log_collector.is_collecting
