"""
새로 추가할 지역들의 보도자료 게시판이 실제로 어떻게 생겼는지
한 번에 캡처해두는 정찰용 스크립트.

이 스크립트는 실제 수집을 하지 않고, 각 사이트의 목록 페이지를
스크린샷(png)과 HTML로 저장하기만 한다. 이 결과물을 보고
사이트별 실제 수집 코드를 정확하게 작성할 수 있다.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

SITES = {
    "incheon": "https://www.incheon.go.kr/IC010205",
    "busan": "https://www.busan.go.kr/nbtnewsBU",
    "daejeon": "https://www.daejeon.go.kr/drh/board/boardNormalList.do?boardId=normal_0189&menuSeq=1632",
    "daegu": "https://info.daegu.go.kr/newshome/mtnmain.php?mtnkey=scatelist&mkey=26",
    "suwon": "https://www.suwon.go.kr/web/board/BD_board.list.do?bbsCd=1043",
    "hwaseong": "https://www.hscity.go.kr/www/user/bbs/BD_selectBbsList.do?q_bbsCode=1051",
    "yongin": "https://www.yongin.go.kr/user/bbs/BD_selectBbsList.do?q_bbsCode=1020",
    "changwon": "https://www.changwon.go.kr/cwportal/10310/10429/10432.web",
    "gyeonggi": "https://gnews.gg.go.kr/briefing/brief_gongbo.do",
    "ansan": "https://www.ansan.go.kr/www/common/bbs/selectPageListBbs.do?bbs_code=B0238",
    "jeonnam_gwangju": "https://www.jeonnam-gwangju.go.kr/boardList.do?boardId=JG_0000000003&pageId=jngj22",
}

OUT_DIR = Path(__file__).resolve().parent.parent / "debug_sites"


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))

        for name, url in SITES.items():
            print(f"[{name}] {url} 확인 중...")
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2500)
                page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
                (OUT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
                print(f"  성공")
            except Exception as e:
                print(f"  실패: {e}")
                try:
                    page.screenshot(path=str(OUT_DIR / f"{name}_error.png"), full_page=True)
                except Exception:
                    pass

        browser.close()

    print("완료")


if __name__ == "__main__":
    run()
