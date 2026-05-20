<!-- F007JobDetailView.vue — F007 작업 상세 페이지 -->
<!-- StageTimeline + StageResultViewer 2패널 레이아웃 -->
<!-- RUNNING/PENDING 상태 시 5초 폴링, PENDING_APPROVAL 상태 배너 + 승인 버튼(백엔드 연동 예정) -->
<!-- F007 6단계: STAGE_01_TOPIC ~ STAGE_06_UPLOAD, 스테이지 이름 한국어 매핑 -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useF007Store } from '../store/f007.js'
import StageResultViewer from '../components/StageResultViewer.vue'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const f007Store = useF007Store()

// ── route.params에서 jobId 추출 ──
const jobId = computed(() => route.params.jobId)

// ── 선택된 스테이지 (ResultViewer에 전달) ──
const selectedStage = ref(null)

// ── 현재 작업 편의 참조 ──
const job = computed(() => f007Store.currentJob)

// ── F007 스테이지 순서 및 이름 한국어 매핑 ──
const STAGE_KEYS = [
  'STAGE_01_TOPIC',
  'STAGE_02_SCRIPT',
  'STAGE_03_TTS',
  'STAGE_04_VISUAL',
  'STAGE_05_VIDEO',
  'STAGE_06_UPLOAD',
]

const stageNameMap = {
  STAGE_01_TOPIC: '01. 주제 발굴',
  STAGE_02_SCRIPT: '02. 스크립트 생성',
  STAGE_03_TTS: '03. TTS 합성',
  STAGE_04_VISUAL: '04. 슬라이드 생성',
  STAGE_05_VIDEO: '05. 영상 합성',
  STAGE_06_UPLOAD: '06. 업로드',
}

// ── 선택된 스테이지 한국어 이름 ──
const selectedStageLabel = computed(() => {
  if (!selectedStage.value) return '결과'
  return stageNameMap[selectedStage.value.stage_id] ?? selectedStage.value.stage_id
})

// ── PENDING_APPROVAL 배너 표시 조건 ──
const approvalStage = computed(() => {
  if (!job.value?.stages) return null
  const byStage = job.value.stages.find(s => s.status === 'PENDING_APPROVAL')
  if (byStage) return byStage
  if (job.value.status === 'PENDING_APPROVAL') {
    return job.value.stages.find(s => s.stage_id === 'STAGE_06_UPLOAD') ?? null
  }
  return null
})

// ── 채널 유형 레이블 ──
const channelTypeLabel = computed(() => {
  const type = job.value?.channel_type
  if (type === 'finance') return '금융/경제'
  if (type === 'language') return '언어학습'
  return type ?? ''
})

// ── 채널 유형 태그 클래스 ──
const channelTypeClass = computed(() => {
  const type = job.value?.channel_type
  if (type === 'finance') return 'finance'
  if (type === 'language') return 'language'
  return ''
})

// ── 작업 상태가 폴링 대상인지 확인 (PENDING/RUNNING/WAITING) ──
const isRunning = computed(() =>
  ['PENDING', 'RUNNING', 'WAITING'].includes(job.value?.status)
)

// ── 날짜 포맷 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── 스테이지 객체 조회 헬퍼 ──
function getStageObj(stageKey) {
  return job.value?.stages?.find(s => s.stage_id === stageKey) ?? null
}

// ── 스테이지 아이템 클래스 ──
function getStageItemClass(stageKey) {
  const stage = getStageObj(stageKey)
  const isSelected = selectedStage.value?.stage_id === stageKey
  return {
    selected: isSelected,
    clickable: !!stage,
  }
}

// ── 스테이지 상태 도트 클래스 ──
function getStageStatusDotClass(stageKey) {
  const stage = getStageObj(stageKey)
  if (!stage) return 'dot-pending'
  const s = stage.status
  if (s === 'DONE') return 'dot-done'
  if (s === 'RUNNING') return 'dot-running'
  if (s === 'FAILED') return 'dot-failed'
  if (s === 'PENDING_APPROVAL') return 'dot-approval'
  if (s === 'WAITING') return 'dot-waiting'
  return 'dot-pending'
}

// ── 스테이지 상태 텍스트 ──
function getStageStatusText(stageKey) {
  const stage = getStageObj(stageKey)
  if (!stage) return '대기'
  const map = {
    PENDING: '대기',
    RUNNING: '실행 중',
    DONE: '완료',
    FAILED: '실패',
    PENDING_APPROVAL: '승인 대기',
    WAITING: '일시 정지',
    CANCELLED: '취소',
  }
  return map[stage.status] ?? stage.status
}

