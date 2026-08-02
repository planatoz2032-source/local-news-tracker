"""
서울시 보도자료(주택/교통/도시계획 분야) 수집 스크립트

- 목록 페이지는 자바스크립트로 나중에 채워지는 방식이라, 실제 브라우저처럼
  동작하는 Playwright로 페이지를 열어서 "화면에 보이는 대로" 링크를 긁어온다.
- 이미 저장된 게시물(nttNo)은 건너뛰고, 새 게시물만 상세 페이지에 들어가서
  담당부서/등록일/분류 정보를 채운다.
- 저작권 정책(공공누리 4유형: 출처표시+상업적이용금지+변경금지)을 지키기 위해
  본문 전체를 저장하지 않고, 제목/날짜/부서/분류/원문 링크만 저장한다.
"""

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# 서울시 보도자료 목록 (분류코드 464,465,466,467 = 사용자가 지정한 주택/교통/도시계획 등 분야)
LIST_URL = (
    "https://www.seoul.go.kr/news/news_report.do"
    "?srchCtgryType=464,465,466,467&cntPerPage=50&curPage={page}"
)
DETAIL_URL = "https://www.seoul.go.kr/news/news_report.do?nttNo={ntt_no}"

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "seoul.json"
MAX_PAGES_PER_RUN = 10  # 한 번 실행할 때 최대 몇 페이지까지 볼지 (신규글이 없으면 더 일찍 멈춤)
REGION = "서울특별시"


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def save(items):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 최신 등록일 순으로 정렬해서 저장
    items = sorted(items, key=lambda x: x.get("date", ""), reverse=True)
    DATA_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def collect_list_links(page, page_no):
    """목록 페이지에서 nttNo(게시물 번호)와 제목을 뽑아온다."""
    url = LIST_URL.format(page=page_no)
    page.goto(url, wait_until="networkidle", timeout=60000)
    # 자바스크립트 렌더링이 끝날 시간을 넉넉히 준다
    page.wait_for_timeout(2500)

    links = page.eval_on_selector_all(
        "a[href*='nttNo=']",
        """els => els.map(e => ({
            href: e.getAttribute('href') || '',
            text: (e.textContent || '').trim()
        }))""",
    )

    results = {}
    for link in links:
        m = re.search(r"nttNo=(\d+)", link["href"])
        if not m:
            continue
        ntt_no = m.group(1)
        title = link["text"]
        if not title:
            continue
        # 이전/다음 페이지 이동 링크 등 게시물이 아닌 것 걸러내기 (제목이 너무 짧으면 스킵)
        if len(title) < 4:
            continue
        results[ntt_no] = title
    return results


def extract_detail(page, ntt_no):
    """상세 페이지에서 담당부서/등록일/분류를 뽑아온다."""
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
                time.sleep(0.5)  # 서버 부담을 줄이기 위한 짧은 대기

            # 이번 페이지에 신규 글이 하나도 없었다면, 그 뒤 페이지는 다 이미 본 것들이므로 중단
            if not page_had_new and page_no > 1:
                print("  신규 게시물이 없어 이후 페이지는 건너뜁니다.")
                break

        browser.close()

    save(list(existing_by_id.values()))
    print(f"완료: 새 게시물 {new_count}건 추가, 총 {len(existing_by_id)}건 저장됨.")


if __name__ == "__main__":
    run()
