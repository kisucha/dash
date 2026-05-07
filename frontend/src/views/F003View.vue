<!-- F003View.vue — F003 영상제작 전용 UI — 다단계 폼으로 ComfyUI 이미지/동영상 생성 -->
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '../store/tasks.js'
import { getDownloads } from '../api/index.js'

const router = useRouter()
const taskStore = useTaskStore()

// ── Step 상태 ──
const currentStep = ref(1)

// ── Step 1: 생성 유형 ──
const generationType = ref('image')

// ── Step 2: 스타일 ──
const artStyle = ref('realistic')
const characterFace = ref('')
const characterHairStyle = ref('')
const characterHairColor = ref('')
const characterEyes = ref('')
const characterOutfit = ref('')
const cameraAngle = ref('')
const cameraComposition = ref('close_up')
const depthOfField = ref('')
const lighting = ref('natural_day')
const background = ref('')
const motionIntensity = ref('subtle')
const motionType = ref('camera_movement')
const loopAnimation = ref('false')
const selectedDetailLoras = ref([])

// ── Step 3: 파라미터 ──
const userDescription = ref('')
const width = ref(512)
const height = ref(768)
const steps = ref(20)
const cfgScale = ref(7)
const seed = ref(-1)
const videoLength = ref(16)
const fps = ref(8)

// ── 실행 상태 ──
const running = ref(false)
const errorMsg = ref('')

// ── 다운로드 진행 폴링 ──
const downloads = ref([])
let downloadPollTimer = null

// 진행 중인 모델 다운로드 목록 갱신 (2초 간격)
async function pollDownloads() {
  try {
    const res = await getDownloads()
    downloads.value = (res.data || []).filter(d => d.status === 'DOWNLOADING' || d.status === 'QUEUED')
  } catch { /* 다운로드 API 오류는 무시하고 계속 폴링 */ }
}

onMounted(() => {
  if (taskStore.features.length === 0) taskStore.fetchFeatures().catch(() => {})
  downloadPollTimer = setInterval(pollDownloads, 2000)
})
onUnmounted(() => {
  if (downloadPollTimer) clearInterval(downloadPollTimer)
})

// ── 아트 스타일별 기반 모델 맵 (디테일 LoRA 호환 필터용) ──
// 스타일에 따라 사용하는 기반 모델이 다르므로 LoRA 호환 목록도 달라진다
const baseModelMap = {
  anime: 'SDXL',
  realistic: 'SD1.5',
  fantasy: 'SDXL',
  cyberpunk: 'SD1.5',
  watercolor: 'SD1.5',
  '3d_render': 'SDXL',
  pixel_art: 'SDXL',
  flux: 'Flux.1',
}
const currentBaseModel = computed(() => baseModelMap[artStyle.value] || 'SD1.5')

// 디테일 LoRA 호환 목록 — 기반 모델 기준으로 필터링
const detailLoraCompatMap = {
  detail_tweaker: ['SD1.5'],
  detail_tweaker_xl: ['SDXL'],
  add_more_details: ['SD1.5'],
  flux_image_upgrader: ['Flux.1', 'SDXL', 'SD1.5'],
  detailifier: ['Flux.1', 'SD3.5', 'SDXL', 'SD1.5'],
}
const availableDetailLoras = computed(() =>
  Object.entries(detailLoraCompatMap)
    .filter(([, models]) => models.includes(currentBaseModel.value))
    .map(([key]) => key)
)

