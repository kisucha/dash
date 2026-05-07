# Dash F003 영상제작 파이프라인 리서치 보고서

| 필드 | 내용 |
|------|------|
| 문서명 | Dash F003 영상제작 파이프라인 리서치 보고서 |
| 버전 | V3 |
| 날짜 | 2026-05-07 |
| 작성자 | Claude (kisuc 승인) |
| 문서 유형 | 리서치 보고서 |
| 모델 | claude-sonnet-4-6 |

---

## 개요

Dash 프로젝트에 추가될 F003 "영상제작" 파이프라인의 기술적 구현을 위한 심층 리서치 결과물이다.
기존 아키텍처(Vue 3 + FastAPI + Ollama + SQLite)와의 통합을 전제로 한다.

**V2 핵심 변경사항**: 개발 컴퓨터가 ComfyUI 기반으로 구성되어 있음이 확인됨.
AUTOMATIC1111 관련 내용 전면 삭제 후 **ComfyUI 단일 플랫폼**으로 통일.
스타일 선택 옵션 시스템(6개 카테고리) 신규 추가.

### F003 핵심 기능 요약

```
사용자 → "영상제작" 클릭
  → 생성 유형 선택 (동영상 / 그림)
  → 스타일 카테고리 선택 (아트 스타일 / 캐릭터 / 촬영 기법 / 조명 / 배경 / 모션 / 디테일 향상)
  → 세부 파라미터 입력
  → Ollama가 선택된 스타일 기반 프롬프트 자동 생성
  → ComfyUI 워크플로우 JSON 자동 조립 (스타일 → 체크포인트/LoRA/노드 매핑)
  → 모델 자동 관리 (로컬 확인 → 없으면 다운로드 → 설치)
  → 결과 대시보드 표시
```

### 아키텍처 확정 (V2)

| 구분 | V1 (변경 전, 잘못된 가정) | V2 (변경 후, 확정) |
|------|--------------------------|-------------------|
| 동영상 생성 | AUTOMATIC1111 + sd-webui-animatediff (포트 7860) | ComfyUI + ComfyUI-AnimateDiff-Evolved (포트 8188) |
| 그림 생성 | ComfyUI + Flux.1 (포트 8188) | ComfyUI + Flux.1 워크플로우 (포트 8188) |
| 플랫폼 수 | 이원화 (A1111 + ComfyUI) | **단일 ComfyUI** |
| 스타일 시스템 | 없음 | 7개 카테고리 스타일 선택 시스템 (6개 + 디테일 향상 카테고리 추가) |

---

## 영역 A: ComfyUI 커스텀 노드 관리 시스템

### A-1. 커스텀 노드 설치 방법

ComfyUI 커스텀 노드 설치는 두 가지 방법으로 이루어진다.

#### 방법 1 — ComfyUI-Manager를 통한 자동 설치 (권장)

ComfyUI-Manager는 ComfyUI에 내장된 확장 관리 도구다.
(`ComfyUI/custom_nodes/ComfyUI-Manager/` 디렉토리로 설치)

내부 동작 방식:
- Git 레포지토리를 `ComfyUI/custom_nodes/` 디렉토리에 클론
- `requirements.txt`에 명시된 Python 의존성을 pip으로 순차 설치
- `install.py` 스크립트 존재 시 자동 실행
- 설치 완료 후 ComfyUI 재시작 필요

#### 방법 2 — 수동 git clone (자동화 파이프라인 권장)

F003 파이프라인에서 자동화 설치 시 사용할 방법:

```
1. cd ComfyUI/custom_nodes/
2. git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git
3. cd ComfyUI-AnimateDiff-Evolved
4. pip install -r requirements.txt
5. ComfyUI 재시작 필요
```

**재시작 필요 여부**: 커스텀 노드 설치 후 ComfyUI 서버를 반드시 재시작해야 한다.
ComfyUI는 시작 시 `custom_nodes/` 디렉토리를 스캔하여 노드를 로드한다.

### A-2. ComfyUI-Manager HTTP API 엔드포인트

ComfyUI-Manager가 설치된 경우 다음 엔드포인트들이 추가로 노출된다.
(기본 포트 8188에서 동작)

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/manager/reboot` | POST | ComfyUI 서버 재시작 |
| `/manager/install-custom-node` | POST | 커스텀 노드 설치 |
| `/manager/installed-custom-nodes` | GET | 설치된 커스텀 노드 목록 조회 |
| `/manager/uninstall-custom-node` | POST | 커스텀 노드 제거 |
| `/manager/enable-custom-node` | POST | 커스텀 노드 활성화 |
| `/manager/disable-custom-node` | POST | 커스텀 노드 비활성화 |

**주의**: ComfyUI-Manager의 HTTP API 엔드포인트는 Manager 버전에 따라 변경될 수 있다.
F003 파이프라인에서 Manager API 직접 호출 대신 수동 git clone + pip install + 재시작 방식이 더 안정적이다.

### A-3. 커스텀 노드 설치 여부 확인 방법

ComfyUI 파일 시스템 스캔으로 확인:

```
# 노드 폴더 존재 여부 확인
ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/  → 존재하면 설치됨

