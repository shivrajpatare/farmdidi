const SPREADSHEET_ID = '1emB-iOq1KQdMTYrgL9Hl5fX8UvpAJ0dLvBVG2Skmz0A';
const SHEET_NAME = 'Daily Check-ins';


function doGet() {
  try {
    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);

    if (!sheet) {
      return jsonResponse({
        success: false,
        error: 'Worksheet not found'
      });
    }

    return jsonResponse({
      success: true,
      service: 'FarmDidi Google Sheets',
      sheet: SHEET_NAME
    });

  } catch (error) {
    return jsonResponse({
      success: false,
      error: 'Unable to access spreadsheet'
    });
  }
}


function doPost(request) {
  try {
    if (
      !request ||
      !request.postData ||
      !request.postData.contents
    ) {
      return jsonResponse({
        success: false,
        error: 'Request body is missing'
      });
    }

    const body = JSON.parse(request.postData.contents);
    const record = body.record;

    if (!record) {
      return jsonResponse({
        success: false,
        error: 'Record is required'
      });
    }

    // Safety check: Apps Script should only receive
    // already-confirmed records from the backend.
    if (record.status !== 'confirmed') {
      return jsonResponse({
        success: false,
        error: 'Only confirmed records can be written'
      });
    }

    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);

    if (!sheet) {
      return jsonResponse({
        success: false,
        error: 'Worksheet not found'
      });
    }

    const row = [
      record.date || '',
      record.didi_id || '',
      record.didi_name || '',
      record.production_status || '',
      record.product || '',
      record.quantity === null || record.quantity === undefined
        ? ''
        : record.quantity,
      record.unit || '',
      record.has_issue === true,
      record.issue_type || '',
      record.issue || '',
      record.issue_details || '',
      record.status || ''
    ];

    sheet.appendRow(row);

    return jsonResponse({
      success: true,
      sheet: SHEET_NAME,
      row_written: true
    });

  } catch (error) {
    return jsonResponse({
      success: false,
      error: 'Invalid record payload'
    });
  }
}


function jsonResponse(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}