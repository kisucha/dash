# 목적: ComfyUI 모델 로컬 인벤토리 관리 및 CivitAI/HuggingFace 다운로드 처리
import sys
import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional

import httpx

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)

# SQLite DB 경로 (동기 sqlite3 사용)
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"

# CivitAI REST API 기본 URL
CIVITAI_API_BASE = "https://civitai.com"


class ModelManager:
    """ComfyUI 모델 인벤토리 관리 및 다운로드 처리 클래스.

    scan_local_models: 로컬 파일 스캔 후 DB 갱신
    is_model_available: DB + 파일 시스템 이중 확인
    ensure_models: 누락 모델 다운로드 + ComfyUI 재시작
    download_from_civitai: CivitAI 스트리밍 다운로드
    download_from_hf: HuggingFace Hub 다운로드
    """

    def __init__(self, comfyui_path: str = r"C:\ComfyUI"):
        # ComfyUI 설치 루트 경로
        self.comfyui_path = Path(comfyui_path)
        # ComfyUI 모델 타입별 서브디렉토리 매핑
        self._model_dirs = {
            "checkpoint": self.comfyui_path / "models" / "checkpoints",
            "lora": self.comfyui_path / "models" / "loras",
            "motion_module": self.comfyui_path / "models" / "animatediff_models",
            "vae": self.comfyui_path / "models" / "vae",
            "clip": self.comfyui_path / "models" / "clip",
            "diffusion_model": self.comfyui_path / "models" / "diffusion_models",
        }

    def _get_db(self) -> sqlite3.Connection:
        """DB 연결을 반환한다. Row 결과를 dict처럼 접근할 수 있게 row_factory를 설정한다."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def scan_local_models(self) -> int:
        """ComfyUI/models/ 디렉토리를 재귀 스캔하여 model_inventory DB를 갱신한다.

        ON CONFLICT(filename) 지원 여부에 따라 UPSERT 또는 SELECT+UPDATE 방식을 사용한다.

        Returns:
            갱신(삽입 또는 업데이트)된 모델 파일 수
        """
        # 처리 대상 확장자 집합
        valid_exts = {".safetensors", ".ckpt", ".pt", ".bin"}
        count = 0
        conn = self._get_db()
        try:
            for model_type, dir_path in self._model_dirs.items():
                if not dir_path.exists():
                    continue
                for file_path in dir_path.rglob("*"):
                    if file_path.suffix.lower() not in valid_exts:
                        continue
                    filename = file_path.name
                    local_path = str(file_path)
                    file_size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
                    try:
                        conn.execute(
                            """
                            INSERT INTO model_inventory
                                (model_type, name, filename, local_path, is_downloaded, file_size_mb)
                            VALUES (?, ?, ?, ?, 1, ?)
                            ON CONFLICT(filename) DO UPDATE SET
                                local_path = excluded.local_path,
                                is_downloaded = 1,
                                file_size_mb = excluded.file_size_mb
                            """,
                            (model_type, filename, filename, local_path, file_size_mb),
                        )
                    except sqlite3.OperationalError:
                        # ON CONFLICT 미지원 버전 대비 fallback
                        existing = conn.execute(
                            "SELECT id FROM model_inventory WHERE filename = ?", (filename,)
                        ).fetchone()
                        if existing:
                            conn.execute(
                                "UPDATE model_inventory SET local_path=?, is_downloaded=1, file_size_mb=? WHERE filename=?",
                                (local_path, file_size_mb, filename),
                            )
                        else:
                            conn.execute(
                                "INSERT INTO model_inventory (model_type, name, filename, local_path, is_downloaded, file_size_mb) VALUES (?,?,?,?,1,?)",
                                (model_type, filename, filename, local_path, file_size_mb),
                            )
                    count += 1
            conn.commit()
        finally:
            conn.close()
        logger.info(f"로컬 모델 스캔 완료: {count}개 갱신")
        return count

    def is_model_available(self, filename: str, model_type: Optional[str] = None) -> bool:
        """DB 조회 + 파일 시스템 확인으로 모델 사용 가능 여부를 판단한다.

        Args:
            filename: 모델 파일명 (예: 'anime_art_diffusion_xl.safetensors')
            model_type: 모델 타입 필터 (None이면 타입 구분 없이 조회)

        Returns:
            DB에 is_downloaded=1이고 파일이 실제로 존재하면 True
        """
        conn = self._get_db()
        try:
            if model_type:
                row = conn.execute(
                    "SELECT local_path, is_downloaded FROM model_inventory WHERE filename = ? AND model_type = ?",
                    (filename, model_type),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT local_path, is_downloaded FROM model_inventory WHERE filename = ?",
                    (filename,),
                ).fetchone()
        finally:
            conn.close()

        if not row or not row["is_downloaded"]:
            return False
        return Path(row["local_path"]).exists()

    def ensure_models(
        self,
        required_models: list[dict],
        comfyui_client,
        manager_url: Optional[str] = None,
    ) -> bool:
        """필요한 모델이 없으면 다운로드하고 ComfyUI를 재시작한다.

        Args:
            required_models: 필요한 모델 목록
                각 항목: {"filename": str, "model_type": str, "source": str, "source_id": str}
                source 값: "civitai" 또는 "huggingface"
            comfyui_client: ComfyUIClient 인스턴스 (reboot, wait_for_ready 메서드 보유)
            manager_url: ComfyUI Manager URL (None이면 기본값 사용)

        Returns:
            모든 모델이 준비되면 True, 하나라도 실패하면 False
        """
        # 누락된 모델만 선별
        missing = [
            m for m in required_models
            if not self.is_model_available(m["filename"], m.get("model_type"))
        ]

        if not missing:
            logger.info("필요한 모든 모델이 이미 준비됨")
            return True

        logger.info(f"누락된 모델 {len(missing)}개 다운로드 시작")
        all_ok = True

        for m in missing:
            source = m.get("source", "")
            model_type = m.get("model_type", "checkpoint")
            target_dir = self._model_dirs.get(model_type, self.comfyui_path / "models" / "checkpoints")
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                if source == "civitai":
                    target_path = target_dir / m["filename"]
                    self.download_from_civitai(
                        version_id=int(m["source_id"]),
                        model_type=model_type,
                        target_path=str(target_path),
                    )
                elif source == "huggingface":
                    self.download_from_hf(
                        repo_id=m["source_id"],
                        filename=m["filename"],
                        local_dir=str(target_dir),
                    )
                else:
                    logger.warning(f"알 수 없는 다운로드 소스: {source} - {m['filename']} 건너뜀")
                    all_ok = False
                    continue
            except Exception as e:
                logger.error(f"모델 다운로드 실패: {m['filename']} - {e}")
                all_ok = False

        # 다운로드 후 ComfyUI 재시작 및 준비 대기
        if missing and all_ok:
            logger.info("모델 추가 완료 - ComfyUI 재시작 중...")
            comfyui_client.reboot(manager_url)
            ready = comfyui_client.wait_for_ready()
            if not ready:
                logger.error("ComfyUI 재시작 타임아웃")
                return False
            # 재시작 후 DB 인벤토리 갱신
            self.scan_local_models()

        return all_ok

    def _enqueue_download(self, source: str, model_type: str, source_id: str, target_path: str) -> int:
        """model_download_queue에 다운로드 항목을 추가하고 새 행의 ID를 반환한다."""
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "INSERT INTO model_download_queue (source, model_type, source_id, target_path, status) VALUES (?,?,?,?,'QUEUED')",
                (source, model_type, source_id, target_path),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def _update_download_queue(
        self,
        queue_id: int,
        status: str,
        progress: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """model_download_queue 항목의 상태와 진행률을 업데이트한다.

        완료/실패 시에는 finished_at도 함께 기록한다.
        """
        conn = self._get_db()
        try:
            if status in ("DONE", "FAILED"):
                conn.execute(
                    "UPDATE model_download_queue SET status=?, progress_pct=?, error_message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                    (status, progress, error, queue_id),
                )
            else:
                conn.execute(
                    "UPDATE model_download_queue SET status=?, progress_pct=? WHERE id=?",
                    (status, progress, queue_id),
                )
            conn.commit()
        finally:
            conn.close()

    def download_from_civitai(
        self,
        version_id: int,
        model_type: str,
        target_path: str,
        civitai_api_key: Optional[str] = None,
    ) -> None:
        """CivitAI에서 모델을 스트리밍 다운로드한다.

        1MB 청크 단위로 읽어 파일에 기록하며, 진행률을 DB에 주기적으로 업데이트한다.

        Args:
            version_id: CivitAI 모델 버전 ID
            model_type: 모델 타입 (DB 기록용)
            target_path: 저장할 파일 경로
            civitai_api_key: API 키 (None이면 환경변수 CIVITAI_API_KEY 사용)
        """
        queue_id = self._enqueue_download("civitai", model_type, str(version_id), target_path)
        download_url = f"{CIVITAI_API_BASE}/api/download/models/{version_id}"

        # API 키 헤더 설정
        headers = {}
        api_key = civitai_api_key or os.getenv("CIVITAI_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            self._update_download_queue(queue_id, "DOWNLOADING", 0.0)
            with httpx.Client(timeout=None, follow_redirects=True) as client:
                with client.stream("GET", download_url, headers=headers) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = round(downloaded / total * 100, 1)
                                self._update_download_queue(queue_id, "DOWNLOADING", pct)
            self._update_download_queue(queue_id, "DONE", 100.0)
            # 인벤토리 DB에 등록
            self._register_downloaded_model(model_type, Path(target_path).name, target_path)
            logger.info(f"CivitAI 다운로드 완료: {target_path}")
        except Exception as e:
            self._update_download_queue(queue_id, "FAILED", 0.0, str(e))
            raise

    def download_from_hf(self, repo_id: str, filename: str, local_dir: str, model_type: str = "checkpoint") -> str:
        """HuggingFace Hub에서 모델을 다운로드한다.

        huggingface_hub 패키지가 설치되어 있어야 한다.
        환경변수 HF_TOKEN이 있으면 비공개 저장소에도 접근 가능하다.

        Args:
            repo_id: HuggingFace 저장소 ID (예: 'black-forest-labs/FLUX.1-dev')
            filename: 저장소 내 파일명
            local_dir: 로컬 저장 디렉토리

        Returns:
            다운로드된 파일의 로컬 절대 경로
        """
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise RuntimeError("huggingface_hub 패키지 미설치. pip install huggingface-hub 실행 필요")

        hf_token = os.getenv("HF_TOKEN")
        queue_id = self._enqueue_download("huggingface", model_type, repo_id, f"{local_dir}/{filename}")
        try:
            self._update_download_queue(queue_id, "DOWNLOADING", 0.0)
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                token=hf_token,
            )
            self._update_download_queue(queue_id, "DONE", 100.0)
            self._register_downloaded_model(model_type, filename, local_path, hf_repo_id=repo_id)
            logger.info(f"HuggingFace 다운로드 완료: {local_path}")
            return local_path
        except Exception as e:
            self._update_download_queue(queue_id, "FAILED", 0.0, str(e))
            raise

    def _register_downloaded_model(
        self,
        model_type: str,
        filename: str,
        local_path: str,
        hf_repo_id: Optional[str] = None,
    ) -> None:
        """다운로드 완료된 모델을 model_inventory에 등록하거나 기존 행을 갱신한다."""
        file_size_mb = 0.0
        if Path(local_path).exists():
            file_size_mb = round(Path(local_path).stat().st_size / (1024 * 1024), 2)

        conn = self._get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM model_inventory WHERE filename = ?", (filename,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE model_inventory SET local_path=?, is_downloaded=1, file_size_mb=?, downloaded_at=CURRENT_TIMESTAMP WHERE filename=?",
                    (local_path, file_size_mb, filename),
                )
            else:
                conn.execute(
                    "INSERT INTO model_inventory (model_type, name, filename, local_path, hf_repo_id, is_downloaded, file_size_mb, downloaded_at) VALUES (?,?,?,?,?,1,?,CURRENT_TIMESTAMP)",
                    (model_type, filename, filename, local_path, hf_repo_id, file_size_mb),
                )
            conn.commit()
        finally:
            conn.close()