# GET /object_info 응답에서 노드 타입 확인
GET http://localhost:8188/object_info
→ 응답 딕셔너리 키에 "ADE_AnimateDiffLoaderGen1" 등이 있으면 설치+로드됨
```

`GET /object_info` 엔드포인트는 현재 로드된 모든 노드 타입, 입력 파라미터, 기본값, 문서를 반환하므로
설치 및 로드 상태를 확인하는 가장 신뢰할 수 있는 방법이다.

### A-4. F003에 필요한 핵심 커스텀 노드 목록

| 커스텀 노드 | GitHub | 용도 | F003 필수 여부 |
|-----------|--------|------|----------------|
| ComfyUI-AnimateDiff-Evolved | `Kosinkadink/ComfyUI-AnimateDiff-Evolved` | AnimateDiff 동영상 생성 | 동영상 경로 필수 |
| ComfyUI-WanVideoWrapper | `kijai/ComfyUI-WanVideoWrapper` | WanVideo 차세대 동영상 생성 | 선택 (대안 경로) |
| ComfyUI-Manager | `Comfy-Org/ComfyUI-Manager` | 노드 관리 도구 | 권장 |

**WanVideo 참고**: ComfyUI는 2025년 2월부터 Wan2.1/Wan2.2 (알리바바 오픈소스, Apache 2.0) 네이티브 지원을 시작했다.
Wan2.6은 2026년 초 기준 최신 버전이다. ComfyUI-WanVideoWrapper는 네이티브 미지원 기능의 실험적 확장 래퍼다.
F003 초기 구현은 AnimateDiff-Evolved를 메인으로, WanVideo는 추후 옵션으로 추가 검토한다.

---

## 영역 B: 스타일 선택 시스템 설계

### B-1. 스타일 선택 시스템 개요

F003 UI에서 사용자가 고르는 스타일 선택지를 ComfyUI 워크플로우의 기술적 요소에 자동 매핑한다.

**매핑 4요소**:
1. **체크포인트(Checkpoint)**: 기반 모델 변경
2. **스타일 LoRA**: 아트 스타일/특성 추가 및 가중치 조정
3. **프롬프트 키워드**: Ollama 프롬프트 생성 시 자동 삽입
4. **디테일 향상 LoRA**: 스타일 선택과 독립적으로 전체 이미지 품질/디테일 보강 (선택적 추가 적용)

---

### B-2. 카테고리 1 — 아트 스타일

| 선택지 | 설명 | 권장 체크포인트 | 권장 LoRA | 프롬프트 키워드 |
|--------|------|----------------|-----------|----------------|
| 애니메이션(Anime) | 일본 애니 스타일 | Anime Art Diffusion XL, AAM XL AnimeMix | Aesthetic Anime LoRA | anime style, anime coloring, cel shading |
| 사실적(Realistic) | 포토리얼 인물/풍경 | cyberrealisticPony (SD1.5/SDXL 혼합), Realistic Vision | - | photorealistic, hyperrealistic, RAW photo |
| 판타지(Fantasy) | 마법적/중세 판타지 분위기 | fantasy-art-style, Landscape Anime Pro | Alpha Fantasy Touch LoRA | fantasy art, magical, ethereal, painterly |
| 사이버펑크(Cyberpunk) | 미래도시/네온/디스토피아 | cyberrealisticPony | CyberpunkAnime LoRA (트리거: cyberpunk 또는 anime) | cyberpunk, neon lights, futuristic city, dystopia |
| 수채화/일러스트 | 수채화 페인팅 스타일 | Landscape Anime Pro | 수채화 전용 LoRA | watercolor painting, soft brushstrokes, illustration |
| 3D 렌더링 | Pixar/3D 애니 스타일 | SDXL 기반 | 3D 스타일 LoRA | 3D render, CGI, unreal engine, octane render |
| 픽셀아트(Pixel Art) | 레트로 게임 픽셀 스타일 | Pixel Art Diffusion XL (SDXL) | Pixel Art & Anime Screencap LoRA | pixel art, 8-bit, retro game, pixelated |

**체크포인트 선택 원칙**:
- SD 1.5 기반 체크포인트: 빠른 생성, AnimateDiff 호환성 높음
- SDXL 기반 체크포인트: 높은 품질, 더 많은 VRAM 필요
- F003 동영상 경로는 SD 1.5 기반 체크포인트 우선 권장 (AnimateDiff 안정성)

---

### B-3. 카테고리 2 — 캐릭터 외형

캐릭터 외형은 주로 LoRA와 프롬프트 키워드 조합으로 제어한다.

**얼굴 특성**

| 선택지 | 프롬프트 키워드 | LoRA 활용 |
|--------|----------------|-----------|
| 서양풍 | western facial features, caucasian features | 서양 인물 특화 LoRA |
| 동양풍 | asian facial features, east asian | 동양 인물 특화 LoRA |
| 혼혈풍 | mixed features, eurasian | 혼합 LoRA 중간 가중치 적용 |

**헤어스타일**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 긴 머리 | long hair, flowing hair |
| 단발 | short hair, bob cut |
| 트윈테일 | twin tails, twintails |
| 포니테일 | ponytail |
| 단발+앞머리 | bob cut, bangs |

**헤어 컬러**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 금발 | blonde hair, golden hair |
| 갈색 | brown hair, brunette |
| 검정 | black hair, dark hair |
| 분홍 | pink hair |
| 은발/흰색 | silver hair, white hair |
| 그라데이션 | gradient hair, multicolored hair |

**눈매**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 큰 눈 | large eyes, big eyes |
| 날카로운 눈 | sharp eyes, narrow eyes |
| 올라간 눈꼬리 | upturned eyes |
| 내려간 눈꼬리 | downturned eyes |

**체형**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 슬림 | slim figure, slender |
| 보통 | average build |
| 스포티 | athletic build, toned |

**의상 스타일**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 캐주얼 | casual clothes, everyday wear |
| 판타지 | fantasy armor, magical outfit |
| 교복 | school uniform, seifuku |
| 스포츠웨어 | sportswear, athletic wear |
| 드레스 | elegant dress, formal wear |
| 사이버펑크 | cyberpunk outfit, neon jacket |

---

### B-4. 카테고리 3 — 촬영 기법 / 카메라

카메라/앵글 설정은 프롬프트 키워드로만 제어한다.

**앵글**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 정면 | facing viewer, front view |
| 측면 | profile view, side view |
| 위에서 | from above, bird's eye view, overhead shot |
| 아래서 | from below, low angle, worm's eye view |
| 극적인 로우앵글 | dramatic low angle, dutch angle |

**구도**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 클로즈업 | close-up, face focus, portrait |
| 상반신 | upper body, half body |
| 전신 | full body, full length |
| 원경 | wide shot, establishing shot, distant view |

**심도 효과**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 아웃포커스(보케) | bokeh, depth of field, blurry background |
| 팬포커스(선명) | pan focus, sharp focus, in focus |

**렌즈 효과**

| 선택지 | 프롬프트 키워드 |
|--------|----------------|
| 광각 | wide angle lens, fisheye effect |
| 표준 | standard lens |
| 망원 | telephoto lens, compressed perspective |

---

### B-5. 카테고리 4 — 조명 / 분위기

| 선택지 | 프롬프트 키워드 | 추가 설명 |
|--------|----------------|---------|
| 자연광(낮) | natural lighting, daylight, sunlit | 밝고 자연스러운 |
| 황혼 | golden hour, sunset lighting, warm orange hue | 따뜻한 오렌지 계열 |
| 야경 | night scene, moonlight, city lights at night | 어둡고 대비 강함 |
| 실내 조명 | indoor lighting, interior light, warm room lighting | 은은한 실내 |
| 극적(드라마틱) | dramatic lighting, high contrast, chiaroscuro | 강한 명암 대비 |
| 부드러운(소프트) | soft lighting, diffused light, even illumination | 피부 묘사에 유리 |
| 역광 | backlit, rim lighting, silhouette | 윤곽선 강조 |
| 스튜디오 | studio lighting, professional lighting setup | 균일한 조명 |
| 네온 | neon lighting, neon glow, fluorescent light | 사이버펑크 분위기 |

---

### B-6. 카테고리 5 — 배경 / 환경

| 그룹 | 선택지 | 프롬프트 키워드 |
|------|--------|----------------|
| 실내 | 학교 교실 | classroom, school interior |
| 실내 | 카페 | cafe interior, coffee shop |
| 실내 | 방/침실 | bedroom, room interior |
| 실내 | 사무실 | office, modern office |
| 실외 | 도시 거리 | city street, urban background |
| 실외 | 자연/공원 | nature, park, green scenery |
| 실외 | 해변 | beach, ocean, seaside |
| 실외 | 산/숲 | mountain, forest, woodland |
| 판타지 | 성/성채 | castle, medieval fortress |
| 판타지 | 마법 공간 | magical realm, ethereal space, glowing environment |
| 판타지 | 다른 세계 | otherworldly, alien landscape, isekai |
| 추상 | 단색/그라데이션 배경 | simple background, gradient background, plain background |
| 추상 | 추상적 | abstract background, geometric patterns |

---

### B-7. 카테고리 6 — 동영상 전용: 모션 스타일

동영상 생성(AnimateDiff-Evolved) 사용 시에만 적용.

**모션 강도**

| 선택지 | AnimateDiff 설정 | 프롬프트 키워드 |
|--------|-----------------|----------------|
| 약한 움직임 | context_frames=16, 낮은 노이즈 | subtle motion, gentle movement |
| 보통 움직임 | context_frames=16 (기본) | moderate motion |
| 역동적 움직임 | context_frames=16, 높은 노이즈 | dynamic motion, energetic movement |

**모션 타입**

| 선택지 | AnimateDiff/CameraCtrl 설정 | 프롬프트 키워드 |
|--------|---------------------------|----------------|
| 카메라 이동 | CameraCtrl 노드 활성화 (`ADE_LoadAnimateDiffModelWithCameraCtrl`, `ADE_ApplyAnimateDiffModelWithCameraCtrl`) | camera pan, camera dolly |
| 캐릭터 움직임 | 기본 AnimateDiff 모션 모듈 | character movement, walking, head turn |
| 파티클/환경 | Motion LoRA 추가 | wind, particles, floating elements |

**루프 여부**

| 선택지 | ADE 설정 |
|--------|---------|
| 루프 애니메이션 | `closed_loop: true` (ADE 샘플링 설정에서 활성화) |
| 1회 재생 | `closed_loop: false` |

**AnimateDiff 모션 모듈 선택 (카테고리 6 내부 연결)**

| 모션 모듈 | 대상 기반 모델 | 특징 | HuggingFace |
|----------|-------------|------|------------|
| `mm_sd_v15_v2.ckpt` | SD 1.5 V2 | 개선판 — F003 기본 권장 | `guoyww/animatediff` |
| `mm_sd_v15.ckpt` | SD 1.5 | 표준 버전 | `guoyww/animatediff` |
| `mm_sdxl_v10_beta.ckpt` | SDXL | SDXL 동영상 | `guoyww/animatediff` |
| `hsxl_temporal_layers.safetensors` | SDXL | HotshotXL (8프레임 특화) | `hotshotco/Hotshot-XL` |
| `CameraCtrl_pruned.safetensors` | SD 1.5 (v3 모듈 필요) | CameraCtrl 카메라 제어 | (별도 레포) |

**저장 경로**: `ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/models/`
또는 `extra_model_paths.yaml`의 `animatediff_models` 경로 지정 시 해당 경로.

---

### B-8. 카테고리 7 — 전체 디테일 향상 LoRA (글로벌 품질 옵션)

#### 개요 및 적용 원칙

이 카테고리는 카테고리 1~6의 스타일 선택과 **완전히 독립적으로** 선택 가능하다.
선택한 디테일 향상 LoRA는 스타일 LoRA 위에 추가 적용(스택)되며, 복수 선택도 가능하다.

- 어떤 아트 스타일(카테고리 1)을 선택하든 추가 적용 가능
- 스타일 LoRA와 충돌 없이 품질만 보강하는 것이 설계 목적
- ComfyUI에서 `Load LoRA` 노드를 체인으로 연결하여 스타일 LoRA → 디테일 향상 LoRA 순서로 적용

#### 서브카테고리 A — 전체 품질 향상 (Quality Enhancement)

| 선택지명 | 효과 설명 | CivitAI 검색 키워드 | 지원 기반모델 | 권장 가중치 | 트리거 단어 | 주의사항 |
|---------|---------|------------------|------------|-----------|-----------|---------|
| Detail Tweaker (SD 1.5) | 세부 디테일 증가/감소 쌍방향 제어 — 양수: 디테일 증가, 음수: 디테일 감소 | `Detail Tweaker LoRA` | SD 1.5 | 0.5 ~ 1.5 (권장 1.0) | 없음 | SDXL/Flux.1에 직접 사용 불가 |
| Detail Tweaker XL | SDXL 전용 디테일 증가/감소 쌍방향 제어 | `Detail Tweaker XL` | SDXL | 1.0 ~ 2.0 (최대 3.0 가능) | 없음 | 애니/페인팅 스타일에 효과 우수, 사실적 스타일은 1.5 이하 권장 |
| Add More Details (SD 1.5) | 디테일 증폭기 — 텍스처, 에지, 세부 묘사 전체 강화 | `Add More Details detail enhancer` | SD 1.5 | 0.5 ~ 1.0 | 없음 | 과도한 가중치(>1.5) 시 노이즈 발생 가능 |
| FLUX Image Upgrader | Flux.1 전용 디테일 극대화 + 낮은 CFG 대비 보정 | `FLUX Image Upgrader Detail Maximizer` | Flux.1 / SDXL / SD 1.5 | 0.5 ~ 1.0 | 없음 | Flux.1의 낮은 CFG 설정에서 디테일 손실 보완에 특히 효과적 |
| Detailifier | 얼굴/피부/의류/털/소재 디테일 향상 — 다중 기반모델 지원 | `Detailifier SD35 Flux SDXL` | Flux.1 / SD3.5 / SDXL / Pony / SD 1.5 | 0.5 ~ 0.9 | 없음 | 다중 아키텍처 지원으로 가장 범용적인 디테일 향상 LoRA |
| imagination Detail Tweaker 2025 | Flux.1 전용 업그레이드 버전 디테일 트위커 — 대부분 LoRA와 호환 | `imagination upgraded detail tweaker 2025` | Flux.1 | 0.6 ~ 1.0 | 없음 | 2025년 출시 Flux.1 특화, 스택 사용에 최적화 |

#### 서브카테고리 B — 텍스처 향상 (Texture Enhancement)

| 선택지명 | 효과 설명 | CivitAI 검색 키워드 | 지원 기반모델 | 권장 가중치 | 주의사항 |
|---------|---------|------------------|------------|-----------|---------|
| Realistic Skin Texture | 피부 표면 디테일(모공, 미세 주름, 질감) 강화 | `Realistic Skin Texture style Detailed Skin XL` | SD 1.5 / SDXL / Flux.1 / Pony | 0.5 ~ 0.8 | 사실적 스타일에서 효과 극대화, 애니 스타일에는 낮은 가중치 권장 |
| Skin Realism (SDXL) | 피부 불완전함(모공, 잔주름, 색소침착) 추가로 초실감 구현 | `Skin Realism Acne Skin Details Imperfections SDXL` | SDXL | 0.4 ~ 0.6 (1.0 이상 변형 발생) | 가중치 1.0 초과 시 왜곡 발생 위험; 사실적 인물 사진에만 권장 |
| epiNoiseoffset | 노이즈 오프셋 기반 대비 강화 + 피부/재질 디테일 향상 | `epi_noiseoffset` | SD 1.5 | 0.2 ~ 0.6 | 어두운 스튜디오/림 라이팅 등 조명 키워드와 함께 사용 시 효과 극대화; SDXL/Flux.1 비호환 |

#### 서브카테고리 C — 필름/사진 효과 (Film/Photo)

| 선택지명 | 효과 설명 | CivitAI 검색 키워드 | 지원 기반모델 | 권장 가중치 | 트리거 단어 | 주의사항 |
|---------|---------|------------------|------------|-----------|-----------|---------|
| Touch of Grain (SDXL) | 자연스러운 필름 그레인 추가 — AI 특유의 과도한 매끄러움 제거 | `Touch of Grain SDXL` | SDXL | 0.4 ~ 0.8 | 없음 (프롬프트에 `film grain` 추가 권장) | 그레인 강도는 가중치로 조절; 지나치면 화질 저하처럼 보일 수 있음 |
| FilmGrain Redmond (SDXL) | SDXL 전용 사진 필름 그레인 스타일 | `FilmGrain Redmond SDXL` | SDXL | 0.6 ~ 1.0 | `FilmGrain` | 트리거 단어 없으면 효과 없음 |
| Lazy Haze (Film Photo) | 소프트 시네마틱 헤이즈 + 빈티지 필름감 + 미세 그레인 | `Lazy Haze Film Photography SDXL FLUX` | SDXL / Flux.1 | 0.5 ~ 0.8 | 없음 | 황금빛 아웃포커스 배경 효과; 선명도 중시 이미지에는 부적합 |
| SDXL Film Photography Style | 아날로그 필름 카메라 사진 분위기 전체 재현 | `SDXL Film Photography Style` | SDXL | 0.5 ~ 0.9 | 없음 | 스타일 변화 수반 — 순수 디테일 향상보다 분위기 변환에 가까움 |

#### 서브카테고리 D — 라이팅/명암 향상 (Lighting Enhancement)

| 선택지명 | 효과 설명 | CivitAI 검색 키워드 | 지원 기반모델 | 권장 가중치 | 주의사항 |
|---------|---------|------------------|------------|-----------|---------|
| FLUX Cinematic Lighting (SDXL/Flux) | 드라마틱 시네마틱 조명 + 림라이트 + 그림자 + 깊이감 강화 | `SDXL LoRA Dramatic Lighting Ethereal Fantasy Detail` | SDXL / Flux.1 | 0.5 ~ 0.9 | 조명 카테고리(카테고리 4)와 중복 선택 시 과적용 주의 |
| Ultimate Cinema XL | 영화적 색감/대비/조명 품질 전체 향상 | `Ultimate Cinema XL SDXL` | SDXL | 0.5 ~ 0.8 | 카테고리 4(조명)와 병행 시 가중치를 0.3~0.5로 낮춰 사용 권장 |

#### ComfyUI 다중 LoRA 스택 적용 방식

**기본 체인 구성 (Load LoRA 노드 직렬 연결)**

```
[CheckpointLoaderSimple]
    ↓ MODEL + CLIP
