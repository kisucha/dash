<!-- App.vue — 최상위 레이아웃 컴포넌트 -->
<!-- 상단 네비게이션 바, 메인 콘텐츠 + 채팅 패널 2분할 레이아웃, 드래그 분할 지원 -->
<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import ChatPanel from './components/ChatPanel.vue'

// 라우트 변경 감지용
const route = useRoute()

// page-content 스크롤 컨테이너 ref
const pageContentRef = ref(null)

// 채팅 패널 ref — 포커스 제어용 (defineExpose 경유)
const chatPanelRef = ref(null)

// 라우트 이동 시 page-content 스크롤 최상단으로 리셋 + 채팅창 포커스 복귀
watch(() => route.path, async () => {
  if (pageContentRef.value) {
    pageContentRef.value.scrollTop = 0
  }
  // 라우트 이동 후에도 채팅창 포커스 유지
  await nextTick()
  chatPanelRef.value?.focusInput()
})

// ── 인터넷 사용 여부 (localStorage 에 저장해 새로고침 후에도 유지) ──
const useInternet = ref(
  localStorage.getItem('dash_use_internet') === 'true'
)

function toggleInternet() {
  useInternet.value = !useInternet.value
  localStorage.setItem('dash_use_internet', String(useInternet.value))
}

// ── 검색 엔진 선택: 'searxng'(기본) | 'tavily' ──
// ddgs가 저장돼 있던 경우 searxng으로 마이그레이션
const _savedProvider = localStorage.getItem('dash_search_provider')
const searchProvider = ref(
  (_savedProvider === 'ddgs' || !_savedProvider) ? 'searxng' : _savedProvider
)
if (_savedProvider === 'ddgs' || !_savedProvider) {
  localStorage.setItem('dash_search_provider', 'searxng')
}

function setProvider(p) {
  searchProvider.value = p
  localStorage.setItem('dash_search_provider', p)
}

// ── 드래그로 채팅 패널 너비 조절 ──

// 채팅 패널 너비 (px) — 초기값은 localStorage 에서 복원, 없으면 화면의 40%
const defaultChatWidth = Math.round(window.innerWidth * 0.4)
const chatWidth = ref(
  parseInt(localStorage.getItem('dash_chat_width') || String(defaultChatWidth), 10)
)

// 드래그 상태
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartWidth = ref(0)

function onDragStart(e) {
  dragging.value = true
  dragStartX.value = e.clientX
  dragStartWidth.value = chatWidth.value
  // 드래그 중 텍스트 선택 방지
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
}

function onDragMove(e) {
  if (!dragging.value) return
  // 마우스가 오른쪽으로 이동 → 채팅 패널이 좁아짐
  const delta = dragStartX.value - e.clientX
  const newWidth = Math.min(
    Math.max(dragStartWidth.value + delta, 260), // 최소 260px
    window.innerWidth - 400,                       // 메인 최소 400px 보장
  )
  chatWidth.value = newWidth
}

function onDragEnd() {
  if (!dragging.value) return
  dragging.value = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  localStorage.setItem('dash_chat_width', String(chatWidth.value))
}

// 왼쪽 콘텐츠 영역 클릭 시 — 인터랙티브 요소가 아닌 곳이면 채팅창 포커스 복귀
function onContentClick(e) {
  const interactive = ['input', 'textarea', 'button', 'select', 'option', 'a', 'label']
  const tag = e.target.tagName.toLowerCase()
  const insideInteractive = e.target.closest(
    'button, a, input, textarea, select, label, [tabindex]:not([tabindex="-1"])'
  )
  if (!interactive.includes(tag) && !insideInteractive) {
    chatPanelRef.value?.focusInput()
  }
}

onMounted(() => {
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
})
</script>

