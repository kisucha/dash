<!-- StageTimeline.vue — F001 파이프라인 6단계 세로 타임라인 컴포넌트 -->
<!-- 각 스테이지의 상태(아이콘/뱃지), 완료 시각, 재시도/반송 버튼을 세로 스텝 라인으로 표시 -->
<script setup>
import { computed } from 'vue'

// ── Props ──
// stages: 스테이지 객체 배열 (stage_id, status, started_at, completed_at 등 포함)
// activeStageId: 현재 선택된 스테이지 ID (ResultViewer 연동용)
const props = defineProps({
  stages: {
    type: Array,
    default: () => [],
  },
  activeStageId: {
    type: String,
    default: null,
  },
})

// ── Emits ──
const emit = defineEmits(['stage-click', 'retry', 'reject'])

// ── 스테이지 ID → 한국어 이름 맵 ──
const stageNameMap = {
  STAGE_01_RESEARCH: '주제 발굴',
  STAGE_02_SCRIPT: '스크립트',
  STAGE_03_TTS: 'TTS',
  STAGE_04_VIDEO_GEN: '영상 생성',
  STAGE_05_EDIT: '영상 편집',
  STAGE_06_UPLOAD: 'SEO/업로드',
}

// ── 스테이지 상태 → 아이콘 맵 ──
const statusIconMap = {
  PENDING: '○',
  RUNNING: '⟳',
  DONE: '✓',
  FAILED: '✗',
  SKIPPED: '↷',
  REJECTED: '↩',
  PENDING_APPROVAL: '⏳',
}

// ── 스테이지 상태 → CSS 클래스 맵 ──
const statusClassMap = {
  PENDING: 'status-pending',
  RUNNING: 'status-running',
  DONE: 'status-done',
  FAILED: 'status-failed',
  SKIPPED: 'status-skipped',
  REJECTED: 'status-rejected',
  PENDING_APPROVAL: 'status-approval',
}

// ── 스테이지 상태 → 뱃지 텍스트 맵 ──
const statusLabelMap = {
  PENDING: '대기',
  RUNNING: '진행 중',
  DONE: '완료',
  FAILED: '실패',
  SKIPPED: '건너뜀',
  REJECTED: '반송됨',
  PENDING_APPROVAL: '승인 대기',
}

// 정렬된 스테이지 목록 — stage_id 알파벳순 정렬로 STAGE_01~06 순서 보장
const sortedStages = computed(() =>
  [...props.stages].sort((a, b) => a.stage_id.localeCompare(b.stage_id))
)

// 스테이지 이름 조회
function getStageName(stageId) {
  return stageNameMap[stageId] ?? stageId
}

// 상태 아이콘 조회
function getStatusIcon(status) {
  return statusIconMap[status] ?? '?'
}

// 상태 CSS 클래스 조회
function getStatusClass(status) {
  return statusClassMap[status] ?? ''
}

// 상태 뱃지 텍스트 조회
function getStatusLabel(status) {
  return statusLabelMap[status] ?? status
}

// 날짜 포맷 — 완료/시작 시각 표시용
function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// 재시도 가능한 상태인지 — FAILED 또는 REJECTED 상태만 재시도 가능
function canRetry(status) {
  return status === 'FAILED' || status === 'REJECTED'
}

// 스테이지 행 클릭 핸들러
function handleStageClick(stage) {
  emit('stage-click', stage)
}

// 재시도 버튼 클릭 핸들러
function handleRetry(stageId, event) {
  event.stopPropagation()
  emit('retry', stageId)
}

// 반송 버튼 클릭 핸들러 — DONE/PENDING_APPROVAL 상태인 스테이지에서 반송 가능
function handleReject(stageId, event) {
  event.stopPropagation()
  emit('reject', stageId)
}

// 반송 버튼을 표시할 상태인지 — DONE 또는 PENDING_APPROVAL만 반송 가능
function canReject(status) {
  return status === 'DONE' || status === 'PENDING_APPROVAL'
}
</script>

