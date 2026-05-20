<!-- F007View.vue — F007 YouTube 자동화 파이프라인 V5 메인 페이지 -->
<!-- 채널 유형(finance/language) 탭 필터 + 3단계 작업 생성 모달 -->
<!-- Step 1: 채널 설정, Step 2: 미디어 설정, Step 3: 업로드 설정 + 요약 -->
<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useF007Store } from '../store/f007.js'
import StatusBadge from '../components/StatusBadge.vue'

const router = useRouter()
const f007Store = useF007Store()

// ── 탭 필터 ──
// activeTab: null=전체, 'finance'=금융/경제, 'language'=언어학습
const activeTab = ref(null)

// ── 모달 상태 ──
const showModal = ref(false)
// modalStep: 모달 현재 단계 (1~3)
const modalStep = ref(1)

// ── 폼 오류 메시지 ──
const formError = ref('')

// ── Step 1: 채널 설정 ──
// channel_type: 채널 유형 라디오 선택 (finance/language)
const channelType = ref('finance')
// channel_name: 채널 이름 (선택)
const channelName = ref('')
// keywords_hint: 추가 검색 키워드 힌트 (선택)
const keywordsHint = ref('')
// days: 보완 검색 기간 (1~14일, 기본 3)
const days = ref(3)

// ── Step 2: 미디어 설정 ──
// tts_provider: TTS 프로바이더 선택
const ttsProvider = ref('supertone3')
// tts_voice: TTS 목소리 선택
const ttsVoice = ref('F1')
// tts_skip: TTS 건너뜀 여부
const ttsSkip = ref(false)
// slide_theme: 슬라이드 테마 선택
const slideTheme = ref('dark_blue')
// bgm_path: 배경 음악 선택 ('random'=랜덤, ''=없음)
const bgmPath = ref('random')
// bgm_volume: 배경 음악 볼륨 (0~1, step 0.05)
const bgmVolume = ref(0.15)

// ── Step 3: 업로드 설정 ──
// upload_mode: 업로드 모드 선택
const uploadMode = ref('manual_approval')
// privacy: 공개 범위 선택
const privacy = ref('private')

// ── TTS 목소리 옵션 ──
// supertone3: F1/F2/F3/M1/M2, coqui/pyttsx3: 목소리 선택 없음
const ttsVoiceOptions = computed(() => {
  if (ttsProvider.value === 'supertone3') {
    return [
      { value: 'F1', label: 'F1 (여성)' },
      { value: 'F2', label: 'F2 (여성)' },
      { value: 'F3', label: 'F3 (여성)' },
      { value: 'M1', label: 'M1 (남성)' },
      { value: 'M2', label: 'M2 (남성)' },
    ]
  }
  return []
})

// ttsProvider 변경 시 첫 번째 목소리로 자동 초기화
watch(ttsProvider, () => {
  const opts = ttsVoiceOptions.value
  ttsVoice.value = opts.length > 0 ? opts[0].value : ''
})

// ── finance 채널 선택 시 upload_mode 강제 manual_approval ──
watch(channelType, (val) => {
  if (val === 'finance') {
    uploadMode.value = 'manual_approval'
  }
})

// ── 날짜 포맷 헬퍼 ──
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── 채널 유형 레이블 ──
function channelTypeLabel(type) {
  if (type === 'finance') return '금융/경제'
  if (type === 'language') return '언어학습'
  return type ?? '-'
}

// ── 탭 클릭 — 필터 변경 후 목록 재조회 ──
async function onTabClick(tab) {
  activeTab.value = tab
  f007Store.channelTypeFilter.value = tab
  await f007Store.fetchJobs(20, tab, null)
}

// ── 모달 열기 ──
function openModal() {
  modalStep.value = 1
  formError.value = ''
  // 기본값 초기화
  channelType.value = 'finance'
  channelName.value = ''
  keywordsHint.value = ''
  days.value = 3
  ttsProvider.value = 'supertone3'
  ttsVoice.value = 'F1'
  ttsSkip.value = false
  slideTheme.value = 'dark_blue'
  bgmPath.value = 'random'
  bgmVolume.value = 0.15
  uploadMode.value = 'manual_approval'
  privacy.value = 'private'
  showModal.value = true
}