<template>
  <div id="app-wrapper">
    <!-- 상단 네비게이션 바 -->
    <nav class="navbar">
      <div class="navbar-brand">
        <span class="brand-icon">⚡</span>
        <span class="brand-name">Dash</span>
      </div>

      <ul class="nav-links">
        <li>
          <RouterLink to="/" active-class="active" exact-active-class="active">대시보드</RouterLink>
        </li>
        <li>
          <RouterLink to="/schedules" active-class="active">스케줄</RouterLink>
        </li>
      </ul>

      <!-- 인터넷 검색 토글 + 검색 엔진 선택 -->
      <div class="internet-controls">
        <label class="internet-toggle" :class="{ active: useInternet }">
          <input
            type="checkbox"
            :checked="useInternet"
            @change="toggleInternet"
          />
          <span class="toggle-dot"></span>
          <span class="toggle-label">인터넷 검색</span>
        </label>

        <!-- 검색 엔진 선택 — 인터넷 ON 시에만 표시 -->
        <div v-if="useInternet" class="provider-selector">
          <button
            class="provider-btn"
            :class="{ active: searchProvider === 'searxng' }"
            @click="setProvider('searxng')"
            title="SearXNG — 로컬 인스턴스, 무제한, 빠름"
          >SearXNG</button>
          <button
            class="provider-btn"
            :class="{ active: searchProvider === 'tavily' }"
            @click="setProvider('tavily')"
            title="Tavily — 1크레딧/회, LLM 최적화 검색"
          >Tavily</button>
        </div>
      </div>
    </nav>

    <!-- 메인 콘텐츠 영역 + 채팅 패널 2분할 -->
    <div class="body-layout" :class="{ dragging }">

      <!-- 왼쪽: 페이지 라우터 뷰 — 비인터랙티브 영역 클릭 시 채팅창 포커스 복귀 -->
      <main ref="pageContentRef" class="page-content" @click="onContentClick">
        <RouterView />
      </main>

      <!-- 드래그 핸들 — 두 패널 사이 -->
      <div
        class="drag-handle"
        @mousedown="onDragStart"
        title="드래그하여 너비 조절"
      >
        <div class="drag-grip"></div>
      </div>

      <!-- 오른쪽: 채팅 패널 -->
      <aside class="chat-pane" :style="{ width: chatWidth + 'px' }">
        <ChatPanel
          ref="chatPanelRef"
          :use-internet="useInternet"
          :search-provider="searchProvider"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* 전체 레이아웃 래퍼 — 100%로 #app 높이 상속, overflow:hidden은 style.css에서 차단됨 */
#app-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

/* ── 네비게이션 바 ── */
.navbar {
  background: #ffffff;
  border-bottom: 1px solid #e0e0e0;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 100;
}

/* 브랜드 로고 */
.navbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}
.brand-icon { font-size: 20px; }
.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: #4a90d9;
  letter-spacing: -0.3px;
}

/* 네비게이션 링크 */
.nav-links {
  list-style: none;
  display: flex;
  gap: 4px;
  margin: 0;
  padding: 0;
}
.nav-links a {
  display: block;
  padding: 6px 16px;
  border-radius: 6px;
  text-decoration: none;
  color: #555;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}
.nav-links a:hover { background: #f0f0f0; color: #222; }
.nav-links a.active {
  background: #e8f0fd;
  color: #4a90d9;
  font-weight: 600;
}

/* ── 인터넷 검색 컨트롤 묶음 ── */
.internet-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

/* ── 인터넷 검색 토글 스위치 ── */
.internet-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  user-select: none;
}

/* ── 검색 엔진 선택 ── */
.provider-selector {
  display: flex;
  border: 1px solid #ddd;
  border-radius: 6px;
  overflow: hidden;
}

.provider-btn {
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  background: #f5f5f5;
  color: #888;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.provider-btn + .provider-btn {
  border-left: 1px solid #ddd;
}
.provider-btn:hover { background: #ebebeb; color: #444; }
.provider-btn.active {
  background: #4a90d9;
  color: #fff;
}
.internet-toggle input { display: none; }

/* 토글 슬라이더 */
.toggle-dot {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: #ccc;
  position: relative;
  transition: background 0.2s;
  flex-shrink: 0;
}
.toggle-dot::after {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  top: 3px;
  left: 3px;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.internet-toggle.active .toggle-dot {
  background: #22c55e;
}
.internet-toggle.active .toggle-dot::after {
  transform: translateX(16px);
}

.toggle-label {
  font-size: 13px;
  font-weight: 500;
  color: #555;
  white-space: nowrap;
}
.internet-toggle.active .toggle-label {
  color: #166534;
}

/* ── 2분할 바디 레이아웃 ── */
/* min-height:0 필수 — flex 자식이 overflow-y:auto로 독립 스크롤하려면 높이 축소 허용 필요 */
.body-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* 드래그 중에는 전체 영역에서 텍스트 선택 방지 */
.body-layout.dragging {
  user-select: none;
}

/* 왼쪽 메인 콘텐츠 영역 */
.page-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
  min-width: 0;
}

/* 드래그 핸들 */
.drag-handle {
  width: 8px;
  background: #e8e8e8;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s;
}
.drag-handle:hover,
.body-layout.dragging .drag-handle {
  background: #4a90d9;
}

/* 드래그 핸들 내 점 3개 */
.drag-grip {
  width: 4px;
  height: 40px;
  background: repeating-linear-gradient(
    to bottom,
    #bbb 0px, #bbb 3px,
    transparent 3px, transparent 7px
  );
  border-radius: 2px;
}
.drag-handle:hover .drag-grip,
.body-layout.dragging .drag-grip {
  background: repeating-linear-gradient(
    to bottom,
    rgba(255,255,255,0.7) 0px, rgba(255,255,255,0.7) 3px,
    transparent 3px, transparent 7px
  );
}

/* 오른쪽 채팅 패널 */
.chat-pane {
  flex-shrink: 0;
  overflow: hidden;
}
</style>
