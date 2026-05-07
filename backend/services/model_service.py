# 목적: model_inventory 테이블 CRUD 서비스 — 모델 인벤토리 조회 및 갱신
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
from typing import Optional

import aiosqlite


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """aiosqlite.Row를 dict로 변환한다."""
    return dict(row)


class ModelService:
    """model_inventory 테이블 CRUD를 담당하는 서비스 클래스."""

    async def list_models(
        self,
        db: aiosqlite.Connection,
        model_type: Optional[str] = None,
        base_model: Optional[str] = None,
    ) -> list[dict]:
        """모델 인벤토리 목록을 조회한다. 필터 조건 선택 가능."""
        conditions = []
        params = []
        if model_type:
            conditions.append("model_type = ?")
            params.append(model_type)
        if base_model:
            conditions.append("base_model = ?")
            params.append(base_model)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        cursor = await db.execute(
            f"SELECT * FROM model_inventory {where} ORDER BY model_type, name",
            params,
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def get_model_by_filename(
        self,
        db: aiosqlite.Connection,
        filename: str,
    ) -> Optional[dict]:
        """파일명으로 모델 단건 조회."""
        cursor = await db.execute(
            "SELECT * FROM model_inventory WHERE filename = ?", (filename,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def upsert_model(self, db: aiosqlite.Connection, model_data: dict) -> dict:
        """모델 정보를 INSERT OR REPLACE한다."""
        fields = [
            "model_type", "name", "filename", "local_path", "civitai_version_id",
            "hf_repo_id", "is_downloaded", "file_size_mb", "base_model", "style_tags",
        ]
        existing = await self.get_model_by_filename(db, model_data.get("filename", ""))
        if existing:
            # 기존 레코드 UPDATE
            set_parts = []
            values = []
            for field in fields:
                if field in model_data:
                    set_parts.append(f"{field} = ?")
                    val = model_data[field]
                    # style_tags 리스트는 JSON 문자열로 직렬화
                    if field == "style_tags" and isinstance(val, list):
                        val = json.dumps(val, ensure_ascii=False)
                    values.append(val)
            values.append(existing["id"])
            await db.execute(
                f"UPDATE model_inventory SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
            await db.commit()
            return await self.get_model_by_filename(db, model_data["filename"])
        else:
            # 신규 레코드 INSERT
            values = []
            col_names = []
            for field in fields:
                if field in model_data:
                    col_names.append(field)
                    val = model_data[field]
                    # style_tags 리스트는 JSON 문자열로 직렬화
                    if field == "style_tags" and isinstance(val, list):
                        val = json.dumps(val, ensure_ascii=False)
                    values.append(val)
            placeholders = ", ".join(["?" for _ in col_names])
            cursor = await db.execute(
                f"INSERT INTO model_inventory ({', '.join(col_names)}) VALUES ({placeholders})",
                values,
            )
            await db.commit()
            return await self.get_model_by_filename(db, model_data["filename"])

    async def set_downloaded(
        self,
        db: aiosqlite.Connection,
        model_id: int,
        local_path: str,
    ) -> None:
        """모델을 다운로드 완료 상태로 업데이트한다."""
        await db.execute(
            "UPDATE model_inventory SET is_downloaded = 1, local_path = ?, downloaded_at = CURRENT_TIMESTAMP WHERE id = ?",
            (local_path, model_id),
        )
        await db.commit()


# 싱글턴 인스턴스 — 라우터에서 import하여 사용
model_service = ModelService()