// ── 모달 닫기 ──
function closeModal() {
  showModal.value = false
}

// ── 다음 단계 이동 ──
function nextStep() {
  formError.value = ''
  // Step 1 유효성 검사 없음 (channel_type 라디오는 항상 선택됨)
  if (modalStep.value < 3) modalStep.value++
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
    channel_type: channelType.value,
    ...(channelName.value.trim() ? { channel_name: channelName.value.trim() } : {}),
    ...(keywordsHint.value.trim() ? { keywords_hint: keywordsHint.value.trim() } : {}),
    days: days.value,
    tts_provider: ttsProvider.value,
    ...(ttsVoice.value ? { tts_voice: ttsVoice.value } : {}),
    tts_skip: ttsSkip.value,
    slide_theme: slideTheme.value,
    ...(bgmPath.value ? { bgm_path: bgmPath.value } : {}),
    bgm_volume: bgmVolume.value,
    upload_mode: uploadMode.value,
    privacy: privacy.value,
  }
  try {
    const job = await f007Store.createJob(params)
    closeModal()
    // 생성 후 상세 페이지로 이동
    router.push({ name: 'F007JobDetail', params: { jobId: job.id } })
  } catch {
    formError.value = f007Store.errorMsg || '작업 생성에 실패했습니다.'
  }
}

// ── 작업 행 클릭 → 상세 페이지 이동 ──
function goToJob(job) {
  router.push({ name: 'F007JobDetail', params: { jobId: job.id } })
}

// ── 작업 삭제 ──
async function deleteJob(job) {
  if (!confirm(`#${job.id} 작업을 삭제하시겠습니까?\n(관련 스테이지 데이터도 모두 삭제됩니다)`)) return
  try {
    await f007Store.deleteJob(job.id)
  } catch {
    alert('삭제에 실패했습니다.')
  }
}

// ── 볼륨 퍼센트 표시 ──
const bgmVolumePercent = computed(() => Math.round(bgmVolume.value * 100) + '%')

// ── 업로드 모드 레이블 ──
const uploadModeLabel = computed(() => {
  const map = { manual_approval: '수동 승인', auto: '자동', skip: '건너뛰기' }
  return map[uploadMode.value] ?? uploadMode.value
})

// ── 마운트: 작업 목록 로드 ──
onMounted(async () => {
  await f007Store.fetchJobs(20, null, null)
})
</script>