// ── 실행 함수 ──
async function startGeneration() {
  if (running.value) return
  running.value = true
  errorMsg.value = ''
  try {
    const params = {
      generation_type: generationType.value,
      art_style: artStyle.value,
      character_face: characterFace.value,
      character_hair_style: characterHairStyle.value,
      character_hair_color: characterHairColor.value,
      character_eyes: characterEyes.value,
      character_outfit: characterOutfit.value,
      camera_angle: cameraAngle.value,
      camera_composition: cameraComposition.value,
      depth_of_field: depthOfField.value,
      lighting: lighting.value,
      background: background.value,
      motion_intensity: motionIntensity.value,
      motion_type: motionType.value,
      loop_animation: loopAnimation.value,
      detail_loras: selectedDetailLoras.value.join(','),
      user_description: userDescription.value,
      width: width.value,
      height: height.value,
      steps: steps.value,
      cfg_scale: cfgScale.value,
      seed: seed.value,
      video_length: videoLength.value,
      fps: fps.value,
    }
    const task = await taskStore.createTask('F003', params)
    router.push({ name: 'TaskDetail', params: { id: task.id } })
  } catch (err) {
    errorMsg.value = err?.response?.data?.detail || '생성 요청에 실패했습니다.'
  } finally {
    running.value = false
  }
}

// ── 라벨 맵 — 화면 표시용 한국어 레이블 ──
const artStyleLabels = {
  anime: '애니메이션',
  realistic: '실사',
  fantasy: '판타지',
  cyberpunk: '사이버펑크',
  watercolor: '수채화',
  '3d_render': '3D 렌더',
  pixel_art: '픽셀 아트',
  flux: 'Flux.1 (고품질)',
}
const loraLabels = {
  detail_tweaker: 'Detail Tweaker (SD1.5)',
  detail_tweaker_xl: 'Detail Tweaker XL',
  add_more_details: 'Add More Details',
  flux_image_upgrader: 'Flux Image Upgrader',
  detailifier: 'Detailifier',
}
</script>

