<!-- F003View.vue — F003 영상제작 전용 UI — 다단계 폼으로 ComfyUI 이미지/동영상 생성 -->
<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '../store/tasks.js'
import { getDownloads, getF003Loras, predownloadF003Loras, getF003Models } from '../api/index.js'

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
const selectedDetailLoras = ref([])  // 선택된 LoRA — [{ key: string, strength: number }] 객체 배열

// 커스텀 모델 선택 ('' = 자동)
const customCheckpoint = ref('')
const customVae = ref('')
const customClip = ref('')  // 정보 표시 전용

// ComfyUI 설치 모델 목록
const availableCheckpoints = ref([])
const availableVaes = ref([])
const availableClips = ref([])
const noClipCheckpoints = ref([])   // CLIP 없는 체크포인트 파일명 목록 (UI 경고용)
const modelsLoading = ref(false)

// 선택된 커스텀 체크포인트가 CLIP 없는 모델인지 여부
const selectedCheckpointHasNoClip = computed(() =>
  customCheckpoint.value !== '' && noClipCheckpoints.value.includes(customCheckpoint.value)
)

// ── LoRA 목록 (API에서 로드) ──
const loraCategories = ref({})      // { enhancement: [...], character: [...], style: [...], background: [...] }
const loraLoading = ref(false)
const loraLoadError = ref('')
const predownloading = ref(false)
const predownloadMsg = ref('')

// ── Step 3: 파라미터 ──
const userDescription = ref('')
const width = ref(512)
const height = ref(768)
const steps = ref(20)
const cfgScale = ref(7)
const seed = ref(-1)
const videoLength = ref(16)
const fps = ref(8)

// ── img2img 모드 상태 ──
const isImg2Img = ref(false)          // img2img 모드 토글 여부
const inputImageFile = ref(null)      // 업로드된 File 객체
const inputImagePreview = ref('')     // 미리보기용 data URL
const inputImageBase64 = ref('')      // 백엔드 전송용 base64 data URL
const denoiseStrength = ref(0.75)     // 수정 강도 (0.1 ~ 1.0)

// ── 실행 상태 ──
const running = ref(false)
const errorMsg = ref('')

// ── 다운로드 진행 폴링 ──
const downloads = ref([])
let downloadPollTimer = null

// ── img2img 이미지 업로드 처리 — FileReader로 data URL 추출 ──
function handleImageUpload(event) {
  const file = event.target.files[0]
  if (!file) return
  inputImageFile.value = file
  const reader = new FileReader()
  reader.onload = (e) => {
    // data URL을 미리보기와 전송 모두에 사용
    inputImagePreview.value = e.target.result
    inputImageBase64.value = e.target.result
  }
  reader.readAsDataURL(file)
}

// ── 업로드된 기준 이미지 제거 ──
function removeInputImage() {
  inputImageFile.value = null
  inputImagePreview.value = ''
  inputImageBase64.value = ''
}

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
  loadLoras()
  loadF003Models()
})
onUnmounted(() => {
  if (downloadPollTimer) clearInterval(downloadPollTimer)
})

// ── 아트 스타일별 기반 모델 맵 (LoRA 호환 필터용) ──
// 스타일에 따라 기반 모델이 달라지므로 호환 LoRA 목록도 달라진다
const baseModelMap = {
  anime: 'SDXL',
  realistic: 'SDXL',
  fantasy: 'SDXL',
  cyberpunk: 'SDXL',
  watercolor: 'SDXL',
  '3d_render': 'SDXL',
  pixel_art: 'SDXL',
  flux: 'Flux.1',
}
const currentBaseModel = computed(() => baseModelMap[artStyle.value] || 'SDXL')

// LoRA 호환성 체크 — 현재 기반 모델이 해당 LoRA의 base_models에 포함되는지 확인
function isLoraCompatible(lora) {
  return lora.base_models.includes(currentBaseModel.value)
}

// LoRA 카테고리 한국어 레이블 맵
const loraCategoryLabels = {
  enhancement: '디테일 향상',
  character: '캐릭터 / 신체',
  style: '스타일',
  background: '배경',
}

// LoRA 목록 API 로드
async function loadLoras() {
  loraLoading.value = true
  loraLoadError.value = ''
  try {
    const res = await getF003Loras()
    loraCategories.value = res.data.categories || {}
  } catch {
    loraLoadError.value = 'LoRA 목록을 불러오지 못했습니다.'
  } finally {
    loraLoading.value = false
  }
}

