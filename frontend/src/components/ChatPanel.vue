<!-- ChatPanel.vue — 우측 채팅 패널 컴포넌트 -->
<!-- Ollama LLM과 SSE 스트리밍 채팅, 인터넷 검색 컨텍스트 삽입 지원 -->
<script setup>
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { sendChatStream, searchWeb, refineQuery } from '../api/index.js'

// ── props: 인터넷 사용 여부 및 검색 엔진은 부모(App.vue)에서 관리 ──
const props = defineProps({
  useInternet: {
    type: Boolean,
    default: false,
  },
  searchProvider: {
    type: String,
    default: 'searxng', // 'searxng' | 'tavily'
  },
})

// ── 상태 ──

// 입력창 텍스트
const inputText = ref('')

// 대화 메시지 목록 — {id, role: 'user'|'assistant'|'system', content, loading}
const messages = ref([])

// 현재 스트리밍 중인지 여부 (입력 잠금용)
const streaming = ref(false)

// 검색 중 여부
const searching = ref(false)

// 스크롤 컨테이너 ref
const scrollContainer = ref(null)

// 텍스트 입력창 ref — 포커스 제어용
const inputRef = ref(null)

// 고유 ID 카운터
let msgId = 0

// 브라우저 창/탭이 다시 포커스를 받으면 입력창 포커스 복원 (ERR-004 방지)
function restoreFocus() {
  // 스트리밍 중이 아닐 때만 복원 (타이핑 방해 방지)
  if (!streaming.value) {
    inputRef.value?.focus()
  }
}

// visibilitychange 핸들러 — cleanup용으로 별도 변수에 저장
const onVisibilityChange = () => {
  if (document.visibilityState === 'visible') restoreFocus()
}

