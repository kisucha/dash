# 목적: /api/chat SSE 스트리밍 채팅 + /api/chat/refine 쿼리 정제 엔드포인트
# 대화 이력 기반 쿼리 정제(shared.query_refiner) + 멀티 홉 심층 검색(shared.multihop_search)

import sys
import json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import re
from typing import Any, AsyncGenerator
import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.config import OLLAMA_BASE_URL, DB_PATH
from shared.prompt_builder import build_optimized_prompt
from shared.query_refiner import needs_refinement, refine_query_async
import aiosqlite

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Ollama 스트리밍 타임아웃 (초)
_STREAM_TIMEOUT: float = 180.0


# ── 요청/응답 모델 ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """대화 이력 단건 — role은 'user' 또는 'assistant'."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """POST /api/chat 요청 바디."""
    message: str = Field(..., description="사용자 입력 메시지")
    history: list[ChatMessage] = Field(default_factory=list)
    search_context: str | None = Field(default=None, description="검색 결과 요약 텍스트")
    search_provider: str = Field(default="searxng", description="검색 엔진 선택")
    # 프론트에서 정제된 검색 쿼리 — 의도 감지 시 이 쿼리로 추가 검색 수행
    refined_query: str | None = Field(default=None, description="이력 기반으로 정제된 검색 쿼리")


class RefineRequest(BaseModel):
    """POST /api/chat/refine 요청 바디."""
    message: str = Field(..., description="현재 사용자 질문")
    history: list[ChatMessage] = Field(default_factory=list)
    search_provider: str = Field(default="searxng")


class RefineResponse(BaseModel):
    """POST /api/chat/refine 응답."""
    original: str           # 원본 질문
    refined: str            # 정제된 검색 쿼리
    was_refined: bool       # 실제로 정제가 수행되었는지 (False면 원본과 동일)


# ── DB 유틸 ────────────────────────────────────────────────────────────────────

async def _get_selected_model(conn: aiosqlite.Connection) -> str:
    """DB에서 선택된 모델을 조회한다. 없으면 기본 모델 반환."""
    cursor = await conn.execute(
        "SELECT value FROM settings WHERE key = 'selected_model'"
    )
    row = await cursor.fetchone()
    if row and row[0]:
        return row[0]
    return "exaone3.5:2.4b"


# ── 추가 제안 생성 ─────────────────────────────────────────────────────────────

async def _generate_suggestions_async(
    question: str, response_text: str, model: str
) -> list[str]:
    """멀티 홉 검색 완료 후 사용자가 이어서 물어볼 만한 제안 3가지를 생성한다."""
    context = response_text[:2000] if len(response_text) > 2000 else response_text
    prompt = (
        f"다음은 사용자 질문과 AI 답변이다.\n\n"
        f"[질문] {question}\n\n"
        f"[답변 요약]\n{context}\n\n"
        f"위 내용을 바탕으로 사용자가 다음에 물어볼 만한 구체적인 후속 질문 3가지를 생성해라.\n"
        f"각 질문은 한 줄씩, 번호나 기호 없이, 질문 형태로만 출력해라. 설명이나 부연은 금지."
    )
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 256, "temperature": 0.8},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()
    except Exception:
        return []

    suggestions: list[str] = []
    for line in text.splitlines():
        clean = re.sub(r'^[\d]+[.)]\s*|^[-*]\s*', '', line.strip()).strip()
        if clean:
            suggestions.append(clean)
        if len(suggestions) >= 3:
            break
    return suggestions


# ── Ollama 스트리밍 ────────────────────────────────────────────────────────────

async def _stream_ollama(
    model: str,
    prompt: str,
    has_search_context: bool = False,
) -> AsyncGenerator[str, None]:
    """Ollama /api/generate 스트리밍 응답을 SSE 형식으로 yield한다."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_ctx": 8192 if has_search_context else 4096,
            "num_predict": 4096,
            "temperature": 0.7,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk: dict[str, Any] = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token: str = chunk.get("response", "")
                    done: bool = chunk.get("done", False)

                    yield f"data: {json.dumps({'token': token, 'done': done}, ensure_ascii=False)}\n\n"

                    if done:
                        break

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Ollama 서버에 연결할 수 없습니다.', 'done': True})}\n\n"
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'error': 'Ollama 응답 시간 초과.', 'done': True})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"


# ── 채팅 응답 생성 ─────────────────────────────────────────────────────────────

async def _generate_response(request: ChatRequest, model: str) -> AsyncGenerator[str, None]:
    """
    채팅 응답 전체 흐름을 처리하는 SSE 제너레이터.

    search_context가 있으면(프론트 멀티 홉 결과) deep_analysis 모드로 프롬프트 빌드.
    답변 완료 후 search_context가 있었으면 추가 제안 3가지를 SSE로 전송한다.
    """
    has_context = bool(request.search_context)
    history_dicts = [{"role": m.role, "content": m.content} for m in request.history]
    prompt = build_optimized_prompt(
        question=request.message,
        history=history_dicts,
        search_context=request.search_context,
        deep_analysis=False,
    )

    # 인터넷 검색 결과가 있을 때만 토큰 수집 (제안 생성용)
    token_buf: list[str] = []
    async for line in _stream_ollama(model, prompt, has_search_context=has_context):
        yield line
        if has_context and line.startswith("data: "):
            try:
                chunk = json.loads(line[6:].strip())
                if chunk.get("token"):
                    token_buf.append(chunk["token"])
            except Exception:
                pass

    # 인터넷 검색 결과를 참고한 답변이면 추가 제안 3가지 생성
    if has_context and token_buf:
        suggestions = await _generate_suggestions_async(
            request.message, "".join(token_buf), model
        )
        if suggestions:
            yield f"data: {json.dumps({'type': 'suggestions', 'items': suggestions}, ensure_ascii=False)}\n\n"


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@router.post("/refine", response_model=RefineResponse)
async def refine_query_endpoint(request: RefineRequest) -> RefineResponse:
    """
    대화 이력을 기반으로 검색 쿼리를 정제한다.

    지시대명사("해당", "그", "이")가 있는 경우 이력에서 실제 대상을 파악해 구체적 쿼리 생성.
    정제가 불필요하면(독립적 질문) was_refined=False로 원본을 그대로 반환한다.
    """
    history_dicts = [{"role": m.role, "content": m.content} for m in request.history]

    if not needs_refinement(request.message, history_dicts):
        return RefineResponse(
            original=request.message,
            refined=request.message,
            was_refined=False,
        )

    async with aiosqlite.connect(DB_PATH) as conn:
        model = await _get_selected_model(conn)

    refined = await refine_query_async(
        question=request.message,
        history=history_dicts,
        ollama_url=OLLAMA_BASE_URL,
        model=model,
    )

    return RefineResponse(
        original=request.message,
        refined=refined,
        was_refined=(refined.strip() != request.message.strip()),
    )


@router.post("")
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Ollama와 SSE 스트리밍 채팅을 수행한다.

    - search_context가 있으면(프론트 멀티 홉 결과) deep_analysis 모드로 답변
    - 답변 완료 후 search_context가 있었으면 추가 제안 3가지 SSE 전송
    - history로 이전 대화 맥락을 유지
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        model = await _get_selected_model(conn)

    return StreamingResponse(
        _generate_response(request, model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
