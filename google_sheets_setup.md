# Підключення вашої Google Таблиці до TeraWet Agent (За 1 хвилину)

Цей спосіб дозволяє підключити **будь-яку вашу Google Таблицю з лідами** напряму до агента без створення складних проектів у Google Cloud та без встановлення сторонніх бібліотек.

Скрипт читатиме нові контакти зі статусом `NEW` і **в реальному часі оновлюватиме рядок у Google Таблиці** на `DRAFT_CREATED` з темою та ID чернетки, щойно лист з'явиться у вашому Gmail!

---

## Крок 1. Перевірте назви колонок у вашій таблиці

У першому рядку вашої таблиці мають бути такі стовпчики (порядок не має значення):
* **`company_name`** (назва компанії)
* **`website`** (сайт компанії)
* **`country`** (країна: Spain, Italy, Romania, Bulgaria тощо)
* **`language`** (код мови: `es`, `it`, `fr`, `ro`, `bg`, `el`, `pt`, `hr`, `sl`, `sk`, `en`)
* **`crops`** (культури: виноградники, оливи, сади, овочі)
* **`contact_person`** (ім'я агронома або директора)
* **`email`** (робоча пошта)
* **`status`** (початково вкажіть **`NEW`**)
* **`draft_id`** (сюди агент запише ID чернетки)
* **`generated_subject`** (сюди агент запише згенеровану тему листа)

---

## Крок 2. Додайте скрипт синхронізації (15 секунд)

1. Відкрийте вашу Google Таблицю.
2. У верхньому меню натисніть:  
   **Розширення (Extensions)** ➔ **Apps Script**.
3. Видаліть весь стандартний код у вікні редактора і вставте цей готовий скрипт:

```javascript
function doGet(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    return ContentService.createTextOutput("[]").setMimeType(ContentService.MimeType.JSON);
  }
  var headers = data[0];
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      row[headers[j]] = data[i][j];
    }
    row["_row_number"] = i + 1;
    rows.push(row);
  }
  return ContentService.createTextOutput(JSON.stringify(rows)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var params = JSON.parse(e.postData.contents);
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var statusCol = headers.indexOf("status") + 1;
  var draftCol = headers.indexOf("draft_id") + 1;
  var subjectCol = headers.indexOf("generated_subject") + 1;
  
  var row = params.row_number;
  if (statusCol > 0 && params.status) {
    sheet.getRange(row, statusCol).setValue(params.status);
  }
  if (draftCol > 0 && params.draft_id) {
    sheet.getRange(row, draftCol).setValue(params.draft_id);
  }
  if (subjectCol > 0 && params.generated_subject) {
    sheet.getRange(row, subjectCol).setValue(params.generated_subject);
  }
  
  return ContentService.createTextOutput(JSON.stringify({status: "ok"})).setMimeType(ContentService.MimeType.JSON);
}
```

---

## Крок 3. Розгорніть як веб-додаток (Web App)

1. У правому верхньому кутку редактора Apps Script натисніть синю кнопку **Розгорнути (Deploy)** ➔ **Нове розгортання (New deployment)**.
2. Натисніть на значок шестерні біля "Виберіть тип" та оберіть **Веб-додаток (Web app)**.
3. Заповніть параметри:
   * **Опис:** `TeraWet Sync`
   * **Виконувати від імені:** `Я (ваш email)`
   * **Хто має доступ (Who has access):** **Будь-хто (Anyone)** *(це необхідно, щоб локальний скрипт міг звертатися до таблиці)*.
4. Натисніть **Розгорнути (Deploy)**, надайте доступ і скопіюйте отриману адресу **URL-адресу веб-додатка**  
   *(вона має вигляд: `https://script.google.com/macros/s/AKfycb.../exec`)*.

---

## Крок 4. Додайте URL у `.env`

Відкрийте файл `.env` у папці `terawet_sales_agent` і вставте посилання:

```env
GOOGLE_SHEET_WEBHOOK_URL=https://script.google.com/macros/s/ВАШ_СКРИПТ/exec
```

---

## Крок 5. Готово! Запустіть агента

Тепер просто виконайте:
```bash
python3 main.py
```
* Агент автоматично підтягне контакти зі статусом `NEW` з вашої Google Таблиці.
* Згенерує листи з посиланням на **`https://tera-wet.com`**.
* Збереже чернетки у вашому **Gmail**.
* **Одразу оновить статус клієнта у вашій Google Таблиці** на `DRAFT_CREATED` та запише тему листа й ID!
