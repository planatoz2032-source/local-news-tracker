"""
서울시 보도자료(주택/교통/도시계획 분야) 수집 스크립트
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


def collect_list_links(page, page_no):
    url = LIST_URL.format(page=page_no)
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3500)

    if page_no == 1:
        save_debug(page, "list_page1")

    links = page.eval_on_selector_all(
        "a[href*='nttNo=']",
        """els => els.map(e => ({
            href: e.getAttribute('href') || '',
            text: (e.textContent || '').trim()
        }))""",
    )
    print(f"  a[href*='nttNo=']로 찾은 링크 수: {len(links)}")

    if not links:
        all_a = page.eval_on_selector_all(
            "a",
            """els => els.slice(0, 40).map(e => ({
                href: e.getAttribute('href') || '',
                onclick: e.getAttribute('onclick') || '',
                text: (e.textContent || '').trim().slice(0, 40)
            }))""",
        )
        print("  전체 링크 샘플(최대 40개):")
        for a in all_a:
            if a["text"] or a["onclick"]:
                print(f"    href={a['href']!r} onclick={a['onclick']!r} text={a['text']!r}")

    results = {}
    for link in links:
        m = re.search(r"nttNo=(\d+)", link["href"])
        if not m:
            continue
        ntt_no = m.group(1)
        title = link["text"]
        if not title:
            continue
        if len(title) < 4:
            continue
        results[ntt_no] = title
    return results


def extract_detail(page, ntt_no):
    url = DETAIL_URL.format(ntt_no=ntt_no)
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1200)

    text = page.inner_text("body")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    def value_after(label):
        for i, line in enumerate(lines):
            if line == label and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    dept = value_after("담당부서")
    date = value_after("등록일")
    category = value_after("분류")

    return {"dept": dept, "date": date, "category": category, "url": url}


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
            links = collect_list_links(page, page_no)
            if not links:
                print("  더 이상 게시물이 없어 중단합니다.")
                break

            page_had_new = False
            for ntt_no, title in links.items():
                if ntt_no in existing_by_id:
                    continue
                page_had_new = True
                print(f"  신규 발견: {title}")
                detail = extract_detail(page, ntt_no)
                existing_by_id[ntt_no] = {
                    "id": ntt_no,
                    "region": REGION,
                    "title": title,
                    "dept": detail["dept"],
                    "date": detail["date"],
                    "category": detail["category"],
                    "url": detail["url"],
                }
                new_count += 1
                time.sleep(0.5)

            if not page_had_new and page_no > 1:
                print("  신규 게시물이 없어 이후 페이지는 건너뜁니다.")
                break

        browser.close()

    save(list(existing_by_id.values()))
    print(f"완료: 새 게시물 {new_count}건 추가, 총 {len(existing_by_id)}건 저장됨.")


if __name__ == "__main__":
    run()
