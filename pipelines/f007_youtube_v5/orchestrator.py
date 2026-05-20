# pipelines/f007_youtube_v5/orchestrator.py
# 목적: F007 6스테이지 오케스트레이터 - channel_type(finance/language) 분기 지원
# BasePipeline 상속으로 call_ollama, call_searxng 유틸 재사용.
# content_jobs + stages 테이블 기반 동기 sqlite3 사용.

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

# DB 경로 - orchestrator.py 기준 세 단계 상위가 프로젝트 루트
DB_PATH: str = str(Path(__file__).parent.parent.parent / "storage" / "dash.db")

# 스테이지 실행 순서 - (stage_id, stage_order) 쌍
STAGE_SEQUENCE: list[tuple[str, int]] = [
    ("STAGE_01_TOPIC",  1),
    ("STAGE_02_SCRIPT", 2),
    ("STAGE_03_TTS",    3),
    ("STAGE_04_VISUAL", 4),
    ("STAGE_05_VIDEO",  5),
    ("STAGE_06_UPLOAD", 6),
]


def _get_stage_classes() -> dict:
    """스테이지 클래스 지연 임포트 - 순환 참조 방지.

    Returns:
        {stage_id: StageClass} 딕셔너리
    """
    from pipelines.f007_youtube_v5.stages.stage01_topic import Stage01Topic
    from pipelines.f007_youtube_v5.stages.stage02_script import Stage02Script
    from pipelines.f007_youtube_v5.stages.stage03_tts import Stage03TTS
    from pipelines.f007_youtube_v5.stages.stage04_visual import Stage04Visual
    from pipelines.f007_youtube_v5.stages.stage05_video import Stage05Video
    from pipelines.f007_youtube_v5.stages.stage06_upload import Stage06Upload
    return {
        "STAGE_01_TOPIC":  Stage01Topic,
        "STAGE_02_SCRIPT": Stage02Script,
        "STAGE_03_TTS":    Stage03TTS,
        "STAGE_04_VISUAL": Stage04Visual,
        "STAGE_05_VIDEO":  Stage05Video,
        "STAGE_06_UPLOAD": Stage06Upload,
    }