// ComfyUI 설치 모델 목록 로드
async function loadF003Models() {
  modelsLoading.value = true
  try {
    const res = await getF003Models()
    availableCheckpoints.value = res.data.checkpoints || []
    availableVaes.value = res.data.vaes || []
    availableClips.value = res.data.clips || []
    noClipCheckpoints.value = res.data.no_clip_checkpoints || []
  } catch {
    // ComfyUI 미실행 시 조용히 실패
  } finally {
    modelsLoading.value = false
  }
}

// 사전 다운로드 트리거 — 미설치 & 다운로드 가능 LoRA를 백그라운드에서 내려받기 시작
async function triggerPredownload() {
  predownloading.value = true
  predownloadMsg.value = ''
  try {
    const res = await predownloadF003Loras()
    const { queued_count, queued } = res.data
    if (queued_count === 0) {
      predownloadMsg.value = '다운로드할 항목이 없습니다 (이미 모두 설치됨)'
    } else {
      predownloadMsg.value = `${queued_count}개 다운로드 시작: ${queued.join(', ')}`
    }
  } catch {
    predownloadMsg.value = '다운로드 트리거 실패'
  } finally {
    predownloading.value = false
  }
}

// LoRA 선택 여부 확인
function isLoraSelected(key) {
  return selectedDetailLoras.value.some(item => item.key === key)
}

// LoRA 강도 조회 (선택 안 되어 있으면 default_weight 반환)
function getLoraStrength(key, defaultWeight = 1.0) {
  const found = selectedDetailLoras.value.find(item => item.key === key)
  return found ? found.strength : defaultWeight
}

// LoRA 토글 — 선택/해제
function toggleLora(lora) {
  const idx = selectedDetailLoras.value.findIndex(item => item.key === lora.key)
  if (idx === -1) {
    selectedDetailLoras.value.push({ key: lora.key, strength: lora.default_weight })
  } else {
    selectedDetailLoras.value.splice(idx, 1)
  }
}

