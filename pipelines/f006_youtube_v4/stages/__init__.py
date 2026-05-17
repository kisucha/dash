# 목적: F006 스테이지 공통 인터페이스 - BaseStage, ValidationResult 정의.
# 모든 스테이지 클래스는 이 모듈의 BaseStage를 상속받아 구현한다.

import sys

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValidationResult:
    """스테이지 입/출력 유효성 검증 결과.

    is_valid: 유효 여부 (False이면 오케스트레이터가 반송 처리)
    rejection_reason: 반송 사유 텍스트 (UI 표시용)
    rejection_target: 반송할 스테이지 ID (예: STAGE_01_INPUT)
                      None이면 현재 스테이지 자기 재시도
    """

    is_valid: bool
    rejection_reason: Optional[str] = None
    rejection_target: Optional[str] = None


class BaseStage:
    """F006 스테이지 추상 베이스 클래스.

    하위 클래스(Stage01Input 등)가 반드시 구현해야 하는 메서드:
      - execute(job_id, input_data) -> dict

    validate_input, validate_output은 기본 구현(항상 통과)이 있으며
    필요 시 오버라이드한다.

    BasePipeline의 call_ollama(), call_searxng() 같은 유틸은
    각 스테이지 클래스 내부에서 BasePipeline 인스턴스를 별도로
    생성하거나, 오케스트레이터로부터 주입받는 방식으로 사용한다.
    """

    # 하위 클래스에서 반드시 재정의할 상수
    STAGE_ID: str = ""       # 예: "STAGE_01_INPUT"
    STAGE_ORDER: int = 0     # 실행 순서 (1~6)

    def validate_input(self, data: dict) -> ValidationResult:
        """스테이지 실행 전 입력 데이터 유효성 검증.

        기본 구현은 항상 유효 판정을 반환한다.
        필수 파라미터가 있는 스테이지는 이 메서드를 오버라이드한다.

        Args:
            data: 이 스테이지에 전달될 입력 딕셔너리

        Returns:
            ValidationResult - is_valid=True이면 execute() 진행,
                               is_valid=False이면 반송 처리
        """
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """스테이지 실제 실행 - 하위 클래스에서 반드시 구현.

        Args:
            job_id: content_jobs.id - 결과 저장 경로 구성에 사용
            input_data: 이전 스테이지 출력 + 초기 파라미터 조합

        Returns:
            이 스테이지의 출력 딕셔너리 (JSON 직렬화 가능해야 함)

        Raises:
            NotImplementedError: 하위 클래스에서 구현하지 않은 경우
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.execute()를 구현해야 합니다."
        )

    def validate_output(self, output: dict) -> ValidationResult:
        """스테이지 실행 후 출력 데이터 유효성 검증.

        기본 구현은 항상 유효 판정을 반환한다.
        품질 기준(분량, 필수 키 존재 등)이 있는 스테이지는 오버라이드한다.

        Args:
            output: execute()가 반환한 출력 딕셔너리

        Returns:
            ValidationResult - is_valid=False이면 오케스트레이터가 반송 처리
        """
        return ValidationResult(is_valid=True)
