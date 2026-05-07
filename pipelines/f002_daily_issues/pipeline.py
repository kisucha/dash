# F002 이슈 발굴 파이프라인 — 멀티 홉 검색(shared.multihop_search) + Ollama 분석
# 1단계: 멀티 홉 검색으로 키워드 관련 뉴스/커뮤니티 수집 (N차까지)
# 2단계: Ollama LLM으로 이슈 분석·요약

import sys
import logging
from datetime import date

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

# 파서 표시 이름 매핑
_PARSER_DISPLAY: dict[str, str] = {
    "trafilatura": "trafilatura",
    "beautifulsoup": "BeautifulSoup",
    "BeautifulSoup": "BeautifulSoup",
}

# 기본 분석 지시문 템플릿
# {keywords} — 검색 키워드 문자열, {max_issues} — 최대 이슈 수로 치환됨
# features.py의 prompt_template 기본값과 반드시 동일하게 유지할 것
_DEFAULT_INSTRUCTION: str = (
    "위 실제 검색 결과를 바탕으로 '{keywords}' 관련 주요 이슈 {max_issues}개를 아래 형식으로 정리해줘.\n"
    "반드시 실제 검색 결과에 있는 내용만 사용하고, 없는 내용을 만들지 마.\n\n"
    "각 이슈는 반드시 아래 형식으로 작성 (---로 앞뒤 구분):\n"
    "---\n"
    "1. 이슈 제목\n"
    "요약: 이슈 내용을 2~4문장으로 요약\n"
    "중요도: 높음\n"
    "---\n\n"
    "조건:\n"
    "- 이슈 제목에 반드시 구체적인 제품명·모델명·브랜드명을 포함할 것\n"
    "  나쁜 예: 'AI 가전 혁신', '스마트 헬스 웨어러블'\n"
    "  좋은 예: '삼성 갤럭시 S25 엣지 보더리스 공개', '로지텍 MX Keys S Pro 한국 출시'\n"
    "- 이슈 제목은 40자 이내\n"
    "- 요약은 검색 결과에서 발췌한 구체적 수치·제품명·사건을 포함\n"
    "- 중요도는 반드시 '높음', '보통', '낮음' 중 하나\n"
    "- {max_issues}개 이슈를 빠짐없이 출력 (추가 설명 없이)\n"
    "- 한국어로 작성"
)


