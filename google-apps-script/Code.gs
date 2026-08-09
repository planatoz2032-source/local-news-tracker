/**
 * 사용법
 * 1. 새 구글 시트를 만든다.
 * 2. 상단 메뉴 확장 프로그램 → Apps Script 클릭
 * 3. 기본으로 열려있는 코드를 전부 지우고 이 파일 내용을 붙여넣는다.
 * 4. 저장(디스크 아이콘) → 상단 배포 → 새 배포
 *    - 유형: 웹 앱
 *    - 실행 계정: 나
 *    - 액세스 권한이 있는 사용자: 모든 사용자(익명 사용자 포함)
 * 5. "배포" 클릭 → 나오는 웹 앱 URL을 복사해서
 *    - index.html 안의 FAVORITES_WEBAPP_URL 값
 *    - scraper/scrape_seoul.py 안의 COMMITTEE_WEBAPP_URL 값
 *    두 군데에 똑같이 붙여넣는다.
 * 6. 이후 시트를 다시 열어보면:
 *    - ★ 즐겨찾기를 누를 때마다 "즐겨찾기" 탭에
 *    - 제목에 "위원회"가 들어간 서울시 보도자료의 안건표가 새로 감지될 때마다 "위원회" 탭에
 *    자동으로 줄이 쌓인다. (탭이 없으면 첫 데이터가 들어올 때 자동 생성됨)
 */

const SHEETS = {
  favorite: {
    name: "즐겨찾기",
    header: ["저장시각", "동작", "지역", "분야", "제목", "담당부서", "등록일", "링크"],
  },
  committee: {
    name: "위원회",
    header: ["감지시각", "날짜", "위원회구분", "회차", "안건명", "안건개요", "심의결과", "비고", "링크"],
  },
};

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const kind = data.sheet === "committee" ? "committee" : "favorite";
    const sheet = getOrCreateSheet_(kind);

    if (kind === "committee") {
      sheet.appendRow([
        new Date(),
        data.date || "",
        data.committee_type || "",
        data.session || "",
        data.agenda_name || "",
        data.agenda_summary || "",
        data.result || "",
        data.note || "",
        data.url || "",
      ]);
    } else {
      sheet.appendRow([
        new Date(),
        data.action || "즐겨찾기",
        data.region_name || "",
        data.category || "",
        data.title || "",
        data.dept || "",
        data.date || "",
        data.url || "",
      ]);
    }

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet_(kind) {
  const conf = SHEETS[kind];
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(conf.name);
  if (!sheet) {
    sheet = ss.insertSheet(conf.name);
    sheet.appendRow(conf.header);
    sheet.setFrozenRows(1);
  }
  return sheet;
}
