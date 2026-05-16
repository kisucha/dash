<!-- StageResultViewer.vue — F001 스테이지별 결과 표시 컴포넌트 -->
<!-- output_data JSON을 파싱해 stage_id에 따라 맞춤형 결과 뷰어를 렌더링한다 -->
<script setup>
import { computed, ref } from 'vue'

// ── Props ──
// stage: 스테이지 객체 (stage_id, status, output_data 문자열 포함)
// jobId: 부모 작업 ID — 미디어 파일 경로 구성에 사용
const props = defineProps({
  stage: {
    type: Object,
    default: null,
  },
  jobId: {
    type: [Number, String],
    default: null,
  },
})

// ── Emits ──
// select-topic: 주제 선택 버튼 클릭 (STAGE_01_RESEARCH)
// approve: SEO 승인 버튼 클릭 (STAGE_06_UPLOAD)
const emit = defineEmits(['select-topic', 'approve', 'rerun-from-tts'])

// ── output_data 파싱 ──
// output_data는 JSON 문자열 또는 이미 파싱된 객체일 수 있으므로 방어적으로 처리
const parsedOutput = computed(() => {
  if (!props.stage?.output_data) return null
  if (typeof props.stage.output_data === 'object') return props.stage.output_data
  try {
    return JSON.parse(props.stage.output_data)
  } catch {
    return null
  }
})

// ── STAGE_06_UPLOAD: SEO 메타데이터 편집용 로컬 상태 ──
// 승인 시 편집된 값을 그대로 approve 이벤트로 전달한다
const editTitle = ref('')
const editDescription = ref('')
const editTags = ref('')  // 콤마 구분 문자열로 편집, 제출 시 배열로 변환

// SEO 데이터가 로드될 때 편집 폼 초기값 설정
const seoMeta = computed(() => {
  const out = parsedOutput.value
  if (!out) return null
  return out.seo_metadata ?? out
})

// seoMeta가 변경될 때 편집 필드 초기화
function initEditFields() {
  if (seoMeta.value) {
    editTitle.value = seoMeta.value.title ?? ''
    editDescription.value = seoMeta.value.description ?? ''
    const tags = seoMeta.value.tags ?? []
    editTags.value = Array.isArray(tags) ? tags.join(', ') : tags
  }
}

// computed watch 대신 스테이지 prop 변경 시 편집 필드 갱신
import { watch } from 'vue'
watch(() => props.stage, () => initEditFields(), { immediate: true })

// 주제 선택 핸들러
function handleSelectTopic(topic) {
  emit('select-topic', topic)
}

// 승인 핸들러 — 편집된 SEO 메타데이터를 포함해 approve 이벤트 발행
function handleApprove() {
  const finalMeta = {
    title: editTitle.value,
    description: editDescription.value,
    tags: editTags.value.split(',').map(t => t.trim()).filter(Boolean),
  }
  emit('approve', finalMeta)
}

// 미디어 파일 URL 조합 헬퍼 — 정적 서빙 경로 기준
function mediaUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return path
}

// 절대 경로를 /results/f001/{job_id}/... 형태 URL로 변환
// 예: "E:\Dash\storage\results\f001\17\thumbnails\thumbnail.png" → "/results/f001/17/thumbnails/thumbnail.png"
function f001AssetUrl(absPath) {
  if (!absPath) return ''
  if (absPath.startsWith('http')) return absPath
  const normalized = absPath.replace(/\\/g, '/')
  const marker = 'results/f001/'
  const idx = normalized.indexOf(marker)
  if (idx !== -1) return '/' + normalized.slice(idx)
  return absPath
}

// 절대 경로를 /results/f004/{job_id}/... 형태 URL로 변환
// 예: "E:\Dash\storage\results\f004\17\final\output.mp4" → "/results/f004/17/final/output.mp4"
function f004AssetUrl(absPath) {
  if (!absPath) return ''
  if (absPath.startsWith('http')) return absPath
  const normalized = absPath.replace(/\\/g, '/')
  const marker = 'results/f004/'
  const idx = normalized.indexOf(marker)
  if (idx !== -1) return '/' + normalized.slice(idx)
  return absPath
}

