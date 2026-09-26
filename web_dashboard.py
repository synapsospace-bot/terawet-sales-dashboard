import json
import logging
import threading
import time
import io
import csv
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse
from pathlib import Path
import os
import config
from sheets_service import LeadDataService, UPDATED_CSV_FILE
from agent_brain import TerawetAgentBrain
from gmail_service import GmailDraftService
from lead_finder import LeadFinderService

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("WebDashboard")

PORT = int(os.environ.get("PORT", 8585))

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TERAWET-ORIGINAL — Командний Центр Лідогенерації</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --primary: #007001;
    --primary-dark: #004d01;
    --accent: #ffd602;
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #1e293b;
    --muted: #64748b;
    --border: #e2e8f0;
    --warning-bg: #fef9c3;
    --warning-text: #854d0e;
    --success-bg: #dcfce7;
    --success-text: #166534;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
  body { background: var(--bg); color: var(--text); padding-bottom: 60px; }
  
  .navbar {
    background: #ffffff;
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand h1 { font-size: 20px; font-weight: 700; color: var(--primary-dark); }
  .badge-env {
    background: #e0f2fe; color: #0369a1; font-size: 12px; font-weight: 600;
    padding: 4px 10px; border-radius: 9999px;
  }
  .status-pill {
    display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500;
    background: #f1f5f9; padding: 6px 14px; border-radius: 9999px;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
  .lang-switch {
    display: inline-flex;
    background: #e2e8f0;
    border-radius: 9999px;
    padding: 3px;
    gap: 3px;
  }
  .lang-btn {
    border: none;
    background: transparent;
    padding: 5px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 700;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .lang-btn.active {
    background: #ffffff;
    color: var(--primary-dark);
    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
  }
  .lang-btn:hover:not(.active) {
    color: var(--text);
  }

  .container { max-width: 1400px; margin: 28px auto; padding: 0 24px; }

  .stats-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .stat-title { font-size: 13px; color: var(--muted); font-weight: 500; margin-bottom: 8px; }
  .stat-val { font-size: 28px; font-weight: 700; color: var(--text); }
  
  .actions-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 24px; margin-bottom: 24px; display: flex; flex-wrap: wrap;
    justify-content: space-between; align-items: center; gap: 16px;
  }
  .btn-group { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn {
    padding: 10px 18px; border-radius: 8px; font-size: 14px; font-weight: 600;
    cursor: pointer; border: none; transition: all 0.15s ease; text-decoration: none;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover { background: var(--primary-dark); }
  .btn-secondary { background: #f1f5f9; color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { background: #e2e8f0; }
  .btn-download { background: #0284c7; color: #fff; }
  .btn-download:hover { background: #0369a1; }

  .search-box {
    display: flex; gap: 12px; width: 100%; max-width: 450px;
  }
  .search-box input {
    width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px;
    font-size: 14px; outline: none;
  }
  .search-box input:focus { border-color: var(--primary); }

  .filter-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
  .tab-btn {
    padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 600;
    background: #fff; border: 1px solid var(--border); cursor: pointer; color: var(--muted);
  }
  .tab-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }

  .table-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  table { width: 100%; border-collapse: collapse; text-align: left; }
  th {
    background: #f8fafc; padding: 14px 18px; font-size: 12px; font-weight: 600;
    color: var(--muted); border-bottom: 1px solid var(--border); text-transform: uppercase;
  }
  td { padding: 14px 18px; font-size: 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:hover td { background: #f8fafc; }

  .badge-status {
    display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600;
  }
  .status-yellow { background: var(--warning-bg); color: var(--warning-text); }
  .status-green { background: var(--success-bg); color: var(--success-text); }
  .status-gray { background: #f1f5f9; color: var(--muted); }

  /* Modal */
  .modal {
    display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.5); z-index: 1000; align-items: center; justify-content: center;
  }
  .modal-content {
    background: #fff; border-radius: 12px; width: 90%; max-width: 750px;
    max-height: 85vh; overflow-y: auto; padding: 28px; box-shadow: 0 10px 25px rgba(0,0,0,0.2);
  }
  .modal-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
    border-bottom: 1px solid var(--border); padding-bottom: 14px;
  }
  .close-btn { font-size: 24px; cursor: pointer; color: var(--muted); border: none; background: none; }
  .email-preview {
    background: #fdfdfd; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;
    line-height: 1.6; font-size: 14px; color: #222;
  }
  .toast {
    position: fixed; bottom: 24px; right: 24px; background: #0f172a; color: #fff;
    padding: 12px 20px; border-radius: 8px; font-size: 14px; display: none; z-index: 2000;
  }
</style>
</head>
<body>

<div class="navbar">
  <div class="brand">
    <span style="font-size: 24px;">🌱</span>
    <div>
      <h1 data-i18n="appTitle">TERAWET-ORIGINAL Command Center</h1>
      <div style="font-size: 12px; color: var(--muted);"><span data-i18n="siteLabel">Сайт</span>: <a href="https://tera-wet.com" target="_blank" style="color: var(--primary); font-weight: 600;">tera-wet.com</a> | <span data-i18n="phoneLabel">Тел</span>: +359 888 516501</div>
    </div>
  </div>
  <div style="display: flex; align-items: center; gap: 14px;">
    <!-- Language Switcher -->
    <div class="lang-switch">
      <button type="button" class="lang-btn active" id="lang-uk" onclick="setLanguage('uk')">🇺🇦 UA</button>
      <button type="button" class="lang-btn" id="lang-bg" onclick="setLanguage('bg')">🇧🇬 BG</button>
    </div>
    <div class="status-pill">
      <div class="dot"></div>
      <span id="navEmailText">Пошта: synapso.space@gmail.com</span>
    </div>
  </div>
</div>

<div class="container">
  <!-- Stats -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-title" data-i18n="statTotal">Всього контактів у таблиці</div>
      <div class="stat-val" id="stat-total">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-title" data-i18n="statReview">🟡 Чернетки на перевірці в Gmail</div>
      <div class="stat-val" id="stat-review" style="color: #ca8a04;">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-title" data-i18n="statPending">⚪ Очікують створення чернетки</div>
      <div class="stat-val" id="stat-pending" style="color: #0284c7;">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-title" data-i18n="statSent">✅ Листи відправлено</div>
      <div class="stat-val" id="stat-sent" style="color: #16a34a;">0</div>
    </div>
  </div>

  <!-- Actions -->
  <div class="actions-card">
    <div class="search-box">
      <input type="text" id="searchInput" data-i18n-placeholder="searchPlaceholder" placeholder="🔍 Пошук за назвою, містом, email..." oninput="renderTable()">
    </div>
    <div class="btn-group">
      <button class="btn btn-primary" data-i18n="btnGenBatch" onclick="generateBatch(5)">⚡ Створити наступні 5 чернеток у Gmail</button>
      <button class="btn btn-secondary" data-i18n="btnFindLeads" onclick="findNewLeadsNow()" style="border-color: #38bdf8; color: #0369a1; background: #f0f9ff;">🔍 Знайти 20–30 лідів</button>
      <button class="btn btn-secondary" data-i18n="btnSyncSent" onclick="syncSent()" style="border-color: #86efac; color: #166534; background: #f0fdf4;">📥 Перевірити відправлені в Gmail</button>
      <button class="btn btn-secondary" data-i18n="btnRefresh" onclick="refreshData()">🔄 Оновити дані</button>
      <a href="/download/updated_csv" class="btn btn-download" data-i18n="btnDownloadCsv" download="updated_google_sheet.csv">📥 Завантажити CSV для таблиці</a>
    </div>
  </div>

  <!-- Filter Tabs -->
  <div class="filter-tabs">
    <button class="tab-btn active" data-filter="all" data-i18n="tabAll" onclick="setFilter('all', this)">Всі ліди</button>
    <button class="tab-btn" data-filter="pending" data-i18n="tabPending" onclick="setFilter('pending', this)">⚪ Очікують опрацювання</button>
    <button class="tab-btn" data-filter="review" data-i18n="tabReview" onclick="setFilter('review', this)">🟡 Чернетки на перевірці</button>
    <button class="tab-btn" data-filter="sent" data-i18n="tabSent" onclick="setFilter('sent', this)">✅ Відправлені</button>
  </div>

  <!-- Leads Table -->
  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th style="width: 50px;">#</th>
          <th data-i18n="thCompany">Компанія</th>
          <th data-i18n="thCity">Місто / Локація</th>
          <th data-i18n="thCategory">Категорія</th>
          <th data-i18n="thEmail">Email</th>
          <th data-i18n="thStatus">Статус</th>
          <th style="text-align: right;" data-i18n="thActions">Дії</th>
        </tr>
      </thead>
      <tbody id="leadsTableBody">
        <tr><td colspan="7" id="leadsTableLoading" style="text-align: center; padding: 40px; color: var(--muted);" data-i18n="loadingContacts">Завантаження контактів...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Modal -->
<div class="modal" id="previewModal">
  <div class="modal-content">
    <div class="modal-header">
      <h3 id="modalTitle" style="font-size: 18px;" data-i18n="modalTitleDefault">Перегляд чернетки</h3>
      <button class="close-btn" onclick="closeModal()">&times;</button>
    </div>
    <div style="margin-bottom: 12px; font-size: 13px; color: var(--muted);" id="modalMeta"></div>
    <div class="email-preview" id="modalBody"></div>
    <div style="margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px;">
      <button class="btn btn-secondary" data-i18n="modalClose" onclick="closeModal()">Закрити</button>
      <button class="btn btn-secondary" id="modalRegenBtn" data-i18n="modalRegenBtn" onclick="regenerateLeadText()" style="border-color: #f59e0b; color: #b45309; background: #fffbeb;">🔄 Перегенерувати текст</button>
      <button class="btn btn-primary" id="modalActionBtn" data-i18n="modalActionBtn">Створити чернетку в Gmail</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>


<script>
const I18N = {
  uk: {
    appTitle: "TERAWET-ORIGINAL Командний Центр",
    siteLabel: "Сайт",
    phoneLabel: "Тел",
    navEmail: "Пошта: synapso.space@gmail.com",
    statTotal: "Всього контактів у таблиці",
    statReview: "🟡 Чернетки на перевірці в Gmail",
    statPending: "⚪ Очікують створення чернетки",
    statSent: "✅ Листи відправлено",
    searchPlaceholder: "🔍 Пошук за назвою, містом, email...",
    btnGenBatch: "⚡ Створити наступні 5 чернеток у Gmail",
    btnFindLeads: "🔍 Знайти 20–30 лідів",
    btnSyncSent: "📥 Перевірити відправлені в Gmail",
    btnRefresh: "🔄 Оновити дані",
    btnDownloadCsv: "📥 Завантажити CSV для таблиці",
    tabAll: "Всі ліди",
    tabPending: "⚪ Очікують опрацювання",
    tabReview: "🟡 Чернетки на перевірці",
    tabSent: "✅ Відправлені",
    thNum: "#",
    thCompany: "Компанія",
    thCity: "Місто / Локація",
    thCategory: "Категорія",
    thEmail: "Email",
    thStatus: "Статус",
    thActions: "Дії",
    statusPending: "⚪ Очікує",
    statusReview: "🟡 Чернетка на перевірці",
    statusSent: "✅ Відправлено",
    btnView: "👁️ Переглянути",
    btnMarkSent: "✓ Надіслано",
    markSentTitle: "Позначити відправленим",
    emptySearch: "Нічого не знайдено",
    loadingContacts: "Завантаження контактів...",
    modalTitleDefault: "Перегляд чернетки",
    modalEmail: "Email:",
    modalCity: "Місто:",
    modalLang: "Мова:",
    modalSite: "Сайт у листі:",
    modalClose: "Закрити",
    modalRegenBtn: "🔄 Перегенерувати текст",
    modalActionBtn: "Створити чернетку в Gmail",
    subjectPrefix: "📌 Тема листа:",
    subjectRegenPrefix: "📌 Оновлена тема:",
    modalPitchLoading: "⏳ Формую персоналізовану пропозицію з урахуванням регіону...",
    modalAltLoading: "⏳ Створюю альтернативний варіант копірайтингу...",
    toastErrorLoad: "Помилка завантаження даних",
    toastGenDraft: "Генерую чернетку в Gmail...",
    toastDraftSuccess: "✅ Чернетка створена у вашому Gmail!",
    toastError: "Помилка: ",
    toastNetError: "Помилка зв'язку з сервером",
    toastGenBatchStart: "Генерую наступні {n} чернеток у Gmail...",
    toastGenBatchSuccess: "🎉 Успішно створено {n} чернеток у Gmail!",
    toastRefreshStart: "Оновлюю дані з Google Таблиці...",
    toastRefreshDone: "Дані оновлено!",
    toastSyncStart: "🔍 Сканую папку 'Надіслані' в Gmail...",
    toastSyncDone: "✅ Синхронізовано! Оновлено відправлених: {n}",
    toastSyncFail: "Не вдалося синхронізувати",
    toastMarkSentSuccess: "✅ Статус оновлено: 'Лист відправлено'!",
    toastMarkSentFail: "Помилка оновлення статусу.",
    toastRegenStart: "⏳ Перегенеровую текст листа (новий ракурс)...",
    toastRegenSuccess: "✨ Текст успішно перегенеровано! Для створення чернетки натисніть зелену кнопку.",
    toastRegenFail: "Помилка перегенерації: ",
    toastFindStart: "🔍 Шукаю та імпортую 20–30 нових агро-лідів...",
    toastFindSuccess: "🎉 Знайдено та імпортовано {n} нових лідів!",
  },
  bg: {
    appTitle: "TERAWET-ORIGINAL Команден Център",
    siteLabel: "Уебсайт",
    phoneLabel: "Тел",
    navEmail: "Имейл: synapso.space@gmail.com",
    statTotal: "Общо контакти в таблицата",
    statReview: "🟡 Чернови за проверка в Gmail",
    statPending: "⚪ Чакащи създаване на чернова",
    statSent: "✅ Изпратени писма",
    searchPlaceholder: "🔍 Търсене по име, град, имейл...",
    btnGenBatch: "⚡ Създай следващите 5 чернови в Gmail",
    btnFindLeads: "🔍 Намери 20–30 лийда",
    btnSyncSent: "📥 Провери изпратените в Gmail",
    btnRefresh: "🔄 Обнови данните",
    btnDownloadCsv: "📥 Изтегли CSV за таблицата",
    tabAll: "Всички лийдове",
    tabPending: "⚪ Чакащи обработка",
    tabReview: "🟡 Чернови за проверка",
    tabSent: "✅ Изпратени",
    thNum: "#",
    thCompany: "Компания",
    thCity: "Град / Локация",
    thCategory: "Категория",
    thEmail: "Имейл",
    thStatus: "Статус",
    thActions: "Действия",
    statusPending: "⚪ Чакащ",
    statusReview: "🟡 Чернова за проверка",
    statusSent: "✅ Изпратено",
    btnView: "👁️ Преглед",
    btnMarkSent: "✓ Изпратено",
    markSentTitle: "Маркирай като изпратено",
    emptySearch: "Няма намерени резултати",
    loadingContacts: "Зареждане на контакти...",
    modalTitleDefault: "Преглед на чернова",
    modalEmail: "Имейл:",
    modalCity: "Град:",
    modalLang: "Език:",
    modalSite: "Уебсайт в писмото:",
    modalClose: "Затвори",
    modalRegenBtn: "🔄 Прегенерирай текста",
    modalActionBtn: "Създай чернова в Gmail",
    subjectPrefix: "📌 Относно (Тема):",
    subjectRegenPrefix: "📌 Обновена тема:",
    modalPitchLoading: "⏳ Генериране на персонализирано предложение според региона...",
    modalAltLoading: "⏳ Създаване на алтернативен копирайтинг вариант...",
    toastErrorLoad: "Грешка при зареждане на данните",
    toastGenDraft: "Създаване на чернова в Gmail...",
    toastDraftSuccess: "✅ Черновата е създадена във вашия Gmail!",
    toastError: "Грешка: ",
    toastNetError: "Грешка във връзката със сървъра",
    toastGenBatchStart: "Създаване на следващите {n} чернови в Gmail...",
    toastGenBatchSuccess: "🎉 Успешно създадени {n} чернови в Gmail!",
    toastRefreshStart: "Обновяване на данни от Google Таблица...",
    toastRefreshDone: "Данните са обновени!",
    toastSyncStart: "🔍 Сканиране на папка 'Изпратени' в Gmail...",
    toastSyncDone: "✅ Синхронизирано! Обновени изпратени: {n}",
    toastSyncFail: "Синхронизацията беше неуспешна",
    toastMarkSentSuccess: "✅ Статусът е обновен: 'Писмото е изпратено'!",
    toastMarkSentFail: "Грешка при обновяване на статуса.",
    toastRegenStart: "⏳ Прегенериране на текста на писмото (нов ъгъл)...",
    toastRegenSuccess: "✨ Текстът е успешно прегенериран! За създаване на чернова натиснете зеления бутон.",
    toastRegenFail: "Грешка при прегенериране: ",
    toastFindStart: "🔍 Търсене и импортиране на 20–30 нови агро лийда...",
    toastFindSuccess: "🎉 Намерени и импортирани {n} нови лийда!",
  }
};

let currentLang = 'uk';
try {
  const urlParams = new URLSearchParams(window.location.search);
  const qLang = urlParams.get('lang');
  if (qLang && (qLang === 'uk' || qLang === 'bg')) {
    currentLang = qLang;
    localStorage.setItem('terawet_lang', currentLang);
  } else {
    const savedLang = localStorage.getItem('terawet_lang');
    if (savedLang && (savedLang === 'uk' || savedLang === 'bg')) {
      currentLang = savedLang;
    }
  }
} catch (e) {}

let leadsData = [];
let activeFilter = 'all';
let currentViewingRow = null;

function setLanguage(lang) {
  if (lang !== 'uk' && lang !== 'bg') return;
  currentLang = lang;
  try {
    localStorage.setItem('terawet_lang', lang);
  } catch (e) {}

  // Update switcher buttons
  document.querySelectorAll('.lang-btn').forEach(b => {
    if (b && b.classList) b.classList.remove('active');
  });
  const activeBtn = document.getElementById('lang-' + lang);
  if (activeBtn && activeBtn.classList) activeBtn.classList.add('active');

  const dict = I18N[currentLang] || I18N.uk;

  // Update elements with data-i18n
  document.querySelectorAll('[data-i18n]').forEach(el => {
    if (!el) return;
    const key = el.getAttribute('data-i18n');
    if (key && dict[key] !== undefined) {
      el.innerText = dict[key];
    }
  });

  // Update placeholders
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    if (!el) return;
    const key = el.getAttribute('data-i18n-placeholder');
    if (key && dict[key] !== undefined) {
      el.placeholder = dict[key];
    }
  });

  // Update nav email
  const navEmail = document.getElementById('navEmailText');
  if (navEmail) navEmail.innerText = dict.navEmail;

  // Re-render table with new translations
  renderTable();

  // If modal is open, re-render metadata
  if (currentViewingRow) {
    const lead = leadsData.find(l => l && l.row_number === currentViewingRow);
    if (lead) updateModalMeta(lead);
  }
}

let isDataLoaded = false;

async function loadData() {
  try {
    const res = await fetch('/api/leads');
    leadsData = await res.json();
    isDataLoaded = true;
    updateStats();
    renderTable();
  } catch (e) {
    showToast((I18N[currentLang] || I18N.uk).toastErrorLoad);
  }
}

function updateStats() {
  const total = leadsData.length;
  const review = leadsData.filter(l => {
    const s = (l && l.status) ? String(l.status) : '';
    return s.includes('🟡') || s.includes('DRAFT_CREATED');
  }).length;
  const sent = leadsData.filter(l => {
    const s = (l && l.status) ? String(l.status) : '';
    return s.includes('✅');
  }).length;
  const pending = leadsData.filter(l => {
    const s = (l && l.status) ? String(l.status) : '';
    return l && l.email && !s.includes('🟡') && !s.includes('✅');
  }).length;

  const stTotal = document.getElementById('stat-total');
  if (stTotal) stTotal.innerText = total;
  const stRev = document.getElementById('stat-review');
  if (stRev) stRev.innerText = review;
  const stSent = document.getElementById('stat-sent');
  if (stSent) stSent.innerText = sent;
  const stPend = document.getElementById('stat-pending');
  if (stPend) stPend.innerText = pending;
}

function setFilter(filter, btn) {
  activeFilter = filter;
  document.querySelectorAll('.filter-tabs .tab-btn').forEach(b => {
    if (b && b.classList) b.classList.remove('active');
  });
  if (btn && btn.classList) btn.classList.add('active');
  renderTable();
}

function renderTable() {
  const t = I18N[currentLang] || I18N.uk;
  const tbody = document.getElementById('leadsTableBody');
  if (!tbody) return;

  if (!isDataLoaded) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--muted);">${t.loadingContacts}</td></tr>`;
    return;
  }

  const sInput = document.getElementById('searchInput');
  const q = sInput ? sInput.value.toLowerCase() : '';
  tbody.innerHTML = '';

  const filtered = leadsData.filter(l => {
    if (!l) return false;
    const s = (l.status) ? String(l.status) : '';
    const matchText = ((l.company_name || '') + " " + (l.city || '') + " " + (l.email || '') + " " + (l.category || '')).toLowerCase().includes(q);
    if (!matchText) return false;

    if (activeFilter === 'pending') return l.email && !s.includes('🟡') && !s.includes('✅');
    if (activeFilter === 'review') return s.includes('🟡') || s.includes('DRAFT_CREATED');
    if (activeFilter === 'sent') return s.includes('✅');
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--muted);">${t.emptySearch}</td></tr>`;
    return;
  }

  filtered.forEach(lead => {
    const s = (lead && lead.status) ? String(lead.status) : '';
    let badgeClass = 'status-gray';
    let statusText = t.statusPending;
    if (s.includes('🟡') || s.includes('DRAFT_CREATED')) {
      badgeClass = 'status-yellow';
      statusText = t.statusReview;
    } else if (s.includes('✅')) {
      badgeClass = 'status-green';
      statusText = t.statusSent;
    }

    let actionButtons = `<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="viewLead(${lead.row_number})">${t.btnView}</button>`;
    if (s.includes('🟡') || s.includes('DRAFT_CREATED')) {
      actionButtons = `
        <button class="btn btn-secondary" style="padding: 6px 10px; font-size: 12px; color: #166534; border-color: #86efac; background: #f0fdf4; margin-right: 6px;" onclick="markSent(${lead.row_number}, '${lead.email || ''}')" title="${t.markSentTitle}">${t.btnMarkSent}</button>
        <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="viewLead(${lead.row_number})">${t.btnView}</button>
      `;
    }


    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="color: var(--muted); font-size: 13px;">${lead.row_number}</td>
      <td><strong>${lead.company_name}</strong></td>
      <td>${lead.city || '—'}</td>
      <td><span style="font-size: 13px; color: var(--muted);">${lead.category || '—'}</span></td>
      <td><code>${lead.email || '—'}</code></td>
      <td><span class="badge-status ${badgeClass}">${statusText}</span></td>
      <td style="text-align: right;">
        ${actionButtons}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function updateModalMeta(lead) {
  const t = I18N[currentLang];
  let langDisplay = (lead.language || 'bg').toUpperCase();
  const langMap = {
    bg: currentLang === 'bg' ? 'Български (BG)' : 'Болгарська (BG)',
    el: currentLang === 'bg' ? 'Гръцки (EL)' : 'Грецька (EL)',
    ro: currentLang === 'bg' ? 'Румънски (RO)' : 'Румунська (RO)',
    es: currentLang === 'bg' ? 'Испански (ES)' : 'Іспанська (ES)',
    it: currentLang === 'bg' ? 'Италиански (IT)' : 'Італійська (IT)',
    fr: currentLang === 'bg' ? 'Френски (FR)' : 'Французька (FR)',
    de: currentLang === 'bg' ? 'Немски / Австрия (DE)' : 'Німецька / Австрія (DE)',
    hu: currentLang === 'bg' ? 'Унгарски (HU)' : 'Угорська (HU)',
    sl: currentLang === 'bg' ? 'Словенски (SL)' : 'Словенська (SL)',
    sk: currentLang === 'bg' ? 'Словашки (SK)' : 'Словацька (SK)',
    sr: currentLang === 'bg' ? 'Сръбски (SR)' : 'Сербська (SR)',
    hr: currentLang === 'bg' ? 'Хърватски (HR)' : 'Хорватська (HR)',
    en: 'English (EN)'
  };
  if (lead.language && langMap[lead.language]) {
    langDisplay = langMap[lead.language];
  }

  document.getElementById('modalMeta').innerHTML = `
    <strong>${t.modalEmail}</strong> ${lead.email || '—'} &nbsp;|&nbsp; 
    <strong>${t.modalCity}</strong> ${lead.city || '—'} &nbsp;|&nbsp; 
    <strong>${t.modalLang}</strong> ${langDisplay} &nbsp;|&nbsp; 
    <strong>${t.modalSite}</strong> <a href="https://www.tera-wet.com" target="_blank" style="color: var(--primary); font-weight:600;">www.tera-wet.com</a>
  `;
}

async function viewLead(rowNumber) {
  currentViewingRow = rowNumber;
  const lead = leadsData.find(l => l.row_number === rowNumber);
  if (!lead) return;
  const t = I18N[currentLang];

  document.getElementById('modalTitle').innerText = lead.company_name;
  updateModalMeta(lead);

  document.getElementById('modalBody').innerHTML = `<p style="color:#64748b;">${t.modalPitchLoading}</p>`;
  document.getElementById('previewModal').style.display = 'flex';

  if (lead.generation_sheet) {
    document.getElementById('modalBody').innerHTML = lead.generation_sheet.split('\\n').join('<br>');
  } else {
    try {
      const res = await fetch(`/api/preview?row_number=${lead.row_number}`);
      const data = await res.json();
      if (data.success) {
        document.getElementById('modalBody').innerHTML = `
          <div style="margin-bottom: 14px; padding: 10px 14px; background: #f0fdf4; border-left: 4px solid #007001; border-radius: 6px; font-weight: 600; color: #007001; font-size: 14px;">
            ${t.subjectPrefix} ${data.subject}
          </div>
          ${data.body_html}
        `;
      } else {
        document.getElementById('modalBody').innerHTML = `<p style="color: #ef4444;">${t.toastError}${data.error}</p>`;
      }
    } catch (e) {
      document.getElementById('modalBody').innerHTML = `<p style="color: #ef4444;">${t.toastNetError}</p>`;
    }
  }

  const actBtn = document.getElementById('modalActionBtn');
  actBtn.innerText = t.modalActionBtn;
  actBtn.onclick = () => generateSingle(lead.row_number);
}

function closeModal() {
  document.getElementById('previewModal').style.display = 'none';
}

async function generateSingle(rowNumber) {
  const t = I18N[currentLang];
  showToast(t.toastGenDraft);
  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({row_number: rowNumber})
    });
    const result = await res.json();
    if (result.success) {
      showToast(t.toastDraftSuccess);
      closeModal();
      await loadData();
    } else {
      showToast(t.toastError + (result.error || ""));
    }
  } catch (e) {
    showToast(t.toastNetError);
  }
}

async function generateBatch(count) {
  const t = I18N[currentLang];
  showToast(t.toastGenBatchStart.replace('{n}', count));
  try {
    const res = await fetch('/api/generate_batch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({count: count})
    });
    const result = await res.json();
    if (result.success) {
      showToast(t.toastGenBatchSuccess.replace('{n}', result.processed));
      await loadData();
    } else {
      showToast(t.toastError + (result.error || ""));
    }
  } catch (e) {
    showToast(t.toastNetError);
  }
}

async function refreshData() {
  const t = I18N[currentLang];
  showToast(t.toastRefreshStart);
  try {
    await fetch('/api/refresh');
  } catch (e) {}
  await loadData();
  showToast(t.toastRefreshDone);
}

async function syncSent() {
  const t = I18N[currentLang];
  showToast(t.toastSyncStart);
  try {
    const res = await fetch('/api/sync_sent');
    const data = await res.json();
    if (data.success) {
      showToast(t.toastSyncDone.replace('{n}', data.updated));
      await loadData();
    } else {
      showToast(t.toastError + (data.error || t.toastSyncFail));
    }
  } catch (e) {
    showToast(t.toastNetError);
  }
}

async function markSent(rowNumber, email) {
  const t = I18N[currentLang];
  try {
    const res = await fetch('/api/mark_status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({row_number: rowNumber, email: email, status: '✅ Лист відправлено'})
    });
    const data = await res.json();
    if (data.success) {
      showToast(t.toastMarkSentSuccess);
      await loadData();
    }
  } catch (e) {
    showToast(t.toastMarkSentFail);
  }
}

async function regenerateLeadText() {
  if (!currentViewingRow) return;
  const t = I18N[currentLang];
  showToast(t.toastRegenStart);
  document.getElementById('modalBody').innerHTML = `<p style="color:#64748b;">${t.modalAltLoading}</p>`;
  try {
    const res = await fetch('/api/regenerate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({row_number: currentViewingRow})
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('modalBody').innerHTML = `
        <div style="margin-bottom: 14px; padding: 10px 14px; background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 6px; font-weight: 600; color: #92400e; font-size: 14px;">
          ${t.subjectRegenPrefix} ${data.subject}
        </div>
        ${data.body_html}
      `;
      showToast(t.toastRegenSuccess);
      await loadData();
    } else {
      showToast(t.toastRegenFail + (data.error || ""));
    }
  } catch (e) {
    showToast(t.toastNetError);
  }
}

async function findNewLeadsNow() {
  const t = I18N[currentLang];
  showToast(t.toastFindStart);
  try {
    const res = await fetch('/api/find_leads', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({count: 25})
    });
    const data = await res.json();
    if (data.success) {
      showToast(t.toastFindSuccess.replace('{n}', data.imported));
      await loadData();
    } else {
      showToast(t.toastError + (data.error || ""));
    }
  } catch (e) {
    showToast(t.toastNetError);
  }
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.innerText = msg;
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 3500);
}

