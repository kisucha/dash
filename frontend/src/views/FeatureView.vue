<!-- FeatureView.vue — 업무 상세 페이지 (/features/:id) -->
<!-- 파라미터 입력 폼 + 해당 업무의 실행 이력 테이블을 함께 표시한다 -->
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getFeature, getTasksByFeature, deleteTaskRecord } from '../api/index.js'
import { useTaskStore } from '../store/tasks.js'
import StatusBadge from '../components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()

// ── Feature 상태 ──
const feature = ref(null)
const loading = ref(true)
const errorMsg = ref('')
const submitting = ref(false)
const formValues = ref({})

// ── 실행 이력 상태 ──
const historyTasks = ref([])
const historyLoading = ref(false)
const historyTotal = ref(0)

// ── Feature 로드 + 이력 로드 ──
onMounted(async () => {
  try {
    const res = await getFeature(route.params.id)
    feature.value = res.data
    initForm(res.data.input_schema)
  } catch {
    errorMsg.value = '업무 정보를 불러올 수 없습니다.'
  } finally {
    loading.value = false
  }
  fetchHistory()
})

async function fetchHistory() {
  historyLoading.value = true
  try {
    const res = await getTasksByFeature(route.params.id, 50)
    historyTasks.value = res.data.items ?? []
    historyTotal.value = res.data.total ?? 0
  } catch {
    // 이력 로드 실패는 조용히 무시
  } finally {
    historyLoading.value = false
  }
}

// ── 폼 초기화 ──
function initForm(schema) {
  if (!Array.isArray(schema)) return
  const values = {}
  for (const field of schema) {
    const key = field.name
    if (field.type === 'integer') {
      values[key] = field.default !== undefined && field.default !== null ? field.default : 0
    } else {
      values[key] = field.default !== undefined && field.default !== null ? String(field.default) : ''
    }
  }
  formValues.value = values
}

const fields = computed(() => {
  const schema = feature.value?.input_schema
  if (!Array.isArray(schema)) return []
  return schema.map(field => ({
    key: field.name,
    label: field.title ?? field.name,
    type: field.type ?? 'string',
    description: field.description ?? '',
    required: field.required ?? false,
    options: field.options ?? [],
    default: field.default,
  }))
})

// ── 실행 제출 ──
async function handleSubmit() {
  if (submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    const params = buildParams()
    const task = await taskStore.createTask(feature.value.feature_id, params)
    // 실행 후 이력 갱신
    await fetchHistory()
    router.push({ name: 'TaskDetail', params: { id: task.id } })
  } catch (err) {
    errorMsg.value = err?.response?.data?.detail ?? '작업 생성 중 오류가 발생했습니다.'
  } finally {
    submitting.value = false
  }
}

function buildParams() {
  const result = {}
  for (const field of fields.value) {
    const raw = formValues.value[field.key]
    if (field.type === 'integer') {
      const num = Number(raw)
      if (!isNaN(num)) result[field.key] = num
    } else if (field.type === 'list') {
      const arr = String(raw).split(',').map(s => s.trim()).filter(s => s.length > 0)
      if (arr.length > 0) result[field.key] = arr
    } else {
      if (String(raw).trim() !== '') result[field.key] = String(raw)
    }
  }
  return result
}

// ── 이력 삭제 ──
async function deleteHistory(task) {
  if (task.status === 'RUNNING') return
  if (!confirm(`#${task.id} 이력을 삭제하시겠습니까?`)) return
  try {
    await deleteTaskRecord(task.id)
    historyTasks.value = historyTasks.value.filter(t => t.id !== task.id)
    historyTotal.value = Math.max(0, historyTotal.value - 1)
  } catch {
    alert('삭제에 실패했습니다.')
  }
}

// ── 날짜 포맷 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>

