"""
여러 지역 스크래퍼가 공통으로 쓰는 유틸리티.
- get_with_retry: SSL/연결 오류 재시도 + 오래된 정부 사이트 TLS 궁합 문제 우회
- score_importance / importance_label: 중요도 판정 로직 (주택·교통 최우선)
"""

import json
import re
import ssl
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "close",
}


class LegacyTLSAdapter(HTTPAdapter):
    """오래된 정부 사이트에서 흔한 'UNEXPECTED_EOF_WHILE_READING' 오류 우회용."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except ssl.SSLError:
            pass
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def make_session(referer: str | None = None):
    session = requests.Session()
    session.mount("https://", LegacyTLSAdapter(max_retries=0))
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    session.headers.update(headers)
    return session


def get_with_retry(session, url, tries=5, delay=3.0, timeout=30):
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_err = e
            print(f"  [재시도 {attempt}/{tries}] {url} 요청 실패: {e}")
            time.sleep(delay * attempt)
    raise last_err


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


CORE_FIELDS = {"주택", "교통"}
CORE_TEXT_KEYWORDS = ["주택", "부동산", "정비사업", "재건축", "재개발", "임대주택", "지하철", "버스", "도로", "교통"]

CROSS_KEYWORDS = [
    "주택", "부동산", "전월세", "정비사업", "재건축", "재개발", "공급",
    "도시계획", "규제", "조례", "예산", "협약", "지하철", "버스", "도로",
    "철도", "교통", "임대", "분양", "세제", "용적률", "정비구역",
]
SIGNAL_KEYWORDS = ["위원회", "심의", "발표", "계획", "대책", "도입", "확대", "개편", "본격"]


def score_importance(title: str, category: str | None = None, dept: str | None = None):
    """분류(category)가 있으면 그걸로, 없으면 부서명/제목 키워드로 주택·교통 여부를 판단한다."""
    score = 0
    is_core = False
    if category and category in CORE_FIELDS:
        is_core = True
    elif dept and any(kw in dept for kw in CORE_TEXT_KEYWORDS):
        is_core = True
    elif any(kw in title for kw in ["주택", "교통", "지하철", "버스"]):
        is_core = True

    if is_core:
        score += 100
    score += sum(15 for kw in CROSS_KEYWORDS if kw in title)
    score += sum(5 for kw in SIGNAL_KEYWORDS if kw in title)
    return score


def importance_label(score: int) -> str:
    if score >= 100:
        return "높음"
    if score >= 30:
        return "중간"
    return "낮음"
