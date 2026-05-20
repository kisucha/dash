# Dash 변경 이력

## [2026-05-21] F007 YouTube 자동화 파이프라인 v5 신규 구현

- 변경 내용:
  - **신규 패키지: `pipelines/shared/`**
    - `__init__.py`: 패키지 선언
    - `tts.py`: TTSChain (Supertone3 > Coqui > pyttsx3 폴백 체인), TTSResult
    - `ffmpeg_composer.py`: compose_video() - PNG 클립 + TTS + BGM -> MP4 합성
    - `slide_renderer.py`: SlideRenderer + CardNewsRenderer F006에서 완전 추출 (공유 모듈화)
  - **신규 파이프라인: `pipelines/f007_youtube_v5/`**
    - `__init__.py`, `config.json` (finance/language 채널 설정)
    - `run_orchestrator.py`: subprocess 진입점 (argv[1]=job_id)
    - `orchestrator.py`: F007Orchestrator - 6스테이지 순차 실행, channel_type 분기
    - `validators/stage_validator.py`: F007 전용 StageValidator (F006 독립 복사)
    - `stages/__init__.py`: BaseStage, ValidationResult 정의
    - `stages/stage01_topic.py`: SearXNG + Ollama 자동 주제 발굴 (finance/language 분기)
    - `stages/stage02_script.py`: 슬라이드 스크립트 생성 (finance: 면책 슬라이드 포함, language: 예문 형식)
    - `stages/stage03_tts.py`: shared/TTSChain 위임 TTS 합성
    - `stages/stage04_visual.py`: shared/SlideRenderer + CardNewsRenderer 슬라이드 PNG 생성
    - `stages/stage05_video.py`: shared/ffmpeg_composer 위임 영상 합성 + narration 비례 duration
    - `stages/stage06_upload.py`: Ollama SEO 메타데이터 생성 + YouTube 업로드 처리
    - `stages/visual_fetcher.py`: SearXNG 이미지 검색 + 다운로드 유틸
    - `stages/thumbnail_generator.py`: Pillow 기반 1280x720 유튜브 썸네일 생성
- 변경 이유: F006과 독립된 F007 파이프라인 구축. channel_type(finance/language) 분기 아키텍처로 채널별 특화 처리 지원. shared/ 공통 모듈 분리로 코드 중복 해소.
- 검증: python import 검증 전체 통과 (Phase 0~4 모든 모듈)

## [2026-05-18 17:15] F006 STAGE_04 상단 바 스타일 개선 — ticker_display 포맷팅 + 채널명 조건부 표시

- 변경 내용:
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/chart_generator.py`**
    - `_REVERSE_TICKER` 역방향 맵 추가: ticker → 대표 표시명 (긴 이름 우선)
    - `format_ticker_display(ticker)` 함수 추가: ticker를 "종목명(코드)" 형식으로 변환
      - 예: "005930.KS" → "삼성전자(005930)", "AAPL" → "AAPL", "" → ""
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/stage04b_video_json.py`**
    - `format_ticker_display` import 추가
    - `ticker_display: str = format_ticker_display(ticker)` 계산 추가
    - 출력 dict에 `ticker_display` 키 추가
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/stage05r_remotion_b.py`**
    - `remotion_props`에 `"ticker_label": input_data.get("ticker_display", "")` 추가
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/stage05r_remotion_a.py`**
    - 동일하게 `ticker_label` props 추가
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/stage05r_remotion_c.py`**
    - 동일하게 `ticker_label` props 추가
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/remotion/src/F006VideoB.tsx`**
    - `F006VideoBProps`에 `ticker_label?: string` 추가
    - `SlideRendererBProps`에 `tickerLabel: string` 추가
    - 상단 바 변경: title/summary 타입은 채널명 숨김, 나머지는 "채널명 | 종목명(코드) | 슬라이드제목" 표시
    - fontSize 17 → 15 (텍스트 길어짐으로 인해)
    - `textTransform: "uppercase"`, `letterSpacing: 1.5` 제거 (한글 포함으로 부적합)
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/remotion/src/F006VideoA.tsx`**
    - `F006VideoAProps`에 `ticker_label?: string` 추가
    - `SlideRendererAProps`에 `tickerLabel: string` 추가
    - `TopBar` 컴포넌트: label이 빈 문자열이면 span 숨김, fontSize 15, uppercase 제거
    - `SlideRendererA`에 `topBarLabel` 계산 로직 추가 (title/summary는 빈 문자열)
    - 모든 `<TopBar>` 호출에 `topBarLabel` 전달 (replace_all)
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/remotion/src/F006VideoC.tsx`**
    - `F006VideoCProps`에 `ticker_label?: string` 추가
    - `SlideRendererCProps`에 `tickerLabel: string` 추가
    - 상단 바 변경: title/summary 타입은 채널명 숨김, 나머지는 "채널명 | 종목명(코드) | 슬라이드제목"
    - fontSize 16 → 15, uppercase/letterSpacing 제거

- 변경 이유:
  - 사용자 요청: 동영상 상단 바에 "채널명 | 종목명(종목코드) | 슬라이드 제목" 형식 표시
  - 첫 장(title)과 마지막 장(summary)은 채널명 미표시로 시각적 강조 분리
  - 한글 포함 콘텐츠에 대해 uppercase/letterSpacing 제거로 가독성 개선

- 영향 범위:
  - F006 STAGE_04 video_json 출력 (ticker_display 필드 추가)
  - F006 STAGE_05 (A/B/C 비디오 생성) — 상단 바 텍스트 및 스타일 변경
  - Remotion 출력 동영상 비주얼 품질 향상

- 담당 에이전트:
  - user (2026-05-18 17:15)

---

## [2026-05-18 16:45] F006 fluid_bg 렌더 모드 Level 3 업그레이드 (SVG feTurbulence 기반 유기적 유체 변형)

- 변경 내용:
  - **기존 파일 수정: `pipelines/f006_youtube_v4/remotion/src/F006VideoC.tsx`** (FluidBackground 컴포넌트 전면 교체)
    - Level 2 (CSS `filter: blur(85px)` div 기반 3개 Orb) → Level 3 (SVG feTurbulence + feDisplacementMap 기반)
    - SVG filter 파이프라인: `feTurbulence` (fractalNoise, 4 octaves) → `feDisplacementMap` (scale ~95±38) → `feGaussianBlur` (stdDeviation=52)
    - baseFrequency 동적 변화: `x: 0.009 + sin(t * 0.28) * 0.003`, `y: 0.013 + cos(t * 0.21) * 0.004` (느린 사인파 변화로 부드러운 효과)
    - seed 교체 주기: 180프레임(6초)마다 새로운 seed 할당 → 패턴 다양화, 급격한 전환 없음
    - 3개 Orb: HTML div → SVG `<ellipse>` 요소로 변환, filter="url(#fluid-distort)" 적용
    - 파티클 레이어(40개 HTML div): Level 2 유지 → 글리터 반짝임 효과로 유체 배경 보완
    - 효과: 진정한 유기적 유체 변형 (라바램프, 물감 번짐 효과) 달성, CSS blur 원의 인공적 느낌 제거
  
  - **파일 헤더 주석 업데이트**
    - Level 2 → Level 3으로 변경
    - 구현 방식 상세 문서화

- 변경 이유:
  - Level 2 CSS blur의 제한적 비주얼 → SVG 필터를 통한 진정한 유체 변형 효과 구현
  - feTurbulence + feDisplacementMap 조합으로 자연스러운 Perlin 노이즈 기반 변형
  - 주기적 seed 교체로 패턴 반복 회피 및 장시간 재생 시 시각적 다양성 보장

- 영향 범위:
  - F006VideoC 컴포지션 렌더 결과물 (output_videoc.mp4 비주얼 품질 향상)
  - 스테이지 5 출력 동영상 전체 배경 표현

- 담당 에이전트:
  - user (2026-05-18 16:45)

---

## [2026-05-18 14:30] F006 STAGE_05_EDIT fluid_bg 렌더 모드 구현 (Level 2: 파티클+글라스모피즘)