// TTS 오디오 URL — f004/f001 경로 모두 변환 처리
const ttsAudioUrl = computed(() => {
  const out = parsedOutput.value
  if (!out) return ''
  const path = out.audio_file_path
  if (!path) return `/results/f001/${props.jobId}/voiceover.mp3`
  if (path.includes('results/f004') || path.includes('results\\f004')) return f004AssetUrl(path)
  if (path.includes('results/f001') || path.includes('results\\f001')) return f001AssetUrl(path)
  return mediaUrl(path)
})

// 영상 편집 결과 비디오 URL — f004/f001 경로 모두 변환 처리
const editVideoUrl = computed(() => {
  const out = parsedOutput.value
  if (!out?.video_file_path) return ''
  const path = out.video_file_path
  if (path.includes('results/f004') || path.includes('results\\f004')) return f004AssetUrl(path)
  if (path.includes('results/f001') || path.includes('results\\f001')) return f001AssetUrl(path)
  return mediaUrl(path)
})

// 자막 파일 내용 (SRT) — STAGE_03 직접 생성분 + STAGE_05 편집 결과분 모두 처리
const subtitleContent = computed(() =>
  parsedOutput.value?.srt_content
  ?? parsedOutput.value?.subtitle_content
  ?? parsedOutput.value?.subtitle
  ?? ''
)

// STAGE_03 SRT 다운로드 핸들러
function downloadSrt() {
  const content = parsedOutput.value?.srt_content ?? ''
  if (!content) return
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `voiceover_job${props.jobId}.srt`
  a.click()
  URL.revokeObjectURL(url)
}

// SRT 접기/펼치기 상태
const srtExpanded = ref(false)

// 클립 목록 (STAGE_04_VIDEO_GEN)
const clipList = computed(() => parsedOutput.value?.clips ?? [])

// 썸네일 (STAGE_04_VIDEO_GEN)
const thumbnailPath = computed(() => parsedOutput.value?.thumbnail_path ?? null)
const thumbnailCandidates = computed(() => parsedOutput.value?.thumbnail_candidates ?? [])

// 스크립트 데이터 (STAGE_02_SCRIPT) — F001: hook/body/cta 구조, F004: slides/script_text 구조
const scriptData = computed(() => parsedOutput.value?.script ?? parsedOutput.value)

// STAGE_02 스크립트 편집 상태 (F004 전용)
const showScriptEdit = ref(false)
const editScriptText = ref('')

// 스크립트 편집 토글 — 편집 모드 진입 시 현재 script_text로 초기화
function toggleScriptEdit() {
  if (!showScriptEdit.value) {
    editScriptText.value = parsedOutput.value?.script_text ?? ''
  }
  showScriptEdit.value = !showScriptEdit.value
}

// TTS부터 재생성 emit
function handleRerunFromTTS() {
  emit('rerun-from-tts', {
    scriptText: editScriptText.value.trim(),
    slides: parsedOutput.value?.slides ?? null,
  })
  showScriptEdit.value = false
}

// 주제 목록 (STAGE_01_RESEARCH)
const topicList = computed(() => parsedOutput.value?.topics ?? [])
// 이미 선택된 주제 제목 — API가 selected_topic을 문자열로 저장하므로 방어적으로 처리
const selectedTopicTitle = computed(() => {
  const sel = parsedOutput.value?.selected_topic
  if (!sel) return null
  return typeof sel === 'string' ? sel : (sel.title ?? null)
})
</script>

