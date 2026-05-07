// api/index.js — 백엔드 FastAPI와의 모든 HTTP 통신을 담당하는 API 레이어
// axios 인스턴스를 생성하고 tasks, features, schedules, health 관련 함수를 export한다
import axios from 'axios'

// axios 인스턴스 — baseURL을 비워서 Vite 프록시(/api → localhost:8000)를 경유
// 직접 localhost:8000을 지정하면 CORS preflight가 필요해 브라우저에서 차단될 수 있음
const api = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ────────────────────────────────────────────────
// Health API
// ────────────────────────────────────────────────

// Ollama 연결 상태 확인
export const getOllamaHealth = () => api.get('/api/health/ollama')

// ────────────────────────────────────────────────
// Features API — 업무(기능) 목록 및 상세 조회
// ────────────────────────────────────────────────

// 전체 Feature 목록 조회
export const getFeatures = () => api.get('/api/features')

// 특정 Feature 상세 조회
export const getFeature = (id) => api.get(`/api/features/${id}`)

// ────────────────────────────────────────────────
// Tasks API — 작업 생성, 조회, 취소
// ────────────────────────────────────────────────

// 작업 목록 조회 (cursor 기반 페이징 — cursor 없으면 최신 N개 첫 페이지)
export const getTasks = (limit = 20, cursor = null) =>
  api.get('/api/tasks', { params: { limit, ...(cursor != null ? { cursor } : {}) } })

// 특정 업무의 작업 이력 조회 (feature_id 필터, cursor 기반 페이징)
export const getTasksByFeature = (featureId, limit = 50, cursor = null) =>
  api.get('/api/tasks', { params: { feature_id: featureId, limit, ...(cursor != null ? { cursor } : {}) } })

// 특정 작업 상세 조회
export const getTask = (id) => api.get(`/api/tasks/${id}`)

// 새 작업 생성 — body: { feature_id, params }
export const createTask = (featureId, params) =>
  api.post('/api/tasks', { feature_id: featureId, params })

// 작업 취소
export const cancelTask = (id) => api.delete(`/api/tasks/${id}`)

// 작업 이력 삭제 — 완료(DONE/FAILED/CANCELLED) 상태 작업만 삭제 가능
export const deleteTaskRecord = (id) => api.delete(`/api/tasks/${id}/history`)

// ────────────────────────────────────────────────
// Models API — Ollama 모델 목록 및 선택
// ────────────────────────────────────────────────

// 설치된 모델 목록 + 현재 선택 모델 조회
export const getModels = () => api.get('/api/models')

// 모델 선택 저장
export const selectModel = (model) => api.put('/api/models/select', { model })

// ────────────────────────────────────────────────
// Schedules API — 스케줄 관련 (Phase 3 완성 예정)
// ────────────────────────────────────────────────

// 스케줄 목록 조회
export const getSchedules = () => api.get('/api/schedules')

// ────────────────────────────────────────────────
// Search API — DuckDuckGo 인터넷 검색
// ────────────────────────────────────────────────

// 인터넷 검색 — provider: 'searxng'(기본, 로컬) | 'tavily'(LLM 최적화)
// multihop=true 시 각 hop 후 서브쿼리를 생성해 maxHops차까지 심층 검색
// useLlmSubqueries=true: LLM이 발견된 엔티티를 파고드는 depth-first 쿼리 생성
// timeout 60s: 멀티 홉 + LLM 서브쿼리 생성은 30~45초 소요 → 기본 15초로는 항상 실패함
export const searchWeb = (query, maxResults = 20, provider = 'searxng', multihop = false, maxHops = 3, useLlmSubqueries = false) =>
  api.post('/api/search', { query, max_results: maxResults, provider, multihop, max_hops: maxHops, use_llm_subqueries: useLlmSubqueries }, { timeout: 60000 })

// ────────────────────────────────────────────────
// Chat API — Ollama 스트리밍 채팅 (fetch 직접 사용)
// SSE 스트림이므로 axios 대신 fetch API를 사용한다
// ────────────────────────────────────────────────

// 쿼리 정제 — 이력 기반으로 지시대명사("해당", "그") 포함 질문을 구체적 검색어로 변환
// was_refined=true이면 refined에 정제된 쿼리, false이면 original 그대로 반환
export const refineQuery = (message, history = [], searchProvider = 'searxng') =>
  api.post('/api/chat/refine', { message, history, search_provider: searchProvider })

// 채팅 스트리밍 요청 — ReadableStream을 반환하므로 호출부에서 reader로 처리
// refinedQuery: 이력 기반으로 정제된 검색 쿼리 (없으면 null — 백엔드가 원본 사용)
export const sendChatStream = (message, history = [], searchContext = null, searchProvider = 'searxng', refinedQuery = null) =>
  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history,
      search_context: searchContext,
      search_provider: searchProvider,
      refined_query: refinedQuery,
    }),
  })

// ────────────────────────────────────────────────
// Model Assets API — F003 영상제작 모델 관리
// ────────────────────────────────────────────────

// 모델 인벤토리 목록 조회 (model_type, base_model 필터 가능)
export const getModelAssets = (modelType = null, baseModel = null) =>
  api.get('/api/model-assets', { params: { ...(modelType ? { model_type: modelType } : {}), ...(baseModel ? { base_model: baseModel } : {}) } })

// 진행 중인 다운로드 목록 조회
export const getDownloads = () => api.get('/api/model-assets/downloads')

// 다운로드 트리거
export const triggerDownload = (payload) => api.post('/api/model-assets/download', payload)

// 로컬 모델 재스캔
export const scanLocalModels = () => api.post('/api/model-assets/scan')