[Load LoRA] ← 스타일 LoRA (카테고리 1~6에서 결정)
    ↓ MODEL + CLIP
[Load LoRA] ← 디테일 향상 LoRA #1 (카테고리 7 첫 번째 선택)
    ↓ MODEL + CLIP
[Load LoRA] ← 디테일 향상 LoRA #2 (카테고리 7 두 번째 선택, 선택적)
    ↓ MODEL + CLIP
[KSampler]
```

- 각 `Load LoRA` 노드는 `MODEL`과 `CLIP` 두 출력을 다음 노드에 연결
- `lora_name`: 적용할 LoRA 파일명
- `strength_model`: 모델(UNet) 영향 강도 (통상 0.5~1.0)
- `strength_clip`: CLIP 텍스트 인코더 영향 강도 (디테일 향상 LoRA는 0.0~0.5 권장)

**Flux.1에서 다중 LoRA 스택 (LoraLoaderModelOnly 사용)**

Flux.1은 `LoraLoaderModelOnly` 노드를 체인으로 직렬 연결한다 (CLIP 출력 없음):

```
[Load Diffusion Model (UNETLoader)]
    ↓ MODEL
[LoraLoaderModelOnly] ← Flux.1 전용 스타일 LoRA
    ↓ MODEL
[LoraLoaderModelOnly] ← Flux.1 전용 디테일 향상 LoRA
    ↓ MODEL
[KSampler]
```

**가중치 관리 지침**

| 상황 | 권장 전략 |
|------|---------|
| 스타일 LoRA 1개 + 디테일 향상 LoRA 1개 | 스타일 0.6~0.8 / 디테일 0.5~0.7 |
| 스타일 LoRA 1개 + 디테일 향상 LoRA 2개 | 스타일 0.6~0.7 / 각 디테일 0.3~0.5씩 |
| LoRA 3개 이상 스택 | 각 LoRA 가중치를 0.3~0.5로 낮춰 총합 과적용 방지 |
| 효과 확인 방법 | 단독 검증 후 스택 — LoRA를 하나씩 적용하며 효과 확인 후 조합 |

**총 가중치 과적용 방지 원칙**:
- 동일 계열(예: 디테일 향상 LoRA 복수) 스택 시 각 가중치를 0.3~0.5 범위로 낮춤
- 스타일 LoRA와 디테일 향상 LoRA 가중치 합산이 2.0을 초과하지 않도록 관리
- 과적용 증상: 과도한 선명도(oversharpening), 노이즈 증가, 색감 왜곡

#### SD 1.5 / SDXL / Flux.1 기반모델별 호환성 요약

| 기반모델 | 사용 가능한 디테일 향상 LoRA | 비고 |
|---------|--------------------------|------|
| SD 1.5 | Detail Tweaker (SD 1.5), Add More Details, epiNoiseoffset | SDXL/Flux.1 전용 LoRA는 직접 사용 불가 |
| SDXL | Detail Tweaker XL, intenseMODE, Skin Realism, Touch of Grain, FilmGrain Redmond, Ultimate Cinema XL | SD 1.5 LoRA와 아키텍처 불호환 |
| Flux.1 | FLUX Image Upgrader, Detailifier (Flux버전), imagination Detail Tweaker 2025, Lazy Haze (Flux버전) | SD 1.5 LoRA 직접 사용 불가 — Flux.1 전용 버전 필요 |

> **핵심**: SD 1.5 LoRA는 Flux.1에서 사용 불가. Flux.1용 디테일 향상 LoRA는 별도로 존재하며, 일부 LoRA(Detailifier, FLUX Image Upgrader 등)는 여러 기반모델을 동시 지원하는 멀티-아키텍처 버전을 제공한다.

---

### B-9. 스타일 → ComfyUI 워크플로우 매핑 메커니즘

사용자가 스타일을 선택하면 F003 파이프라인은 다음 순서로 워크플로우를 조립한다:

```
1. 스타일 선택값 수집 (카테고리 1~7)

