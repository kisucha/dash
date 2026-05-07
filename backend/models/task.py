# 목적: aiosqlite.Row를 Pydantic 스키마용 dict로 변환하는 헬퍼 함수 모음
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import aiosqlite


def row_to_dict(row: aiosqlite.Row) -> dict:
    """aiosqlite.Row를 일반 dict로 변환한다."""
    return dict(row)


def rows_to_dicts(rows: list[aiosqlite.Row]) -> list[dict]:
    """aiosqlite.Row 목록을 dict 목록으로 변환한다."""
    return [dict(row) for row in rows]
