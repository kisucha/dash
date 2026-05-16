# 목적: F004 validators 패키지 초기화.
# stage_validator.py의 StageValidator 클래스를 외부에서 간편하게 임포트할 수 있도록 한다.

import sys

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pipelines.f004_youtube_v2.validators.stage_validator import StageValidator

__all__ = ["StageValidator"]