<template>
  <div class="f007-view">

    <!-- ── 페이지 헤더 ── -->
    <div class="page-header">
      <button class="back-btn" @click="router.push({ name: 'Dashboard' })">← 대시보드</button>
      <h1 class="page-title">YouTube 자동화 파이프라인 v5 <span class="badge-f007">F007</span></h1>
      <p class="page-desc">채널 유형(금융/경제, 언어학습)에 따라 주제를 자동 발굴하고 YouTube 컨텐츠를 제작합니다.</p>
    </div>

    <!-- ── 오류 메시지 ── -->
    <div v-if="f007Store.errorMsg" class="error-box">{{ f007Store.errorMsg }}</div>

    <!-- ── 작업 목록 섹션 ── -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title">작업 목록</h2>
        <button class="btn-create" @click="openModal">+ 새 작업 만들기</button>
      </div>

      <!-- 채널 유형 탭 필터 -->
      <div class="tab-bar">
        <button
          class="tab-btn"
          :class="{ active: activeTab === null }"
          @click="onTabClick(null)"
        >전체</button>
        <button
          class="tab-btn finance"
          :class="{ active: activeTab === 'finance' }"
          @click="onTabClick('finance')"
        >금융/경제</button>
        <button
          class="tab-btn language"
          :class="{ active: activeTab === 'language' }"
          @click="onTabClick('language')"
        >언어학습</button>
      </div>

      <!-- 로딩 중 -->
      <div v-if="f007Store.loading && f007Store.jobs.length === 0" class="empty-text">
        로딩 중...
      </div>

      <!-- 작업 없음 -->
      <div v-else-if="f007Store.jobs.length === 0" class="empty-text">
        생성된 F007 작업이 없습니다. 새 작업을 만드세요.
      </div>

      <!-- 작업 테이블 -->
      <table v-else class="board-table">
        <colgroup>
          <col style="width: 60px" />
          <col style="width: 110px" />
          <col style="width: 110px" />
          <col />
          <col style="width: 145px" />
          <col style="width: 60px" />
          <col style="width: 40px" />
        </colgroup>
        <thead>
          <tr>
            <th class="center">ID</th>
            <th class="center">상태</th>
            <th class="center">채널 유형</th>
            <th>현재 스테이지</th>
            <th>생성 일시</th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in f007Store.jobs"
            :key="job.id"
            class="clickable-row"
            @click="goToJob(job)"
          >
            <td class="center job-id-cell">#{{ job.id }}</td>
            <td class="center">
              <StatusBadge :status="job.status" />
            </td>
            <td class="center">
              <span
                class="channel-type-tag"
                :class="job.channel_type === 'finance' ? 'finance' : 'language'"
              >{{ channelTypeLabel(job.channel_type) }}</span>
            </td>
            <td class="stage-cell">{{ job.current_stage ?? '-' }}</td>
            <td class="time-cell">{{ formatDate(job.created_at) }}</td>
            <td class="center" @click.stop>
              <button class="btn-detail" @click="goToJob(job)">상세</button>
            </td>
            <td class="center" @click.stop>
              <button class="btn-delete" title="작업 삭제" @click="deleteJob(job)">X</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 더 불러오기 버튼 (cursor 기반 페이징) -->
      <div v-if="f007Store.hasMore" class="load-more-wrap">
        <button
          class="btn-load-more"
          :disabled="f007Store.loading"
          @click="f007Store.fetchMoreJobs(20)"
        >
          {{ f007Store.loading ? '로딩 중...' : '더 불러오기' }}
        </button>
      </div>
    </section>

    <!-- ══════════════════════════════════════════════ -->
    <!-- 새 작업 생성 모달 — 3단계 설정 위저드           -->
    <!-- ══════════════════════════════════════════════ -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-box">

        <!-- 모달 헤더 -->
        <div class="modal-header">
          <h2 class="modal-title">새 F007 작업 만들기</h2>
          <button class="modal-close" @click="closeModal">X</button>
        </div>

        <!-- 단계 표시 도트 -->
        <div class="modal-steps">
          <div
            v-for="n in 3"
            :key="n"
            class="modal-step-dot"
            :class="{ active: modalStep === n, done: modalStep > n }"
          >
            <span class="dot-num">{{ n }}</span>
            <span class="dot-label">{{ ['채널 설정', '미디어 설정', '업로드 설정'][n - 1] }}</span>
          </div>
        </div>

        <!-- 폼 오류 메시지 -->
        <div v-if="formError" class="form-error">{{ formError }}</div>

        <!-- ── Step 1: 채널 설정 ── -->
        <div v-show="modalStep === 1" class="modal-body">
          <h3 class="step-subtitle">채널 설정</h3>

          <!-- 채널 유형 라디오 (필수) -->
          <div class="form-item full-width">
            <label class="form-label">채널 유형 <span class="required-mark">*</span></label>
            <div class="radio-group">
              <label class="radio-label" :class="{ selected: channelType === 'finance' }">
                <input type="radio" v-model="channelType" value="finance" />
                <span class="radio-type-tag finance">금융/경제</span>
                <span class="radio-desc">주식, 경제, 재테크 관련 컨텐츠</span>
              </label>
              <label class="radio-label" :class="{ selected: channelType === 'language' }">
                <input type="radio" v-model="channelType" value="language" />
                <span class="radio-type-tag language">언어학습</span>
                <span class="radio-desc">영어, 일본어 등 언어 학습 컨텐츠</span>
              </label>
            </div>
          </div>

          <!-- finance 채널 경고 배너 -->
          <div v-if="channelType === 'finance'" class="warning-banner">
            <span class="warning-icon">!</span>
            <span class="warning-text">금융 채널은 업로드 전 수동 검토가 필요합니다. 업로드 모드가 자동으로 수동 승인으로 설정됩니다.</span>
          </div>

          <div class="form-grid">
            <!-- 채널 이름 (선택) -->
            <div class="form-item">
              <label class="form-label">채널 이름 <span class="optional-mark">(선택)</span></label>
              <input
                type="text"
                v-model="channelName"
                class="form-input"
                placeholder="예: 누구나 쉽게 배우는 경제"
              />
              <p class="field-hint">슬라이드 헤더에 표시될 채널 브랜드명</p>
            </div>

            <!-- 키워드 힌트 (선택) -->
            <div class="form-item">
              <label class="form-label">키워드 힌트 <span class="optional-mark">(선택)</span></label>
              <input
                type="text"
                v-model="keywordsHint"
                class="form-input"
                placeholder="추가 검색 키워드 힌트"
              />
              <p class="field-hint">주제 발굴 시 참고할 추가 키워드</p>
            </div>

            <!-- 보완 검색 기간 -->
            <div class="form-item">
              <label class="form-label">검색 기간 (일)</label>
              <input
                type="number"
                v-model.number="days"
                min="1"
                max="14"
                class="form-input"
              />
              <p class="field-hint">최근 N일 이내 트렌드 기반 주제 발굴 (1~14일)</p>
            </div>
          </div>
        </div>

        <!-- ── Step 2: 미디어 설정 ── -->
        <div v-show="modalStep === 2" class="modal-body">
          <h3 class="step-subtitle">미디어 설정</h3>

          <div class="form-grid">
            <!-- TTS 프로바이더 -->
            <div class="form-item">
              <label class="form-label">TTS 프로바이더</label>
              <select v-model="ttsProvider" class="form-select" :disabled="ttsSkip">
                <option value="supertone3">Supertone3 (로컬, 고품질)</option>
                <option value="coqui">Coqui TTS (로컬)</option>
                <option value="pyttsx3">pyttsx3 (로컬, 기본)</option>
              </select>
            </div>

            <!-- TTS 목소리 (supertone3만 선택 가능) -->
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

            <!-- TTS 건너뜀 -->
            <div class="form-item">
              <label class="form-label">TTS 건너뜀</label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="ttsSkip" />
                <span>TTS 단계 건너뜀</span>
              </label>
              <p class="field-hint">음성 없이 영상만 생성할 때 선택</p>
            </div>

            <!-- 슬라이드 테마 -->
            <div class="form-item">
              <label class="form-label">슬라이드 테마</label>
              <select v-model="slideTheme" class="form-select">
                <option value="dark_blue">다크 블루 (기본)</option>
                <option value="clean_white">클린 화이트 (밝은)</option>
                <option value="warm_gray">웜 그레이 (고급)</option>
              </select>
            </div>

            <!-- 배경 음악 -->
            <div class="form-item">
              <label class="form-label">배경 음악 (BGM)</label>
              <select v-model="bgmPath" class="form-select">
                <option value="random">랜덤 선택</option>
                <option value="">없음</option>
              </select>
            </div>

            <!-- BGM 볼륨 -->
            <div class="form-item">
              <label class="form-label">BGM 볼륨 <span class="volume-pct">{{ bgmVolumePercent }}</span></label>
              <input
                type="range"
                v-model.number="bgmVolume"
                min="0"
                max="1"
                step="0.05"
                class="form-range"
                :disabled="!bgmPath"
              />
              <div class="range-labels">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Step 3: 업로드 설정 + 요약 ── -->
        <div v-show="modalStep === 3" class="modal-body">
          <h3 class="step-subtitle">업로드 설정</h3>

          <div class="form-grid">
            <!-- 업로드 모드 — finance 채널은 강제 manual_approval + 비활성 -->
            <div class="form-item">
              <label class="form-label">업로드 모드</label>
              <select
                v-model="uploadMode"
                class="form-select"
                :disabled="channelType === 'finance'"
              >
                <option value="manual_approval">수동 승인 후 업로드</option>
                <option value="auto">자동 업로드</option>
                <option value="skip">건너뛰기 (파일만 생성)</option>
              </select>
              <!-- finance 채널 고정 안내 -->
              <p v-if="channelType === 'finance'" class="field-hint warn-hint">
                금융 채널은 수동 승인으로 고정됩니다.
              </p>
              <p v-else class="field-hint">수동 승인: SEO 검토 후 직접 업로드 버튼 클릭</p>
            </div>

            <!-- 공개 범위 -->
            <div class="form-item">
              <label class="form-label">공개 범위</label>
              <select v-model="privacy" class="form-select">
                <option value="private">비공개</option>
                <option value="unlisted">미등록 (링크 공유)</option>
                <option value="public">공개</option>
              </select>
            </div>
          </div>

          <!-- 설정 요약 -->
          <div class="summary-box">
            <h4 class="summary-title">설정 요약</h4>
            <div class="summary-row">
              <span>채널 유형</span>
              <strong>{{ channelTypeLabel(channelType) }}</strong>
            </div>
            <div class="summary-row" v-if="channelName">
              <span>채널 이름</span>
              <strong>{{ channelName }}</strong>
            </div>
            <div class="summary-row" v-if="keywordsHint">
              <span>키워드 힌트</span>
              <strong>{{ keywordsHint }}</strong>
            </div>
            <div class="summary-row">
              <span>검색 기간</span>
              <strong>{{ days }}일</strong>
            </div>
            <div class="summary-row">
              <span>TTS</span>
              <strong>{{ ttsSkip ? '건너뜀' : ttsProvider }}</strong>
            </div>
            <div v-if="!ttsSkip && ttsVoiceOptions.length > 0" class="summary-row">
              <span>TTS 목소리</span>
              <strong>{{ ttsVoiceOptions.find(o => o.value === ttsVoice)?.label ?? ttsVoice }}</strong>
            </div>
            <div class="summary-row">
              <span>슬라이드 테마</span>
              <strong>{{ { dark_blue: '다크 블루', clean_white: '클린 화이트', warm_gray: '웜 그레이' }[slideTheme] }}</strong>
            </div>
            <div class="summary-row">
              <span>BGM</span>
              <strong>{{ bgmPath === 'random' ? '랜덤' : (bgmPath ? bgmPath : '없음') }} (볼륨 {{ bgmVolumePercent }})</strong>
            </div>
            <div class="summary-row">
              <span>업로드 모드</span>
              <strong>{{ uploadModeLabel }}</strong>
            </div>
            <div class="summary-row">
              <span>공개 범위</span>
              <strong>{{ { private: '비공개', unlisted: '미등록', public: '공개' }[privacy] }}</strong>
            </div>
          </div>
        </div>

        <!-- 모달 하단 네비게이션 버튼 -->
        <div class="modal-footer">
          <button v-if="modalStep > 1" class="btn-modal-back" @click="prevStep">이전</button>
          <div class="footer-spacer"></div>
          <button v-if="modalStep < 3" class="btn-modal-next" @click="nextStep">다음</button>
          <button
            v-else
            class="btn-modal-create"
            :disabled="f007Store.loading"
            @click="submitCreateJob"
          >
            {{ f007Store.loading ? '생성 중...' : '작업 시작' }}
          </button>
        </div>

      </div>
    </div>

  </div>
