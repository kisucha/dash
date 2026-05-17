<!-- F006JobDetailView.vue — F006 작업 상세 페이지 -->
<!-- StageTimeline + StageResultViewer 2패널 레이아웃 -->
<!-- RUNNING 상태일 때 2초 폴링, PENDING_APPROVAL 상태 배너, 승인/재생성 처리 -->
<!-- F004 대비 차이: handleSelectTopic 없음 (F006는 주제 선택 단계 없음) -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useF006Store } from '../store/f006.js'
import StageTimeline from '../components/StageTimeline.vue'
import StageResultViewer from '../components/StageResultViewer.vue'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const f006Store = useF006Store()

// ── route.params에서 jobId 추출 ──
const jobId = computed(() => route.params.jobId)

// ── 선택된 스테이지 (ResultViewer에 전달) ──
const selectedStage = ref(null)

// ── 반송 모달 상태 ──
const showRejectModal = ref(false)
const rejectTargetStageId = ref('')
const rejectReason = ref('')
const rejectError = ref('')

// ── 현재 작업 편의 참조 ──
const job = computed(() => f006Store.currentJob)

// ── PENDING_APPROVAL 배너 표시 조건 ──
// stages에 PENDING_APPROVAL 행이 있거나, job 자체가 PENDING_APPROVAL이면 STAGE_06 가리킴
const approvalStage = computed(() => {
  if (!job.value?.stages) return null
  const byStage = job.value.stages.find(s => s.status === 'PENDING_APPROVAL')
  if (byStage) return byStage
  // 이미 완료된 job에서 stages.status가 DONE이어도 job.status로 fallback
  if (job.value.status === 'PENDING_APPROVAL') {
    return job.value.stages.find(s => s.stage_id === 'STAGE_06_UPLOAD') ?? null
  }
  return null
})

// ── 작업 상태가 RUNNING인지 확인 (폴링 조건: RUNNING + WAITING 모두 폴링) ──
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

// ── 스테이지 클릭 — ResultViewer 패널 업데이트 ──
function handleStageClick(stage) {
  selectedStage.value = stage
}

// ── 스테이지 재시도 핸들러 ──
async function handleRetry(stageId) {
  if (!confirm(`스테이지 ${stageId}를 재시도하시겠습니까?`)) return
  try {
    await f006Store.retryStage(jobId.value, stageId)
  } catch {
    alert('재시도 요청에 실패했습니다.')
  }
}

// ── 반송 모달 열기 ──
function openRejectModal(stageId) {
  rejectTargetStageId.value = stageId
  rejectReason.value = ''
  rejectError.value = ''
  showRejectModal.value = true
}

// ── 반송 확인 제출 ──
async function submitReject() {
  if (!rejectReason.value.trim()) {
    rejectError.value = '반송 사유를 입력하세요.'
    return
  }
  try {
    await f006Store.rejectStage(jobId.value, rejectTargetStageId.value, rejectReason.value.trim())
    showRejectModal.value = false
    // 반송 후 선택된 스테이지 갱신
    if (selectedStage.value?.stage_id === rejectTargetStageId.value) {
      const updated = job.value?.stages?.find(s => s.stage_id === rejectTargetStageId.value)
      if (updated) selectedStage.value = updated
    }
  } catch {
    rejectError.value = '반송 요청에 실패했습니다.'
  }
}

// ── 승인 이벤트 처리 (StageResultViewer emit) ──
async function handleApprove(finalMeta) {
  if (!confirm('이 SEO 메타데이터로 YouTube에 업로드하시겠습니까?')) return
  try {
    await f006Store.approveJob(jobId.value, finalMeta)
    // 승인 후 STAGE_06 ResultViewer 갱신
    const updated = job.value?.stages?.find(s => s.stage_id === 'STAGE_06_UPLOAD')
    if (updated) selectedStage.value = updated
  } catch {
    alert('승인 요청에 실패했습니다.')
  }
}

// ── 스크립트 수정 후 TTS부터 재생성 이벤트 처리 (StageResultViewer emit) ──
async function handleRerunFromTTS({ scriptText, slides }) {
  if (!scriptText?.trim()) {
    alert('스크립트를 입력해 주세요.')
    return
  }
  if (!confirm('수정된 스크립트로 TTS부터 재생성하시겠습니까?\nSTAGE_03~06이 초기화되고 다시 실행됩니다.')) return
  try {
    await f006Store.rerunFromTTS(jobId.value, scriptText, slides)
    // 재생성 시작 후 STAGE_03 선택
    const s03 = job.value?.stages?.find(s => s.stage_id === 'STAGE_03_TTS')
    if (s03) selectedStage.value = s03
  } catch {
    alert('재생성 요청에 실패했습니다.')
  }
}

// ── 폴링 설정 ──
// RUNNING 상태일 때만 2초마다 fetchJob 호출
let pollTimer = null

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (!isRunning.value) {
      stopPolling()
      return
    }
    await f006Store.fetchJob(jobId.value)
    // 선택된 스테이지 정보도 폴링 결과로 갱신
    if (selectedStage.value && job.value?.stages) {
      const updated = job.value.stages.find(s => s.stage_id === selectedStage.value.stage_id)
      if (updated) selectedStage.value = updated
    }
  }, 2000)
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

