# 목적: F001 6스테이지 오케스트레이터 — content_jobs + stages 테이블 기반 순차 실행.
# BasePipeline을 상속받아 call_ollama, call_searxng 등 유틸을 재사용한다.
# run_orchestrator.py에서 subprocess로 호출되며, argv[1]=job_id를 받는다.

import sys
import sqlite3
import json
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# BasePipeline 상속 — call_ollama, call_searxng 유틸 재사용
from pipelines.base import BasePipeline

# 스테이지 클래스 임포트
from pipelines.f001_youtube.stages.stage01_research import Stage01Research
from pipelines.f001_youtube.stages.stage02_script import Stage02Script
from pipelines.f001_youtube.stages.stage03_tts import Stage03TTS
from pipelines.f001_youtube.stages.stage04_video import Stage04VideoGen
from pipelines.f001_youtube.stages.stage05_edit import Stage05Edit
from pipelines.f001_youtube.stages.stage06_upload import Stage06Upload

# 반송(reject) 메커니즘 임포트
from pipelines.f001_youtube.validators.stage_validator import StageValidator

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# DB 경로 상수 — f001_youtube/orchestrator.py 기준 세 단계 상위가 프로젝트 루트
DB_PATH: str = str(Path(__file__).parent.parent.parent / "storage" / "dash.db")

# 스테이지 실행 순서 — (stage_id, stage_order) 쌍
STAGE_SEQUENCE: list[tuple[str, int]] = [
    ("STAGE_01_RESEARCH", 1),
    ("STAGE_02_SCRIPT", 2),
    ("STAGE_03_TTS", 3),
    ("STAGE_04_VIDEO_GEN", 4),
    ("STAGE_05_EDIT", 5),
    ("STAGE_06_UPLOAD", 6),
]

# stage_id → 스테이지 클래스 매핑
_STAGE_CLASS_MAP: dict[str, type] = {
    "STAGE_01_RESEARCH": Stage01Research,
    "STAGE_02_SCRIPT": Stage02Script,
    "STAGE_03_TTS": Stage03TTS,
    "STAGE_04_VIDEO_GEN": Stage04VideoGen,
    "STAGE_05_EDIT": Stage05Edit,
    "STAGE_06_UPLOAD": Stage06Upload,
}