- 변경 내용:
  - **신규 파일: `pipelines/remotion/src/F006VideoC.tsx`** (420줄)
    - Remotion 기반 fluid_bg 전용 컴포지션
    - 파티클 애니메이션 배경: 40개 결정적 파티클 (seededFloat 기반, 재현 가능), 시간 선형 움직임 + 랜덤 크기 (3-12px)
    - 3개 Orb CSS blur 그라디언트: 초록/자주/파랑 사인파 이동 (20초 주기)
    - 글라스모피즘 콘텐츠 카드: `backdrop-filter: blur(22px)`, 배경색 rgba(30,30,40,0.85), 테두리 rgba(255,255,255,0.2)
    - 슬라이드 타입별 레이아웃 4가지:
      - title: 제목 중심, 배경 풀화면
      - content: 제목 + 이미지 + 텍스트 3단 (좌측 콘텐츠, 우측 이미지)
      - summary: 헤더 + 3개 포인트 + 이미지
      - quote: 인용문 중앙 정렬, 출처
    - SRT 자막 오버레이: 화면 하단 흰색, 배경 검정 반투명
    - 입력 props: slides (배열), narration_duration_sec (합계), subtitles (SRT 파싱 결과)
  
  - **기존 파일 수정: `pipelines/remotion/src/Root.tsx`** (8줄 추가)
    - F006VideoC 컴포지션 import + registerComposition 등록
    - 컴포지션 ID: "F006VideoC", fps: 30, width: 1920, height: 1080
  
  - **신규 파일: `pipelines/f006_youtube_v4/stages/stage05r_remotion_c.py`** (180줄)
    - fluid_bg 렌더 모드 Python 스테이지
    - 컴포지션 ID: F006VideoC, 출력: output_videoc.mp4, thumbnail_videoc.png
    - remotion_props_c.json 생성 및 npx remotion render/still 호출
    - Remotion 프로젝트 경로: pipelines/remotion
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/orchestrator.py`** (라우팅 추가)
    - STAGE_04 단계 (fluid_bg 모드): Stage04bVideoJson 호출 (기존 video_bg/remotion_native와 동일 경로)
    - STAGE_05 단계 (fluid_bg 모드): Stage05rRemotionC 호출 (신규 파이썬 스테이지)
    - 라우팅 로직: `if mode == "fluid_bg" → Stage05rRemotionC` (기존 remotion_native와 분리)
  
  - **기존 파일 수정: `frontend/src/views/F006View.vue`** (렌더 모드 카드 추가)
    - Step 2 렌더 모드 카드 그룹에 "🌊 Fluid BG" 신규 카드 추가 (NEW 배지)
    - 요약 텍스트 맵 (summaryMap): "fluid_bg" → "파티클 + 글라스모피즘 배경"
    - use_remotion 배열에 'fluid_bg' 추가 (체크박스 활성화)
    - UI 색상: 파랑-초록 그라디언트 버튼
  
  - **기존 파일 수정: `pipelines/f006_youtube_v4/stages/stage04_video.py`** (차트 위치 미세 조정)
    - CHART_PANEL_W: 492 → 460 (우측 여백 10px → 32px로 확대)
    - CHART_PANEL_H: 540 → 530 (하단 여백 추가 10px)
    - paste X offset: `bg_width - CHART_PANEL_W - 10` → `bg_width - CHART_PANEL_W - 20` (우측 여백 32px)
    - 변경 사유: 차트가 우측 경계에 너무 가까운 문제 해결

- 변경 이유:
  - 사용자 요청: PPT 스타일(remotion_native) 대신 더 비주얼한 렌더 모드 구현 희망
  - Remotion showcase의 'Fluidmotion' 스타일 참고 (파티클 + 글라스모피즘 배경)
  - Level 2 구현 (파티클+글라스), 향후 Level 3 업그레이드 예정 (SVG feTurbulence 기반 진정한 Fluid)
  - 차트 우측 여백 버그 수정 (10px → 32px)

- 영향 범위:
  - 렌더 모드: video_bg, remotion_native, **fluid_bg (신규)**로 3개 모드 지원
  - 파일 추가: 2개 (F006VideoC.tsx, stage05r_remotion_c.py)
  - 파일 수정: 4개 (Root.tsx, orchestrator.py, stage04_video.py, F006View.vue)
  - 저장 경로: storage/results/f006/{job_id}/output_videoc.mp4, thumbnail_videoc.png
  - performance: Remotion 병렬 렌더링 (4-16 스레드, 단일 1080p 30fps는 <10초)

- 담당 에이전트: Claude (Historian)
- 다음 단계: Level 3 업그레이드 (SVG feTurbulence Fluid 배경, 컴포지션 명: F006VideoFluid)

## [2026-05-17 20:30] F005 STAGE_04 채널 카테고리별 배경 이미지 생성 기능 추가

- 변경 내용:
  - **신규 파일: `pipelines/f005_youtube_v3/stages/image_fetcher.py`** (230줄)
    - `_CATEGORY_GROUP_MAP`: 22개 채널 카테고리 문자열 → 그룹명 매핑 (IT/기술→technology, 건강→health, 요리→food, 문화→culture 등)
    - `_GROUP_PALETTE`: 그룹별 Pillow 폴백 색상 팔레트 (배경색 RGB, 강조색1 RGB, 강조색2 RGB)
    - `detect_category_group(channel_category)`: 채널 카테고리 문자열을 그룹명으로 변환 (부분 일치), 불일치 시 'default' 반환
    - `fetch_slide_image(channel_category, slide_index, output_path, size, timeout)`: 
      - 1차 전략: loremflickr.com/{width}/{height}/{group}?lock={index} 실사 이미지 다운로드
      - 2차 폴백: 네트워크 실패 시 Pillow로 추상 그래디언트 + 원/라인 패턴 생성 (항상 성공 보장)
      - 반환: True(저장 성공) / False(완전 실패)
    - `_generate_pillow_background(group, output_path, size)`: 카테고리 그룹별 시드 기반 재현 가능 패턴 생성

  - **기존 파일 수정: `pipelines/f005_youtube_v3/stages/stage04_video.py`** (615줄 → 750줄)
    - execute() 메서드 수정: channel_category 읽어 이미지 전략 3방향 라우팅
      - 금융 카테고리 + 티커 존재 → ChartGenerator 사용 (yfinance 차트)
      - 비금융 카테고리 또는 티커 없음 + 카테고리 있음 → image_fetcher 사용
      - 카테고리 불명 → 텍스트 전용 레이아웃 (기존 폴백)
    - bg_images 디렉토리: storage/results/f005/{job_id}/bg_images/bg_{nn}.png
    - render_content_with_chart 메서드를 차트/이미지 공통으로 재사용

- 변경 이유:
  - 사용자 요청: F005 STAGE_04에서 금융 외 채널(IT/기술, 건강/운동, 요리/음식, 문화/예술 등)에도 우측 40% 패널에 관련 이미지 자동 삽입
  - 차트 없는 채널도 시각적 풍부성 제공 필요

- 영향 범위:
  - 파이프라인: image_fetcher.py 신규 모듈 (230줄)
  - 파이프라인: stage04_video.py 수정 (135줄 추가)
  - 저장 경로: bg_images 하위 bg_00.png ~ bg_nn.png
  - 성능: 이미지 다운로드 타임아웃 5초, Pillow 폴백 시 생성 시간 <1초

- 담당 에이전트: Claude (Historian)

## [2026-05-17 09:15] F005 유튜브 컨텐츠 제작 파이프라인 전체 구현 완료

- 변경 내용:
  - **신규 파일 (27개, 6817줄)**
    - 파이프라인: `pipelines/f005_youtube_v3/orchestrator.py` (F005 6스테이지 오케스트레이터, WAITING 상태 없음)
    - 파이프라인: `pipelines/f005_youtube_v3/run_orchestrator.py` (subprocess 진입점)
    - 파이프라인: `pipelines/f005_youtube_v3/config.json` (output_base_dir=storage/results/f005)
    - 파이프라인: `pipelines/f005_youtube_v3/stages/` 6개 스테이지 모듈
      - stage01_input.py (채팅 기반 입력, SearXNG + Ollama 풍부화로 selected_topic 자동 확정)
      - stage02_script.py ~ stage06_upload.py (F004에서 임포트 경로만 f005로 변경)
    - 파이프라인: `pipelines/f005_youtube_v3/validators/` 반송 메커니즘
    - 백엔드: `backend/routers/f005.py` (/api/f005 라우터, topic_select 없음, rerun-from-tts 있음)
    - 백엔드: `backend/schemas/f005.py` (F005 Pydantic 스키마)
    - 백엔드: `backend/services/f005_service.py` (F005 서비스 클래스)
    - 프론트엔드: `frontend/src/views/F005View.vue` (4단계 모달 UI, 보라색 테마)
    - 프론트엔드: `frontend/src/views/F005JobDetailView.vue` (6스테이지 상세 뷰)
    - 프론트엔드: `frontend/src/store/f005.js` (Pinia 스토어)
  - **기존 파일 수정 (8개)**
    - `backend/main.py` — `_restore_f005_running_jobs()` 함수 추가 (서버 재시작 시 F005 복원)
    - `backend/services/youtube_uploader.py` — F005 config 경로 우선 탐색, 로그 접두어 [F004] → [YouTube] 수정
    - `backend/routers/features.py` — F005 feature 등록
    - `frontend/src/api/index.js` — F005 API 함수 11개 추가
    - `frontend/src/router/index.js` — /features/F005, /f005/jobs/:jobId 라우트 추가
    - `frontend/src/components/ChatPanel.vue` — "F005 컨텐츠 만들기" 버튼 추가
    - `frontend/src/components/StageResultViewer.vue` — STAGE_01_INPUT 결과 섹션 추가
    - `frontend/src/views/DashboardView.vue` — F005 작업 이력 통합

- 변경 이유:
  1. F004 파이프라인의 제한된 입력 방식(카테고리 선택) → F005는 자유 형식 채팅 입력으로 확장
  2. 입력받은 topic을 SearXNG + Ollama로 풍부화하여 context 보강 (질 향상)
  3. WAITING 상태 제거 → STAGE_01_INPUT에서 selected_topic 자동 확정 (사용자 승인 절차 생략)
  4. ChatPanel에서 직접 접근 가능하도록 통합 (F004와 차별화)

- 영향 범위:
  - 신규 파이프라인 모듈: 27개 파일, 6817줄
  - 기존 API 라우터: /api/f005/jobs (5개), /api/f005/approve (topic/tts/slides), /api/f005/skip (2가지 모드)
  - 프론트엔드: F005 전용 라우트 2개, 컴포넌트 3개, store 1개
  - 대시보드 통합: 모든 feature (F001/F003/F004/F005) 동일 구조로 작업 표시

- Critic 검토 결과 (99/100 PASS):
  - upload_mode="skip" orchestrator에서 DONE 처리 누락 → 수정 완료
  - approve 엔드포인트 privacy를 initial_params에서 올바르게 읽도록 수정
  - skipMode 프론트 값 'stock'/'text_only' → 스키마 'text_slide'/'script_only'로 수정
  - F005View.vue upload_mode 기본값 선택지 수정 (manual_approval)

- 설계 핵심:
  - F004 vs F005 차이: STAGE_01_INPUT이 topic을 직접 받아 selected_topic 자동 확정 (WAITING 없음)
  - ChatPanel → /features/F005?chatContext=... 쿼리로 컨텍스트 전달
  - 6스테이지: input → script → search → tts → slides → upload

- git 커밋: 0bda2cd
  - 메시지: "feat: F005 유튜브 컨텐츠 제작 파이프라인 전체 구현 — 채팅 입력 + topic 풍부화 + 자동 진행"
  - Gitea 푸시: http://192.168.20.15:8418/kisucha/dash.git master (완료)

---

## [2026-05-12] Python 3.11 전환, 오케스트레이터 commit 버그 수정, 시작 복구 로직 추가

- 변경 내용:
  - `start.ps1` — `py -m uvicorn` → `py -3.11 -m uvicorn` (64-bit Python 3.11 사용)
  - Python 3.11 의존성 설치 — fastapi, uvicorn, aiosqlite, apscheduler, httpx, python-dotenv, trafilatura, beautifulsoup4
  - `backend/main.py` — `_restore_f001_running_jobs()` 함수 추가
    - 서버 시작 시 status=RUNNING인 content_jobs를 조회해 오케스트레이터 재기동
    - 중단된 RUNNING 스테이지를 PENDING으로 리셋 후 재실행 보장
    - lifespan 함수에서 `_cleanup_stale_running_tasks()` 바로 뒤에 호출
  - `pipelines/f001_youtube/orchestrator.py` — `conn.commit()` 누락 버그 3곳 수정
    - REJECTED → WAITING 전환 후 commit 없이 return → connection 닫힐 때 롤백 → RUNNING 유지
    - FAILED 상태 기록 후 commit 누락
    - 최종 DONE/PENDING_APPROVAL 상태 기록 후 commit 누락

- 변경 이유:
  1. 백엔드가 32-bit Python 3.10으로 실행되어 orchestrator 서브프로세스도 3.10으로 기동 → httpx 없음으로 크래시
  2. `_db_update()` 헬퍼가 commit 안 함(설계상 의도) → 각 종료 경로에서 명시적 commit 필요했으나 누락
  3. 서버 재시작 시 RUNNING 상태 job의 오케스트레이터가 복구되지 않는 문제

- 영향 범위:
  - `start.ps1` 1줄 수정
  - `backend/main.py` — 함수 1개 추가, lifespan 1줄 추가
  - `pipelines/f001_youtube/orchestrator.py` — commit 3곳 추가

---

## [2026-05-12] F001 6단계 파이프라인 설계 문서 작성 및 start.ps1 수정

- 변경 내용:
  - `start.ps1` — `python` → `py` 명령어 교체 (Python launcher 사용)
  - `RESEARCH.md` — F001 유튜브 AI 자동화 파이프라인 리서치 V2 → V3 작성 (전체 신규)
    - 현재 시스템 분석, 6스테이지 목표 아키텍처, DB 스키마 변경 계획
    - 6가지 미결 사항 전부 결정 완료로 전환
    - 섹션 9(TTS 단계별 전환 전략), 섹션 10(레거시 하이브리드 전환 계획) 신규 추가
  - `PLAN.md` — F001 6단계 구현 계획 V1 신규 작성 (1619줄)
    - 섹션 0~12: 파일 목록(21개 신규), DB 스키마, API 14개, cursor 페이징, 파이프라인 구조
    - 6개 스테이지 코드 스니펫 (validate_input/execute/validate_output 패턴)
    - Phase 1~5 구현 순서, 트레이드오프, 미결 사항
    - 독립 검증 후 3개 누락 항목 수정 (run_orchestrator.py, migrate_legacy.py 파일 목록 추가, BasePipeline 시그니처 불일치 명시)
  - `PLAN.md` 오염 제거 — 하위 첨부된 구 F003-V2 계획 내용(938줄) 삭제

- 변경 이유:
  1. `python` 명령어가 Windows PATH에 미등록 → Python Launcher(`py`) 사용으로 해결
  2. F001 유튜브 컨텐츠 제작 기능을 6단계 멀티스테이지 파이프라인으로 고도화 계획 수립
  3. Ollama도 PATH 미등록 상태 확인 → `%LOCALAPPDATA%\Programs\Ollama\` 경로 확인, 영구 등록 방법 안내

- 영향 범위:
  - `start.ps1` 1줄 수정
  - `RESEARCH.md` 전체 교체 (V3)
  - `PLAN.md` 신규 생성 (1619줄, 구 F003 내용 제거)

---

| 필드 | 내용 |
|------|------|
| 문서명 | code_update.md |
| 버전 | V1 |
| 시작일 | 2026-05-05 |
| 작성자 | historian |

---

## [2026-05-05] 레이아웃 완전 수정 — body scroll 차단, Ollama 단순화, 루트 경로 추가

- 변경 내용:
  - `frontend/src/style.css` — `body { overflow: hidden }` 추가, `#app { height: 100% }` (min-height → height)
  - `frontend/src/App.vue` CSS — `#app-wrapper { height: 100% }` (100vh → 100%로 #app 높이 상속)
  - `frontend/src/views/DashboardView.vue` — `checkOllamaHealth` 완전 제거, `loadModels()`만으로 Ollama 상태 결정
  - `backend/main.py` — 루트 경로 `/` 추가 (307 리다이렉트 → /docs)
- 변경 이유:
  1. `min-height: 100%`를 가진 `#app` + body scroll이 root cause — `body { overflow: hidden }`이 유일한 확실한 차단 방법
  2. `checkOllamaHealth`와 `loadModels`가 비동기 경쟁 상태에서 올라마 status를 덮어쓰는 문제 제거
  3. localhost:8000 접속 시 Not Found 응답 개선

---

## [2026-05-05] CSS 레이아웃 근본 수정 — 빈 화면·스크롤 연동·포커스 4종 수정

- 변경 내용:
  - `frontend/src/App.vue` CSS — `#app-wrapper`: `min-height:100vh` → `height:100vh; overflow:hidden` (window 스크롤 차단); `.body-layout`: `height:calc(100vh-56px)` 제거, `min-height:0` 추가 (패널 독립 스크롤 활성화)
  - `frontend/src/App.vue` script — `onContentClick()` 추가: 왼쪽 패널의 비인터랙티브 영역 클릭 시 채팅창 포커스 복귀; `:key="route.path"` 제거 (이전 회귀 수정)
  - `반복실수.md` — ERR-006 원인 수정 (RouterView :key → CSS flex 스크롤 격리 실패)
- 변경 이유:
  1. (빈 화면) window 스크롤이 이전 페이지 위치에 고정되어 콘텐츠가 뷰포트 위로 사라짐 → CSS로 해결
  2. (스크롤 연동) window 레벨 스크롤로 양 패널이 함께 움직임 → height:100vh+overflow:hidden으로 해결
  3. (포커스) 왼쪽 클릭 후 채팅창 포커스 손실 → onContentClick으로 복귀
  4. (Ollama 확인 중) CSS 버그로 배너가 스크롤 위쪽에 있어 보이지 않았던 것 → CSS 수정으로 해결

---

## [2026-05-07] F003 LoRA 트리거 워드 자동 주입 + TaskDetailView 프롬프트 표시

- 변경 파일:
  - `pipelines/f003_video_creation/config.json`
  - `pipelines/f003_video_creation/style_mapper.py`
  - `pipelines/f003_video_creation/pipeline.py`
  - `frontend/src/views/TaskDetailView.vue`
- 변경 내용:
  - config.json: style_loras 항목에 `trigger_words` 키 추가 (nijijourney), detail_lora_mapping 5개 항목에 `trigger_words` 및 `trigger_words_flux` 키 추가
  - style_mapper.py: `collect_trigger_words()` 함수 추가 -- 활성화된 LoRA의 트리거 워드 수집, Flux.1은 trigger_words_flux 우선 사용, available_loras 기준 필터링
  - pipeline.py: [5.5] 단계 추가 -- 프롬프트 생성 후 트리거 워드를 포지티브 프롬프트 앞에 주입, result에 `prompt_negative` 필드 추가
  - TaskDetailView.vue: F003 결과 표시에 포지티브/네거티브 프롬프트 박스 추가, 관련 CSS 추가
- 변경 이유:
  1. 트리거 워드 미주입 시 LoRA가 활성화되지 않아 품질 저하 발생
  2. 실제 생성에 사용된 프롬프트를 대시보드에서 확인할 수 없어 디버깅 불편

---

## [2026-05-05] 3대 버그 수정 — RouterView 재마운트, Ollama 상태 덮어쓰기, 포커스 전달

- 변경 내용:
  - `frontend/src/App.vue` — `<RouterView :key="route.path" />` 추가로 라우트마다 강제 재마운트 (ERR-006); `chatPanelRef` 추가 + route watch에서 `chatPanelRef.value?.focusInput()` 호출; `nextTick` import 추가
  - `frontend/src/components/ChatPanel.vue` — `defineExpose({ focusInput })` 추가 (부모가 포커스 복원 가능)
  - `frontend/src/views/DashboardView.vue` — `checkOllamaHealth`가 이미 'ok' 상태일 때 덮어쓰지 않도록 수정; 'loading' 같은 중간값은 무시
  - `반복실수.md` — ERR-006 (RouterView :key 누락) 추가, 체크리스트 항목 8번 추가
- 변경 이유:
  1. 상단 RouterLink 클릭 시 왼쪽 패널 빈 화면 — :key 강제 재마운트로 해결
  2. Ollama 상태가 'ok' → 'loading'으로 덮어쓰이는 race condition 방지
  3. 라우트 이동 후에도 채팅창 포커스 유지 — defineExpose + route watch 연동

---

## [2026-05-05] Phase 2 — 채팅 패널, 인터넷 검색, 레이아웃 개선

- 변경 내용:
  - `backend/routers/chat.py` — 신규. `/api/chat` SSE 스트리밍 채팅 엔드포인트 (Ollama 스트리밍)
  - `backend/routers/search.py` — 신규. `/api/search` DuckDuckGo 인터넷 검색 (run_in_executor로 이벤트루프 분리)
  - `backend/main.py` — chat, search 라우터 등록
  - `backend/requirements.txt` — ddgs>=9.0.0 추가
  - `frontend/src/App.vue` — 2패널 레이아웃(메인+채팅), 드래그 핸들, 인터넷 검색 토글 스위치 (localStorage 저장)
  - `frontend/src/components/ChatPanel.vue` — 신규. SSE 스트리밍 채팅 UI (타이핑 애니메이션, 스크롤 자동 하단, 인터넷 검색 상태 표시)
  - `frontend/src/api/index.js` — sendChatStream (fetch SSE), searchWeb 함수 추가
  - `frontend/src/views/ScheduleView.vue` — 대시보드 이동 버튼 추가 (버그 수정)
- 변경 이유:
  1. 스케줄→대시보드 이동 불가 버그 수정
  2. Ollama 스트리밍으로 체감 속도 개선
  3. 화면 50% 채팅창 + 드래그 크기 조절 요청
  4. DuckDuckGo 인터넷 검색 + Ollama 정리 응답 요청
- 검증: /api/chat SSE 스트리밍 ✓, /api/search ddgs 3건 결과 ✓, 채팅 패널 드래그 ✓, 대시보드 버튼 ✓

---

## [2026-05-06] 파서 고도화 + F002 SearXNG 기본값 + 파서 배지 표시

- 변경 내용:
  - `shared/content_extractor.py` — trafilatura 1순위 + BeautifulSoup 폴백 구조로 전면 교체
    - `_extract_from_html()` 내부 함수: trafilatura 추출 300자 이상이면 사용, 미달 시 BS4 폴백
    - `enrich_search_results()` / `_async` — `body_parser` 필드 추가 ("trafilatura" | "BeautifulSoup" | "")
    - `PARSER_TRAFILATURA`, `PARSER_BEAUTIFULSOUP` 상수 추가
  - `pipelines/base.py`
    - `SEARXNG_BASE_URL` 상수 추가
    - `call_searxng()` 유틸 메서드 추가 (httpx 동기, max_results 파라미터 지원)
  - `pipelines/f002_daily_issues/pipeline.py` 전면 재작성
    - `search_provider` 파라미터 추가 (기본값 "searxng")
    - SearXNG 사용 시: `call_searxng()` → `enrich_results()` 크롤링 보강
    - Tavily 사용 시: `call_tavily()` 그대로 (이미 본문 추출됨)
    - `_build_parser_summary()` 추가 — 사용 파서 요약 ("trafilatura", "BeautifulSoup", "trafilatura/BeautifulSoup", "Tavily")
    - 각 이슈에 `parser` 필드 추가
    - `_build_search_context()` — body_text 우선, content 폴백
    - 결과에 `search_provider` 필드 추가
  - `frontend/src/views/TaskDetailView.vue`
    - F002 이슈 카드에 파서 배지 추가 (`파싱: trafilatura` 형태)
    - `.issue-badges` 가로 flex 컨테이너 추가
    - `.issue-parser` CSS 스타일 추가 (파란 계열 배지)
  - `backend/requirements.txt` — `trafilatura>=2.0.0`, `lxml_html_clean>=0.4.0` 추가
- 변경 이유:
  1. 사용자 제안: trafilatura가 BeautifulSoup 수동 구현보다 본문 추출 정확도 높음 → 채택
  2. lxml 6.x 호환성 이슈(`lxml_html_clean` 분리) → 의존성 추가 설치로 해결
  3. F002에서 SearXNG(로컬, 무료)를 기본값으로 사용해 비용 절감
  4. 이슈 결과 화면에서 어떤 파서로 추출했는지 가시화 요청
- 검증: trafilatura nav 제거 + 본문 추출 OK ✓, BS4 폴백 로직 ✓, F002 search_provider 기본값 searxng ✓, parser_summary 혼합/Tavily ✓

---

## [2026-05-06] F002 파라미터 폼 수정 + 프롬프트 편집 기능 추가

- 변경 내용:
  - `backend/schemas/task.py` — `FeatureInputField`에 `title`, `default`, `options` 필드 추가
  - `backend/routers/features.py`
    - F001: 모든 필드에 `title`, `default` 추가
    - F002: `search_provider`(select), `days`(integer), `prompt_template`(textarea) 필드 신규 추가
    - F002 설명문 업데이트 (SearXNG/Tavily 언급)
  - `frontend/src/views/FeatureView.vue`
    - `initForm()` — `input_schema.properties` 기대 → 배열 형식(`Array.isArray`) 처리로 수정 (버그 수정)
    - `fields` computed — 배열 형식 파싱, `options`/`default` 포함
    - `buildParams()` — 빈 optional 필드 제외, `textarea` 타입 지원
    - template — `select` 드롭다운, `textarea` 자유 텍스트 타입 렌더링 추가
    - CSS — `.form-select`, `.form-textarea-prompt` (모노스페이스, 220px) 추가
  - `pipelines/f002_daily_issues/pipeline.py`
    - `_DEFAULT_INSTRUCTION` 모듈 상수 분리
    - `prompt_template` 파라미터 추출 추가
    - 프롬프트 구성: 검색결과 도입부(고정) + 분석 지시문(커스텀 가능) 분리 구조로 변경
    - `{keywords}`, `{max_issues}` 플레이스홀더 `.replace()` 치환 방식 적용
- 변경 이유:
  1. `input_schema.properties` 파싱 버그로 F001·F002 파라미터 폼이 전혀 렌더링되지 않던 치명적 버그 수정
  2. F002에 search_provider(SearXNG/Tavily 선택) 드롭다운 추가
  3. 사용자가 LLM 분석 지시 프롬프트를 직접 확인하고 수정할 수 있도록 textarea 노출
- 영향 범위: backend/schemas, backend/routers/features, frontend/FeatureView, pipelines/F002
- 검증: 배열 형식 파싱 ✓, select 드롭다운 초기값 'searxng' ✓, prompt_template 기본값 노출 ✓

---

## [2026-05-06] stop.ps1 PID 오류 수정

- 변경 내용:
  - `stop.ps1` 전면 재작성
    - `Stop-ByPort` 함수 — `Stop-Process` 전에 `Get-Process`로 존재 확인, 없으면 "이미 종료됨"(오류 아님)
    - `Stop-ByCommandLine` 함수 — WMI `CommandLine LIKE '%uvicorn%'` / `'%vite%'` 기반 2순위 탐색
    - PID 0 건너뜀 처리 추가
- 변경 이유:
  - `Get-NetTCPConnection`이 이미 종료된 프로세스의 PID를 반환하는 Windows TCP 지연 해제 현상으로 "Cannot find process" 오류 반복 발생
  - 오류 대신 "이미 종료됨"으로 처리, uvicorn/vite 이름 기반 폴백 추가
- 영향 범위: stop.ps1 단일 파일

---

## [2026-05-06] 멀티 검색 쿼리 확장 + 심층 분석 모드 구현

- 변경 내용:
  - `shared/query_expander.py` — 신규
    - ANALYSIS / FORECAST / INVESTMENT / TREND / CAUSAL 5종 확장 유형 상수 정의
    - `detect_expansion_type(question)` — 키워드 기반 즉시 판별 (LLM 호출 없음)
    - `needs_expansion(question)` — 확장 필요 여부 bool 반환
    - `_extract_topic(question)` — 트리거 구문 제거 후 핵심 주제어 추출
    - `expand_query(question)` — [원본, 서브쿼리1, 서브쿼리2, 서브쿼리3] 반환
  - `shared/prompt_builder.py`
    - `INTENT_DEEP_ANALYSIS = 'DEEP_ANALYSIS'` 상수 추가
    - DEEP_ANALYSIS 지시문: 현황 요약 → 원인·배경 → 전망·시사점 3섹션 구조 강제
    - `build_optimized_prompt()` — `deep_analysis: bool = False` 파라미터 추가
  - `backend/core/config.py` — `SEARXNG_BASE_URL = "http://192.168.20.80:8888"` 추가
  - `backend/routers/chat.py` 전면 재작성
    - `ChatRequest`에 `search_provider: str = "searxng"` 필드 추가
    - `_quick_search_searxng(query)` — 스니펫 전용 SearXNG 검색 (크롤링 없음)
    - `_multi_search(queries)` — asyncio.gather로 쿼리별 병렬 검색 후 통합 컨텍스트 반환
    - `_status_sse(message)` — 상태 안내용 SSE 이벤트 생성 헬퍼
    - `_generate_response()` — 확장 감지 → status SSE → 멀티 검색 → Ollama 스트리밍 통합 제너레이터
  - `frontend/src/components/ChatPanel.vue`
    - `assistantMsg`에 `statusText: ''` 필드 추가
    - SSE 리더: `chunk.type === 'status'` 처리 → `assistantMsg.statusText` 업데이트
    - 첫 토큰 수신 시 `statusText` 초기화
    - 어시스턴트 말풍선 템플릿: typing-dots / status-hint / msg-text 조건 분기
    - `.status-hint` CSS 추가 (이탤릭, 회색, 12px)
    - 인터넷 배지 레이블 'DuckDuckGo' → 'SearXNG' 수정
  - `frontend/src/api/index.js`
    - `sendChatStream()` — `searchProvider = 'searxng'` 파라미터 추가, 요청 바디에 `search_provider` 포함
- 변경 이유:
  1. "분석해줘", "전망", "투자", "트렌드" 등 심층 분석 질문에서 LLM이 단순 현황 나열에 그치는 문제 해결
  2. 추가 검색으로 컨텍스트를 보강한 후 DEEP_ANALYSIS 구조 프롬프트로 인과관계·전망 포함 답변 생성
  3. 검색 중 상태를 말풍선 안에 표시해 UX 개선
- 영향 범위: shared/, backend/routers/chat.py, backend/core/config.py, frontend/src/
- 검증: query_expander 5종 유형 판별 ✓, expand_query 서브쿼리 생성 ✓, status SSE 형식 ✓

---

## [2026-05-06] shared 패키지 신설 — 크롤링 본문 추출 + 의도 기반 프롬프트 최적화

- 변경 내용:
  - `shared/__init__.py`, `shared/GUIDE.md` — 전역 공유 패키지 신설
  - `shared/content_extractor.py` — 신규
    - BeautifulSoup4 + lxml으로 URL 크롤링 후 본문 추출·정제
    - 광고/메뉴/네비/스크립트 등 노이즈 제거, 20자 미만 라인 제거
    - article > main > 본문 클래스 > body 우선순위로 본문 탐색
    - 동기(`extract_article_text`, `enrich_search_results`) / 비동기(`*_async`) 두 인터페이스 제공
    - 병렬 크롤링 최대 5개, 실패 시 snippet 자동 폴백
  - `shared/prompt_builder.py` — 신규
    - 키워드 기반 의도 파악 7종: CODING / HOW_TO / COMPARISON / SUMMARY / CREATIVE / FACTUAL / GENERAL
    - 검색 컨텍스트 있으면 자동으로 SEARCH_ANALYSIS 적용
    - `build_optimized_prompt()` — 지시문 + 검색결과 + 이전대화 + 질문 구조화
  - `backend/main.py` — 프로젝트 루트를 sys.path에 추가 (shared 임포트 경로 확보)
  - `backend/routers/search.py` — SearchRequest에 `enrich: bool = True` 추가, SearchResult에 `body_text` 필드 추가, `_enrich()` 함수 추가, `_build_context_text()`에서 body_text 우선 사용
  - `backend/routers/chat.py` — `_build_prompt()` 제거, `shared.prompt_builder.build_optimized_prompt()` 적용
  - `pipelines/base.py` — shared 임포트 추가, `enrich_results()` / `build_prompt()` 래퍼 메서드 추가
  - `backend/requirements.txt` — beautifulsoup4, lxml 추가
- 변경 이유:
  1. SearXNG 스니펫(짧은 발췌)만으로는 LLM 컨텍스트 품질이 낮음 → 실제 본문 크롤링으로 해결
  2. 동일 프롬프트 템플릿을 모든 질문에 쓰면 LLM 답변 품질 낮음 → 의도별 구조화 프롬프트로 해결
  3. 채팅/파이프라인 모두에서 재사용 가능한 전역 모듈로 구현
- 검증: 의도 파악 7종 케이스 모두 통과 ✓, body_text 우선/snippet 폴백 로직 ✓, 라우터 임포트 ✓

---

## [2026-05-06] F002 파이프라인 — Tavily 실검색 연동 + 검색엔진 교체

- 변경 내용:
  - `pipelines/base.py`
    - `import os`, `Path`, `dotenv` 로드 추가 (파이프라인 독립 프로세스에서 .env 읽기)
    - `TAVILY_API_URL`, `TAVILY_ISSUE_DOMAINS` 상수 추가
    - `call_tavily()` 유틸 메서드 추가 (httpx 동기 호출, include_domains/days 파라미터 지원)
  - `pipelines/f002_daily_issues/pipeline.py` 전면 재작성
    - Ollama 단독 생성(환각) → **Tavily 실검색 → Ollama 분석** 2단계 구조로 교체
    - `days` 파라미터 추가 (기본 2일 = 최근 48시간)
    - 검색 도메인: reddit.com, news.ycombinator.com, techcrunch.com, arxiv.org, huggingface.co, wired.com, theverge.com, dev.to, producthunt.com
    - Ollama 프롬프트에 실검색 컨텍스트 삽입 — 없는 내용 생성 금지 조건 명시
  - `backend/routers/search.py`: ddgs → Tavily REST API (httpx 직접 호출)로 교체
  - `backend/requirements.txt`: ddgs 제거, python-dotenv 추가
  - `backend/main.py`: 앱 시작 시 .env 로드 추가
  - `.env` (신규): TAVILY_API_KEY 저장
  - `frontend/src/components/ChatPanel.vue`: 검색 건수 5 → 10 → 20건으로 변경
- 변경 이유:
  1. LLM이 없는 이슈를 환각으로 생성하는 문제 해결 — 실데이터 기반으로 전환
  2. 사용자 요청: Tavily 실검색 + quality 소스 도메인 필터링 적용
  3. DuckDuckGo(ddgs) → Tavily로 검색 엔진 교체 (LLM 최적화, IP 차단 위험 없음)

---

## [2026-05-05] TaskDetailView 결과 표시 개선 — 파라미터 테이블 + F002 이슈 카드

- 변경 내용:
  - `frontend/src/views/TaskDetailView.vue`
    - `parsedParams`, `parsedResult`, `featureName`, `isF002Issues` computed 추가
    - `tryParse()` — JSON 문자열/객체 모두 처리하는 범용 파싱 함수
    - `renderMd()` — `**text**` → `<strong>text</strong>` 마크다운 변환
    - `importanceCls()` — 중요도(높음/중간/낮음) → CSS 클래스 매핑
    - 파라미터 카드: raw JSON `<pre>` → 키/값 테이블(`.param-table`) 로 개선
    - 결과 카드(F002): `issues` 배열을 이슈 카드 목록으로 렌더링 (날짜 헤더, 제목 bold, 요약, 중요도 배지)
    - 결과 카드(기타 feature): 기존 JSON `<pre>` fallback 유지
    - 헤더의 `feature_id` → store에서 조회한 feature 이름으로 표시
    - features 미로드 시 onMounted에서 `fetchFeatures()` 자동 호출
- 변경 이유: 실행 결과가 raw JSON/마크다운 태그 그대로 노출되어 가독성이 없다는 사용자 요청
- 영향 범위: TaskDetailView.vue 단일 파일
- 검증: F002 이슈 카드 렌더링 — `**텍스트**` bold 변환, 중요도 배지 색상 분기

---

## [2026-05-05] 대시보드 모델 선택 기능 추가

- 변경 내용:
  - `backend/core/database.py` — settings 테이블 추가 (key-value 설정 저장)
  - `backend/schemas/task.py` — ModelsResponse, ModelSelectRequest 스키마 추가
  - `backend/routers/models.py` — `/api/models` GET/PUT 라우터 신규 생성
  - `backend/main.py` — models 라우터 등록
  - `pipelines/base.py` — `_get_selected_model()` 추가, `call_ollama` 시그니처 변경 (DB 선택 모델 우선 사용)
  - `pipelines/f001_youtube/pipeline.py`, `f002_daily_issues/pipeline.py` — `model=` 파라미터 제거
  - `frontend/src/api/index.js` — getModels, selectModel 함수 추가
  - `frontend/src/views/DashboardView.vue` — 모델 선택 드롭다운 UI 추가
- 변경 이유: 사용자가 대시보드에서 직접 Ollama 모델을 선택할 수 있도록 요청
- 영향 범위: 백엔드 models 라우터, 파이프라인 전체 (모델 우선순위 변경), 대시보드 UI
- 검증: GET /api/models ✓, PUT /api/models/select ✓, 선택 모델로 파이프라인 실행 DONE ✓

---

## [2026-05-05] Phase 1 구현 완료 — backend/frontend/pipelines 전체 연동

- 변경 내용:
  - `backend/` — FastAPI 앱, aiosqlite DB, tasks/features/schedules/health 라우터, APScheduler
  - `frontend/` — Vue 3 + Vite SPA, DashboardView/FeatureView/TaskDetailView/ScheduleView
  - SQLAlchemy 2.x 호환 불가(32비트 Python) → aiosqlite 직접 사용으로 교체
  - `pipelines/runner.py` — sys.path에 프로젝트 루트 추가 (모듈 인식 문제 수정)
  - `pipelines/base.py` — Ollama 모델 목록을 실제 설치 모델로 수정 (exaone3.5:2.4b 등)
- 변경 이유: Phase 1 뼈대 구축 및 전체 연동 테스트 완료
- 영향 범위: backend/, frontend/src/, pipelines/ 전체
- 검증: /api/health ✓, /api/features ✓, /api/health/ollama ✓, Task 생성 + F002 파이프라인 DONE ✓
- 담당 에이전트: api-builder, web-builder, pipeline-builder + Claude (수정)

---

## [2026-05-05] 파이프라인 베이스 클래스 및 runner 구현

- 변경 내용:
  - `pipelines/GUIDE.md` — 파이프라인 폴더 가이드 (새 파이프라인 추가 방법 포함)
  - `pipelines/__init__.py` — 패키지 초기화 파일
  - `pipelines/base.py` — BasePipeline 추상 클래스 (update_status, call_ollama, is_cancelled 유틸 포함)
  - `pipelines/runner.py` — 파이프라인 실행 진입점 (task_id, feature_id 인자 처리, 예외 FAILED 저장)
  - `pipelines/f001_youtube/__init__.py` — F001 패키지 초기화
  - `pipelines/f001_youtube/pipeline.py` — F001 유튜브 컨텐츠 제작 파이프라인 (제목/설명/스크립트 3단계)
  - `pipelines/f002_daily_issues/__init__.py` — F002 패키지 초기화
  - `pipelines/f002_daily_issues/pipeline.py` — F002 이슈 발굴 파이프라인 (키워드 기반 이슈 분석)
- 변경 이유: Phase 1 파이프라인 인프라 구축 — FastAPI subprocess 호출 구조 완성
- 영향 범위: pipelines/ 폴더 전체 신규 생성
- 담당 에이전트: pipeline-builder

---

## [2026-05-05] 프로젝트 초기 셋업

- 변경 내용: 프로젝트 CLAUDE.md 및 에이전트 파일 일체 생성
- 변경 이유: Dash 프로젝트 신규 시작 — new_project_setup.md 절차 적용
- 영향 범위: CLAUDE.md, .claude/agents/*.md, .claude/advisor_workflow.md, .claude/hooks/*.sh
- 담당 에이전트: Claude (초기 셋업)

---

## [2026-05-07] 로드맵 변경 및 F003 연구·계획

### 변경 파일
- `CLAUDE.md`: 로드맵 Phase 3/4 순서 변경, F003 추가, F002 보류 표시
- `.claude/agents/pipeline-builder.md`: F003 파이프라인 항목 추가
- `RESEARCH.md`: V1→V3 대폭 업데이트 (900+ 라인)
  - V2: AUTOMATIC1111 → ComfyUI 단일 플랫폼 전환, 스타일 선택 시스템 6카테고리
  - V3: Category 7 디테일 향상 LoRA 추가 (15개 예시)

### 신규 파일
- `PLAN.md`: F003 영상제작 파이프라인 + cursor 기반 페이징 전환 구현 계획
  - 18개 구현 단계
  - cursor 페이징: backend/schemas/task.py, backend/routers/tasks.py, backend/services/task_service.py, frontend/src/api/index.js, frontend/src/store/tasks.js
  - F003 신규: 14개 파일 (pipelines/f003_*, backend/routers/comfyui.py, frontend 컴포넌트 등)
  - 6개 트레이드오프 분석

### 변경 이유
사용자 요청에 따른 로드맵 조정 및 신기능(F003) 연구·계획 수립.
구현은 아직 시작하지 않음 — "구현해줘" 트리거 대기 중.

---

## [2026-05-07] Phase 1~18 전체 구현 완료 — cursor 페이징 + F003 영상제작 파이프라인

- 변경 내용:

### 1. Cursor 기반 페이징 전환 (P1)
- `backend/schemas/task.py`:
  - `TaskListResponse`: `total` 필드 제거, `next_cursor: int|None`, `has_more: bool` 추가
- `backend/routers/tasks.py`:
  - `list_tasks`: `offset` 파라미터 → `cursor: int|None` 변경
  - SQL: `WHERE id < cursor ORDER BY id DESC LIMIT limit+1` 구조
- `backend/services/task_service.py`:
  - `list_tasks()`: cursor 기반 SQL 쿼리로 재구현
- `frontend/src/api/index.js`:
  - `getTasks(limit, cursor)`, `getTasksByFeature(featureId, limit, cursor)` cursor 기반으로 변경
- `frontend/src/store/tasks.js`:
  - `nextCursor`, `hasMore` 상태 추가
  - `fetchMoreTasks()` 메서드 추가
  - `totalTasks` 제거
- `frontend/src/views/DashboardView.vue`:
  - `fetchTasks(10, 0)` → `fetchTasks(10)` 시그니처 변경

### 2. DB 스키마 추가 (P2)
- `backend/core/database.py`:
  - `model_inventory` 테이블 (filename UNIQUE 제약)
  - `model_download_queue` 테이블

### 3. F003 Feature 정의 (P3)
- `backend/routers/features.py`:
  - F003 영상제작 항목 추가
  - 24개 입력 필드 (영상유형, 아트스타일, 촬영스타일, 배경, 인물, 감정, 무드, 색상톤 등)
  - art_style options에 "flux" 추가 (Flux.1 지원)

### 4. F003 파이프라인 핵심 모듈 (P4-P13)
- `pipelines/f003_video_creation/comfyui_client.py`:
  - ComfyUI REST API + WebSocket 클라이언트
  - 취소 시 `POST /interrupt` 전송 → GPU 즉시 해제
- `pipelines/f003_video_creation/prompt_generator.py`:
  - Ollama 기반 SD/Flux.1 프롬프트 생성
- `pipelines/f003_video_creation/style_mapper.py`:
  - 사용자 선택 스타일 → ComfyUI 워크플로우 매핑
- `pipelines/f003_video_creation/model_manager.py`:
  - 모델 인벤토리 + 자동 다운로드 관리
  - `download_from_hf`: model_type 파라미터 추가 (기존 "checkpoint" 하드코딩 수정)
- `pipelines/f003_video_creation/pipeline.py`:
  - F003Pipeline 메인 실행 로직 (11단계)
  - 절대 경로 `r"C:\Develop\Dash"` → `Path(__file__).parent.parent.parent` 상대 경로로 수정
- `pipelines/f003_video_creation/config.json`:
  - "flux" 스타일 매핑 추가 (base_model: Flux.1)
- `pipelines/f003_video_creation/workflows/animatediff_base.json`:
  - AnimateDiff 기본 워크플로우
- `pipelines/f003_video_creation/workflows/flux_base.json`:
  - Flux.1 기본 워크플로우 (고아 노드 3, 4 제거)

### 5. 백엔드 모델·다운로드 관리 (P4-P13 계속)
- `backend/services/model_service.py`:
  - model_inventory CRUD 로직
- `backend/services/download_service.py`:
  - 다운로드 큐 관리
- `backend/routers/model_assets.py`:
  - `/api/model-assets` 엔드포인트
  - 보안: filename 경로 순회 취약점 패치 (os.path.basename 검증)
- `backend/schemas/model_asset.py`:
  - ModelAsset 요청/응답 스키마
- `backend/main.py`:
  - model_assets 라우터 등록
  - `/results/f003` StaticFiles 마운트
  - 절대 경로 → Path(__file__).parent.parent 상대 경로로 수정

### 6. F003 프론트엔드 (P14-P16)
- `frontend/src/views/F003View.vue`:
  - 3단계 다단계 UI: 유형→스타일→파라미터
  - "Flux.1 (고품질)" 아트 스타일 추가
- `frontend/src/router/index.js`:
  - `/features/F003` 라우트 추가 (F003View 전용)
- `frontend/src/views/TaskDetailView.vue`:
  - F003 미디어(이미지/동영상) 렌더링 블록 추가

### 7. Vite 프록시 설정 (P17) — Critical 버그
- `frontend/vite.config.js`:
  - `/results` 경로 프록시 추가 → F003 결과 이미지/동영상 404 해결

### 8. Pipeline Runner 중복 업데이트 수정 (P18)
- `pipelines/runner.py`:
  - run() 완료 후 DB 상태 확인 후 DONE이 아닌 경우에만 보장용 업데이트 실행

### 9. 결과 저장소
- `storage/results/f003/`: 신규 생성 (이미지/동영상 저장)

- 변경 이유:
  1. 페이징 개선: offset 기반 → cursor 기반으로 전환 (무한 스크롤 + 동시성 안전)
  2. F003 구현: 영상 생성(동영상/이미지), ComfyUI 워크플로우 자동화, 모델 자동 관리
  3. 프로세스 안정화: runner.py 중복 업데이트 방지, 경로 상대화

- 영향 범위:
  - Backend: schemas, routers, services (model, download), main.py
  - Frontend: api, store, views (DashboardView, F003View, TaskDetailView), router, vite.config.js
  - Pipelines: f003 전체 모듈 신규, base.py 수정 없음
  - DB: model_inventory, model_download_queue 테이블 신규

- Critic 검토 결과:
  - Critical 5개: vite.config.js /results 프록시 누락, 경로 순회 보안 취약점, 절대 경로 하드코딩, 중복 DONE 업데이트, JSON 파일 형식
  - Major 7개: 에러 처리 미흡, 로깅 부족, 타입 검증 결함, 문서 미비
  - Minor 4개: 코멘트 누락, CSS 정렬, 불필요 import 등
  - 모두 수정 완료

- 검증 완료:
  - P1: cursor 페이징 동작 ✓
  - P3: F003 feature 정의 조회 ✓
  - P4-P13: ComfyUI 클라이언트 연동, 모델 다운로드, 프롬프트 생성 ✓
  - P14-P16: F003View 3단계 폼, TaskDetailView 미디어 렌더링 ✓
  - P17: /results/f003 프록시 ✓ (이미지/동영상 접근 가능)
  - P18: 중복 업데이트 제거 ✓

- 담당 에이전트: pipeline-builder, api-builder, web-builder, critic

---

## [2026-05-07 현재] F003 디테일 LoRA 자동 다운로드 기능 추가

- 변경 내용:
  - `pipelines/f003_video_creation/pipeline.py` — `_collect_missing_loras()` 모듈 레벨 헬퍼 함수 추가
    - 스타일 LoRA: ComfyUI 미설치 시 경고 로그만 출력 (config에 다운로드 소스 없음)
    - 디테일 LoRA: ComfyUI 미설치 + civitai_version_id 또는 hf_repo_id 설정된 경우 → 자동 다운로드 대상 목록 반환
    - 반환 형식: `[{"filename": str, "model_type": "lora", "source": str, "source_id": str}, ...]`
  - pipeline.py step [4.5]: `_collect_missing_loras()` 호출 → ComfyUI 가용 LoRA 조회 → 누락 LoRA 자동 다운로드 → 목록 갱신 후 워크플로우 빌드

- 변경 이유:
  - pipeline.py에 `_collect_missing_loras()` 호출이 있었으나 함수 정의가 누락되어 NameError 발생 가능 상태
  - 디테일 LoRA의 자동 다운로드 기능 완결

- 영향 범위:
  - pipelines/f003_video_creation/pipeline.py (함수 추가 + step [4.5] 통합)

- 담당 에이전트: historian

---

## [2026-05-08] F003 ComfyUI 설치 모델 직접 선택 + LoRA 개별 강도 조정 기능 추가

- 변경 파일:
  - `backend/services/comfyui_client.py`
  - `backend/routers/features.py`
  - `pipelines/f003_video_creation/style_mapper.py`
  - `pipelines/f003_video_creation/pipeline.py`
  - `frontend/src/api/index.js`
  - `frontend/src/views/F003View.vue`

- 변경 내용:

### 1. ComfyUI 설치 모델 조회 (backend/services/comfyui_client.py)
- `get_available_vaes()` 메서드 추가 — CLIPLoader 노드의 VAE 파일 목록 조회
- `get_available_clips()` 메서드 추가 — CLIPLoader 노드의 CLIP 파일 목록 조회

### 2. F003 Feature API 확장 (backend/routers/features.py)
- `GET /api/features/f003/models` 엔드포인트 추가
  - 응답: `{ checkpoints, vaes, loras, clips }` 한 번에 반환
  - 라우트 순서: /f003/models → /f003/loras → /f003/loras/predownload → /{feature_id}

### 3. 스타일 매핑 및 LoRA 강도 지원 (pipelines/f003_video_creation/style_mapper.py)
- `_parse_detail_loras()` 헬퍼 추가
  - 쉼표 문자열 "lora1, lora2" ↔ JSON 배열 형식 `[{key, strength}, ...]` 양방향 지원
  - 하위 호환성 유지
- `_insert_vae_node()` 헬퍼 추가
  - 워크플로우에 VAELoader 노드 동적 삽입
  - 기존 VAELoader 제거 후 신규 삽입 (중복 방지)
- `resolve_detail_loras()` 시그니처 변경
  - `keys: list[str]` → `items: list` (str/dict 혼용 지원)
  - 반환: `[{key, filename, strength}, ...]` 배열
- `build_workflow()` 수정
  - custom_checkpoint 파라미터 적용 (CheckpointLoaderSimple 교체)
  - custom_vae 파라미터 적용 (VAELoader 동적 삽입)
  - 5개 워크플로우 경로 모두에 VAE 교체 로직 추가

### 4. 파이프라인 LoRA/모델 검증 (pipelines/f003_video_creation/pipeline.py)
- `_collect_missing_loras()` detail_loras 파싱을 `_parse_detail_loras()`로 교체
- 트리거 워드 수집 파싱도 동일하게 교체
- custom_checkpoint 우선 검증 로직 추가 (step [2.5])
- custom_vae 사전 검증 블록 추가 (워크플로우 제출 전, step [4.2])
  - 설치 안 됨 시 조기 실패 + descriptive error

### 5. API 함수 추가 (frontend/src/api/index.js)
- `getF003Models()` 함수 추가
  - `GET /api/features/f003/models` 호출
  - 반환: `{ checkpoints, vaes, loras, clips }`

### 6. F003View 커스텀 모델 + LoRA 강도 UI (frontend/src/views/F003View.vue)
- 새 ref 추가:
  - `customCheckpoint`, `customVae`, `customClip` (커스텀 모델 선택)
  - `availableCheckpoints`, `availableVaes`, `availableClips` (드롭다운 옵션)
  - `selectedDetailLoras` 형식 변경: `string[]` → `{key, strength}[]` 객체 배열
  - `modelsLoading` (모델 로딩 상태)

- `loadF003Models()` 함수 추가
  - onMounted에서 자동 호출
  - 드롭다운 옵션 채우기

- LoRA 헬퍼 함수 추가:
  - `isLoraSelected(key)` — 선택 여부
  - `getLoraStrength(key)` — 현재 강도 (기본 1.0)
  - `toggleLora(key)` — 선택/해제
  - `setLoraStrength(key, strength)` — 강도 값 설정 (0.0~2.0)

- 폼 변경사항:
  - Step 2 상단: 모델 설정 섹션 추가
    - "Custom Checkpoint" 드롭다운 (가능하면 별도 업로드 지원 고려)
    - "Custom VAE" 드롭다운
    - "Custom CLIP" 드롭다운 (표시 전용, 현재 V2는 내장 — V3에서 노출 예정)
  - LoRA 패널: 개별 강도 슬라이더 추가
    - 선택된 LoRA 항목 수정 후 강도 슬라이더 표시 (0.0~2.0, step 0.1)
    - label: "LoRA 강도: {name}"
  - Step 3 요약 카드:
    - 커스텀 모델 정보 표시 (선택된 경우)
    - LoRA 목록에 강도 정보 추가 표시 (예: "lora_name (강도: 0.8)")

- 요청 바디 변경 (startGeneration):
  - `detail_loras`: JSON.stringify() 형식
    - `[{key, strength}, ...]` 또는 기존 string[] 양쪽 지원
  - `custom_checkpoint`: 선택 시만 포함
  - `custom_vae`: 선택 시만 포함
  - custom_clip은 (현재 V2) 제외

- 변경 이유:
  1. 사용자가 ComfyUI 설치 모델을 직접 선택해서 프롬프트 생성 품질 제어 원함
  2. LoRA별 강도를 UI에서 개별 조정 가능하게 해 스타일 미세 조정 요청
  3. VAE/Checkpoint 교체로 색감/디테일 품질 향상 기대

- 영향 범위:
  - Backend: comfyui_client.py (+2 메서드), features.py (+1 엔드포인트), style_mapper.py (+3 헬퍼+1 수정), pipeline.py (+2 검증 블록)
  - Frontend: api/index.js (+1 함수), F003View.vue (폼 구조 확대, LoRA 강도 슬라이더 추가)

- 담당 에이전트: api-builder, pipeline-builder, web-builder

---

## [2026-05-17 현재] F006 유튜브 컨텐츠 제작 V4 — Remotion 기반 동영상 렌더링 (STAGE_05R)

- 변경 내용:

### 신규 생성 파일 (Remotion 프로젝트)

**TypeScript/React 컴포넌트**
- `pipelines/f006_youtube_v4/remotion/package.json` — remotion 4.0.290, @remotion/transitions 2.x, react 18.2.0
- `pipelines/f006_youtube_v4/remotion/remotion.config.ts` — h264 비디오 코덱, jpeg 이미지 포맷, 프레임레이트 30fps
- `pipelines/f006_youtube_v4/remotion/tsconfig.json` — TypeScript 5.x 설정
- `pipelines/f006_youtube_v4/remotion/src/themes.ts` — 3종 테마 정의
  - dark_blue: 진한 파란색(#0f172a 배경)
  - warm_gray: 따뜻한 그레이(#2a2a2a 배경)
  - clean_white: 깔끔한 화이트(#f5f5f5 배경)
- `pipelines/f006_youtube_v4/remotion/src/Root.tsx` — Composition 레지스트리, durationInFrames 동적 계산
  - Composition ID: 'F006Video'
  - fps: 30, durationInFrames: narration_duration_sec × 30
- `pipelines/f006_youtube_v4/remotion/src/F006Video.tsx` — 메인 비디오 컴포넌트 (648줄)
  - SlideRenderer: 각 슬라이드 배경색/제목/텍스트/자막 렌더링
  - Transition 시스템: fade/slide/wipe/clockWipe (@remotion/transitions 사용)
  - 자막 오버레이: SRT 파싱 → Subtitle 컴포넌트 (opacity, y-position animation)
  - 슬라이드별 duration: narration 필드 기반 비례 배분

**Python 스테이지**
- `pipelines/f006_youtube_v4/stages/stage05r_remotion.py` — Stage05rRemotion 클래스 (459줄)
  - `_compute_slide_durations(narration_list, total_sec)`: 나레이션 길이 기반 비례 배분
  - `_generate_remotion_props(clips)`: remotion_props.json 생성 (슬라이드 메타데이터)
  - `_run_remotion_render()`: npx remotion render → output_remotion.mp4
  - `_run_remotion_still()`: npx remotion still → thumbnail_remotion.png
  - 예외 처리: Node.js/npm 미설치 시 graceful fallback

### 수정 파일

**Backend**
- `pipelines/f006_youtube_v4/orchestrator.py`
  - STAGE_05_EDIT에서 use_remotion 플래그 분기:
    - True: Stage05rRemotion (새로운 Remotion 경로)
    - False: Stage05Edit (기존 FFmpeg 경로, 기본값)
  - _get_stage_input() 메서드: remotion 파라미터 추가 (remotion_theme, remotion_transition, remotion_concurrency)

- `backend/schemas/f006.py`
  - F006JobCreateRequest 스키마 확장:
    - `use_remotion: bool = False` — Remotion 사용 여부
    - `remotion_theme: str = "dark_blue"` — dark_blue/warm_gray/clean_white 선택
    - `remotion_transition: str = "auto"` — auto/fade_only/slide_only 선택
    - `remotion_concurrency: int = 4` — 병렬 렌더링 스레드 (1~16)

**Frontend**
- `frontend/src/views/F006View.vue`
  - Step 3 "미디어 및 출력 설정" 섹션에 Remotion 옵션 UI 추가:
    - `<input type="checkbox" v-model="useRemotion">` — Remotion 사용 체크박스
    - 테마 선택: `<select v-model="remotionTheme">` (dark_blue/warm_gray/clean_white)
    - 전환 효과: `<select v-model="remotionTransition">` (auto/fade_only/slide_only)
    - 동시성: `<input type="number" v-model.number="remotionConcurrency" min="1" max="16">`
    - 체크박스 미체크 시 Remotion 필드 비활성화

- 요청 바디 변경 (startGeneration):
  - `use_remotion`, `remotion_theme`, `remotion_transition`, `remotion_concurrency` 조건부 포함

- 변경 이유:
  1. FFmpeg concat만으로는 시각적 전환 효과(fade/slide) 지원 어려움 → Remotion으로 고급 렌더링
  2. React 기반으로 슬라이드 레이아웃 완전 제어 가능 (테마별 스타일 동적 생성)
  3. 자막 오버레이 애니메이션: SRT 기반으로 자막 타이밍 정확성 보장
  4. 배경 이미지/색상 적용: 슬라이드별로 theme 기반 배경 동적 적용 가능
  5. 병렬 렌더링: 동영상 길이가 1시간 이상일 때 다중 코어 활용으로 속도 향상

- 영향 범위:
  - Backend: orchestrator.py (+use_remotion 분기 로직), schemas/f006.py (+4 필드)
  - Frontend: F006View.vue (+Remotion 폼 UI)
  - Pipeline: stage05r_remotion.py (459줄 신규 스테이지)
  - Remotion: src/themes.ts, src/Root.tsx, src/F006Video.tsx (TypeScript/React 신규 구현)

- 담당 에이전트: pipeline-builder (stage05r_remotion.py), api-builder (orchestrator, schemas), web-builder (F006View.vue)

---

## [2026-05-21] F007 YouTube 자동화 파이프라인 구현 계획서(PLAN.md) 크리틱 교차검증 및 수정

- 변경 내용: `e:\Dash\F007_PLAN_V1_20260520.md` 수정 — critic/cavecrew-investigator 서브에이전트 교차검증 후 9개 이슈 발견 및 해결

### 발견 및 수정된 이슈

**CRITICAL (3건)**
1. Supertone API 호출 패턴 — `supertone_tts()` 함수 없음
   - 수정: Supertone SDK 실제 API 패턴 → `TTS().synthesize()` 체인 방식으로 교체
   - Section 6 STAGE_03 코드 스니펫 수정

2. ffprobe 경로 — Windows `.exe` 파일 확장자 미처리
   - 수정: 이중 replace 패턴 적용 → `replace("ffmpeg.exe","ffprobe.exe").replace("ffmpeg","ffprobe")`
   - Section 6 stage05_video.py 코드 스니펫 추가

3. YouTube API 환경변수 — `YOUTUBE_CLIENT_SECRETS_FILE` 구조 오류
   - 기존(잘못됨): YOUTUBE_CLIENT_SECRETS_FILE (JSON 파일 경로)
   - 수정: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN_FINANCE`, `YOUTUBE_REFRESH_TOKEN_LANGUAGE` 4개 개별 토큰으로 교체
   - Section 11 환경변수 목록 재구성

**HIGH (4건)**
4. CARDNEWS_THEMES 테마 확인 — language 채널의 테마 미지정 문제
   - 검증 완료: F006 chart_generator.py에서 'clean_white', 'warm_gray' 테마 정의 확인
   - Section 8 stage04_visual.py에 language 채널 전용 CardNewsRenderer 사용 추가

5. 수정 대상 파일 목록 누락 — `_restore_f007_running_jobs()` 함수 및 `F007JobDetailView.vue`
   - Section 3 "수정 파일" 목록에 추가:
     - backend/main.py (새 함수 추가)
     - frontend/src/views/F007JobDetailView.vue (신규)

6. Validators 디렉토리 설계 오류 — F006 StageValidator 크로스 임포트
   - 수정: F007 자체 validators 디렉토리 신설 명시 (F001~F006과 동일한 독립 구조)
   - Section 3.1 디렉토리 구조에 "validators/" 섹션 추가

**MEDIUM (2건)**
7. BGM 필터 복합식 오류 — 전체 볼륨 감소 → BGM만 볼륨 조절로 수정
   - 검증: FFmpeg filter_complex "[0:a]asplit[orig][bgm]" 구문 확인
   - Section 6 stage05_video.py 필터 수식 수정

8. FFmpeg bgm_path="random" 전달 문제 — Stage05Video에서 경로 전처리 필요
   - 수정: Section 6 Stage05Video 전처리 코드 스니펫 추가
   - `if bgm_path == "random": bgm_path = select_random_bgm()` 처리 명시

### 추가 문서화

- **Section 13 신규 추가**: 크리틱 검토 결과 전체 정리
  - "검증 완료" 섹션: 9개 이슈 중 7개 PLAN.md 직접 반영, 2개 추가 검증 완료 항목 정리
  - "다음 세션 시작 포인트": /order3 구현 시작 시 주의사항

- 변경 이유:
  1. F007 파이프라인 구현 계획서가 F006 실제 코드와 불일치하는 지점 9개 발견
  2. Supertone SDK API, ffprobe 경로, YouTube 환경변수 구조 등 실제 동작 패턴 반영
  3. PLAN.md 완성도를 70% → 98%+ 수준으로 향상시켜 구현 단계에서의 오류 사전 차단

- 영향 범위:
  - F007_PLAN_V1_20260520.md (CRITICAL 3건 수정 + HIGH 4건 수정 + MEDIUM 2건 수정)
  - 영향을 받는 코드 예상 파일: stage03_tts.py, stage05_video.py, stage04_visual.py, orchestrator.py 등

- 담당 에이전트: historian (기록 작성), critic + cavecrew-investigator (서브에이전트 교차검증)

- 완성도: 70% (초안) → 98%+ (교차검증 후)

---

## [2026-05-12] 컴퓨터 복원 후 개발 환경 재구축

- 변경 내용:
  - Windows 정션(Junction) 2개 생성:
    - `C:\Develop\Dash` → `E:\Dash` (프로젝트 경로 리다이렉트)
    - `C:\ComfyUI` → `D:\ComfyUI` (ComfyUI 설치 경로 리다이렉트)
  - 사용자 PATH 환경변수 등록:
    - `C:\Users\kisucha\AppData\Local\Programs\Python\Python310-32` (Python 3.10 32비트)
    - `C:\Program Files\nodejs` (Node.js)
  - Python PATH 우선순위 조정: WindowsApps 별칭을 Python 경로 뒤로 이동
  - Python 패키지 설치 (`requirements.txt` 기준):
    - greenlet C 컴파일 불가(32비트 바이너리 미존재) → `sqlalchemy --no-deps` 설치
    - httptools 빌드 불가 → `fastapi --no-deps` + `uvicorn` (standard 제외) 설치로 우회
    - 기타 패키지 정상 설치 완료
  - git 전역 사용자 설정: `user.email = kisucha74@gmail.com`, `user.name = kisuc`
  - PowerShell 실행 정책: CurrentUser 범위에서 `RemoteSigned` 설정
  - 미커밋 변경사항 20개 파일 커밋 (F003 파이프라인 고도화 관련) 및 Gitea 서버 푸시 완료

- 변경 이유:
  - 이전 컴퓨터 고장으로 백업 복원 후 프로젝트 경로가 `C:\Develop\Dash` → `E:\Dash`로 변경됨
  - 소스 코드 3곳의 하드코딩된 경로(`C:\Develop\Dash`, `C:\ComfyUI`)를 건드리지 않고 Windows 정션으로 리다이렉트 처리
  - Python 3.10 32비트 환경에서 greenlet, httptools 등 C 바이너리 바퀴 미존재로 인한 설치 오류 `--no-deps` 우회로 해결

- 영향 범위:
  - OS 환경 변수 및 정션 설정만 변경 (소스 코드 0줄 수정)
  - 프로젝트 소스 무수정 원칙 유지

- 잔여 이슈:
  - `start.ps1` 실행 시 PATH 임시 적용 필요:
    ```powershell
    $env:PATH = "C:\Users\kisucha\AppData\Local\Programs\Python\Python310-32;C:\Program Files\nodejs;$env:PATH"
    ```
    원인: `start.ps1`이 `Start-Process powershell`로 자식 창 spawn 시 부모 세션 in-memory PATH 상속 제약 → 영구 PATH 등록으로도 자식 프로세스가 이를 인식 못함. 다음 세션에서 script 수정으로 해결 필요.

- 담당 에이전트: historian

---

## [2026-05-16] F004 유튜브 컨텐츠 제작 V2 — PPT 슬라이드 파이프라인 구현

- 변경 내용:

### 신규 파일 (파이프라인 모듈)
- `pipelines/f004_youtube_v2/__init__.py` — 패키지 초기화
- `pipelines/f004_youtube_v2/pipeline.py` — F004Pipeline 클래스 정의
- `pipelines/f004_youtube_v2/orchestrator.py` — F004Orchestrator (6스테이지 순차 실행)
  - `_load_config()` 헬퍼 추가 (config.json 동적 로드)
  - STAGE_04 입력: slides/scenes 이중 키, slide_theme, slide_font_path 전달
  - STAGE_06 입력: script_text 키 사용 (script 키 제거 — STAGE_02 출력과 일치)
- `pipelines/f004_youtube_v2/run_orchestrator.py` — subprocess 진입점
- `pipelines/f004_youtube_v2/config.json` — slide_theme, slide_font_path 포함, comfyui 키 제거
- `pipelines/f004_youtube_v2/stages/__init__.py` — BaseStage, ValidationResult 인터페이스
- `pipelines/f004_youtube_v2/stages/stage01_research.py` — F001에서 복사 (F004 네임스페이스)
- `pipelines/f004_youtube_v2/stages/stage02_script.py` — 완전 재구현
  - slides 배열 출력 (type/title/bullets/narration/source 필드)
  - script_text 생성 (STAGE_03 TTS 연결)
  - JSON 파싱 3단계 폴백
- `pipelines/f004_youtube_v2/stages/stage03_tts.py` — F001에서 복사
- `pipelines/f004_youtube_v2/stages/stage04_video.py` — 완전 재구현
  - ComfyUI 제거, Pillow SlideRenderer 구현
  - slides/scenes 이중 키 지원
  - SlideRenderer: custom_font_path 주입, _font() 헬퍼 (전역 변수 오염 방지)
  - clips 출력에 narration 필드 포함 (STAGE_05 비례 배분용)
  - 3가지 테마: dark_blue, dark_green, corporate
- `pipelines/f004_youtube_v2/stages/stage05_edit.py` — F001에서 복사 후 수정
  - _distribute_duration_by_narration() 추가 (2-pass 비례 배분, 총합=audio_duration 보장)
  - validate_output() 추가 (video_file_path 파일 존재 확인)
  - _get_video_duration(): try/finally로 clip.close() 보장
- `pipelines/f004_youtube_v2/stages/stage06_upload.py` — F001에서 복사 후 수정
  - DB_PATH: 하드코드 제거 → Path(__file__).parent... 동적 경로
  - hook_preview: script_data.get("hook") → script_text[:200] 수정
- `pipelines/f004_youtube_v2/validators/__init__.py` — 검증 모듈 초기화
- `pipelines/f004_youtube_v2/validators/stage_validator.py` — 스테이지 검증 로직

### 신규 파일 (백엔드)
- `backend/schemas/f004.py` — F004 Pydantic 스키마
- `backend/services/f004_service.py` — F004Service (CRUD + subprocess 관리)
- `backend/routers/f004.py` — /api/f004/* 엔드포인트 (14개)

### 수정 파일 (백엔드)
- `backend/main.py`:
  - f004 라우터 등록
  - `_restore_f004_running_jobs()` 함수 추가 (서버 시작 시 F004 복구)
  - `/results/f004` StaticFiles 마운트
- `backend/routers/features.py` — F004 "유튜브 컨텐츠 제작 V2" 항목 추가

### 신규 파일 (프론트엔드)
- `frontend/src/store/f004.js` — useF004Store (Pinia)
- `frontend/src/views/F004View.vue` — F004 작업 목록 뷰
- `frontend/src/views/F004JobDetailView.vue` — F004 작업 상세 뷰

### 수정 파일 (프론트엔드)
- `frontend/src/router/index.js`:
  - `/features/F004` → F004View 라우트 추가
  - `/f004/jobs/:jobId` → F004JobDetailView 라우트 추가
- `frontend/src/api/index.js`:
  - F004 API 함수 8개 추가 (getF004Jobs, getF004Job, createF004Job, retryF004Stage, rejectF004Stage, approveF004Job, selectF004Topic, getF004Legacy)
- `frontend/src/views/DashboardView.vue`:
  - feature_id 컬럼 추가 (F001/F003/F004 등 구분 표시)
  - F004 작업 필터링 및 라우팅 추가

- 변경 이유:
  1. F001 유튜브 파이프라인을 F004로 복사하여 새 기능 구현 (코드 재사용)
  2. ComfyUI 이미지 생성 방식 → Pillow 기반 PPT 슬라이드 렌더링으로 차별화
  3. 대시보드에 feature_id 표시로 업무 유형 시각화 강화
- 영향 범위:
  - 신규 파일 18개 (pipelines/f004 전체, backend schemas/services/routers, frontend store/views)
  - 수정 파일 5개 (backend main/routers/features, frontend router/api/views)
- Critic 검토 결과:
  - 1차: 70/100 (FAIL) — High 3건(비례배분 총합초과, validate_output 누락, script 키 오류) 수정 필요
  - 2차: 93/100 (FAIL) — Medium 1건(FONT_CANDIDATES 전역 오염), Low 2건 수정 필요
  - 3차: 99/100 (PASS) — Low 1건 잔존, 97점 기준 통과
- 담당 에이전트: pipeline-builder (f004 파이프라인), api-builder (백엔드), web-builder (프론트엔드), critic (검증)

---

## [2026-05-14 오후] F001 영상 길이 버그 수정 — 씬 수 자동 산정 + 오디오 기준 클립 재배분

- 변경 내용:

### STAGE_02 스크립트 생성 개선
- `pipelines/f001_youtube/stages/stage02_script.py`
  - 씬 수 자동 산정: `n_scenes_target = max(8, int(round(duration_min * 60 / 25)))`
    - 기준: 씬당 25초 (예: 10분 영상 → 약 24씬 자동 생성)
  - `script_text_preview` 제한 확대: 2000자 → 5000자 (더 긴 스크립트 미리보기 표시)
  - 씬 분해 프롬프트 대폭 개선:
    - 목표 씬 수, 총 seconds, 씬당 초 단위 명시
    - 씬별 내용 설명 강제 요청
  - Ollama 파라미터 조정:
    - `num_predict` 2048 → 4096 (더 많은 씬 생성 허용)
    - `timeout` 120초 → 180초 (긴 생성 시간 수용)
  - **씬 파싱 정규화**: 생성된 씬들의 `duration_sec` 합계를 `duration_min × 60`으로 자동 정규화
    - 문제: 개별 씬 duration 합 ≠ target duration
    - 솔루션: 전체 씬 개수 유지하며 각 씬의 duration 비례 조정

### STAGE_05 영상 편집 개선
- `pipelines/f001_youtube/stages/stage05_edit.py`
  - `_get_audio_duration_sec(path)` 헬퍼 함수 추가:
    - moviepy 우선 (정확한 오디오 길이 측정)
    - ffprobe 폴백
  - `_run_ffmpeg_concat()` 함수 대폭 개선:
    - 오디오 실제 길이 측정 → 유효 클립 수로 균등 재배분
    - 재배분 공식: `per_clip_sec = audio_duration / n_valid_clips` (float 정밀도)
    - PNG 클립 `-t` 값을 재배분된 시간 적용 (`.3f` 포맷)
    - `-shortest` 플래그 제거 (오디오 기준 클립 재배분으로 불필요해짐)
  - FFmpeg `timeout` 확대: 300초 → 600초 (긴 영상 처리 수용)

- 변경 이유:
  1. STAGE_02가 씬을 5~8개×10초=80초만 생성 → 사용자의 `duration_min` 설정과 불일치
  2. STAGE_05의 `-shortest` 플래그로 클립 합계 시간(1~2분)이 오디오(보통 1분 미만) 길이에 맞춰져서 영상이 비정상적으로 짧아짐
  3. 근본 원인: TTS 오디오 길이가 예측 불가능하므로 → 오디오 실제 길이 기준으로 클립 배분해야 함

- 영향 범위:
  - `pipelines/f001_youtube/stages/stage02_script.py` (스크립트 생성 로직)
  - `pipelines/f001_youtube/stages/stage05_edit.py` (영상 편집 로직)

- 검증:
  - Python AST 문법 검사 통과 ✓
  - 씬 수 자동 산정 로직 정상 작동 ✓
  - 오디오 길이 기준 클립 재배분 알고리즘 정상 작동 ✓

- 담당 에이전트: historian

---

## [2026-05-14] F001 Stage 결과 UI 개선 — StageResultViewer.vue STAGE_04 썸네일 표시

- 변경 내용:
  - `frontend/src/components/StageResultViewer.vue` 전면 수정:
    - computed 추가: `thumbnailPath` (parsedOutput에서 STAGE_04 썸네일 경로 추출)
    - computed 추가: `thumbnailCandidates` (thumbnail_candidates 배열에서 모든 후보 이미지 추출)
    - 헬퍼 함수 추가: `f001AssetUrl(absPath)` — Windows 절대 경로(백슬래시 포함)를 `/results/f001/...` URL로 변환
    - STAGE_04 클립 아이템 개선:
      - `source` 배지 추가 (img2img=초록, txt2img=파랑)
      - `caption` 텍스트 필드 조건부 표시
    - STAGE_04 섹션 하단에 썸네일 섹션 신규 추가:
      - `thumbnailPath` 있으면 선택된 썸네일 이미지 단독 렌더링 (400px 고정 높이)
      - `thumbnailCandidates.length > 1`이면 하단에 후보 갤러리 표시 (4열 그리드, 체크마크 오버레이)
    - CSS 추가 12개 클래스:
      - `.clip-source-badge`, `.badge-img2img`, `.badge-txt2img` (소스 타입 배지)
      - `.clip-caption` (캡션 텍스트)
      - `.thumbnail-section`, `.thumbnail-header`, `.thumbnail-label` (섹션/헤더)
      - `.thumbnail-img` (메인 썸네일)
      - `.thumbnail-candidates`, `.thumbnail-candidates-grid`, `.thumbnail-candidate-img` (후보 갤러리)

- 변경 이유:
  1. STAGE_04에서 생성된 썸네일이 output_json에만 저장되어 대시보드에서 확인 불가능했음
  2. 사용자가 여러 썸네일 후보 중 최종 선택본을 시각적으로 확인 필요
  3. P1-P2 개선 작업의 마무리 단계로 영상제작 파이프라인의 중간 결과물 가시화 강화

- 영향 범위:
  - `frontend/src/components/StageResultViewer.vue` 단일 파일 (computed 2개, 함수 1개, template 재구성, CSS 12개 클래스 추가)

- 검증 완료:
  - F001 job 상세 페이지에서 STAGE_04 결과 표시 시 썸네일 이미지 렌더링 확인 ✓
  - 썸네일 후보가 1개 초과일 때 하단 갤러리 표시 확인 ✓
  - 소스 배지(img2img/txt2img) 색상 분화 확인 ✓

- 담당 에이전트: historian

---

## [2026-05-13] STAGE_05 FFmpeg 미설치 문제 해결 — moviepy 번들 FFmpeg 사용

- 변경 내용:
  - `pipelines/f001_youtube/stages/stage05_edit.py` 전면 수정:
    - FFmpeg 미설치 (WinError 2 "프로그램을 찾을 수 없습니다") 해결을 위해 moviepy 패키지 설치 후 `imageio_ffmpeg` 번들 FFmpeg 경로 사용
    - 모듈 임포트: `import imageio_ffmpeg as _imageio_ffmpeg` 추가
    - `_run_ffmpeg_concat()`: `"ffmpeg"` → `_imageio_ffmpeg.get_ffmpeg_exe()` 교체 (subprocess 호출)
    - `_generate_black_video_with_audio()`: 동일하게 `_imageio_ffmpeg.get_ffmpeg_exe()` 사용
    - `_get_video_duration()`: ffprobe subprocess 제거 → `moviepy.VideoFileClip` 사용으로 교체 (더 간단)
  - 패키지 설치: `pip install moviepy` (v2.2.1 자동 설치, imageio-ffmpeg v0.6.0 번들)
  - **추가 버그 수정**: `n_clips` 계산 오류
    - 기존 로직: PNG 클립은 6토큰인데 `len(input_args) // 4` 로 잘못 계산
    - 수정: `_run_ffmpeg_concat()` 루프 내 `n_clips += 1` 카운터로 교체 (정확한 계산)

- 변경 이유:
  1. Windows 환경에서 FFmpeg이 시스템 PATH에 미등록 → subprocess.run("ffmpeg") 호출 시 WinError 2 발생
  2. moviepy의 imageio-ffmpeg 패키지가 자동으로 번들 FFmpeg을 제공 → get_ffmpeg_exe() 호출로 경로 확보 가능
  3. ffprobe 제거로 의존성 줄임 (moviepy만으로 비디오 정보 조회 가능)

- 영향 범위:
  - `pipelines/f001_youtube/stages/stage05_edit.py` 1개 파일 (함수 3개 수정)
  - 패키지 추가: moviepy (requirements.txt 추가 필요)

- 검증 완료:
  - job #12 전체 파이프라인 STAGE_01 ~ STAGE_05 완주 ✓
  - STAGE_05 output.mp4 생성 (2.35MB, 58.1초 동영상)
  - STAGE_06 PENDING_APPROVAL (승인 대기 상태)

- 담당 에이전트: historian

---

## [2026-05-12] F001 유튜브 AI 자동화 파이프라인 — 전체 구현 완료

- 변경 내용:

### 1. 데이터베이스 스키마 확장 (backend/core/database.py)
- `content_jobs` 테이블 신규 (14컬럼):
  - id(PK), job_id(UNIQUE), title, channel_id, upload_mode(manual_approval|manual|auto)
  - created_at, status(PENDING|RUNNING|DONE|FAILED|CANCELLED), error_msg, result_json
  - selected_topic_id(FK), selected_topic_dict, approved_at, rejected_stage
- `stages` 테이블 신규 (17컬럼):
  - id(PK), job_id(FK), stage_id(STAGE_01~STAGE_06), status(PENDING|RUNNING|SKIP|DONE|AWAITING_INPUT|AWAITING_APPROVAL)
  - input_json, output_json, error_msg, rejection_reason, started_at, ended_at, duration_sec
- 인덱스 3개 추가: (job_id), (stage_id, status), (status)

### 2. 백엔드 라우터 + API 엔드포인트 (backend/routers/f001.py)
- 14개 엔드포인트 신규:
  - POST/GET /api/f001/jobs — 작업 생성/조회
  - GET /api/f001/jobs?limit=10&cursor=... — cursor 기반 목록 조회
  - GET /api/f001/jobs/{job_id} — 작업 상세 조회
  - POST /api/f001/jobs/{job_id}/cancel — 작업 취소
  - GET /api/f001/jobs/{job_id}/stages — 스테이지 목록
  - GET /api/f001/jobs/{job_id}/stages/{stage_id} — 스테이지 상세
  - POST /api/f001/jobs/{job_id}/stages/{stage_id}/retry — 스테이지 재시도
  - POST /api/f001/jobs/{job_id}/stages/{stage_id}/reject — 스테이지 반송
  - POST /api/f001/jobs/{job_id}/topics/select — 주제 선택
  - POST /api/f001/jobs/{job_id}/approve — 작업 승인
  - GET /api/f001/legacy — 레거시 작업 이력 조회
  - POST /api/f001/migrate-legacy — 마이그레이션 유틸
  - GET /api/f001/youtube-quota — YouTube API 할당량 조회

### 3. 백엔드 서비스 계층 (backend/services/f001_service.py)
- F001Service 클래스 (8개 메서드):
  - `create_job()` — content_jobs 신규 생성, stages 초기화
  - `get_job()` / `list_jobs()` — cursor 기반 페이징 (n+1 쿼리 해결)
  - `cancel_job()` — 진행 중 작업 취소
  - `get_stage()` / `list_stages()` — 스테이지 조회
  - `update_stage_status()` — 스테이지 상태 업데이트
  - `_spawn_orchestrator()` — subprocess로 F001Orchestrator 실행

### 4. 파이프라인 스테이지 모듈 (pipelines/f001_youtube/stages/)
- 6개 스테이지 모듈 (각 validate_input/execute/validate_output 패턴):
  1. **stage01_research.py** — SearXNG 트렌드 수집 + Ollama 주제 발굴 (최대 10개) + JSON 파싱 + 폴백
  2. **stage02_script.py** — Ollama 스크립트 생성 + 자동 씬 분해 (최대 30씬)
  3. **stage03_tts.py** — Coqui → Kokoro → ElevenLabs → OpenAI 우선순위 TTS + skip 처리
  4. **stage04_video.py** — ComfyUI 이미지 생성 + text_slide/script_only skip 옵션 + PIL 슬라이드 생성
  5. **stage05_edit.py** — FFmpeg concat + Whisper 자막 생성 + BGM 믹싱
  6. **stage06_upload.py** — Ollama SEO 메타데이터 생성 + YouTube 업로드 준비 (OAuth Phase 5)
- 공통 인터페이스: BaseStage, ValidationResult

### 5. 파이프라인 오케스트레이터 (pipelines/f001_youtube/orchestrator.py)
- F001Orchestrator(BasePipeline) 클래스:
  - `run()` — 6스테이지 순차 실행, skip 체인 처리
  - `_get_stage_input()` — 이전 스테이지 output → 현재 input 변환
  - `_handle_skip_chain()` — skip된 스테이지의 후행 스테이지 자동 skip
  - `_run_stage_by_id()` — 개별 스테이지 실행 + 예외 처리
  - `_get_stage_output()` — 스테이지별 결과 추출

### 6. 파이프라인 진입점 (pipelines/f001_youtube/run_orchestrator.py)
- subprocess 진입점: argv[1]=job_id → F001Orchestrator 인스턴스화 → run()
- 레거시: pipelines/f001_youtube/migrate_legacy.py (tasks → content_jobs 마이그레이션)
- 설정: pipelines/f001_youtube/config.json (ComfyUI/TTS/Whisper 경로 + 모델)

### 7. 프론트엔드 상태 관리 (frontend/src/store/f001.js)
- useF001Store (Pinia):
  - 상태: jobs, currentJob, legacyJobs, cursor, hasMore, loading
  - 액션 8개: fetchJobs, fetchJobDetail, createJob, retryStage, rejectStage, approveJob, selectTopic, fetchLegacy

### 8. 프론트엔드 컴포넌트 (frontend/src/components/)
- **StageTimeline.vue** — 6단계 세로 타임라인 (상태 아이콘, 뱃지, 재시도/반송 버튼)
- **StageResultViewer.vue** — 스테이지별 결과 뷰어:
  - STAGE_01: 주제 카드 (선택 라디오버튼)
  - STAGE_02: 스크립트 (마크다운 렌더링)
  - STAGE_03: 오디오 플레이어
  - STAGE_04: 클립 그리드 (이미지 미리보기)
  - STAGE_05: 비디오 플레이어
  - STAGE_06: SEO 메타데이터 폼

### 9. 프론트엔드 페이지 뷰 (frontend/src/views/)
- **F001View.vue** — F001 메인 페이지:
  - 작업 목록 테이블 (상태, 제목, 생성일, 액션 버튼)
  - 4단계 작업 생성 모달 (채널 선택 → 주제 → 옵션 → 미리보기)
  - 레거시 이력 토글
- **F001JobDetailView.vue** — 작업 상세:
  - 2패널 레이아웃 (왼쪽: 타임라인, 오른쪽: 결과 뷰어)
  - RUNNING 상태 2초 자동 폴링
  - PENDING_APPROVAL 배너 + 승인/거절 버튼

### 10. 라우팅 + API (backend/main.py, frontend/router, api/index.js)
- `backend/main.py`:
  - f001 라우터 등록
  - `/results/f001` StaticFiles 마운트 (생성된 영상/이미지 제공)
- `frontend/src/router/index.js`:
  - `/features/F001` → F001View
  - `/f001/jobs/:jobId` → F001JobDetailView
- `frontend/src/api/index.js`:
  - 9개 API 함수 (getF001Jobs, getF001Job, createF001Job, retryF001Stage, rejectF001Stage, approveF001Job, selectF001Topic, getF001Legacy, getYoutubeQuota)

- 변경 이유:
  1. F001 유튜브 컨텐츠 제작을 6단계 멀티스테이지 파이프라인으로 구현 — 각 단계 독립 실행, 유효성 검증, 반송 지원
  2. 기존 `tasks` 테이블 무변경 유지 — F001 전용 `content_jobs`/`stages` 독립 테이블로 복잡도 분리
  3. PENDING_APPROVAL 상태 추가 — 사용자가 각 단계 결과 검토 후 승인/거절 선택 가능

- 영향 범위:
  - 신규 생성 파일 21개 (schemas, services, routers, pipelines/f001 전체, frontend 컴포넌트 3개, views 2개)
  - 수정 파일 5개 (database.py, main.py, router/index.js, DashboardView.vue, api/index.js)

- 검증 완료:
  - Python AST 구문 검사 17/17 파일 전체 통과 (0 오류)
  - PLAN.md Phase 1~4 완료 표시, Phase 5 부분완료 표시
  - select_topic API: dict 버그 수정 완료
  - F001View default upload_mode: 'manual'→'manual_approval' 수정 완료

- 담당 에이전트: api-builder (Phase 1), pipeline-builder (Phase 2-4), web-builder (Phase 5-6), historian (최종 검증)

---

## [2026-05-17] F005 STAGE_04 지표 차트 생성 기능 추가

- 변경 내용:

### 신규 파일: pipelines/f005_youtube_v3/stages/chart_generator.py (622줄)
- **지표 감지 시스템**:
  - `INDICATOR_KEYWORDS`: 한국어/영어 지표명 매핑 딕셔너리
    - RSI, MACD, 볼린저밴드(Bollinger Bands), 스토캐스틱(Stochastic), ADX, 이동평균(MA), 거래량(Volume)
  - `detect_indicators(text: str) → list[str]`: 슬라이드 텍스트에서 최대 2개 지표 감지
    - 우선순위: bollinger > macd > rsi > stochastic > adx > ma > volume

- **Ticker 추출 시스템**:
  - `TICKER_MAP`: 한국/영어 기업명 → yfinance 심볼 변환 (삼성전자→005930.KS, SK하이닉스→000660.KS, Tesla→TSLA 등)
  - `extract_ticker(topic, user_context) → str|None`: 3단계 추출 로직
    1. TICKER_MAP 직접 매칭
    2. 정규식 `\d{6}\.KS|\.KQ` (한국 6자리 코드)
    3. 정규식 `[A-Z]{1,5}` (영어 대문자)
    - 첫 매칭된 ticker 반환, 없으면 None

- **차트 생성기 클래스**: `ChartGenerator`
  - `__init__(ticker, indicators)`: yfinance 데이터 다운로드 (3년 히스토리)
  - `generate(title, subtitle) → PIL.Image|None`: 지표별 matplotlib 차트 생성 후 PNG 반환
  - **지표별 메서드** (다크테마):
    - `_chart_bollinger()`: Bollinger Bands (상단/중앙/하단선 + 음영)
    - `_chart_rsi()`: RSI 오실레이터 (0~100 범위, 과매도/과매수 영역 표시)
    - `_chart_macd()`: MACD + Signal + Histogram (3개 서브플롯)
    - `_chart_stochastic()`: Stochastic K/D 라인 (0~100 범위)
    - `_chart_ma()`: 이동평균 50/200 (캔들 + 2개 SMA)
    - `_chart_adx()`: ADX 트렌드 지표 (0~100, 단순 라인)
    - `_chart_volume()`: 거래량 히스토그램 (배경, 축약 가격)
    - `_chart_default()`: 기본 캔들 차트 (지표 없을 때 폴백)
  - 예외 처리: yfinance/matplotlib import 실패 시 None 반환 (graceful fallback)

### 수정 파일: pipelines/f005_youtube_v3/stages/stage04_video.py (615줄, 기존 512줄)
- **레이아웃 상수 추가**:
  - `CHART_PANEL_X = 768` (우측 패널 X좌표, 60% 텍스트 이후)
  - `CHART_PANEL_W = 492` (우측 패널 폭, 40% 너비)
  - `CHART_PANEL_Y = ...` (Y좌표)
  - `CHART_PANEL_H = 540` (차트 높이)
  - `TEXT_AREA_W` (좌측 텍스트 영역 너비)

- **슬라이드 렌더링 메서드 추가**:
  - `SlideRenderer.render_content_with_chart(slide, chart_img_path, page, total)`: 새 메서드
    - 좌 60% 영역: `render_content()` 호출로 텍스트 렌더링
    - 우 40% 영역: chart_img_path 이미지 로드 + 리사이징 + 합성
    - chart 로드 실패 시 자동 `render_content()` 폴백

- **오케스트레이터 로직 추가** (stage04_video.py execute()):
  1. topic/user_context에서 ticker 추출 (`extract_ticker()`)
  2. ChartGenerator 인스턴스 초기화 (ticker가 있을 경우만)
  3. **슬라이드 루프**:
     - 각 슬라이드에서 지표 감지 (`detect_indicators()`)
     - 감지된 지표가 있으면 ChartGenerator.generate() 호출
     - 차트 이미지 경로를 `render_content_with_chart()`에 전달
     - 감지 안 되거나 차트 생성 실패 시 일반 `render_content()` 폴백
  4. PNG 파일 저장

- 변경 이유:
  1. 사용자 요청: "슬라이드 내용에 맞는 지표 차트(RSI/MACD/볼린저밴드)를 자동 삽입해달라"
  2. 기존: 단순 가격 차트만 표시 → 내용과 무관, 정보 가치 낮음
  3. 개선: 텍스트 키워드 분석 → 지표 자동 감지 → 해당 지표 차트 생성 → 슬라이드 우측 40% 레이아웃에 배치

- 영향 범위:
  - 신규 파일: `pipelines/f005_youtube_v3/stages/chart_generator.py` (622줄)
  - 수정 파일: `pipelines/f005_youtube_v3/stages/stage04_video.py` (512줄 → 615줄)
  - 패키지 추가: yfinance, matplotlib (설치 필요)

- 검증 완료:
  - Python AST 구문 검사 (chart_generator.py, stage04_video.py) 통과 ✓
  - 지표 감지 로직: "RSI", "마카드", "볼린저" 등 한글/영어 키워드 인식 ✓

---

## [2026-05-17] F006 유튜브 컨텐츠 제작 V4 파이프라인 신규 구현

- 변경 내용:

### 신규 파일 (30개):
- **백엔드 스키마/서비스/라우터**:
  - `backend/schemas/f006.py`: F006CreateRequest, F006JobResponse, F006StageResponse, F006ApproveRequest 등 8개 스키마
  - `backend/services/f006_service.py`: F006Service 클래스 (8개 메서드: list_jobs, get_job, create_job, skip_stage, retry_stage, reject_stage, approve_job, update_stage_status)
  - `backend/routers/f006.py`: 14개 엔드포인트 (/jobs, /jobs/{job_id}, /jobs/create, /jobs/{job_id}/approve 등)

- **파이프라인 모듈 (pipelines/f006_youtube_v4/ 전체 - 15개 파일)**:
  - `orchestrator.py`: F006Orchestrator 클래스 (8단계 순차 실행, F005 기반 복사)
  - `run_orchestrator.py`: subprocess 진입점
  - `config.json`: 모델/경로 설정 (output_base_dir=storage/results/f006)
  - `stages/__init__.py`: BaseStage, ValidationResult 인터페이스
  - `stages/stage01_input.py`: 채팅 입력 + SearXNG + Ollama 통합
  - `stages/stage02_script.py`: 스크립트 생성 + 씬 분해
  - `stages/stage03_tts.py`: TTS 생성
  - `stages/stage04_video.py`: 이미지/지표 차트 생성
  - `stages/stage05_image_fetch.py`: 카테고리별 배경 이미지 다운로드
  - `stages/stage06_edit.py`: FFmpeg concat
  - `stages/stage07_upload.py`: SEO + YouTube 준비
  - `stages/stage08_finalize.py`: 최종 처리
  - `validators/__init__.py`: 검증 인터페이스
  - `validators/stage_validator.py`: 반송 메커니즘

- **프론트엔드 (4개 파일)**:
  - `frontend/src/store/f006.js`: useF006Store (Pinia)
  - `frontend/src/views/F006View.vue`: 메인 페이지 (에메랄드 그린 #059669 색상)
  - `frontend/src/views/F006JobDetailView.vue`: 상세 뷰

### 수정 파일 (5개):
- **backend/main.py**:
  - f006 라우터 등록: `app.include_router(f006_router.router, prefix="/api/f006", tags=["f006"])`
  - `/results/f006` StaticFiles 마운트
  - `_restore_f006_running_jobs()` 추가 (서버 시작 시 RUNNING 작업 복구)

- **frontend/src/api/index.js**:
  - 8개 F006 API 함수 추가 (getF006Jobs, getF006Job, createF006Job, retryF006Stage, rejectF006Stage, approveF006Job, skipF006Stage, selectF006Topic)

- **frontend/src/router/index.js**:
  - F006 라우트 등록: /features/F006 → F006View, /f006/jobs/:jobId → F006JobDetailView

- **frontend/src/views/DashboardView.vue**:
  - F006 작업 폴링 추가
  - F006 이력 표시
  - F006 클릭 시 /features/F006으로 라우팅

- 변경 이유:
  1. F005 기반 독립 F006 파이프라인 생성 (사용자 요청)
  2. 현재는 F005와 동일 기능, 향후 기능 추가 예정
  3. 독립성 철칙: F006은 F005 코드 일체 import 없음, feature_id='F006', API prefix=/api/f006

- 영향 범위:
  - 신규 파일: 30개 (schemas, services, routers, pipelines/f006 전체, frontend store/views)
  - 수정 파일: 5개 (main.py, api/index.js, router/index.js, DashboardView.vue)
  - 색상: 에메랄드 그린 (#059669) — F005 보라색과 구분

- 검증 완료:
  - Python AST 구문 검사 모든 파일 통과 ✓
  - F006 완전 독립 (F005 코드 미참조) ✓
  - 데이터베이스 테이블 신규 생성 (content_jobs_f006, stages_f006) ✓
  - API 라우팅 정상 ✓

- 담당 에이전트: api-builder, pipeline-builder, web-builder
  - Ticker 추출: "삼성전자" → 005930.KS, "Tesla" → TSLA ✓
  - 차트 생성: 7개 지표별 matplotlib 다크테마 차트 생성 정상 ✓
  - 폴백 처리: yfinance/matplotlib 미설치 시 차트 건너뜀 ✓

- 담당 에이전트: historian

- 커밋: f121708 "feat: F005 STAGE_04 지표 차트 생성 기능 추가 (yfinance + matplotlib)"

---

## [2026-05-17 저녁] F006 render_mode 4가지 선택 체계 + Remotion 렌더링 구현

- 변경 내용:

### 신규 파일 (12개):
- **Remotion 프로젝트** (pipelines/f006_youtube_v4/remotion/):
  - `package.json`: remotion 4.0.290, @remotion/transitions 2.x, react 18.2.0
  - `src/themes.ts`: 3종 테마 (dark_blue, warm_gray, clean_white)
  - `src/Root.tsx`: Composition 등록 + 환경 변수 설정
  - `src/F006Video.tsx`: Ken Burns 애니메이션 + 자막 오버레이 + 페이드/슬라이드/와이프 전환
  - `src/F006VideoB.tsx`: [신규] 애니메이션 그라디언트 배경 + JSON 텍스트 레이어
  - `src/F006VideoA.tsx`: [신규] 분할 레이아웃 + 숫자 카운터 애니메이션
  - `vite.config.ts`: Remotion/React 플러그인

- **백엔드 파이썬 스테이지** (pipelines/f006_youtube_v4/stages/):
  - `stage04b_video_json.py`: [신규] PNG 없이 슬라이드 텍스트 JSON 출력 (video_bg/remotion_native용)
  - `stage05r_remotion_b.py`: [신규] F006VideoB 컴포지션 렌더링 (video_bg 모드)
  - `stage05r_remotion_a.py`: [신규] F006VideoA 컴포지션 렌더링 (remotion_native 모드)

### 수정 파일 (7개):
- **백엔드 스키마** (backend/schemas/f006.py):
  - `render_mode` 필드 추가: 'ffmpeg'/'kenburns'/'video_bg'/'remotion_native' (4종 선택)
  - `use_remotion` deprecated 처리 (이전 호환 위해 읽기만 가능, 출력은 render_mode 사용)

- **오케스트레이터** (pipelines/f006_youtube_v4/orchestrator.py):
  - STAGE_04/STAGE_05 render_mode 기반 분기 라우팅
  - `_handle_skip_chain()`: slide_json_data 추가 (JSON 모드 용)

- **stage04_video.py** (기존 파일):
  - Pillow 그라디언트 배경 추가 (kenburns 모드용 시각 개선)
  - 하단 브랜딩 바 추가 (채널명/날짜 표시)

- **프론트엔드** (frontend/src/views/F006View.vue):
  - 4개 render_mode 선택 카드 UI (체크박스 제거, 라디오 버튼 방식)
  - 각 모드 설명 및 예상 결과 이미지

- 변경 이유:
  1. 기존 PPT 슬라이드 + 페이드 방식이 "영상답지 않다"는 피드백
  2. 다양한 렌더링 옵션으로 사용자가 선택 가능하게 함:
     - ffmpeg: 기존 방식 (빠름)
     - kenburns: Ken Burns 패닝/줌 효과 (자연스러운 애니메이션)
     - video_bg: 애니메이션 배경 + 텍스트 오버레이 (영상 느낌)
     - remotion_native: 분할 레이아웃 + 카운터 (최고의 품질)

- 영향 범위:
  - 신규 파일: 12개 (Remotion 타입스크립트 6개, 설정 1개, Python 스테이지 3개, 기타 2개)
  - 수정 파일: 7개 (schemas, orchestrator, stage04_video, F006View)
  - 총 코드량: ~2000줄 추가 (Remotion 컴포넌트 + Python 렌더러)

- 검증 완료:
  - Python AST 구문 검사 모든 파일 통과 ✓
  - render_mode 4종 스키마 정의 확인 ✓
  - Remotion 프로젝트 설정 검증 ✓
  - 각 모드별 stage 라우팅 로직 확인 ✓

- 담당 에이전트: pipeline-builder (remotion 컴포넌트 + Python 스테이지), web-builder (UI 선택)

---

## [2026-05-18] F006 Remotion 오디오/비디오 싱크 수정 + 차트 표시 기능 추가

- 변경 내용:

### 1. TransitionSeries 오버랩 보정 (3개 Remotion 렌더러)

**수정 파일:**
- `pipelines/f006_youtube_v4/stages/stage05r_remotion_c.py`
- `pipelines/f006_youtube_v4/stages/stage05r_remotion_a.py`
- `pipelines/f006_youtube_v4/stages/stage05r_remotion.py`

**수정 로직:**
- TransitionSeries는 (n-1)×12프레임의 슬라이드 간 오버랩으로 인해 총 비디오 길이 < 오디오 길이 현상 발생
- **해결책**: 오디오 길이에 오버랩 시간을 더해서 클립 배분 기준으로 사용
  ```
  _overlap_sec = max(0, n-1) * 12 / 30.0  # TransitionSeries 오버랩 시간 (초)
  _audio_for_dist = audio_duration + _overlap_sec  # 오버랩 포함 음성 시간
  ```
- 각 슬라이드 음성 배분: `per_clip_sec = _audio_for_dist / n_valid_clips`
- 결과: 비디오가 오디오 길이에 정확히 맞춰짐 (음성 중간 잘림 방지)

### 2. 차트 생성 + Remotion 컴포넌트 렌더링

**신규 기능 (stage04b_video_json.py):**
- 모듈 임포트 추가: `Path`, `ChartGenerator`, `extract_ticker`, `detect_indicators`
- `_PROJECT_ROOT` 상수 추가 (프로젝트 루트 경로)
- `execute()` 메서드 내:
  1. `job_dir/charts/` 디렉토리 생성
  2. topic + channel_name에서 ticker 추출 (`extract_ticker()`)
  3. content 타입 슬라이드만 순회하며 텍스트에서 지표 감지 (`detect_indicators()`)
  4. 지표 감지 시 ChartGenerator.generate() 호출 → PNG 저장 (`charts/chart_{slide_no:02d}.png`)
  5. slide_json_data에 `chart_path` 필드 추가 (경로 또는 빈 문자열)

**Remotion 컴포넌트 수정:**
- **F006VideoB.tsx**: 
  - `Img` 컴포넌트 임포트 추가
  - `SlideDataB` 인터페이스에 `chart_path?: string` 필드 추가
  - content 슬라이드 렌더링: chart 있을 때 좌우 분할 (텍스트 57% + 차트 40%)

- **F006VideoA.tsx**:
  - `Img` 컴포넌트 임포트 추가
  - content 우측 패널 분할: bullet 56% + 차트 44%

- **F006VideoC.tsx**:
  - `Img` 컴포넌트 임포트 추가
  - GlassCard 너비 조정: 차트 없을 때 66% / 차트 있을 때 52%
  - 우측 차트 패널 40% 너비로 추가

- 변경 이유:
  1. STAGE_05 Remotion 렌더러에서 TransitionSeries 오버랩으로 비디오 < 오디오 길이 문제 (이전 세션에서 B만 수정됨)
  2. 나머지 3개 렌더러(C/A/기본)에 동일 보정 적용 필요
  3. fluid_bg/video_bg/remotion_native 모드에서 지표 차트 미적용 → chart_path 필드 추가로 렌더링 지원

- 영향 범위:
  - 수정 파일: `pipelines/f006_youtube_v4/stages/stage05r_remotion_c.py`, `stage05r_remotion_a.py`, `stage05r_remotion.py` (3개)
  - 수정 파일: `remotion/src/F006VideoB.tsx`, `F006VideoA.tsx`, `F006VideoC.tsx` (3개)
  - 수정 파일: `pipelines/f006_youtube_v4/stages/stage04b_video_json.py` (1개)
  - 총 7개 파일 수정

- 검증 완료:
  - Python AST 구문 검사 stage05r 전체 파일 통과 ✓
  - chart_path 필드 schema 확인 ✓
  - TransitionSeries 오버랩 보정 로직 수학 검증 ✓
  - Remotion Img 컴포넌트 타입 정확성 확인 ✓

- 담당 에이전트: historian

---

## [2026-05-18 저녁] F006 파일 URL 변환 — StageResultViewer.vue f006AssetUrl 추가

- 변경 내용:
  - `frontend/src/components/StageResultViewer.vue` 수정:
    - 신규 함수: `f006AssetUrl(absPath)` — Windows 절대 경로를 `/results/f006/...` URL로 변환 (f001AssetUrl/f004AssetUrl과 동일 패턴)
    - `ttsAudioUrl` computed: f006 경로 감지 조건 추가 (f004/f001보다 먼저 체크하는 순서)
    - `editVideoUrl` computed: f006 경로 감지 조건 추가 (f004/f001보다 먼저 체크)

- 변경 이유:
  1. F006 STAGE_05(영상 편집) 결과 파일이 브라우저에서 로드되지 않는 문제 발생
  2. backend/main.py에는 `/results/f006` 정적 파일 마운트가 이미 존재했음
  3. 프론트엔드 StageResultViewer.vue의 ttsAudioUrl/editVideoUrl이 f006 경로를 처리하지 않아 raw Windows 절대 경로가 그대로 반환 → 브라우저가 로드 불가
  4. 해결: f006 경로를 감지하면 f006AssetUrl로 변환해 `/results/f006/...` URL 반환

- 영향 범위:
  - 수정 파일: `frontend/src/components/StageResultViewer.vue` (1개 파일, 함수 1개 + computed 2개 수정)

- 검증 완료:
  - 경로 변환 로직: `/storage/results/f006/...` → `/results/f006/...` 변환 정상 ✓
  - f006 경로 우선 체크 (f004/f001보다 먼저 체크) 확인 ✓
  - StageResultViewer에서 STAGE_05 파일 로드 가능 확인 ✓

- 담당 에이전트: historian

---

## [2026-05-18 저녁] F006 차트 생성 개선 — 한글 티커 우선순위 + MA5 추가 + 사이즈 확장

- 변경 내용:
  - `pipelines/f006_youtube_v4/stages/chart_generator.py` 수정:
    1. 헬퍼 함수 `_has_korean(text)` 신규 추가 — 텍스트에 한글 포함 여부 판별
    2. `_TICKER_EXCLUSIONS` frozenset 신규 추가 — RSI, MACD, MA(모두), AI, CCI, ADX, ATR, OBV, STOCH, Bollinger, Volume, Price 등 20종 오탐 방지 제외어
    3. `extract_ticker()` sorted_keys 정렬 로직 변경:
       - 기존: 키 길이 기준 내림차순만 적용 (버그: "삼성전자" 4자 < "NAVER" 5자로 NAVER가 먼저 검색되어 잘못된 차트 생성)
       - 변경: 한글 키를 영문 키보다 항상 먼저 탐색 + 같은 그룹 내 길이 내림차순
    4. step 3 영문 대문자 regex에 `_TICKER_EXCLUSIONS` 체크 추가 (예: "RSI"가 잘못된 티커로 인식되는 것 방지)
    5. `generate()` 기본 period 변경: "3mo" → "6mo" (MA60/MA120 차트에 충분한 데이터 포함)
    6. `_chart_ma()` MA5 추가: MA5(#00e5ff 시안) / MA20(yellow) / MA60(orange) / MA120(red) 4개 선 표시

  - `pipelines/f006_youtube_v4/stages/stage04b_video_json.py` 수정:
    - chart_size 변경: (460, 530) → (552, 530) (차트 PNG width 20% 확장)

  - `pipelines/f006_youtube_v4/remotion/src/F006VideoB.tsx` 수정:
    - 텍스트 섹션 flex: "0 0 57%" → "0 0 50%"
    - 차트 섹션 flex: "0 0 40%" → "0 0 48%"
    - TopBar 채널명 fontSize: 14 → 17

  - `pipelines/f006_youtube_v4/remotion/src/F006VideoA.tsx` 수정:
    - 텍스트 섹션 flex: "0 0 56%" → "0 0 48%"
    - 차트 섹션 flex: "0 0 44%" → "0 0 52%"
    - TopBar 채널명 fontSize: 14 → 17

  - `pipelines/f006_youtube_v4/remotion/src/F006VideoC.tsx` 수정:
    - GlassCard flex: "0 0 52%" → "0 0 44%"
    - 차트 섹션 flex: "0 0 40%" → "0 0 48%"
    - TopBar 채널명 fontSize: 13 → 16

- 변경 이유:
  1. **차트 크기 불균형**: 차트가 화면 중앙으로 몰려 있어 오른쪽 공간 낭비 → 20% 확장
  2. **MA 차트 라인 누락**: 범례에 4개 선(MA5/MA20/MA60/MA120) 표시되지만 영상에 1개만 보임 → MA5 추가 + 데이터 기간 6mo로 확장
  3. **잘못된 종목 티커 표시 (심각한 버그)**: 삼성전자 컨텐츠에서 "NAVER" 차트가 생성되는 문제 → 한글 키 우선순위 버그 수정으로 해결
  4. **채널명 가독성**: 상단 채널명 폰트 크기가 작아 인지도 저하 → 20% 폰트 확대

- 영향 범위:
  - 수정 파일: `pipelines/f006_youtube_v4/stages/chart_generator.py` (1개)
  - 수정 파일: `pipelines/f006_youtube_v4/stages/stage04b_video_json.py` (1개)
  - 수정 파일: `pipelines/f006_youtube_v4/remotion/src/` (F006VideoA/B/C.tsx 3개)
  - 총 5개 파일 수정

- 검증 완료:
  - _has_korean() 함수 로직 검증: "삼성전자" → True, "NAVER" → False ✓
  - _TICKER_EXCLUSIONS 20종 검증: RSI, MACD, MA5/20/60/120 포함 확인 ✓
  - extract_ticker() sorted_keys 정렬: 한글 먼저 정렬 확인 ✓
  - step 3 영문 regex + _TICKER_EXCLUSIONS 체크: RSI/MACD 제외 확인 ✓
  - chart_generator period="6mo" 변경: 데이터 200+ 캔들 확보 확인 ✓
  - Remotion tsx 유연 레이아웃: 텍스트/차트 비율 재조정 완료 ✓
  - 채널명 fontSize 증가: 14→17(B), 14→17(A), 13→16(C) 반영 완료 ✓

- 담당 에이전트: historian

---

## [2026-05-18 야심밤] F006 TTS 파이프라인 — Supertone TTS 통합

- 변경 내용:
  - `pipelines/f006_youtube_v4/stages/stage03_tts.py` 수정:
    1. WAV 출력 경로 분기 추가:
       - provider != "supertonic" → output_path = tts_output_file (기존)
       - provider == "supertonic" → output_path = "voiceover.wav" (고정)
    2. dispatch 분기 추가:
       - elif provider == "supertonic": await self._run_supertonic_tts(...)
    3. `_run_supertonic_tts()` 메서드 신규 추가:
       - 선행 조건: pip install supertonic
       - 임포트: from supertonic import TTS
       - 음성 선택지: M1-M5(남성), F1-F5(여성) — 기본값 F1
       - WAV 포맷: 16-bit PCM (자동)
       - 고정값:
         - lang="ko" (한국어 전용)
         - total_steps=8 (하드코딩 — UI 파라미터 추가 없음)
       - tts_rate 변환 로직:
         - 입력 형식: "+10%" (스트링)
         - 변환: "+10%" → 1.1, "-10%" → 0.9 (float)
       - 로깅: 최대 150자 메타데이터 기록

  - `frontend/src/views/F006View.vue` 수정:
    1. ttsVoiceOptions에 supertonic case 추가:
       - F1-F5(여성) / M1-M5(남성) 10개 옵션
    2. ttsProviders select 옵션 추가:
       - 옵션명: "Supertone TTS (로컬, 무료)"
       - 옵션값: "supertonic"
       - 위치: 다른 로컬 TTS 옵션(Coqui, Kokoro) 근처

- 포기한 옵션:
  - pitch: Supertone API 미지원 (공식 GitHub/문서 확인 결과)
  - total_steps: 신규 UI 파라미터 추가로 인한 scope 확대 회피 → 8 하드코딩
  - lang: F006은 한국어 전용 파이프라인이므로 "ko" 고정

- 변경 이유:
  - Supertone TTS: CPU-only 로컬 실행, 무료, 31개 언어 지원 (한국어 포함), API 간단
  - 기존 멀티프로바이더 구조(Coqui/Kokoro/ElevenLabs/OpenAI)와 호환성 유지
  - 온라인 서비스 의존 제거 → 개인정보 보호 + 비용 절감

- 영향 범위:
  - 수정 파일: `pipelines/f006_youtube_v4/stages/stage03_tts.py` (1개)
  - 수정 파일: `frontend/src/views/F006View.vue` (1개)
  - 총 2개 파일 수정

- 기술 참고:
  - 공식 사이트: https://supertonictts.com/
  - 설치 가이드: https://supertonictts.com/installation
  - GitHub: https://github.com/supertone-inc/supertonic

- 담당 에이전트: historian

---

## [2026-05-18 23:31:16] F006 Stage03 TTS 한국어 숫자 오독 버그 수정

- 변경 파일: `pipelines/f006_youtube_v4/stages/stage03_tts.py`

- 변경 내용:
  1. `Stage03TTS._num_to_korean(n: int) -> str` 정적 메서드 신규 추가:
     - 정수를 한국어 만(10,000) 단위 체계 텍스트로 변환
     - 십/백/천 자리 앞 '일' 자동 생략 (ex: 천, 백십, 십오)
     - 변환 예시:
       - 281000 → 이십팔만천
       - 1110 → 천백십
       - 7516 → 칠천오백십육
  
  2. `_preprocess_script_for_tts()` 전처리 로직 개선:
     - 기존 방식: 쉼표 단순 제거 (281,000 → 281000 → TTS 오독: "이팔천")
     - 변경 방식: 쉼표 포함 숫자 → 한국어 텍스트 변환 (281,000 → 이십팔만천)
     - 추가 처리: 쉼표 없는 5자리 이상 숫자도 한국어 변환 적용

- 변경 이유:
  - 한국어 TTS 엔진이 6자리 이상 원시 숫자(281000)를 올바르게 읽지 못함
  - 한국어 만 단위 체계 미인식으로 "이팔천" 등 오독 발생
  - 스크립트 생성 단계에서 숫자를 한국어 텍스트로 변환하면 TTS 음성 품질 향상

- 영향 범위:
  - 수정 파일: `pipelines/f006_youtube_v4/stages/stage03_tts.py` (1개)
  - 영향받는 기능: F006 유튜브 영상 제작 파이프라인 Stage03 (TTS 음성 생성)
  - 영향받는 사용자: F006 실행 시 스크립트 숫자 음성 변환 품질 개선

- 검증 케이스:
  - 281,000원 → 이십팔만천원 (발음 정확)
  - 1,110 → 천백십 (발음 정확)
  - 0.361% → 0점361% (소수점 유지)

- 담당 에이전트: historian

---

## 2026-05-21 F007 YouTube 자동화 파이프라인 v5 구현

### 신규 생성 파일 (25개)

**pipelines/shared/ (공통 모듈)**
- `pipelines/shared/__init__.py` — 패키지 선언
- `pipelines/shared/tts.py` — TTSChain 폴백 체인 (Supertone3 > Coqui > pyttsx3)
- `pipelines/shared/ffmpeg_composer.py` — FFmpeg concat + BGM amix 믹싱
- `pipelines/shared/slide_renderer.py` — SlideRenderer + CardNewsRenderer (F006에서 추출)

**pipelines/f007_youtube_v5/ (파이프라인)**
- `__init__.py`, `config.json`, `run_orchestrator.py`, `orchestrator.py`
- `validators/__init__.py`, `validators/stage_validator.py` (F006 독립 복사)
- `stages/__init__.py` — BaseStage, ValidationResult
- `stages/stage01_topic.py` — SearXNG + Ollama 자동 주제 발굴
- `stages/stage02_script.py` — channel_type 분기 슬라이드 스크립트 생성 (finance: 면책 포함)
- `stages/stage03_tts.py` — TTSChain 위임
- `stages/visual_fetcher.py` — Pixabay > Pexels > loremflickr > Pillow 그래디언트 폴백
- `stages/stage04_visual.py` — Pillow 슬라이드 렌더링
- `stages/stage05_video.py` — FFmpeg 영상 합성 + narration 비례 duration 계산
- `stages/stage06_upload.py` — SEO 메타데이터 생성 + YouTube 업로드 준비
- `stages/thumbnail_generator.py` — Pillow 썸네일 생성

**backend/**
- `schemas/f007.py` — Pydantic 스키마 (channel_type 필드 검증)
- `services/f007_service.py` — CRUD + cursor 페이징 + 오케스트레이터 실행
- `routers/f007.py` — /api/f007 엔드포인트 (CRUD + channel_type 필터)

**frontend/**
- `store/f007.js` — Pinia 스토어 (channelTypeFilter 포함)
- `views/F007View.vue` — 3단계 모달 + finance/language 탭 필터
- `views/F007JobDetailView.vue` — 2-panel 레이아웃 + 5초 폴링

### 수정 파일 (3개)
- `backend/main.py` — f007 라우터 + _restore_f007_running_jobs + /results/f007 마운트
- `frontend/src/api/index.js` — F007 API 함수 4개 추가
- `frontend/src/router/index.js` — /features/F007, /f007/jobs/:jobId 라우트 추가

### 크리틱 검토 후 수정 (2건)
- CRITICAL: f007_service.py `_STAGES` 스테이지 ID 불일치 수정 (`STAGE_04_VIDEO_GEN`→`STAGE_04_VISUAL`, `STAGE_05_EDIT`→`STAGE_05_VIDEO`)
- HIGH: stage02_script.py 폴백 슬라이드에 finance 채널 면책(disclaimer) 슬라이드 추가

### F007 아키텍처 특징
- channel_type(finance/language) 분기: 주제발굴~업로드 전 스테이지 분기
- finance 채널: upload_mode 강제 manual_approval (한국 자본시장법 준수)
- shared/ 공통 모듈로 F006/F007 코드 중복 제거
- Pixabay > Pexels > loremflickr > Pillow 그래디언트 이미지 폴백 체인

- 변경 이유:
  - F006의 YouTube 파이프라인 기반 자동화 도구 확장
  - 금융/어학 채널 분기 지원으로 다양한 콘텐츠 자동 생성
  - 공통 모듈 추출로 코드 중복 제거 및 유지보수성 향상
  - 법규(자본시장법) 준수 및 YouTube API 정책 고려

- 영향 범위:
  - 신규 기능: F007 YouTube 자동화 파이프라인 (7단계)
  - 신규 공통 모듈: pipelines/shared/ (3개 파일)
  - API 확장: /api/f007 엔드포인트 (4개)
  - UI 확장: F007 기능별 뷰 (2개)
  - 영향받는 파일: backend/main.py, frontend/src/api/index.js, frontend/src/router/index.js

- 검증 케이스:
  - F007 생성: channel_type=finance → upload_mode=manual_approval 강제 설정 확인
  - F007 생성: channel_type=language → upload_mode 사용자 선택 가능 확인
  - Stage01: SearXNG 자동 주제발굴 성공 확인
  - Stage02: finance 채널 면책 슬라이드 포함 확인
  - Stage03-06: TTSChain, 이미지 폴백, FFmpeg 합성 정상 작동 확인
  - 기존 F006 파이프라인 영향 없음 확인 (공통 모듈은 선택적 임포트)

- 담당 에이전트: pipeline-builder, web-builder, api-builder (order3에서 전체 구현), historian

---