<template>
  <div class="feature-view">

    <!-- 로딩 중 -->
    <div v-if="loading" class="loading-text">불러오는 중...</div>

    <!-- 오류 -->
    <div v-else-if="!feature" class="error-box">{{ errorMsg || '업무를 찾을 수 없습니다.' }}</div>

    <!-- 콘텐츠 -->
    <template v-else>

      <!-- 헤더 -->
      <div class="page-header">
        <button class="back-btn" @click="router.back()">← 뒤로</button>
        <h1 class="page-title">{{ feature.name }}</h1>
        <p class="page-desc">{{ feature.description }}</p>
      </div>

      <!-- ── 파라미터 입력 폼 ── -->
      <div class="section-card">
        <h2 class="section-title">파라미터 설정</h2>

        <div v-if="fields.length === 0" class="no-params">
          이 업무는 추가 파라미터가 없습니다.
        </div>

        <form v-else @submit.prevent="handleSubmit">
          <div v-for="field in fields" :key="field.key" class="form-group">
            <label class="form-label">
              {{ field.label }}
              <span v-if="field.required" class="required-mark">*</span>
            </label>

            <select
              v-if="field.type === 'select'"
              v-model="formValues[field.key]"
              class="form-input form-select"
            >
              <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
            </select>

            <textarea
              v-else-if="field.type === 'textarea'"
              v-model="formValues[field.key]"
              class="form-input form-textarea form-textarea-prompt"
              :placeholder="field.description"
              rows="12"
              spellcheck="false"
            />

            <textarea
              v-else-if="field.type === 'list'"
              v-model="formValues[field.key]"
              class="form-input form-textarea"
              :placeholder="`쉼표로 구분하여 입력 (예: 값1, 값2, 값3)`"
              rows="2"
            />

            <input
              v-else-if="field.type === 'integer'"
              v-model.number="formValues[field.key]"
              type="number"
              class="form-input"
              :placeholder="field.description"
            />

            <input
              v-else
              v-model="formValues[field.key]"
              type="text"
              class="form-input"
              :placeholder="field.description"
            />

            <span v-if="field.description" class="form-hint">{{ field.description }}</span>
          </div>

          <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
          <button type="submit" class="submit-btn" :disabled="submitting">
            {{ submitting ? '실행 중...' : '실행' }}
          </button>
        </form>

        <div v-if="fields.length === 0">
          <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
          <button class="submit-btn" :disabled="submitting" @click="handleSubmit">
            {{ submitting ? '실행 중...' : '실행' }}
          </button>
        </div>
      </div>

      <!-- ── 실행 이력 ── -->
      <div class="section-card">
        <div class="history-header">
          <h2 class="section-title">실행 이력</h2>
          <span class="history-count">총 {{ historyTotal }}건</span>
        </div>

        <div v-if="historyLoading" class="loading-text">불러오는 중...</div>

        <div v-else-if="historyTasks.length === 0" class="empty-text">
          아직 실행 이력이 없습니다.
        </div>

        <table v-else class="history-table">
          <colgroup>
            <col style="width: 70px" />
            <col style="width: 110px" />
            <col />
            <col style="width: 50px" />
          </colgroup>
          <thead>
            <tr>
              <th class="center">ID</th>
              <th class="center">상태</th>
              <th>실행 시각</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="task in historyTasks"
              :key="task.id"
              class="clickable-row"
              @click="router.push({ name: 'TaskDetail', params: { id: task.id } })"
            >
              <td class="center task-id-cell">#{{ task.id }}</td>
              <td class="center">
                <StatusBadge :status="task.status" />
              </td>
              <td class="time-cell">{{ formatDate(task.created_at) }}</td>
              <td class="center" @click.stop>
                <button
                  class="delete-btn"
                  :disabled="task.status === 'RUNNING'"
                  :title="task.status === 'RUNNING' ? '실행 중인 작업은 삭제할 수 없습니다' : '이력 삭제'"
                  @click="deleteHistory(task)"
                >🗑</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

    </template>
  </div>
</template>

<style scoped>
.feature-view {
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.loading-text { color: #999; font-size: 14px; padding: 20px 0; }

.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 14px 18px;
  font-size: 14px;
}

/* ── 헤더 ── */
.page-header { margin-bottom: 4px; }

.back-btn {
  background: none;
  border: none;
  color: #4a90d9;
  font-size: 14px;
  cursor: pointer;
  padding: 0;
  margin-bottom: 12px;
  display: inline-block;
}
.back-btn:hover { text-decoration: underline; }

.page-title { font-size: 22px; font-weight: 700; color: #222; margin: 0 0 6px; }
.page-desc  { font-size: 14px; color: #666; margin: 0; line-height: 1.5; }

/* ── 섹션 카드 공통 ── */
.section-card {
  background: #ffffff;
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #333;
  margin: 0 0 18px;
}

/* ── 폼 ── */
.no-params { font-size: 14px; color: #aaa; margin-bottom: 20px; }

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 18px;
}

.form-label { font-size: 13px; font-weight: 600; color: #444; }
.required-mark { color: #ef4444; margin-left: 2px; }

.form-input {
  border: 1px solid #d8d8d8;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 14px;
  color: #222;
  background: #fafafa;
  transition: border-color 0.15s;
  outline: none;
  font-family: inherit;
}
.form-input:focus { border-color: #4a90d9; background: #fff; }
.form-select { cursor: pointer; appearance: auto; }

.form-textarea-prompt {
  min-height: 220px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
}
.form-textarea { resize: vertical; min-height: 60px; }
.form-hint { font-size: 12px; color: #aaa; }

.error-msg {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  margin-bottom: 16px;
}

.submit-btn {
  width: 100%;
  background: #4a90d9;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 11px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: #357abd; }
.submit-btn:disabled { background: #a0c4e8; cursor: not-allowed; }

/* ── 실행 이력 ── */
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.history-header .section-title { margin-bottom: 0; }

.history-count {
  font-size: 12px;
  color: #999;
  font-weight: 500;
}

.empty-text { font-size: 14px; color: #aaa; text-align: center; padding: 20px 0; }

.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.history-table th {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #888;
  border-bottom: 2px solid #e8e8e8;
  background: #fafafa;
  text-align: left;
  white-space: nowrap;
}
.history-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  color: #333;
  vertical-align: middle;
}
.history-table tbody tr:last-child td { border-bottom: none; }

.clickable-row { cursor: pointer; transition: background 0.12s; }
.clickable-row:hover td { background: #f5f9ff; }

.center { text-align: center; }

.task-id-cell {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #4a90d9;
}
.time-cell { font-size: 13px; color: #666; }

.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 15px;
  padding: 4px 6px;
  border-radius: 6px;
  opacity: 0.5;
  transition: opacity 0.15s, background 0.15s;
  line-height: 1;
}
.delete-btn:hover:not(:disabled) { opacity: 1; background: #fee2e2; }
.delete-btn:disabled { opacity: 0.2; cursor: not-allowed; }
</style>