// 마운트 직후 포커스 + 창 복귀 시 포커스 이벤트 등록
onMounted(() => {
  inputRef.value?.focus()
  window.addEventListener('focus', restoreFocus)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

// 언마운트 시 이벤트 리스너 정리
onUnmounted(() => {
  window.removeEventListener('focus', restoreFocus)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

// ── 메서드 ──

// 메시지 목록 아래로 스크롤
async function scrollToBottom() {
  await nextTick()
  if (scrollContainer.value) {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }
}

// Ollama에 전달할 이력 형식으로 변환 (system 메시지 제외, 최근 10턴)
function buildHistory() {
  return messages.value
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(-10)
    .map(m => ({ role: m.role, content: m.content }))
}

// 메시지 전송
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  inputText.value = ''
  streaming.value = true

  // 사용자 메시지 추가 전에 이력 캡처 — 쿼리 정제 시 현재 질문 이전 이력을 참조
  const historyForRefine = buildHistory()

  // 사용자 메시지 추가
  messages.value.push({ id: ++msgId, role: 'user', content: text })
  await scrollToBottom()

  let searchContext = null
  let refinedQuery = null  // 이력 기반으로 정제된 검색 쿼리

  // 인터넷 사용이 켜져 있으면 먼저 검색
  if (props.useInternet) {
    searching.value = true
    // sysMsg를 직접 참조로 관리해 나중에 내용을 업데이트
    const sysMsg = { id: ++msgId, role: 'system', content: `인터넷에서 "${text}" 검색 중...` }
    messages.value.push(sysMsg)
    await scrollToBottom()

    try {
      // ── [1] 이력 기반 쿼리 정제 ─────────────────────────────────────
      // "해당 영화", "그 제품" 같은 지시대명사가 있으면 이력에서 실제 대상을 파악
      let searchQuery = text
      if (historyForRefine.length > 0) {
        try {
          const refineRes = await refineQuery(text, historyForRefine, props.searchProvider)
          if (refineRes.data.was_refined) {
            searchQuery = refineRes.data.refined
            refinedQuery = searchQuery
            sysMsg.content = `검색어 재구성: "${searchQuery}" 검색 중...`
            await scrollToBottom()
          }
        } catch {
          // 정제 API 실패 시 원본 쿼리 그대로 사용
        }
      }

      // ── [2] LLM 서브쿼리 depth-first 멀티 홉 심층 검색 ──────────────
      // useLlmSubqueries=true: 각 hop 후 LLM이 발견된 핵심 엔티티를 파고드는 쿼리를 생성
      const res = await searchWeb(searchQuery, 20, props.searchProvider, true, 3, true)
      searchContext = res.data.context_text
      const providerLabel = props.searchProvider === 'tavily' ? 'Tavily' : 'SearXNG'
      const hops = res.data.hops_executed ?? 1
      const queryLabel = refinedQuery ? ` ("${searchQuery}")` : ''
      sysMsg.content = `${providerLabel} 검색 완료${queryLabel} (${res.data.results.length}건, ${hops}차 탐색) — 검색 결과를 참고하여 답변합니다.`
    } catch {
      sysMsg.content = '인터넷 검색 실패 — LLM 자체 지식으로 답변합니다.'
    } finally {
      searching.value = false
    }
    await scrollToBottom()
  }

  // 어시스턴트 응답 메시지 (스트리밍으로 채워짐)
  // statusText: 검색 중 등 상태 힌트 — content가 오기 전 말풍선에 표시
  // suggestions: 멀티 홉 후 후속 제안 버튼 목록
  const assistantMsg = { id: ++msgId, role: 'assistant', content: '', loading: true, statusText: '', suggestions: [] }
  messages.value.push(assistantMsg)
  await scrollToBottom()

  try {
    const history = buildHistory()
    // refinedQuery를 백엔드에 전달 — 의도 감지 시 추가 검색에 정제된 쿼리 활용
    const response = await sendChatStream(text, history, searchContext, props.searchProvider, refinedQuery)

    if (!response.ok) {
      assistantMsg.content = `오류: ${response.statusText}`
      assistantMsg.loading = false
      streaming.value = false
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    // SSE 스트림 읽기 루프
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE는 "\n\n"으로 이벤트 구분
      const events = buffer.split('\n\n')
      // 마지막 미완성 조각은 다시 버퍼에
      buffer = events.pop() || ''

      for (const event of events) {
        const line = event.trim()
        if (!line.startsWith('data:')) continue

        const jsonStr = line.slice(5).trim()
        if (!jsonStr) continue

        try {
          const chunk = JSON.parse(jsonStr)
          if (chunk.error) {
            assistantMsg.content = `오류: ${chunk.error}`
            break
          }
          // 상태 힌트 SSE — 검색 중 메시지 표시
          if (chunk.type === 'status') {
            assistantMsg.statusText = chunk.message || ''
            await scrollToBottom()
            continue
          }
          // 추가 제안 SSE — 멀티 홉 완료 후 후속 질문 3가지
          if (chunk.type === 'suggestions') {
            assistantMsg.suggestions = chunk.items || []
            await scrollToBottom()
            continue
          }
          // 첫 토큰 수신 시 상태 힌트 제거
          if (chunk.token) {
            assistantMsg.statusText = ''
          }
          assistantMsg.content += chunk.token || ''
          // 실시간 스크롤 유지
          if (scrollContainer.value) {
            const el = scrollContainer.value
            const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
            if (isAtBottom) await scrollToBottom()
          }
          if (chunk.done) break
        } catch {
          // JSON 파싱 오류 무시
        }
      }
    }
  } catch (err) {
    assistantMsg.content = `연결 오류: ${err.message}`
  } finally {
    assistantMsg.loading = false
    streaming.value = false
    await scrollToBottom()
    // 전송 완료 후 입력창 포커스 복귀
    await nextTick()
    inputRef.value?.focus()
  }
}

// 추가 제안 버튼 클릭 — 제안 텍스트를 입력창에 넣고 바로 전송
function sendSuggestion(text) {
  inputText.value = text
  sendMessage()
}

// 대화 초기화
function clearChat() {
  messages.value = []
  nextTick(() => inputRef.value?.focus())
}

// Enter 키 전송 (Shift+Enter는 줄바꿈)
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// 부모(App.vue)가 라우트 이동 등의 상황에서 포커스를 복원할 수 있도록 노출
defineExpose({ focusInput: () => inputRef.value?.focus() })
</script>

<template>
  <div class="chat-panel">
    <!-- 패널 헤더 -->
    <div class="chat-header">
      <span class="chat-title">AI 채팅</span>
      <div class="header-actions">
        <span v-if="useInternet" class="internet-badge" :class="searchProvider">
          {{ searchProvider === 'tavily' ? 'Tavily' : 'SearXNG' }}
        </span>
        <button class="clear-btn" @click="clearChat" :disabled="streaming">초기화</button>
      </div>
    </div>

    <!-- 메시지 목록 -->
    <div class="chat-messages" ref="scrollContainer">
      <!-- 빈 상태 안내 -->
      <div v-if="messages.length === 0" class="empty-chat">
        <div class="empty-icon">💬</div>
        <div class="empty-text">LLM에게 무엇이든 물어보세요.</div>
        <div v-if="useInternet" class="empty-sub">인터넷 검색이 활성화되어 있습니다.</div>
      </div>

      <!-- 메시지들 -->
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-row"
        :class="msg.role"
      >
        <!-- 시스템 안내 메시지 (검색 상태 등) -->
        <div v-if="msg.role === 'system'" class="sys-msg">
          {{ msg.content }}
        </div>

        <!-- 사용자 메시지 -->
        <div v-else-if="msg.role === 'user'" class="bubble user-bubble">
          {{ msg.content }}
        </div>

        <!-- 어시스턴트 메시지 -->
        <div v-else class="bubble assistant-bubble">
          <!-- 로딩 중 — statusText 없으면 점 애니메이션 -->
          <span v-if="msg.loading && !msg.content && !msg.statusText" class="typing-dots">
            <span></span><span></span><span></span>
          </span>
          <!-- 상태 힌트 — 추가 검색 중 등 -->
          <span v-if="msg.loading && msg.statusText && !msg.content" class="status-hint">
            {{ msg.statusText }}
          </span>
          <!-- 줄바꿈 유지 -->
          <span class="msg-text" style="white-space: pre-wrap;">{{ msg.content }}</span>
          <span v-if="msg.loading && msg.content" class="cursor-blink">▌</span>
          <!-- 추가 제안 버튼 — 멀티 홉 검색 완료 후 표시 -->
          <div v-if="!msg.loading && msg.suggestions && msg.suggestions.length > 0" class="suggestions">
            <div class="suggestions-label">이어서 물어보기</div>
            <button
              v-for="(sug, idx) in msg.suggestions"
              :key="idx"
              class="suggestion-chip"
              :disabled="streaming"
              @click="sendSuggestion(sug)"
            >{{ sug }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 입력 영역 -->
    <div class="chat-input-area">
      <textarea
        ref="inputRef"
        v-model="inputText"
        class="chat-input"
        placeholder="메시지를 입력하세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
        rows="3"
        :disabled="streaming"
        @keydown="onKeydown"
      ></textarea>
      <button
        class="send-btn"
        :disabled="streaming || !inputText.trim()"
        @click="sendMessage"
      >
        <span v-if="streaming">...</span>
        <span v-else>전송</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 채팅 패널 전체 레이아웃 — 세로 flex */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-left: 1px solid #e0e0e0;
  overflow: hidden;
}

/* 헤더 */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #f9f9f9;
  flex-shrink: 0;
}

.chat-title {
  font-size: 15px;
  font-weight: 700;
  color: #222;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 인터넷 활성 배지 */
.internet-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.internet-badge.searxng {
  background: #dcfce7;
  color: #166534;
}
.internet-badge.tavily {
  background: #e8f0fd;
  color: #1d4ed8;
}

/* 초기화 버튼 */
.clear-btn {
  font-size: 12px;
  color: #888;
  background: none;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  transition: background 0.15s;
}
.clear-btn:hover:not(:disabled) {
  background: #f0f0f0;
}
.clear-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 메시지 스크롤 영역 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 빈 상태 */
.empty-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: #aaa;
}
.empty-icon { font-size: 32px; }
.empty-text { font-size: 14px; font-weight: 500; }
.empty-sub { font-size: 12px; color: #22c55e; }

/* 메시지 행 */
.message-row {
  display: flex;
}
.message-row.user { justify-content: flex-end; }
.message-row.assistant { justify-content: flex-start; }
.message-row.system { justify-content: center; }

/* 시스템 메시지 */
.sys-msg {
  font-size: 12px;
  color: #888;
  background: #f5f5f5;
  border-radius: 8px;
  padding: 5px 12px;
  max-width: 90%;
  text-align: center;
}

/* 말풍선 공통 */
.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

/* 사용자 말풍선 — 파란색 */
.user-bubble {
  background: #4a90d9;
  color: #ffffff;
  border-bottom-right-radius: 4px;
}

/* 어시스턴트 말풍선 — 밝은 회색 */
.assistant-bubble {
  background: #f3f3f3;
  color: #222;
  border-bottom-left-radius: 4px;
}

/* 타이핑 중 점 애니메이션 */
.typing-dots {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-dots span {
  width: 7px;
  height: 7px;
  background: #aaa;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-5px); }
}

/* 추가 검색 중 등 상태 힌트 */
.status-hint {
  display: block;
  font-size: 12px;
  color: #888;
  font-style: italic;
  padding: 2px 0 4px;
}

/* 스트리밍 커서 깜빡임 */
.cursor-blink {
  animation: blink 1s step-end infinite;
  color: #4a90d9;
  font-weight: 700;
}
@keyframes blink {
  50% { opacity: 0; }
}

/* 입력 영역 */
.chat-input-area {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #e8e8e8;
  background: #f9f9f9;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  resize: none;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  line-height: 1.5;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}
.chat-input:focus {
  border-color: #4a90d9;
}
.chat-input:disabled {
  background: #f5f5f5;
  color: #aaa;
}

/* 추가 제안 버튼 묶음 */
.suggestions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #e0e0e0;
}

.suggestions-label {
  font-size: 11px;
  color: #aaa;
  font-weight: 600;
  letter-spacing: 0.03em;
  margin-bottom: 2px;
}

.suggestion-chip {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 12px;
  background: #fff;
  border: 1px solid #c8d8ef;
  border-radius: 8px;
  font-size: 13px;
  color: #3578c5;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  line-height: 1.4;
}
.suggestion-chip:hover:not(:disabled) {
  background: #e8f0fd;
  border-color: #4a90d9;
}
.suggestion-chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 전송 버튼 */
.send-btn {
  align-self: flex-end;
  padding: 9px 18px;
  background: #4a90d9;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}
.send-btn:hover:not(:disabled) {
  background: #3578c5;
}
.send-btn:disabled {
  background: #b0c8e8;
  cursor: not-allowed;
}
</style>