<template>
  <div class="f003-view">
    <div class="page-header">
      <button class="back-btn" @click="router.back()">← 뒤로</button>
      <h1 class="page-title">영상제작 <span class="badge-f003">F003</span></h1>
      <p class="page-desc">ComfyUI + Ollama로 이미지 또는 동영상을 자동 생성합니다.</p>
    </div>

    <!-- 모델 다운로드 진행 바 — 다운로드 중인 항목이 있을 때만 표시 -->
    <div v-if="downloads.length > 0" class="download-notice">
      <div v-for="dl in downloads" :key="dl.id" class="download-item">
        <span class="dl-label">모델 다운로드 중: {{ dl.target_path.split('\\').pop() }}</span>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: dl.progress_pct + '%' }"></div>
        </div>
        <span class="dl-pct">{{ dl.progress_pct.toFixed(1) }}%</span>
      </div>
    </div>

    <!-- Step 탭 네비게이션 -->
    <div class="step-tabs">
      <button
        v-for="(label, idx) in ['생성 유형', '스타일', '파라미터']"
        :key="idx"
        class="step-tab"
        :class="{ active: currentStep === idx + 1 }"
        @click="currentStep = idx + 1"
      >
        {{ idx + 1 }}. {{ label }}
      </button>
    </div>

    <!-- ── Step 1: 생성 유형 선택 ── -->
    <div v-if="currentStep === 1" class="step-content">
      <h2 class="step-title">생성 유형 선택</h2>
      <div class="type-cards">
        <!-- 이미지 생성 카드 -->
        <div
          class="type-card"
          :class="{ selected: generationType === 'image' }"
          @click="generationType = 'image'"
        >
          <div class="type-icon">🖼</div>
          <div class="type-name">이미지</div>
          <div class="type-desc">Flux.1 / SD 기반 고품질 이미지 생성</div>
        </div>
        <!-- 동영상 생성 카드 -->
        <div
          class="type-card"
          :class="{ selected: generationType === 'video' }"
          @click="generationType = 'video'"
        >
          <div class="type-icon">🎬</div>
          <div class="type-name">동영상</div>
          <div class="type-desc">AnimateDiff 기반 짧은 동영상 클립 생성</div>
        </div>
      </div>
      <div class="step-nav">
        <button class="btn-next" @click="currentStep = 2">다음 →</button>
      </div>
    </div>

    <!-- ── Step 2: 스타일 선택 ── -->
    <div v-if="currentStep === 2" class="step-content">
      <h2 class="step-title">스타일 선택</h2>

      <!-- 카테고리 1: 아트 스타일 -->
      <div class="cat-section">
        <h3 class="cat-title">아트 스타일</h3>
        <div class="style-chips">
          <button
            v-for="(label, key) in artStyleLabels" :key="key"
            class="chip"
            :class="{ selected: artStyle === key }"
            @click="artStyle = key"
          >{{ label }}</button>
        </div>
        <p class="base-model-hint">기반 모델: <strong>{{ currentBaseModel }}</strong></p>
      </div>

      <!-- 카테고리 2: 캐릭터 외형 -->
      <div class="cat-section">
        <h3 class="cat-title">캐릭터 외형</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>얼굴형</label>
            <select v-model="characterFace">
              <option value="">기본</option>
              <option value="western">서양</option>
              <option value="asian">동양</option>
              <option value="mixed">혼합</option>
            </select>
          </div>
          <div class="form-item">
            <label>헤어스타일</label>
            <select v-model="characterHairStyle">
              <option value="">기본</option>
              <option value="long_hair">롱 헤어</option>
              <option value="short_hair">숏 헤어</option>
              <option value="twin_tails">트윈테일</option>
              <option value="ponytail">포니테일</option>
              <option value="bob_with_bangs">앞머리 단발</option>
            </select>
          </div>
          <div class="form-item">
            <label>헤어 색상</label>
            <select v-model="characterHairColor">
              <option value="">기본</option>
              <option value="blonde">금발</option>
              <option value="brown">갈색</option>
              <option value="black">검정</option>
              <option value="pink">분홍</option>
              <option value="silver">은색</option>
              <option value="gradient">그라데이션</option>
            </select>
          </div>
          <div class="form-item">
            <label>눈매</label>
            <select v-model="characterEyes">
              <option value="">기본</option>
              <option value="large_eyes">큰 눈</option>
              <option value="sharp_eyes">날카로운 눈</option>
              <option value="upturned">올라간 눈</option>
              <option value="downturned">내려간 눈</option>
            </select>
          </div>
          <div class="form-item">
            <label>의상</label>
            <select v-model="characterOutfit">
              <option value="">기본</option>
              <option value="casual">캐주얼</option>
              <option value="fantasy">판타지 코스튬</option>
              <option value="school_uniform">교복</option>
              <option value="sportswear">운동복</option>
              <option value="dress">드레스</option>
              <option value="cyberpunk">사이버펑크</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 카테고리 3: 촬영 기법 -->
      <div class="cat-section">
        <h3 class="cat-title">촬영 기법</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>카메라 앵글</label>
            <select v-model="cameraAngle">
              <option value="">기본</option>
              <option value="front">정면</option>
              <option value="side">측면</option>
              <option value="from_above">위에서</option>
              <option value="from_below">아래서</option>
              <option value="dramatic_low">드라마틱 로우</option>
            </select>
          </div>
          <div class="form-item">
            <label>화면 구도</label>
            <select v-model="cameraComposition">
              <option value="close_up">클로즈업</option>
              <option value="upper_body">상반신</option>
              <option value="full_body">전신</option>
              <option value="wide_shot">와이드샷</option>
            </select>
          </div>
          <div class="form-item">
            <label>심도</label>
            <select v-model="depthOfField">
              <option value="">기본</option>
              <option value="bokeh">보케</option>
              <option value="pan_focus">팬 포커스</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 카테고리 4: 조명 -->
      <div class="cat-section">
        <h3 class="cat-title">조명</h3>
        <select v-model="lighting" class="full-select">
          <option value="natural_day">자연광 (낮)</option>
          <option value="golden_hour">골든아워</option>
          <option value="night">야간</option>
          <option value="indoor">실내 조명</option>
          <option value="dramatic">드라마틱</option>
          <option value="soft">소프트</option>
          <option value="backlit">역광</option>
          <option value="studio">스튜디오</option>
          <option value="neon">네온</option>
        </select>
      </div>

      <!-- 카테고리 5: 배경 -->
      <div class="cat-section">
        <h3 class="cat-title">배경</h3>
        <select v-model="background" class="full-select">
          <option value="">기본</option>
          <option value="classroom">교실</option>
          <option value="cafe">카페</option>
          <option value="bedroom">침실</option>
          <option value="office">사무실</option>
          <option value="city_street">도시 거리</option>
          <option value="nature_park">자연 공원</option>
          <option value="beach">해변</option>
          <option value="mountain_forest">산/숲</option>
          <option value="castle">성</option>
          <option value="magical_realm">마법의 세계</option>
          <option value="otherworldly">이세계</option>
          <option value="plain_background">단색 배경</option>
          <option value="abstract">추상 배경</option>
        </select>
      </div>

      <!-- 카테고리 6: 동영상 모션 — 동영상 유형 선택 시에만 표시 -->
      <div v-if="generationType === 'video'" class="cat-section">
        <h3 class="cat-title">모션 (동영상 전용)</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>모션 강도</label>
            <select v-model="motionIntensity">
              <option value="subtle">부드러운</option>
              <option value="moderate">보통</option>
              <option value="dynamic">역동적</option>
            </select>
          </div>
          <div class="form-item">
            <label>모션 유형</label>
            <select v-model="motionType">
              <option value="camera_movement">카메라 움직임</option>
              <option value="character_movement">캐릭터 움직임</option>
              <option value="particle_environment">파티클/환경</option>
            </select>
          </div>
          <div class="form-item">
            <label>루프</label>
            <select v-model="loopAnimation">
              <option value="false">없음</option>
              <option value="true">루프</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 카테고리 7: 디테일 향상 LoRA — 현재 기반 모델과 호환되는 항목만 활성화 -->
      <div class="cat-section">
        <h3 class="cat-title">디테일 향상 LoRA</h3>
        <p class="cat-hint">
          현재 기반 모델({{ currentBaseModel }})과 호환되는 LoRA만 활성화됩니다.
          <span class="install-hint">선택해도 ComfyUI에 미설치된 LoRA는 자동으로 건너뜁니다.</span>
        </p>
        <div class="lora-checkboxes">
          <label
            v-for="key in ['detail_tweaker', 'detail_tweaker_xl', 'add_more_details', 'flux_image_upgrader', 'detailifier']"
            :key="key"
            class="lora-label"
            :class="{ disabled: !availableDetailLoras.includes(key) }"
          >
            <input
              type="checkbox"
              :value="key"
              v-model="selectedDetailLoras"
              :disabled="!availableDetailLoras.includes(key)"
            />
            {{ loraLabels[key] }}
          </label>
        </div>
      </div>

      <div class="step-nav">
        <button class="btn-back" @click="currentStep = 1">← 이전</button>
        <button class="btn-next" @click="currentStep = 3">다음 →</button>
      </div>
    </div>

    <!-- ── Step 3: 파라미터 설정 + 실행 ── -->
    <div v-if="currentStep === 3" class="step-content">
      <h2 class="step-title">파라미터 설정</h2>

      <!-- 추가 설명 입력 -->
      <div class="cat-section">
        <h3 class="cat-title">추가 설명</h3>
        <textarea
          v-model="userDescription"
          class="desc-textarea"
          placeholder="생성할 이미지/동영상에 대한 추가 설명을 입력하세요 (한국어 가능)"
          rows="3"
        ></textarea>
      </div>

      <!-- 공통 파라미터 — 이미지/동영상 모두 적용 -->
      <div class="cat-section">
        <h3 class="cat-title">공통 파라미터</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>가로 (px)</label>
            <input type="number" v-model.number="width" min="256" max="2048" step="64" />
          </div>
          <div class="form-item">
            <label>세로 (px)</label>
            <input type="number" v-model.number="height" min="256" max="2048" step="64" />
          </div>
          <div class="form-item">
            <label>스텝 수</label>
            <input type="number" v-model.number="steps" min="1" max="150" />
          </div>
          <div class="form-item">
            <label>CFG 스케일</label>
            <input type="number" v-model.number="cfgScale" min="1" max="30" step="0.5" />
          </div>
          <div class="form-item">
            <label>시드 (-1: 무작위)</label>
            <input type="number" v-model.number="seed" />
          </div>
        </div>
      </div>

      <!-- 동영상 전용 파라미터 — 동영상 유형 선택 시에만 표시 -->
      <div v-if="generationType === 'video'" class="cat-section">
        <h3 class="cat-title">동영상 파라미터</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>프레임 수</label>
            <input type="number" v-model.number="videoLength" min="8" max="64" step="8" />
          </div>
          <div class="form-item">
            <label>FPS</label>
            <input type="number" v-model.number="fps" min="1" max="30" />
          </div>
        </div>
      </div>

      <!-- 선택 요약 카드 — Step 3 진입 전 설정한 값을 한눈에 확인 -->
      <div class="summary-card">
        <h3 class="cat-title">선택 요약</h3>
        <div class="summary-row">
          <span>생성 유형</span>
          <strong>{{ generationType === 'image' ? '이미지' : '동영상' }}</strong>
        </div>
        <div class="summary-row">
          <span>아트 스타일</span>
          <strong>{{ artStyleLabels[artStyle] }}</strong>
        </div>
        <div class="summary-row">
          <span>기반 모델</span>
          <strong>{{ currentBaseModel }}</strong>
        </div>
        <div class="summary-row">
          <span>해상도</span>
          <strong>{{ width }} x {{ height }}</strong>
        </div>
        <div v-if="selectedDetailLoras.length > 0" class="summary-row">
          <span>디테일 LoRA</span>
          <strong>{{ selectedDetailLoras.join(', ') }}</strong>
        </div>
      </div>

      <!-- API 오류 메시지 -->
      <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>

      <div class="step-nav">
        <button class="btn-back" @click="currentStep = 2">← 이전</button>
        <button class="btn-run" :disabled="running" @click="startGeneration">
          {{ running ? '생성 요청 중...' : '생성 시작' }}
        </button>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* 페이지 래퍼 */