<template>
  <div class="stage-timeline">
    <div
      v-for="(stage, index) in sortedStages"
      :key="stage.stage_id"
      class="stage-row"
      :class="[getStatusClass(stage.status), { 'stage-active': activeStageId === stage.stage_id }]"
      @click="handleStageClick(stage)"
    >
      <!-- 세로 스텝 라인 영역 -->
      <div class="step-line-col">
        <!-- 상태 아이콘 원형 배지 -->
        <div class="step-icon" :class="getStatusClass(stage.status)">
          <span :class="{ 'icon-spin': stage.status === 'RUNNING' }">
            {{ getStatusIcon(stage.status) }}
          </span>
        </div>
        <!-- 마지막 스테이지가 아닌 경우 세로 연결선 표시 -->
        <div v-if="index < sortedStages.length - 1" class="step-connector"></div>
      </div>

      <!-- 스테이지 정보 영역 -->
      <div class="stage-info">
        <div class="stage-header">
          <!-- 스테이지 번호 + 이름 -->
          <span class="stage-name">{{ getStageName(stage.stage_id) }}</span>
          <!-- 상태 뱃지 -->
          <span class="stage-badge" :class="getStatusClass(stage.status)">
            {{ getStatusLabel(stage.status) }}
          </span>
        </div>

        <!-- RUNNING: 진행 중 표시 -->
        <div v-if="stage.status === 'RUNNING'" class="stage-meta running-text">
          진행 중...
        </div>

        <!-- DONE: 완료 시각 -->
        <div v-else-if="stage.status === 'DONE' && stage.completed_at" class="stage-meta">
          완료: {{ formatTime(stage.completed_at) }}
        </div>

        <!-- SKIPPED: 건너뜀 안내 -->
        <div v-else-if="stage.status === 'SKIPPED'" class="stage-meta skipped-text">
          건너뜀 (설정에 의해 생략)
        </div>

        <!-- FAILED: 오류 메시지 + 재시도 버튼 -->
        <div v-else-if="stage.status === 'FAILED'" class="stage-meta failed-text">
          <span v-if="stage.error_message" class="error-msg">{{ stage.error_message }}</span>
        </div>

        <!-- REJECTED: 반송 사유 -->
        <div v-else-if="stage.status === 'REJECTED'" class="stage-meta rejected-text">
          <span v-if="stage.rejection_reason" class="rejection-msg">반송 사유: {{ stage.rejection_reason }}</span>
        </div>

        <!-- PENDING_APPROVAL: 승인 대기 안내 -->
        <div v-else-if="stage.status === 'PENDING_APPROVAL'" class="stage-meta approval-text">
          승인 대기 중 — 결과를 확인하고 승인하세요
        </div>

        <!-- 액션 버튼 영역 -->
        <div class="stage-actions" @click.stop>
          <!-- 재시도 버튼 — FAILED/REJECTED 상태 -->
          <button
            v-if="canRetry(stage.status)"
            class="btn-retry"
            @click="handleRetry(stage.stage_id, $event)"
          >
            재시도
          </button>
          <!-- 반송 버튼 — DONE/PENDING_APPROVAL 상태 -->
          <button
            v-if="canReject(stage.status)"
            class="btn-reject"
            @click="handleReject(stage.stage_id, $event)"
          >
            반송
          </button>
        </div>
      </div>
    </div>

    <!-- 스테이지 없음 -->
    <div v-if="sortedStages.length === 0" class="empty-stages">
      스테이지 정보가 없습니다.
    </div>
  </div>
</template>

<style scoped>
/* 타임라인 래퍼 */
.stage-timeline {
  display: flex;
  flex-direction: column;
  padding: 4px 0;
}

/* ── 스테이지 행 ── */
.stage-row {
  display: flex;
  gap: 14px;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 8px;
  transition: background 0.12s;
  min-height: 56px;
}

.stage-row:hover {
  background: #f5f9ff;
}

/* 활성(선택) 스테이지 행 강조 */
.stage-row.stage-active {
  background: #e8f0fe;
  border-left: 3px solid #4a90d9;
  padding-left: 5px;
}

/* ── 세로 라인 컬럼 ── */
.step-line-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 32px;
}

