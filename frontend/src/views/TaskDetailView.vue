<!-- TaskDetailView.vue — 개별 작업 상세 정보 페이지 (/tasks/:id) -->
<!-- 작업 상태, 파라미터, 결과, 오류를 표시하며 2초 간격으로 폴링한다 -->
<!-- DONE/FAILED/CANCELLED 상태 도달 시 폴링을 자동 중단한다 -->
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getTask } from '../api/index.js'
import { useTaskStore } from '../store/tasks.js'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()

// 현재 Task 객체
const task = ref(null)
// 로딩 상태
const loading = ref(true)
// 오류 메시지
const errorMsg = ref('')
// 취소 처리 중 여부
const cancelling = ref(false)

// 폴링 타이머 ID
let pollTimer = null

// 종료 상태 목록 — 이 상태에 도달하면 폴링 중단
const TERMINAL_STATUSES = ['DONE', 'FAILED', 'CANCELLED']

// ────────────────────────────────────────────────
// 작업 데이터 조회
// ────────────────────────────────────────────────

async function fetchTask() {
  try {
    const res = await getTask(route.params.id)
    task.value = res.data
    if (TERMINAL_STATUSES.includes(task.value.status)) {
      stopPolling()
    }
  } catch {
    errorMsg.value = '작업 정보를 불러올 수 없습니다.'
    stopPolling()
  }
}

// ────────────────────────────────────────────────
// 폴링 — 2초 간격으로 상태 갱신
// ────────────────────────────────────────────────