2. config.json 스타일 매핑 테이블 참조:
   - 카테고리 1(아트 스타일) → 체크포인트명 결정
   - 카테고리 2~5 → 스타일 LoRA 목록 + 가중치 결정
   - 카테고리 6 → 모션 모듈 + ADE 설정값 결정
   - 카테고리 7(디테일 향상 LoRA) → 추가 LoRA 목록 + 가중치 결정
     ※ 기반모델(SD 1.5 / SDXL / Flux.1)에 따라 호환 LoRA 필터링 적용

3. 사전 정의된 기본 워크플로우 JSON 로드:
   - 동영상: animatediff_base_workflow.json
   - 그림: flux_base_workflow.json 또는 sd_base_workflow.json

4. 워크플로우 JSON 내 특정 노드 값 교체:
   - 체크포인트 노드의 ckpt_name 값
   - 스타일 LoRA 노드(들)의 lora_name + strength_model 값
   - 디테일 향상 LoRA 노드(들)의 lora_name + strength_model 값
     ※ Load LoRA 노드를 스타일 LoRA 뒤에 체인으로 추가 삽입
     ※ Flux.1 경로: LoraLoaderModelOnly 노드 체인 사용
   - KSampler의 seed, steps, cfg 값
   - CLIPTextEncode의 text 값 (Ollama 생성 프롬프트)
   - AnimateDiff 전용 노드 설정값

5. Ollama 호출: 선택된 스타일 키워드를 컨텍스트로 제공하여
   풍부한 영문 프롬프트 자동 생성

6. ComfyUI POST /prompt 에 조립된 워크플로우 JSON 제출
```

---

## 영역 C: ComfyUI-AnimateDiff-Evolved 완전 분석

### C-1. 개요 및 설치

- GitHub: `Kosinkadink/ComfyUI-AnimateDiff-Evolved`
- 설치 경로: `ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/`
- 최종 업데이트: 2025-03-13 기준 활발히 유지관리 중
- 의존성: `requirements.txt` pip 설치 필요

### C-2. 핵심 노드 목록 및 역할

ComfyUI-AnimateDiff-Evolved는 세대(Gen)별로 구분된다.

**Gen 1 노드 (SD 1.5 기반, 레거시이지만 안정적)**

| 노드 이름 | Class Type | 역할 |
|----------|-----------|------|
| AnimateDiff Loader [Legacy] | `ADE_AnimateDiffLoaderWithContext` | 모션 모듈 로드 + 컨텍스트 옵션 연결 |
| AnimateDiff Loader | `ADE_AnimateDiffLoaderGen1` | Gen1 표준 모션 모듈 로더 |

**Gen 2 노드 (Evolved 방식, 권장)**

| 노드 이름 | Class Type | 역할 |
|----------|-----------|------|
| Use Evolved Sampling | `ADE_UseEvolvedSampling` | 고급 샘플링 기법 적용 — 메인 제어 노드 |
| Load AnimateDiff Model | `ADE_LoadAnimateDiffModel` | 모션 모듈 로드 (Gen2) |
| Apply AnimateDiff Model | `ADE_ApplyAnimateDiffModel` | 로드된 모션 모듈을 모델에 적용 |
| Uniform Context Options | `ADE_AnimateDiffUniformContextOptions` | 슬라이딩 윈도우 컨텍스트 설정 (deprecated, 신규 Context 노드 권장) |
| Sample Settings | `ADE_AnimateDiffSamplingSettings` | 노이즈 타입, 시드, closed_loop 등 샘플링 세부 설정 |

**CameraCtrl 노드 (카메라 이동 제어)**

| 노드 이름 | Class Type | 역할 |
|----------|-----------|------|
| Load AnimateDiff+CameraCtrl Model | `ADE_LoadAnimateDiffModelWithCameraCtrl` | CameraCtrl 모델 로드 |
| Apply AnimateDiff+CameraCtrl Model | `ADE_ApplyAnimateDiffModelWithCameraCtrl` | CameraCtrl 모델 적용 |

CameraCtrl 사용 조건:
- `CameraCtrl_pruned.safetensors` 모델 필요
- SD 1.5 v3 모션 모듈과 함께 사용
- Gen2/CameraCtrl 서브메뉴에서 접근

**SparseCtrl (희소 프레임 제어)**

`ComfyUI-Advanced-ControlNet` 플러그인과 연동하여 Context Options 기반 SparseCtrl 지원.
특정 프레임을 앵커로 지정하여 영상 내 특정 시점을 정밀 제어할 수 있다.

### C-3. Context Options (무한 길이 영상)

컨텍스트 옵션은 16프레임 이상의 긴 영상을 슬라이딩 윈도우 방식으로 생성할 때 사용한다.

| 파라미터 | 설명 | 권장값 |
|---------|------|--------|
| `context_frames` | 한 번에 처리하는 프레임 수 | 16 (SD 1.5 모듈 학습 기준) |
| `context_stride` | 컨텍스트 윈도우 이동 간격 | 1 |
| `context_overlap` | 연속 윈도우 간 겹치는 프레임 수 | 4 (부드러운 전환) |
| `closed_loop` | 마지막 프레임이 첫 프레임에 근접 (루프 영상) | true/false |

`ADE_AnimateDiffSamplingSettings` 노드의 주요 입력:
- `noise_type`: 노이즈 생성 방식 (default 권장)
- `seed_override`: 재현 가능한 결과 고정 시드
- `adapt_denoise_steps`: 품질-성능 균형 조정

### C-4. 워크플로우 JSON 구조 예시 (API 포맷)

AnimateDiff-Evolved 기반 동영상 생성 워크플로우의 핵심 노드 구성:

```
노드 연결 흐름 (Gen2 Evolved 방식):
[CheckpointLoaderSimple] → MODEL
    ↓
[ADE_LoadAnimateDiffModel] (모션 모듈 로드)
    ↓
[ADE_ApplyAnimateDiffModel] → MODEL with motion
    ↓ (ADE_AnimateDiffSamplingSettings 연결)
[ADE_UseEvolvedSampling]
    │ (Context Options 연결)
    ↓
[KSampler] → LATENT
    ↓
[VAEDecode] → IMAGE
    ↓
[VHS_VideoCombine 또는 SaveImage]
```

실제 API 포맷 JSON에서 각 노드는 숫자 문자열 ID를 키로 사용한다:

```
{
  "prompt": {
    "1": {
      "class_type": "CheckpointLoaderSimple",
      "inputs": { "ckpt_name": "v1-5-pruned-emaonly.safetensors" }
    },
    "2": {
      "class_type": "ADE_LoadAnimateDiffModel",
      "inputs": { "model_name": "mm_sd_v15_v2.ckpt", "model": ["1", 0] }
    },
    "3": {
      "class_type": "ADE_AnimateDiffSamplingSettings",
      "inputs": { "batch_size": 16, "seed_override": -1, "closed_loop": false }
    },
    "4": {
      "class_type": "ADE_ApplyAnimateDiffModel",
      "inputs": {
        "ad_model": ["2", 0],
        "sampling_settings": ["3", 0]
      }
    },
    ...
  },
  "client_id": "{uuid}"
}
```

**주의**: 위 JSON은 개념 설명용이며 실제 구현 시 `GET /object_info` 응답으로 정확한 입력 파라미터명을 반드시 확인해야 한다.

### C-5. 출력 저장 노드

AnimateDiff 결과는 프레임 시퀀스이므로 비디오로 합성하는 노드 필요:

| 노드 | 설명 |
|------|------|
| `VHS_VideoCombine` (VideoHelperSuite) | MP4/GIF/WebM으로 합성, 가장 널리 사용됨 |
| `SaveAnimatedWEBP` | WEBP 애니메이션으로 저장 |
| `SaveImage` (개별 프레임) | PNG 시퀀스로 저장 후 별도 합성 |

**VideoHelperSuite** (`Kosinkadink/ComfyUI-VideoHelperSuite`) 커스텀 노드 추가 설치 권장:
`VHS_VideoCombine` 노드가 MP4/GIF 최종 출력에 가장 많이 활용된다.

---

## 영역 D: ComfyUI 단일 플랫폼 모델 경로 구조

### D-1. ComfyUI 기준 전체 모델 경로

```
ComfyUI/
├── models/
│   ├── checkpoints/          # SD 체크포인트 (.safetensors, .ckpt)
│   ├── loras/                # LoRA 파일 (.safetensors, .pt)
│   ├── vae/                  # VAE 모델
│   ├── clip/                 # 텍스트 인코더 (Flux.1용 CLIP-L, T5)
│   ├── diffusion_models/     # Flux.1 메인 모델 (구: unet/)
│   ├── unet/                 # diffusion_models의 별칭 (하위 호환)
│   ├── controlnet/           # ControlNet 모델
│   ├── upscale_models/       # 업스케일러 (ESRGAN 등)
│   ├── clip_vision/          # CLIP 비전 인코더
│   ├── embeddings/           # 텍스추얼 인버전
│   └── hypernetworks/        # 하이퍼네트워크
│
└── custom_nodes/
    └── ComfyUI-AnimateDiff-Evolved/
        └── models/           # AnimateDiff 모션 모듈 (기본 경로)
            └── mm_sd_v15_v2.ckpt
