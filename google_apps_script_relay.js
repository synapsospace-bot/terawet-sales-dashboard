/**
 * TERAWET-ORIGINAL Cloud Email Relay & Google Sheet Sync
 * 
 * Надає 100% хмарну автономну відправку з Render через HTTPS (Порт 443).
 * Листи надсилаються безпосередньо з вашого акаунту Gmail (synapso.space@gmail.com)
 * і автоматично з'являються у папці "Надіслані" (Sent) у Gmail!
 */

var SECRET_TOKEN = "terawet_secure_sync_2026";

function doGet(e) {
  var remainingQuota = MailApp.getRemainingDailyQuota();
  var userEmail = Session.getActiveUser().getEmail();
  return ContentService.createTextOutput(JSON.stringify({
    status: "ok",
    message: "TERAWET Google Apps Script Relay активний!",
    email_user: userEmail,
    remaining_daily_quota: remainingQuota
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var raw = e.postData.contents;
    var params = JSON.parse(raw);

    // Перевірка секретного токена
    if (params.secret && params.secret !== SECRET_TOKEN) {
      return ContentService.createTextOutput(JSON.stringify({
        success: false,
        error: "Невірний секретний токен"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var action = params.action || "send_email";

    // 1. Тест зв'язку
    if (action === "test" || action === "test_connection") {
      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        message: "Google Apps Script Relay успішно підключено!",
        user: Session.getActiveUser().getEmail(),
        quota: MailApp.getRemainingDailyQuota()
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 2. Пряма відправка листа через GmailApp
    if (action === "send_email" || action === "send") {
      var to = (params.to || "").trim();
      var subject = params.subject || "";
      var bodyPlain = params.body_plain || "";
      var bodyHtml = params.body_html || "";
      var senderName = params.sender_name || "Dmytro Bendyk | TERAWET-ORIGINAL";
      var replyTo = params.reply_to || "terawet.original@gmail.com";

      if (!to || !subject) {
        return ContentService.createTextOutput(JSON.stringify({
          success: false,
          error: "Відсутні обов'язкові поля: to або subject"
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var quota = MailApp.getRemainingDailyQuota();
      if (quota < 1) {
        return ContentService.createTextOutput(JSON.stringify({
          success: false,
          error: "Вичерпано денний ліміт відправки Google (Daily Quota Exceeded)"
        })).setMimeType(ContentService.MimeType.JSON);
      }

      // Відправка листа напряму з Gmail
      GmailApp.sendEmail(to, subject, bodyPlain, {
        htmlBody: bodyHtml,
        name: senderName,
        replyTo: replyTo
      });

      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        status: "ok",
        message: "Лист успішно надіслано через GmailApp",
        remaining_quota: quota - 1
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 3. Створення чернетки в Gmail
    if (action === "create_draft" || action === "draft") {
      var draft = GmailApp.createDraft(
        params.to,
        params.subject,
        params.body_plain || "",
        {
          htmlBody: params.body_html || "",
          name: params.sender_name || "Dmytro Bendyk | TERAWET-ORIGINAL",
          replyTo: params.reply_to || "terawet.original@gmail.com"
        }
      );
      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        draft_id: draft.getId(),
        message: "Чернетку збережено в Gmail"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: "Невідома дія: " + action
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Щоденний автономний тригер для Google Apps Script (Таймер по часу: щодня о 09:00 - 10:00).
 * Будить Render і запускає відправку 50 лідів напряму.
 */
function triggerDailyOutreach() {
  var url = "https://terawet-sales-dashboard.onrender.com/api/outreach/start";
  var options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ count: 50, mode: "send" }),
    muteHttpExceptions: true
  };
  try {
    var response = UrlFetchApp.fetch(url, options);
    Logger.log("Trigger response: " + response.getContentText());
  } catch (e) {
    Logger.log("Trigger error: " + e.toString());
  }
}

