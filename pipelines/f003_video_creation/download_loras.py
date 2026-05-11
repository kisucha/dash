# 목적: F003 파이프라인용 LoRA 파일을 CivitAI에서 직접 다운로드하는 독립 스크립트
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
import httpx

# CivitAI API 키 — .env 파일에서 읽거나 직접 지정
CIVITAI_API_KEY = os.getenv("CIVITAI_API_KEY", "8564ef587ca75bb706a7ab1030ec8dfd")

# ComfyUI LoRA 저장 디렉토리
LORA_DIR = Path(r"C:\ComfyUI\ComfyUI\models\loras")

# 다운로드 대상 LoRA 목록
# civitai_version_id가 있는 항목만 포함
DOWNLOAD_TARGETS = [
    {
        "key": "detail_tweaker_xl",
        "civitai_version_id": 274039,
        "target_filename": "detail_tweaker_xl.safetensors",
    },
    {
        "key": "detailifier",
        "civitai_version_id": 1031573,
        "target_filename": "detailifier.safetensors",
    },
    {
        "key": "detail_tweaker",
        "civitai_version_id": 135867,
        "target_filename": "detail_tweaker_sd15.safetensors",
    },
    {
        "key": "add_more_details",
        "civitai_version_id": 87153,
        "target_filename": "add_more_details.safetensors",
    },
]


def download_lora(key: str, version_id: int, target_path: Path) -> bool:
    """CivitAI에서 LoRA를 스트리밍 다운로드한다.

    이미 파일이 존재하면 건너뛴다.
    1MB 청크 단위로 읽어 진행률을 콘솔에 출력한다.

    Args:
        key: LoRA 식별 키 (로그 출력용)
        version_id: CivitAI 버전 ID
        target_path: 저장할 파일 절대 경로

    Returns:
        성공 시 True, 실패 또는 건너뜀 시 False
    """
    # 파일이 이미 존재하면 건너뜀
    if target_path.exists():
        size_mb = round(target_path.stat().st_size / (1024 * 1024), 1)
        print(f"[SKIP] {key} - 이미 존재함 ({size_mb} MB): {target_path}")
        return False

    download_url = f"https://civitai.com/api/download/models/{version_id}"
    headers = {"Authorization": f"Bearer {CIVITAI_API_KEY}"}

    print(f"[START] {key} (version_id={version_id})")
    print(f"        URL: {download_url}")
    print(f"        저장 경로: {target_path}")

    # 저장 디렉토리 생성 (없으면)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 연결 타임아웃 30초, read/write는 무제한 (대용량 파일 대비)
        with httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=None, write=None, pool=None),
            follow_redirects=True,
        ) as client:
            with client.stream("GET", download_url, headers=headers) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("content-length", 0))
                total_mb = round(total_bytes / (1024 * 1024), 1) if total_bytes else 0
                print(f"        파일 크기: {total_mb} MB")

                downloaded = 0
                last_printed_pct = -1

                with open(target_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 5% 단위로 진행률 출력
                        if total_bytes > 0:
                            pct = int(downloaded / total_bytes * 100)
                            if pct >= last_printed_pct + 5:
                                downloaded_mb = round(downloaded / (1024 * 1024), 1)
                                print(f"        진행: {pct}% ({downloaded_mb}/{total_mb} MB)")
                                last_printed_pct = pct

        final_size_mb = round(target_path.stat().st_size / (1024 * 1024), 1)
        print(f"[DONE] {key} - 완료 ({final_size_mb} MB)")
        return True

    except httpx.HTTPStatusError as e:
        # 스트리밍 응답에서는 .text 직접 접근 불가 — status_code만 출력
        print(f"[FAIL] {key} - HTTP 오류: {e.response.status_code}")
        # 실패한 부분 파일 삭제
        if target_path.exists():
            target_path.unlink()
        return False
    except Exception as e:
        print(f"[FAIL] {key} - 예외 발생: {e}")
        if target_path.exists():
            target_path.unlink()
        return False


def main() -> None:
    """다운로드 대상 LoRA를 순서대로 처리한다."""
    print("=" * 60)
    print("F003 LoRA 사전 다운로드 시작")
    print(f"저장 디렉토리: {LORA_DIR}")
    print(f"대상 LoRA 수: {len(DOWNLOAD_TARGETS)}개")
    print("=" * 60)

    success_count = 0
    skip_count = 0
    fail_count = 0

    for target in DOWNLOAD_TARGETS:
        key = target["key"]
        version_id = target["civitai_version_id"]
        target_path = LORA_DIR / target["target_filename"]

        already_existed = target_path.exists()
        result = download_lora(key, version_id, target_path)
        if result is True:
            success_count += 1
        elif already_existed:
            # 함수 진입 전에 이미 파일이 있었으면 skip
            skip_count += 1
        else:
            fail_count += 1

        print()

    print("=" * 60)
    print(f"완료 - 성공: {success_count}개 / 건너뜀: {skip_count}개 / 실패: {fail_count}개")
    print("=" * 60)


if __name__ == "__main__":
    main()