function startPolling() {
  pollTimer = setInterval(fetchTask, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ────────────────────────────────────────────────
// 작업 취소
// ────────────────────────────────────────────────

async function handleCancel() {
  if (cancelling.value) return
  cancelling.value = true
  try {
    await taskStore.cancelTask(route.params.id)
    await fetchTask()
  } catch {
    errorMsg.value = '작업 취소 중 오류가 발생했습니다.'
  } finally {
    cancelling.value = false
  }
}

// ────────────────────────────────────────────────
// 파싱 / 렌더링 유틸
// ────────────────────────────────────────────────

// JSON 문자열 또는 객체를 파싱 — 실패 시 null 반환
function tryParse(val) {
  if (val === null || val === undefined) return null
  if (typeof val === 'object') return val
  try { return JSON.parse(val) } catch { return null }
}

// **text** 마크다운을 <strong>text</strong>로 변환
function renderMd(text) {
  if (!text) return ''
  return String(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}

// 날짜 포맷
function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// 들여쓰기 JSON 문자열화 (fallback 표시용)
function formatJson(val) {
  if (val === null || val === undefined) return '-'
  try { return JSON.stringify(val, null, 2) } catch { return String(val) }
}

// 중요도 → CSS 클래스
function importanceCls(imp) {
  if (imp === '높음') return 'imp-high'
  if (imp === '중간') return 'imp-mid'
  return 'imp-low'
}

// ────────────────────────────────────────────────
// Computed
// ────────────────────────────────────────────────

// store의 features에서 이름 조회
const featureName = computed(() => {
  if (!task.value) return ''
  const f = taskStore.features.find(f => f.feature_id === task.value.feature_id)
  return f ? f.name : task.value.feature_id
})

// params 파싱 결과 (객체 또는 null)
const parsedParams = computed(() => tryParse(task.value?.params))

// result 파싱 결과 (객체 또는 null)
const parsedResult = computed(() => tryParse(task.value?.result))

// F002 이슈 목록 여부
const isF002Issues = computed(() =>
  task.value?.feature_id === 'F002' && Array.isArray(parsedResult.value?.issues)
)

// F003 미디어 결과 여부 — feature_id가 F003이고 결과에 file_name이 있을 때
const isF003Result = computed(() =>
  task.value?.feature_id === 'F003' && parsedResult.value?.file_name
)

// F003 결과가 동영상인지 여부 — generation_type으로 판별
const f003IsVideo = computed(() =>
  parsedResult.value?.generation_type === 'video'
)

// ────────────────────────────────────────────────
// 라이프사이클
// ────────────────────────────────────────────────

onMounted(async () => {
  // features가 없으면 미리 로드 (feature 이름 표시용)
  if (taskStore.features.length === 0) taskStore.fetchFeatures().catch(() => {})
  await fetchTask()
  loading.value = false
  if (task.value && !TERMINAL_STATUSES.includes(task.value.status)) {
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="task-detail">

    <!-- 로딩 중 -->
    <div v-if="loading" class="loading-text">불러오는 중...</div>

    <!-- 데이터 오류 -->
    <div v-else-if="!task" class="error-box">{{ errorMsg || '작업을 찾을 수 없습니다.' }}</div>

    <!-- 작업 상세 -->
    <template v-else>
      <!-- 페이지 헤더 -->
      <div class="page-header">
        <button class="back-btn" @click="router.back()">← 뒤로</button>
        <div class="header-row">
          <h1 class="page-title">작업 #{{ task.id }}</h1>
          <StatusBadge :status="task.status" />
        </div>
        <div class="feature-label">{{ featureName }}</div>
      </div>

      <!-- 시각 정보 카드 -->
      <div class="info-card">
        <div class="info-row">
          <span class="info-key">생성 시각</span>
          <span class="info-val">{{ formatDate(task.created_at) }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">시작 시각</span>
          <span class="info-val">{{ formatDate(task.started_at) }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">완료 시각</span>
          <span class="info-val">{{ formatDate(task.finished_at) }}</span>
        </div>
      </div>

      <!-- 파라미터 카드 -->
      <div class="detail-card">
        <h2 class="card-title">파라미터</h2>
        <!-- 파싱 성공 시: 키/값 테이블 -->
        <div v-if="parsedParams" class="param-table">
          <div v-for="(val, key) in parsedParams" :key="key" class="param-row">
            <span class="param-key">{{ key }}</span>
            <span class="param-val">{{ val }}</span>
          </div>
        </div>
        <!-- 파싱 실패 시: raw 텍스트 -->
        <pre v-else class="json-block">{{ formatJson(task.params) }}</pre>
      </div>

      <!-- 결과 카드 -->
      <div class="detail-card">
        <h2 class="card-title">결과</h2>
        <!-- 실행 전 안내 -->
        <div v-if="task.status === 'RUNNING' || task.status === 'PENDING'" class="pending-text">
          실행이 완료되면 결과가 표시됩니다.
        </div>
        <!-- F002 이슈 카드 렌더링 -->
        <template v-else-if="isF002Issues">
          <div v-if="parsedResult.date" class="result-date">{{ parsedResult.date }} 주요 이슈</div>
          <div class="issue-list">
            <div
              v-for="(issue, idx) in parsedResult.issues"
              :key="idx"
              class="issue-card"
            >
              <div class="issue-title" v-html="renderMd(issue.title)"></div>
              <div class="issue-summary">{{ issue.summary }}</div>
              <div class="issue-badges">
                <span v-if="issue.importance" class="issue-imp" :class="importanceCls(issue.importance)">
                  중요도: {{ issue.importance }}
                </span>
                <span v-if="issue.parser" class="issue-parser">
                  파싱: {{ issue.parser }}
                </span>
              </div>
            </div>
          </div>
        </template>
        <!-- F003 미디어 렌더링 — 이미지 또는 동영상 -->
        <template v-else-if="isF003Result">
          <!-- 동영상 결과 -->
          <video
            v-if="f003IsVideo"
            :src="`/results/f003/${parsedResult.file_name}`"
            controls
            class="result-media"
          ></video>
          <!-- 이미지 결과 -->
          <img
            v-else
            :src="`/results/f003/${parsedResult.file_name}`"
            alt="생성된 이미지"
            class="result-media"
          />
          <!-- 생성 메타 정보 -->
          <div class="result-meta">
            <span>생성 유형: {{ parsedResult.generation_type === 'video' ? '동영상' : '이미지' }}</span>
            <span v-if="parsedResult.art_style"> | 스타일: {{ parsedResult.art_style }}</span>
            <span v-if="parsedResult.base_model"> | 기반 모델: {{ parsedResult.base_model }}</span>
            <span v-if="parsedResult.seed"> | 시드: {{ parsedResult.seed }}</span>
          </div>
          <!-- 파일 경로 — 클릭 시 브라우저에서 직접 열기 -->
          <div class="result-file">
            파일:
            <a
              :href="`/results/f003/${parsedResult.file_name}`"
              target="_blank"
              class="result-file-link"
            >{{ parsedResult.file_name }}</a>
          </div>
          <!-- 포지티브 프롬프트 -->
          <div v-if="parsedResult.prompt_positive" class="prompt-section">
            <div class="prompt-label">포지티브 프롬프트</div>
            <div class="prompt-box">{{ parsedResult.prompt_positive }}</div>
          </div>
          <!-- 네거티브 프롬프트 (있을 때만 표시) -->
          <div v-if="parsedResult.prompt_negative" class="prompt-section">
            <div class="prompt-label">네거티브 프롬프트</div>
            <div class="prompt-box">{{ parsedResult.prompt_negative }}</div>
          </div>
        </template>
        <!-- 그 외: 들여쓰기 JSON -->
        <pre v-else class="json-block">{{ formatJson(task.result) }}</pre>
      </div>

      <!-- 오류 메시지 카드 (FAILED 상태일 때만) -->
      <div v-if="task.status === 'FAILED' && task.error_message" class="error-card">
        <h2 class="card-title">오류 내용</h2>
        <p class="error-text">{{ task.error_message }}</p>
      </div>

      <!-- API 오류 메시지 -->
      <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>

      <!-- 취소 버튼 — RUNNING 상태일 때만 표시 -->
      <div v-if="task.status === 'RUNNING'" class="action-row">
        <button class="cancel-btn" :disabled="cancelling" @click="handleCancel">
          {{ cancelling ? '취소 중...' : '작업 취소' }}
        </button>
      </div>
    </template>

  </div>
</template>

<style scoped>
/* 페이지 래퍼 */
.task-detail {
  max-width: 700px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 로딩/오류 텍스트 */
.loading-text {
  color: #999;
  font-size: 14px;
  padding: 20px 0;
}

.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 14px 18px;
  font-size: 14px;
}

/* ── 페이지 헤더 ── */
.page-header {
  margin-bottom: 4px;
}

.back-btn {
  background: none;
  border: none;
  color: #4a90d9;
  font-size: 14px;
  cursor: pointer;
  padding: 0;
  margin-bottom: 10px;
  display: inline-block;
}

.back-btn:hover { text-decoration: underline; }

/* 제목과 배지를 나란히 배치 */
.header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #222;
  margin: 0;
}

/* Feature ID 표시 */
.feature-label {
  font-size: 14px;
  color: #888;
}

/* ── 정보 카드 ── */
.info-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 키-값 한 행 */
.info-row {
  display: flex;
  gap: 16px;
  font-size: 13px;
}

.info-key {
  color: #888;
  width: 90px;
  flex-shrink: 0;
}

.info-val {
  color: #333;
  font-weight: 500;
}

/* ── 상세 카드 (파라미터/결과) ── */
.detail-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #444;
  margin: 0 0 12px;
}

/* JSON 코드 블록 */
.json-block {
  background: #f8f8f8;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #333;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

/* 실행 중/대기 중 안내 텍스트 */
.pending-text {
  font-size: 13px;
  color: #aaa;
}

/* ── 오류 카드 ── */
.error-card {
  background: #fff5f5;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 18px 20px;
}

.error-text {
  font-size: 13px;
  color: #991b1b;
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 파라미터 테이블 ── */
.param-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
  padding: 5px 0;
  border-bottom: 1px solid #f0f0f0;
}
.param-row:last-child { border-bottom: none; }

.param-key {
  width: 130px;
  flex-shrink: 0;
  color: #888;
  font-weight: 500;
}

.param-val {
  color: #333;
  word-break: break-all;
}

/* ── F002 이슈 결과 ── */
.result-date {
  font-size: 14px;
  font-weight: 700;
  color: #4a90d9;
  margin-bottom: 14px;
}

.issue-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.issue-card {
  background: #f8faff;
  border: 1px solid #dce8f8;
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.issue-title {
  font-size: 14px;
  font-weight: 600;
  color: #222;
  line-height: 1.5;
}

.issue-summary {
  font-size: 13px;
  color: #555;
  line-height: 1.6;
}

/* 중요도 배지 */
.issue-imp {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
  align-self: flex-start;
}

.imp-high { background: #fee2e2; color: #b91c1c; }
.imp-mid  { background: #fef9c3; color: #854d0e; }
.imp-low  { background: #dcfce7; color: #166534; }

/* 중요도 + 파서 배지를 가로로 나열 */
.issue-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

/* 파서 배지 */
.issue-parser {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 10px;
  background: #f0f4ff;
  color: #4a6fa5;
}

/* ── 액션 버튼 영역 ── */
.action-row {
  display: flex;
  justify-content: flex-end;
}

/* 취소 버튼 */
.cancel-btn {
  background: #fff;
  color: #ef4444;
  border: 1.5px solid #ef4444;
  border-radius: 8px;
  padding: 8px 22px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.cancel-btn:hover:not(:disabled) {
  background: #fee2e2;
}

.cancel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── F003 미디어 결과 ── */

/* 생성된 이미지/동영상 — 전체 너비에 맞추되 둥근 모서리 */
.result-media {
  max-width: 100%;
  border-radius: 8px;
  margin-bottom: 10px;
  display: block;
}

/* 생성 메타 정보 — 생성 유형, 스타일, 기반 모델, 시드를 한 줄로 나열 */
.result-meta {
  font-size: 12px;
  color: #888;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

/* 파일 경로 — 모노스페이스로 경로 가독성 확보 */
.result-file {
  font-size: 11px;
  color: #bbb;
  font-family: monospace;
  word-break: break-all;
}

/* 파일 링크 — 밑줄 + 호버 시 밝아짐 */
.result-file-link {
  color: #90caf9;
  text-decoration: underline;
  cursor: pointer;
}
.result-file-link:hover {
  color: #bbdefb;
}

/* 프롬프트 섹션 — 포지티브/네거티브 프롬프트 표시 영역 */
.prompt-section {
  margin-top: 10px;
}

/* 프롬프트 레이블 — 섹션 제목 */
.prompt-label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  margin-bottom: 4px;
}

/* 프롬프트 내용 — 회색 배경 박스, 작은 폰트 */
.prompt-box {
  background: #f5f5f5;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 11px;
  color: #555;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
</style>
