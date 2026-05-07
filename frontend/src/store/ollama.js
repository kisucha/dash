// store/ollama.js — Ollama 서버 상태, 모델 목록, 선택 모델 전역 관리 스토어
// 컴포넌트 remount 후에도 상태가 유지되어 "상태 확인 중" 반복 노출을 방지한다
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getModels, selectModel as apiSelectModel } from '../api/index.js'

export const useOllamaStore = defineStore('ollama', () => {
  // ── 상태 ──────────────────────────────────────────
  // Ollama 연결 상태: 'loading' | 'ok' | 'error'
  const status = ref('loading')
  // 오류·경고 문자열 (정상이면 빈 문자열)
  const message = ref('')
  // 설치된 Ollama 모델 이름 배열
  const modelList = ref([])
  // 현재 선택된 모델명
  const selectedModel = ref('')
  // 모델 변경 저장 진행 중 여부
  const modelSaving = ref(false)

  // ── Actions ───────────────────────────────────────

  // 모델 목록 로드 및 연결 상태 갱신 — 실패해도 status를 'error'로 명확히 설정
  async function loadModels() {
    console.log('[OllamaStore] loadModels 시작')
    try {
      const res = await getModels()
      console.log('[OllamaStore] 응답 수신:', res.data)
      const models = res.data?.models ?? []
      const selected = res.data?.selected_model ?? ''
      modelList.value = models
      selectedModel.value = selected
      status.value = 'ok'
      message.value = models.length === 0 ? '설치된 모델 없음' : ''
    } catch (err) {
      console.error('[OllamaStore] 오류:', err)
      status.value = 'error'
      message.value = err?.message ?? '모델 목록 로드 실패'
    }
  }

  // 사용 모델 변경 및 백엔드 저장 — 실패 시 이전 선택 유지
  async function changeModel(model) {
    if (!model || modelSaving.value) return
    const prev = selectedModel.value
    modelSaving.value = true
    try {
      const res = await apiSelectModel(model)
      selectedModel.value = res.data.selected_model
    } catch {
      selectedModel.value = prev
    } finally {
      modelSaving.value = false
    }
  }

  return { status, message, modelList, selectedModel, modelSaving, loadModels, changeModel }
})