<template>
  <div class="result-viewer">
    <!-- stage 없음 -->
    <div v-if="!stage" class="viewer-empty">스테이지를 선택하면 결과를 표시합니다.</div>

    <!-- FAILED — 오류 메시지 표시 -->
    <div v-else-if="stage.status === 'FAILED'" class="viewer-failed">
      <div class="failed-title">스테이지 실패</div>
      <div v-if="stage.rejection_reason" class="failed-reason">{{ stage.rejection_reason }}</div>
      <div v-else class="failed-reason failed-reason--empty">오류 메시지가 없습니다.</div>
    </div>

    <!-- output_data 없음 (PENDING 제외) -->
    <div v-else-if="!parsedOutput && stage.status !== 'PENDING'" class="viewer-empty">
      결과 데이터가 없습니다.
      <span v-if="stage.status === 'RUNNING'" class="running-hint">진행 중...</span>
    </div>

    <!-- STAGE_01_RESEARCH — 주제 발굴 결과 -->
    <div v-else-if="stage.stage_id === 'STAGE_01_RESEARCH'" class="stage-result">
      <h3 class="result-title">주제 발굴 결과</h3>
      <div v-if="topicList.length === 0" class="viewer-empty">주제 목록이 없습니다.</div>
      <div v-else class="topic-list">
        <div
          v-for="topic in topicList"
          :key="topic.rank"
          class="topic-card"
          :class="{ 'topic-selected': selectedTopicTitle === topic.title }"
        >
          <!-- 순위 배지 + 제목 -->
          <div class="topic-header">
            <span class="topic-rank">#{{ topic.rank }}</span>
            <span class="topic-title">{{ topic.title }}</span>
            <!-- 이미 선택된 주제 표시 -->
            <span v-if="selectedTopicTitle === topic.title" class="selected-badge">선택됨</span>
          </div>
          <!-- 점수 -->
          <div v-if="topic.score != null" class="topic-score">
            관련성 점수: <strong>{{ topic.score }}</strong>
          </div>
          <!-- 추천 이유 -->
          <div v-if="topic.recommended_reason" class="topic-reason">
            {{ topic.recommended_reason }}
          </div>
          <!-- 키워드 태그 -->
          <div v-if="topic.keywords && topic.keywords.length > 0" class="topic-keywords">
            <span v-for="kw in topic.keywords" :key="kw" class="keyword-tag">{{ kw }}</span>
          </div>
          <!-- 주제 선택 버튼 — 아직 선택 전이고 DONE 상태일 때만 표시 -->
          <button
            v-if="!selectedTopicTitle && stage.status === 'DONE'"
            class="btn-select-topic"
            @click="handleSelectTopic(topic)"
          >
            이 주제 선택
          </button>
        </div>
      </div>
    </div>

    <!-- STAGE_02_SCRIPT — 스크립트 결과 -->
    <div v-else-if="stage.stage_id === 'STAGE_02_SCRIPT'" class="stage-result">
      <h3 class="result-title">스크립트</h3>
      <div v-if="!parsedOutput" class="viewer-empty">스크립트 데이터가 없습니다.</div>

      <!-- ── F004 형식: slides + script_text ── -->
      <template v-else-if="parsedOutput.slides">

        <!-- 슬라이드 목록 -->
        <div class="f004-slide-list">
          <div class="f004-slide-list-header">슬라이드 구성 ({{ parsedOutput.slides.length }}장)</div>
          <div
            v-for="(slide, idx) in parsedOutput.slides"
            :key="idx"
            class="f004-slide-item"
          >
            <span class="f004-slide-num">{{ idx + 1 }}</span>
            <div class="f004-slide-body">
              <div class="f004-slide-title">{{ slide.title }}</div>
              <div v-if="slide.summary" class="f004-slide-summary">{{ slide.summary }}</div>
            </div>
          </div>
        </div>

        <!-- 나레이션 스크립트 + 편집 -->
        <div class="f004-narration-section">
          <div class="f004-narration-header">
            <span class="f004-narration-label">나레이션 스크립트</span>
            <button
              class="btn-script-edit"
              :class="{ active: showScriptEdit }"
              @click="toggleScriptEdit"
            >
              {{ showScriptEdit ? '취소' : '스크립트 편집' }}
            </button>
          </div>

          <!-- 편집 모드 -->
          <div v-if="showScriptEdit" class="f004-edit-zone">
            <textarea
              v-model="editScriptText"
              class="script-edit-textarea"
              rows="14"
              placeholder="나레이션 스크립트를 수정하세요..."
            ></textarea>
            <div class="f004-edit-actions">
              <span class="f004-char-count">{{ editScriptText.length }}자</span>
              <button
                class="btn-rerun-tts"
                :disabled="!editScriptText.trim()"
                @click="handleRerunFromTTS"
              >
                TTS부터 재생성
              </button>
            </div>
          </div>

          <!-- 읽기 모드 -->
          <pre v-else class="f004-script-readonly">{{ parsedOutput.script_text }}</pre>
        </div>
      </template>

      <!-- ── F001 형식: hook / body / cta ── -->
      <div v-else class="script-view">
        <div v-if="scriptData.hook" class="script-section">
          <div class="script-section-label">Hook (도입)</div>
          <div class="script-text">{{ scriptData.hook }}</div>
        </div>
        <div v-if="scriptData.body" class="script-section">
          <div class="script-section-label">본문</div>
          <template v-if="Array.isArray(scriptData.body)">
            <div v-for="(section, idx) in scriptData.body" :key="idx" class="script-body-section">
              <div v-if="section.title" class="body-section-title">{{ section.title }}</div>
              <div class="script-text">{{ section.content ?? section }}</div>
            </div>
          </template>
          <div v-else class="script-text">{{ scriptData.body }}</div>
        </div>
        <div v-if="scriptData.cta" class="script-section">
          <div class="script-section-label">CTA (행동 유도)</div>
          <div class="script-text">{{ scriptData.cta }}</div>
        </div>
      </div>
    </div>

    <!-- STAGE_03_TTS — TTS 오디오 + SRT 자막 결과 -->
    <div v-else-if="stage.stage_id === 'STAGE_03_TTS'" class="stage-result">
      <h3 class="result-title">TTS 음성</h3>
      <!-- SKIPPED 처리 -->
      <div v-if="stage.status === 'SKIPPED'" class="viewer-empty skipped-msg">
        TTS 건너뜀 (tts_skip 설정)
      </div>
      <div v-else-if="ttsAudioUrl" class="tts-player">
        <audio :src="ttsAudioUrl" controls class="audio-player"></audio>
        <p class="file-path-hint">{{ ttsAudioUrl }}</p>
      </div>
      <div v-else class="viewer-empty">오디오 파일이 없습니다.</div>

      <!-- SRT 자막 섹션 -->
      <div v-if="subtitleContent" class="srt-section">
        <div class="srt-header">
          <span class="srt-label">SRT 자막</span>
          <div class="srt-actions">
            <button class="btn-srt-toggle" @click="srtExpanded = !srtExpanded">
              {{ srtExpanded ? '접기' : '펼치기' }}
            </button>
            <button class="btn-srt-download" @click="downloadSrt">다운로드</button>
          </div>
        </div>
        <pre v-if="srtExpanded" class="srt-content">{{ subtitleContent }}</pre>
      </div>
    </div>

    <!-- STAGE_04_VIDEO_GEN — 영상/이미지 클립 결과 -->
    <div v-else-if="stage.stage_id === 'STAGE_04_VIDEO_GEN'" class="stage-result">
      <h3 class="result-title">영상 클립</h3>
      <!-- SKIPPED 처리 -->
      <div v-if="stage.status === 'SKIPPED'" class="viewer-empty skipped-msg">
        영상 생성 건너뜀 (skip_mode: {{ parsedOutput?.skip_mode ?? 'unknown' }})
      </div>
      <div v-else-if="clipList.length === 0" class="viewer-empty">클립 파일이 없습니다.</div>
      <div v-else class="clip-grid">
        <div v-for="(clip, idx) in clipList" :key="idx" class="clip-item">
          <!-- 영상 파일이면 video 태그, 이미지면 img 태그 -->
          <video
            v-if="clip.path && (clip.path.endsWith('.mp4') || clip.path.endsWith('.webm'))"
            :src="`/results/f001/${jobId}/clips/${clip.filename ?? clip.path.split('/').pop()}`"
            controls
            class="clip-media"
          ></video>
          <img
            v-else
            :src="`/results/f001/${jobId}/clips/${clip.filename ?? clip.path?.split('/').pop() ?? clip}`"
            :alt="`클립 ${idx + 1}`"
            class="clip-media clip-image"
          />
          <div class="clip-label">
            클립 {{ idx + 1 }}
            <span v-if="clip.source" class="clip-source-badge" :class="clip.source === 'img2img' ? 'badge-img2img' : 'badge-txt2img'">
              {{ clip.source }}
            </span>
          </div>
          <div v-if="clip.caption" class="clip-caption">{{ clip.caption }}</div>
        </div>
      </div>

      <!-- 썸네일 섹션 -->
      <div v-if="thumbnailPath" class="thumbnail-section">
        <div class="thumbnail-header">
          <span class="thumbnail-label">생성된 썸네일</span>
        </div>
        <img
          :src="f001AssetUrl(thumbnailPath)"
          alt="썸네일"
          class="thumbnail-img"
          @error="(e) => e.target.style.display='none'"
        />
        <p class="file-path-hint">{{ thumbnailPath }}</p>
      </div>

      <!-- 썸네일 후보 목록 -->
      <div v-if="thumbnailCandidates.length > 1" class="thumbnail-candidates">
        <div class="thumbnail-candidates-label">썸네일 후보</div>
        <div class="thumbnail-candidates-grid">
          <img
            v-for="(c, i) in thumbnailCandidates"
            :key="i"
            :src="f001AssetUrl(c)"
            :alt="`후보 ${i + 1}`"
            class="thumbnail-candidate-img"
            @error="(e) => e.target.style.display='none'"
          />
        </div>
      </div>
    </div>

    <!-- STAGE_05_EDIT — 영상 편집 결과 -->
    <div v-else-if="stage.stage_id === 'STAGE_05_EDIT'" class="stage-result">
      <h3 class="result-title">편집 영상</h3>
      <div v-if="editVideoUrl" class="video-player-wrap">
        <video :src="editVideoUrl" controls class="video-player"></video>
        <p class="file-path-hint">{{ editVideoUrl }}</p>
      </div>
      <div v-else class="viewer-empty">영상 파일이 없습니다.</div>
      <!-- 자막 내용 표시 -->
      <div v-if="subtitleContent" class="subtitle-section">
        <div class="subtitle-label">자막 (SRT)</div>
        <pre class="subtitle-content">{{ subtitleContent }}</pre>
      </div>
    </div>

    <!-- STAGE_06_UPLOAD — SEO 메타데이터 편집 + 업로드 승인 -->
    <div v-else-if="stage.stage_id === 'STAGE_06_UPLOAD'" class="stage-result">
      <h3 class="result-title">SEO / 업로드</h3>

      <!-- 업로드 완료 배너 -->
      <div v-if="parsedOutput?.upload_status === 'UPLOADED'" class="uploaded-banner">
        <span class="uploaded-icon">✅</span>
        <span class="uploaded-text">YouTube 업로드 완료!</span>
        <a
          v-if="parsedOutput.youtube_url"
          :href="parsedOutput.youtube_url"
          target="_blank"
          class="youtube-link-btn"
        >
          YouTube에서 보기 →
        </a>
      </div>

      <!-- 업로드 상태 태그 (완료가 아닌 경우) -->
      <div v-else-if="parsedOutput?.upload_status" class="upload-status-row">
        <span class="upload-status-label">업로드 상태:</span>
        <span class="upload-status-value" :class="{ 'status-pending': parsedOutput.upload_status === 'PENDING_APPROVAL' }">
          {{ parsedOutput.upload_status }}
        </span>
      </div>

      <!-- SEO 메타데이터 편집 폼 (업로드 완료 전까지 표시) -->
      <div v-if="parsedOutput?.upload_status !== 'UPLOADED'" class="seo-form">
        <div class="form-item">
          <label class="form-label">제목</label>
          <input type="text" v-model="editTitle" class="form-input" placeholder="YouTube 영상 제목" />
        </div>
        <div class="form-item">
          <label class="form-label">설명</label>
          <textarea v-model="editDescription" class="form-textarea" rows="5" placeholder="YouTube 영상 설명"></textarea>
        </div>
        <div class="form-item">
          <label class="form-label">태그 <span class="form-hint">(콤마로 구분)</span></label>
          <input type="text" v-model="editTags" class="form-input" placeholder="태그1, 태그2, 태그3" />
        </div>
      </div>

      <!-- PENDING_APPROVAL: 승인 버튼 (stage.status 또는 upload_status 기준) -->
      <div v-if="(stage.status === 'PENDING_APPROVAL' || parsedOutput?.upload_status === 'PENDING_APPROVAL') && parsedOutput?.upload_status !== 'UPLOADED'" class="approve-section">
        <p class="approve-hint">SEO 메타데이터를 검토하고 승인하면 YouTube에 업로드됩니다.</p>
        <button class="btn-approve" @click="handleApprove">승인 및 YouTube 업로드</button>
      </div>

      <!-- 업로드 완료 시 video_id 표시 -->
      <div v-if="parsedOutput?.youtube_video_id && parsedOutput?.upload_status === 'UPLOADED'" class="video-id-row">
        <span class="video-id-label">Video ID:</span>
        <code class="video-id-value">{{ parsedOutput.youtube_video_id }}</code>
      </div>
    </div>

    <!-- 그 외 스테이지 — 원시 JSON 표시 -->
    <div v-else-if="parsedOutput" class="stage-result">
      <h3 class="result-title">결과 데이터 ({{ stage.stage_id }})</h3>
      <pre class="raw-json">{{ JSON.stringify(parsedOutput, null, 2) }}</pre>
    </div>

    <!-- PENDING 상태 -->
    <div v-else-if="stage.status === 'PENDING'" class="viewer-empty">대기 중...</div>
  </div>