// LoRA 강도 변경
function setLoraStrength(key, strength) {
  const found = selectedDetailLoras.value.find(item => item.key === key)
  if (found) found.strength = parseFloat(strength)
}

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
      detail_loras: JSON.stringify(selectedDetailLoras.value),
      user_description: userDescription.value,
      width: width.value,
      height: height.value,
      steps: steps.value,
      cfg_scale: cfgScale.value,
      seed: seed.value,
      video_length: videoLength.value,
      fps: fps.value,
      ...(customCheckpoint.value ? { custom_checkpoint: customCheckpoint.value } : {}),
      ...(customVae.value ? { custom_vae: customVae.value } : {}),
    }
    // img2img 모드가 활성화되고 기준 이미지가 업로드된 경우에만 추가
    if (isImg2Img.value && inputImageBase64.value) {
      params.input_image = inputImageBase64.value
      params.denoise = denoiseStrength.value
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
// loraLabels 제거 — API 응답의 display_name 필드로 대체됨
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
      <!-- img2img 구분선 -->
      <hr class="section-divider" />

      <!-- img2img 모드 토글 -->
      <div class="img2img-section">
        <label class="img2img-toggle-label">
          <input type="checkbox" v-model="isImg2Img" class="img2img-checkbox" />
          <span class="img2img-toggle-text">이미지 기반 수정 (img2img)</span>
        </label>
        <p class="img2img-desc">기준 이미지를 업로드하면 해당 이미지를 바탕으로 수정 생성합니다.</p>

        <!-- img2img ON일 때만 표시 -->
        <div v-if="isImg2Img" class="img2img-controls">

          <!-- 이미지 업로드 영역 -->
          <div class="upload-area-wrapper">
            <label class="upload-area" :class="{ 'has-image': inputImagePreview }">
              <!-- 미리보기: 이미지가 업로드된 경우 -->
              <template v-if="inputImagePreview">
                <img :src="inputImagePreview" class="upload-preview" alt="기준 이미지 미리보기" />
                <button type="button" class="remove-image-btn" @click.prevent="removeInputImage">제거</button>
              </template>

              <!-- 업로드 전: 안내 문구 -->
              <template v-else>
                <span class="upload-icon">+</span>
                <span class="upload-label">클릭하여 이미지 선택</span>
                <span class="upload-hint">PNG, JPG, WEBP 지원</span>
                <input
                  type="file"
                  accept="image/*"
                  class="upload-input"
                  @change="handleImageUpload"
                />
              </template>
            </label>
          </div>

          <!-- 수정 강도 슬라이더 -->
          <div class="form-item denoise-item">
            <label class="denoise-label">
              수정 강도
              <span class="denoise-value">{{ denoiseStrength.toFixed(2) }}</span>
            </label>
            <input
              type="range"
              v-model.number="denoiseStrength"
              min="0.1"
              max="1.0"
              step="0.05"
              class="denoise-slider"
            />
            <p class="denoise-hint">낮을수록 원본 이미지 유지, 높을수록 프롬프트 반영</p>
          </div>
        </div>
      </div>

      <div class="step-nav">
        <button class="btn-next" @click="currentStep = 2">다음 →</button>
      </div>
    </div>

    <!-- ── Step 2: 스타일 선택 ── -->
    <div v-if="currentStep === 2" class="step-content">
      <h2 class="step-title">스타일 선택</h2>

      <!-- 모델 설정 — ComfyUI 설치 모델 직접 선택 (선택사항) -->
      <div class="cat-section model-settings-section">
        <h3 class="cat-title">모델 설정 <span class="optional-badge">선택사항</span></h3>
        <p class="section-hint">비워두면 아트 스타일에 맞는 모델이 자동 선택됩니다.</p>
        <div class="form-grid">
          <!-- Checkpoint -->
          <div class="form-item">
            <label>Checkpoint <span class="hint-text">(자동 = 스타일 기반)</span></label>
            <select v-model="customCheckpoint" :disabled="modelsLoading">
              <option value="">자동 선택</option>
              <option v-for="ckpt in availableCheckpoints" :key="ckpt" :value="ckpt">{{ ckpt }}</option>
            </select>
            <p v-if="modelsLoading" class="field-hint">ComfyUI 모델 목록 로드 중...</p>
            <p v-else-if="availableCheckpoints.length === 0" class="field-hint warn">
              ComfyUI에서 모델 목록을 가져오지 못했습니다 (ComfyUI 실행 확인)
            </p>
            <!-- CLIP 없는 체크포인트 선택 시 경고 -->
            <div v-if="selectedCheckpointHasNoClip" class="no-clip-warning">
              ⚠️ 이 체크포인트에는 CLIP(텍스트 인코더)이 없습니다. 이미지/동영상 생성 시 오류가 발생합니다.
              AnimateDiff용 unet-only 모델은 단독 사용이 불가합니다.
            </div>
          </div>
          <!-- VAE -->
          <div class="form-item">
            <label>VAE <span class="hint-text">(내장 = 체크포인트 기본)</span></label>
            <select v-model="customVae" :disabled="modelsLoading">
              <option value="">체크포인트 내장 VAE</option>
              <option v-for="vae in availableVaes" :key="vae" :value="vae">{{ vae }}</option>
            </select>
          </div>
          <!-- CLIP — Flux.1이 아닌 경우만 표시, 정보 전용 -->
          <div class="form-item" v-if="artStyle !== 'flux'">
            <label>CLIP <span class="hint-text">(정보 전용 — SD/SDXL은 체크포인트 내장)</span></label>
            <select :value="''" disabled>
              <option value="">체크포인트 내장 CLIP</option>
              <option v-for="clip in availableClips" :key="clip" :value="clip">{{ clip }}</option>
            </select>
            <p class="field-hint">SD/SDXL에서 CLIP은 체크포인트에 내장됩니다. 별도 선택은 향후 지원 예정.</p>
          </div>
        </div>
      </div>

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

      <!-- 카테고리 7: LoRA 선택 — API에서 카테고리별 목록을 로드해 2x2 그리드로 표시 -->
      <div class="cat-section lora-section">
        <div class="lora-section-header">
          <h3 class="cat-title">LoRA 선택</h3>
          <div class="lora-header-actions">
            <span class="base-model-badge">{{ currentBaseModel }}</span>
            <button class="btn-predownload" :disabled="predownloading" @click="triggerPredownload">
              {{ predownloading ? '다운로드 중...' : '사전 다운로드' }}
            </button>
          </div>
        </div>
        <p v-if="predownloadMsg" class="predownload-msg" :class="{ error: predownloadMsg.includes('실패') }">
          {{ predownloadMsg }}
        </p>

        <div v-if="loraLoading" class="lora-loading">LoRA 목록 로드 중...</div>
        <div v-else-if="loraLoadError" class="lora-error">{{ loraLoadError }}</div>
        <div v-else class="lora-panels">
          <!-- 카테고리별 패널 — loraCategoryLabels 순서대로 렌더링 -->
          <div
            v-for="(catLabel, catKey) in loraCategoryLabels"
            :key="catKey"
            class="lora-panel"
            v-show="loraCategories[catKey] && loraCategories[catKey].length > 0"
          >
            <h4 class="lora-panel-title">{{ catLabel }}</h4>
            <div class="lora-list">
              <div
                v-for="lora in (loraCategories[catKey] || [])"
                :key="lora.key"
                class="lora-item"
                :class="{
                  'lora-disabled': !isLoraCompatible(lora),
                  'lora-not-installed': !lora.installed && isLoraCompatible(lora),
                  'lora-selected': isLoraSelected(lora.key)
                }"
                :title="lora.description"
              >
                <!-- 체크박스 + 이름 + 상태 행 -->
                <div class="lora-row-top">
                  <input
                    type="checkbox"
                    :checked="isLoraSelected(lora.key)"
                    :disabled="!isLoraCompatible(lora)"
                    @change="toggleLora(lora)"
                  />
                  <span class="lora-name">{{ lora.display_name }}</span>
                  <span
                    class="lora-status"
                    :class="lora.installed ? 'status-ok' : (lora.downloadable ? 'status-dl' : 'status-manual')"
                  >
                    {{ lora.installed ? '설치됨' : (lora.downloadable ? '다운로드 가능' : '수동 설치') }}
                  </span>
                </div>
                <!-- 강도 슬라이더 — 선택된 경우만 표시 -->
                <div v-if="isLoraSelected(lora.key)" class="lora-strength-row">
                  <span class="strength-label">강도</span>
                  <input
                    type="range"
                    :value="getLoraStrength(lora.key, lora.default_weight)"
                    min="0.0"
                    max="2.0"
                    step="0.1"
                    class="strength-slider"
                    @input="setLoraStrength(lora.key, $event.target.value)"
                  />
                  <span class="strength-value">{{ getLoraStrength(lora.key, lora.default_weight).toFixed(1) }}</span>
                </div>
              </div>
            </div>
          </div>
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
          <strong>{{ selectedDetailLoras.map(l => `${l.key}(${l.strength.toFixed(1)})`).join(', ') }}</strong>
        </div>
        <!-- 커스텀 모델 표시 -->
        <div v-if="customCheckpoint" class="summary-row">
          <span>체크포인트</span>
          <strong>{{ customCheckpoint }}</strong>
        </div>
        <div v-if="customVae" class="summary-row">
          <span>VAE</span>
          <strong>{{ customVae }}</strong>
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

