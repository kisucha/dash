<!-- F005View.vue — F005 유튜브 컨텐츠 제작 채팅 기반 파이프라인 메인 페이지 -->
<!-- 작업 목록(cursor 기반 페이징) + 새 작업 생성 4단계 모달 -->
<!-- Step 1: AI 채팅에서 수집한 주제 + 컨텍스트 입력 (topic, user_context 필수) -->
<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useF005Store } from '../store/f005.js'
import StatusBadge from '../components/StatusBadge.vue'

const router = useRouter()
const route = useRoute()
const f005Store = useF005Store()

// ── 모달 상태 ──
// showModal: 새 작업 생성 모달 표시 여부
const showModal = ref(false)
// modalStep: 모달 현재 단계 (1~4)
const modalStep = ref(1)

// ── 모달 Step 1: 주제 및 배경 정보 ──
const topic = ref('')              // 필수 — 영상 주제
const userContext = ref('')        // 필수 — AI 채팅에서 수집한 컨텍스트 (최소 10자)
const channelCategory = ref('')    // 선택 — 채널 카테고리 (미입력 시 topic으로 대체)
const keywordsHint = ref('')       // 선택 — 추가 검색 키워드
const days = ref(7)                // 보완 검색 기간 (일)

// ── 채팅 컨텍스트 가져오기 힌트 메시지 ──
const chatContextHint = ref('')

// ── 모달 Step 2: 스크립트 설정 ──
const durationMin = ref(8)         // 영상 목표 길이 (분)
const channelTone = ref('informative')  // 채널 톤
const hookStyle = ref('question')  // 훅 스타일
const ctaType = ref('subscribe')   // CTA 유형

// ── 모달 Step 3: 미디어 설정 ──
const ttsProvider = ref('edge_tts')  // TTS 프로바이더
const ttsVoice = ref('ko-KR-SunHiNeural')  // TTS 목소리 ID
const ttsRate = ref('+0%')           // TTS 발화 속도 (edge_tts 전용)
const ttsPitch = ref('+0Hz')         // TTS 음성 피치 (edge_tts 전용)
const ttsSkip = ref(false)           // TTS 건너뜀 여부