/* 상태 아이콘 원형 */
.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
  border: 2px solid #e0e0e0;
  background: #fff;
  color: #aaa;
  z-index: 1;
}

/* 세로 연결선 */
.step-connector {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: #e0e0e0;
  margin: 2px 0;
}

/* ── 스테이지 정보 영역 ── */
.stage-info {
  flex: 1;
  padding-top: 4px;
}

.stage-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.stage-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

/* 상태 뱃지 */
.stage-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

/* 메타 텍스트 (시각, 오류 메시지 등) */
.stage-meta {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
  line-height: 1.4;
}

/* ── 상태별 색상 ── */

/* PENDING */
.status-pending .step-icon {
  border-color: #d1d5db;
  color: #9ca3af;
}
.stage-badge.status-pending {
  background: #f3f4f6;
  color: #6b7280;
}

/* RUNNING — 파란색 + 아이콘 회전 */
.step-icon.status-running {
  border-color: #3b82f6;
  background: #eff6ff;
  color: #3b82f6;
}
.stage-row.status-running .stage-name { color: #1d4ed8; }
.stage-badge.status-running {
  background: #dbeafe;
  color: #1d4ed8;
}
.running-text { color: #3b82f6; font-weight: 500; }

/* DONE — 초록색 */
.step-icon.status-done {
  border-color: #16a34a;
  background: #f0fdf4;
  color: #16a34a;
}
.stage-row.status-done .stage-name { color: #166534; }
.stage-badge.status-done {
  background: #dcfce7;
  color: #166534;
}
/* DONE 행의 연결선도 초록색으로 */
.stage-row.status-done .step-connector { background: #86efac; }

/* FAILED — 빨간색 */
.step-icon.status-failed {
  border-color: #ef4444;
  background: #fef2f2;
  color: #ef4444;
}
.stage-row.status-failed .stage-name { color: #991b1b; }
.stage-badge.status-failed {
  background: #fee2e2;
  color: #991b1b;
}
.failed-text { color: #ef4444; }
.error-msg {
  display: block;
  font-size: 11px;
  color: #dc2626;
  background: #fff5f5;
  padding: 4px 8px;
  border-radius: 4px;
  border-left: 2px solid #ef4444;
  margin-top: 2px;
  word-break: break-all;
}

/* REJECTED — 주황색 */
.step-icon.status-rejected {
  border-color: #f59e0b;
  background: #fffbeb;
  color: #f59e0b;
}
.stage-badge.status-rejected {
  background: #fef3c7;
  color: #92400e;
}
.rejected-text { color: #b45309; }
.rejection-msg {
  font-size: 11px;
  color: #92400e;
}

/* SKIPPED — 회색 */
.step-icon.status-skipped {
  border-color: #d1d5db;
  background: #f9fafb;
  color: #9ca3af;
}
.stage-badge.status-skipped {
  background: #f3f4f6;
  color: #6b7280;
}
.skipped-text { color: #9ca3af; font-style: italic; }

/* PENDING_APPROVAL — 보라색 */
.step-icon.status-approval {
  border-color: #8b5cf6;
  background: #faf5ff;
  color: #8b5cf6;
}
.stage-row.status-approval .stage-name { color: #6d28d9; }
.stage-badge.status-approval {
  background: #ede9fe;
  color: #6d28d9;
}
.approval-text { color: #7c3aed; font-weight: 500; }

/* ── 아이콘 회전 애니메이션 (RUNNING) ── */
.icon-spin {
  display: inline-block;
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── 액션 버튼 ── */
.stage-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.btn-retry {
  font-size: 12px;
  padding: 3px 10px;
  background: #ef4444;
  color: #fff;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.12s;
}
.btn-retry:hover { background: #dc2626; }

.btn-reject {
  font-size: 12px;
  padding: 3px 10px;
  background: #fff;
  color: #f59e0b;
  border: 1px solid #f59e0b;
  border-radius: 5px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.12s;
}
.btn-reject:hover {
  background: #fffbeb;
  border-color: #d97706;
}

/* ── 빈 상태 ── */
.empty-stages {
  font-size: 13px;
  color: #aaa;
  text-align: center;
  padding: 16px 0;
}
</style>
