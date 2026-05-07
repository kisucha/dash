# 목적: Ollama 로컬 LLM 서버 헬스체크 및 텍스트 생성 호출 담당 서비스 레이어
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Any

import httpx

from core.config import OLLAMA_BASE_URL

# Ollama API 요청 타임아웃 (초) — 헬스체크용 짧은 타임아웃
_HEALTH_TIMEOUT: float = 5.0

# 생성 요청 타임아웃 (초) — LLM 응답 대기 시간 여유 있게 설정
_GENERATE_TIMEOUT: float = 120.0


class OllamaService:
    """Ollama 로컬 서버와 통신하는 서비스 클래스.

    헬스체크와 텍스트 생성 기능을 제공한다.
    """

    async def check_health(self) -> dict[str, Any]:
        """Ollama 서버 연결 상태를 확인한다.

        GET /api/tags 응답으로 연결 여부와 사용 가능한 모델 목록을 반환한다.
        연결 실패 시 status='error'와 오류 메시지를 반환한다.
        """
        try:
            async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()

                # Ollama /api/tags 응답 구조: {"models": [{"name": "..."}, ...]}
                model_names: list[str] = [
                    m.get("name", "") for m in data.get("models", [])
                ]
                return {"status": "ok", "models": model_names, "error": None}

        except httpx.ConnectError:
            return {
                "status": "error",
                "models": [],
                "error": "Ollama 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.",
            }
        except httpx.TimeoutException:
            return {
                "status": "error",
                "models": [],
                "error": "Ollama 서버 응답 시간 초과.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "models": [],
                "error": str(exc),
            }

    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Ollama /api/generate 엔드포인트로 텍스트를 생성한다.

        파이프라인 runner에서 직접 호출하는 용도.
        오류 발생 시 예외를 그대로 전파한다.
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }
        async with httpx.AsyncClient(timeout=_GENERATE_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()


# 싱글턴 인스턴스 — 라우터/서비스에서 임포트하여 사용
ollama_service = OllamaService()
