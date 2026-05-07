<!-- StatusBadge.vue — 작업 상태를 색상 배지로 표시하는 공통 컴포넌트 -->
<!-- props: status (PENDING/RUNNING/DONE/FAILED/CANCELLED) -->
<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 작업 상태값 — 백엔드 Task 모델의 status 필드와 동일
  status: {
    type: String,
    required: true,
  },
})

// 상태별 한국어 라벨 매핑
const labelMap = {
  PENDING: '대기중',
  RUNNING: '실행중',
  DONE: '완료',
  FAILED: '실패',
  CANCELLED: '취소됨',
}

// 상태별 CSS 클래스 매핑
const classMap = {
  PENDING: 'badge-pending',
  RUNNING: 'badge-running',
  DONE: 'badge-done',
  FAILED: 'badge-failed',
  CANCELLED: 'badge-cancelled',
}

// 현재 status에 맞는 라벨 계산
const label = computed(() => labelMap[props.status] ?? props.status)
// 현재 status에 맞는 CSS 클래스 계산
const badgeClass = computed(() => classMap[props.status] ?? '')
</script>

<template>
  <span class="status-badge" :class="badgeClass">{{ label }}</span>
</template>

<style scoped>
/* 상태 배지 기본 스타일 */
.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

/* PENDING — 회색 */
.badge-pending {
  background: #e8e8e8;
  color: #666;
}

/* RUNNING — 파란색 */
.badge-running {
  background: #dbeafe;
  color: #1d4ed8;
}

/* DONE — 초록색 */
.badge-done {
  background: #dcfce7;
  color: #166534;
}

/* FAILED — 빨간색 */
.badge-failed {
  background: #fee2e2;
  color: #991b1b;
}

/* CANCELLED — 주황색 */
.badge-cancelled {
  background: #ffedd5;
  color: #9a3412;
}
</style>
