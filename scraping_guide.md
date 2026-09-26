# Інструкція з пошуку та парсингу B2B-клієнтів для TeraWet (Європа)

Ця інструкція містить готові пошукові запити для швидкого збору бази фермерів, розсадників, виноробень та агро-дистриб'юторів у ключових сільськогосподарських країнах Європи з дефіцитом вологи.

---

## 1. Рекомендовані сервіси для збору контактів

1. **[Outscraper (Google Maps Scraper)](https://outscraper.com)**: витягує назву, сайт, робочий email, телефон, категорію та рейтинг напряму з карт.
2. **[Apify (Google Maps Extractor)](https://apify.com)**: швидкий хмарний парсер із вивантаженням у CSV.
3. **[Apollo.io](https://apollo.io)**: вихід на ключових осіб (Head of Agronomy, Procurement, Owner) великих кооперативів та дистриб'юторів.

---

## 2. Пошукові запити рідними мовами (Search Queries)

### 🇪🇸 Іспанія (Найбільший ринок посухи в ЄС)
*Регіони гострої засухи: Andalucía (Sevilla, Córdoba, Jaén), Murcia, Comunidad Valenciana, Cataluña.*

| Ніша | Запит для Google Maps / Outscraper | Цільовий продукт TeraWet |
| :--- | :--- | :--- |
| **Оливкові гаї** | `almazara olivar`, `productor de aceite de oliva`, `finca olivos` | T400 (15 г під дерево) |
| **Виноградники** | `bodega viticultura`, `viñedos`, `elaborador de vino` | T400 (10–15 г під лозу) |
| **Розсадники рослин** | `vivero de plantas`, `vivero viticola`, `plantones de olivo` | T100 паста-гель (100% приживлення) |
| **Овочі та ягідники** | `cooperativa hortofruticola`, `productor frutos rojos Huelva` | T400 (2 кг/декар) |
| **Дистриб'ютори** | `distribuidor fertilizantes fitosanitarios`, `suministros agricolas` | Дистрибуція / гурт |

---

### 🇮🇹 Італія (Виноградарство, сади, криза зрошення в басейні По та на півдні)
*Регіони: Toscana, Puglia, Sicilia, Emilia-Romagna, Veneto.*

| Ніша | Запит для Google Maps / Outscraper | Цільовий продукт TeraWet |
| :--- | :--- | :--- |
| **Виноробні та лози** | `azienda vitivinicola`, `cantina vinicola`, `viticoltore` | T400 (10–15 г під лозу) |
| **Розсадники** | `vivaio piante`, `barbatelle vite`, `vivai frutticoli` | T100 паста для коренів |
| **Оливкові господарства**| `frantoio oleario`, `oliveto azienda agricola` | T400 під дерево |
| **Агромагазини / Опт** | `consorzio agrario`, `vendita concimi fitofarmaci` | B2B Дистрибуція |

---

### 🇫🇷 Франція (Суворі префектурні заборони на полив улітку)
*Регіони: Languedoc-Roussillon, Provence, Bordeaux, Vallée du Rhône.*

| Ніша | Запит для Google Maps / Outscraper | Цільовий продукт TeraWet |
| :--- | :--- | :--- |
| **Виноробство** | `domaine viticole`, `château vignoble`, `exploitant viticole` | T400 під корінь |
| **Розсадники** | `pépinière viticole`, `pépinière arboricole`, `plants de vigne` | T100 паста (5–8 г/л) |
| **Сади та овочівництво**| `arboriculture fruitière`, `maraîchage biologique` | T400 (20 кг/га) |
| **Агропостачальники** | `négoce agricole`, `coopérative agricole approvisionnement` | Партнерство / опт |

---

### 🇵🇹 Португалія (Спекотний Алентежу та долина Доуро)
*Регіони: Alentejo (Beja, Évora), Douro, Ribatejo.*

* `quinta vinícola`, `produtor de vinho` (виноробні)
* `olival superintensivo`, `lagar de azeite` (оливи)
* `viveiro de plantas florestais e fruteiras` (розсадники)
* `cooperativa agrícola distribuição` (дистриб'ютори)

---

### 🇭🇷 Хорватія (Кам'янистий карст, дефіцит вологи)
*Регіони: Istra, Dalmacija, Slavonija.*

* `vinarija vinogradi` (виноробні)
* `maslinici proizvodnja ulja` (оливкові плантації)
* `rasadnik vocnih sadnica` (розсадники саджанців)
* `poljoprivredna ljekarna` (агроаптеки/гурт)

---

### 🇸🇮 Словенія
*Регіони: Goriška, Primorska, Podravska.*

* `vinogradništvo klet` (виноробство)
* `sadjarstvo nasadi` (плодові сади)
* `drevesnica sadike` (розсадники дерев)
* `kmetijska zadruga trgovina` (сільгоспкооперативи)

---

### 🇸🇰 Словаччина
*Регіони: Podunajsko, Tokaj, Záhorie.*

* `vinohradníctvo vinárstvo` (виноробні)
* `ovocné sady pestovateľ` (плодівництво)
* `okrasná škôlka sadenice` (декоративні та плодові розсадники)
* `poľnohospodárske družstvo` (агрокооперативи)

---

### 🇷🇴 Румунія, 🇧🇬 Болгарія, 🇬🇷 Греція
*Детальні запити за цими країнами збережені в основному реєстрі (див. `leads_sample.csv`).*

---

## 3. Валідація email та імпорт
1. Перевіряйте адреси через [NeverBounce](https://neverbounce.com) або [Debounce.io](https://debounce.io).
2. Залишайте тільки статус `Valid`.
3. Додавайте контакти в `leads_sample.csv` або вашу Google Таблицю зі статусом `NEW`.