// 프로바이더별 목소리 목록 (목소리 없는 프로바이더는 빈 배열)
const ttsVoiceOptions = computed(() => {
  switch (ttsProvider.value) {
    case 'edge_tts':
      return [
        { value: 'ko-KR-SunHiNeural', label: '선희 (여성)' },
        { value: 'ko-KR-InJoonNeural', label: '인준 (남성)' },
      ]
    case 'elevenlabs':
      return [
        { value: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel' },
        { value: 'AZnzlk1XvdvUeBnXmlld', label: 'Domi' },
        { value: 'EXAVITQu4vr4xnSDxMaL', label: 'Bella' },
        { value: 'ErXwobaYiN019PkySvjV', label: 'Antoni' },
        { value: 'VR6AewLTigWG4xSOukaG', label: 'Arnold' },
        { value: 'pNInz6obpgDQGcFmaJgB', label: 'Adam' },
      ]
    case 'openai':
      return [
        { value: 'alloy', label: 'Alloy' },
        { value: 'echo', label: 'Echo' },
        { value: 'fable', label: 'Fable' },
        { value: 'onyx', label: 'Onyx' },
        { value: 'nova', label: 'Nova' },
        { value: 'shimmer', label: 'Shimmer' },
      ]
    default:  // coqui, gtts — 목소리 선택 없음
      return []
  }
})

// 프로바이더 변경 시 첫 번째 목소리로 자동 초기화
watch(ttsProvider, () => {
  const opts = ttsVoiceOptions.value
  ttsVoice.value = opts.length > 0 ? opts[0].value : ''
})
const generationBackend = ref('comfyui')  // 영상 생성 백엔드
const skipMode = ref('')             // 스킵 모드 (stock 등)

// ── 모달 Step 4: 업로드 설정 ──
const uploadMode = ref('manual_approval')    // 업로드 모드 (manual_approval / auto)
const privacy = ref('private')      // 공개 범위

// ── 폼 유효성 오류 메시지 ──
const formError = ref('')

// ── 날짜 포맷 헬퍼 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── 채팅 컨텍스트 가져오기 — sessionStorage 우선, 없으면 URL 쿼리 파라미터 폴백 ──
function loadChatContext() {
  const fromSession = sessionStorage.getItem('f005_chat_context')
  const fromQuery = route.query.chatContext
  const chatContext = fromSession || fromQuery || ''
  if (chatContext) {
    userContext.value = chatContext
    chatContextHint.value = '채팅 컨텍스트가 자동으로 입력되었습니다.'
    // 1회 사용 후 세션 스토리지 삭제 (다음 번 모달 오픈 시 재입력 방지)
    sessionStorage.removeItem('f005_chat_context')
  } else {
    chatContextHint.value = 'AI 채팅 패널에서 컨텍스트를 먼저 복사하세요.'
  }
}

// ── 모달 열기 ──
function openModal() {
  modalStep.value = 1
  formError.value = ''
  chatContextHint.value = ''
  // 쿼리 파라미터로 전달된 채팅 컨텍스트가 있으면 자동 입력
  loadChatContext()
  showModal.value = true
}

// ── 모달 닫기 ──
function closeModal() {
  showModal.value = false
}

// ── 다음 단계 이동 (Step 1 → 2 → 3 → 4) ──
function nextStep() {
  formError.value = ''
  // Step 1 유효성 검사 — topic 필수, user_context 필수 + 최소 10자
  if (modalStep.value === 1) {
    if (!channelCategory.value.trim()) {
      formError.value = '채널 카테고리를 입력하세요.'
      return
    }
    if (!topic.value.trim() || topic.value.trim().length < 2) {
      formError.value = '주제를 2자 이상 입력하세요.'
      return
    }
    if (!userContext.value.trim()) {
      formError.value = '사용자 입력 컨텍스트를 입력하세요.'
      return
    }
    if (userContext.value.trim().length < 10) {
      formError.value = '컨텍스트는 최소 10자 이상 입력하세요.'
      return
    }
  }
  if (modalStep.value < 4) modalStep.value++
}

// ── 이전 단계 이동 ──
function prevStep() {
  formError.value = ''
  if (modalStep.value > 1) modalStep.value--
}

// ── 작업 생성 실행 ──
async function submitCreateJob() {
  formError.value = ''
  const params = {
    channel_category: channelCategory.value.trim(),
    topic: topic.value.trim(),
    user_context: userContext.value.trim(),
    ...(keywordsHint.value.trim() ? { keywords_hint: keywordsHint.value.trim() } : {}),
    days: days.value,
    duration_min: durationMin.value,
    channel_tone: channelTone.value,
    hook_style: hookStyle.value,
    cta_type: ctaType.value,
    tts_provider: ttsProvider.value,
    tts_voice: ttsVoice.value || undefined,
    tts_rate: ttsRate.value,
    tts_pitch: ttsPitch.value,
    tts_skip: ttsSkip.value,
    generation_backend: generationBackend.value,
    ...(skipMode.value ? { skip_mode: skipMode.value } : {}),
    upload_mode: uploadMode.value,
    privacy: privacy.value,
  }
  try {
    const job = await f005Store.createJob(params)
    closeModal()
    // 생성 후 상세 페이지로 이동
    router.push({ name: 'F005JobDetail', params: { jobId: job.id } })
  } catch {
    formError.value = f005Store.errorMsg || '작업 생성에 실패했습니다.'
  }
}

// ── 작업 행 클릭 → 상세 페이지 이동 ──
function goToJob(job) {
  router.push({ name: 'F005JobDetail', params: { jobId: job.id } })
}

// ── 작업 삭제 ──
async function deleteJob(job) {
  if (!confirm(`#${job.id} 작업을 삭제하시겠습니까?\n(관련 스테이지 데이터도 모두 삭제됩니다)`)) return
  try {
    await f005Store.deleteJob(job.id)
  } catch {
    alert('삭제에 실패했습니다.')
  }
}

// ── 마운트: 작업 목록 로드 + ChatPanel에서 넘어온 경우 모달 자동 열기 ──
onMounted(async () => {
  await f005Store.fetchJobs(20)
  // sessionStorage에 chatContext가 있으면 ChatPanel에서 넘어온 것 → 모달 자동 오픈
  if (sessionStorage.getItem('f005_chat_context')) {
    openModal()
  }
})
</script>

<template>
  <div class="f005-view">

    <!-- ── 페이지 헤더 ── -->
    <div class="page-header">
      <button class="back-btn" @click="router.push({ name: 'Dashboard' })">← 대시보드</button>
      <h1 class="page-title">유튜브 제작 (채팅 기반) <span class="badge-f005">F005</span></h1>
      <p class="page-desc">AI 채팅에서 수집한 정보를 기반으로 YouTube 컨텐츠를 자동 제작합니다.</p>
    </div>

    <!-- ── 오류 메시지 ── -->
    <div v-if="f005Store.errorMsg" class="error-box">{{ f005Store.errorMsg }}</div>

    <!-- ── 작업 목록 섹션 ── -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title">작업 목록</h2>
        <button class="btn-create" @click="openModal">+ 새 작업 생성</button>
      </div>

      <!-- 로딩 중 -->
      <div v-if="f005Store.loading && f005Store.jobs.length === 0" class="empty-text">
        로딩 중...
      </div>

      <!-- 작업 없음 -->
      <div v-else-if="f005Store.jobs.length === 0" class="empty-text">
        생성된 F005 작업이 없습니다. 새 작업을 생성하세요.
      </div>

      <!-- 작업 테이블 -->
      <table v-else class="board-table">
        <colgroup>
          <col style="width: 60px" />
          <col style="width: 110px" />
          <col />
          <col style="width: 150px" />
          <col style="width: 145px" />
          <col style="width: 60px" />
          <col style="width: 40px" />
        </colgroup>
        <thead>
          <tr>
            <th class="center">ID</th>
            <th class="center">상태</th>
            <th>주제</th>
            <th>현재 스테이지</th>
            <th>생성 일시</th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in f005Store.jobs"
            :key="job.id"
            class="clickable-row"
            @click="goToJob(job)"
          >
            <td class="center job-id-cell">#{{ job.id }}</td>
            <td class="center">
              <StatusBadge :status="job.status" />
            </td>
            <td class="category-cell">{{ job.channel_category ?? '-' }}</td>
            <td class="stage-cell">{{ job.current_stage ?? '-' }}</td>
            <td class="time-cell">{{ formatDate(job.created_at) }}</td>
            <td class="center" @click.stop>
              <button class="btn-detail" @click="goToJob(job)">상세</button>
            </td>
            <td class="center" @click.stop>
              <button
                class="btn-delete"
                title="작업 삭제"
                @click="deleteJob(job)"
              >🗑</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 더 보기 버튼 (cursor 기반 페이징) -->
      <div v-if="f005Store.hasMore" class="load-more-wrap">
        <button
          class="btn-load-more"
          :disabled="f005Store.loading"
          @click="f005Store.fetchMoreJobs(20)"
        >
          {{ f005Store.loading ? '로딩 중...' : '더 보기' }}
        </button>
      </div>
    </section>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 새 작업 생성 모달 — CSS position:fixed 오버레이 -->
    <!-- ══════════════════════════════════════════════ -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-box">

        <!-- 모달 헤더 -->
        <div class="modal-header">
          <h2 class="modal-title">새 F005 작업 생성</h2>
          <button class="modal-close" @click="closeModal">✕</button>
        </div>

        <!-- 단계 탭 표시 -->
        <div class="modal-steps">
          <div
            v-for="n in 4"
            :key="n"
            class="modal-step-dot"
            :class="{ active: modalStep === n, done: modalStep > n }"
          >
            <span class="dot-num">{{ n }}</span>
            <span class="dot-label">{{ ['주제/컨텍스트', '스크립트', '미디어', '업로드'][n - 1] }}</span>
          </div>
        </div>

        <!-- 오류 메시지 -->
        <div v-if="formError" class="form-error">{{ formError }}</div>

        <!-- ── Step 1: 기본 설정 — 채널/주제/컨텍스트 ── -->
        <div v-show="modalStep === 1" class="modal-body">
          <h3 class="step-subtitle">기본 설정</h3>

          <!-- 채팅 컨텍스트 가져오기 버튼 -->
          <div class="chat-import-bar">
            <button class="btn-chat-import" @click="loadChatContext">채팅 내용 가져오기</button>
            <span v-if="chatContextHint" class="chat-import-hint">{{ chatContextHint }}</span>
          </div>

          <!-- 채널 카테고리 (필수) -->
          <div class="form-item required-item">
            <label class="form-label">채널 카테고리 <span class="required-mark">*</span></label>
            <input
              type="text"
              v-model="channelCategory"
              class="form-input"
              placeholder="예: IT/기술, 금융/재테크, 건강/운동"
            />
            <p class="field-hint">콘텐츠 발굴 및 스크립트 방향에 사용됩니다.</p>
          </div>

          <!-- 주제 (필수, min 2자) -->
          <div class="form-item required-item">
            <label class="form-label">주제 <span class="required-mark">*</span></label>
            <input
              type="text"
              v-model="topic"
              class="form-input"
              placeholder="예: 비트코인 2025 전망, 파이썬 비동기 프로그래밍 입문"
            />
            <p class="field-hint">영상에서 다룰 핵심 주제를 입력하세요. (2자 이상)</p>
          </div>

          <!-- 사용자 입력 컨텍스트 (필수, 최소 10자) -->
          <div class="form-item required-item">
            <label class="form-label">컨텍스트 정보 <span class="required-mark">*</span></label>
            <textarea
              v-model="userContext"
              class="form-textarea"
              rows="6"
              placeholder="AI 채팅에서 확인한 정보, 메모, 조사 내용을 자유롭게 입력하세요. (10자 이상)"
            ></textarea>
            <p class="field-hint">ChatGPT, Claude 등 AI 채팅에서 리서치한 내용을 붙여넣으세요. 스크립트 품질에 직결됩니다. (최대 50,000자)</p>
          </div>

          <div class="form-grid">
            <!-- 추가 검색 키워드 (선택) -->
            <div class="form-item">
              <label class="form-label">키워드 힌트 <span class="optional-mark">(선택)</span></label>
              <input
                type="text"
                v-model="keywordsHint"
                class="form-input"
                placeholder="추가 검색 키워드 힌트"
              />
            </div>

            <!-- 보완 검색 기간 -->
            <div class="form-item">
              <label class="form-label">검색 기간 (일) <span class="optional-mark">(선택)</span></label>
              <input type="number" v-model.number="days" min="1" max="90" class="form-input" />
              <p class="field-hint">보완 리서치에 사용할 기간</p>
            </div>
          </div>
        </div>

        <!-- ── Step 2: 스크립트 설정 ── -->
        <div v-show="modalStep === 2" class="modal-body">
          <h3 class="step-subtitle">스크립트 설정</h3>

          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">영상 목표 길이 (분)</label>
              <input type="number" v-model.number="durationMin" min="3" max="60" class="form-input" />
            </div>
            <div class="form-item">
              <label class="form-label">채널 톤</label>
              <select v-model="channelTone" class="form-select">
                <option value="informative">정보 전달형</option>
                <option value="entertaining">엔터테인먼트형</option>
                <option value="educational">교육형</option>
                <option value="conversational">대화형</option>
                <option value="professional">전문가형</option>
              </select>
            </div>
            <div class="form-item">
              <label class="form-label">훅 스타일</label>
              <select v-model="hookStyle" class="form-select">
                <option value="question">질문형</option>
                <option value="statistic">통계/수치형</option>
                <option value="story">스토리텔링형</option>
                <option value="problem">문제 제기형</option>
                <option value="shock">충격/반전형</option>
              </select>
            </div>
            <div class="form-item">
              <label class="form-label">CTA 유형</label>
              <select v-model="ctaType" class="form-select">
                <option value="subscribe">구독 유도</option>
                <option value="like">좋아요 유도</option>
                <option value="comment">댓글 유도</option>
                <option value="next_video">다음 영상 연결</option>
              </select>
            </div>
          </div>
        </div>

        <!-- ── Step 3: 미디어 설정 ── -->
        <div v-show="modalStep === 3" class="modal-body">
          <h3 class="step-subtitle">미디어 설정</h3>

          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">TTS 프로바이더</label>
              <select v-model="ttsProvider" class="form-select" :disabled="ttsSkip">
                <option value="edge_tts">Edge TTS (무료, 인터넷)</option>
                <option value="gtts">Google TTS (무료, 인터넷)</option>
                <option value="coqui">Coqui TTS (로컬)</option>
                <option value="elevenlabs">ElevenLabs (API 키 필요)</option>
                <option value="openai">OpenAI TTS (API 키 필요)</option>
              </select>
            </div>
            <div class="form-item">
              <label class="form-label">
                TTS 목소리
                <span v-if="ttsVoiceOptions.length === 0" class="optional-mark">(해당 없음)</span>
              </label>
              <select
                v-if="ttsVoiceOptions.length > 0"
                v-model="ttsVoice"
                class="form-select"
                :disabled="ttsSkip"
              >
                <option v-for="opt in ttsVoiceOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <div v-else class="voice-na">자동 선택</div>
            </div>
            <div class="form-item" v-if="ttsProvider === 'edge_tts' && !ttsSkip">
              <label class="form-label">발화 속도 <span class="optional-mark">(Edge TTS)</span></label>
              <select v-model="ttsRate" class="form-select">
                <option value="-20%">느리게 (0.8배)</option>
                <option value="+0%">보통 (기본)</option>
                <option value="+10%">약간 빠르게 (1.1배)</option>
                <option value="+20%">빠르게 (1.2배)</option>
                <option value="+30%">매우 빠르게 (1.3배)</option>
              </select>
            </div>
            <div class="form-item" v-if="ttsProvider === 'edge_tts' && !ttsSkip">
              <label class="form-label">음성 피치 <span class="optional-mark">(Edge TTS)</span></label>
              <select v-model="ttsPitch" class="form-select">
                <option value="-10Hz">낮게</option>
                <option value="+0Hz">보통 (기본)</option>
                <option value="+10Hz">높게</option>
              </select>
            </div>
            <div class="form-item">
              <label class="form-label">TTS 건너뜀</label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="ttsSkip" />
                <span>TTS 단계 건너뜀</span>
              </label>
              <p class="field-hint">음성 없이 영상만 생성할 때 선택</p>
            </div>
            <div class="form-item">
              <label class="form-label">영상 생성 백엔드</label>
              <select v-model="generationBackend" class="form-select">
                <option value="comfyui">ComfyUI</option>
                <option value="stable_diffusion">Stable Diffusion</option>
                <option value="skip">건너뜀</option>
              </select>
            </div>
            <div class="form-item">
              <label class="form-label">스킵 모드 <span class="optional-mark">(선택)</span></label>
              <select v-model="skipMode" class="form-select">
                <option value="">없음</option>
                <option value="text_slide">텍스트 슬라이드</option>
                <option value="script_only">스크립트만 (영상 없음)</option>
              </select>
            </div>
          </div>
        </div>

        <!-- ── Step 4: 업로드 설정 ── -->
        <div v-show="modalStep === 4" class="modal-body">
          <h3 class="step-subtitle">업로드 설정</h3>

          <div class="form-grid">
            <div class="form-item">
              <label class="form-label">업로드 모드</label>
              <select v-model="uploadMode" class="form-select">
                <option value="manual_approval">수동 승인 후 업로드</option>
                <option value="auto">자동 업로드</option>
                <option value="skip">업로드 없음 (파일만 생성)</option>
              </select>
              <p class="field-hint">수동 승인: SEO 검토 후 직접 업로드 버튼 클릭</p>
            </div>
            <div class="form-item">
              <label class="form-label">공개 범위</label>
              <select v-model="privacy" class="form-select">
                <option value="private">비공개</option>
                <option value="unlisted">링크 공유</option>
                <option value="public">공개</option>
              </select>
            </div>
          </div>

          <!-- 설정 요약 -->
          <div class="summary-box">
            <h4 class="summary-title">설정 요약</h4>
            <div class="summary-row">
              <span>채널 카테고리</span>
              <strong>{{ channelCategory || '-' }}</strong>
            </div>
            <div class="summary-row">
              <span>주제</span>
              <strong>{{ topic || '-' }}</strong>
            </div>
            <div class="summary-row">
              <span>컨텍스트 길이</span>
              <strong>{{ userContext.trim().length }}자</strong>
            </div>
            <div class="summary-row">
              <span>검색 기간</span>
              <strong>{{ days }}일</strong>
            </div>
            <div class="summary-row">
              <span>영상 길이</span>
              <strong>{{ durationMin }}분</strong>
            </div>
            <div class="summary-row">
              <span>채널 톤</span>
              <strong>{{ channelTone }}</strong>
            </div>
            <div class="summary-row">
              <span>TTS</span>
              <strong>{{ ttsSkip ? '건너뜀' : ttsProvider }}</strong>
            </div>
            <div v-if="!ttsSkip && ttsVoiceOptions.length > 0" class="summary-row">
              <span>TTS 목소리</span>
              <strong>{{ ttsVoiceOptions.find(o => o.value === ttsVoice)?.label || ttsVoice }}</strong>
            </div>
            <div v-if="!ttsSkip && ttsProvider === 'edge_tts'" class="summary-row">
              <span>속도 / 피치</span>
              <strong>{{ ttsRate }} / {{ ttsPitch }}</strong>
            </div>
            <div class="summary-row">
              <span>영상 생성</span>
              <strong>{{ generationBackend }}</strong>
            </div>
            <div class="summary-row">
              <span>업로드 모드 / 공개</span>
              <strong>{{ uploadMode }} / {{ privacy }}</strong>
            </div>
          </div>
        </div>

        <!-- 모달 하단 네비게이션 버튼 -->
        <div class="modal-footer">
          <button v-if="modalStep > 1" class="btn-modal-back" @click="prevStep">← 이전</button>
          <div class="footer-spacer"></div>
          <button v-if="modalStep < 4" class="btn-modal-next" @click="nextStep">다음 →</button>
          <button
            v-else
            class="btn-modal-create"
            :disabled="f005Store.loading"
            @click="submitCreateJob"
          >
            {{ f005Store.loading ? '생성 중...' : '작업 생성' }}
          </button>
        </div>

      </div>
    </div>

  </div>
</template>

<style scoped>
/* 페이지 래퍼 */
.f005-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── 페이지 헤더 ── */
.page-header { margin-bottom: 4px; }

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

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #222;
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* F005 배지 — 보라색 계열 */
.badge-f005 {
  font-size: 12px;
  font-weight: 600;
  background: #ede9fe;
  color: #7c3aed;
  padding: 2px 8px;
  border-radius: 10px;
}

.page-desc {
  font-size: 14px;
  color: #666;
  margin: 0;
}

/* ── 오류 박스 ── */
.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
}