class F007Orchestrator(BasePipeline):
    """F007 6스테이지 오케스트레이터.

    BasePipeline 상속으로 call_ollama(), call_searxng() 등 유틸 재사용.
    content_jobs + stages 테이블 기반 동기 sqlite3 사용.

    channel_type 분기:
      - "finance": 수치/데이터 중심, upload_mode 강제로 manual_approval
      - "language": 예문/대화 형식, 일반 upload_mode 적용

    실행 흐름:
      1. content_jobs WHERE id=job_id 로드
      2. initial_params JSON 파싱
      3. STAGE_SEQUENCE 순서대로 각 스테이지 실행
         - REJECTED 상태이면 루프 중단 (사용자 개입 대기 -> WAITING)
         - DONE이면 계속 진행
      4. 모든 스테이지 완료 후 upload_mode에 따라 최종 상태 업데이트
    """

    def get_metadata(self) -> dict:
        """F007 오케스트레이터 메타데이터."""
        return {
            "feature_id": "F007",
            "name": "F007 YouTube 자동화 파이프라인",
            "description": "6스테이지 유튜브 컨텐츠 제작 v5 (channel_type 분기: finance/language)",
            "input_schema": {},
            "supports_schedule": False,
        }

    def run(self, job_id: int, params: dict = None) -> dict:  # type: ignore[override]
        """6스테이지 파이프라인 실행 진입점.

        Args:
            job_id: content_jobs.id
            params: 사용되지 않음 (BasePipeline 추상 메서드 계약 충족용)

        Returns:
            {"status": "completed", "final_status": ...} 또는
            {"status": "waiting", "stage": ...}
        """
        logger.info(f"[F007Orchestrator] 시작 - job_id={job_id}")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 딕셔너리 형식 접근 가능

        try:
            # 1. content_jobs 로드 및 RUNNING 전환
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
            logger.info(f"[F007Orchestrator][job_id={job_id}] content_jobs RUNNING 전환")

            # 2. initial_params JSON 파싱
            try:
                initial_params: dict = json.loads(job.get("initial_params") or "{}")
            except (json.JSONDecodeError, TypeError):
                initial_params = {}

            # 3. 스테이지 순차 실행
            stage_classes = _get_stage_classes()
            prev_output: dict = {}

            for stage_id, stage_order in STAGE_SEQUENCE:
                logger.info(
                    f"[F007Orchestrator][job_id={job_id}] "
                    f"스테이지 시작: {stage_id} (order={stage_order})"
                )

                input_data = self._get_stage_input(
                    conn, job_id, stage_id, initial_params, prev_output
                )

                result = self._run_stage_by_id(
                    conn, job_id, stage_id, stage_order, input_data, stage_classes
                )

                # REJECTED: 사용자 개입 필요 -> WAITING 전환 후 정상 종료
                if result.get("rejected", False):
                    logger.warning(
                        f"[F007Orchestrator][job_id={job_id}] "
                        f"스테이지 {stage_id} REJECTED - 사용자 개입 대기"
                    )
                    self._db_update(
                        conn,
                        "UPDATE content_jobs SET status = 'WAITING' WHERE id = ?",
                        (job_id,),
                    )
                    conn.commit()
                    return {"status": "waiting", "stage": stage_id}

                prev_output = result

            # 4. 모든 스테이지 완료 - upload_mode 분기
            upload_mode: str = initial_params.get("upload_mode", "manual_approval")
            channel_type: str = initial_params.get("channel_type", "finance")

            # finance 채널은 upload_mode 강제로 manual_approval (투자 권유 방지)
            if channel_type == "finance":
                upload_mode = "manual_approval"

            if upload_mode in ("auto", "skip"):
                final_status = "DONE"
            else:
                final_status = "PENDING_APPROVAL"

            now = datetime.now(timezone.utc).isoformat()
            self._db_update(
                conn,
                "UPDATE content_jobs SET status = ?, finished_at = ? WHERE id = ?",
                (final_status, now, job_id),
            )
            conn.commit()
            logger.info(
                f"[F007Orchestrator][job_id={job_id}] 모든 스테이지 완료 - "
                f"최종 상태: {final_status}"
            )
            return {"status": "completed", "final_status": final_status}

        except Exception as e:
            logger.error(f"[F007Orchestrator][job_id={job_id}] 오케스트레이터 실패: {e}")
            now = datetime.now(timezone.utc).isoformat()
            try:
                self._db_update(
                    conn,
                    "UPDATE content_jobs SET status = 'FAILED', finished_at = ?, notes = ? WHERE id = ?",
                    (now, str(e)[:500], job_id),
                )
                conn.commit()
            except Exception as db_e:
                logger.error(f"[F007Orchestrator][job_id={job_id}] FAILED 업데이트 실패: {db_e}")
            raise

        finally:
            conn.close()

    def _get_stage_input(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
        initial_params: dict,
        prev_output: dict,
    ) -> dict:
        """스테이지별 입력 데이터 구성.

        channel_type을 모든 스테이지에 전파한다.
        각 스테이지는 이전 스테이지 출력을 DB에서 읽어 입력으로 사용한다.
        """
        # 모든 스테이지에 공통으로 전달할 채널 정보
        common: dict = {
            "channel_type": initial_params.get("channel_type", "finance"),
            "channel_name": initial_params.get("channel_name", ""),
        }

        if stage_id == "STAGE_01_TOPIC":
            # 초기 파라미터 그대로 전달 (channel_type, days, model 등 포함)
            return {**initial_params, **common}

        if stage_id == "STAGE_02_SCRIPT":
            # STAGE_01 출력에서 selected_topic, enriched_context 읽기
            s01 = self._get_stage_output(conn, job_id, "STAGE_01_TOPIC")
            return {
                **initial_params, **common,
                "selected_topic": s01.get("selected_topic"),
                "enriched_context": s01.get("enriched_context", ""),
                "search_context": s01.get("search_context", ""),
                "topics": s01.get("topics", []),
            }

        if stage_id == "STAGE_03_TTS":
            # STAGE_02 출력에서 script_text 읽기
            s02 = self._get_stage_output(conn, job_id, "STAGE_02_SCRIPT")
            return {
                **initial_params, **common,
                "script_text": s02.get("script_text", ""),
                "tts_provider": initial_params.get("tts_provider", "supertone3"),
                "tts_voice": initial_params.get("tts_voice", "F1"),
                "tts_skip": initial_params.get("tts_skip", False),
            }

        if stage_id == "STAGE_04_VISUAL":
            # STAGE_02 출력에서 slides, selected_topic 읽기
            s02 = self._get_stage_output(conn, job_id, "STAGE_02_SCRIPT")
            return {
                **initial_params, **common,
                "slides": s02.get("slides", []),
                "selected_topic": s02.get("selected_topic", ""),
                "slide_theme": initial_params.get("slide_theme", "dark_blue"),
                "render_mode": initial_params.get("render_mode", "slide"),
            }

        if stage_id == "STAGE_05_VIDEO":
            # STAGE_03(오디오), STAGE_04(클립) 출력 합성
            s03 = self._get_stage_output(conn, job_id, "STAGE_03_TTS")
            s04 = self._get_stage_output(conn, job_id, "STAGE_04_VISUAL")
            return {
                **common,
                "clips": s04.get("clips", []),
                "audio_file_path": s03.get("audio_file_path"),
                "srt_file_path": s03.get("srt_file_path"),
                "duration_sec": s03.get("duration_sec", 0),
                "bgm_path": initial_params.get("bgm_path", "random"),
                "bgm_volume": initial_params.get("bgm_volume", 0.15),
            }

        if stage_id == "STAGE_06_UPLOAD":
            # STAGE_02(스크립트), STAGE_04(썸네일), STAGE_05(영상) 출력 합성
            s02 = self._get_stage_output(conn, job_id, "STAGE_02_SCRIPT")
            s04 = self._get_stage_output(conn, job_id, "STAGE_04_VISUAL")
            s05 = self._get_stage_output(conn, job_id, "STAGE_05_VIDEO")
            return {
                **initial_params, **common,
                "script_text": s02.get("script_text", ""),
                "selected_topic": s02.get("selected_topic", ""),
                "thumbnail_path": s04.get("thumbnail_path"),
                "video_file_path": s05.get("video_file_path"),
                "upload_mode": initial_params.get("upload_mode", "manual_approval"),
                "privacy": initial_params.get("privacy", "private"),
            }

        # 알 수 없는 stage_id: prev_output + initial_params 합성
        return {**initial_params, **common, **prev_output}

    def _run_stage_by_id(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
        stage_order: int,
        input_data: dict,
        stage_classes: dict,
    ) -> dict:
        """단일 스테이지 실행 + DB 상태 관리.

        처리 흐름:
          1. stages 레코드 조회 (DONE이면 스킵, REJECTED이면 반송 신호 반환)
          2. validate_input -> RUNNING 전환 -> execute -> validate_output
          3. 결과를 stages output_data에 저장, status=DONE

        Returns:
            스테이지 output_data 딕셔너리
            {"rejected": True}: 반송 발생 시
        """
        from pipelines.f007_youtube_v5.validators.stage_validator import StageValidator

        now: str = datetime.now(timezone.utc).isoformat()

        # stages 레코드 조회
        cursor = conn.execute(
            "SELECT * FROM stages WHERE job_id = ? AND stage_id = ?",
            (job_id, stage_id),
        )
        stage_row = cursor.fetchone()

        if stage_row is None:
            logger.error(
                f"[F007][job_id={job_id}] stages 레코드 없음: {stage_id} - "
                f"content_jobs 생성 시 6개 stages가 함께 INSERT되어야 합니다."
            )
            raise RuntimeError(f"stages 레코드 없음: {stage_id} (job_id={job_id})")

        stage: dict = dict(stage_row)

        # 이미 DONE/SKIPPED 상태이면 output_data 그대로 반환 (재실행 방지)
        if stage["status"] in ("DONE", "SKIPPED"):
            logger.info(
                f"[F007][job_id={job_id}] {stage_id} 이미 {stage['status']} - 건너뜀"
            )
            try:
                return json.loads(stage["output_data"] or "{}")
            except (json.JSONDecodeError, TypeError):
                return {"status": stage["status"]}

        # REJECTED 상태이면 사용자 재시도 대기
        if stage["status"] == "REJECTED":
            logger.warning(
                f"[F007][job_id={job_id}] {stage_id} REJECTED 상태 - 사용자 재시도 대기 중"
            )
            return {"rejected": True}

        # 스테이지 클래스 인스턴스화
        StageClass = stage_classes.get(stage_id)
        if StageClass is None:
            raise RuntimeError(f"알 수 없는 stage_id: {stage_id}")

        stage_instance = StageClass()

        # 입력 유효성 검증
        input_validation = stage_instance.validate_input(input_data)
        if not input_validation.is_valid:
            logger.warning(
                f"[F007][job_id={job_id}] {stage_id} 입력 검증 실패: "
                f"{input_validation.rejection_reason}"
            )
            StageValidator.handle_rejection(conn, job_id, stage_id, input_validation)
            return {"rejected": True}

        # stages RUNNING 전환 + content_jobs current_stage 업데이트
        self._db_update(
            conn,
            "UPDATE stages SET status = 'RUNNING', started_at = ? WHERE job_id = ? AND stage_id = ?",
            (now, job_id, stage_id),
        )
        self._db_update(
            conn,
            "UPDATE content_jobs SET current_stage = ? WHERE id = ?",
            (stage_id, job_id),
        )
        conn.commit()

        logger.info(f"[F007][job_id={job_id}] {stage_id} RUNNING 전환 완료")

        # 스테이지 실행
        try:
            output_data: dict = stage_instance.execute(job_id, input_data)
        except Exception as e:
            logger.error(f"[F007][job_id={job_id}] {stage_id} execute() 예외: {e}")
            now = datetime.now(timezone.utc).isoformat()
            self._db_update(
                conn,
                "UPDATE stages SET status = 'FAILED', finished_at = ?, rejection_reason = ? "
                "WHERE job_id = ? AND stage_id = ?",
                (now, str(e)[:500], job_id, stage_id),
            )
            conn.commit()
            raise

        # 출력 유효성 검증
        output_validation = stage_instance.validate_output(output_data)
        if not output_validation.is_valid:
            logger.warning(
                f"[F007][job_id={job_id}] {stage_id} 출력 검증 실패: "
                f"{output_validation.rejection_reason}"
            )
            StageValidator.handle_rejection(conn, job_id, stage_id, output_validation)
            return {"rejected": True}

        # 출력 DB 저장 + 상태 DONE 업데이트
        output_json: str = json.dumps(output_data, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()

        # STAGE_06이 PENDING_APPROVAL 상태이면 stages도 PENDING_APPROVAL로 저장
        output_status = output_data.get("status", "COMPLETED")
        upload_status = output_data.get("upload_status", "")
        if stage_id == "STAGE_06_UPLOAD" and upload_status == "PENDING_APPROVAL":
            db_final = "PENDING_APPROVAL"
        elif output_status == "SKIPPED":
            db_final = "SKIPPED"
        else:
            db_final = "DONE"

        self._db_update(
            conn,
            "UPDATE stages SET status = ?, output_data = ?, finished_at = ? "
            "WHERE job_id = ? AND stage_id = ?",
            (db_final, output_json, now, job_id, stage_id),
        )
        conn.commit()

        logger.info(f"[F007][job_id={job_id}] {stage_id} 완료 - DB 상태: {db_final}")
        return output_data

    def _get_stage_output(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        stage_id: str,
    ) -> dict:
        """stages 테이블에서 특정 스테이지의 output_data를 JSON 파싱하여 반환.

        스테이지 레코드가 없거나 output_data가 비어 있으면 빈 딕셔너리를 반환한다.
        """
        try:
            cursor = conn.execute(
                "SELECT output_data FROM stages WHERE job_id = ? AND stage_id = ?",
                (job_id, stage_id),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.warning(f"[F007][job_id={job_id}] {stage_id} output_data 조회 실패: {e}")
        return {}

    def _db_update(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params: tuple,
    ) -> None:
        """공통 DB 업데이트 헬퍼 - commit은 호출자가 처리한다."""
        try:
            conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"[F007] DB 업데이트 실패 - SQL: {sql[:80]}, 오류: {e}")
            raise