/* ── LoRA 섹션 (카테고리 패널 방식) ── */
.lora-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.lora-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 현재 기반 모델 배지 */
.base-model-badge {
  font-size: 12px;
  background: #e8f0fe;
  color: #3367d6;
  border-radius: 4px;
  padding: 2px 8px;
  font-weight: 600;
}

/* 사전 다운로드 버튼 */
.btn-predownload {
  font-size: 12px;
  padding: 4px 12px;
  background: #4caf50;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.btn-predownload:hover:not(:disabled) { background: #388e3c; }
.btn-predownload:disabled { opacity: 0.6; cursor: default; }

/* 사전 다운로드 결과 메시지 */
.predownload-msg {
  font-size: 13px;
  color: #388e3c;
  margin: 4px 0 8px;
  padding: 6px 10px;
  background: #f1f8e9;
  border-radius: 4px;
}
.predownload-msg.error { color: #c62828; background: #ffebee; }

/* LoRA 패널 2x2 그리드 */
.lora-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 10px;
}

.lora-panel {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafafa;
}

.lora-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.lora-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* LoRA 개별 항목 — 체크박스 + 이름 + 상태 배지 + 강도 슬라이더 */
.lora-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.15s;
  cursor: default;
  user-select: none;
}

/* 선택된 LoRA 항목 강조 */
.lora-item.lora-selected {
  background: #f0f7ff;
  border: 1px solid #bdd7f5;
}

/* 비호환 LoRA는 흐리게 + 클릭 불가 */
.lora-item.lora-disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 체크박스 + 이름 + 상태 배지가 가로로 배치되는 행 */
.lora-row-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lora-name { flex: 1; }

