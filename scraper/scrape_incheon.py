"""
인천광역시 보도자료 수집기 (data/news_incheon.json)

사이트 구조가 바뀌면 이 스크립트가 실패할 수 있음.
그럴 때는 GitHub Actions 로그(빨간 글씨 오류)를 그대로 복사해서 Claude에게 붙여넣으면 됨.
"""

import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

from common import get_with_retry, make_session, load_json, save_json, score_importance, importance_label

BASE = "https://www.incheon.go.kr/IC010205"
LIST_TMPL = BASE + "?curPage={page}"
DETAIL_TMPL = "https://www.incheon.go.kr/IC010205/view?repSeq={rep_seq}"

SESSION = make_session(referer=BASE)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEWS_JSON = DATA_DIR / "news_incheon.json"
SEEN_JSON = DATA_DIR / "seen_incheon.json"

REGION_ID = "incheon"
REGION_NAME = "인천광역시"

MAX_LIST_PAGES = 6
MAX_KEEP_ITEMS = 400
REQUEST_DELAY = 1.2


def fetch_list_page(page: int):
    """목록 페이지에서 (repSeq, 제목, 미리보기, 날짜, 부서) 목록을 만든다."""
    resp = get_with_retry(SESSION, LIST_TMPL.format(page=page))
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_on_page = set()
    for a in soup.select("a[href*='IC010205/view']"):
        href = a.get("href") or ""
        m = re.search(r"repSeq=([\w\-]+)", href)
        if not m:
            continue
        rep_seq = m.group(1)
        if rep_seq in seen_on_page:
            continue

        subject_el = a.select_one(".subject")
        title = subject_el.get_text(strip=True) if subject_el else ""
        if not title:
            continue

        preview_el = a.select_one(".txt")
        preview = preview_el.get_text(strip=True) if preview_el else ""

        block_text = a.get_text(" ", strip=True)
        date_m = re.search(r"\d{4}-\d{2}-\d{2}", block_text)
        date = date_m.group(0) if date_m else None
        dept_m = re.search(r"제공부서\s*([^\s|]+)", block_text)
        dept = dept_m.group(1) if dept_m else None

        seen_on_page.add(rep_seq)
        items.append(
            {
                "repSeq": rep_seq,
                "title": title,
                "preview": preview,
                "date": date,
                "dept": dept,
            }
        )
    return items


def fetch_detail(rep_seq: str):
    """상세 페이지에서 정확한 담당부서/제공일시와 본문 앞부분을 보강한다."""
    resp = get_with_retry(SESSION, DETAIL_TMPL.format(rep_seq=rep_seq))
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]

    dept = None
    for i, line in enumerate(lines):
        if line == "담당부서" and i + 1 < len(lines):
            dept = lines[i + 1].split("/")[0].strip()
            break

    date = None
    for i, line in enumerate(lines):
        if line in ("제공일시", "제공일자") and i + 1 < len(lines):
            m = re.search(r"\d{4}-\d{2}-\d{2}", lines[i + 1])
            if m:
                date = m.group(0)
            break
    if not date:
        for line in lines:
            m = re.search(r"\d{4}-\d{2}-\d{2}", line)
            if m:
                date = m.group(0)
                break

    body_lines = [l for l in lines if len(l) > 15 and not l.startswith("http")]
    summary = body_lines[:3]

    return dept, date, summary


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
            if row["repSeq"] in seen:
                stop = True
                break
            new_items.append(row)
        time.sleep(REQUEST_DELAY)

    print(f"새 글 {len(new_items)}건 발견")

    for row in new_items:
        try:
            dept, date, summary = fetch_detail(row["repSeq"])
        except Exception as e:  # noqa: BLE001
            print(f"[경고] {row['repSeq']} 상세 조회 실패: {e}")
            dept, date, summary = None, None, []
        time.sleep(REQUEST_DELAY)

        dept = dept or row.get("dept") or ""
        date = date or row.get("date") or ""
        if not summary and row.get("preview"):
            summary = [row["preview"]]

        score = score_importance(row["title"], dept=dept)
        row.update(
            {
                "id": f"{REGION_ID}-{row['repSeq']}",
                "region": REGION_ID,
                "region_name": REGION_NAME,
                "nttNo": row["repSeq"],
                "dept": dept,
                "date": date,
                "category": None,
                "importance_score": score,
                "importance": importance_label(score),
                "summary": summary,
                "url": DETAIL_TMPL.format(rep_seq=row["repSeq"]),
            }
        )
        row.pop("preview", None)
        seen.add(row["repSeq"])

    combined = new_items + existing
    combined.sort(key=lambda x: (x.get("date") or "", x["repSeq"]), reverse=True)
    combined = combined[:MAX_KEEP_ITEMS]

    save_json(NEWS_JSON, combined)
    save_json(SEEN_JSON, sorted(seen)[-2000:])
    print(f"저장 완료: 총 {len(combined)}건")


if __name__ == "__main__":
    main()