// Init
setLanguage(currentLang);
loadData();

</script>
</body>
</html>
"""

class DashboardHandler(BaseHTTPRequestHandler):
    data_service = LeadDataService()
    agent_brain = TerawetAgentBrain()
    draft_service = GmailDraftService()
    finder_service = LeadFinderService(data_service=data_service)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif path == "/api/leads":
            leads = self.data_service.get_all_leads()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(leads, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/refresh":
            try:
                self.data_service._sync_live_sheet()
            except Exception as e:
                logger.warning(f"Refresh live sheet notice: {e}")
            leads = self.data_service.get_all_leads()
            self.send_json({"success": True, "count": len(leads)})

        elif path == "/api/sync_sent":
            try:
                updated = self.data_service.sync_sent_emails(self.draft_service)
                self.send_json({"success": True, "updated": updated})
            except Exception as e:
                logger.error(f"Sync sent error: {e}")
                self.send_json({"success": False, "error": str(e)})

        elif path == "/api/preview":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                row_num = int(query.get("row_number", ["0"])[0])
            except ValueError:
                row_num = 0
            leads = self.data_service.get_all_leads()
            target = next((l for l in leads if l["row_number"] == row_num), None)
            if target:
                email = target.get("email", "").strip().lower()
                cached = self.data_service.state.get(email, {})
                variant = cached.get("variant", 0)
                subj, body_html, body_plain = self.agent_brain.generate_pitch(target, variant=variant)
                self.send_json({"success": True, "subject": subj, "body_html": body_html, "body_plain": body_plain})
            else:
                self.send_json({"success": False, "error": "Lead not found"})

        elif path == "/download/updated_csv":
            self.data_service.export_updated_csv()
            if UPDATED_CSV_FILE.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="updated_google_sheet.csv"')
                self.end_headers()
                with open(UPDATED_CSV_FILE, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File not found")

        elif path in ("/api/sheets_feed.csv", "/download/sheets_feed.csv"):
            leads = self.data_service.get_all_leads()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Компанія", "Категорія", "Місто", "Мова", "Email", "Телефон", "Сайт", "Статус", "Дата", "Тема листа"])
            for l in leads:
                email = l.get("email", "").strip().lower()
                cached = self.data_service.state.get(email, {})
                subject = cached.get("subject", "")
                if not subject and "Subject:" in l.get("generation_sheet", ""):
                    subject = l["generation_sheet"].split("\n")[0].replace("Subject:", "").strip()
                writer.writerow([
                    l.get("row_number", ""),
                    l.get("company_name", ""),
                    l.get("category", ""),
                    l.get("city", ""),
                    l.get("language", "").upper(),
                    l.get("email", ""),
                    l.get("phone", ""),
                    l.get("website", ""),
                    l.get("status", ""),
                    l.get("date", ""),
                    subject
                ])
            csv_bytes = output.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(csv_bytes)
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query_params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                body_params = json.loads(body) if body else {}
            except Exception:
                body_params = {}

            params = {**query_params, **body_params}

            if path == "/api/generate":
                row_num = params.get("row_number")
                leads = self.data_service.get_all_leads()
                target = next((l for l in leads if l["row_number"] == row_num), None)

                if not target or not target["email"]:
                    self.send_json({"success": False, "error": "Lead not found or missing email"})
                    return

                try:
                    email = target.get("email", "").strip().lower()
                    cached = self.data_service.state.get(email, {})
                    variant = cached.get("variant", 0)
                    subject, body_html, body_plain = self.agent_brain.generate_pitch(target, variant=variant)
                    draft_id = self.draft_service.create_draft(
                        to_email=target["email"],
                        subject=subject,
                        body_html=body_html,
                        body_plain=body_plain,
                        company_name=target["company_name"]
                    )
                    self.data_service.mark_draft_created(target, draft_id, subject, body_plain)
                    self.send_json({"success": True, "draft_id": draft_id})
                except Exception as e:
                    logger.error(f"Error generating single draft: {e}", exc_info=True)
                    self.send_json({"success": False, "error": str(e)})

            elif path == "/api/regenerate":
                row_num = params.get("row_number")
                leads = self.data_service.get_all_leads()
                target = next((l for l in leads if l["row_number"] == row_num), None)

                if not target:
                    self.send_json({"success": False, "error": "Lead not found"})
                    return

                try:
                    email = target.get("email", "").strip().lower()
                    key = email if email else f"row_{row_num}"
                    cached = self.data_service.state.get(key, {})
                    current_variant = cached.get("variant", 0) + 1
                    cached["variant"] = current_variant

                    subject, body_html, body_plain = self.agent_brain.generate_pitch(target, variant=current_variant)
                    cached["subject"] = subject
                    cached["generation_sheet"] = f"Subject: {subject}\n\n{body_plain}"
                    self.data_service.state[key] = cached
                    self.data_service._save_state()
                    self.data_service.export_updated_csv()

                    self.send_json({
                        "success": True, 
                        "subject": subject, 
                        "body_html": body_html, 
                        "body_plain": body_plain,
                        "variant": current_variant
                    })
                except Exception as e:
                    logger.error(f"Error regenerating pitch: {e}", exc_info=True)
                    self.send_json({"success": False, "error": str(e)})

            elif path == "/api/find_leads":
                count = int(params.get("count", 25))
                try:
                    imported = self.finder_service.find_and_import_leads(count=count)
                    self.send_json({"success": True, "imported": imported})
                except Exception as e:
                    logger.error(f"Error finding leads: {e}", exc_info=True)
                    self.send_json({"success": False, "error": str(e)})

            elif path == "/api/generate_batch":
                count = int(params.get("count", 5))
                new_leads = self.data_service.get_new_leads()[:count]

                processed = 0
                for lead in new_leads:
                    try:
                        email = lead.get("email", "").strip().lower()
                        cached = self.data_service.state.get(email, {})
                        variant = cached.get("variant", 0)
                        subject, body_html, body_plain = self.agent_brain.generate_pitch(lead, variant=variant)
                        draft_id = self.draft_service.create_draft(
                            to_email=lead["email"],
                            subject=subject,
                            body_html=body_html,
                            body_plain=body_plain,
                            company_name=lead["company_name"]
                        )
                        self.data_service.mark_draft_created(lead, draft_id, subject, body_plain)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Error generating batch draft: {e}")

                self.send_json({"success": True, "processed": processed})

            elif path == "/api/mark_status":
                row_num = params.get("row_number")
                email = params.get("email", "")
                new_status = params.get("status", "✅ Лист відправлено")
                key = email.strip().lower() if email else f"row_{row_num}"
                self.data_service.mark_status(key, new_status)
                self.send_json({"success": True})
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            logger.error(f"Unhandled error in do_POST: {e}", exc_info=True)
            try:
                self.send_json({"success": False, "error": str(e)})
            except Exception:
                pass

    def send_json(self, data: dict):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        # Suppress socket noise and client disconnection traces
        msg = format % args
        if "Broken pipe" in msg or "Connection reset" in msg:
            return
        logger.info(f"{self.client_address[0]} - {msg}")

def _daily_lead_search_scheduler():
    """Background scheduler that automatically searches 20-30 leads every day at 09:00 AM."""
    logger.info("Daily lead search scheduler initialized (runs automatically every morning at 09:00 AM).")
    last_run_date = None

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            # Trigger if it's 9:00 AM or later and hasn't run today yet
            if now.hour >= 9 and last_run_date != today_str:
                logger.info("⏰ [09:00 AM TRIGGER] Running daily automated lead search (20-30 leads)...")
                imported = DashboardHandler.finder_service.find_and_import_leads(count=25)
                logger.info(f"Daily lead search finished: {imported} leads imported.")
                last_run_date = today_str
        except Exception as e:
            logger.error(f"Daily scheduler exception: {e}")
        time.sleep(30)

def _periodic_background_syncer():
    """Silently syncs live Google Sheet & Gmail sent emails in background every 4 minutes without blocking UI."""
    time.sleep(10)
    while True:
        try:
            DashboardHandler.data_service._sync_live_sheet()
            DashboardHandler.data_service.sync_sent_emails(DashboardHandler.draft_service)
        except Exception as e:
            logger.debug(f"Background syncer notice: {e}")
        time.sleep(240)

class RobustThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Ignore client abrupt disconnects cleanly
        pass

def start_server():
    sched_thread = threading.Thread(target=_daily_lead_search_scheduler, daemon=True)
    sched_thread.start()

    sync_thread = threading.Thread(target=_periodic_background_syncer, daemon=True)
    sync_thread.start()

    while True:
        try:
            server = RobustThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
            print(f"🚀 TERAWET Web Dashboard is running at: http://localhost:{PORT}")
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping dashboard by user interrupt.")
            break
        except Exception as e:
            logger.error(f"Server socket error: {e}. Auto-restarting in 2 seconds...")
            time.sleep(2)

if __name__ == "__main__":
    start_server()
