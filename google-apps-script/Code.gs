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
 *    index.html 안의 FAVORITES_WEBAPP_URL 값으로 붙여넣는다.
 * 6. 이후 시트를 다시 열어보면 첫 즐겨찾기가 저장될 때 자동으로
 *    "즐겨찾기" 라는 이름의 시트 탭이 만들어지고 거기에 쌓인다.
 */

const SHEET_NAME = "즐겨찾기";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = getOrCreateSheet_();

    sheet.appendRow([
      new Date(),          // 저장된 시각
      data.action || "즐겨찾기",
      data.region_name || "",
      data.category || "",
      data.title || "",
      data.dept || "",
      data.date || "",
      data.url || "",
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(["저장시각", "동작", "지역", "분야", "제목", "담당부서", "등록일", "링크"]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}
