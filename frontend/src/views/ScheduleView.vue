<!-- ScheduleView.vue — 스케줄 목록 페이지 (/schedules) -->
<!-- Phase 3에서 완성될 예정이며, 현재는 기본 뼈대만 구현되어 있다 -->
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getSchedules } from '../api/index.js'

const router = useRouter()

// 스케줄 목록 배열
const schedules = ref([])
// 로딩 상태
const loading = ref(true)
// 오류 메시지
const errorMsg = ref('')

onMounted(async () => {
  try {
    const res = await getSchedules()
    schedules.value = res.data
  } catch {
    // 백엔드 미구현 상태로 오류는 무시하고 빈 목록으로 처리
    schedules.value = []
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="schedule-view">
    <div class="page-header">
      <div>
        <h1 class="page-title">스케줄 관리</h1>
        <p class="page-desc">반복 실행 스케줄을 관리합니다. (Phase 3에서 완성 예정)</p>
      </div>
      <button class="back-btn" @click="router.push('/')">← 대시보드</button>
    </div>

    <div class="schedule-card">
      <!-- 로딩 중 -->
      <div v-if="loading" class="loading-text">불러오는 중...</div>

      <!-- 오류 -->
      <div v-else-if="errorMsg" class="error-box">{{ errorMsg }}</div>

      <!-- 데이터 없음 -->
      <div v-else-if="schedules.length === 0" class="empty-text">
        등록된 스케줄이 없습니다.
      </div>

      <!-- 스케줄 목록 (Phase 3에서 상세 구현) -->
      <ul v-else class="schedule-list">
        <li v-for="schedule in schedules" :key="schedule.id" class="schedule-item">
          <span class="schedule-id">#{{ schedule.id }}</span>
          <span class="schedule-info">{{ schedule.feature_id }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
/* 페이지 레이아웃 */
.schedule-view {
  max-width: 800px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #222;
  margin: 0 0 6px;
}

.page-desc {
  font-size: 14px;
  color: #888;
  margin: 0;
}

/* 대시보드로 돌아가기 버튼 */
.back-btn {
  padding: 8px 16px;
  background: #e8f0fd;
  color: #4a90d9;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.back-btn:hover {
  background: #d0e4fb;
}

/* 스케줄 카드 영역 */
.schedule-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

/* 로딩/빈 상태 텍스트 */
.loading-text,
.empty-text {
  font-size: 14px;
  color: #aaa;
  text-align: center;
  padding: 20px 0;
}

/* 오류 메시지 */
.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
}

/* 스케줄 목록 */
.schedule-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.schedule-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #eee;
  border-radius: 8px;
  font-size: 14px;
}

.schedule-id {
  font-family: monospace;
  color: #4a90d9;
  font-weight: 600;
}

.schedule-info {
  color: #444;
}
</style>