.f003-view {
  max-width: 760px;
  display: flex;
  flex-direction: column;
  gap: 20px;
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

/* F003 배지 */
.badge-f003 {
  font-size: 12px;
  font-weight: 600;
  background: #e0e7ff;
  color: #4338ca;
  padding: 2px 8px;
  border-radius: 10px;
}

.page-desc {
  font-size: 14px;
  color: #666;
  margin: 0;
}

/* ── 다운로드 진행 바 ── */
.download-notice {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.download-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.dl-label {
  flex: 1;
  color: #92400e;
}

.progress-bar {
  flex: 2;
  height: 8px;
  background: #fde68a;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #f59e0b;
  border-radius: 4px;
  transition: width 0.3s;
}

.dl-pct {
  width: 42px;
  text-align: right;
  color: #92400e;
  font-weight: 600;
}

/* ── Step 탭 ── */
.step-tabs {
  display: flex;
  gap: 8px;
  border-bottom: 2px solid #e8e8e8;
  padding-bottom: 0;
}

.step-tab {
  padding: 8px 18px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 14px;
  font-weight: 500;
  color: #888;
  cursor: pointer;
  margin-bottom: -2px;
  transition: all 0.15s;
}

.step-tab.active {
  color: #4a90d9;
  border-bottom-color: #4a90d9;
  font-weight: 700;
}

.step-tab:hover:not(.active) { color: #555; }

/* ── Step 콘텐츠 공통 ── */
.step-content {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.step-title {
  font-size: 18px;
  font-weight: 700;
  color: #222;
  margin: 0 0 20px;
}

/* ── 생성 유형 카드 (Step 1) ── */
.type-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.type-card {
  flex: 1;
  border: 2px solid #e8e8e8;
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
}

.type-card:hover {
  border-color: #93c5fd;
  background: #f0f8ff;
}

.type-card.selected {
  border-color: #4a90d9;
  background: #e0f0ff;
}

.type-icon { font-size: 32px; margin-bottom: 8px; }
.type-name { font-size: 16px; font-weight: 700; color: #222; margin-bottom: 4px; }
.type-desc { font-size: 13px; color: #666; }

/* ── 카테고리 섹션 (Step 2, 3 공통) ── */
.cat-section { margin-bottom: 20px; }

.cat-title {
  font-size: 14px;
  font-weight: 700;
  color: #444;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.cat-hint {
  font-size: 12px;
  color: #888;
  margin: 0 0 8px;
}

.install-hint {
  display: block;
  margin-top: 3px;
  color: #b45309;
  font-size: 11px;
}

.base-model-hint {
  font-size: 12px;
  color: #888;
  margin: 6px 0 0;
}

/* ── 스타일 칩 버튼 ── */
.style-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  padding: 6px 14px;
  border: 1.5px solid #ddd;
  border-radius: 20px;
  font-size: 13px;
  background: #fff;
  color: #555;
  cursor: pointer;
  transition: all 0.12s;
}

.chip:hover { border-color: #93c5fd; color: #4a90d9; }

.chip.selected {
  border-color: #4a90d9;
  background: #e0f0ff;
  color: #1d4ed8;
  font-weight: 600;
}

/* ── 폼 그리드 ── */
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-item label {
  font-size: 12px;
  color: #888;
  font-weight: 500;
}

.form-item select,
.form-item input {
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  color: #333;
  background: #fff;
}

.form-item select:focus,
.form-item input:focus {
  outline: none;
  border-color: #4a90d9;
}

/* 전체 너비 select */
.full-select {
  width: 100%;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 7px 10px;
  font-size: 13px;
  color: #333;
}

.full-select:focus {
  outline: none;
  border-color: #4a90d9;
}

/* ── LoRA 체크박스 ── */
.lora-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lora-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #333;
  cursor: pointer;
}

/* 비호환 LoRA는 회색으로 표시 */
.lora-label.disabled {
  color: #bbb;
  cursor: not-allowed;
}

.lora-label input {
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.lora-label.disabled input { cursor: not-allowed; }

/* ── 설명 textarea ── */
.desc-textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  color: #333;
  resize: vertical;
  font-family: inherit;
}

.desc-textarea:focus {
  outline: none;
  border-color: #4a90d9;
}

/* ── 선택 요약 카드 ── */
.summary-card {
  background: #f8faff;
  border: 1px solid #dce8f8;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 4px 0;
  border-bottom: 1px solid #edf2ff;
}

.summary-row:last-child { border-bottom: none; }
.summary-row span { color: #666; }
.summary-row strong { color: #222; }

/* ── 오류 박스 ── */
.error-box {
  background: #fee2e2;
  color: #991b1b;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  margin-bottom: 8px;
}

/* ── Step 네비게이션 버튼 ── */
.step-nav {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.btn-back {
  background: #fff;
  border: 1.5px solid #ddd;
  color: #555;
  border-radius: 8px;
  padding: 9px 22px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.btn-back:hover { background: #f5f5f5; }

.btn-next {
  background: #4a90d9;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 9px 22px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.btn-next:hover { background: #357abd; }

/* 생성 시작 버튼 — 초록색으로 차별화 */
.btn-run {
  background: #16a34a;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 9px 28px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.btn-run:hover:not(:disabled) { background: #15803d; }

.btn-run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
