"""
대전광역시 보도자료 수집기 (data/news_daejeon.json)

사이트 구조가 바뀌면 이 스크립트가 실패할 수 있음.
그럴 때는 GitHub Actions 로그(빨간 글씨 오류)를 그대로 복사해서 Claude에게 붙여넣으면 됨.
"""

import re
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import get_with_retry, make_session, load_json, save_json, score_importance, importance_label

BASE = "https://www.daejeon.go.kr"
LIST_TMPL = BASE + "/drh/board/boardNormalList.do?boardId=normal_0189&menuSeq=6825&pageIndex={page}"

SESSION = make_session(referer=LIST_TMPL.format(page=1))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEWS_JSON = DATA_DIR / "news_daejeon.json"
SEEN_JSON = DATA_DIR / "seen_daejeon.json"

REGION_ID = "daejeon"
REGION_NAME = "대전광역시"

MAX_LIST_PAGES = 6
MAX_KEEP_ITEMS = 400
REQUEST_DELAY = 1.2


def fetch_list_page(page: int):
    """목록 표에서 (ntatcSeq, 제목, 부서, 날짜, 상세URL) 목록을 만든다.
    맨 위에 고정되는 '공지' 행은 번호가 숫자가 아니므로 건너뛴다."""
    resp = get_with_retry(SESSION, LIST_TMPL.format(page=page))
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for tr in soup.select("table.board_table_list tbody tr"):
        num_td = tr.select_one("td.num")
        num_text = num_td.get_text(strip=True) if num_td else ""
        if not num_text.isdigit():
            continue  # '공지' 등 고정 게시물은 건너뜀

        subject_td = tr.select_one("td.al_left.subject") or tr.select_one("td.subject")
        if not subject_td:
            continue
        a = subject_td.find("a")
        if not a:
            continue
        href = a.get("href") or ""
        m = re.search(r"ntatcSeq=(\d+)", href)
        if not m:
            continue
        ntatc_seq = m.group(1)
        title = a.get_text(strip=True)
        if not title:
            continue

        dept_td = tr.select_one("td.division")
        dept = dept_td.get_text(strip=True) if dept_td else None
        date_td = tr.select_one("td.date")
        date = date_td.get_text(strip=True) if date_td else None

        items.append(
            {
                "ntatcSeq": ntatc_seq,
                "title": title,
                "dept": dept,
                "date": date,
                "url": urljoin(BASE, href),
            }
        )
    return items


def fetch_detail_summary(url: str):
    """상세 페이지에서 본문 앞부분을 요약용으로 가져온다."""
    resp = get_with_retry(SESSION, url)
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]
    body_lines = [l for l in lines if len(l) > 20 and not l.startswith("http")]
    return body_lines[:3]


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_json(NEWS_JSON, [])
    seen = set(load_json(SEEN_JSON, []))

    new_items = []
    added_ids = set()
    stop = False
    for page in range(1, MAX_LIST_PAGES + 1):
        if stop:
            break
        rows = fetch_list_page(page)
        if not rows:
            break
        for row in rows:
            if row["ntatcSeq"] in added_ids:
                continue
            if row["ntatcSeq"] in seen:
                stop = True
                break
            added_ids.add(row["ntatcSeq"])
            new_items.append(row)
        time.sleep(REQUEST_DELAY)

    print(f"새 글 {len(new_items)}건 발견")

    for row in new_items:
        try:
            summary = fetch_detail_summary(row["url"])
        except Exception as e:  # noqa: BLE001
            print(f"[경고] {row['ntatcSeq']} 상세 조회 실패: {e}")
            summary = []
        time.sleep(REQUEST_DELAY)

        score = score_importance(row["title"], dept=row.get("dept"))
        row.update(
            {
                "id": f"{REGION_ID}-{row['ntatcSeq']}",
                "region": REGION_ID,
                "region_name": REGION_NAME,
                "nttNo": row["ntatcSeq"],
                "dept": row.get("dept") or "",
                "date": row.get("date") or "",
                "category": None,
                "importance_score": score,
                "importance": importance_label(score),
                "summary": summary,
            }
        )
        seen.add(row["ntatcSeq"])

    combined = new_items + existing
    combined.sort(key=lambda x: (x.get("date") or "", x["ntatcSeq"]), reverse=True)
    combined = combined[:MAX_KEEP_ITEMS]

    save_json(NEWS_JSON, combined)
    save_json(SEEN_JSON, sorted(seen)[-2000:])
    print(f"저장 완료: 총 {len(combined)}건")


if __name__ == "__main__":
    main()
