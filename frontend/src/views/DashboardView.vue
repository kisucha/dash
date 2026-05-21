<!-- DashboardView.vue — 메인 대시보드 페이지 (/) -->
<!-- Ollama 연결 상태, 업무 목록(게시판), 최근 실행 이력(tasks + F001 + F005 + F006 content_jobs 통합) -->
<!-- 작업 목록은 10초 폴링, Ollama 상태는 30초 폴링 -->
<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '../store/tasks.js'
import { useOllamaStore } from '../store/ollama.js'
import { useF001Store } from '../store/f001.js'
import { useF005Store } from '../store/f005.js'
import { useF006Store } from '../store/f006.js'
import StatusBadge from '../components/StatusBadge.vue'

const router = useRouter()
const taskStore = useTaskStore()
const f001Store = useF001Store()
const f005Store = useF005Store()
const f006Store = useF006Store()
const ollama = useOllamaStore()

// ── feature_id → feature 객체 빠른 조회용 Map ──
const featureMap = computed(() => {
  const m = {}
  for (const f of taskStore.features) m[f.feature_id] = f
  return m
})

function getFeatureName(featureId) {
  return featureMap.value[featureId]?.name ?? featureId
}

// ── 최근 이력 통합 — tasks 테이블 + F001 content_jobs 합산, created_at DESC ──
const recentHistory = computed(() => {
  const taskItems = taskStore.tasks.map((t) => ({
    _type: 'task',
    id: t.id,
    featureName: getFeatureName(t.feature_id),
    status: t.status,
    created_at: t.created_at,
  }))
  const f001Items = f001Store.jobs.map((j) => ({
    _type: 'f001',
    id: j.id,
    featureName: 'F001 유튜브 컨텐츠 제작',
    status: j.status,
    created_at: j.created_at,
  }))
  const f005Items = f005Store.jobs.map((j) => ({
    _type: 'f005',
    id: j.id,
    featureName: 'F005 유튜브 제작(채팅기반)',
    status: j.status,
    created_at: j.created_at,
  }))
  const f006Items = f006Store.jobs.map((j) => ({
    _type: 'f006',
    id: j.id,
    featureName: 'F006 유튜브 제작(V4 채팅기반)',
    status: j.status,
    created_at: j.created_at,
  }))
  const merged = [...taskItems, ...f001Items, ...f005Items, ...f006Items]
  merged.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  return merged.slice(0, 15)
})

// ── 이력 행 클릭 → 적절한 상세 페이지로 이동 ──
function goToHistory(item) {
  if (item._type === 'f001') {
    router.push({ name: 'F001JobDetail', params: { jobId: item.id } })
  } else if (item._type === 'f005') {
    router.push({ name: 'F005JobDetail', params: { jobId: item.id } })
  } else if (item._type === 'f006') {
    router.push({ name: 'F006JobDetail', params: { jobId: item.id } })
  } else {
    router.push({ name: 'TaskDetail', params: { id: item.id } })
  }
}

// ── 날짜 포맷 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── 이력 삭제 ──
async function deleteHistory(item) {
  if (item.status === 'RUNNING') return
  if (!confirm(`#${item.id} 이력을 삭제하시겠습니까?`)) return
  try {
    if (item._type === 'f001') {
      await f001Store.deleteJob(item.id)
    } else if (item._type === 'f005') {
      await f005Store.deleteJob(item.id)
    } else if (item._type === 'f006') {
      await f006Store.deleteJob(item.id)
    } else {
      await taskStore.deleteTaskRecord(item.id)
    }
  } catch {
    alert('삭제에 실패했습니다.')
  }
}

// ── 폴링 ──
let pollTimer = null
let ollamaTimer = null

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    taskStore.fetchTasks(10)
    f001Store.fetchJobs(10)
    f005Store.fetchJobs(10)
    f006Store.fetchJobs(10)
  }, 10000)
  ollamaTimer = setInterval(() => ollama.loadModels(), 30000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (ollamaTimer) { clearInterval(ollamaTimer); ollamaTimer = null }
}

onMounted(async () => {
  taskStore.fetchFeatures().catch(() => {})
  taskStore.fetchTasks(10).catch(() => {})
  f001Store.fetchJobs(10).catch(() => {})
  f005Store.fetchJobs(10).catch(() => {})
  f006Store.fetchJobs(10).catch(() => {})
  if (ollama.status === 'loading') {
    await ollama.loadModels()
  } else {
    ollama.loadModels()
  }
  startPolling()
})

onUnmounted(() => stopPolling())
</script>