class F002Pipeline(BasePipeline):
    """
    F002 매일 아침 이슈 발굴 파이프라인.

    입력 파라미터:
    - keywords (list[str] | str, 선택): 키워드 (기본: ["AI", "tech", "startup"])
    - date (str, 선택): 분석 기준일 YYYY-MM-DD (기본: 오늘)
    - max_issues (int, 선택, 기본 5): 최대 이슈 수 (1~20)
    - days (int, 선택, 기본 2): 검색 기간 최근 N일 (Tavily 전용)
    - search_provider (str, 선택, 기본 "searxng"): 검색 엔진 선택
    - max_hops (int, 선택, 기본 2): 멀티 홉 검색 깊이 (1~5)

    출력 형식:
    {
        "date": str,
        "search_provider": str,
        "hops_executed": int,
        "issues": [
            {"title": str, "summary": str, "importance": str, "parser": str},
            ...
        ]
    }
    """

    def get_metadata(self) -> dict:
        return {
            "feature_id": "F002",
            "name": "매일 아침 이슈 발굴",
            "description": (
                "멀티 홉 검색(SearXNG/Tavily)으로 최신 뉴스를 수집하고 "
                "Ollama LLM이 주요 이슈를 분석·요약합니다."
            ),
            "input_schema": {
                "keywords": {
                    "type": "list[str] | str",
                    "required": False,
                    "default": ["AI", "tech", "startup"],
                    "description": "발굴할 이슈 관련 키워드 (리스트 또는 쉼표 구분 문자열)",
                },
                "date": {
                    "type": "str",
                    "required": False,
                    "default": "오늘 날짜 자동 사용",
                    "description": "이슈 분석 기준 날짜 (YYYY-MM-DD)",
                },
                "max_issues": {
                    "type": "int",
                    "required": False,
                    "default": 5,
                    "description": "발굴할 이슈 최대 개수 (1~20)",
                },
                "days": {
                    "type": "int",
                    "required": False,
                    "default": 2,
                    "description": "Tavily 검색 기간 — 최근 N일 (기본 2일, Tavily 전용)",
                },
                "search_provider": {
                    "type": "str",
                    "required": False,
                    "default": "searxng",
                    "description": "검색 엔진 선택: searxng(기본, 로컬) | tavily(유료)",
                },
                "max_hops": {
                    "type": "int",
                    "required": False,
                    "default": 2,
                    "description": "멀티 홉 검색 깊이 (1~5, 기본 2) — 높을수록 구체적이나 시간 증가",
                },
            },
            "supports_schedule": True,
        }

    def run(self, task_id: int, params: dict) -> dict:
        logger.info(f"[F002][task_id={task_id}] 파이프라인 실행 시작")

        # ── [1] 파라미터 추출 ─────────────────────────────────────────────
        raw_keywords = params.get("keywords", ["AI", "tech", "startup"])
        keywords: list[str] = self._parse_keywords(raw_keywords)
        if not keywords:
            keywords = ["AI", "tech", "startup"]

        raw_date = params.get("date", "").strip()
        target_date: str = raw_date if raw_date else date.today().isoformat()

        try:
            max_issues: int = max(1, min(20, int(params.get("max_issues", 5))))
        except (ValueError, TypeError):
            max_issues = 5

        try:
            days: int = max(1, min(30, int(params.get("days", 2))))
        except (ValueError, TypeError):
            days = 2

        try:
            max_hops: int = max(1, min(5, int(params.get("max_hops", 2))))
        except (ValueError, TypeError):
            max_hops = 2

        search_provider: str = str(params.get("search_provider", "searxng")).lower().strip()
        if search_provider not in ("searxng", "tavily"):
            logger.warning(f"[F002] 알 수 없는 search_provider='{search_provider}' — searxng으로 대체")
            search_provider = "searxng"

        # 사용자 정의 프롬프트 (비어 있으면 _DEFAULT_INSTRUCTION 사용)
        custom_instruction: str = str(params.get("prompt_template", "")).strip()

        logger.info(
            f"[F002][task_id={task_id}] 파라미터 — "
            f"keywords={keywords}, date={target_date}, "
            f"max_issues={max_issues}, days={days}, provider={search_provider}, max_hops={max_hops}"
        )

        # ── [2] RUNNING 상태 업데이트 ─────────────────────────────────────
        self.update_status(task_id=task_id, status="RUNNING")

        if self.is_cancelled(task_id):
            return {}

        # ── [3] 멀티 홉 검색 ─────────────────────────────────────────────
        query = " ".join(keywords)
        period_desc = f"최근 {days}일간"

        self.update_status(
            task_id=task_id,
            status="RUNNING",
            result={"progress": f"멀티 홉 검색 중... (최대 {max_hops}차)"},
        )

        logger.info(
            f"[F002][task_id={task_id}] 멀티 홉 검색 시작 — "
            f"query={query!r}, max_hops={max_hops}, days={days}"
        )

        mh_result = self.multihop_search(
            query=query,
            provider=search_provider,
            max_hops=max_hops,
            results_per_hop=10,
            subqueries_per_hop=3,
            enrich=True,
            days=days,
            categories="news",  # 뉴스 카테고리 — publishedDate 포함, 최신성 보장
        )

        if not mh_result.results:
            raise RuntimeError(
                f"{search_provider} 검색 결과가 없습니다. 키워드를 확인하세요."
            )

        logger.info(
            f"[F002][task_id={task_id}] 검색 완료 — "
            f"{len(mh_result.results)}건, {mh_result.hops_executed}차 수행"
        )

        if self.is_cancelled(task_id):
            return {}

        # 사용된 파서 요약 계산
        parser_summary = self._build_parser_summary(mh_result.results, search_provider)
        logger.info(f"[F002][task_id={task_id}] 파서 요약: {parser_summary}")

        # ── [4] Ollama 분석 프롬프트 구성 ─────────────────────────────────
        self.update_status(
            task_id=task_id,
            status="RUNNING",
            result={"progress": "Ollama 이슈 분석 중...", "target_date": target_date},
        )

        keywords_str = ", ".join(keywords)

        # 사용자 정의 지시문 또는 기본 지시문 선택 후 플레이스홀더 치환
        instruction_template = custom_instruction if custom_instruction else _DEFAULT_INSTRUCTION
        instruction = (
            instruction_template
            .replace("{keywords}", keywords_str)
            .replace("{max_issues}", str(max_issues))
        )

        # 검색 결과 도입부(고정) + 분석 지시문(수정 가능) 결합
        # mh_result.context_text에는 hop별 구조화된 검색 결과가 포함됨
        prompt: str = (
            f"아래는 {period_desc} 수집된 실제 뉴스/커뮤니티 검색 결과입니다.\n\n"
            f"{mh_result.context_text}\n\n"
            f"[분석 지시]\n\n"
            f"{instruction}"
        )

        raw_response: str = self.call_ollama(prompt=prompt, timeout=180)
        logger.info(f"[F002][task_id={task_id}] Ollama 응답 수신 ({len(raw_response)}자)")

        # ── [5] 파싱 및 결과 반환 ─────────────────────────────────────────
        issues = self._parse_issues(raw_response, max_issues)

        for issue in issues:
            issue["parser"] = parser_summary

        logger.info(f"[F002][task_id={task_id}] {len(issues)}개 이슈 추출 완료")
        return {
            "date": target_date,
            "search_provider": search_provider,
            "hops_executed": mh_result.hops_executed,
            "issues": issues,
        }

    # ── 내부 유틸 ──────────────────────────────────────────────────────────────

    def _parse_keywords(self, raw: object) -> list[str]:
        if isinstance(raw, list):
            return [str(k).strip() for k in raw if str(k).strip()]
        elif isinstance(raw, str):
            return [k.strip() for k in raw.split(",") if k.strip()]
        converted = str(raw).strip()
        return [converted] if converted else []

    def _build_parser_summary(self, results: list[dict], search_provider: str) -> str:
        """사용된 파서 종류를 요약한 문자열을 반환한다."""
        if search_provider == "tavily":
            return "Tavily"

        parsers: set[str] = set()
        for r in results:
            raw = r.get("body_parser", "")
            display = _PARSER_DISPLAY.get(raw, "")
            if display:
                parsers.add(display)

        if not parsers:
            return ""
        if parsers == {"trafilatura"}:
            return "trafilatura"
        if parsers == {"BeautifulSoup"}:
            return "BeautifulSoup"
        return "trafilatura/BeautifulSoup"

    def _parse_issues(self, raw_text: str, max_issues: int) -> list[dict]:
        """Ollama 응답 텍스트를 이슈 딕셔너리 리스트로 파싱한다."""
        import re

        logger.debug(f"[F002] Ollama 원본 응답 ({len(raw_text)}자):\n{raw_text[:1000]}")

        issues: list[dict] = []
        blocks = raw_text.split("---")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue

            # 제목 추출 — 다양한 번호 형식 제거
            # 처리 대상: "1. 제목", "[1]. 제목", "1) 제목", "- 제목", "[1] 제목"
            title_line = lines[0]

            # [N]. 또는 [N] 형식 먼저 제거 (대괄호 번호)
            bracket_match = re.match(r'^\[\d+\][.)]\s*', title_line)
            if bracket_match:
                title_line = title_line[bracket_match.end():]
            else:
                # "N. ", "N) ", "- " 형식 제거
                for sep in [". ", ") ", "- "]:
                    if sep in title_line:
                        parts = title_line.split(sep, 1)
                        prefix = parts[0].strip()
                        if prefix.isdigit() or prefix in ["-", "*"]:
                            title_line = parts[1].strip()
                            break

            title = title_line[:50]

            # 요약 추출
            summary = ""
            for line in lines[1:]:
                if line.lower().startswith("요약:") or line.lower().startswith("요약 :"):
                    summary = line.split(":", 1)[-1].strip()
                    break
            if not summary and len(lines) > 1:
                summary = " ".join(
                    l for l in lines[1:] if not l.startswith("중요도")
                ).strip()

            # 중요도 추출
            importance = "보통"
            for line in lines:
                if line.startswith("중요도"):
                    val = line.split(":", 1)[-1].strip()
                    if "높음" in val:
                        importance = "높음"
                    elif "낮음" in val:
                        importance = "낮음"
                    break

            if title:
                issues.append({"title": title, "summary": summary, "importance": importance})

            if len(issues) >= max_issues:
                break

        if not issues:
            logger.warning("[F002] 이슈 파싱 실패 — 원본 텍스트를 단일 항목으로 반환")
            issues = [{"title": "이슈 파싱 실패", "summary": raw_text[:500], "importance": "보통"}]

        logger.info(f"[F002] 파싱 결과: {len(issues)}개 이슈 추출 (요청: {max_issues}개)")
        return issues