</template>

<style scoped>
/* 결과 뷰어 래퍼 */
.result-viewer {
  height: 100%;
  overflow-y: auto;
}

/* ── 빈 상태 메시지 ── */
.viewer-empty {
  font-size: 13px;
  color: #aaa;
  text-align: center;
  padding: 24px 0;
}

.running-hint {
  display: block;
  color: #3b82f6;
  font-weight: 500;
  margin-top: 6px;
}

/* ── FAILED 오류 메시지 ── */
.viewer-failed {
  padding: 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  margin: 8px 0;
}

.failed-title {
  font-size: 13px;
  font-weight: 700;
  color: #991b1b;
  margin-bottom: 8px;
}

.failed-reason {
  font-size: 12px;
  color: #7f1d1d;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  background: #fff5f5;
  border-radius: 4px;
  padding: 8px 10px;
}

.failed-reason--empty {
  color: #aaa;
  font-style: italic;
}

.skipped-msg {
  color: #9ca3af;
  font-style: italic;
}

/* ── 결과 공통 ── */
.stage-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.result-title {
  font-size: 15px;
  font-weight: 700;
  color: #333;
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

/* ── STAGE_01: 주제 발굴 ── */
.topic-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.topic-card {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px 14px;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.12s;
}

.topic-card.topic-selected {
  border-color: #16a34a;
  background: #f0fdf4;
}

.topic-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.topic-rank {
  font-size: 12px;
  font-weight: 700;
  color: #4a90d9;
  min-width: 24px;
}

.topic-title {
  font-size: 14px;
  font-weight: 600;
  color: #222;
  flex: 1;
}

.selected-badge {
  font-size: 11px;
  background: #dcfce7;
  color: #166534;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.topic-score {
  font-size: 12px;
  color: #888;
}

.topic-reason {
  font-size: 13px;
  color: #555;
  line-height: 1.5;
}

.topic-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.keyword-tag {
  font-size: 11px;
  background: #e0e7ff;
  color: #4338ca;
  padding: 2px 8px;
  border-radius: 10px;
}

.btn-select-topic {
  align-self: flex-end;
  margin-top: 4px;
  font-size: 12px;
  padding: 5px 14px;
  background: #4a90d9;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.12s;
}
.btn-select-topic:hover { background: #357abd; }

/* ── STAGE_02: 스크립트 ── */
.script-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.script-section {
  border-left: 3px solid #dbeafe;
  padding-left: 12px;
}

.script-section-label {
  font-size: 11px;
  font-weight: 700;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}

.script-body-section {
  margin-bottom: 8px;
}

.body-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #444;
  margin-bottom: 4px;
}

.script-text {
  font-size: 13px;
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
}

/* ── STAGE_03: TTS ── */
.tts-player {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.audio-player {
  width: 100%;
}

/* ── SRT 자막 섹션 ── */
.srt-section {
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  overflow: hidden;
  margin-top: 4px;
}

.srt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #eef2ff;
}

.srt-label {
  font-size: 12px;
  font-weight: 700;
  color: #4338ca;
}

.srt-actions {
  display: flex;
  gap: 6px;
}

.btn-srt-toggle,
.btn-srt-download {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.12s;
}

.btn-srt-toggle {
  background: #fff;
  border: 1px solid #c7d2fe;
  color: #4338ca;
}
.btn-srt-toggle:hover { background: #e0e7ff; }

.btn-srt-download {
  background: #4338ca;
  border: none;
  color: #fff;
}
.btn-srt-download:hover { background: #3730a3; }

.srt-content {
  font-size: 11px;
  color: #444;
  background: #f8f8ff;
  padding: 12px 14px;
  margin: 0;
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-family: monospace;
  line-height: 1.6;
  border-top: 1px solid #e0e7ff;
}

/* ── STAGE_04: 클립 그리드 ── */
.clip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.clip-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.clip-media {
  width: 100%;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
  background: #000;
}

.clip-image {
  object-fit: contain;
  max-height: 180px;
  background: #f0f0f0;
}

.clip-label {
  font-size: 11px;
  color: #888;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  flex-wrap: wrap;
}

.clip-source-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}

.badge-img2img {
  background: #dcfce7;
  color: #166534;
}

.badge-txt2img {
  background: #dbeafe;
  color: #1e40af;
}

.clip-caption {
  font-size: 10px;
  color: #aaa;
  text-align: center;
  line-height: 1.4;
  word-break: break-word;
  max-height: 40px;
  overflow: hidden;
}

/* ── 썸네일 섹션 ── */
.thumbnail-section {
  border: 1px solid #fde68a;
  border-radius: 8px;
  overflow: hidden;
  margin-top: 8px;
}

.thumbnail-header {
  background: #fef3c7;
  padding: 8px 12px;
}

.thumbnail-label {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
}

.thumbnail-img {
  width: 100%;
  display: block;
  max-height: 300px;
  object-fit: cover;
  background: #f0f0f0;
}

.thumbnail-candidates {
  margin-top: 8px;
}

.thumbnail-candidates-label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  margin-bottom: 6px;
}

.thumbnail-candidates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px;
}

