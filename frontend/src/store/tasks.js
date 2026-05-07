// store/tasks.js — Tasks 및 Features 전역 상태 관리 Pinia 스토어
// 작업 목록, 기능 목록, 전체 작업 수를 state로 보유하고
// fetchTasks, fetchFeatures, createTask, cancelTask 액션을 제공한다
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
  // 전체 작업 수 (페이지네이션용)
  const totalTasks = ref(0)

  // ────────────────────────────────────────────────
  // Actions
  // ────────────────────────────────────────────────

  // 작업 목록을 백엔드에서 가져와 state에 반영
  async function fetchTasks(limit = 20, offset = 0) {
    try {
      const res = await apiGetTasks(limit, offset)
      tasks.value = res.data.items ?? []
      totalTasks.value = res.data.total ?? 0
    } catch (err) {
      console.error('[TaskStore] fetchTasks 실패:', err)
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
    totalTasks.value = Math.max(0, totalTasks.value - 1)
  }

  return { tasks, features, totalTasks, fetchTasks, fetchFeatures, createTask, cancelTask, deleteTaskRecord }
})