// ── 마운트: 작업 상세 로드 → RUNNING이면 폴링 시작 ──
onMounted(async () => {
  await f006Store.fetchJob(jobId.value)
  // 첫 번째 스테이지를 기본 선택
  if (job.value?.stages?.length > 0) {
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
    <div v-if="f006Store.loading && !job" class="loading-text">로딩 중...</div>

    <!-- ── 작업 없음 / 오류 ── -->
    <div v-else-if="!job" class="error-box">
      작업을 찾을 수 없습니다.
      <button class="back-btn-inline" @click="router.push({ name: 'F006Feature' })">목록으로</button>
    </div>

    <template v-else>

      <!-- ── 페이지 헤더 ── -->
      <div class="page-header">
        <button class="back-btn" @click="router.push({ name: 'F006Feature' })">← F006 목록</button>
        <div class="header-main">
          <h1 class="page-title">
            작업 #{{ job.id }}
            <span v-if="job.channel_category" class="category-label">({{ job.channel_category }})</span>
          </h1>
          <StatusBadge :status="job.status" />
        </div>
        <p class="header-meta">생성: {{ formatDate(job.created_at) }}</p>
      </div>

      <!-- ── PENDING_APPROVAL 배너 ── -->
      <div v-if="approvalStage" class="approval-banner">
        <span class="approval-icon">⏳</span>
        <span class="approval-text">SEO 메타데이터 검토 후 승인이 필요합니다.</span>
        <button
          class="btn-go-approval"
          @click="selectedStage = approvalStage"
        >
          승인 화면으로 이동
        </button>
      </div>

      <!-- ── 2패널 레이아웃 ── -->
      <div class="two-panel">

        <!-- 왼쪽: 스테이지 타임라인 -->
        <div class="panel-left">
          <div class="panel-header">
            <h2 class="panel-title">파이프라인 단계</h2>
            <!-- RUNNING 표시 -->
            <span v-if="isRunning" class="polling-badge">실시간 업데이트 중</span>
          </div>
          <StageTimeline
            :stages="job.stages ?? []"
            :active-stage-id="selectedStage?.stage_id ?? null"
            @stage-click="handleStageClick"
            @retry="handleRetry"
            @reject="openRejectModal"
          />
        </div>

        <!-- 오른쪽: 결과 뷰어 -->
        <div class="panel-right">
          <div class="panel-header">
            <h2 class="panel-title">
              {{ selectedStage ? selectedStage.stage_id : '결과' }}
            </h2>
          </div>
          <StageResultViewer
            :stage="selectedStage"
            :job-id="jobId"
            @approve="handleApprove"
            @rerun-from-tts="handleRerunFromTTS"
          />
        </div>

      </div>

    </template>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 반송 사유 입력 모달                              -->
    <!-- ══════════════════════════════════════════════ -->
    <div v-if="showRejectModal" class="modal-overlay" @click.self="showRejectModal = false">
      <div class="reject-modal">
        <div class="modal-header">
          <h3 class="modal-title">스테이지 반송</h3>
          <button class="modal-close" @click="showRejectModal = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="reject-target-label">대상: <strong>{{ rejectTargetStageId }}</strong></p>
          <div class="form-item">
            <label class="form-label">반송 사유 <span class="required-mark">*</span></label>
            <textarea
              v-model="rejectReason"
              class="reject-textarea"
              rows="3"
              placeholder="반송 이유를 입력하세요..."
            ></textarea>
          </div>
          <div v-if="rejectError" class="form-error">{{ rejectError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showRejectModal = false">취소</button>
          <button class="btn-confirm-reject" @click="submitReject">반송 확인</button>
        </div>
      </div>
    </div>

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
  color: #059669;
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
}

.category-label {
  font-size: 16px;
  font-weight: 500;
  color: #666;
}

.header-meta {
  font-size: 12px;
  color: #999;
  margin: 0;
}

/* ── PENDING_APPROVAL 배너 ── */
.approval-banner {
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #065f46;
}

.approval-icon { font-size: 18px; }
.approval-text { flex: 1; font-weight: 500; }

.btn-go-approval {
  font-size: 13px;
  padding: 5px 14px;
  background: #059669;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.12s;
}
.btn-go-approval:hover { background: #047857; }

/* ── 폴링 배지 ── */
.polling-badge {
  font-size: 11px;
  font-weight: 600;
  background: #d1fae5;
  color: #047857;
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
  grid-template-columns: 300px 1fr;
  gap: 16px;
  align-items: start;
}

/* 왼쪽 패널 — 타임라인 */
.panel-left {
  background: #fff;
  border-radius: 10px;
  padding: 16px 18px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 16px;
}

/* 오른쪽 패널 — 결과 뷰어 */
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

/* ══════════════════════════════════════════════ */
/* ── 반송 모달 ──                                 */
/* ══════════════════════════════════════════════ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.reject-modal {
  background: #fff;
  border-radius: 10px;
  width: 440px;
  max-width: calc(100vw - 40px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.modal-title {
  font-size: 16px;
  font-weight: 700;
  color: #222;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  color: #999;
  cursor: pointer;
}
.modal-close:hover { color: #333; }

.modal-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reject-target-label {
  font-size: 13px;
  color: #666;
  margin: 0;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
}

.required-mark { color: #ef4444; }

.reject-textarea {
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  resize: vertical;
  font-family: inherit;
  background: #fff;
}

.reject-textarea:focus {
  outline: none;
  border-color: #059669;
}

.form-error {
  background: #fee2e2;
  color: #991b1b;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px 16px;
  border-top: 1px solid #f0f0f0;
}

.btn-cancel {
  background: #fff;
  border: 1.5px solid #ddd;
  color: #555;
  border-radius: 7px;
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-cancel:hover { background: #f5f5f5; }

.btn-confirm-reject {
  background: #f59e0b;
  color: #fff;
  border: none;
  border-radius: 7px;
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s;
}
.btn-confirm-reject:hover { background: #d97706; }
</style>