.thumbnail-candidate-img {
  width: 100%;
  height: 90px;
  object-fit: cover;
  border-radius: 5px;
  border: 1px solid #e0e0e0;
  background: #f0f0f0;
  cursor: pointer;
  transition: opacity 0.12s;
}
.thumbnail-candidate-img:hover { opacity: 0.85; }

/* ── STAGE_05: 편집 영상 ── */
.video-player-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.video-player {
  width: 100%;
  border-radius: 8px;
  background: #000;
}

.subtitle-section {
  margin-top: 8px;
}

.subtitle-label {
  font-size: 12px;
  font-weight: 600;
  color: #888;
  margin-bottom: 4px;
}

.subtitle-content {
  font-size: 11px;
  color: #555;
  background: #f8f8f8;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
  overflow-x: auto;
  max-height: 200px;
  white-space: pre-wrap;
  font-family: monospace;
}

/* ── STAGE_06: SEO/업로드 ── */
.upload-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 4px;
}

.upload-status-label { color: #666; }
.upload-status-value { font-weight: 600; color: #333; }

.seo-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.form-hint {
  font-size: 11px;
  font-weight: normal;
  color: #aaa;
}

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
  border-color: #4a90d9;
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
  border-color: #4a90d9;
}

.approve-section {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.approve-hint {
  font-size: 12px;
  color: #666;
  margin: 0;
  background: #ede9fe;
  padding: 8px 12px;
  border-radius: 6px;
  border-left: 3px solid #8b5cf6;
}

.btn-approve {
  align-self: flex-end;
  padding: 8px 20px;
  background: #16a34a;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s;
}
.btn-approve:hover { background: #15803d; }

.upload-link-section { margin-top: 8px; }

.video-link {
  color: #4a90d9;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
}
.video-link:hover { text-decoration: underline; }

/* ── 파일 경로 힌트 ── */
.file-path-hint {
  font-size: 11px;
  color: #aaa;
  font-family: monospace;
  margin: 2px 0 0;
  word-break: break-all;
}

/* ── 원시 JSON ── */
.raw-json {
  font-size: 11px;
  color: #555;
  background: #f8f8f8;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
  overflow-x: auto;
  max-height: 400px;
  white-space: pre-wrap;
  font-family: monospace;
}

/* ── STAGE_02 F004 슬라이드 + 스크립트 편집 ── */
.f004-slide-list {
  margin-bottom: 18px;
}

.f004-slide-list-header {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.f004-slide-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 6px;
  background: #fafafa;
}

.f004-slide-num {
  min-width: 24px;
  height: 24px;
  background: #1565c0;
  color: #fff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.f004-slide-body {
  flex: 1;
  min-width: 0;
}

.f004-slide-title {
  font-size: 13px;
  font-weight: 600;
  color: #222;
}

.f004-slide-summary {
  font-size: 12px;
  color: #666;
  margin-top: 3px;
  white-space: pre-wrap;
  word-break: break-word;
}

.f004-narration-section {
  border: 1px solid #dde4ef;
  border-radius: 8px;
  overflow: hidden;
}

.f004-narration-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f0f4ff;
  border-bottom: 1px solid #dde4ef;
}

.f004-narration-label {
  font-size: 13px;
  font-weight: 600;
  color: #1565c0;
}

.btn-script-edit {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid #1565c0;
  border-radius: 5px;
  background: #fff;
  color: #1565c0;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.btn-script-edit:hover,
.btn-script-edit.active {
  background: #1565c0;
  color: #fff;
}

.f004-script-readonly {
  padding: 14px;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
  max-height: 360px;
  overflow-y: auto;
  margin: 0;
}

.f004-edit-zone {
  padding: 12px 14px;
}

.script-edit-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  font-size: 13px;
  line-height: 1.7;
  border: 1px solid #ccc;
  border-radius: 6px;
  resize: vertical;
  font-family: inherit;
  color: #333;
}

.f004-edit-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 10px;
}

.f004-char-count {
  font-size: 12px;
  color: #888;
}

.btn-rerun-tts {
  padding: 8px 18px;
  background: #e65100;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-rerun-tts:hover:not(:disabled) {
  background: #bf360c;
}

.btn-rerun-tts:disabled {
  background: #bbb;
  cursor: not-allowed;
}

/* ── STAGE_06 업로드 완료 배너 ── */
.uploaded-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #e8f5e9;
  border: 1px solid #66bb6a;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.uploaded-icon {
  font-size: 20px;
  line-height: 1;
}

.uploaded-text {
  font-size: 15px;
  font-weight: 600;
  color: #2e7d32;
}

.youtube-link-btn {
  display: inline-block;
  margin-left: auto;
  padding: 6px 14px;
  background: #ff0000;
  color: #fff;
  border: none;
  border-radius: 5px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.2s;
}

.youtube-link-btn:hover {
  background: #cc0000;
}

/* ── upload_status 뱃지 ── */
.upload-status-value {
  font-weight: 600;
  color: #1565c0;
}

.upload-status-value.status-pending {
  color: #e65100;
}

/* ── YouTube video ID 행 ── */
.video-id-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 10px 14px;
  background: #f3f8ff;
  border: 1px solid #90caf9;
  border-radius: 6px;
  font-size: 13px;
}

.video-id-label {
  color: #555;
  font-weight: 500;
  white-space: nowrap;
}

.video-id-value {
  font-family: monospace;
  font-size: 13px;
  color: #1a237e;
  word-break: break-all;
}
</style>