class F001Orchestrator(BasePipeline):
    """F001 6스테이지 오케스트레이터.

    BasePipeline 상속으로 call_ollama(), call_searxng() 등 유틸 재사용.
    content_jobs + stages 테이블 기반 동기 sqlite3 사용.

    실행 흐름:
      1. content_jobs WHERE id=job_id 로드
      2. initial_params JSON 파싱
      3. STAGE_SEQUENCE 순서대로 각 스테이지 실행
         - 이전 스테이지 output_data를 다음 입력으로 연결
         - REJECTED 상태이면 루프 중단 (사용자 개입 대기)
         - DONE/SKIPPED이면 계속 진행
      4. 모든 스테이지 완료 후 upload_mode에 따라 content_jobs 상태 업데이트
    """

    def get_metadata(self) -> dict:
        """F001 오케스트레이터 메타데이터."""
        return {
            "feature_id": "F001_MULTI",
            "name": "F001 멀티스테이지 오케스트레이터",
            "description": "6스테이지 유튜브 컨텐츠 제작 파이프라인",
            "input_schema": {},
            "supports_schedule": False,
        }

    def run(self, job_id: int, params: dict = None) -> dict:  # type: ignore[override]
        """6스테이지 파이프라인 실행 진입점.

        BasePipeline의 추상 메서드 run(task_id, params)와 시그니처가 다르다.
        F001Orchestrator는 content_jobs 기반이므로 job_id만 받아 DB에서 로드한다.
        # type: ignore[override]로 타입체커 경고를 억제한다.

        Args:
            job_id: content_jobs.id
            params: 사용되지 않음 (BasePipeline 추상 메서드 계약 충족용)

        Returns:
            {"status": "completed"} 또는 {"status": "rejected", "stage": ...}
        """
        logger.info(f"[F001Orchestrator] 시작 — job_id={job_id}")

        # DB 커넥션 생성 (동기 sqlite3)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 딕셔너리 형식 접근 가능

        try:
            # ----------------------------------------------------------------
            # 1. content_jobs 로드 및 RUNNING 상태 전환
            # ----------------------------------------------------------------
            cursor = conn.execute(
                "SELECT * FROM content_jobs WHERE id = ?", (job_id,)
            )
            job_row = cursor.fetchone()
            if not job_row:
                raise RuntimeError(f"content_jobs id={job_id} 레코드 없음")

            job: dict = dict(job_row)
            now: str = datetime.now(timezone.utc).isoformat()

            self._db_update(
                conn,
                "UPDATE content_jobs SET status = 'RUNNING', started_at = ? WHERE id = ?",
                (now, job_id),
            )
            logger.info(f"[F001Orchestrator][job_id={job_id}] content_jobs RUNNING 전환")

            # ----------------------------------------------------------------
            # 2. initial_params JSON 파싱
            # ----------------------------------------------------------------
            try:
                initial_params: dict = json.loads(job["initial_params"] or "{}")
            except (json.JSONDecodeError, TypeError):
                initial_params = {}

            # ----------------------------------------------------------------
            # 3. 스테이지 순차 실행
            # ----------------------------------------------------------------
            prev_output: dict = {}  # 이전 스테이지 출력 (다음 입력으로 연결)

            for stage_id, stage_order in STAGE_SEQUENCE:
                logger.info(
                    f"[F001Orchestrator][job_id={job_id}] "
                    f"스테이지 시작: {stage_id} (order={stage_order})"
                )

                # 이 스테이지의 입력 데이터 구성
                input_data = self._get_stage_input(
                    conn, job_id, stage_id, initial_params, prev_output
                )

                # 스테이지 실행
                result = self._run_stage_by_id(
                    conn, job_id, stage_id, stage_order, input_data
                )

                # REJECTED: 사용자 개입이 필요한 상태 → job을 WAITING으로 전환 후 정상 종료
                if result.get("rejected", False):
                    logger.warning(
                        f"[F001Orchestrator][job_id={job_id}] "
                        f"스테이지 {stage_id} REJECTED — 사용자 개입 대기"
                    )
                    self._db_update(
                        conn,
                        "UPDATE content_jobs SET status = 'WAITING' WHERE id = ?",
                        (job_id,),
                    )
                    conn.commit()
                    return {"status": "waiting", "stage": stage_id}

                # STAGE_01 완료 후 주제 선택 대기 — selected_topic이 없으면 WAITING 전환
                # STAGE_02를 먼저 실행하면 validate_input 실패로 STAGE_01 output_data가 삭제됨
                if stage_id == "STAGE_01_RESEARCH":
                    stage01_output = self._get_stage_output(conn, job_id, "STAGE_01_RESEARCH")
                    if not stage01_output.get("selected_topic"):
                        logger.info(
                            f"[F001Orchestrator][job_id={job_id}] "
                            f"STAGE_01 완료 — 주제 미선택, WAITING 전환"
                        )
                        self._db_update(
                            conn,
                            "UPDATE content_jobs SET status = 'WAITING' WHERE id = ?",
                            (job_id,),
                        )
                        conn.commit()
                        return {"status": "waiting", "stage": "STAGE_01_RESEARCH"}

                prev_output = result

            # ----------------------------------------------------------------
            # 4. 모든 스테이지 완료 — upload_mode 분기
            # ----------------------------------------------------------------
            upload_mode: str = job.get("upload_mode", "manual_approval")
            final_status: str

            if upload_mode == "auto":
                # STAGE_06에서 실제 업로드까지 처리했으므로 DONE
                final_status = "DONE"
            else:
                # manual_approval: 사용자 승인 대기
                final_status = "PENDING_APPROVAL"

            now = datetime.now(timezone.utc).isoformat()
            self._db_update(
                conn,
                (
                    "UPDATE content_jobs "
                    "SET status = ?, finished_at = ? "
                    "WHERE id = ?"
                ),
                (final_status, now, job_id),
            )
            conn.commit()
            logger.info(
                f"[F001Orchestrator][job_id={job_id}] 모든 스테이지 완료 — "
                f"최종 상태: {final_status}"
            )
            return {"status": "completed", "final_status": final_status}

        except Exception as e:
            # 예외 발생 시 content_jobs FAILED 처리
            logger.error(f"[F001Orchestrator][job_id={job_id}] 오케스트레이터 실패: {e}")
            now = datetime.now(timezone.utc).isoformat()
            try:
                self._db_update(
                    conn,
                    (
                        "UPDATE content_jobs "
                        "SET status = 'FAILED', finished_at = ?, notes = ? "
                        "WHERE id = ?"
                    ),
                    (now, str(e)[:500], job_id),
                )
                conn.commit()
            except Exception as db_e:
                logger.error(f"[F001Orchestrator][job_id={job_id}] FAILED 업데이트 실패: {db_e}")
            raise

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 스테이지 실행 메서드
    # ------------------------------------------------------------------

    def _run_stage_by_id(
        self,
        db_conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
        stage_order: int,
        input_data: dict,
    ) -> dict:
        """단일 스테이지 실행 + DB 상태 관리.

        처리 흐름:
          1. stages 레코드 조회 (PENDING이면 실행, DONE이면 스킵)
          2. stages status=RUNNING 업데이트
          3. 스테이지 클래스 인스턴스화 → validate_input → execute → validate_output
          4. 결과를 stages output_data에 저장, status=DONE

        Args:
            db_conn: sqlite3 커넥션
            job_id: content_jobs.id
            stage_id: 스테이지 ID 문자열 (예: "STAGE_01_RESEARCH")
            stage_order: 스테이지 실행 순서 (1~6)
            input_data: 이 스테이지에 전달할 입력 딕셔너리

        Returns:
            스테이지 output_data 딕셔너리
            {"rejected": True}: 반송 발생 시
        """
        now: str = datetime.now(timezone.utc).isoformat()

        # stages 레코드 조회
        cursor = db_conn.execute(
            "SELECT * FROM stages WHERE job_id = ? AND stage_id = ?",
            (job_id, stage_id),
        )
        stage_row = cursor.fetchone()

        if stage_row is None:
            logger.error(
                f"[job_id={job_id}] stages 레코드 없음: {stage_id} — "
                f"content_jobs 생성 시 6개 stages가 함께 INSERT되어야 합니다."
            )
            raise RuntimeError(
                f"stages 레코드 없음: {stage_id} (job_id={job_id})"
            )

        stage: dict = dict(stage_row)

        # 이미 DONE/SKIPPED 상태이면 output_data를 그대로 반환 (재실행 방지)
        if stage["status"] in ("DONE", "SKIPPED"):
            logger.info(
                f"[job_id={job_id}] {stage_id} 이미 {stage['status']} — 건너뜀"
            )
            try:
                return json.loads(stage["output_data"] or "{}")
            except (json.JSONDecodeError, TypeError):
                return {"status": stage["status"]}

        # REJECTED: 사용자가 아직 재시도를 요청하지 않은 상태
        if stage["status"] == "REJECTED":
            logger.warning(
                f"[job_id={job_id}] {stage_id} REJECTED 상태 — 사용자 재시도 대기 중"
            )
            return {"rejected": True}

        # stages RUNNING 전환 + content_jobs current_stage 업데이트
        self._db_update(
            db_conn,
            (
                "UPDATE stages "
                "SET status = 'RUNNING', started_at = ? "
                "WHERE job_id = ? AND stage_id = ?"
            ),
            (now, job_id, stage_id),
        )
        self._db_update(
            db_conn,
            "UPDATE content_jobs SET current_stage = ? WHERE id = ?",
            (stage_id, job_id),
        )
        db_conn.commit()

        logger.info(f"[job_id={job_id}] {stage_id} RUNNING 전환 완료")

        # 스테이지 클래스 인스턴스화
        stage_class = _STAGE_CLASS_MAP.get(stage_id)
        if stage_class is None:
            raise RuntimeError(f"알 수 없는 stage_id: {stage_id}")

        stage_instance = stage_class()

        # ----------------------------------------------------------------
        # 입력 유효성 검증
        # ----------------------------------------------------------------
        input_validation = stage_instance.validate_input(input_data)
        if not input_validation.is_valid:
            logger.warning(
                f"[job_id={job_id}] {stage_id} 입력 검증 실패: "
                f"{input_validation.rejection_reason}"
            )
            target = input_validation.rejection_target or stage_id
            StageValidator.handle_rejection(
                db_conn, job_id, stage_id, target, input_validation.rejection_reason or ""
            )
            return {"rejected": True}

        # ----------------------------------------------------------------
        # 스테이지 실행
        # ----------------------------------------------------------------
        try:
            output_data: dict = stage_instance.execute(job_id, input_data)
        except Exception as e:
            logger.error(
                f"[job_id={job_id}] {stage_id} execute() 예외: {e}"
            )
            now = datetime.now(timezone.utc).isoformat()
            self._db_update(
                db_conn,
                (
                    "UPDATE stages "
                    "SET status = 'FAILED', finished_at = ?, rejection_reason = ? "
                    "WHERE job_id = ? AND stage_id = ?"
                ),
                (now, str(e)[:500], job_id, stage_id),
            )
            db_conn.commit()
            raise

        # ----------------------------------------------------------------
        # 출력 유효성 검증
        # ----------------------------------------------------------------
        output_validation = stage_instance.validate_output(output_data)
        if not output_validation.is_valid:
            logger.warning(
                f"[job_id={job_id}] {stage_id} 출력 검증 실패: "
                f"{output_validation.rejection_reason}"
            )
            target = output_validation.rejection_target or stage_id
            StageValidator.handle_rejection(
                db_conn, job_id, stage_id, target, output_validation.rejection_reason or ""
            )
            return {"rejected": True}

        # ----------------------------------------------------------------
        # 출력 DB 저장 + 상태 DONE/SKIPPED 업데이트
        # ----------------------------------------------------------------
        output_json: str = json.dumps(output_data, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        # 스테이지 status 결정 (SKIPPED인 경우 그대로 유지)
        final_stage_status = output_data.get("status", "DONE")
        if final_stage_status == "SKIPPED":
            db_final = "SKIPPED"
        elif final_stage_status == "COMPLETED":
            db_final = "DONE"
        else:
            db_final = "DONE"

        self._db_update(
            db_conn,
            (
                "UPDATE stages "
                "SET status = ?, output_data = ?, finished_at = ? "
                "WHERE job_id = ? AND stage_id = ?"
            ),
            (db_final, output_json, now, job_id, stage_id),
        )
        db_conn.commit()

        logger.info(
            f"[job_id={job_id}] {stage_id} 완료 — DB 상태: {db_final}"
        )
        return output_data

    # ------------------------------------------------------------------
    # 스테이지 입력 구성 메서드
    # ------------------------------------------------------------------

    def _get_stage_input(
        self,
        db_conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
        initial_params: dict,
        prev_output: dict,
    ) -> dict:
        """스테이지별 입력 데이터 구성.

        STAGE_01: initial_params 그대로.
        STAGE_02: prev_output(STAGE_01) + selected_topic (DB 최신 STAGE_01 output_data 우선).
        STAGE_03: STAGE_02 output_data + tts_provider, tts_skip.
        STAGE_04: STAGE_02 output_data(scenes) + generation_backend, skip_mode.
        STAGE_05: STAGE_03/STAGE_04 output_data 조합 (_handle_skip_chain 활용).
        STAGE_06: STAGE_02/STAGE_05 output_data + upload_mode, privacy.

        Args:
            db_conn: sqlite3 커넥션
            job_id: content_jobs.id
            stage_id: 이 스테이지의 ID
            initial_params: content_jobs.initial_params JSON 파싱 결과
            prev_output: 바로 이전 스테이지의 output_data

        Returns:
            이 스테이지에 전달할 입력 딕셔너리
        """
        if stage_id == "STAGE_01_RESEARCH":
            return {**initial_params}

        if stage_id == "STAGE_02_SCRIPT":
            # STAGE_01 output_data에서 selected_topic 읽기
            # selected_topic이 없으면 None으로 전달 → validate_input이 REJECTED 처리
            # (RuntimeError를 올리면 job이 FAILED가 되므로 여기서는 raise 금지)
            stage01_output = self._get_stage_output(db_conn, job_id, "STAGE_01_RESEARCH")
            return {
                **initial_params,
                **stage01_output,
                "selected_topic": stage01_output.get("selected_topic"),
            }

        if stage_id == "STAGE_03_TTS":
            stage02_output = self._get_stage_output(db_conn, job_id, "STAGE_02_SCRIPT")
            return {
                **initial_params,
                **stage02_output,
                "tts_provider": initial_params.get("tts_provider", "edge_tts"),
                "tts_voice": initial_params.get("tts_voice") or "",
                "tts_rate": initial_params.get("tts_rate") or "+0%",
                "tts_pitch": initial_params.get("tts_pitch") or "+0Hz",
                "tts_skip": initial_params.get("tts_skip", False),
            }

        if stage_id == "STAGE_04_VIDEO_GEN":
            stage02_output = self._get_stage_output(db_conn, job_id, "STAGE_02_SCRIPT")
            return {
                **initial_params,
                "scenes": stage02_output.get("scenes", []),
                "generation_backend": initial_params.get("generation_backend", "comfyui"),
                "skip_mode": initial_params.get("skip_mode"),
            }

        if stage_id == "STAGE_05_EDIT":
            return self._handle_skip_chain(db_conn, job_id)

        if stage_id == "STAGE_06_UPLOAD":
            stage02_output = self._get_stage_output(db_conn, job_id, "STAGE_02_SCRIPT")
            stage05_output = self._get_stage_output(db_conn, job_id, "STAGE_05_EDIT")
            return {
                **initial_params,
                "script": stage02_output.get("script", {}),
                "selected_topic": stage02_output.get("selected_topic", ""),
                "video_file_path": stage05_output.get("video_file_path"),
                "upload_mode": initial_params.get("upload_mode", "manual_approval"),
                "privacy": initial_params.get("privacy", "private"),
            }

        # 기본값: prev_output + initial_params 합성
        return {**initial_params, **prev_output}

    def _handle_skip_chain(
        self,
        db_conn: sqlite3.Connection,
        job_id: int,
    ) -> dict:
        """STAGE_03/STAGE_04 output_data를 읽어 STAGE_05 입력을 구성.

        skip 체인 규칙:
          STAGE_04 SKIPPED(script_only) → stage05_auto_skipped=True
          STAGE_04 SKIPPED(text_slide) → clips = 텍스트 슬라이드 경로들
          STAGE_03 SKIPPED → audio_file_path = None (BGM 전용 모드)

        Args:
            db_conn: sqlite3 커넥션
            job_id: content_jobs.id

        Returns:
            STAGE_05 execute()에 전달할 입력 딕셔너리
        """
        stage03_output = self._get_stage_output(db_conn, job_id, "STAGE_03_TTS")
        stage04_output = self._get_stage_output(db_conn, job_id, "STAGE_04_VIDEO_GEN")

        stage04_status: str = stage04_output.get("status", "COMPLETED")
        stage04_skip_mode: Optional[str] = stage04_output.get("skip_mode")

        # STAGE_04 script_only skip → STAGE_05 자동 SKIPPED
        if stage04_status == "SKIPPED" and stage04_skip_mode == "script_only":
            logger.info(
                f"[job_id={job_id}] STAGE_04 script_only skip → STAGE_05 자동 SKIPPED"
            )
            return {"stage05_auto_skipped": True}

        # STAGE_03 TTS 오디오 경로 결정
        audio_file_path: Optional[str] = None
        if stage03_output.get("status") != "SKIPPED":
            audio_file_path = stage03_output.get("audio_file_path")

        # 클립 목록 결정
        clips: list[dict] = stage04_output.get("clips", [])

        # STAGE_03에서 생성된 SRT 자막 파일 경로 전달
        srt_file_path: Optional[str] = stage03_output.get("srt_file_path")

        return {
            "clips": clips,
            "audio_file_path": audio_file_path,
            "srt_file_path": srt_file_path,
        }

    # ------------------------------------------------------------------
    # DB 헬퍼 메서드
    # ------------------------------------------------------------------

    def _get_stage_output(
        self,
        db_conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
    ) -> dict:
        """stages 테이블에서 특정 스테이지의 output_data를 JSON 파싱하여 반환.

        스테이지 레코드가 없거나 output_data가 비어 있으면 빈 딕셔너리를 반환한다.

        Args:
            db_conn: sqlite3 커넥션
            job_id: content_jobs.id
            stage_id: 조회할 스테이지 ID

        Returns:
            output_data 딕셔너리 (없으면 {})
        """
        try:
            cursor = db_conn.execute(
                "SELECT output_data FROM stages WHERE job_id = ? AND stage_id = ?",
                (job_id, stage_id),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(
                f"[job_id={job_id}] {stage_id} output_data 조회 실패: {e}"
            )
        return {}

    def _db_update(
        self,
        db_conn: sqlite3.Connection,
        sql: str,
        params: tuple,
    ) -> None:
        """공통 DB 업데이트 헬퍼.

        execute 후 commit은 호출자가 별도로 처리한다.
        (여러 업데이트를 배치로 처리 후 한 번에 commit하기 위해 분리)

        Args:
            db_conn: sqlite3 커넥션
            sql: UPDATE/INSERT SQL 문
            params: SQL 파라미터 튜플
        """
        try:
            db_conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"DB 업데이트 실패 — SQL: {sql[:80]}, 오류: {e}")
            raise