/* ── 섹션 공통 ── */
.section {
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #222;
  margin: 0;
}

/* 새 작업 생성 버튼 — 보라색 계열 */
.btn-create {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s;
}
.btn-create:hover { background: #6d28d9; }

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
  margin-top: 14px;
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

.board-table tbody tr:last-child td { border-bottom: none; }

.clickable-row {
  cursor: pointer;
  transition: background 0.12s;
}
.clickable-row:hover td { background: #f5f3ff; }

.center { text-align: center; }

.job-id-cell {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #7c3aed;
}

.category-cell {
  font-weight: 500;
  color: #222;
}

.stage-cell {
  font-size: 12px;
  font-family: monospace;
  color: #666;
}

.time-cell {
  font-size: 13px;
  color: #666;
}

.btn-detail {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #ddd;
  border-radius: 5px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-detail:hover {
  background: #7c3aed;
  color: #fff;
  border-color: #7c3aed;
}

.btn-delete {
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
  color: #ccc;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.12s;
}
.btn-delete:hover { color: #ef4444; }

/* 더 보기 버튼 */
.load-more-wrap {
  text-align: center;
  padding: 12px 0 0;
}

.btn-load-more {
  font-size: 13px;
  padding: 7px 24px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-load-more:hover:not(:disabled) {
  background: #f5f3ff;
  border-color: #7c3aed;
  color: #7c3aed;
}
.btn-load-more:disabled { opacity: 0.5; cursor: not-allowed; }

/* ══════════════════════════════════════════════ */
/* ── 모달 오버레이 ──                             */
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

/* 모달 박스 */
.modal-box {
  background: #fff;
  border-radius: 12px;
  width: 600px;
  max-width: calc(100vw - 40px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
}

/* 모달 헤더 */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 14px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.modal-title {
  font-size: 17px;
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
  padding: 0 4px;
  line-height: 1;
}
.modal-close:hover { color: #333; }

/* 단계 표시 도트 */
.modal-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 14px 22px 10px;
  border-bottom: 1px solid #f5f5f5;
  flex-shrink: 0;
}

.modal-step-dot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
  position: relative;
}

/* 단계 도트 사이 연결선 */
.modal-step-dot:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 13px;
  left: calc(50% + 13px);
  width: calc(100% - 26px);
  height: 2px;
  background: #e0e0e0;
  z-index: 0;
}

.modal-step-dot.done::after { background: #c4b5fd; }

.dot-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: #f0f0f0;
  color: #aaa;
  border: 2px solid #e0e0e0;
  z-index: 1;
  position: relative;
  transition: all 0.15s;
}

.modal-step-dot.active .dot-num {
  background: #7c3aed;
  color: #fff;
  border-color: #7c3aed;
}

.modal-step-dot.done .dot-num {
  background: #8b5cf6;
  color: #fff;
  border-color: #8b5cf6;
}

.dot-label {
  font-size: 11px;
  color: #aaa;
  white-space: nowrap;
}

.modal-step-dot.active .dot-label { color: #7c3aed; font-weight: 600; }
.modal-step-dot.done .dot-label { color: #6d28d9; }

/* 폼 오류 메시지 */
.form-error {
  background: #fee2e2;
  color: #991b1b;
  padding: 8px 16px;
  font-size: 13px;
  border-bottom: 1px solid #fecaca;
  flex-shrink: 0;
}

/* 모달 본문 */
.modal-body {
  padding: 18px 22px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.step-subtitle {
  font-size: 15px;
  font-weight: 700;
  color: #333;
  margin: 0 0 4px;
}

/* 채팅 컨텍스트 가져오기 바 */
.chat-import-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #f5f3ff;
  border: 1px solid #ddd6fe;
  border-radius: 8px;
}

.btn-chat-import {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 14px;
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s;
}
.btn-chat-import:hover { background: #6d28d9; }

.chat-import-hint {
  font-size: 12px;
  color: #6d28d9;
}

/* 폼 공통 */
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.required-item { grid-column: 1 / -1; }

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
}

.required-mark { color: #ef4444; }
.optional-mark { color: #aaa; font-weight: normal; font-size: 11px; }

.form-input {
  padding: 7px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  background: #fff;
}

.form-input:focus {
  outline: none;
  border-color: #7c3aed;
}

.form-textarea {
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  resize: vertical;
  font-family: inherit;
  background: #fff;
  line-height: 1.6;
}

.form-textarea:focus {
  outline: none;
  border-color: #7c3aed;
}

.form-select {
  padding: 7px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  background: #fff;
}

.form-select:focus {
  outline: none;
  border-color: #7c3aed;
}

.form-select:disabled { background: #f5f5f5; color: #aaa; }

.field-hint {
  font-size: 11px;
  color: #aaa;
  margin: 2px 0 0;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #444;
  cursor: pointer;
  padding: 5px 0;
}

.voice-na {
  padding: 7px 10px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  font-size: 13px;
  color: #aaa;
  background: #f9f9f9;
}

/* ── 설정 요약 카드 ── */
.summary-box {
  background: #f5f3ff;
  border: 1px solid #ddd6fe;
  border-radius: 8px;
  padding: 14px 16px;
  margin-top: 4px;
}

.summary-title {
  font-size: 13px;
  font-weight: 700;
  color: #555;
  margin: 0 0 10px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 4px 0;
  border-bottom: 1px solid #ede9fe;
}
.summary-row:last-child { border-bottom: none; }
.summary-row span { color: #666; }
.summary-row strong { color: #222; }

/* ── 모달 하단 ── */
.modal-footer {
  display: flex;
  align-items: center;
  padding: 14px 22px 18px;
  border-top: 1px solid #f0f0f0;
  gap: 10px;
  flex-shrink: 0;
}

.footer-spacer { flex: 1; }

.btn-modal-back {
  background: #fff;
  border: 1.5px solid #ddd;
  color: #555;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-modal-back:hover { background: #f5f5f5; }

.btn-modal-next {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-modal-next:hover { background: #6d28d9; }

.btn-modal-create {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 22px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s;
}
.btn-modal-create:hover:not(:disabled) { background: #6d28d9; }
.btn-modal-create:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
