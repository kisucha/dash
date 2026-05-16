// store/f001.js — F001 유튜브 컨텐츠 제작 파이프라인 Pinia 스토어
// 작업 목록, 작업 단건, 스테이지 조작, YouTube 할당량 상태를 관리한다
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getF001Jobs,
  getF001Job,
  createF001Job,
  retryF001Stage,
  rejectF001Stage,
  approveF001Job,
  selectF001Topic,
  deleteF001Job,
  getYoutubeQuota,
} from '../api/index.js'

// F001 스토어 — Composition API 스타일로 정의
export const useF001Store = defineStore('f001', () => {
  // ── 상태 (State) ──
  // jobs: F001 작업 목록 (cursor 기반 페이징)
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
  // youtubeQuota: YouTube Data API 일일 할당량 사용 현황
  const youtubeQuota = ref(null)

  // ── 액션 (Actions) ──

  // 작업 목록 조회 — 첫 페이지부터 새로 로드 (status 필터 선택 가능)
  async function fetchJobs(limit = 20, status = null) {
    loading.value = true
    errorMsg.value = ''
    try {
      const res = await getF001Jobs(limit, null, status)
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
      const res = await getF001Jobs(limit, nextCursor.value, null)
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
      const res = await getF001Job(jobId)
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
      const res = await createF001Job(params)
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
    await deleteF001Job(jobId)
    jobs.value = jobs.value.filter((j) => j.id !== jobId)
  }

  // 주제 선택 — 스테이지 결과에서 특정 rank의 주제를 선택하고 작업 새로고침
  async function selectTopic(jobId, topicRank, title) {
    await selectF001Topic(jobId, topicRank, title)
    await fetchJob(jobId)
  }

  // 스테이지 재시도 — 실패/반송된 스테이지를 재실행하고 작업 새로고침
  async function retryStage(jobId, stageId, overrideParams = null) {
    await retryF001Stage(jobId, stageId, overrideParams)
    await fetchJob(jobId)
  }

  // 스테이지 반송 — 특정 스테이지를 반송하고 작업 새로고침
  async function rejectStage(jobId, stageId, reason, rejectionTarget = null) {
    await rejectF001Stage(jobId, stageId, reason, rejectionTarget)
    await fetchJob(jobId)
  }

  // 업로드 승인 — SEO 메타데이터 최종 승인 후 업로드 실행, 작업 새로고침
  async function approveJob(jobId, finalMeta = {}) {
    await approveF001Job(jobId, finalMeta)
    await fetchJob(jobId)
  }

  // YouTube 할당량 조회 — 실패 시 조용히 처리
  async function fetchQuota() {
    try {
      const res = await getYoutubeQuota()
      youtubeQuota.value = res.data
    } catch {
      // 할당량 조회 실패는 조용히 처리
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
    youtubeQuota,
    // 액션 노출
    fetchJobs,
    fetchMoreJobs,
    fetchJob,
    createJob,
    deleteJob,
    selectTopic,
    retryStage,
    rejectStage,
    approveJob,
    fetchQuota,
  }
})
