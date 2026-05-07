// store/tasks.js — Tasks 및 Features 전역 상태 관리 Pinia 스토어
// cursor 기반 페이징 지원: nextCursor, hasMore 상태 및 fetchMoreTasks 액션 제공
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getTasks as apiGetTasks,
  getFeatures as apiGetFeatures,
  createTask as apiCreateTask,
  cancelTask as apiCancelTask,
  deleteTaskRecord as apiDeleteTaskRecord,
} from '../api/index.js'

export const useTaskStore = defineStore('tasks', () => {
  // ────────────────────────────────────────────────
  // State
  // ────────────────────────────────────────────────

  // 작업 목록 배열
  const tasks = ref([])
  // 업무(Feature) 목록 배열
  const features = ref([])
  // cursor 기반 페이징 상태
  const nextCursor = ref(null)
  const hasMore = ref(false)

  // ────────────────────────────────────────────────
  // Actions
  // ────────────────────────────────────────────────

  // 작업 목록을 백엔드에서 가져와 state에 반영 (첫 페이지 또는 cursor 지정 페이지)
  async function fetchTasks(limit = 20, cursor = null) {
    try {
      const res = await apiGetTasks(limit, cursor)
      tasks.value = res.data.items ?? []
      nextCursor.value = res.data.next_cursor ?? null
      hasMore.value = res.data.has_more ?? false
    } catch (err) {
      console.error('[TaskStore] fetchTasks 실패:', err)
    }
  }

  // 다음 페이지를 기존 목록에 이어 붙임 (무한 스크롤 / 더 보기)
  async function fetchMoreTasks(limit = 20) {
    if (!hasMore.value || nextCursor.value == null) return
    try {
      const res = await apiGetTasks(limit, nextCursor.value)
      tasks.value = [...tasks.value, ...(res.data.items ?? [])]
      nextCursor.value = res.data.next_cursor ?? null
      hasMore.value = res.data.has_more ?? false
    } catch (err) {
      console.error('[TaskStore] fetchMoreTasks 실패:', err)
    }
  }

  // Feature 목록을 백엔드에서 가져와 state에 반영
  async function fetchFeatures() {
    try {
      const res = await apiGetFeatures()
      features.value = res.data
    } catch (err) {
      console.error('[TaskStore] fetchFeatures 실패:', err)
    }
  }

  // 새 작업을 생성하고 생성된 Task 객체를 반환
  async function createTask(featureId, params) {
    const res = await apiCreateTask(featureId, params)
    return res.data
  }

  // 작업을 취소 (DELETE)
  async function cancelTask(id) {
    await apiCancelTask(id)
  }

  // 작업 이력을 DB에서 삭제하고 로컬 state에서도 제거
  async function deleteTaskRecord(id) {
    await apiDeleteTaskRecord(id)
    tasks.value = tasks.value.filter(t => t.id !== id)
  }

  return {
    tasks,
    features,
    nextCursor,
    hasMore,
    fetchTasks,
    fetchMoreTasks,
    fetchFeatures,
    createTask,
    cancelTask,
    deleteTaskRecord,
  }
})