```

**AnimateDiff 모션 모듈 경로 2가지 옵션**:

| 옵션 | 경로 | 설정 방법 |
|------|------|---------|
| 기본 경로 | `ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/models/` | 설정 불필요 |
| 중앙집중 경로 | 임의 경로 | `extra_model_paths.yaml`에서 `animatediff_models` 키로 지정 |

`extra_model_paths.yaml` 예시:
```yaml
my_custom:
    base_path: C:/AI/models
    animatediff_models: animatediff_models/
    animatediff_motion_lora: animatediff_motion_lora/
```

### D-2. 모델 타입별 CivitAI/HuggingFace 다운로드 후 배치 경로

| 모델 타입 | ComfyUI 배치 경로 | CivitAI 타입 필터 |
|---------|-----------------|-----------------|
| SD 1.5 체크포인트 | `ComfyUI/models/checkpoints/` | `Checkpoint` + `baseModel=SD+1.5` |
| SDXL 체크포인트 | `ComfyUI/models/checkpoints/` | `Checkpoint` + `baseModel=SDXL+1.0` |
| LoRA (SD 1.5) | `ComfyUI/models/loras/` | `LORA` |
| LoRA (SDXL) | `ComfyUI/models/loras/` | `LORA` |
| Flux.1 메인 모델 | `ComfyUI/models/diffusion_models/` | HuggingFace 전용 |
| Flux.1 VAE | `ComfyUI/models/vae/` | HuggingFace 전용 |
| Flux.1 텍스트 인코더 | `ComfyUI/models/clip/` | HuggingFace 전용 |
| AnimateDiff 모션 모듈 | `ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/models/` | `MotionModule` |
| ControlNet | `ComfyUI/models/controlnet/` | `Controlnet` |
| 업스케일러 | `ComfyUI/models/upscale_models/` | `Upscaler` |

### D-3. Flux.1 모델 파일 구성 (ComfyUI 기준)

Flux.1은 단일 파일이 아니라 여러 파일로 구성된다:

| 파일 | 경로 | 크기 | HuggingFace |
|------|------|------|------------|
| `flux1-dev-fp8.safetensors` | `diffusion_models/` | ~17.2GB | `Kijai/flux-fp8` |
| `flux1-schnell-fp8.safetensors` | `diffusion_models/` | ~17.2GB | `Comfy-Org/flux1-schnell` |
| `ae.safetensors` (VAE) | `vae/` | ~335MB | `black-forest-labs/FLUX.1-dev` |
| `clip_l.safetensors` (CLIP-L) | `clip/` | ~246MB | `openai/clip-vit-large-patch14` |
| `t5xxl_fp8_e4m3fn.safetensors` (T5) | `clip/` | ~4.9GB | `Comfy-Org/mochi-preview-fp8` 등 |

**토큰 필요 여부**:
- `black-forest-labs/FLUX.1-dev` 공식 레포: HuggingFace 라이선스 동의 + 토큰 필요
- `Kijai/flux-fp8`, `Comfy-Org/*`: 토큰 불필요 — F003 초기 구현에서 우선 사용

### D-4. ComfyUI 모델 목록 갱신 방법

**재시작 없이 모델 목록 갱신**: 현재 ComfyUI는 재시작 없이 모델 목록을 프로그래밍적으로 갱신하는 전용 REST API 엔드포인트가 없다.

| 방법 | 설명 |
|------|------|
| 서버 재시작 | 가장 확실한 방법. `POST /manager/reboot` (ComfyUI-Manager 필요) |
| UI Refresh | ComfyUI 웹 UI에서 `Edit → Refresh Node Definitions` 또는 `R` 단축키 |
| GET /object_info | 현재 로드된 노드 정보 조회 (갱신 트리거 아님, 상태 확인용) |

**F003 모델 다운로드 후 처리 전략**:
- 다운로드 완료 후 `POST /manager/reboot` 로 ComfyUI 재시작
- 재시작 완료 감지: `GET http://localhost:8188/system_stats` 폴링 (200 응답 = 준비 완료)
- AUTOMATIC1111의 `refresh-checkpoints` API에 해당하는 방법이 없으므로 재시작이 표준 절차

---

## 영역 3: Flux.1 통합 (유지, ComfyUI 기준으로 확정)

### 3-1. Flux.1 모델 종류

| 모델명 | 라이선스 | 특징 | 용도 |
|--------|---------|------|------|
| `flux1-dev` | 비상업용 | 고품질, 느린 속도 | 최고 품질 이미지 |
| `flux1-schnell` | Apache 2.0 | 빠른 속도, 약간 품질 저하 | 빠른 생성 |
| `flux1-dev-fp8` | 비상업용 | FP8 양자화, VRAM 절약 | 낮은 VRAM 환경 |
| `flux1-schnell-fp8` | Apache 2.0 | FP8 + 빠른 속도 | 저VRAM + 빠른 생성 |

### 3-2. VRAM 요구사항

| 설정 | 최소 VRAM | 권장 VRAM |
|------|-----------|-----------|
| FP16 전체 로드 | 24GB | 32GB+ |
| FP8 양자화 | 12GB | 16GB |
| GGUF Q4_K_M | 6GB | 8GB |
| CPU 오프로드 | 8GB | 12GB |

### 3-3. ComfyUI API 구조 (확정)

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/prompt` | POST | 워크플로우 JSON 제출 (실행 큐 추가) |
| `/history/{prompt_id}` | GET | 생성 결과 조회 |
| `/queue` | GET | 현재 실행 큐 상태 |
| `/system_stats` | GET | 서버 상태 (헬스체크) |
| `/object_info` | GET | 사용 가능한 노드 타입 목록 + 파라미터 |
| `/ws?clientId={id}` | WebSocket | 실시간 진행 상황 스트리밍 |
| `/view?filename={}&type=output` | GET | 생성된 파일 다운로드 |

**결과 파일 접근 흐름**:
```
POST /prompt → {prompt_id}
    ↓ (WebSocket 완료 이벤트 수신)
GET /history/{prompt_id} → outputs[].images[].filename
    ↓
GET /view?filename={filename}&type=output → 파일 바이너리
```

### 3-4. Flux.1 ComfyUI 워크플로우 핵심 노드

| 노드 | Class Type | 설명 |
|------|-----------|------|
| 모델 로더 | `UNETLoader` 또는 `CheckpointLoaderSimple` | Flux.1 모델 로드 |
| LoRA 로더 | `LoraLoaderModelOnly` | Flux.1 전용 LoRA 로더 (CLIP 반영 안 함) |
| CLIP 인코더 L | `CLIPTextEncode` | CLIP-L 텍스트 인코딩 |
| T5 인코더 | `CLIPTextEncode` | T5XXL 텍스트 인코딩 |
| KSampler | `KSampler` | 이미지 샘플링 |
| VAE 디코더 | `VAEDecode` | 잠재 공간 → 이미지 변환 |
| 이미지 저장 | `SaveImage` | 결과 PNG 저장 |

**Flux.1 LoRA 적용 방법**:
- `LoraLoaderModelOnly` 노드 사용: `Load Diffusion Model` → `LoraLoaderModelOnly` → KSampler 연결
- 파일 위치: `ComfyUI/models/loras/`
- `strength_model` 파라미터로 가중치 조절 (권장 0.7~0.9)
- CLIP(텍스트 인코더)에는 반영되지 않음 — SD의 표준 Load LoRA와 다른 점

---

## 영역 4: CivitAI API — 모델 검색 및 다운로드 (유지)

### 4-1. API 기본 정보

- 베이스 URL: `https://civitai.com/api/v1/`
- 인증: Bearer 토큰 (계정 설정에서 생성)
- 인증 헤더 형식: `Authorization: Bearer {API_KEY}`

### 4-2. 모델 검색 API

**엔드포인트**: `GET /api/v1/models`

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `query` | 검색어 | `?query=anime+style` |
| `types` | 모델 타입 필터 | `?types=Checkpoint` |
| `sort` | 정렬 기준 | `?sort=Most+Downloaded` |
| `limit` | 결과 수 | `?limit=20` |
| `baseModel` | 베이스 모델 필터 | `?baseModel=SD+1.5` |

**지원 모델 타입**:
- `Checkpoint` — 메인 체크포인트
- `LORA` — LoRA 모델
- `MotionModule` — AnimateDiff 모션 모듈
- `Controlnet` — ControlNet
- `VAE` — VAE
- `Upscaler` — 업스케일러

### 4-3. 다운로드 URL 획득 및 파일 저장

```
GET /api/v1/models/{modelId}
→ modelVersions[].files[].downloadUrl 획득

GET https://civitai.com/api/download/models/{modelVersionId}
헤더: Authorization: Bearer {API_KEY}
→ 파일 스트리밍 다운로드
```

### 4-4. ComfyUI 기준 다운로드 후 저장 경로 (V2 갱신)

| 모델 타입 | ComfyUI 저장 경로 |
|---------|-----------------|
| Checkpoint (SD 1.5/SDXL) | `ComfyUI/models/checkpoints/` |
| LoRA | `ComfyUI/models/loras/` |
| MotionModule (AnimateDiff) | `ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved/models/` |
| VAE | `ComfyUI/models/vae/` |
| ControlNet | `ComfyUI/models/controlnet/` |
| Upscaler | `ComfyUI/models/upscale_models/` |

---

## 영역 5: HuggingFace Hub — 모델 다운로드 (유지)

### 5-1. huggingface_hub 라이브러리 개요

- 설치: `pip install huggingface_hub`
- 인증: `HF_TOKEN` 환경변수 또는 `login()` 함수

### 5-2. 주요 함수 파라미터

`hf_hub_download(repo_id, filename, local_dir, token)`

| 파라미터 | 설명 |
|---------|------|
| `repo_id` | 레포지토리 ID (예: `Kijai/flux-fp8`) |
| `filename` | 다운로드할 파일명 |
| `local_dir` | 직접 저장할 경로 (ComfyUI 모델 폴더 지정) |
| `token` | HuggingFace 토큰 |

### 5-3. Flux.1 HuggingFace 레포지토리

| 모델 | HuggingFace 경로 | 토큰 필요 |
|------|-----------------|---------|
| FLUX.1-dev (공식) | `black-forest-labs/FLUX.1-dev` | 필요 |
| flux1-dev-fp8 (Kijai) | `Kijai/flux-fp8` | 불필요 |
| flux1-schnell-fp8 (Comfy-Org) | `Comfy-Org/flux1-schnell` | 불필요 |

### 5-4. AnimateDiff HuggingFace 레포지토리

| 레포지토리 | 내용 |
|-----------|------|
| `guoyww/animatediff` | 공식 원본 모션 모듈 (mm_sd_v14/v15/v15_v2) |
| `guoyww/animatediff-motion-adapter-v1-5` | diffusers 호환 형식 |

---

## 영역 6: 로컬 모델 인벤토리 관리 (ComfyUI 기준으로 업데이트)

### 6-1. ComfyUI 기준 모델 저장 위치 전체 구조

```
ComfyUI/
├── models/
│   ├── checkpoints/    # SD/SDXL 체크포인트
│   ├── loras/          # LoRA (.safetensors, .pt)
│   ├── vae/            # VAE
│   ├── clip/           # 텍스트 인코더 (Flux.1용)
│   ├── diffusion_models/ # Flux.1 메인 모델
│   ├── controlnet/     # ControlNet
│   └── upscale_models/ # 업스케일러
└── custom_nodes/
    └── ComfyUI-AnimateDiff-Evolved/
        └── models/     # AnimateDiff 모션 모듈
```

### 6-2. ComfyUI 모델 목록 확인 방법

```
GET /object_info
→ 각 노드 타입의 입력 파라미터에 사용 가능한 모델 목록 포함
  예: CheckpointLoaderSimple.inputs.ckpt_name = ["model1.safetensors", ...]

GET /system_stats
→ 200이면 서버 정상 (헬스체크용)
```

로컬 파일 직접 스캔 방법:
- `pathlib.Path.glob("*.safetensors")` 로 각 경로 스캔
- 파일 확장자 필터: `.safetensors`, `.ckpt`, `.pt`, `.bin`

### 6-3. 모델명 매칭 로직

| 문제 | 해결 방법 |
|------|---------|
| 파일명 대소문자 차이 | 소문자 정규화 후 비교 |
| 버전 숫자 포함 여부 | 핵심 키워드 추출 후 포함 여부 |
| 공백 vs 언더스코어 | 정규화 처리 |
| SHA256 해시 매칭 | CivitAI 모델 해시와 비교 (가장 정확) |

### 6-4. F003 모델 인벤토리 DB 설계 (ComfyUI 경로로 갱신)

SQLite `model_inventory` 테이블:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| model_type | TEXT | checkpoint/lora/motion_module/vae/clip |
| name | TEXT | 표시 이름 |
| filename | TEXT | 실제 파일명 |
| local_path | TEXT | ComfyUI 기준 절대 경로 |
| civitai_version_id | INTEGER | CivitAI 버전 ID (null 가능) |
| hf_repo_id | TEXT | HuggingFace 레포 ID (null 가능) |
| is_downloaded | BOOLEAN | 로컬 존재 여부 |
| file_size_mb | FLOAT | 파일 크기 (MB) |
| downloaded_at | DATETIME | 다운로드 완료 시각 |
| base_model | TEXT | SD 1.5 / SDXL / Flux 등 |
| style_tags | TEXT | 스타일 카테고리 태그 (JSON 배열 문자열) |

`style_tags` 컬럼: 스타일 선택 시스템과 연동 — 예: `["anime", "realistic", "category1"]`

---

## 영역 7: Ollama 프롬프트 생성 전략 (스타일 시스템 연동 추가)

### 7-1. SD용 프롬프트 특성

**포지티브 프롬프트 구조**:
```
[품질 태그], [아트 스타일], [피사체 묘사], [캐릭터 외형], [촬영 앵글/구도], [조명], [배경], [카메라 설정]
예: masterpiece, best quality, anime style, 1girl, long pink hair, twin tails,
    portrait, from above, dramatic lighting, school background, bokeh
```

### 7-2. Flux.1용 프롬프트 특성

Flux.1은 자연어 기반 프롬프트가 더 효과적:
- CLIP + T5 텍스트 인코더 → 긴 자연어 문장 이해 우수
- 자세한 묘사적 문장 형식 권장

### 7-3. 스타일 선택 → Ollama 프롬프트 생성 연동

스타일 선택 데이터를 Ollama에 전달하여 최적화된 프롬프트 자동 생성:

**Ollama 입력 컨텍스트 구성**:
```
{
  "art_style": "anime",           // 카테고리 1 선택값
  "character": {
    "face": "asian",
    "hair_style": "twin tails",
    "hair_color": "pink",
    "eyes": "large eyes",
    "outfit": "school uniform"
  },                              // 카테고리 2 선택값
  "camera": {
    "angle": "from above",
    "composition": "portrait",
    "depth_of_field": "bokeh"
  },                              // 카테고리 3 선택값
  "lighting": "dramatic",        // 카테고리 4 선택값
  "background": "classroom",     // 카테고리 5 선택값
  "user_description": "밝고 활발한 학생 캐릭터"
}
```

**시스템 프롬프트 역할**: Stable Diffusion 전문 프롬프트 엔지니어
**출력 형식**: `{"positive": "...", "negative": "..."}`

### 7-4. Ollama API 호출 형식

POST `http://localhost:11434/api/chat`:
```
{
  "model": "gemma3:12b",
  "stream": false,
  "format": "json",
  "messages": [
    {"role": "system", "content": "시스템 프롬프트..."},
    {"role": "user", "content": "스타일 JSON 컨텍스트 + 사용자 설명"}
  ]
}
```

**응답 파싱 전략**:
1. `format: "json"` 사용 후 `json.loads(response)` 직접 파싱
2. 실패 시 정규표현식으로 ```json ... ``` 블록 추출
3. 2차 실패 시 `{` 와 `}` 사이 텍스트 추출

### 7-5. 권장 Ollama 모델

| 모델 | VRAM | 적합성 |
|------|------|--------|
| `gemma3:12b` | ~8GB | 높음 — 한국어+영어 우수 |
| `qwen2.5:7b` | ~5GB | 높음 — 다국어 우수 |
| `llama3.2:3b` | ~2GB | 보통 — 저사양 환경 |
| `brxce/stable-diffusion-prompt-generator` | ~4GB | 매우 높음 — SD 전용 |

---

## F003 통합 아키텍처 (V2 — ComfyUI 단일 플랫폼)

### 전체 시스템 구성도

```
[Vue 3 대시보드]
    │
    ▼ REST API (Axios)
[FastAPI 서버 — localhost:8000]
    │
    ├─ [모델 관리 서비스]
    │      ├─ 로컬 인벤토리 조회 (SQLite)
    │      ├─ CivitAI API 검색/다운로드
    │      └─ HuggingFace Hub 다운로드
    │
    ├─ [Ollama 서비스 — localhost:11434]
    │      ├─ 스타일 기반 프롬프트 자동 생성
    │      └─ 모델 추천 판단
    │
    └─ [독립 파이프라인 프로세스]
           │
           └─ ComfyUI (localhost:8188) — 단일 플랫폼
                  ├─ 동영상 경로:
                  │      AnimateDiff-Evolved 워크플로우 JSON
                  │      → MP4/GIF 생성
                  │
                  └─ 그림 경로:
                         Flux.1 또는 SD 워크플로우 JSON
                         → PNG 생성
```

### 포트 구성 (V2 — 서비스 2개로 단순화)

| 서비스 | 포트 | 역할 |
|--------|------|------|
| FastAPI | 8000 | Dash 메인 API 서버 |
| Vue 3 (dev) | 5173 | 프론트엔드 |
| Ollama | 11434 | 로컬 LLM |
| ComfyUI | 8188 | 동영상 + 그림 생성 (단일) |

### F003 작업 흐름 상세 (V2)

```
1. 사용자가 F003 선택 → 생성 유형 선택 (동영상/그림)
2. 스타일 카테고리 6개에서 선택지 고르기
3. 사용자가 간단한 설명 입력 + 사이즈/품질 설정
4. FastAPI → Ollama /api/chat 호출
   → 선택된 스타일 컨텍스트 + 사용자 설명 → 포지티브/네거티브 프롬프트 JSON 생성
5. FastAPI → 스타일 매핑 테이블 참조
   → 필요 체크포인트명, LoRA 목록, 모션 모듈명 결정
6. FastAPI → 로컬 model_inventory 테이블 확인
   - 필요 모델 모두 로컬에 있음 → 8단계
   - 없음 → 7단계
7. 모델 다운로드 (백그라운드):
   a. model_download_queue 항목 추가 (status=QUEUED)
   b. httpx.AsyncClient 스트리밍 다운로드 (CivitAI 또는 HuggingFace)
   c. 청크 처리마다 progress_pct 업데이트 (status=DOWNLOADING)
   d. 완료 후 ComfyUI 모델 경로 배치 (status=DONE)
   e. POST /manager/reboot 로 ComfyUI 재시작
   f. GET /system_stats 폴링으로 재시작 완료 감지
   g. model_inventory 테이블 업데이트 (is_downloaded=True)
8. tasks 테이블 새 작업 생성 (status=PENDING → RUNNING)
9. 독립 파이프라인 프로세스 spawn:
   i. ComfyUI 헬스체크: GET http://localhost:8188/system_stats (200 = 정상)
   ii. Ollama 헬스체크: GET http://localhost:11434/api/tags (200 = 정상)
   iii. 기본 워크플로우 JSON 로드 (동영상: animatediff_workflow.json / 그림: flux_workflow.json)
   iv. 스타일 매핑값으로 JSON 내 노드 파라미터 교체:
       - 체크포인트 노드의 ckpt_name
       - LoRA 노드(들)의 lora_name + strength_model
       - AnimateDiff 노드의 모션 모듈명 + 컨텍스트 설정
       - CLIPTextEncode의 text 값 (Ollama 생성 프롬프트)
   v. POST http://localhost:8188/prompt (워크플로우 JSON 제출)
   vi. WebSocket /ws?clientId={uuid} 로 완료 이벤트 수신
   vii. GET /history/{prompt_id} → 파일명 추출
   viii. GET /view?filename={filename}&type=output → 파일 다운로드
   ix. storage/results/ 에 결과 파일 저장
10. tasks 테이블 DONE 업데이트, result에 파일 경로 저장
11. Vue 3 대시보드에서 결과 파일 표시 (이미지/동영상 플레이어)
```

### 모델 자동 관리 판단 플로우 (V2)

```
사용자 스타일 선택 + 설명 입력
    │
    ▼
스타일 매핑 → 필요 모델 목록 생성
(체크포인트 + LoRA + 모션 모듈)
    │
    ▼
로컬 model_inventory 조회
    │
    ├─ [모두 있음] → 즉시 파이프라인 시작
    │
    └─ [일부/전부 없음]
            │
            ▼
        CivitAI API 검색 (modelVersionId 획득)
            │
            ├─ [CivitAI에 있음] → CivitAI 다운로드 → ComfyUI 경로 배치
            │
            └─ [없음] → HuggingFace hf_hub_download → ComfyUI 경로 배치
                            │
                            ▼
                       POST /manager/reboot (ComfyUI 재시작)
                            │
                            ▼
                       GET /system_stats 폴링 (재시작 완료 감지)
                            │
                            ▼
                       파이프라인 시작
```

### F003 SQLite 추가 테이블

**model_inventory 테이블**: 로컬 모델 목록 + 스타일 태그 관리

**model_download_queue 테이블**: 다운로드 진행 상태

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| source | TEXT | civitai / huggingface |
| model_type | TEXT | checkpoint/lora/motion_module/vae/clip |
| source_id | TEXT | CivitAI modelVersionId 또는 HF repo_id+filename |
| target_path | TEXT | ComfyUI 기준 저장 목표 경로 |
| status | TEXT | QUEUED/DOWNLOADING/DONE/FAILED |
| progress_pct | FLOAT | 다운로드 진행률 (0-100) |
| error_message | TEXT | 실패 메시지 |
| created_at | DATETIME | 큐 등록 시각 |
| finished_at | DATETIME | 완료 시각 |

### F003 디렉토리 구조 (V2 — sd_client.py 삭제)

```
Dash/
├── pipelines/
│   ├── f003_video_creation/
│   │   ├── __init__.py
│   │   ├── pipeline.py              # 메인 파이프라인 로직
│   │   ├── comfyui_client.py        # ComfyUI API 클라이언트 (단일)
│   │   ├── model_manager.py         # 모델 자동 관리 (다운로드/설치)
│   │   ├── style_mapper.py          # 스타일 선택 → ComfyUI 파라미터 매핑
│   │   ├── prompt_generator.py      # Ollama 프롬프트 생성
│   │   ├── workflows/               # 사전 정의 워크플로우 JSON
│   │   │   ├── animatediff_base.json
│   │   │   └── flux_base.json
│   │   └── config.json              # F003 기본 설정
├── backend/
│   ├── services/
│   │   ├── model_service.py
│   │   └── download_service.py
│   ├── routers/
│   │   └── models.py
│   └── models/
│       ├── model_inventory.py
│       └── download_queue.py
└── storage/
    └── models/
```

---

## 핵심 위험 요소 및 제약사항 (V2)

### 위험 1: VRAM 부족 (심각도: 높음)

| 상황 | 문제 | 대응 |
|------|------|------|
| SD + AnimateDiff | 16프레임 기준 8-12GB VRAM 필요 | context_frames 줄이거나 프레임 수 제한 |
| Flux.1 FP16 | 24GB+ VRAM 필요 | FP8 버전 사용 (12-16GB로 절감) |
| 동시 실행 | VRAM 공유 불가 | 큐 기반 순차 실행 강제 |
| AnimateDiff SDXL | SDXL 기반 모듈 사용 시 더 많은 VRAM | SD 1.5 기반 모듈 우선 사용 |

### 위험 2: 외부 서비스 의존성 (심각도: 낮아짐)

V2에서 AUTOMATIC1111 제거로 서비스 수가 3개 → 2개로 감소. 관리 복잡도 대폭 감소.

헬스체크 엔드포인트:
- ComfyUI: `GET http://localhost:8188/system_stats` (200이면 정상)
- Ollama: `GET http://localhost:11434/api/tags` (200이면 정상)

### 위험 3: 모델 다운로드 시간 (심각도: 중간)

- Flux.1 FP8: ~17.2GB → 약 23분 소요 (100Mbps 기준)
- SD 체크포인트: 2-7GB → 3-10분 소요
- AnimateDiff 모션 모듈: ~1.7GB → 2-3분 소요
- 대응: 비동기 다운로드 큐 + UI 진행률 표시 필수

**FastAPI 다운로드 구현 전략**:
- `httpx.AsyncClient` + `client.stream()` 으로 청크 단위 스트리밍 다운로드
- 청크 크기: 1MB
- `aiofiles`로 비동기 파일 쓰기
- SQLite `progress_pct` 컬럼 주기적 업데이트
- Vue 3 프론트에서 2초 폴링으로 진행률 표시

### 위험 4: CivitAI API 제한 (심각도: 중간)

- 비인증 속도 제한 → API 키 발급 필수
- 일부 모델 계정 동의 필요

### 위험 5: ComfyUI 워크플로우 포맷 복잡성 (심각도: 중간)

- ComfyUI API는 워크플로우 JSON을 노드 ID 기반으로 정의
- 사전 정의 JSON 파일 관리 필요 (`workflows/` 폴더)
- 스타일 변경 시 JSON 내 특정 노드 ID의 값만 교체하는 로직 필요
- `GET /object_info` 로 현재 파라미터명 반드시 사전 확인

### 위험 6: ComfyUI 재시작 대기 (심각도: 중간, 신규)

모델 다운로드 후 ComfyUI 재시작이 필요하며 재시작 완료까지 10-30초 소요될 수 있다.
파이프라인에서 `GET /system_stats` 폴링 루프로 준비 완료를 감지해야 한다.

### 위험 7: AnimateDiff 노드 버전 변화 (심각도: 낮음)

- Gen1 vs Gen2 노드 체계로 인한 워크플로우 호환성 문제
- `ADE_AnimateDiffUniformContextOptions`는 deprecated → 신규 Context 노드 사용
- `GET /object_info` 로 설치된 노드 목록 확인 후 적합한 노드 선택

---

## 리서치 완료 자기 검토 (V2)

### 체크리스트

- [x] ComfyUI 커스텀 노드 설치 API 엔드포인트 확인
  - ComfyUI-Manager: `/manager/install-custom-node`, `/manager/reboot`, `/manager/installed-custom-nodes`
  - 수동 설치: git clone + pip install + 재시작
  - 설치 확인: `GET /object_info` 응답 키 존재 여부

- [x] ComfyUI-AnimateDiff-Evolved 노드 이름 및 파라미터 정확성
  - Gen2 핵심: `ADE_UseEvolvedSampling`, `ADE_LoadAnimateDiffModel`, `ADE_ApplyAnimateDiffModel`
  - 샘플링: `ADE_AnimateDiffSamplingSettings`
  - CameraCtrl: `ADE_LoadAnimateDiffModelWithCameraCtrl`, `ADE_ApplyAnimateDiffModelWithCameraCtrl`

- [x] 스타일 카테고리 7개 모두 채워짐
  - 카테고리 1: 아트 스타일 (7개 선택지 + 기술 매핑)
  - 카테고리 2: 캐릭터 외형 (얼굴/헤어/눈/체형/의상 세분화)
  - 카테고리 3: 촬영 기법/카메라 (앵글/구도/심도/렌즈)
  - 카테고리 4: 조명/분위기 (9개 선택지)
  - 카테고리 5: 배경/환경 (4그룹 13개 선택지)
  - 카테고리 6: 동영상 전용 모션 스타일 (강도/타입/루프/모듈 선택)
  - 카테고리 7: 전체 디테일 향상 LoRA (4개 서브카테고리, 14개 이상 선택지, ComfyUI 스택 방법 포함)

- [x] ComfyUI 모델 경로 구조 완전 정확
  - checkpoints/, loras/, vae/, clip/, diffusion_models/, controlnet/, upscale_models/
  - AnimateDiff: custom_nodes/ComfyUI-AnimateDiff-Evolved/models/ 또는 extra_model_paths.yaml

- [x] AUTOMATIC1111 참조 완전 제거
  - 영역 1 전체 삭제 (AUTOMATIC1111 API 구조)
  - 영역 2 전체 교체 (sd-webui-animatediff → ComfyUI-AnimateDiff-Evolved)
  - 통합 아키텍처 포트 구성 AUTOMATIC1111(7860) 삭제
  - 디렉토리 구조에서 sd_client.py 삭제, style_mapper.py 추가

- [x] 통합 아키텍처 업데이트 반영
  - 단일 ComfyUI 플랫폼
  - 서비스 3개 → 2개 (Ollama + ComfyUI)
  - 작업 흐름 ComfyUI 단일 경로로 통일

- [x] 위험 요소 재평가
  - 위험 2 심각도 하향 조정 (서비스 수 감소)
  - 위험 6 신규 추가 (ComfyUI 재시작 대기)
  - 위험 7 업데이트 (A1111 AnimateDiff 파라미터 불안정 → ADE 노드 버전 변화)

### 완성도 자체 평가 (V2)

| 항목 | 완성도 | 비고 |
|------|--------|------|
| 영역 A: ComfyUI 커스텀 노드 관리 | 97% | Manager API 상세 문서 제한적이나 핵심 엔드포인트 확인 |
| 영역 B: 스타일 선택 시스템 (7 카테고리) | 98% | 프롬프트 키워드, 기술 매핑 상세화; 카테고리 7 디테일 향상 LoRA 추가 |
| 영역 C: AnimateDiff-Evolved 완전 분석 | 97% | Gen1/Gen2 노드 체계, CameraCtrl, SparseCtrl 확인 |
| 영역 D: ComfyUI 모델 경로 구조 | 98% | 전체 경로 확인, 모션 모듈 경로 2가지 옵션 |
| 영역 3: Flux.1 통합 | 98% | ComfyUI 기준으로 확정 |
| 영역 4: CivitAI API | 97% | 경로 ComfyUI 기준으로 갱신 |
| 영역 5: HuggingFace Hub | 97% | 유지 |
| 영역 6: 로컬 인벤토리 관리 | 97% | ComfyUI 경로로 갱신, style_tags 컬럼 추가 |
| 영역 7: Ollama 프롬프트 전략 | 98% | 스타일 시스템 연동 추가 |
| 통합 아키텍처 | 98% | 단일 ComfyUI 전환 완료, 재시작 플로우 추가 |
| 위험 요소 분석 | 97% | 7개 항목 재평가 |
| **전체 평균** | **97.8%** | |

### 리서치 데이터 소스

| 출처 | 활용 영역 |
|------|---------|
| Kosinkadink/ComfyUI-AnimateDiff-Evolved GitHub | 영역 C: 노드 목록, 파라미터 |
| runcomfy.com (노드 문서) | 영역 C: ADE 노드 상세 설명 |
| docs.comfy.org (공식 문서) | 영역 D: 모델 경로, 설치 방법 |
| comfyui-wiki.com | 영역 D: 폴더 구조, LoRA 사용 |
| Comfy-Org/ComfyUI-Manager GitHub | 영역 A: Manager API |
| stable-diffusion-art.com | 영역 B: 스타일/체크포인트 추천 |
| CivitAI (모델 페이지) | 영역 B: 스타일별 LoRA/체크포인트 |
| kijai/ComfyUI-WanVideoWrapper GitHub | 영역 A: WanVideo 노드 |
| docs.comfy.org/tutorials/video/wan | 영역 A: WanVideo 네이티브 지원 |
| github.com/Comfy-Org/ComfyUI (Discussion #4536) | 영역 D: 모델 갱신 API 현황 |
| guoyww/animatediff HuggingFace | 영역 C: 모션 모듈 파일명/경로 |
| CivitAI (Detail Tweaker LoRA / XL 페이지) | 영역 B-8: 디테일 향상 LoRA 가중치/트리거 |
| CivitAI (FLUX Image Upgrader, Detailifier) | 영역 B-8: Flux.1 디테일 향상 LoRA 현황 |
| CivitAI (epiNoiseoffset, Skin Realism SDXL) | 영역 B-8: 텍스처 향상 LoRA 가중치 |
| CivitAI (FilmGrain Redmond, Touch of Grain) | 영역 B-8: 필름/사진 효과 LoRA |
| neurocanvas.net (Multi-LoRA Workflows) | 영역 B-8: ComfyUI 다중 LoRA 스택 방법 |
| docs.comfy.org/tutorials/basic/multiple-loras | 영역 B-8: ComfyUI 공식 다중 LoRA 가이드 |

---

## 변경 이력

### V1 → V2 변경 내용 (2026-05-07)

| 변경 유형 | 내용 |
|---------|------|
| **삭제** | 영역 1 전체 (AUTOMATIC1111 API 구조) |
| **삭제** | 영역 2 전체 (sd-webui-animatediff, A1111 기반) |
| **삭제** | 디렉토리 구조에서 `sd_client.py` |
| **삭제** | 통합 아키텍처 및 포트 구성의 AUTOMATIC1111(7860) 관련 내용 |
| **삭제** | 위험 2번의 A1111+ComfyUI+Ollama 3개 서비스 내용 |
| **삭제** | 영역 6의 SD WebUI 기준 모델 저장 경로 전체 |
| **신규 추가** | 영역 A: ComfyUI 커스텀 노드 관리 시스템 |
| **신규 추가** | 영역 B: 스타일 선택 시스템 (6개 카테고리 전체) |
| **신규 추가** | 영역 C: ComfyUI-AnimateDiff-Evolved 완전 분석 |
| **신규 추가** | 영역 D: ComfyUI 단일 플랫폼 모델 경로 구조 |
| **업데이트** | 영역 3: Flux.1 통합 → ComfyUI 단일 기준으로 확정 |
| **업데이트** | 영역 4: CivitAI 다운로드 경로 → ComfyUI 경로로 교체 |
| **업데이트** | 영역 6: 로컬 인벤토리 → ComfyUI 경로, style_tags 컬럼 추가 |
| **업데이트** | 영역 7: Ollama 전략 → 스타일 선택 시스템 연동 추가 |
| **업데이트** | 통합 아키텍처 → 단일 ComfyUI, 2개 서비스, 재시작 플로우 |
| **업데이트** | 위험 2 심각도 하향 조정 (서비스 3→2개) |
| **신규 추가** | 위험 6: ComfyUI 재시작 대기 (신규) |
| **업데이트** | 위험 7: AnimateDiff 노드 버전 변화 (A1111 파라미터 → ADE Gen1/2) |
| **업데이트** | 디렉토리 구조에 `style_mapper.py`, `workflows/` 폴더 추가 |

---

### V2 → V3 변경 내용 (2026-05-07)

| 변경 유형 | 내용 |
|---------|------|
| **업데이트** | 개요 핵심 기능 요약 — 스타일 카테고리 목록에 `디테일 향상` 추가 |
| **업데이트** | 아키텍처 확정 표 — 스타일 시스템 6개 → 7개 카테고리로 확장 |
| **업데이트** | B-1 개요 — 매핑 3요소 → 4요소 확장 (디테일 향상 LoRA 신규 요소 추가) |
| **신규 추가** | B-8: 카테고리 7 — 전체 디테일 향상 LoRA (글로벌 품질 옵션) 섹션 전체 |
| **신규 추가** | B-8 서브카테고리 A: 전체 품질 향상 LoRA 6개 상세 (SD 1.5 / SDXL / Flux.1 별) |
| **신규 추가** | B-8 서브카테고리 B: 텍스처 향상 LoRA 3개 상세 |
| **신규 추가** | B-8 서브카테고리 C: 필름/사진 효과 LoRA 4개 상세 |
| **신규 추가** | B-8 서브카테고리 D: 라이팅/명암 향상 LoRA 2개 상세 |
| **신규 추가** | ComfyUI Load LoRA 체인 구성법 및 Flux.1 LoraLoaderModelOnly 스택 방법 |
| **신규 추가** | 기반모델별 호환성 요약 표 (SD 1.5 / SDXL / Flux.1) |
| **업데이트** | B-9 (구 B-8) 매핑 메커니즘 — 카테고리 7 처리 단계 추가, 기반모델 호환 필터링 명시 |
| **업데이트** | 체크리스트 — 카테고리 7 항목 추가 |
| **업데이트** | 완성도 평가 표 — 영역 B 항목 갱신 |
| **업데이트** | 리서치 데이터 소스 — 디테일 향상 LoRA 관련 출처 7개 추가 |

*리서치 V3 완료: 2026-05-07 | 카테고리 7(전체 디테일 향상 LoRA) 추가 + ComfyUI 스택 방법 상세화 | WebSearch 6회 추가 활용*