</template>

<style scoped>
/* 페이지 래퍼 */
.f007-view {
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

/* F007 배지 — 보라 계열 */
.badge-f007 {
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

/* 새 작업 만들기 버튼 — 보라 계열 */
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

/* ── 탭 필터 ── */
.tab-bar {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.tab-btn {
  font-size: 13px;
  font-weight: 600;
  padding: 5px 16px;
  border: 1.5px solid #ddd;
  border-radius: 20px;
  background: #fff;
  color: #666;
  cursor: pointer;
  transition: all 0.12s;
}
.tab-btn:hover { border-color: #7c3aed; color: #7c3aed; }
.tab-btn.active { background: #7c3aed; color: #fff; border-color: #7c3aed; }

.tab-btn.finance.active { background: #dc2626; border-color: #dc2626; }
.tab-btn.finance:not(.active):hover { border-color: #dc2626; color: #dc2626; }
.tab-btn.language.active { background: #2563eb; border-color: #2563eb; }
.tab-btn.language:not(.active):hover { border-color: #2563eb; color: #2563eb; }

.empty-text {
  font-size: 14px;
  color: #aaa;
  text-align: center;
  padding: 20px 0;
}

/* ── 게시판 테이블 ── */
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

.clickable-row { cursor: pointer; transition: background 0.12s; }
.clickable-row:hover td { background: #faf5ff; }

.center { text-align: center; }

.job-id-cell {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #7c3aed;
}

/* ── 채널 유형 태그 ── */
.channel-type-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  display: inline-block;
  white-space: nowrap;
}
.channel-type-tag.finance {
  background: #fee2e2;
  color: #991b1b;
}
.channel-type-tag.language {
  background: #dbeafe;
  color: #1e40af;
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
  font-size: 13px;
  cursor: pointer;
  color: #ccc;
  padding: 2px 4px;
  border-radius: 4px;
  font-weight: 700;
  transition: color 0.12s;
}
.btn-delete:hover { color: #ef4444; }

/* 더 불러오기 버튼 */
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
  background: #faf5ff;
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
  font-size: 16px;
  font-weight: 700;
  color: #999;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
}
.modal-close:hover { color: #333; background: #f0f0f0; }

/* ── 단계 표시 도트 ── */
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

/* ── 채널 유형 라디오 그룹 ── */
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.12s;
}
.radio-label:hover { border-color: #7c3aed; background: #faf5ff; }
.radio-label.selected { border-color: #7c3aed; background: #faf5ff; }

.radio-label input[type="radio"] { width: 16px; height: 16px; accent-color: #7c3aed; }

.radio-type-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  flex-shrink: 0;
}
.radio-type-tag.finance { background: #fee2e2; color: #991b1b; }
.radio-type-tag.language { background: #dbeafe; color: #1e40af; }

.radio-desc {
  font-size: 13px;
  color: #555;
}

/* ── finance 채널 경고 배너 ── */
.warning-banner {
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: #92400e;
}

.warning-icon {
  font-weight: 900;
  font-size: 14px;
  flex-shrink: 0;
  color: #d97706;
  width: 20px;
  height: 20px;
  border: 2px solid #d97706;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.warning-text { line-height: 1.5; }

/* ── 폼 공통 ── */
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

.full-width { grid-column: 1 / -1; }

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #555;
}

.required-mark { color: #ef4444; }
.optional-mark { color: #aaa; font-weight: normal; font-size: 11px; }

.volume-pct {
  font-size: 11px;
  font-weight: 600;
  color: #7c3aed;
  margin-left: 4px;
}

.form-input {
  padding: 7px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  background: #fff;
}
.form-input:focus { outline: none; border-color: #7c3aed; }

.form-select {
  padding: 7px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  color: #333;
  background: #fff;
}
.form-select:focus { outline: none; border-color: #7c3aed; }
.form-select:disabled { background: #f5f5f5; color: #aaa; cursor: not-allowed; }

.form-range {
  width: 100%;
  accent-color: #7c3aed;
  cursor: pointer;
}
.form-range:disabled { opacity: 0.4; cursor: not-allowed; }

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #bbb;
  margin-top: 2px;
}

.field-hint {
  font-size: 11px;
  color: #aaa;
  margin: 2px 0 0;
}

.warn-hint { color: #d97706; }

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
  background: #faf5ff;
  border: 1px solid #c4b5fd;
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
  border-bottom: 1px solid #c4b5fd;
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
  transition: background 0.12s;
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
