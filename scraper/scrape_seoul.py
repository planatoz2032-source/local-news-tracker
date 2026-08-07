"""
서울시 보도자료 수집기
- 목록 페이지를 훑어서 새 글(nttNo)을 찾고
- 상세 페이지에서 분류/본문 핵심문장(□, ○ 로 시작하는 줄)을 뽑아
- 주택·교통은 항상, 그 외 분야는 키워드가 겹칠 때만 "중요"로 표시해서
- data/news.json 에 누적 저장한다.

사이트 구조가 바뀌면 이 스크립트가 실패할 수 있음.
그럴 때는 GitHub Actions 로그(빨간 글씨 오류)를 그대로 복사해서 Claude에게 붙여넣으면 됨.
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.seoul.go.kr/news/news_report.do"
DETAIL_TMPL = BASE + "?bbsNo=158&nttNo={ntt_no}"
LIST_TMPL = BASE + "?cntPerPage=50&curPage={page}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEWS_JSON = DATA_DIR / "news.json"
SEEN_JSON = DATA_DIR / "seen.json"

REGION_ID = "seoul"
REGION_NAME = "서울특별시"

MAX_LIST_PAGES = 6       # 한 번 실행할 때 최대 몇 페이지(=최대 300건)까지 훑을지
MAX_KEEP_ITEMS = 400      # news.json 에 최대 몇 건까지 보관할지 (오래된 건 정리)
REQUEST_DELAY = 0.4       # 서버 부담을 줄이기 위한 요청 간 대기(초)

CORE_FIELDS = {"주택", "교통"}
ALL_FIELDS = {"경제", "주택", "문화", "교통", "안전", "환경", "행정", "복지"}

CROSS_KEYWORDS = [
    "주택", "부동산", "전월세", "정비사업", "재건축", "재개발", "공급",
    "도시계획", "규제", "조례", "예산", "협약", "지하철", "버스", "도로",
    "철도", "교통", "임대", "분양", "세제", "용적률", "정비구역",
]
SIGNAL_KEYWORDS = ["위원회", "심의", "발표", "계획", "대책", "도입", "확대", "개편", "본격"]

ROW_RE = re.compile(
    r"fnTbbsView\('(?P<ntt>\d+)'\)\);?\">\s*(?P<title>.*?)\s*</a>.*?"
    r"</td>\s*<td[^>]*>\s*(?P<dept>.*?)\s*</td>\s*<td[^>]*>\s*(?P<date>\d{4}-\d{2}-\d{2})",
    re.S,
)


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_tags(html_fragment: str) -> str:
    return BeautifulSoup(html_fragment, "html.parser").get_text(strip=True)


def fetch_list_page(page: int):
    resp = requests.get(LIST_TMPL.format(page=page), headers=HEADERS, timeout=20)
    resp.raise_for_status()
    items = []
    for m in ROW_RE.finditer(resp.text):
        items.append(
            {
                "nttNo": m.group("ntt"),
                "title": strip_tags(m.group("title")),
                "dept": strip_tags(m.group("dept")),
                "date": m.group("date"),
            }
        )
    return items


def fetch_detail(ntt_no: str):
    """상세 페이지에서 분류와 핵심 문장(□, ○ 로 시작하는 줄)을 추출."""
    resp = requests.get(DETAIL_TMPL.format(ntt_no=ntt_no), headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]

    category = None
    for i, line in enumerate(lines):
        if line == "분류" and i + 1 < len(lines) and lines[i + 1] in ALL_FIELDS:
            category = lines[i + 1]
            break

    bullets = [l for l in lines if l.startswith("□") or l.startswith("○")]
    # 너무 짧은 잡음 줄 제거, 앞 4개만 핵심 요약으로 사용
    bullets = [b for b in bullets if len(b) > 6][:4]

    return category, bullets


def score_importance(category, title):
    score = 0
    if category in CORE_FIELDS:
        score += 100
    score += sum(15 for kw in CROSS_KEYWORDS if kw in title)
    score += sum(5 for kw in SIGNAL_KEYWORDS if kw in title)
    return score


def importance_label(score):
    if score >= 100:
        return "높음"
    if score >= 30:
        return "중간"
    return "낮음"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_json(NEWS_JSON, [])
    seen = set(load_json(SEEN_JSON, []))

    new_items = []
    stop = False
    for page in range(1, MAX_LIST_PAGES + 1):
        if stop:
            break
        rows = fetch_list_page(page)
        if not rows:
            break
        for row in rows:
            if row["nttNo"] in seen:
                # 이미 처리한 글을 만나면 그 이후는 예전 글이므로 중단
                stop = True
                break
            new_items.append(row)
        time.sleep(REQUEST_DELAY)

    print(f"새 글 {len(new_items)}건 발견")

    for row in new_items:
        try:
            category, bullets = fetch_detail(row["nttNo"])
        except Exception as e:  # noqa: BLE001
            print(f"[경고] {row['nttNo']} 상세 조회 실패: {e}")
            category, bullets = None, []
        time.sleep(REQUEST_DELAY)

        score = score_importance(category, row["title"])
        row.update(
            {
                "id": f"{REGION_ID}-{row['nttNo']}",
                "region": REGION_ID,
                "region_name": REGION_NAME,
                "category": category,
                "importance_score": score,
                "importance": importance_label(score),
                "summary": bullets,
                "url": DETAIL_TMPL.format(ntt_no=row["nttNo"]),
            }
        )
        seen.add(row["nttNo"])

    combined = new_items + existing
    combined.sort(key=lambda x: (x["date"], x["nttNo"]), reverse=True)
    combined = combined[:MAX_KEEP_ITEMS]

    save_json(NEWS_JSON, combined)
    save_json(SEEN_JSON, sorted(seen)[-2000:])  # seen 목록도 무한정 커지지 않게 정리
    print(f"저장 완료: 총 {len(combined)}건")


if __name__ == "__main__":
    main()
