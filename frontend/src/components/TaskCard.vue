<!-- TaskCard.vue — 최근 실행 작업 정보를 카드 형태로 표시하는 컴포넌트 -->
<!-- props: task (id, feature_id, status, created_at) — 클릭 시 /tasks/{id}로 이동 -->
<script setup>
import { useRouter } from 'vue-router'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  // Task 객체 — id, feature_id, status, created_at 필드 포함
  task: {
    type: Object,
    required: true,
  },
})

const router = useRouter()

// 카드 클릭 시 TaskDetailView로 이동
function goToDetail() {
  router.push({ name: 'TaskDetail', params: { id: props.task.id } })
}

// 생성 시각을 읽기 좋은 형태로 포맷
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="task-card" @click="goToDetail" role="button" tabindex="0"
    @keyup.enter="goToDetail">
    <!-- 상단: 작업 ID + 상태 배지 -->
    <div class="task-card-header">
      <span class="task-id">#{{ task.id }}</span>
      <StatusBadge :status="task.status" />
    </div>

    <!-- 업무 ID (feature_id) -->
    <div class="task-feature">{{ task.feature_id }}</div>

    <!-- 생성 시각 -->
    <div class="task-time">{{ formatDate(task.created_at) }}</div>
  </div>
</template>

<style scoped>
/* 작업 카드 기본 스타일 */
.task-card {
  background: #ffffff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
  outline: none;
}

.task-card:hover,
.task-card:focus {
  box-shadow: 0 2px 8px rgba(74, 144, 217, 0.12);
  border-color: #4a90d9;
}

/* 헤더 — ID와 배지를 양 끝에 배치 */
.task-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

/* 작업 ID 표시 */
.task-id {
  font-size: 13px;
  font-weight: 600;
  color: #4a90d9;
  font-family: monospace;
}

/* Feature ID 표시 */
.task-feature {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 생성 시각 */
.task-time {
  font-size: 12px;
  color: #999;
}
</style>