/* 설치 상태 배지 */
.lora-status {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
  white-space: nowrap;
}
.status-ok     { background: #e8f5e9; color: #2e7d32; }
.status-dl     { background: #fff8e1; color: #f57f17; }
.status-manual { background: #f3e5f5; color: #7b1fa2; }

/* 로드 중 / 오류 표시 */
.lora-loading { color: #888; font-size: 14px; padding: 10px; text-align: center; }
.lora-error   { color: #c62828; font-size: 13px; padding: 6px; }

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

/* ── img2img 섹션 ── */
.section-divider {
  border: none;
  border-top: 1px solid #e8e8e8;
  margin: 8px 0 20px;
}

.img2img-section { margin-bottom: 4px; }

/* 토글 레이블 — 체크박스 + 텍스트 인라인 배치 */
.img2img-toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  color: #333;
  user-select: none;
}

.img2img-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #4a90d9;
}

.img2img-toggle-text { line-height: 1; }

.img2img-desc {
  font-size: 12px;
  color: #888;
  margin: 6px 0 16px 24px;
}

/* img2img ON 시 표시되는 컨트롤 영역 */
.img2img-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #f8faff;
  border: 1px solid #dce8f8;
  border-radius: 10px;
  padding: 16px;
}

/* ── 이미지 업로드 영역 ── */
.upload-area-wrapper { width: 100%; }

.upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px dashed #bdd3f0;
  border-radius: 8px;
  min-height: 120px;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s, background 0.15s;
  position: relative;
  overflow: hidden;
}

.upload-area:hover:not(.has-image) {
  border-color: #4a90d9;
  background: #f0f7ff;
}

/* 이미지가 있을 때는 점선 대신 실선으로 강조 */
.upload-area.has-image {
  border-style: solid;
  border-color: #4a90d9;
  min-height: unset;
  cursor: default;
}

/* 실제 파일 input은 숨기고 label 전체를 클릭 영역으로 활용 */
.upload-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
}

.upload-icon {
  font-size: 28px;
  color: #93c5fd;
  line-height: 1;
  margin-bottom: 6px;
}

.upload-label {
  font-size: 13px;
  color: #4a90d9;
  font-weight: 600;
}

.upload-hint {
  font-size: 11px;
  color: #aaa;
  margin-top: 4px;
}

/* 미리보기 이미지 — 세로 최대 200px, 가로 비율 유지 */
.upload-preview {
  max-height: 200px;
  max-width: 100%;
  object-fit: contain;
  border-radius: 6px;
  display: block;
}

/* 이미지 제거 버튼 — 우상단 오버레이 */
.remove-image-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  z-index: 1;
  transition: background 0.12s;
}

.remove-image-btn:hover { background: rgba(220, 38, 38, 0.85); }

/* ── 수정 강도 슬라이더 ── */
.denoise-item {
  gap: 6px;
}

/* 레이블과 현재 값을 한 줄에 배치 */
.denoise-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #888;
  font-weight: 500;
}

.denoise-value {
  font-weight: 700;
  color: #4a90d9;
  font-size: 13px;
}

/* 슬라이더 전체 너비 */
.denoise-slider {
  width: 100%;
  accent-color: #4a90d9;
  cursor: pointer;
}

.denoise-hint {
  font-size: 11px;
  color: #aaa;
  margin: 2px 0 0;
}

/* ── 모델 설정 섹션 ── */
.optional-badge {
  font-size: 11px;
  background: #f0fdf4;
  color: #16a34a;
  padding: 2px 6px;
  border-radius: 8px;
  margin-left: 6px;
  vertical-align: middle;
}

.section-hint {
  font-size: 13px;
  color: #888;
  margin: 0 0 12px;
}

.hint-text {
  font-size: 11px;
  color: #aaa;
  font-weight: normal;
}

.field-hint {
  font-size: 11px;
  color: #aaa;
  margin: 4px 0 0;
}

.field-hint.warn { color: #d97706; }

/* CLIP 없는 체크포인트 선택 경고 */
.no-clip-warning {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fff7ed;
  border: 1px solid #fb923c;
  border-radius: 6px;
  color: #c2410c;
  font-size: 13px;
  line-height: 1.5;
}

/* ── LoRA 강도 슬라이더 ── */
.lora-strength-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 20px;
}

.strength-label {
  font-size: 11px;
  color: #666;
  min-width: 28px;
}

.strength-slider {
  flex: 1;
  accent-color: #4a90d9;
}

.strength-value {
  font-size: 12px;
  font-weight: 600;
  color: #333;
  min-width: 28px;
  text-align: right;
}
</style>
