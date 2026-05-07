# 목적: ComfyUI REST API + WebSocket 클라이언트 -- 워크플로우 제출, 완료 감지, 결과 다운로드
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import uuid
import time
import logging
from typing import Optional, Callable

import httpx

logger = logging.getLogger(__name__)

# ComfyUI 기본 엔드포인트
COMFYUI_BASE_URL = "http://localhost:8188"


class ComfyUIClient:
    """ComfyUI REST + WebSocket API 클라이언트 (동기).

    주요 기능:
    - 워크플로우 JSON 제출 (/prompt)
    - WebSocket으로 실행 완료 감지 (/ws)
    - 출력 파일 목록 조회 및 다운로드 (/history, /view)
    - 체크포인트/LoRA 모델 목록 조회 (/object_info)
    """

    def __init__(self, base_url: str = COMFYUI_BASE_URL):
        # base_url: ComfyUI REST API 기본 주소
        self.base_url = base_url.rstrip("/")
        # ws_url: WebSocket 연결용 주소 (http -> ws 변환)
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")

    def health_check(self) -> bool:
        """ComfyUI 서버 헬스체크 -- /system_stats 200 응답 확인.

        Returns:
            서버 정상 응답 시 True, 실패 시 False
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.base_url}/system_stats")
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"ComfyUI 헬스체크 실패: {e}")
            return False

    def get_object_info(self) -> dict:
        """ComfyUI 노드 타입 및 파라미터 정보 조회.

        Returns:
            노드 클래스명 -> 입력 파라미터 정보 dict
        """
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{self.base_url}/object_info")
            resp.raise_for_status()
            return resp.json()

    def get_available_checkpoints(self) -> list:
        """로드된 체크포인트 모델 목록 반환.

        Returns:
            체크포인트 파일명 문자열 리스트
        """
        try:
            info = self.get_object_info()
            # CheckpointLoaderSimple 노드의 ckpt_name 파라미터에서 목록 추출
            loader_info = info.get("CheckpointLoaderSimple", {})
            inputs = loader_info.get("input", {}).get("required", {})
            ckpt_info = inputs.get("ckpt_name", [])
            if ckpt_info and isinstance(ckpt_info[0], list):
                return ckpt_info[0]
            return []
        except Exception as e:
            logger.error(f"체크포인트 목록 조회 실패: {e}")
            return []

    def get_available_loras(self) -> list:
        """로드된 LoRA 모델 목록 반환.

        Returns:
            LoRA 파일명 문자열 리스트
        """
        try:
            info = self.get_object_info()
            # LoraLoader 노드의 lora_name 파라미터에서 목록 추출
            loader_info = info.get("LoraLoader", {})
            inputs = loader_info.get("input", {}).get("required", {})
            lora_info = inputs.get("lora_name", [])
            if lora_info and isinstance(lora_info[0], list):
                return lora_info[0]
            return []
        except Exception as e:
            logger.error(f"LoRA 목록 조회 실패: {e}")
            return []

    def submit_workflow(self, workflow_dict: dict) -> str:
        """워크플로우 JSON을 ComfyUI에 제출하고 prompt_id를 반환한다.

        Args:
            workflow_dict: ComfyUI API 포맷 워크플로우 dict (노드 ID -> 노드 정의)

        Returns:
            ComfyUI가 발급한 prompt_id 문자열

        Raises:
            RuntimeError: prompt_id 없이 응답하거나 HTTP 오류 시
        """
        payload = {"prompt": workflow_dict}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.base_url}/prompt", json=payload)
            resp.raise_for_status()
            data = resp.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI 워크플로우 제출 실패: prompt_id 없음 -- {data}")
            logger.info(f"워크플로우 제출 완료: prompt_id={prompt_id}")
            return prompt_id

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout: int = 600,
        cancel_check_fn: Optional[Callable] = None,
        task_id: Optional[int] = None,
    ) -> None:
        """WebSocket으로 ComfyUI 실행 완료를 감지한다.

        ComfyUI WebSocket에서 수신하는 메시지 유형:
        - "executed": 특정 프롬프트 실행 완료
        - "execution_error": 실행 중 오류 발생
        - "execution_cached": 캐시된 결과 사용 (완료로 간주)

        Args:
            prompt_id: 완료를 기다릴 프롬프트 ID
            timeout: 전체 타임아웃 초 (기본 600초 = 10분)
            cancel_check_fn: task_id를 받아 취소 여부를 bool로 반환하는 함수
            task_id: cancel_check_fn에 전달할 작업 ID

        Raises:
            RuntimeError: websocket-client 미설치 또는 ComfyUI 실행 오류 시
            TimeoutError: timeout 초과 시
        """
        try:
            import websocket
        except ImportError:
            raise RuntimeError("websocket-client 패키지가 설치되지 않음. pip install websocket-client")

        # 고유 클라이언트 ID로 WebSocket 연결
        client_id = str(uuid.uuid4())
        ws_endpoint = f"{self.ws_url}/ws?clientId={client_id}"
        start_time = time.time()

        logger.info(f"WebSocket 연결 시작: {ws_endpoint}")
        ws = websocket.create_connection(ws_endpoint, timeout=30)
        try:
            # 5초 recv 타임아웃 -- 취소 감지 루프를 위한 짧은 단위 폴링
            ws.settimeout(5.0)
            while True:
                # 전체 타임아웃 검사
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"ComfyUI 실행 타임아웃: {timeout}초 초과")

                # 외부 취소 신호 감지 — GPU 점유 해제를 위해 ComfyUI에 /interrupt 전송
                if cancel_check_fn and task_id is not None:
                    if cancel_check_fn(task_id):
                        logger.info(f"[task_id={task_id}] 취소 감지 -- ComfyUI /interrupt 전송")
                        try:
                            with httpx.Client(timeout=5.0) as hx:
                                hx.post(f"{self.base_url}/interrupt")
                        except Exception as ie:
                            logger.warning(f"ComfyUI /interrupt 전송 실패 (무시): {ie}")
                        return

                try:
                    raw = ws.recv()
                except Exception:
                    # recv 타임아웃(5초) 발생 시 다음 루프로 진행
                    continue

                # 바이너리 메시지(프리뷰 이미지 등)는 건너뜀
                if not isinstance(raw, str):
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                # 실행 완료 감지
                if msg_type == "executed" and data.get("prompt_id") == prompt_id:
                    logger.info(f"ComfyUI 실행 완료: prompt_id={prompt_id}")
                    return

                # 실행 오류 감지
                if msg_type == "execution_error" and data.get("prompt_id") == prompt_id:
                    error_msg = data.get("exception_message", "알 수 없는 오류")
                    raise RuntimeError(f"ComfyUI 실행 오류: {error_msg}")

                # 캐시된 결과 사용 (완료로 간주)
                if msg_type == "execution_cached" and data.get("prompt_id") == prompt_id:
                    logger.info(f"ComfyUI 캐시된 결과 사용: prompt_id={prompt_id}")
                    return

        finally:
            # 연결 종료는 항상 보장
            try:
                ws.close()
            except Exception:
                pass

    def get_history(self, prompt_id: str) -> dict:
        """실행 결과 및 출력 파일명 조회.

        Args:
            prompt_id: 조회할 프롬프트 ID

        Returns:
            해당 prompt_id의 history dict (outputs, status 등 포함)
        """
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{self.base_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()
            # 전체 history에서 해당 prompt_id 데이터만 추출
            return history.get(prompt_id, {})

    def get_output_files(self, prompt_id: str) -> list:
        """history에서 출력 파일 목록을 추출한다.

        images, gifs, videos 키를 모두 탐색하여 반환.

        Returns:
            [{"filename": str, "subfolder": str, "type": str}, ...]
        """
        history = self.get_history(prompt_id)
        # outputs: {노드ID: {images/gifs/videos: [{filename, subfolder, type}, ...]}}
        outputs = history.get("outputs", {})
        files = []
        for node_id, node_output in outputs.items():
            for key in ("images", "gifs", "videos"):
                for file_info in node_output.get(key, []):
                    files.append({
                        "filename": file_info.get("filename", ""),
                        "subfolder": file_info.get("subfolder", ""),
                        "type": file_info.get("type", "output"),
                    })
        return files

    def download_output(self, filename: str, subfolder: str = "", file_type: str = "output") -> bytes:
        """ComfyUI 출력 파일을 다운로드하여 바이트로 반환한다.

        Args:
            filename: 다운로드할 파일명
            subfolder: ComfyUI output 내 하위 폴더 경로
            file_type: "output" (기본) 또는 "temp"

        Returns:
            파일 바이트 데이터
        """
        params = {"filename": filename, "subfolder": subfolder, "type": file_type}
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(f"{self.base_url}/view", params=params)
            resp.raise_for_status()
            logger.info(f"출력 파일 다운로드 완료: {filename} ({len(resp.content)} bytes)")
            return resp.content

    def reboot(self, manager_url: Optional[str] = None) -> None:
        """ComfyUI 서버를 재시작한다 (ComfyUI-Manager 필요).

        Args:
            manager_url: ComfyUI-Manager 주소 (None이면 base_url 사용)
        """
        url = (manager_url or self.base_url).rstrip("/")
        with httpx.Client(timeout=10.0) as client:
            try:
                client.post(f"{url}/manager/reboot")
            except Exception:
                # 재시작 요청 직후 연결 끊김은 정상 동작
                pass
        logger.info("ComfyUI 재시작 요청 완료")

    def wait_for_ready(self, timeout: int = 120, poll_interval: int = 5) -> bool:
        """ComfyUI 재시작 완료를 폴링으로 기다린다.

        재시작 직후 서버가 내려갈 시간을 고려해 3초 선행 대기 후 폴링 시작.

        Args:
            timeout: 최대 대기 시간 (초)
            poll_interval: 폴링 간격 (초)

        Returns:
            timeout 내 준비 완료 시 True, 초과 시 False
        """
        start = time.time()
        # 서버가 종료될 시간 확보
        time.sleep(3)
        while time.time() - start < timeout:
            if self.health_check():
                logger.info("ComfyUI 재시작 완료 -- 서버 준비됨")
                return True
            elapsed = int(time.time() - start)
            logger.info(f"ComfyUI 재시작 대기 중... ({elapsed}s)")
            time.sleep(poll_interval)
        logger.error(f"ComfyUI 재시작 타임아웃: {timeout}초 초과")
        return False