<template>
  <div class="dashboard">

    <!-- ── Ollama 연결 상태 배너 ── -->
    <section class="status-banner" :class="`status-${ollama.status}`">
      <span class="status-dot"></span>
      <span v-if="ollama.status === 'loading'">Ollama 상태 확인 중...</span>
      <span v-else-if="ollama.status === 'ok'">
        Ollama 정상 연결됨{{ ollama.message ? ' — ' + ollama.message : '' }}
      </span>
      <span v-else>Ollama 연결 오류{{ ollama.message ? ': ' + ollama.message : '' }}</span>

      <select
        v-if="ollama.status === 'ok' && ollama.modelList.length > 0"
        class="model-select"
        :value="ollama.selectedModel"
        :disabled="ollama.modelSaving"
        @change="ollama.changeModel($event.target.value)"
      >
        <option v-for="m in ollama.modelList" :key="m" :value="m">{{ m }}</option>
      </select>
      <span v-if="ollama.modelSaving" class="model-saving-text">저장 중...</span>

      <button v-if="ollama.status !== 'ok'" class="retry-btn" @click="ollama.loadModels">
        재시도
      </button>
    </section>

    <!-- ── 업무 목록 ── -->
    <section class="section">
      <h2 class="section-title">업무 목록</h2>

      <div v-if="taskStore.features.length === 0" class="empty-text">
        등록된 업무가 없습니다.
      </div>

      <table v-else class="board-table">
        <colgroup>
          <col style="width: 60px" />
          <col style="width: 200px" />
          <col />
          <col style="width: 90px" />
        </colgroup>
        <thead>
          <tr>
            <th style="width: 60px" class="center">ID</th>
            <th>업무명</th>
            <th>설명</th>
            <th class="center">스케줄</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="feature in taskStore.features"
            :key="feature.feature_id"
            class="clickable-row"
            @click="feature.feature_id === 'F007'
              ? router.push({ name: 'F007' })
              : feature.feature_id === 'F006'
              ? router.push({ name: 'F006Feature' })
              : feature.feature_id === 'F005'
                ? router.push({ name: 'F005Feature' })
                : feature.feature_id === 'F004'
                ? router.push({ name: 'F004Feature' })
                : feature.feature_id === 'F003'
                  ? router.push({ name: 'F003Feature' })
                  : feature.feature_id === 'F001'
                    ? router.push({ name: 'F001Feature' })
                    : router.push({ name: 'Feature', params: { id: feature.feature_id } })"
          >
            <td class="center feature-id-cell">{{ feature.feature_id }}</td>
            <td class="feature-name-cell">{{ feature.name }}</td>
            <td class="desc-cell">{{ feature.description }}</td>
            <td class="center">
              <span v-if="feature.supports_schedule" class="badge-schedule">✓</span>
              <span v-else class="text-muted">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- ── 최근 실행 이력 (tasks + F001 + F005 content_jobs 통합) ── -->
    <section class="section">
      <h2 class="section-title">최근 실행 이력</h2>

      <div v-if="recentHistory.length === 0" class="empty-text">
        실행된 작업이 없습니다.
      </div>

      <table v-else class="board-table">
        <colgroup>
          <col style="width: 70px" />
          <col style="width: 160px" />
          <col style="width: 110px" />
          <col />
          <col style="width: 50px" />
        </colgroup>
        <thead>
          <tr>
            <th class="center">ID</th>
            <th>업무</th>
            <th class="center">상태</th>
            <th>실행 시각</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in recentHistory"
            :key="`${item._type}-${item.id}`"
            class="clickable-row"
            @click="goToHistory(item)"
          >
            <td class="center task-id-cell">#{{ item.id }}</td>
            <td>{{ item.featureName }}</td>
            <td class="center">
              <StatusBadge :status="item.status" />
            </td>
            <td class="time-cell">{{ formatDate(item.created_at) }}</td>
            <td class="center" @click.stop>
              <button
                class="delete-btn"
                :disabled="item.status === 'RUNNING'"
                :title="item.status === 'RUNNING' ? '실행 중인 작업은 삭제할 수 없습니다' : '이력 삭제'"
                @click="deleteHistory(item)"
              >
                🗑
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── Ollama 상태 배너 ── */
.status-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-loading { background: #f0f0f0; color: #666; }
.status-loading .status-dot { background: #999; }
.status-ok { background: #dcfce7; color: #166534; }
.status-ok .status-dot { background: #22c55e; }
.status-error { background: #fee2e2; color: #991b1b; }
.status-error .status-dot { background: #ef4444; }

.retry-btn {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 0.15s;
  margin-left: 4px;
}
.retry-btn:hover { opacity: 1; }

.model-select {
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font-size: 13px;
  font-family: monospace;
  cursor: pointer;
  opacity: 0.85;
  max-width: 280px;
}
.model-select:disabled { opacity: 0.5; cursor: not-allowed; }
.model-select:focus { outline: none; opacity: 1; }

.model-saving-text { font-size: 12px; opacity: 0.7; flex-shrink: 0; }

/* ── 섹션 공통 ── */
.section {
  background: #ffffff;
  border-radius: 10px;
  padding: 20px 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #222;
  margin: 0 0 14px;
}

.empty-text {
  font-size: 14px;
  color: #aaa;
  text-align: center;
  padding: 20px 0;
}

/* ── 게시판 테이블 공통 ── */
.board-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.board-table th {
  padding: 9px 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #888;
  border-bottom: 2px solid #e8e8e8;
  background: #fafafa;
  white-space: nowrap;
}

.board-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  color: #333;
  vertical-align: middle;
}

.board-table tbody tr:last-child td {
  border-bottom: none;
}

.clickable-row {
  cursor: pointer;
  transition: background 0.12s;
}
.clickable-row:hover td {
  background: #f5f9ff;
}

.center {
  text-align: center;
}

/* 업무 목록 셀 */
.feature-id-cell {
  font-family: monospace;
  font-size: 12px;
  font-weight: 700;
  color: #4a90d9;
}

.feature-name-cell {
  font-weight: 600;
  color: #222;
}

.desc-cell {
  color: #666;
  line-height: 1.5;
}

.badge-schedule {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  color: #4a90d9;
}

.text-muted {
  color: #ccc;
}

/* 최근 이력 셀 */
.task-id-cell {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #4a90d9;
}

.time-cell {
  font-size: 13px;
  color: #666;
}

/* 삭제 버튼 */
.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 15px;
  padding: 4px 6px;
  border-radius: 6px;
  opacity: 0.55;
  transition: opacity 0.15s, background 0.15s;
  line-height: 1;
}
.delete-btn:hover:not(:disabled) {
  opacity: 1;
  background: #fee2e2;
}
.delete-btn:disabled {
  opacity: 0.2;
  cursor: not-allowed;
}
</style>