// ── 스테이지 상태 레이블 클래스 ──
function getStageStatusLabelClass(stageKey) {
  const stage = getStageObj(stageKey)
  if (!stage) return 'label-pending'
  const s = stage.status
  if (s === 'DONE') return 'label-done'
  if (s === 'RUNNING') return 'label-running'
  if (s === 'FAILED') return 'label-failed'
  if (s === 'PENDING_APPROVAL') return 'label-approval'
  if (s === 'WAITING') return 'label-waiting'
  return 'label-pending'
}

// ── 스테이지 아이템 클릭 ──
function onStageItemClick(stageKey) {
  const stage = getStageObj(stageKey)
  if (stage) selectedStage.value = stage
}

// ── 폴링 설정 — 5초 간격 ──
let pollTimer = null

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (!isRunning.value) {
      stopPolling()
      return
    }
    await f007Store.fetchJob(jobId.value)
    // 선택된 스테이지 정보도 폴링 결과로 갱신
    if (selectedStage.value && job.value?.stages) {
      const updated = job.value.stages.find(s => s.stage_id === selectedStage.value.stage_id)
      if (updated) selectedStage.value = updated
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── isRunning 변경 감지 → 자동 폴링 시작/정지 ──
watch(isRunning, (val) => {
  if (val) startPolling()
  else stopPolling()
})

// ── 마운트: 작업 상세 로드 → 첫 번째 스테이지 선택 → 필요 시 폴링 시작 ──
onMounted(async () => {
  await f007Store.fetchJob(jobId.value)
  if (job.value?.stages?.length > 0) {
    // stage_id 오름차순 정렬 후 첫 번째 스테이지를 기본 선택
    const sorted = [...job.value.stages].sort((a, b) => a.stage_id.localeCompare(b.stage_id))
    selectedStage.value = sorted[0]
  }
  if (isRunning.value) {
    startPolling()
  }
})

// ── 언마운트: 폴링 정리 ──
onUnmounted(() => stopPolling())
</script>

<template>
  <div class="job-detail-view">

    <!-- ── 로딩 중 ── -->
    <div v-if="f007Store.loading && !job" class="loading-text">로딩 중...</div>

    <!-- ── 작업 없음 / 오류 ── -->
    <div v-else-if="!job" class="error-box">
      작업을 찾을 수 없습니다.
      <button class="back-btn-inline" @click="router.push({ name: 'F007' })">목록으로</button>
    </div>

    <template v-else>

      <!-- ── 페이지 헤더 ── -->
      <div class="page-header">
        <button class="back-btn" @click="router.push({ name: 'F007' })">F007 목록</button>
        <div class="header-main">
          <h1 class="page-title">
            작업 #{{ job.id }}
            <span
              v-if="job.channel_type"
              class="channel-type-tag"
              :class="channelTypeClass"
            >{{ channelTypeLabel }}</span>
          </h1>
          <StatusBadge :status="job.status" />
        </div>
        <p class="header-meta">생성: {{ formatDate(job.created_at) }}</p>
      </div>

      <!-- ── PENDING_APPROVAL 배너 ── -->
      <div v-if="approvalStage" class="approval-banner">
        <span class="approval-icon">!</span>
        <span class="approval-text">업로드 승인 대기 중입니다. 검토 후 승인 버튼을 클릭하세요.</span>
        <button
          class="btn-go-approval"
          @click="selectedStage = approvalStage"
        >
          승인 화면으로
        </button>
        <!-- 승인 버튼 — 백엔드 연동 예정, 현재 disabled -->
        <button
          class="btn-approve"
          disabled
          title="백엔드 연동 예정"
        >
          승인하기 (준비 중)
        </button>
      </div>

      <!-- ── 2패널 레이아웃 ── -->
      <div class="two-panel">

        <!-- 왼쪽: F007 스테이지 목록 -->
        <div class="panel-left">
          <div class="panel-header">
            <h2 class="panel-title">파이프라인 단계</h2>
            <span v-if="isRunning" class="polling-badge">업데이트 중</span>
          </div>

          <div class="stage-list">
            <div
              v-for="stageKey in STAGE_KEYS"
              :key="stageKey"
              class="stage-item"
              :class="getStageItemClass(stageKey)"
              @click="onStageItemClick(stageKey)"
            >
              <span class="stage-status-dot" :class="getStageStatusDotClass(stageKey)"></span>
              <span class="stage-name">{{ stageNameMap[stageKey] }}</span>
              <span class="stage-status-label" :class="getStageStatusLabelClass(stageKey)">
                {{ getStageStatusText(stageKey) }}
              </span>
            </div>
          </div>
        </div>

        <!-- 오른쪽: 결과 뷰어 -->
        <div class="panel-right">
          <div class="panel-header">
            <h2 class="panel-title">{{ selectedStageLabel }}</h2>
          </div>
          <StageResultViewer
            :stage="selectedStage"
            :job-id="jobId"
          />
        </div>

      </div>

    </template>

  </div>
</template>

<style scoped>
/* 페이지 래퍼 */
.job-detail-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 로딩/오류 ── */
.loading-text {
  font-size: 14px;
  color: #888;
  text-align: center;
  padding: 40px 0;
}

.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 14px 18px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn-inline {
  font-size: 13px;
  padding: 4px 12px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

/* ── 페이지 헤더 ── */
.page-header { margin-bottom: 4px; }

.back-btn {
  background: none;
  border: none;
  color: #7c3aed;
  font-size: 14px;
  cursor: pointer;
  padding: 0;
  margin-bottom: 10px;
  display: inline-block;
}
.back-btn:hover { text-decoration: underline; }

.header-main {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #222;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 채널 유형 태그 ── */
.channel-type-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  display: inline-block;
}
.channel-type-tag.finance { background: #fee2e2; color: #991b1b; }
.channel-type-tag.language { background: #dbeafe; color: #1e40af; }

.header-meta {
  font-size: 12px;
  color: #999;
  margin: 0;
}

/* ── PENDING_APPROVAL 배너 ── */
.approval-banner {
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #92400e;
  flex-wrap: wrap;
}

.approval-icon {
  font-size: 12px;
  font-weight: 900;
  color: #d97706;
  width: 22px;
  height: 22px;
  border: 2px solid #d97706;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.approval-text { flex: 1; font-weight: 500; min-width: 200px; }

.btn-go-approval {
  font-size: 13px;
  padding: 5px 14px;
  background: #d97706;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.12s;
  flex-shrink: 0;
}
.btn-go-approval:hover { background: #b45309; }

/* 승인하기 버튼 — 백엔드 연동 예정 (disabled) */
.btn-approve {
  font-size: 13px;
  padding: 5px 14px;
  background: #f5f5f5;
  color: #aaa;
  border: 1.5px solid #ddd;
  border-radius: 6px;
  cursor: not-allowed;
  font-weight: 600;
  flex-shrink: 0;
}

/* ── 폴링 배지 ── */
.polling-badge {
  font-size: 11px;
  font-weight: 600;
  background: #ede9fe;
  color: #6d28d9;
  padding: 2px 8px;
  border-radius: 10px;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ── 2패널 레이아웃 ── */
.two-panel {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  align-items: start;
}

/* 왼쪽 패널 */
.panel-left {
  background: #fff;
  border-radius: 10px;
  padding: 16px 18px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 16px;
}

/* 오른쪽 패널 */
.panel-right {
  background: #fff;
  border-radius: 10px;
  padding: 16px 18px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  min-height: 400px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #444;
  margin: 0;
}

/* ── F007 스테이지 목록 ── */
.stage-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 7px;
  cursor: default;
  transition: background 0.12s;
  border: 1.5px solid transparent;
}

.stage-item.clickable {
  cursor: pointer;
}
.stage-item.clickable:hover {
  background: #faf5ff;
  border-color: #c4b5fd;
}
.stage-item.selected {
  background: #faf5ff;
  border-color: #7c3aed;
}

/* 상태 도트 */
.stage-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-pending { background: #d1d5db; }
.dot-done { background: #10b981; }
.dot-running {
  background: #3b82f6;
  animation: pulse-dot 1.5s infinite;
}
.dot-failed { background: #ef4444; }
.dot-approval { background: #f59e0b; }
.dot-waiting { background: #f97316; }

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* 스테이지 이름 */
.stage-name {
  flex: 1;
  font-size: 13px;
  color: #333;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 상태 레이블 */
.stage-status-label {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 8px;
  flex-shrink: 0;
  white-space: nowrap;
}
.label-pending { background: #f3f4f6; color: #9ca3af; }
.label-done { background: #d1fae5; color: #065f46; }
.label-running { background: #dbeafe; color: #1e40af; }
.label-failed { background: #fee2e2; color: #991b1b; }
.label-approval { background: #fef3c7; color: #92400e; }
.label-waiting { background: #fed7aa; color: #9a3412; }
</style>
