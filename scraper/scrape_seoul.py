"""
서울시 보도자료(주택/교통/도시계획 등 분야) 수집 스크립트

실제 확인된 구조: 목록 표(table.sib-lst-type-basic)의 각 행(tr) 안에
제목/담당부서/등록일이 이미 다 들어있고, 제목 링크는
javascript:fnTbbsView('게시물번호') 형태로 상세페이지를 연다.
따라서 목록 페이지 하나만 봐도 제목/부서/날짜를 모두 얻을 수 있다.
분류(카테고리)만 상세 페이지에 들어가야 확인 가능해서, 새 게시물에 한해서만
상세 페이지를 잠깐 방문한다.
"""

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LIST_URL = (
    "https://www.seoul.go.kr/news/news_report.do"
    "?srchCtgryType=464,465,466,467&cntPerPage=50&curPage={page}"
)
DETAIL_URL = "https://www.seoul.go.kr/news/news_report.do?nttNo={ntt_no}"

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "seoul.json"
DEBUG_DIR = Path(__file__).resolve().parent.parent / "debug"
MAX_PAGES_PER_RUN = 10
REGION = "서울특별시"

ROW_SELECTOR = "table.sib-lst-type-basic tbody tr"


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def save(items):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=lambda x: x.get("date", ""), reverse=True)
    DATA_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_debug(page, tag):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{tag}.png"), full_page=True)
    except Exception as e:
        print(f"  (스크린샷 저장 실패: {e})")
    try:
        (DEBUG_DIR / f"{tag}.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:
        print(f"  (HTML 저장 실패: {e})")


def collect_list_rows(page, page_no):
    """목록 표에서 제목/부서/날짜/게시물번호를 한 번에 뽑아온다."""
    url = LIST_URL.format(page=page_no)
    page.goto(url, wait_until="networkidle", timeout=60000)
    try:
        page.wait_for_selector(ROW_SELECTOR, timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1500)

    if page_no == 1:
        save_debug(page, "list_page1")

    rows = page.eval_on_selector_all(
        ROW_SELECTOR,
        """trs => trs.map(tr => {
            const a = tr.querySelector('td.sib-lst-type-basic-subject a');
            const tds = tr.querySelectorAll('td');
            return {
                href: a ? (a.getAttribute('href') || '') : '',
                title: a ? a.textContent.trim() : '',
                dept: tds.length > 2 ? tds[2].textContent.trim() : '',
                date: tds.length > 3 ? tds[3].textContent.trim() : ''
            };
        })""",
    )
    print(f"  찾은 행 수: {len(rows)}")

    results = {}
    for row in rows:
        m = re.search(r"fnTbbsView\('(\d+)'\)", row["href"])
        if not m:
            continue
        ntt_no = m.group(1)
        if not row["title"]:
            continue
        results[ntt_no] = row
    return results


def extract_category(page, ntt_no):
    """분류(카테고리)만 상세 페이지에서 확인한다."""
    url = DETAIL_URL.format(ntt_no=ntt_no)
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(800)

    text = page.inner_text("body")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if line == "분류" and i + 1 < len(lines):
            return lines[i + 1]
    return ""


def run():
    existing = load_existing()
    existing_by_id = {item["id"]: item for item in existing}
    new_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))

        for page_no in range(1, MAX_PAGES_PER_RUN + 1):
            print(f"[서울] {page_no}페이지 확인 중...")
            rows = collect_list_rows(page, page_no)
            if not rows:
                print("  더 이상 게시물이 없어 중단합니다.")
                break

            page_had_new = False
            for ntt_no, row in rows.items():
                if ntt_no in existing_by_id:
                    continue
                page_had_new = True
                print(f"  신규 발견: {row['title']}")
                category = extract_category(page, ntt_no)
                existing_by_id[ntt_no] = {
                    "id": ntt_no,
                    "region": REGION,
                    "title": row["title"],
                    "dept": row["dept"],
                    "date": row["date"],
                    "category": category,
                    "url": DETAIL_URL.format(ntt_no=ntt_no),
                }
                new_count += 1
                time.sleep(0.3)

            if not page_had_new and page_no > 1:
                print("  신규 게시물이 없어 이후 페이지는 건너뜁니다.")
                break

        browser.close()

    save(list(existing_by_id.values()))
    print(f"완료: 새 게시물 {new_count}건 추가, 총 {len(existing_by_id)}건 저장됨.")


if __name__ == "__main__":
    run()
