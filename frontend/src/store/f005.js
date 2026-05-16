// store/f005.js — F005 유튜브 컨텐츠 제작 채팅 기반 파이프라인 Pinia 스토어
// 작업 목록, 작업 단건, 스테이지 조작 상태를 관리한다
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getF005Jobs,
  getF005Job,
  createF005Job,
  retryF005Stage,
  rejectF005Stage,
  approveF005Job,
  deleteF005Job,
  rerunF005FromTTS,
} from '../api/index.js'

// F005 스토어 — Composition API 스타일로 정의
export const useF005Store = defineStore('f005', () => {
  // ── 상태 (State) ──
  // jobs: F005 작업 목록 (cursor 기반 페이징)
  const jobs = ref([])
  // currentJob: 현재 상세 조회 중인 작업 (스테이지 포함)
  const currentJob = ref(null)
  // nextCursor: 작업 목록 다음 페이지 커서
  const nextCursor = ref(null)
  // hasMore: 작업 목록 추가 페이지 존재 여부
  const hasMore = ref(false)
  // loading: API 통신 중 여부 (UI 스피너/비활성 처리용)
  const loading = ref(false)
  // errorMsg: 마지막 API 오류 메시지
  const errorMsg = ref('')

  // ── 액션 (Actions) ──

  // 작업 목록 조회 — 첫 페이지부터 새로 로드 (status 필터 선택 가능)
  async function fetchJobs(limit = 20, status = null) {
    loading.value = true
    errorMsg.value = ''
    try {
      const res = await getF005Jobs(limit, null, status)
      jobs.value = res.data.items ?? []
      nextCursor.value = res.data.next_cursor ?? null
      hasMore.value = res.data.has_more ?? false
    } catch (e) {
      errorMsg.value = e.message
    } finally {
      loading.value = false
    }
  }

  // 작업 목록 추가 로드 — cursor를 이용한 다음 페이지 (기존 목록에 append)
  async function fetchMoreJobs(limit = 20) {
    if (!hasMore.value) return
    loading.value = true
    try {
      const res = await getF005Jobs(limit, nextCursor.value, null)
      jobs.value = [...jobs.value, ...(res.data.items ?? [])]
      nextCursor.value = res.data.next_cursor ?? null
      hasMore.value = res.data.has_more ?? false
    } catch (e) {
      errorMsg.value = e.message
    } finally {
      loading.value = false
    }
  }

  // 작업 단건 조회 — 스테이지 목록 포함
  async function fetchJob(jobId) {
    loading.value = true
    try {
      const res = await getF005Job(jobId)
      currentJob.value = res.data
    } catch (e) {
      errorMsg.value = e.message
    } finally {
      loading.value = false
    }
  }

  // 새 작업 생성 — 성공 시 작업 목록 맨 앞에 추가, 실패 시 예외 re-throw
  async function createJob(params) {
    loading.value = true
    errorMsg.value = ''
    try {
      const res = await createF005Job(params)
      jobs.value.unshift(res.data)
      return res.data
    } catch (e) {
      errorMsg.value = e.response?.data?.detail ?? e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  // 작업 삭제 — jobs 목록에서도 제거
  async function deleteJob(jobId) {
    await deleteF005Job(jobId)
    jobs.value = jobs.value.filter((j) => j.id !== jobId)
  }

  // 스테이지 재시도 — 실패/반송된 스테이지를 재실행하고 작업 새로고침
  async function retryStage(jobId, stageId, overrideParams = null) {
    await retryF005Stage(jobId, stageId, overrideParams)
    await fetchJob(jobId)
  }

  // 스테이지 반송 — 특정 스테이지를 반송하고 작업 새로고침
  async function rejectStage(jobId, stageId, reason, rejectionTarget = null) {
    await rejectF005Stage(jobId, stageId, reason, rejectionTarget)
    await fetchJob(jobId)
  }

  // 업로드 승인 — SEO 메타데이터 최종 승인 후 업로드 실행, 작업 새로고침
  async function approveJob(jobId, finalMeta = {}) {
    await approveF005Job(jobId, finalMeta)
    await fetchJob(jobId)
  }

  // 스크립트 수정 후 TTS부터 재생성 — script_text 필수, slides 선택적 전달
  async function rerunFromTTS(jobId, scriptText, slides = null) {
    loading.value = true
    errorMsg.value = ''
    try {
      const payload = { script_text: scriptText }
      if (slides !== null) payload.slides = slides
      await rerunF005FromTTS(jobId, payload)
      await fetchJob(jobId)
    } catch (e) {
      errorMsg.value = e.response?.data?.detail ?? e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    // 상태 노출
    jobs,
    currentJob,
    nextCursor,
    hasMore,
    loading,
    errorMsg,
    // 액션 노출
    fetchJobs,
    fetchMoreJobs,
    fetchJob,
    createJob,
    deleteJob,
    retryStage,
    rejectStage,
    approveJob,
    rerunFromTTS,
  }
})
