import json
import logging
from typing import Dict, Any, Tuple
from pathlib import Path
import config

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "ro": "Romanian (Limba română)",
    "bg": "Bulgarian (Български език)",
    "el": "Greek (Ελληνικά)",
    "es": "Spanish (Español)",
    "it": "Italian (Italiano)",
    "fr": "French (Français)",
    "de": "German / Austrian (Deutsch)",
    "hu": "Hungarian (Magyar)",
    "sl": "Slovenian (Slovenščina)",
    "sk": "Slovak (Slovenčina)",
    "pt": "Portuguese (Português)",
    "hr": "Croatian (Hrvatski)",
    "sr": "Serbian (Српски)",
    "en": "English"
}

SIGNATURE_HTML = """
<div style="margin-top: 28px; padding-top: 18px; border-top: 2px solid #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b;">
  <p style="margin: 0 0 12px 0;">
    <strong>Vanya Kolarova</strong><br>
    📞 <a href="tel:+359888516501" style="color: #007001; text-decoration: none; font-weight: 600;">+359888516501</a>
  </p>
  <p style="margin: 0 0 12px 0;">
    <strong>Bendyk Dmytro</strong><br>
    <span style="color: #64748b; font-size: 13px;">Sales Manager at TeraWet</span><br>
    📞 Phone/WhatsApp: <a href="tel:+380502365858" style="color: #007001; text-decoration: none;">+380502365858</a> / <a href="tel:+359889175452" style="color: #007001; text-decoration: none;">+359889175452</a><br>
    ✉️ Email: <a href="mailto:Terawet.original@gmail.com" style="color: #007001; text-decoration: none;">Terawet.original@gmail.com</a><br>
    🌐 Website: <a href="https://www.tera-wet.com" target="_blank" style="color: #007001; font-weight: bold; text-decoration: underline;">www.tera-wet.com</a>
  </p>
  <p style="margin: 0 0 15px 0; font-size: 13px;">
    📘 Facebook: <a href="https://www.facebook.com/share/1HQAp8QqRt/" target="_blank" style="color: #1877f2; text-decoration: underline;">https://www.facebook.com/share/1HQAp8QqRt/</a><br>
    📷 Instagram: <a href="https://www.instagram.com/terawet.original" target="_blank" style="color: #e4405f; text-decoration: underline;">https://www.instagram.com/terawet.original</a><br>
    💼 LinkedIn: <a href="https://www.linkedin.com/in/terawet-теравет-a7ba0a3b3" target="_blank" style="color: #0a66c2; text-decoration: underline;">https://www.linkedin.com/in/terawet-теравет-a7ba0a3b3</a>
  </p>
</div>
"""

SIGNATURE_PLAIN = """
Vanya Kolarova
+359888516501

Bendyk Dmytro
Sales Manager at TeraWet
Phone/WhatsApp: +380502365858 / +359889175452
Email: Terawet.original@gmail.com
Website: www.tera-wet.com
Facebook: https://www.facebook.com/share/1HQAp8QqRt/
Instagram: https://www.instagram.com/terawet.original
LinkedIn: https://www.linkedin.com/in/terawet-теравет-a7ba0a3b3
"""

class TerawetAgentBrain:
    """
    AI Agricultural Sales Copywriter & Technical Agronomist for TERAWET-ORIGINAL®.
    Generates high-converting, deeply researched outreach emails that highlight:
      1. Specific climatic and hydrological challenges of the lead's location.
      2. The agronomic superiority of potassium hydrogel (400x water capacity, subterranean reservoir).
      3. The transformational benefits for the farm (50% water cut, 2x pump savings, 30-40% fertilizer retention,
         heat stress elimination, 100% sapling survival, 7-10 years in soil).
      4. Crop-specific application rates and direct order links to https://www.tera-wet.com.
      5. Clickable official team signature.
    """

    def __init__(self):
        self.knowledge_base = self._load_knowledge_base()
        self.openai_client = None
        
        if config.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI client: {e}")

    def _load_knowledge_base(self) -> Dict[str, Any]:
        kb_file = config.KNOWLEDGE_BASE_PATH
        if Path(kb_file).exists():
            with open(kb_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def generate_pitch(self, lead: Dict[str, str], variant: int = 0) -> Tuple[str, str, str]:
        lang = lead.get("language", "en").lower().strip()
        if lang not in SUPPORTED_LANGUAGES:
            lang = "en"

        # Check if lead dictionary itself contains a variant offset
        if not variant and "variant" in lead:
            try:
                variant = int(lead["variant"])
            except (ValueError, TypeError):
                variant = 0

        subject, body_html, body_plain = "", "", ""
        if self.openai_client and config.OPENAI_API_KEY:
            try:
                subject, body_html, body_plain = self._generate_with_llm(lead, lang)
            except Exception as e:
                logger.error(f"LLM generation failed: {e}. Falling back to copywriter template.")

        if not subject:
            subject, body_html, body_plain = self._generate_with_template(lead, lang, variant=variant)
        else:
            # If generated by LLM, ensure partnership block is included if omitted
            if not any(k in body_html.lower() for k in ["представницт", "представништв", "predstavništv", "dealership", "distribut", "partner", "αντιπροσωπε"]):
                part_html, part_plain = self._get_partnership_proposal(lang)
                body_html = body_html + "\n\n" + part_html
                body_plain = body_plain + "\n\n" + part_plain

        # Attach official team signature with clickable links
        body_html, body_plain = self._append_official_signature(body_html, body_plain, lang)
        return subject, body_html, body_plain

    def _append_official_signature(self, body_html: str, body_plain: str, lang: str) -> Tuple[str, str]:
        optouts = {
            "ro": "Dacă doriți dezabonarea de la aceste comunicări profesionale, răspundeți cu 'Dezabonare'.",
            "bg": "Ако не желаете да получавате професионални съобщения от нас, отговорете с 'Отказ'.",
            "el": "Εάν δεν επιθυμείτε να λαμβάνετε περαιτέρω επαγγελματικές ενημερώσεις, παρακαλούμε απαντήστε με 'Διαγραφή'.",
            "es": "Para no recibir más comunicaciones profesionales B2B, responda con 'Baja'.",
            "it": "Per disiscriversi da future comunicazioni B2B, risponda 'Cancellami'.",
            "fr": "Pour vous désinscrire de ces communications professionnelles, répondez 'Désinscription'.",
            "de": "Wenn Sie keine weiteren fachlichen Mitteilungen erhalten möchten, antworten Sie bitte mit 'Abmelden'.",
            "hu": "Amennyiben nem kíván több szakmai megkeresést kapni, kérjük, válaszoljon a 'Leiratkozás' szóval.",
            "sl": "Za odjavo od strokovnih obvestil odgovorite z 'Odjava'.",
            "sk": "Ak si neželáte dostávať ďalšie odborné správy, odpovedzte 'Odhlásiť'.",
            "pt": "Para cancelar a subscrição, responda com 'Remover'.",
            "sr": "Уколико не желите да примате ове пословне информације, одговорите са 'Одјава'.",
            "hr": "Ako ne želite primati daljnje poslovne obavijesti, odgovorite s 'Odjava'.",
            "en": "If you prefer not to receive future communications, please reply with 'Unsubscribe'."
        }
        optout_text = optouts.get(lang, optouts["en"])

        html_out = body_html + SIGNATURE_HTML + f"""
<hr style="border:0;border-top:1px solid #e0e0e0;margin-top:20px;">
<p style="font-size:11px;color:#888;margin:0;">{optout_text}</p>
"""
        plain_out = body_plain + "\n\n---\n" + SIGNATURE_PLAIN.strip() + f"\n\n---\n{optout_text}"
        return html_out, plain_out

    def _detect_region_context(self, lead: Dict[str, str]) -> Dict[str, str]:
        """
        Analyzes city, address, crops, company name and extracts specific regional
        climatic challenges and positive agronomic transformations.
        """
        city = (lead.get("city") or "").strip()
        addr = (lead.get("adress") or lead.get("address") or "").strip()
        crops = (lead.get("crops") or lead.get("category") or "").strip()
        text = f"{city} {addr} {crops}".lower()

        # 1. Thessaly (Λάρισα, Τρίκαλα, Καρδίτσα, Βόλος, Αλμυρός, Ελασσόνα)
        if any(k in text for k in ['λάρισα', 'larissa', 'τρίκαλα', 'trikala', 'καρδίτσα', 'karditsa', 'βόλος', 'volos', 'αλμυρός', 'almyros', 'ελασσόνα', 'elassona', 'thessaly']):
            return {
                "region_key": "thessaly",
                "region_name_el": "στη Θεσσαλία",
                "region_name_bg": "в Тесалия",
                "region_name_en": "in Thessaly",
                "pain_el": "στη Θεσσαλία, ο υπεραντλημένος υδροφόρος ορίζοντας, η συνεχής πτώση της στάθμης των γεωτρήσεων και οι παρατεταμένοι καύσωνες άνω των 42°C απειλούν άμεσα την παραγωγή. Οι λογαριασμοί ρεύματος για τις αντλίες άρδευσης έχουν εκτοξευθεί, ενώ τα επιφανειακά ποτίσματα εξατμίζονται άμεσα ή παρασύρουν τα ακριβά υδατοδιαλυτά λιπάσματα στα βαθύτερα στρώματα.",
                "pain_bg": "в района на Тесалия прекомерното изчерпване на сондажите и летните горещини над 42°C изправят стопанствата пред критичен недостиг на вода и огромни сметки за ток за помпите.",
                "pain_en": "in Thessaly, depleted groundwater aquifers, dropping well levels, and scorching heatwaves exceeding 42°C pose severe operational risks, compounding pump electricity costs and drying out crops.",
                "transform_local_el": "Αποφόρτιση των γεωτρήσεων κατά 50% και διασφάλιση συνεχούς υγρασίας στη ρίζα ακόμα και στις πιο κρίσιμες ημέρες καύσωνα.",
                "transform_local_bg": "50% по-малко часове работа на сондажните помпи и защита на корените при екстремни горещини.",
                "transform_local_en": "50% cut in well pumping hours and uninterrupted root moisture during peak heatwaves."
            }

        # 2. Crete & Aegean Islands (Ηράκλειο, Χανιά, Ρέθυμνο, Αγ. Νικόλαος, Σφακάκι, Καλύβες, Γεωργιούπολη, Πλακιάς)
        if any(k in text for k in ['ηράκλειο', 'heraklion', 'χανιά', 'chania', 'ρέθυμνο', 'rethymno', 'νικόλαος', 'nikolaos', 'σφακάκι', 'sfakaki', 'καλύβες', 'kalyves', 'γεωργιούπολη', 'georgioupoli', 'πλακιάς', 'plakias', 'κρήτη', 'crete', 'ρόδος', 'rhodes']):
            return {
                "region_key": "crete",
                "region_name_el": "στην Κρήτη & στα νησιά",
                "region_name_bg": "на остров Крит и островите",
                "region_name_en": "in Crete and the Aegean Islands",
                "pain_el": "στην Κρήτη, η οξεία λειψυδρία, η αυξημένη υφαλμύρωση του αρδευτικού νερού και οι ξηροθερμικοί νότιοι άνεμοι προκαλούν σοβαρό θερμικό σοκ στις καλλιέργειες, οδηγώντας σε πρόωρη καρπόπτωση και υψηλές χρεώσεις νερού ανά κυβικό.",
                "pain_bg": "на остров Крит постоянният дефицит на вода, високата засоленост и палещите ветрове водят до окапване на завръзите и скъпо струващо напояване.",
                "pain_en": "in Crete, chronic water scarcity, brackish water salinity, and drying southern winds cause acute thermal shock and fruit drop while driving up water tariffs.",
                "transform_local_el": "Δημιουργία ασπίδας γλυκού νερού στη ριζόσφαιρα, προστασία από την αλατότητα και μείωση της δαπάνης για νερό άνω του 50%.",
                "transform_local_bg": "Защитен буфер от прясна влага около корените, намаляващ солевия стрес и пестящ над 50% от водата.",
                "transform_local_en": "Fresh moisture shield around roots protecting against salinity and slashing water expenses by over 50%."
            }

        # 3. Peloponnese & Western Greece (Καλαμάτα, Σπάρτη, Τρίπολη, Μυστράς, Αμαλιάδα, Λεβεντοχώρι, Πάτρα, Κόρινθος)
        if any(k in text for k in ['καλαμάτα', 'kalamata', 'σπάρτη', 'sparta', 'τρίπολη', 'tripoli', 'μυστράς', 'mystras', 'αμαλιάδα', 'amaliada', 'λεβεντοχώρι', 'leventochori', 'πάτρα', 'patras', 'αλισσός', 'alissos', 'κόρινθος', 'corinth', 'πελοπόννησος', 'peloponnese']):
            return {
                "region_key": "peloponnese",
                "region_name_el": "στην Πελοπόννησο",
                "region_name_bg": "в Пелопонес",
                "region_name_en": "in the Peloponnese",
                "pain_el": "στην Πελοπόννησο, οι εκτεταμένες περίοδοι ανομβρίας από τον Ιούνιο έως τον Σεπτέμβριο και οι απότομοι καύσωνες καταπονούν ελαιώνες, αμπελώνες και οπωρώνες, προκαλώντας συρρίκνωση των καρπών και αυξημένο κόστος συνεχούς τεχνητής άρδευσης.",
                "pain_bg": "в Пелопонес дългите летни суши и горещите вълни изтощават лозовите и маслиновите масиви, водейки до дребни плодове и високи поливни разходи.",
                "pain_en": "in the Peloponnese, protracted summer dry spells and heat spikes exhaust vineyards, olive groves, and orchards, stunting fruit sizing and driving up irrigation schedules.",
                "transform_local_el": "Εξάλειψη του υδατικού στρες, διατήρηση μεγάλου εμπορικού μεγέθους καρπών και μείωση των αναγκών άρδευσης στο μισό.",
                "transform_local_bg": "Пълен контрол над водния стрес, наедряване на плодовете и съкращаване на поливките с 50%.",
                "transform_local_en": "Elimination of moisture stress, optimal fruit caliber, and cutting irrigation cycles in half."
            }

        # 4. Halkidiki & Central/Northern Macedonia (Κασσάνδρεια, Σιθωνία, Σίβηρη, Επανομή, Μονοπήγαδο, Μαραθούσσα, Ιερισσός, Μεγάλη Παναγία, Πετράλωνα, Αγ. Αθανάσιος, Θεσσαλονίκη, Δράμα, Καβάλα)
        if any(k in text for k in ['χαλκιδική', 'halkidiki', 'κασσάνδρα', 'kassandreia', 'σιθωνία', 'sithonia', 'σίβηρη', 'siviri', 'ιερισσός', 'ierissos', 'επανομή', 'epanomi', 'μονοπήγαδο', 'monopigado', 'μαραθούσσα', 'marathoussa', 'παναγία', 'panagia', 'προποντίδα', 'propontida', 'πετράλωνα', 'petralona', 'αθανάσιος', 'athanasios', 'θεσσαλονίκη', 'thessaloniki', 'δράμα', 'drama', 'καβάλα', 'kavala', 'ημαθία', 'πέλλα']):
            return {
                "region_key": "macedonia_halkidiki",
                "region_name_el": "στη Χαλκιδική & Κεντρική Μακεδονία",
                "region_name_bg": "в Халкидики и Македония",
                "region_name_en": "in Halkidiki and Central Macedonia",
                "pain_el": "στη Χαλκιδική και την Κεντρική Μακεδονία, τα αμμώδη ή επικλινή εδάφη και η παντελής απουσία βροχόπτωσης τους μήνες Ιούνιο–Αύγουστο έχουν ως αποτέλεσμα το νερό και τα λιπάσματα να χάνονται ταχύτατα στα κατώτερα στρώματα, επιβαρύνοντας το κόστος λειτουργίας των γεωτρήσεων και πιέζοντας τις καλλιέργειες σε περίοδο ωρίμανσης.",
                "pain_bg": "в Халкидики и Македония песъчливите и наклонени почви бързо губят влагата в дълбочина през сухите летни месеци, оскъпявайки сондажното напояване.",
                "pain_en": "in Halkidiki and Central Macedonia, sandy and sloped terrains combined with zero summer rainfall cause applied water and fertilizer to filter away rapidly, exhausting deep wells during fruit ripening.",
                "transform_local_el": "Μόνιμη δέσμευση νερού και λιπασμάτων στη ρίζα, διατήρηση ισορροπημένης ωρίμανσης (Brix/οξύτητα) και μείωση του κόστους άντλησης κατά 50%.",
                "transform_local_bg": "Задържане на влагата и торовете в активния слой, стабилно узряване и 50% икономия на изпомпвана вода.",
                "transform_local_en": "Retaining water and nutrients directly in the root layer, ensuring balanced ripening (Brix/acidity), and saving 50% on pumping bills."
            }

        # 5. Bulgaria (Thracian Lowland / Plovdiv / Dobrudja)
        if any(k in text for k in ['plovdiv', 'пловдив', 'брестовица', 'brestovitsa', 'устина', 'ustina', 'момин проход', 'пазарджик', 'стара загора', 'бургас', 'варна', 'русе', 'плевен', 'добрич', 'българия', 'bulgaria']):
            return {
                "region_key": "bulgaria_thrace",
                "region_name_el": "στη Βουλγαρία (Θρακική Πεδιάδα)",
                "region_name_bg": "в Тракийската низина и Южна България",
                "region_name_en": "in the Thracian Lowland and southern Bulgaria",
                "pain_el": "στη Θρακική Πεδιάδα και τη Νότια Βουλγαρία, τα παρατεταμένα καλοκαιρινά επεισόδια καύσωνα και η έλλειψη σταθερού δικτύου άρδευσης επιφέρουν βαθύ υδατικό στρες στα εδάφη, ρίχνοντας τις αποδόσεις και αυξάνοντας το κόστος παραγωγής.",
                "pain_bg": "в Тракийската низина и Южна България екстремните летни засушавания, високите температури и оскъпеното напояване поставят стопанствата под огромен финансов и агрономически натиск, изсушавайки повърхностния коренов слой.",
                "pain_en": "in the Thracian Valley, intense summer droughts, heatwaves, and disrupted canal irrigation threaten crop margins and dehydrate the active root horizons.",
                "transform_local_el": "Σταθερή παροχή υγρασίας για 7-10 χρόνια, μείωση των ποτισμάτων στο μισό και αύξηση της αντοχής των φυτών.",
                "transform_local_bg": "Подземен воден акумулатор за 7–10 години, намаляване на поливките наполовина и пълен имунитет срещу суша.",
                "transform_local_en": "Active 7-10 year subterranean water reservoir, halving irrigation cycles and securing yields against dry spells."
            }

        # 6. Romania (Oltenia / Dobrogea / Bărăgan)
        if any(k in text for k in ['craiova', 'oltenia', 'constanta', 'dobrogea', 'bucuresti', 'romania', 'românia']):
            return {
                "region_key": "romania_oltenia",
                "region_name_el": "στη Ρουμανία (Oltenia / Dobrogea)",
                "region_name_bg": "в Румъния (Олтения и Добруджа)",
                "region_name_en": "in Romania (Oltenia and Dobrogea)",
                "pain_el": "στη Ρουμανία, η ταχεία ερημοποίηση των αμμωδών εδαφών της Oltenia και της Dobrogea και οι ξηροί άνεμοι καθιστούν την άρδευση εξαιρετικά δαπανηρή και ασταθή.",
                "pain_bg": "в Олтения и Добруджа прогресивното засушаване на песъчливите почви води до критична загуба на влага и компрометирани добиви.",
                "pain_en": "in Oltenia and Dobrogea, accelerating soil aridization and dry steppe winds make irrigation both costly and difficult to maintain.",
                "transform_local_el": "Συγκράτηση της υγρασίας στα αμμώδη εδάφη και μείωση του κόστους άρδευσης κατά 50%.",
                "transform_local_bg": "Задържане на влагата в леки почви и намаляване на разходите за вода с 50%.",
                "transform_local_en": "Locking moisture in sandy soil and cutting irrigation expenses by 50%."
            }

        # 7. Spain (Andalucía, Murcia, Valencia)
        if any(k in text for k in ['sevilla', 'andaluc', 'murcia', 'valencia', 'madrid', 'spain', 'españa']):
            return {
                "region_key": "spain_andalucia",
                "region_name_el": "στην Ισπανία (Ανδαλουσία / Μούρθια)",
                "region_name_bg": "в Испания (Андалусия и Мурсия)",
                "region_name_en": "in Spain (Andalusia and Murcia)",
                "pain_el": "στην Ισπανία, οι αυστηροί περιορισμοί στις ποσοστώσεις νερού και η υπερεκμετάλλευση των υδροφορέων απειλούν άμεσα τη βιωσιμότητα των καλλιεργειών.",
                "pain_bg": "в Испания стриктните водни квоти и палещите жеги правят пестенето на всяка капка въпрос на оцеляване на стопанството.",
                "pain_en": "in Spain, severe water quota restrictions and overexploited aquifers make every cubic meter saved essential for farm survival.",
                "transform_local_el": "Μείωση κατανάλωσης νερού άνω του 50% και συμμόρφωση με τις αυστηρότερες ποσοστώσεις άρδευσης.",
                "transform_local_bg": "Спестяване на над 50% вода и пълна адаптация към строгите водни ограничения.",
                "transform_local_en": "Over 50% water reduction ensuring resilience under strict irrigation quotas."
            }

        # 8. Serbia (Vojvodina, Fruška Gora, Šumadija, Čačak, Negotin, Morava)
        if any(k in text for k in ['србија', 'srbija', 'serbia', 'војводина', 'vojvodina', 'fruška gora', 'fruska gora', 'шумадија', 'sumadija', 'čačak', 'cacak', 'неготин', 'negotin', 'нови сад', 'novi sad', 'београд', 'beograd', 'крушевац', 'krusevac', 'суботица', 'subotica', 'нишу', 'nis']):
            return {
                "region_key": "serbia",
                "region_name_el": "στη Σερβία (Vojvodina / Šumadija / Negotin)",
                "region_name_bg": "в Сърбия (Войводина, Шумадия и Неготин)",
                "region_name_sr": "у Србији (Војводина / Шумадија / Неготин)",
                "region_name_hr": "u Srbiji (Vojvodina / Šumadija / Negotin)",
                "region_name_en": "in Serbia (Vojvodina, Šumadija, and Negotin)",
                "pain_el": "στη Σερβία, οι παρατεταμένες θερινές ξηρασίες, οι καύσωνες και η πτώση του υδροφόρου ορίζοντα επιβαρύνουν τα καλλιεργητικά έξοδα και την άρδευση.",
                "pain_bg": "в Сърбия все по-честите летни суши и горещи вълни изчерпват почвената влага и увеличават поливните разходи.",
                "pain_sr": "у Србији су све чешће екстремне летње суше, тропски таласи преко 38°C и пад нивоа подземних вода, што доводи до брзог исушивања земљишта, принудног наводњавања и високих трошкова за струју и гориво за пумпе.",
                "pain_hr": "u Srbiji sve češće ljetne suše i toplinski valovi brzo isušuju tlo i povećavaju troškove navodnjavanja.",
                "pain_en": "in Serbia, escalating summer droughts, intense heat spikes above 38°C, and dropping water tables exhaust soil moisture and drive up pump energy expenses.",
                "transform_local_el": "Μείωση των ποτισμάτων κατά 50% και προστασία των ριζών από την ξηρασία.",
                "transform_local_bg": "Спестяване на 50% вода и защита на кореновата система при засушаване.",
                "transform_local_sr": "Смањење броја заливања за 50% и сигурно очување влаге у зони корена током најтоплијих летњих месеци.",
                "transform_local_hr": "Smanjenje potrebe za navodnjavanjem za 50% i zaštita korijena od suše.",
                "transform_local_en": "Halving irrigation frequency and securing active moisture directly at the root zone during peak summer heat."
            }

        # 9. Croatia (Istra, Kutjevo, Slavonija, Dalmacija, Pelješac, Neretva)
        if any(k in text for k in ['хрватска', 'hrvatska', 'croatia', 'istra', 'istria', 'motovun', 'kutjevo', 'slavonija', 'slavonia', 'pelješac', 'peljesac', 'dingač', 'dingac', 'neretva', 'opuzen', 'zadar', 'ravni kotari', 'zagorje', 'dalmacija', 'dalmatia', 'poreč', 'porec', 'rovinj']):
            return {
                "region_key": "croatia",
                "region_name_el": "στην Κροατία (Istria / Slavonia / Dalmatia)",
                "region_name_bg": "в Хърватия (Истрия, Славония и Далмация)",
                "region_name_sr": "у Хрватској (Истра / Славонија / Далмација)",
                "region_name_hr": "u Hrvatskoj (Istra / Slavonija / Dalmacija)",
                "region_name_en": "in Croatia (Istria, Slavonia, and Dalmatia)",
                "pain_el": "στην Κροατία, οι ξηρασίες στα πετρώδη ή αμμώδη εδάφη και οι περιορισμοί νερού καταπονούν αμπέλια και οπωρώνες.",
                "pain_bg": "в Хърватия летните засушавания и плитките почви в карстовите райони водят до бърза загуба на влага и стрес за насажденията.",
                "pain_sr": "у Хрватској дуге летње суше, плитка тла и недостатак воде у приморским и континенталним крајевима отежавају наводњавање.",
                "pain_hr": "u Hrvatskoj se poljoprivrednici suočavaju s dugotrajnim ljetnim sušama, toplinskim valovima i restrikcijama vode, pri čemu plitka i propusna tla na kršu i pjeskovitim područjima brzo gube vlagu, uzrokujući toplinski šok i pad prinosa.",
                "pain_en": "in Croatia, protracted summer dry spells, intense Mediterranean heatwaves, and water usage limits deplete soil moisture rapidly, threatening crop yields and grape quality.",
                "transform_local_el": "Συγκράτηση υγρασίας στη ρίζα και μείωση της κατανάλωσης νερού κατά 50%.",
                "transform_local_bg": "Задържане на влагата около корените и 50% икономия на поливна вода.",
                "transform_local_sr": "Задржавање влаге у зони корена и 50% мање потрошње воде.",
                "transform_local_hr": "Zadržavanje vlage i hranjiva u zoni korijena, smanjenje potrošnje vode za 50% i potpuna zaštita od ljetnih suša.",
                "transform_local_en": "Locking water and nutrients in the active root layer, slashing irrigation needs by 50% and protecting crops from dry spells."
            }

        # 10. General Mediterranean Fallback
        return {
            "region_key": "general_mediterranean",
            "region_name_el": "στη Μεσογειακή ζώνη",
            "region_name_bg": "в Средиземноморския басейн",
            "region_name_en": "across the Mediterranean basin",
            "pain_el": "οι παρατεταμένοι καλοκαιρινοί καύσωνες άνω των 40°C, η ραγδαία πτώση των υπόγειων υδάτων και το αυξανόμενο ενεργειακό κόστος άντλησης καθιστούν την παραδοσιακή άρδευση αναποτελεσματική, με το 40% του νερού να εξατμίζεται πριν φτάσει στη ρίζα.",
            "pain_bg": "горещите вълни над 40°C, спадът на подпочвените води и високите цени на тока за поливане оскъпяват продукцията, като над 40% от водата се губи от изпарение.",
            "pain_en": "extreme summer heatwaves above 40°C, dropping water tables, and high pump energy costs make conventional irrigation inefficient, with up to 40% lost to surface evaporation.",
            "transform_local_el": "Δημιουργία υπόγειου ταμιευτήρα υγρασίας που μειώνει την ανάγκη ποτίσματος κατά 50% και διατηρεί τη ζωτικότητα των φυτών για 7-10 χρόνια.",
            "transform_local_bg": "Създаване на подземен воден резервоар, спестяващ 50% вода и предпазващ насажденията за 7–10 години.",
            "transform_local_en": "Building an active underground reservoir that reduces watering cycles by 50% for 7 to 10 years."
        }

    def _get_crop_dosage(self, niche: str, lang: str) -> str:
        """Returns agronomic dosage recommendations customized by crop niche and language."""
        dosages = {
            "vineyard": {
                "el": "<strong>Για Αμπελώνες:</strong> 10–15 g TERAWET® T400 στη ριζόσφαιρα κάθε πρέμνου (ή κατά τη φύτευση) εξασφαλίζουν συνεχή διαθεσιμότητα υγρασίας χωρίς υπερβολική βλαστική ανάπτυξη. Αποτρέπεται το θερμικό σοκ, ενισχύεται η σύνθεση ανθοκυανών, ομοιόμορφος δείκτης Brix και σταθερή οξύτητα.",
                "bg": "<strong>За лозови масиви:</strong> 10–15 г ТЕРАУЕТ Т400 в кореновата зона осигуряват постоянен воден буфер. Предотвратява пригора на гроздето, гарантира едри зърна, отличен захарен градус и стабилен добив.",
                "ro": "<strong>Pentru Podgorii & Viță de Vie:</strong> 10–15 g TERAWET® T400 în zona radiculară a fiecărui butuc. Menține umiditatea optimă, previne stresul termic și arsurile pe boabe, asigurând o acumulare echilibrată de zaharuri (Brix) și aciditate constantă.",
                "es": "<strong>Para Viñedos:</strong> 10–15 g de TERAWET® T400 en la rizosfera de cada cepa. Garantiza disponibilidad continua de agua sin exceso vegetativo, evita el golpe de calor, protege el racimo y mantiene una acidez equilibrada y óptimo grado Brix.",
                "it": "<strong>Per Vigneti:</strong> 10–15 g di TERAWET® T400 nella rizosfera di ciascuna vite. Assicura una riserva idrica costante evitando lo stress da calore, previene la scottatura dei grappoli e garantisce un grado Brix ottimale e acidità equilibrata.",
                "fr": "<strong>Pour les Vignobles:</strong> 10–15 g de TERAWET® T400 dans la zone racinaire de chaque pied de vigne. Garantit une hydratation continue sans vigueur végétative excessive, évite le blocage thermique et préserve l'équilibre sucres/acidité.",
                "de": "<strong>Für Weingärten:</strong> 10–15 g TERAWET® T400 im Wurzelbereich jedes Rebstockes. Gewährleistet kontinuierliche Feuchtigkeit ohne übermäßiges vegetatives Wachstum, verhindert Hitzestress und Traubenbrand und sichert optimale Brix-Werte und Säureharmonie.",
                "hu": "<strong>Szőlőültetvényekhez:</strong> Tőkénként 10–15 g TERAWET® T400 a gyökérzónába dolgozva. Folyamatos nedvességet biztosít felesleges lombozatnövekedés nélkül, megelőzi a hőségsokkot és a bogyófonnyadást, fenntartva az optimális cukorfokot és savszerkezetet.",
                "sl": "<strong>Za Vinograde:</strong> 10–15 g TERAWET® T400 v koreninsko območje vsake trte. Zagotavlja stalen vodni vir brez prekomerne bujnosti, preprečuje toplotni šok ter zagotavlja optimalno sladkorno stopnjo in stabilne kisline.",
                "sk": "<strong>Pre Vinohrady:</strong> 10–15 g TERAWET® T400 do koreňovej zóny každého klu viniča. Zabezpečuje stálu dostupnosť vlahy, chráni pred úpalom a vädnutím strapcov, pričom udržiava optimálnu cukornatosť a vyvážené kyseliny.",
                "sr": "<strong>За винограде:</strong> 10–15 g TERAWET® T400 у коренову зону сваког чокота (или приликом садње) обезбеђује сталан извор влаге без претераног вегетативног раста. Спречава топлотни шок, осигурава оптималан Brix индекс шећера и стабилне киселине.",
                "hr": "<strong>Za vinograde:</strong> 10–15 g TERAWET® T400 u korijensku zonu svakog trsa (ili kod sadnje). Osigurava stalnu opskrbu vlagom bez pretjeranog vegetativnog bujanja, sprječava toplinski šok i ožegotine grozda te osigurava uravnotežene šećere (Brix) i stabilnu kiselost.",
                "en": "<strong>For Vineyards:</strong> 10–15 g TERAWET® T400 applied directly to the root zone of each vine locks in moisture for 7–10 years. Prevents thermal shutdown, protects grape bunches, and secures optimal Brix and balanced acidity."
            },
            "nursery": {
                "el": "<strong>Για Φυτώρια & Νέες Φυτεύσεις:</strong> Εμβάπτιση των γυμνών ριζών σε πάστα γέλης TERAWET® T100 (5–8 g/L νερού) εγγυάται <strong>100% επιτυχία ριζοβολίας</strong> χωρίς μεταφυτευτικό σοκ. Για υποστρώματα σε γλάστρες, η ενσωμάτωση T400 (1.5–2 kg/m³) μειώνει τη συχνότητα ποτίσματος κατά 60%.",
                "bg": "<strong>За разсадници и нови насаждения:</strong> Потапянето на корените в гел-паста ТЕРАУЕТ Т100 (5–8 г/л вода) гарантира <strong>100% прихващане на фиданките</strong>. В субстрати за саксии Т400 съкращава поливките с 60%.",
                "ro": "<strong>Pentru Pepiniere & Plantații Noi:</strong> Înmuierea rădăcinilor nude în pastă de gel TERAWET® T100 (5–8 g/L apă) garantează <strong>prindere de 100%</strong> fără șoc de transplantare. În substraturi pentru ghivece, T400 reduce udările cu 60%.",
                "es": "<strong>Para Viveros y Nuevas Plantaciones:</strong> La inmersión de raíces desnudas en pasta de gel TERAWET® T100 (5–8 g/L de agua) asegura un <strong>100% de prendimiento</strong> sin estrés post-trasplante. En sustratos de maceta, T400 reduce el riego en un 60%.",
                "it": "<strong>Per Vivai e Nuovi Impianti:</strong> L'immersione delle radici nude nella pasta gel TERAWET® T100 (5–8 g/L d'acqua) garantisce il <strong>100% di attecchimento</strong> senza shock da trapianto. Nei substrati per vasi, T400 riduce le irrigazioni del 60%.",
                "fr": "<strong>Pour les Pépinières & Jeunes Plantations:</strong> Le pralinage des racines nues dans la pâte de gel TERAWET® T100 (5–8 g/L d'eau) assure <strong>100% de reprise racinaire</strong> sans choc de transplantation. En pots, T400 espace les arrosages de 60%.",
                "de": "<strong>Für Baumschulen & Neupflanzungen:</strong> Das Eintauchen nackter Wurzeln in TERAWET® T100 Gel-Paste (5–8 g/L Wasser) garantiert <strong>100% Anwachserfolg</strong> ohne Pflanzschock. In Substraten senkt T400 die Gießintervalle um 60%.",
                "hu": "<strong>Faiskoláknak & Új Telepítéseknek:</strong> A szabadgyökerű csemeték TERAWET® T100 gélpasztába (5–8 g/L víz) mártása <strong>100%-os megeredést</strong> biztosít ültetési sokk nélkül. Konténeres nevelésnél a T400 60%-kal csökkenti az öntözési fordulót.",
                "sl": "<strong>Za Drevesnice in Nove Nasade:</strong> Pomakanje golih korenin v gelasto pasto TERAWET® T100 (5–8 g/L vode) zagotavlja <strong>100% ukoreninjenje</strong> brez presaditvenega šoka. V substratih T400 zmanjša pogostost zalivanja za 60%.",
                "sk": "<strong>Pre Ovocné a Lesné Škôlky:</strong> Namáčanie voľnokorenných sadeníc do gélovej pasty TERAWET® T100 (5–8 g/L vody) garantuje <strong>100% ujatie</strong> bez presadzovacieho šoku. V substrátoch T400 znižuje frekvenciu polievania o 60%.",
                "sr": "<strong>За расаднике и нове засаде:</strong> Потапање голог корена у гел-пасту TERAWET® T100 (5–8 g/L воде) гарантује <strong>100% пријем садница</strong> без транзитног шока. У супстратима за саксије T400 смањује заливање за 60%.",
                "hr": "<strong>Za rasadnike i mlade nasade:</strong> Uranjanje golog korijena u gel pastu TERAWET® T100 (5–8 g/L vode) jamči <strong>100% uspješnost ukorjenjivanja</strong> bez stresa presađivanja. U supstratima T400 smanjuje zalijevanje za 60%.",
                "en": "<strong>For Nurseries & Transplanting:</strong> Dipping bare roots in TERAWET® T100 gel paste (5–8 g/L water) secures <strong>100% root establishment</strong> with zero transplant shock. For pot substrates, T400 reduces irrigation frequency by over 60%."
            },
            "orchard": {
                "el": "<strong>Για Ελαιώνες & Δενδρώδεις:</strong> 15–25 g TERAWET® T400 ανά δέντρο στη ζώνη των απορροφητικών ριζιδίων. Αποτρέπει την καλοκαιρινή καρπόπτωση, εξασφαλίζει μεγαλύτερη καλίμπρα καρπών και σταθερή ανθοφορία την επόμενη σεζόν.",
                "bg": "<strong>За овощни градини и маслини:</strong> 15–25 г ТЕРАУЕТ Т400 на дърво в активната коренова зона. Спира окапването на завръза в юлските жеги и гарантира едър, качествен плод.",
                "ro": "<strong>Pentru Livezi & Pomi Fructiferi:</strong> 15–25 g TERAWET® T400 per pom în zona rădăcinilor absorbante. Oprește căderea prematură a fructelor în caniculă și asigură un calibru comercial superior.",
                "es": "<strong>Para Olivares y Frutales:</strong> 15–25 g de TERAWET® T400 por árbol en la zona radicular activa. Evita la caída prematura de fruto durante las olas de calor de verano y maximiza el calibre y el rendimiento graso.",
                "it": "<strong>Per Uliveti e Frutteti:</strong> 15–25 g di TERAWET® T400 per albero nella zona delle radici assorbenti. Blocca la cascola estiva dei frutticini durante le ondate di calore e favorisce calibri superiori.",
                "fr": "<strong>Pour Vergers & Oliveraies:</strong> 15–25 g de TERAWET® T400 par arbre au niveau des racines actives. Empêche la chute physiologique des fruits sous forte chaleur et améliore le calibre commercial.",
                "de": "<strong>Für Obstbau & Baumkulturen:</strong> 15–25 g TERAWET® T400 pro Baum im aktiven Feinwurzelbereich. Stoppt vorzeitigen Fruchtfall bei Sommerhitze und sichert erstklassige Fruchtkaliber.",
                "hu": "<strong>Gyümölcsösöknek & Olajfáknak:</strong> Fánként 15–25 g TERAWET® T400 az aktív hajszálgyökerekhez juttatva. Megállítja a júliusi-augusztusi gyümölcshullást a kánikulában, és garantálja a nagyobb méretet.",
                "sl": "<strong>Za Sadovnjake in Oljčnike:</strong> 15–25 g TERAWET® T400 na drevo v območje aktivnih korenin. Preprečuje odpadanje plodičev med poletnimi vročinskimi valovi in povečuje debelino plodov.",
                "sk": "<strong>Pre Ovocné Sady a Olivovníky:</strong> 15–25 g TERAWET® T400 na strom v zóne aktívnych koreňov. Zastavuje predčasný letný opad plodov počas horúčav a zvyšuje ich veľkosť a trhovú kvalitu.",
                "sr": "<strong>За воћњаке и маслињаке:</strong> 15–25 g TERAWET® T400 по стаблу у зони активних жила. Спречава превремено опадање плодова током јулских и августовских врућина и даје крупан, квалитетан плод.",
                "hr": "<strong>Za voćnjake i maslinike:</strong> 15–25 g TERAWET® T400 po stablu u aktivnoj zoni korijena. Sprječava prijevremeno opadanje plodova tijekom ljetnih vrućina i jamči vrhunski kalibar i prinos.",
                "en": "<strong>For Orchards & Olive Groves:</strong> 15–25 g TERAWET® T400 per tree in the active feeder root zone. Prevents premature fruit shedding during heatwaves, ensuring superior fruit caliber and oil accumulation."
            },
            "general_agro": {
                "el": "<strong>Για Υπαίθριες & Θερμοκηπιακές Καλλιέργειες:</strong> 2–3 kg TERAWET® T400 ανά στρέμμα (1000 m²) ή 10–15 g ανά φυτό. Δημιουργεί ένα ενεργό υδροστρώμα διάρκειας 7–10 ετών, μειώνοντας την κατανάλωση νερού και λιπασμάτων στο μισό.",
                "bg": "<strong>За зеленчуци, полски и оранжерийни култури:</strong> 2–3 кг ТЕРАУЕТ Т400 на декар или 10–15 г под корен. Осигурява балансирано хранене и съкращава поливните норми с над 50%.",
                "ro": "<strong>Pentru Legume & Culturi de Câmp:</strong> 2–3 kg TERAWET® T400 la 1.000 m² (sau 10–15 g per plantă). Formează un rezervor subteran activ timp de 7–10 ani, reducând la jumătate apa și îngrășămintele.",
                "es": "<strong>Para Hortalizas y Extensivos:</strong> 2–3 kg de TERAWET® T400 por 1.000 m² (o 10–15 g por planta). Crea un colchón hídrico activo durante 7–10 años que reduce el consumo de agua y fertilizantes a la mitad.",
                "it": "<strong>Per Orticoltura e Pieno Campo:</strong> 2–3 kg di TERAWET® T400 per 1.000 m² (oppure 10–15 g per pianta). Forma un cuscinetto idrico attivo per 7–10 anni, dimezzando consumi di acqua ed elettricità.",
                "fr": "<strong>Pour Maraîchage & Plein Champ:</strong> 2–3 kg de TERAWET® T400 pour 1 000 m² (ou 10–15 g par plant). Crée une réserve d'humidité souterraine active pendant 7 à 10 ans, divisant par deux les besoins en eau et en engrais.",
                "de": "<strong>Für Gemüse- & Feldkulturen:</strong> 2–3 kg TERAWET® T400 pro 1.000 m² (oder 10–15 g pro Pflanze). Schafft ein aktives, 7–10 Jahre haltbares Wasserdepot im Boden und halbiert den Bewässerungs- und Düngerbedarf.",
                "hu": "<strong>Zöldség- és Szántóföldi Kultúrákhoz:</strong> 2–3 kg TERAWET® T400 / 1000 m² (vagy 10–15 g/tő). 7–10 éven át aktív földalatti vízpufferként működik, több mint 50%-kal csökkentve az öntözési- és tápanyag-költségeket.",
                "sl": "<strong>Za Vrtnarstvo in Poljedelstvo:</strong> 2–3 kg TERAWET® T400 na 1.000 m² (ali 10–15 g na rastlino). Ustvari aktiven 7–10 letni vodni blažilec v tleh, ki prepolovi porabo vode in gnojil.",
                "sk": "<strong>Pre Zeleninárstvo a Poľné Plodiny:</strong> 2–3 kg TERAWET® T400 na 1 000 m² (alebo 10–15 g na rastlinu). Vytvára v pôde aktívny podzemný vodný vankúš na 7–10 rokov a znižuje spotrebu vody a hnojív na polovicu.",
                "sr": "<strong>За повртарство и ратарске културе:</strong> 2–3 kg TERAWET® T400 по хектару/декару (или 10–15 g под корен). Ствара активан подземни резервоар воде током 7–10 година, смањујући потрошњу воде и ђубрива за половину.",
                "hr": "<strong>Za povrćarstvo i ratarstvo:</strong> 2–3 kg TERAWET® T400 na 1.000 m² (ili 10–15 g po biljci). Stvara podzemni akumulator vlage koji traje 7–10 godina i smanjuje potrebe za navodnjavanjem i gnojivom za više od 50%.",
                "en": "<strong>For Commercial Crops & Greenhouses:</strong> 2–3 kg TERAWET® T400 per 1,000 m² (or 10–15 g per root). Forms an active 7–10 year moisture cushion, halving water and fertilizer demands."
            }
        }
        niche_dict = dosages.get(niche, dosages["general_agro"])
        return niche_dict.get(lang, niche_dict.get("en", ""))

    def _detect_crop_niche(self, lead: Dict[str, str]) -> Dict[str, str]:
        """Classifies crop/segment for targeted agronomic recommendations."""
        text = f"{lead.get('crops', '')} {lead.get('category', '')} {lead.get('company_name', '')}".lower()

        if any(k in text for k in [
            'οινοποι', 'αμπελ', 'κρασ', 'winery', 'vineyard', 'wine', 'винарна', 'лозя',
            'cantina', 'vigneto', 'viticol', 'domaine', 'château', 'chateau', 'vignoble',
            'weingut', 'winzer', 'borászat', 'boraszat', 'pincészet', 'pinceszet', 'vinograd',
            'vinarij', 'podrum', 'винар', 'виноград', 'подрум',
            'klet', 'vinárstvo', 'vinarstvo', 'bodega', 'viñedo', 'vinedo', 'crama', 'podgori'
        ]):
            niche = "vineyard"
        elif any(k in text for k in [
            'φυτώρι', 'nursery', 'разсадник', 'garden center', 'κηποτεχν', 'landscape',
            'vivaio', 'pépinière', 'pepiniere', 'baumschule', 'faiskola', 'drevesnica',
            'rasadnik', 'садниц', 'расадник',
            'škôlka', 'skolka', 'vivero', 'pepinier', 'arboretum'
        ]):
            niche = "nursery"
        elif any(k in text for k in [
            'ελαι', 'olive', 'οπωρ', 'orchard', 'δένδρ', 'овощ', 'ябъл', 'череш', 'прасков',
            'frutteto', 'oliveto', 'verger', 'oliveraie', 'obstbau', 'gyümölcs', 'gyumolcs',
            'voćnjak', 'vocnjak', 'воћњак', 'maslin', 'маслин', 'šljiv', 'sljiv', 'шљив',
            'olajbogyó', 'sadovnjak', 'oljka', 'ovocn', 'frutales', 'olivar', 'livad', 'citrus'
        ]):
            niche = "orchard"
        else:
            niche = "general_agro"

        return {
            "niche": niche,
            "dosage_el": self._get_crop_dosage(niche, "el"),
            "dosage_bg": self._get_crop_dosage(niche, "bg"),
            "dosage_sr": self._get_crop_dosage(niche, "sr"),
            "dosage_hr": self._get_crop_dosage(niche, "hr"),
            "dosage_en": self._get_crop_dosage(niche, "en")
        }

    def _build_system_prompt(self, lang: str) -> str:
        kb_text = json.dumps(self.knowledge_base, ensure_ascii=False, indent=2)
        target_lang = SUPPORTED_LANGUAGES.get(lang, "English")

        return f"""You are a World-Class Senior Agricultural Copywriter and Technical Agronomist at TERAWET-ORIGINAL® (VANKO 97 EOOD, 25 years of proven field experience in soil superabsorbents).
Website for online orders: https://www.tera-wet.com
Phone: +359 888 516501
Direct sales contact: Bendyk Dmytro, +380502365858 / +359889175452

KNOWLEDGE BASE:
{kb_text}

COPYWRITING PHILOSOPHY & STRUCTURE (Write in {target_lang}):
Write an authoritative, persuasive, highly engaging B2B sales letter designed to solve real farmer pain:
1. THE HOOK & REGIONAL AGITATION:
   - Identify the exact region and climatic pressure of the lead's location (severe drought, heatwaves >40°C, plummeting groundwater aquifers, dry boreholes, extreme pump electricity costs, sandy soil leaching).
   - Acknowledge their specific crops/business (vineyards, nurseries, olive groves, orchards, vegetables).
2. THE SCIENCE & MECHANISM (Why ordinary watering fails & why TERAWET works):
   - Traditional watering at high temperatures loses 40-50% to evaporation and subsoil leaching, washing away expensive N-P-K fertilizers.
   - TERAWET is an eco-friendly cross-linked POTASSIUM polyacrylate (NOT cheap sodium polymers that salinize and ruin soil).
   - Swells up to 400x in water, creating a "Smart Subterranean Reservoir" at the root zone (15-40 cm depth). Osmotic root action pulls moisture strictly on demand.
3. THE POSITIVE TRANSFORMATIONS (Transforming the farm for the better):
   Clearly outline the concrete positive transformations:
   - 💧 50%–60% Irrigation Water Reduction (fewer watering cycles, continuous root hydration).
   - ⚡ 50% Reduction in Pump Electricity & Fuel Costs (doubling pump lifespan, saving thousands of euros).
   - 🧪 >30%–40% Savings on Water-Soluble Fertilizers (nutrients locked in hydrogel, no leaching).
   - 🍇 Heat Stress Elimination & Yield Caliber (no blossom/fruit drop, optimal Brix and uniform sizing).
   - 🌱 100% Sapling Survival & Take-Rate (with T100 root dipping paste).
   - ⏳ 7 to 10 YEARS continuous activity from a SINGLE application (guaranteed 1st-season ROI).
4. SPECIFIC DOSAGE for their crop type (e.g. 10-15g/vine or tree, 2-3kg/decar for field, 5-8g/L for root paste).
5. PACKAGING & DIRECT ONLINE ORDERING:
   - 25 kg professional sacks (360 €) for commercial acreage and 1 kg trial packs.
   - Direct online ordering link: https://www.tera-wet.com
6. STRATEGIC PARTNERSHIP & NATIONAL DEALERSHIP PROPOSAL (CRITICAL):
   - In a dedicated section after the product details and before the final closing, present a professional B2B proposal:
     State clearly that in addition to direct farmer supply, TERAWET-ORIGINAL® (VANKO 97 EOOD) is actively expanding across Europe and is seeking established agricultural distributors, regional input companies, and dealers to establish official national representations, dealership centers, and regional distribution hubs in their country. Mention direct factory terms, attractive dealer margins, full agronomic training, and invite them to schedule a partnership meeting.
7. CALL TO ACTION (CTA):
   - Clear, respectful invitation to order online, discuss acreage calculations, or explore official dealership cooperation.
8. FORMAT: Return JSON strictly:
   {{
     "subject": "...",
     "body_html": "<p>...</p>",
     "body_plain": "..."
   }}
Do NOT include the final signature block; the system will append the official team signature automatically.
"""

    def _generate_with_llm(self, lead: Dict[str, str], lang: str) -> Tuple[str, str, str]:
        user_prompt = f"""Write a masterclass agricultural sales letter for:
- Company: {lead.get('company_name')}
- Contact: {lead.get('contact_person', 'Agronomy Department')}
- City / Region: {lead.get('city')} | Address: {lead.get('adress') or lead.get('address')}
- Country: {lead.get('country')}
- Target Language: {lang}
- Niche/Crops: {lead.get('crops') or lead.get('category')}
- Website: {lead.get('website')}
- Official Site: https://www.tera-wet.com

Highlight the regional drought reality, the positive transformations with TERAWET, dosage, 25 kg sacks (360 €) / 1 kg packs, online ordering at https://www.tera-wet.com, and include the strategic partnership proposal for opening official national representation and dealerships in their country.
Return JSON with subject, body_html, body_plain."""

        response = self.openai_client.chat.completions.create(
            model=config.LLM_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._build_system_prompt(lang)},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        return data.get("subject", ""), data.get("body_html", ""), data.get("body_plain", "")

    def _get_partnership_proposal(self, lang: str) -> Tuple[str, str]:
        """
        Returns a dedicated, highly professional B2B dealership & national representation proposal
        to be appended to the sales letter across all supported languages.
        """
        proposals = {
            "sr": {
                "title": "🤝 Стратешко партнерство и отварање званичног представништва",
                "text": "Поред директне испоруке производа, наша компанија <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> активно шири европску дистрибутивну мрежу и тражи поуздане пословне партнере, пољопривредне дистрибутере и апотеке за <strong>отварање званичног националног представништва и регионалних дистрибутивних центара у Србији</strong>.<br>Нудимо ексклузивне велепродајне услове, фабричке цене, пуну стручну и агрономску подршку, као и маркетиншке материјале. Уколико сте заинтересовани да постанете овлашћени дистрибутер или заступник у вашем региону, са задовољством вас позивамо на директан разговор о сарадњи."
            },
            "hr": {
                "title": "🤝 Strateško partnerstvo i otvaranje službenog predstavništva",
                "text": "Uz izravnu isporuku proizvoda poljoprivrednim gospodarstvima, tvrtka <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> aktivno širi svoju europsku mrežu te traži pouzdane poslovne partnere, poljoprivredne distributere i agrokemijske kuće za <strong>otvaranje službenog nacionalnog predstavništva i regionalnih distribucijskih centara u Hrvatskoj</strong>.<br>Nudimo ugovorne partnerske marže, izravne tvorničke isporuke, cjelovitu tehničku i agronomsku podršku te marketinško vodstvo. Ako je vaša tvrtka zainteresirana za status ovlaštenog distributera ili zastupnika, sa zadovoljstvom ćemo dogovoriti uvodni razgovor o mogućnostima suradnje."
            },
            "el": {
                "title": "🤝 Στρατηγική Συνεργασία & Άνοιγμα Επίσημης Αντιπροσωπείας",
                "text": "Παράλληλα με την απευθείας διάθεση των προϊόντων μας σε παραγωγούς, η εταιρεία <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> αναπτύσσει το ευρωπαϊκό της δίκτυο και αναζητά αξιόπιστους εμπορικούς συνεργάτες, διανομείς αγροτικών εφοδίων και γεωπονικές επιχειρήσεις για τη <strong>δημιουργία επίσημης εθνικής αντιπροσωπείας και περιφερειακών κέντρων διανομής στην Ελλάδα</strong>.<br>Προσφέρουμε προνομιακούς όρους χονδρικής, εργοστασιακές τιμές, πλήρη τεχνική/αγρονομική εκπαίδευση και πιστοποιημένη ευρωπαϊκή ποιότητα. Εάν ενδιαφέρεστε να εντάξετε το TERAWET® στο χαρτοφυλάκιό σας ή να αναλάβετε επίσημη αντιπροσωπεία, είμαστε στη διάθεσή σας για μια κατ' ιδίαν επικοινωνία."
            },
            "bg": {
                "title": "🤝 Стратегическо партньорство и откриване на официално търговско представителство",
                "text": "Освен директните доставки за земеделските стопанства, <strong>TERAWET-ORIGINAL® (ВАНКО 97 ЕООД)</strong> активно разширява партньорската си мрежа и търси доверени регионални партньори, агроаптеки и дистрибутори на торове и семена за <strong>откриване на официални търговски представителства и регионални складови бази</strong>.<br>Предлагаме преференциални дистрибуторски цени, директен производителски достъп, пълен агрономически съпорт и маркетингови материали. Ако проявявате интерес към официално дистрибуторство, с удоволствие ще обсъдим възможностите за дългосрочно партньорство."
            },
            "ro": {
                "title": "🤝 Parteneriat Strategic & Deschiderea unei Reprezentanțe Oficiale",
                "text": "Pe lângă livrarea directă a produselor noastre către ferme, compania <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> își extinde rețeaua europeană de distribuție și caută parteneri comerciali de încredere, distribuitori de inputuri agricole și fitofarmacii pentru <strong>deschiderea unei reprezentanțe oficiale naționale și a unor centre regionale de distribuție în România</strong>.<br>Oferim condiții comerciale avantajoase de distribuție, prețuri directe de producător, asistență tehnică agronomică și suport promoțional complet. Dacă doriți să deveniți distribuitor autorizat sau partener oficial în zona dumneavoastră, vă invităm la o discuție comercială directă."
            },
            "es": {
                "title": "🤝 Alianza Estratégica y Apertura de Representación Oficial",
                "text": "Además del suministro directo a explotaciones agrícolas, <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> está expandiendo su red comercial en Europa y busca distribuidores agropecuarios consolidados, almacenes agrícolas y cooperativas para la <strong>apertura de delegaciones oficiales y centros regionales de distribución en España</strong>.<br>Ofrecemos márgenes comerciales preferentes, suministro directo de fábrica, asesoramiento agronómico especializado y material técnico de apoyo. Si su empresa está interesada en representar nuestra marca o distribuir TERAWET® en su región, estaremos encantados de coordinar una reunión de trabajo."
            },
            "it": {
                "title": "🤝 Opportunità di Partnership Strategica e Rappresentanza Ufficiale",
                "text": "Oltre alla fornitura diretta per le aziende agricole, <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> sta potenziando la propria rete in Italia ed è alla ricerca di partner commerciali affidabili, consorzi agrari e distributori di fitofarmaci ed elementi nutritivi per <strong>l'apertura di una rappresentanza ufficiale nazionale e snodi distributivi regionali</strong>.<br>Garantiamo condizioni esclusive per rivenditori, prezzi diretti di fabbrica, certificazioni di conformità europea e supporto tecnico-agronomico continuo. Se la Vostra realtà è interessata a diventare concessionario o partner di zona, siamo a completa disposizione per un confronto operativo."
            },
            "fr": {
                "title": "🤝 Opportunité de Partenariat Stratégique & Concession Officielle",
                "text": "Au-delà des approvisionnements directs pour les exploitations, <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> développe activement son réseau européen et recherche des partenaires commerciaux établis, distributeurs d'agrofournitures et coopératives agricoles pour <strong>l'ouverture d'une représentation officielle nationale et de relais régionaux de distribution en France</strong>.<br>Nous mettons à disposition des conditions tarifaires concessionnaires avantageuses, des livraisons directes d'usine, un accompagnement agronomique rigoureux et des supports de commercialisation complets. Si vous envisagez de représenter nos solutions dans votre secteur, prenons contact pour étudier les perspectives de collaboration."
            },
            "de": {
                "title": "🤝 Strategische Partnerschaft & Offizielle Landesvertretung",
                "text": "Neben der Direktbelieferung landwirtschaftlicher Betriebe baut <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> sein europäisches Vertriebsnetzwerk kontinuierlich aus und sucht etablierte Agrarhändler, Landtechnik-Vertriebe und regionale Kooperationspartner zur <strong>Errichtung offizieller Landesvertretungen und Stützpunkthändler in Österreich und Deutschland</strong>.<br>Wir bieten exklusive Händlerkonditionen, direkte Werksbelieferung, fundierten agronomischen Support und vollständige Zertifizierungsunterlagen. Bei Interesse an einer autorisierten Vertriebspartnerschaft freuen wir uns auf ein vertiefendes Gespräch."
            },
            "hu": {
                "title": "🤝 Stratégiai Partnerség & Hivatalos Képviselet Nyitása",
                "text": "A gazdaságok közvetlen kiszolgálása mellett a <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> dinamikusan bővíti európai forgalmazói hálózatát, és megbízható agrár-nagykereskedelmi partnereket, növényvédőszer- és műtrágya-forgalmazókat keres <strong>hivatalos országos képviselet és regionális disztribúciós központok megnyitására Magyarországon</strong>.<br>Kiemelt viszonteladói árrést, közvetlen gyári szállítást, teljes körű agronómiai képzést és marketingtámogatást biztosítunk. Amennyiben nyitottak a hivatalos képviseletre vagy a termék forgalmazására, szívesen egyeztetünk a partnerség részleteiről."
            },
            "sl": {
                "title": "🤝 Strateško partnerstvo in odprtje uradnega zastopstva",
                "text": "Poleg neposredne dobave kmetijskim gospodarstvom podjetje <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> aktivno širi svojo distribucijsko mrežo ter išče zanesljive poslovne partnerje, kmetijske zadruge in distributerje za <strong>vzpostavitev uradnega nacionalnega zastopstva in regijskih distribucijskih centrov v Sloveniji</strong>.<br>Zagotavljamo konkurenčne veleprodajne pogoje, direktne tovarniške dobave, strokovno agronomsko podporo in uradne evropske certifikate. Če vas zanima status uradnega distributerja ali zastopnika, vas z veseljem vabimo k skupnemu pogovoru."
            },
            "sk": {
                "title": "🤝 Strategické partnerstvo a otvorenie oficiálneho zastúpenia",
                "text": "Okrem priamych dodávok pre poľnohospodárske podniky spoločnosť <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> aktívne rozširuje svoju distribučnú sieť a hľadá spoľahlivých obchodných partnerov, distribútorov agrochémie a osív na <strong>otvorenie oficiálneho národného zastúpenia a regionálnych skladov na Slovensku</strong>.<br>Ponúkame výhodné distribútorské marže, priame dodávky z výroby, agronomické školenia a kompletnú marketingovú podporu. V prípade záujmu o status autorizovaného predajcu alebo zástupcu veľmi radi preberieme možnosti spolupráce."
            },
            "en": {
                "title": "🤝 Strategic Partnership & National Dealership Opportunity",
                "text": "In addition to direct supply for farming operations, <strong>TERAWET-ORIGINAL® (VANKO 97 EOOD)</strong> is actively expanding its European commercial network and seeking established agricultural distributors, input suppliers, and regional partners to <strong>establish official national representations and dealership hubs in your country</strong>.<br>We offer attractive distributor margins, direct factory fulfillment, extensive agronomic training, and full marketing support. If your company is interested in becoming an authorized distributor or exclusive national representative, we welcome the opportunity to discuss terms."
            }
        }
        item = proposals.get(lang, proposals["en"])
        title = item["title"]
        text_html = item["text"]
        text_plain = text_html.replace("<br>", "\n").replace("<strong>", "").replace("</strong>", "")

        html_block = f"""<div style="background: #f0f9ff; border: 1px solid #bae6fd; border-left: 5px solid #0284c7; border-radius: 8px; padding: 18px 20px; margin: 24px 0;">
  <h4 style="color: #0369a1; margin: 0 0 10px 0; font-size: 15px; font-weight: 700;">{title}</h4>
  <p style="margin: 0; font-size: 14.5px; line-height: 1.6; color: #1e293b;">{text_html}</p>
</div>"""
        plain_block = f"{title}\n{text_plain}"
        return html_block, plain_block

    def _generate_with_template(self, lead: Dict[str, str], lang: str, variant: int = 0) -> Tuple[str, str, str]:
        company = (lead.get("company_name") or lead.get("name") or "Company").strip()
        contact = (lead.get("contact_person") or "").strip()
        crops = (lead.get("crops") or lead.get("category") or "αγροτικές καλλιέργειες").strip()
        site = "https://www.tera-wet.com"

        reg_info = self._detect_region_context(lead)
        crop_info = self._detect_crop_niche(lead)
        v_mode = variant % 3

        # -------------------------------------------------------------
        # 1. GREEK COPYWRITER TEMPLATE (primary market)
        # -------------------------------------------------------------
        if lang == "el":
            contact_greeting = f"Αξιότιμη ομάδα της {company}" if not contact or contact in ["Team", "Admin"] else f"Αξιότιμε/η κ. {contact}"
            reg_display = reg_info["region_name_el"]
            pain_text = reg_info["pain_el"]
            trans_local = reg_info["transform_local_el"]
            dosage_text = crop_info["dosage_el"]

            if v_mode == 1:
                subject = f"Οικονομικό όφελος & 50% μείωση λογαριασμών άντλησης για την {company} ({reg_display})"
            elif v_mode == 2:
                subject = f"Προστασία καλλιεργειών από καύσωνα +40°C και μεγιστοποίηση ποιότητας για την {company} ({reg_display})"
            else:
                subject = f"50% εξοικονόμηση νερού άρδευσης και προστασία από την ξηρασία για την {company} ({reg_display})"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Επικοινωνούμε μαζί σας με αφορμή τις καλλιεργητικές δραστηριότητες της <strong>{company}</strong> ({crops}) {reg_display}. 
Όπως γνωρίζετε από πρώτο χέρι, {pain_text}
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Σε περιόδους με θερμοκρασίες άνω των 35–40°C, η παραδοσιακή άρδευση χάνει σχεδόν το <strong>40%–50% του νερού</strong> από επιφανειακή εξάτμιση και βαρυτική διαρροή. 
Αυτό σημαίνει ότι τα φυτά παραμένουν ευάλωτα σε έντονο θερμικό στρες, ενώ σημαντικό μέρος των δαπανηρών υδατοδιαλυτών λιπασμάτων N-P-K εκπλύνεται βαθύτερα χωρίς ποτέ να απορροφηθεί.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Για να δώσουμε οριστική λύση σε αυτή την πρόκληση, σας παρουσιάζουμε την αποδεδειγμένη τεχνολογία <strong>TERAWET-ORIGINAL®</strong> – πιστοποιημένο οικολογικό υπεραπορροφητικό εδαφοβελτιωτικό <strong>καλίου</strong> (όχι βιομηχανικό νάτριο) με <strong>25 χρόνια εμπειρίας</strong> σε όλη την Ευρώπη (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Οι Θετικές Αλλαγές για την Εκμετάλλευσή σας με το TERAWET®:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Ραγδαία μείωση της κατανάλωσης νερού κατά 50%–60%:</strong> Οι κόκκοι απορροφούν και συγκρατούν έως και 400 φορές το βάρος τους σε νερό, δημιουργώντας έναν <em>«έξυπνο υπόγειο ταμιευτήρα»</em> στη ριζόσφαιρα (15–40 cm). Το νερό αποδίδεται στο φυτό αποκλειστικά μέσω φυσικής ωσμωτικής πίεσης όταν υπάρχει ανάγκη.</li>
    <li><strong>⚡ Έως 50% λιγότερες ώρες λειτουργίας των αντλιών:</strong> {trans_local} Δραστική μείωση στους λογαριασμούς ρεύματος/καυσίμων και αποφυγή υπερθέρμανσης των μοτέρ.</li>
    <li><strong>🧪 Εξοικονόμηση άνω του 30%–40% στα λιπάσματα (N-P-K):</strong> Τα θρεπτικά συστατικά εγκλωβίζονται στη μήτρα του υδρογέλης αντί να εκπλένονται στα υπόγεια ύδατα.</li>
    <li><strong>🍇 Εξάλειψη θερμικού στρες & διατήρηση καρπόδεσης:</strong> Σταθερή παροχή υγρασίας που αποτρέπει την καρπόπτωση, διατηρεί μεγάλο εμπορικό μέγεθος και βέλτιστη ισορροπία σακχάρων (Brix).</li>
    <li><strong>🌱 100% επιτυχία ριζοβολίας στις νέες φυτεύσεις:</strong> Με τη χρήση της πάστας γέλης T100 μηδενίζονται οι απώλειες κατά τη μεταφύτευση.</li>
    <li><strong>⏳ 7 έως 10 ΧΡΟΝΙΑ συνεχούς δράσης με 1 μόνο εφαρμογή:</strong> Μία εφαρμογή αρκεί για μια δεκαετία. Το προϊόν βελτιώνει τον αερισμό του εδάφους και αποσβένεται πλήρως από τον 1ο χρόνο.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Επαγγελματικές Συσκευασίες & Άμεση Παραγγελία:</strong><br>
Το TERAWET-ORIGINAL διατίθεται σε επαγγελματικούς σάκους <strong>25 kg (360 €)</strong> για πλήρη κάλυψη εκτάσεων και σε συσκευασίες <strong>1 kg</strong> για δοκιμαστική εφαρμογή. Μπορείτε να παραγγείλετε άμεσα online από την επίσημη ιστοσελίδα μας:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Παραγγείλτε online στο {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Είμαστε στη διάθεσή σας για να σας υπολογίσουμε την ακριβή δοσολογία και το οικονομικό όφελος (ROI) για τα δικά σας στρέμματα ή για να κανονίσουμε δοκιμαστική παρτίδα.
</p>"""

            body_plain = f"""{contact_greeting},

Επικοινωνούμε μαζί σας σχετικά με τις καλλιεργητικές δραστηριότητες της {company} ({crops}) {reg_display}.
{pain_text}

Σε περιόδους καύσωνα (35-40°C), η παραδοσιακή άρδευση χάνει 40-50% του νερού σε εξάτμιση και διαρροή, παρασύροντας και τα ακριβά λιπάσματα N-P-K.

Το TERAWET-ORIGINAL® (οικολογικό υπεραπορροφητικό καλίου, 25 χρόνια εμπειρίας στην Ευρώπη) λειτουργεί ως έξυπνος υπόγειος ταμιευτήρας νερού στη ρίζα.

🌱 ΟΙ ΘΕΤΙΚΕΣ ΑΛΛΑΓΕΣ ΓΙΑ ΤΗΝ ΕΚΜΕΤΑΛΛΕΥΣΗ ΣΑΣ:
- 💧 Μείωση κατανάλωσης νερού κατά 50%-60% (απορροφά 400x το βάρος του σε νερό).
- ⚡ Έως 50% εξοικονόμηση ρεύματος για αντλίες ({trans_local}).
- 🧪 Εξοικονόμηση άνω του 30%-40% στα λιπάσματα N-P-K.
- 🍇 Εξάλειψη θερμικού στρες, διατήρηση καρπόδεσης, άριστο μέγεθος και Brix.
- 🌱 100% επιτυχία ριζοβολίας νέων φυτεύσεων με πάστα T100.
- ⏳ 7 έως 10 ΧΡΟΝΙΑ ενεργής δράσης με μία μόνο εφαρμογή (απόσβεση από τον 1ο χρόνο).

{crop_info['dosage_el'].replace('<strong>', '').replace('</strong>', '')}

ΣΥΣΚΕΥΑΣΙΕΣ ΚΑΙ ΠΑΡΑΓΓΕΛΙΑ:
- Σάκοι 25 kg (360 €) για εμπορικές εκτάσεις.
- Συσκευασία 1 kg για δοκιμές.
👉 Παραγγελίες online: {site}"""

        # -------------------------------------------------------------
        # 2. BULGARIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "bg":
            contact_greeting = f"Уважаеми екип на {company}" if not contact or contact in ["Team", "Admin"] else f"Уважаеми/а г-н/г-жо {contact}"
            reg_display = reg_info["region_name_bg"]
            pain_text = reg_info["pain_bg"]
            trans_local = reg_info["transform_local_bg"]
            dosage_text = crop_info["dosage_bg"]

            if v_mode == 1:
                subject = f"Намаляване на сметките за ток и поливане с 50% за {company} ({reg_display})"
            elif v_mode == 2:
                subject = f"Защита от горещини над 40°C и гарантирано качество на реколтата за {company} ({reg_display})"
            else:
                subject = f"50% икономия на вода и сигурен добив в условия на суша за {company} ({reg_display})"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Обръщаме се към Вас във връзка със стопанската дейност на <strong>{company}</strong> ({crops}) {reg_display}. 
Всички виждаме как през последните сезони {pain_text}
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
При температури над 35°C конвенционалното напояване губи до <strong>40%–50% от водата</strong> чрез бързо повърхностно изпарение и гравитационно оттичане в дълбочина. Заедно с водата се отмиват и скъпите водоразтворими N-P-K торове, а растенията остават в състояние на остър топлинен стрес.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
За трайно преодоляване на този проблем Ви представяме <strong>ТЕРАУЕТ-ОРИДЖИНАЛ®</strong> – сертифициран калиев суперабсорбент (чист екологичен полимер на калиева основа, без вреден натрий) с <strong>25 години доказан опит в България и ЕС</strong> (ВАНКО 97 ЕООД).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Положителните Трансформации за Вашето Стопанство:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Намаляване на поливната норма с над 50%–60%:</strong> Гранулите абсорбират и задържат до 400 пъти собственото си тегло във воден запас директно около корените (15–40 см дълбочина). Растението черпи влага чрез естествено осмотично налягане само при нужда.</li>
    <li><strong>⚡ Двойно по-малко разходи за електричество и помпи:</strong> {trans_local} По-малко работни часове на помпените агрегати означава директно спестяване на средства и защита на сондажите.</li>
    <li><strong>🧪 Спестяване на над 30%–40% от торовете:</strong> Хранителните вещества остават капсулирани в хидрогела, предотвратявайки отмиването им в подпочвените води.</li>
    <li><strong>🍇 Премахване на топлинния шок и запазване на реколтата:</strong> Предотвратява окапването на завръза, осигурява едри плодове с отличен захарен градус и висок търговски клас.</li>
    <li><strong>🌱 100% прихващане на млади насаждения:</strong> Кореновата паста Т100 гарантира нулева смъртност при разсаждане.</li>
    <li><strong>⏳ 7 до 10 ГОДИНИ активен живот в почвата:</strong> Еднократно внасяне гарантира действие за цяло десетилетие. Инвестицията се изплаща още през 1-вия сезон.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Професионални Опаковки & Директна Поръчка:</strong><br>
ТЕРАУЕТ се предлага в професионални чували <strong>25 кг (360 €)</strong> за стопански площи и в пакети от <strong>1 кг</strong> за опитни полета. Можете да поръчате директно онлайн от официалния ни сайт:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Поръчайте онлайн на {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
С удоволствие ще изготвим точна дозировка и разчет за изплащане на инвестицията (ROI) според Вашите декари.
</p>"""

            body_plain = f"""{contact_greeting},

Във връзка със стопанството на {company} ({crops}) {reg_display}:
{pain_text}

ТЕРАУЕТ-ОРИДЖИНАЛ® (калиев суперабсорбент, 25 години опит в ЕС) създава подземен воден резервоар директно в корените:
- 💧 50%-60% по-малко разход на вода за напояване;
- ⚡ 50% икономия на ток и гориво за помпите ({trans_local});
- 🧪 Над 30%-40% спестени N-P-K торове;
- 🍇 Защита от топлинен шок и окапване на плодовете;
- 🌱 100% прихващане на фиданки с гел Т100;
- ⏳ 7 до 10 ГОДИНИ действие в почвата с едно внасяне.

{crop_info['dosage_bg'].replace('<strong>', '').replace('</strong>', '')}

Опаковки: чували 25 кг (360 €) и 1 кг.
👉 Поръчки онлайн: {site}"""

        # -------------------------------------------------------------
        # 3. ROMANIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "ro":
            contact_greeting = f"Stimate colectiv al companiei {company}" if not contact or contact in ["Team", "Admin"] else f"Stimate d-le/d-nă {contact}"
            reg_display = reg_info.get("region_name_en", "în regiunea dumneavoastră")
            trans_local = reg_info.get("transform_local_en", "Reducerea ciclurilor de pompare cu 50% pentru 7-10 ani.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "ro")

            if v_mode == 1:
                subject = f"Reducerea costurilor de pompare cu 50% și siguranța recoltei pentru {company}"
            elif v_mode == 2:
                subject = f"Protecție împotriva caniculei (+40°C) și maximizarea calității recoltei pentru {company}"
            else:
                subject = f"Economie de 50% la apa de irigații și protecție împotriva secetei pentru {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Vă contactăm în legătură cu exploatația agricolă a companiei <strong>{company}</strong> ({crops}). În contextul secetelor prelungite, al scăderii dramatice a pânzei freatice și al costurilor ridicate cu energia pentru pompare, irigarea convențională pierde până la <strong>40%–50% din apă</strong> prin evaporare rapidă la suprafață și levigare profundă.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Pentru a rezolva definitiv această provocare, vă prezentăm tehnologia dovedită <strong>TERAWET-ORIGINAL®</strong> – polimer superabsorbant reticulat pe bază de <strong>potasiu</strong> (ecologic, non-toxic, fără sodiu dăunător) cu <strong>25 de ani de experiență în Europa</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Transformările Pozitive pentru Ferma Dumneavoastră:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Reducerea consumului de apă cu peste 50%–60%:</strong> Granulele absorb și rețin de până la 400 de ori greutatea lor în apă, creând un <em>rezervor subteran inteligent</em> chiar la nivelul rădăcinilor (15–40 cm).</li>
    <li><strong>⚡ Până la 50% economie la energia pentru pompare:</strong> {trans_local} Reducerea orelor de funcționare a pompelor protejează forajele și scade masiv facturile de energie.</li>
    <li><strong>🧪 Peste 30%–40% economie la îngrășăminte hidrosolubile:</strong> Substanțele nutritive N-P-K rămân fixate în matricea hidrogelului în loc să fie levigate în solul profund.</li>
    <li><strong>🍇 Eliminarea stresului termic & recolte superioare:</strong> Previne avortarea florilor și căderea fructelor în caniculă, menținând un calibru comercial ridicat și indice Brix optim.</li>
    <li><strong>🌱 Rată de prindere de 100% la transplantare:</strong> Utilizarea pastei de rădăcină T100 elimină complet șocul de transplantare al puieților.</li>
    <li><strong>⏳ Durată activă de 7 până la 10 ANI în sol:</strong> O singură aplicare este suficientă pentru un deceniu, cu amortizare încă din primul sezon.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Ambalaje Profesionale & Comandă Online Directă:</strong><br>
TERAWET-ORIGINAL este disponibil în saci profesionali de <strong>25 kg (360 €)</strong> pentru suprafețe agricole și pachete de <strong>1 kg</strong> pentru teste. Puteți comanda direct online pe site-ul nostru oficial:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Comandați online pe {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Suntem la dispoziția dumneavoastră pentru calcularea dozelor exacte și a randamentului investiției (ROI) pentru hectarele dumneavoastră.
</p>"""

            body_plain = f"""{contact_greeting},

În atenția fermei {company} ({crops}):
Irigarea tradițională pierde 40%-50% din apă prin evaporare și levigare.

TERAWET-ORIGINAL® (polimer superabsorbant pe bază de potasiu, 25 ani experiență în UE):
- 💧 Reducere cu 50%-60% a consumului de apă de irigații;
- ⚡ 50% economie la energia pentru pompare;
- 🧪 Peste 30%-40% economie la îngrășăminte N-P-K;
- 🍇 Eliminarea stresului termic și protecția recoltei la +40°C;
- 🌱 100% rată de prindere a puieților cu gelul T100;
- ⏳ 7 până la 10 ANI activ în sol după o singură aplicare.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Ambalaje: saci de 25 kg (360 €) și 1 kg.
👉 Comenzi online: {site}"""

        # -------------------------------------------------------------
        # 4. SPANISH COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "es":
            contact_greeting = f"Estimado equipo de {company}" if not contact or contact in ["Team", "Admin"] else f"Estimado/a {contact}"
            reg_display = reg_info.get("region_name_en", "en su zona agrícola")
            trans_local = reg_info.get("transform_local_en", "Reducción de ciclos de bombeo en un 50% durante 7 a 10 años.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "es")

            if v_mode == 1:
                subject = f"Reducción del 50% en costes de bombeo y electricidad para {company}"
            elif v_mode == 2:
                subject = f"Protección contra olas de calor (+40°C) y rendimiento asegurado para {company}"
            else:
                subject = f"50% de ahorro en agua de riego y blindaje frente a la sequía para {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Nos ponemos en contacto con motivo de la actividad agrícola de <strong>{company}</strong> ({crops}). Con las restricciones hídricas cada vez más severas, el descenso de los acuíferos y el desorbitado coste energético del bombeo, el riego convencional pierde entre el <strong>40% y el 50% del agua</strong> por evaporación y lixiviación antes de que llegue a la raíz.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Para aportar una solución definitiva, les presentamos <strong>TERAWET-ORIGINAL®</strong> – polímero superabsorbente reticulado a base de <strong>potasio</strong> (100% ecológico, sin sodio perjudicial) con <strong>25 años de trayectoria contrastada en Europa</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Transformaciones Positivas para su Explotación:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Ahorro superior al 50%–60% en agua de riego:</strong> Los gránulos absorben y retienen hasta 400 veces su peso en agua, creando un <em>depósito subterráneo inteligente</em> en la rizosfera (15–40 cm).</li>
    <li><strong>⚡ Reducción del 50% en facturas eléctricas de bombeo:</strong> {trans_local} Menos horas de pozo, menor desgaste de motores y protección activa de los sondeos.</li>
    <li><strong>🧪 Ahorro de más del 30%–40% en fertilizantes hidrosolubles:</strong> Los nutrientes N-P-K quedan retenidos en el hidrogel en lugar de lavarse hacia capas profundas.</li>
    <li><strong>🍇 Blindaje térmico y eliminación de la caída de fruto:</strong> Evita el estrés hídrico por encima de 40°C, asegurando calibre comercial óptimo y grado Brix constante.</li>
    <li><strong>🌱 100% de éxito en trasplante y nuevas plantaciones:</strong> Con la pasta radicular T100, se elimina completamente la mortandad de plantones.</li>
    <li><strong>⏳ Vida útil activa de 7 a 10 AÑOS en suelo:</strong> Una sola aplicación mantiene su eficacia durante una década, amortizándose desde la 1ª campaña.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Formatos Profesionales y Pedido Directo Online:</strong><br>
TERAWET-ORIGINAL se suministra en sacos profesionales de <strong>25 kg (360 €)</strong> para fincas comerciales y en envases de <strong>1 kg</strong> para ensayos. Puede cursar su pedido directamente online en nuestra web oficial:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Pedir online en {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Estamos a su entera disposición para calcular la dosis por hectárea y el retorno de inversión (ROI) estimado para sus cultivos.
</p>"""

            body_plain = f"""{contact_greeting},

Respecto a la explotación de {company} ({crops}):
El riego convencional pierde 40%-50% del agua por evaporación y lixiviación.

TERAWET-ORIGINAL® (polímero de potasio certificado, 25 años en Europa):
- 💧 50%-60% de reducción en consumo de agua;
- ⚡ 50% de ahorro en bombeo y energía eléctrica;
- 🧪 30%-40% de ahorro en fertilizantes N-P-K;
- 🍇 Protección frente a golpes de calor (>40°C) y retención del fruto;
- 🌱 100% de prendimiento de plantas con gel radicular T100;
- ⏳ 7 a 10 AÑOS de actividad en el suelo con 1 sola aplicación.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Formatos: sacos de 25 kg (360 €) y 1 kg.
👉 Pedidos online: {site}"""

        # -------------------------------------------------------------
        # 5. ITALIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "it":
            contact_greeting = f"Gentile team di {company}" if not contact or contact in ["Team", "Admin"] else f"Gentile {contact}"
            reg_display = reg_info.get("region_name_en", "nella vostra area agricola")
            trans_local = reg_info.get("transform_local_en", "Riduzione del 50% delle ore di pompaggio per 7-10 anni.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "it")

            if v_mode == 1:
                subject = f"Riduzione del 50% sui costi di pompaggio ed energia per {company}"
            elif v_mode == 2:
                subject = f"Protezione contro ondate di calore (+40°C) e resa garantita per {company}"
            else:
                subject = f"Risparmio del 50% sull'acqua di irrigazione e difesa dalla siccità per {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Vi contattiamo in merito all'attività agricola di <strong>{company}</strong> ({crops}). Con la crescente carenza idrica, il calo delle falde e l'impennata delle bollette elettriche per il pompaggio, l'irrigazione tradizionale perde fino al <strong>40%–50% dell'acqua</strong> per rapida evaporazione e percolazione profonda prima dell'assorbimento radicale.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Per offrire una soluzione definitiva, presentiamo <strong>TERAWET-ORIGINAL®</strong> – polimero superassorbente reticolato a base di <strong>potassio</strong> (100% ecologico, non tossico, senza sodio dannoso) con <strong>25 anni di comprovata esperienza sul campo in Europa</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Le Trasformazioni Positive per la Vostra Azienda Agricola:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Taglio del 50%–60% del consumo d'acqua:</strong> I granuli assorbono e trattengono fino a 400 volte il proprio peso in acqua, creando un <em>bacino idrico sotterraneo intelligente</em> nella rizosfera (15–40 cm).</li>
    <li><strong>⚡ Fino al 50% di risparmio su elettricità e carburante per pompe:</strong> {trans_local} Minori ore di funzionamento dei pozzi, salvaguardia dei motori e drastico taglio delle spese energetiche.</li>
    <li><strong>🧪 Oltre il 30%–40% di risparmio sui fertilizzanti idrosolubili:</strong> Gli elementi N-P-K rimangono trattenuti nella matrice dell'idrogel invece di disperdersi nelle falde.</li>
    <li><strong>🍇 Eliminazione dello stress termico e blocco della cascola:</strong> Difesa attiva contro temperature estreme (+40°C), garantendo calibri commerciali elevati e grado Brix ottimale.</li>
    <li><strong>🌱 100% di attecchimento per le giovani piante:</strong> L'immersione radicale nella pasta gel T100 elimina ogni shock da trapianto.</li>
    <li><strong>⏳ Da 7 a 10 ANNI di efficacia continua nel suolo:</strong> Una sola applicazione garantisce l'effetto per un decennio, ripagandosi fin dal primo ciclo produttivo.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Formati Professionali e Ordine Online Diretto:</strong><br>
TERAWET-ORIGINAL è disponibile in sacchi professionali da <strong>25 kg (360 €)</strong> per superfici commerciali e confezioni da <strong>1 kg</strong> per campi prova. Potete ordinare direttamente online sul nostro sito ufficiale:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Ordina online su {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Siamo a completa disposizione per elaborare un piano di dosaggio personalizzato per i vostri ettari e stimare il ritorno sull'investimento (ROI).
</p>"""

            body_plain = f"""{contact_greeting},

In merito all'azienda agricola {company} ({crops}):
L'irrigazione tradizionale disperde fino al 40%-50% dell'acqua per evaporazione e percolazione.

TERAWET-ORIGINAL® (superassorbente ecologico a base di potassio, 25 anni in Europa):
- 💧 50%-60% di riduzione del consumo idrico;
- ⚡ 50% di risparmio sui costi di pompaggio ed elettricità;
- 🧪 30%-40% di risparmio su fertilizzanti N-P-K;
- 🍇 Protezione totale da stress termico (+40°C) e cascola dei frutti;
- 🌱 100% attecchimento delle piantine con gel T100;
- ⏳ 7-10 ANNI di attività nel terreno con 1 sola applicazione.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Confezioni: sacchi da 25 kg (360 €) e 1 kg.
👉 Ordini online: {site}"""

        # -------------------------------------------------------------
        # 6. FRENCH COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "fr":
            contact_greeting = f"Chère équipe de {company}" if not contact or contact in ["Team", "Admin"] else f"Cher/Chère {contact}"
            reg_display = reg_info.get("region_name_en", "dans votre région")
            trans_local = reg_info.get("transform_local_en", "Réduction de 50% des heures de pompage pendant 7 à 10 ans.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "fr")

            if v_mode == 1:
                subject = f"Réduction de 50% des coûts d'énergie de pompage pour {company}"
            elif v_mode == 2:
                subject = f"Protection contre les canicules (+40°C) et récolte sécurisée pour {company}"
            else:
                subject = f"50% d'économie d'eau d'irrigation et bouclier anti-sécheresse pour {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Nous nous permettons de vous contacter au sujet de l'exploitation de <strong>{company}</strong> ({crops}). Face aux restrictions préfectorales croissantes, à la baisse critique des nappes phréatiques et à l'envolée des coûts énergétiques de pompage, l'irrigation conventionnelle perd près de <strong>40% à 50% de l'eau apportée</strong> par évaporation rapide et lessivage profond.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Pour apporter une réponse durable et éprouvée, nous vous présentons <strong>TERAWET-ORIGINAL®</strong> – polymère superabsorbant réticulé à base de <strong>potassium</strong> (écologique, sans sodium) fort de <strong>25 ans d'expérience sur le terrain en Europe</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Les Bénéfices Concrets pour Votre Exploitation :</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Réduction de plus de 50%–60% des apports d'eau :</strong> Les granulés captent et retiennent jusqu'à 400 fois leur poids en eau, créant une <em>véritable réserve souterraine active</em> au niveau racinaire (15–40 cm).</li>
    <li><strong>⚡ Jusqu'à 50% d'économie sur les dépenses de pompage :</strong> {trans_local} Préservation des forages et réduction majeure des factures d'électricité et de carburant.</li>
    <li><strong>🧪 Plus de 30%–40% d'engrais N-P-K préservés :</strong> Les éléments nutritifs solubles sont captés dans l'hydrogel et protégés du lessivage vers le sous-sol.</li>
    <li><strong>🍇 Zéro stress thermique & maintien de la nouaison :</strong> Protection totale au-delà de 40°C, éliminant la chute prématurée des fruits et assurant un calibre homogène et un Brix idéal.</li>
    <li><strong>🌱 100% de reprise racinaire sur jeunes plantations :</strong> Le pralinage dans le gel T100 élimine tout choc de repiquage.</li>
    <li><strong>⏳ 7 à 10 ANS d'action continue dans le sol :</strong> Une seule incorporation assure une décennie d'efficacité, amortie dès la première saison.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Conditionnements Professionnels & Commande en Ligne :</strong><br>
TERAWET-ORIGINAL est disponible en sacs professionnels de <strong>25 kg (360 €)</strong> pour les parcelles agricoles et en sachets tests de <strong>1 kg</strong>. Vous pouvez commander directement en ligne sur notre site officiel :
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Commander en ligne sur {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Nous restons à votre entière disposition pour calculer le dosage par hectare et le retour sur investissement (ROI) pour votre exploitation.
</p>"""

            body_plain = f"""{contact_greeting},

Concernant l'exploitation de {company} ({crops}):
L'arrosage conventionnel perd 40%-50% d'eau par évaporation et lessivage.

TERAWET-ORIGINAL® (superabsorbant potassique certifié, 25 ans d'expérience en Europe):
- 💧 Réduction de 50%-60% des besoins en eau d'irrigation;
- ⚡ 50% d'économie sur l'énergie et les heures de pompage;
- 🧪 Plus de 30%-40% d'engrais N-P-K préservés;
- 🍇 Élimination du stress thermique et protection de la nouaison;
- 🌱 100% de reprise racinaire des plants avec le gel T100;
- ⏳ 7 à 10 ANS d'action continue en sol avec 1 seule application.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Conditionnements: sacs de 25 kg (360 €) et 1 kg.
👉 Commandes en ligne: {site}"""

        # -------------------------------------------------------------
        # 7. GERMAN / AUSTRIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "de":
            contact_greeting = f"Sehr geehrtes Team von {company}" if not contact or contact in ["Team", "Admin"] else f"Sehr geehrte/r Frau/Herr {contact}"
            reg_display = reg_info.get("region_name_en", "in Ihrer Region")
            trans_local = reg_info.get("transform_local_en", "50% weniger Pumpstunden über 7 bis 10 Jahre hinweg.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "de")

            if v_mode == 1:
                subject = f"50% weniger Strom- und Pumpkosten für {company}"
            elif v_mode == 2:
                subject = f"Schutz vor Hitzewellen (+40°C) und gesicherte Erträge für {company}"
            else:
                subject = f"50% Bewässerungswasser sparen & Trockenschutz für {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
wir wenden uns an Sie bezüglich der landwirtschaftlichen Flächen von <strong>{company}</strong> ({crops}). Angesichts sinkender Grundwasserspiegel, strenger Bewässerungsauflagen und steigender Energiekosten verliert die herkömmliche Bewässerung bis zu <strong>40%–50% des Wassers</strong> durch Oberflächenverdunstung und Versickerung unterhalb des Wurzelbereichs.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Um dieses Problem nachhaltig zu lösen, stellen wir Ihnen <strong>TERAWET-ORIGINAL®</strong> vor – ein zertifiziertes, ökologisches <strong>Kalium</strong>-Superabsorber-Polymer (frei von schädlichem Natrium) mit <strong>25 Jahren Praxiserfahrung in Europa</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Die Messbaren Vorteile für Ihren Betrieb:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 50%–60% Einsparung von Bewässerungswasser:</strong> Das Granulat nimmt das bis zu 400-fache seines Eigengewichts an Wasser auf und bildet ein <em>aktives unterirdisches Feuchtigkeitsdepot</em> direkt an den Wurzeln (15–40 cm).</li>
    <li><strong>⚡ Bis zu 50% weniger Strom- und Kraftstoffkosten für Pumpen:</strong> {trans_local} Reduziert die Laufzeiten der Pumpenaggregate, schützt Brunnen und senkt Betriebskosten massiv.</li>
    <li><strong>🧪 Über 30%–40% Einsparung bei N-P-K Düngemitteln:</strong> Nährstoffe werden im Hydrogel gebunden und nicht mehr ungenutzt ins Grundwasser ausgewaschen.</li>
    <li><strong>🍇 Kein Hitzestress & Vermeidung von Fruchtfall:</strong> Aktiver Schutz bei Temperaturen über 40°C, verhindert Blüten- und Fruchtverlust und sichert erstklassige Kaliber und optimale Zuckerwerte (Brix).</li>
    <li><strong>🌱 100% Anwachserfolg bei Neuanpflanzungen:</strong> Die T100 Wurzelpaste schützt Jungpflanzen vollständig vor dem Pflanzschock.</li>
    <li><strong>⏳ 7 bis 10 JAHRE kontinuierlich im Boden aktiv:</strong> Eine einzige Einarbeitung wirkt ein ganzes Jahrzehnt und amortisiert sich bereits in der ersten Saison.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Profi-Gebinde & Direkte Online-Bestellung:</strong><br>
TERAWET-ORIGINAL ist in professionellen <strong>25 kg Säcken (360 €)</strong> für landwirtschaftliche Nutzflächen sowie in <strong>1 kg</strong> Probepackungen erhältlich. Sie können direkt online über unsere offizielle Webseite bestellen:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Online bestellen unter {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Gerne berechnen wir für Sie die exakte Dosierung pro Hektar und die erwartete Rentabilität (ROI) für Ihre Kulturen.
</p>"""

            body_plain = f"""{contact_greeting},

Bezüglich des Betriebs von {company} ({crops}):
Bei konventioneller Bewässerung gehen 40%-50% des Wassers durch Verdunstung und Versickerung verloren.

TERAWET-ORIGINAL® (zertifizierter Kalium-Superabsorber, 25 Jahre Erfahrung in der EU):
- 💧 50%-60% weniger Bewässerungswasser;
- ⚡ 50% Ersparnis bei Pump- und Stromkosten;
- 🧪 30%-40% Einsparung bei N-P-K Düngemitteln;
- 🍇 Beseitigung von Hitzestress (+40°C) und Fruchtfall;
- 🌱 100% Anwachsquote von Jungpflanzen mit T100 Gel;
- ⏳ 7 bis 10 JAHRE Wirkungsdauer im Boden mit 1 Anwendung.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Gebinde: 25 kg Säcke (360 €) & 1 kg Packungen.
👉 Online bestellen: {site}"""

        # -------------------------------------------------------------
        # 8. HUNGARIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "hu":
            contact_greeting = f"Tisztelt {company} Csapata!" if not contact or contact in ["Team", "Admin"] else f"Tisztelt {contact}!"
            reg_display = reg_info.get("region_name_en", "az Önök térségében")
            trans_local = reg_info.get("transform_local_en", "50%-kal kevesebb szivattyúzási üzemóra 7-10 éven át.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "hu")

            if v_mode == 1:
                subject = f"Akár 50% szivattyúzási energiamegtakarítás a(z) {company} számára"
            elif v_mode == 2:
                subject = f"Hőséghullámok elleni védelem és garantált termésbiztonság a(z) {company} részére"
            else:
                subject = f"50% öntözővíz megtakarítás és aszály elleni védelem a(z) {company} részére"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting}</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Megkeresésünk oka a(z) <strong>{company}</strong> gazdálkodási tevékenysége ({crops}). A visszatérő aszályos időszakok, a csökkenő talajvízszint és a magas öntözési áramköltségek mellett a hagyományos öntözés során az <strong>öntözővíz 40%–50%-a elvész</strong> a gyors felületi párolgás és a mélybe szivárgás miatt.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
A probléma tartós megoldására bemutatjuk a <strong>TERAWET-ORIGINAL®</strong> technológiát – prémium minőségű, környezetbarát <strong>kálium</strong> alapú szuperabszorbens talajkondicionálót (nem tartalmaz káros nátriumot), <strong>25 éves európai szántóföldi tapasztalattal</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Pozitív Változások az Önök Gazdaságában:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 50%–60% öntözővíz megtakarítás:</strong> A szemcsék saját tömegük 400-szorosát kötik meg vízben, <em>aktív földalatti víztározót</em> képezve közvetlenül a gyökérzónában (15–40 cm mélységben).</li>
    <li><strong>⚡ Akár 50% szivattyúzási és áramköltség-csökkenés:</strong> {trans_local} Kevesebb szivattyú-üzemóra, a kutak és berendezések kímélése, közvetlen megtakarítás.</li>
    <li><strong>🧪 Több mint 30%–40% műtrágya megtakarítás:</strong> Az N-P-K tápanyagok a hidrogél hálóban maradnak, nem mosódnak ki a mélyebb rétegekbe.</li>
    <li><strong>🍇 Hőségsokk és gyümölcshullás megszüntetése:</strong> Hatékony védelem 40°C feletti kánikulában, optimális bogyóméret és stabil Brix-cukorfok.</li>
    <li><strong>🌱 100%-os megeredési arány új telepítéseknél:</strong> A T100 gyökérmártó paszta megakadályozza a csemeték pusztulását.</li>
    <li><strong>⏳ 7–10 ÉV aktív élettartam a talajban:</strong> Egyetlen kijuttatás egy teljes évtizedre elegendő nedvességvédelmet nyújt, és már az 1. szezonban megtérül.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Professzionális Kiszerelés & Közvetlen Online Rendelés:</strong><br>
A TERAWET-ORIGINAL professzionális <strong>25 kg-os zsákokban (360 €)</strong> kapható üzemi felületekre, valamint <strong>1 kg-os</strong> próbacsomagban. Megrendelését közvetlenül leadhatja hivatalos weboldalunkon:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Rendeljen online a {site} oldalon</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Készséggel kiszámítjuk a pontos hektáronkénti adagolást és a várható megtérülést (ROI) az Önök ültetvényeire.
</p>"""

            body_plain = f"""{contact_greeting}

A(z) {company} ({crops}) gazdálkodása kapcsán:
A hagyományos öntözés során a víz 40%-50%-a párolgással és elszivárgással elvész.

TERAWET-ORIGINAL® (kálium alapú szuperabszorbens, 25 év tapasztalat az EU-ban):
- 💧 50%-60% öntözővíz megtakarítás;
- ⚡ 50% szivattyúzási és energiamegtakarítás;
- 🧪 30%-40% műtrágya megtakarítás (nincs kimosódás);
- 🍇 Védelem a 40°C feletti hőséghullámok és gyümölcshullás ellen;
- 🌱 100%-os csemete-megeredés a T100 géllel;
- ⏳ 7-10 ÉV aktív hatás a talajban 1etlen kezeléssel.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Kiszerelés: 25 kg-os zsákok (360 €) és 1 kg-os tesztcsomag.
👉 Online rendelés: {site}"""

        # -------------------------------------------------------------
        # 9. SLOVENIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "sl":
            contact_greeting = f"Spoštovana ekipa {company}" if not contact or contact in ["Team", "Admin"] else f"Spoštovani {contact}"
            reg_display = reg_info.get("region_name_en", "na vašem območju")
            trans_local = reg_info.get("transform_local_en", "50% manj obratovalnih ur črpalk za 7 do 10 let.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "sl")

            if v_mode == 1:
                subject = f"50% nižji stroški črpanja vode in zaščita pridelka za {company}"
            elif v_mode == 2:
                subject = f"Zaščita kmetijskih površin pred vročinskimi valovi (+40°C) za {company}"
            else:
                subject = f"50% prihranek vode pri namakanju in zaščita pred sušo za {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Obračamo se na vas glede kmetijske dejavnosti podjetja <strong>{company}</strong> ({crops}). Zaradi vse daljših sušnih obdobij, upadanja podtalnice in visokih stroškov električne energije pri črpanju se pri klasičnem namakanju izgubi do <strong>40%–50% vode</strong> zaradi hitrega izhlapevanja in pronicanja v globino.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Za trajno rešitev vam predstavljamo <strong>TERAWET-ORIGINAL®</strong> – certificiran ekološki zamreženi <strong>kalijev</strong> superabsorbent (brez natrija) s <strong>25 leti dokazanih izkušenj v Evropi</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Pozitivne Spremembe za Vašo Kmetijsko Dejavnost:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Zmanjšanje porabe vode za 50%–60%:</strong> Granule vsrkajo do 400-kratnik lastne teže v vodi in ustvarijo <em>podzemni vodni rezervoar</em> neposredno v koreninski coni (15–40 cm).</li>
    <li><strong>⚡ Do 50% prihranka pri energiji za črpanje:</strong> {trans_local} Manj obratovalnih ur črpalnih agregatov varuje vrtine in drastično znižuje stroške.</li>
    <li><strong>🧪 Več kot 30%–40% prihranka pri gnojilih N-P-K:</strong> Hranila ostanejo ujeta v hidrogelu, namesto da se izpirajo v podtalnico.</li>
    <li><strong>🍇 Odprava toplotnega stresa in zaščita pridelka:</strong> Ohranja nastavek plodov v vročini nad 40°C, zagotavlja odlično debelino in optimalno sladkorno stopnjo (Brix).</li>
    <li><strong>🌱 100% ukoreninjenje mladih sadik:</strong> Pomakanje korenin v gel T100 prepreči presaditveni šok.</li>
    <li><strong>⏳ 7 do 10 LET aktivnega delovanja v tleh:</strong> En sam vnos zadostuje za celo desetletje in se povrne že v prvi sezoni.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Profesionalna Pakiranja & Spletno Naročilo:</strong><br>
TERAWET-ORIGINAL je dobavljiv v profesionalnih vrečah po <strong>25 kg (360 €)</strong> za kmetijske površine ter v poskusnih pakiranjih po <strong>1 kg</strong>. Naročilo lahko oddate neposredno prek spleta:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Naročite prek spleta na {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Z veseljem vam pripravimo natančen izračun odmerka na hektar in oceno donosnosti naložbe (ROI).
</p>"""

            body_plain = f"""{contact_greeting},

Glede kmetijske dejavnosti {company} ({crops}):
Pri običajnem namakanju se izgubi 40%-50% vode zaradi izhlapevanja in izpiranja.

TERAWET-ORIGINAL® (kalijev superabsorbent, 25 let izkušenj v EU):
- 💧 50%-60% prihranek vode pri namakanju;
- ⚡ 50% nižji stroški črpanja in električne energije;
- 🧪 30%-40% prihranka pri vodotopnih N-P-K gnojilih;
- 🍇 Zaščita pred toplotnim stresom (+40°C) in ohranitev pridelka;
- 🌱 100% ukoreninjenje sadik s pasto T100;
- ⏳ 7 do 10 LET delovanja v tleh z enim vnosom.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Pakiranje: 25 kg vreče (360 €) in 1 kg.
👉 Naročila prek spleta: {site}"""

        # -------------------------------------------------------------
        # 10. SLOVAK COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "sk":
            contact_greeting = f"Vážený tím spoločnosti {company}" if not contact or contact in ["Team", "Admin"] else f"Vážený/á {contact}"
            reg_display = reg_info.get("region_name_en", "vo vašom regióne")
            trans_local = reg_info.get("transform_local_en", "50% zníženie prevádzkových hodín čerpadiel na 7 až 10 rokov.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "sk")

            if v_mode == 1:
                subject = f"Zníženie nákladov na čerpanie vody o 50% pre {company}"
            elif v_mode == 2:
                subject = f"Ochrana pred horúčavami nad 40°C a stabilná úroda pre {company}"
            else:
                subject = f"50% úspora závlahovej vody a ochrana pred suchom pre {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Obraciame sa na Vás v súvislosti s pestovateľskou činnosťou spoločnosti <strong>{company}</strong> ({crops}). V dôsledku opakujúcich sa období sucha, poklesu spodných vôd a rastúcich nákladov na energie sa pri konvenčnej závlahe stráca až <strong>40%–50% vody</strong> rýchlym výparom a gravitačným priesakom mimo koreňovej zóny.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Na trvalé vyriešenie tohto problému Vám predstavujeme <strong>TERAWET-ORIGINAL®</strong> – certifikovaný ekologický sieťovaný <strong>draselný</strong> superabsorbent (bez škodlivého sodíka) s <strong>25-ročnou overenou praxou v Európe</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Pozitívne Zmeny pre Vaše Hospodárstvo:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Zníženie spotreby vody o viac ako 50%–60%:</strong> Granuly absorbujú až 400-násobok svojej hmotnosti vo vode a vytvárajú <em>podzemný vodný rezervoár</em> priamo v koreňovej zóne (15–40 cm).</li>
    <li><strong>⚡ Až 50% úspora elektrickej energie a paliva pri čerpaní:</strong> {trans_local} Menej motohodín čerpadiel šetrí studne a znižuje prevádzkové náklady.</li>
    <li><strong>🧪 Viac ako 30%–40% úspora N-P-K hnojív:</strong> Živiny zostávajú viazané v hydrogéli a nevyplavujú sa do spodných vôd.</li>
    <li><strong>🍇 Eliminácia teplotného šoku a opadávania plodov:</strong> Spoľahlivá ochrana pri teplotách nad 40°C, zabezpečenie vysokej trhovej kvality a optimálnej cukornatosti (Brix).</li>
    <li><strong>🌱 100% ujatie mladých výsadieb:</strong> Koreňová gélová pasta T100 eliminuje straty pri výsadbe sadeníc.</li>
    <li><strong>⏳ 7 až 10 ROKOV aktívneho účinku v pôde:</strong> Jednorazová aplikácia postačuje na celé desaťročie s návratnosťou už v 1. sezóne.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Profesionálne Balenia & Priama Online Objednávka:</strong><br>
TERAWET-ORIGINAL dodávame v profesionálnych <strong>25 kg vreciach (360 €)</strong> pre poľnohospodárske plochy a v <strong>1 kg</strong> testovacích baleniach. Objednávku môžete zadať priamo online na našom webe:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Objednávajte online na {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Radi pre Vás pripravíme presný prepočet dávkovania na hektár a kalkuláciu návratnosti investície (ROI).
</p>"""

            body_plain = f"""{contact_greeting},

K hospodáreniu spoločnosti {company} ({crops}):
Pri bežnom zavlažovaní sa stráca 40%-50% vody výparom a priesakom.

TERAWET-ORIGINAL® (draselný superabsorbent, 25 rokov praxe v EÚ):
- 💧 50%-60% úspora závlahovej vody;
- ⚡ 50% zníženie nákladov na čerpanie vody;
- 🧪 30%-40% úspora N-P-K hnojív pred vyplavením;
- 🍇 Ochrana pred horúčavami (+40°C) a opadávaním plodov;
- 🌱 100% ujatie sadeníc s pastou T100;
- ⏳ 7 až 10 ROKOV účinku v pôde po 1 aplikácii.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Balenie: 25 kg vrecia (360 €) a 1 kg balenia.
👉 Online objednávka: {site}"""

        # -------------------------------------------------------------
        # 11. SERBIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "sr":
            contact_greeting = f"Поштовани тиме компаније {company}" if not contact or contact in ["Team", "Admin"] else f"Поштовани/а {contact}"
            reg_display = reg_info.get("region_name_sr", reg_info.get("region_name_en", "у вашем региону"))
            trans_local = reg_info.get("transform_local_sr", "50% мање радних сати пумпи током 7 до 10 година.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "sr")

            if v_mode == 1:
                subject = f"50% уштеде на струји и гориву за наводњавање за {company} ({reg_display})"
            elif v_mode == 2:
                subject = f"Заштита од топлотног удара преко +38°C и очување приноса за {company} ({reg_display})"
            else:
                subject = f"50% уштеда воде за наводњавање и заштита од суше за {company} ({reg_display})"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Обраћамо вам се поводом пољопривредне производње компаније <strong>{company}</strong> ({crops}) {reg_display}. 
Услед све израженијих летњих суша, пада нивоа подземних вода и високих трошкова енергије за пумпе, традиционално наводњавање губи чак <strong>40%–50% воде</strong> због брзог испаравања и понирања у дубље слојеве земљишта пре него што је корен усвоји.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Као проверено решење за ове изазове, представљамо вам <strong>TERAWET-ORIGINAL®</strong> – сертификовани еколошки умрежени <strong>калијумов</strong> суперапсорбент (без штетног натријума) са <strong>25 година доказаног искуства у Европи</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Позитивне Промене за Ваше Имање уз TERAWET®:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Смањење потрошње воде за 50%–60%:</strong> Грануле упијају и до 400 пута више воде од сопствене тежине, стварајући <em>«паметни подземни резервоар»</em> у зони корена (15–40 cm). Вода се биљци ослобађа искључиво осмотским притиском корена по потреби.</li>
    <li><strong>⚡ До 50% мање потрошње струје и горива за пумпе:</strong> {trans_local} Чува бунаре, продужава век трајања пумпи и драстично смањује рачуне.</li>
    <li><strong>🧪 Преко 30%–40% уштеде на водорастворљивим ђубривима (N-P-K):</strong> Хранљиве материје се задржавају у хидрогелу и не испирају у дубље слојеве.</li>
    <li><strong>🍇 Елиминисање топлотног стреса и опадања плодова:</strong> Сигурна заштита у току врелих таласа (+38°C), очување крупноће, одличан квалитет и висок садржај шећера (Brix).</li>
    <li><strong>🌱 100% пријем младих садница:</strong> Коришћењем гел-пасте T100 у потпуности се избегава шок приликом пресађивања.</li>
    <li><strong>⏳ 7 до 10 ГОДИНА континуираног дејства само једном применом:</strong> Једна апликација делује читаву деценију и у потпуности се исплати већ у првој сезони.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Професионална Паковања & Директна Онлајн Поруџбина:</strong><br>
TERAWET-ORIGINAL испоручујемо у професионалним врећама од <strong>25 kg (360 €)</strong> за веће пољопривредне површине и у пробним паковањима од <strong>1 kg</strong>. Поруџбину можете извршити директно путем нашег сајта:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Поручите онлајн на {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Стојимо вам на располагању за прецизан прорачун дозирања по хектару и калкулацију финансијске исплативости (ROI) за ваше имање.
</p>"""

            body_plain = f"""{contact_greeting},

Обраћамо вам се поводом пољопривредне производње {company} ({crops}) {reg_display}.
При класичном наводњавању губи се 40%-50% воде услед испаравања и испирања у дубину.

TERAWET-ORIGINAL® (калијумов суперапсорбент, 25 година искуства у Европи):
- 💧 50%-60% уштеде воде за наводњавање (упија 400x своје тежине);
- ⚡ 50% мањи трошкови струје и горива за пумпе ({trans_local});
- 🧪 30%-40% уштеде на водорастворљивим N-P-K ђубривима;
- 🍇 Елиминисање топлотног стреса (+38°C) и заштита плода;
- 🌱 100% пријем садница уз T100 пасту;
- ⏳ 7 до 10 ГОДИНА дејства у земљишту из само једне примене.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Паковања: 25 kg вреће (360 €) и 1 kg.
👉 Директна онлајн поруџбина: {site}"""

        # -------------------------------------------------------------
        # 12. CROATIAN COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "hr":
            contact_greeting = f"Poštovani tim tvrtke {company}" if not contact or contact in ["Team", "Admin"] else f"Poštovani/a {contact}"
            reg_display = reg_info.get("region_name_hr", reg_info.get("region_name_en", "u vašoj regiji"))
            trans_local = reg_info.get("transform_local_hr", "50% manje radnih sati crpki tijekom 7 do 10 godina.")
            dosage_text = self._get_crop_dosage(crop_info["niche"], "hr")

            if v_mode == 1:
                subject = f"50% uštede na struji i gorivu za crpljenje vode za {company} ({reg_display})"
            elif v_mode == 2:
                subject = f"Zaštita nasada od toplinskog vala iznad +38°C i očuvanje uroda za {company} ({reg_display})"
            else:
                subject = f"50% ušteda vode pri navodnjavanju i zaštita od suše za {company} ({reg_display})"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Javljamo Vam se vezano uz poljoprivrednu proizvodnju tvrtke <strong>{company}</strong> ({crops}) {reg_display}. 
Zbog sve dužih ljetnih suša, pada razine podzemnih voda i rasta troškova energije za crpke, konvencionalnim navodnjavanjem gubi se i do <strong>40%–50% vode</strong> zbog brzog isparavanja i prodiranja u dublje slojeve tla prije nego što je korijenje stigne iskoristiti.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Kao trajno i dokazano rješenje predstavljamo Vam <strong>TERAWET-ORIGINAL®</strong> – certificirani ekološki umreženi <strong>kalijev</strong> superapsorbent (bez štetnog natrija) s <strong>25 godina dokazanog iskustva u Europi</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Pozitivne Promjene za Vaše Gospodarstvo uz TERAWET®:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Smanjenje potrošnje vode za 50%–60%:</strong> Granule upijaju do 400 puta više vode od vlastite mase, stvarajući <em>«podzemni vodeni spremnik»</em> u zoni korijena (15–40 cm). Voda se biljci oslobađa isključivo putem prirodnog osmotskog tlaka prema stvarnim potrebama.</li>
    <li><strong>⚡ Do 50% manje radnih sati crpki i ušteda energije:</strong> {trans_local} Štiti bušotine, produljuje vijek trajanja crpnih sustava i značajno smanjuje račune.</li>
    <li><strong>🧪 Preko 30%–40% uštede na vodotopivim N-P-K gnojivima:</strong> Hranjiva ostaju vezana u hidrogelu umjesto da se ispiru u podzemne vode.</li>
    <li><strong>🍇 Zaštita od toplinskog stresa i opadanja plodova:</strong> Pouzdano sprječava zastoje u vegetaciji pri temperaturama iznad 38°C, osigurava vrhunski kalibar i uravnotežene šećere (Brix).</li>
    <li><strong>🌱 100% uspješnost ukorjenjivanja mladih sadnica:</strong> Uranjanjem korijena u T100 gel pastu potpuno se uklanja stres presađivanja.</li>
    <li><strong>⏳ 7 do 10 GODINA aktivnog djelovanja u tlu nakon samo jedne primjene:</strong> Jedna primjena dostatna je za čitavo desetljeće uz povrat ulaganja već u prvoj sezoni.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Profesionalna Pakiranja & Izravna Online Narudžba:</strong><br>
TERAWET-ORIGINAL isporučujemo u profesionalnim vrećama od <strong>25 kg (360 €)</strong> za poljoprivredne površine i u probnim pakiranjima od <strong>1 kg</strong>. Narudžbu možete izvršiti izravno putem našeg weba:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Naručite online na {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
Rado ćemo za Vas izraditi točan izračun doze po hektaru i procjenu povrata investicije (ROI) za Vaše nasade.
</p>"""

            body_plain = f"""{contact_greeting},

Javljamo Vam se u vezi poljoprivredne proizvodnje tvrtke {company} ({crops}) {reg_display}.
Pri klasičnom navodnjavanju gubi se 40%-50% vode zbog isparavanja i ispiranja u dubinu.

TERAWET-ORIGINAL® (kalijev superapsorbent, 25 godina iskustva u Europi):
- 💧 50%-60% smanjenje potrošnje vode za navodnjavanje;
- ⚡ 50% niži troškovi crpljenja vode i električne energije ({trans_local});
- 🧪 30%-40% uštede na vodotopivim N-P-K gnojivima;
- 🍇 Otklanjanje toplinskog stresa (+38°C) i zaštita plodova;
- 🌱 100% primitak sadnica uz T100 gel pastu;
- ⏳ 7 do 10 GODINA djelovanja u tlu uz samo 1 primjenu.

{dosage_text.replace('<strong>', '').replace('</strong>', '')}

Pakiranja: 25 kg vreće (360 €) i 1 kg pakiranja.
👉 Online narudžba: {site}"""

        # -------------------------------------------------------------
        # 13. ENGLISH / INTERNATIONAL FALLBACK
        # -------------------------------------------------------------
        else:
            contact_greeting = f"Dear {company} Team" if not contact or contact in ["Team", "Admin"] else f"Dear {contact}"
            reg_display = reg_info["region_name_en"]
            pain_text = reg_info["pain_en"]
            trans_local = reg_info["transform_local_en"]
            dosage_text = crop_info["dosage_en"]

            if v_mode == 1:
                subject = f"50% Lower Pump Electricity & Fuel Costs for {company} ({reg_display})"
            elif v_mode == 2:
                subject = f"Protection against +40°C Heatwaves and Secured Yield for {company} ({reg_display})"
            else:
                subject = f"50% Irrigation Water Savings & Drought Immunity for {company} ({reg_display})"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
I am reaching out regarding the operations of <strong>{company}</strong> ({crops}) {reg_display}. 
As growers face severe heatwaves, dropping water tables, and escalating pumping tariffs, conventional irrigation loses up to <strong>40%–50% of applied water</strong> to rapid evaporation and deep leaching before root uptake.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
To secure yields and reduce water reliance, we introduce <strong>TERAWET-ORIGINAL®</strong> – certified eco-friendly <strong>potassium</strong> superabsorbent (not sodium) with <strong>25 years of proven field performance in Europe</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Positive Transformations for Your Farm:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 50%–60% Reduction in Irrigation Water:</strong> Granules swell up to 400x in water, creating a subterranean reservoir right at the root zone (15–40 cm).</li>
    <li><strong>⚡ Up to 50% Lower Pump Electricity & Fuel Costs:</strong> {trans_local} Protects boreholes and extends pump lifespan.</li>
    <li><strong>🧪 Over 30%–40% Savings on Water-Soluble Fertilizers:</strong> N-P-K nutrients are captured in the gel matrix rather than leaching into deep subsoils.</li>
    <li><strong>🍇 Thermal Shock Immunity & Fruit Retention:</strong> Eliminates blossom and fruit drop during peak +40°C heat, boosting caliber and Brix.</li>
    <li><strong>🌱 100% Rooting Success on New Plantings:</strong> T100 root dipping paste eliminates transplanting shock completely.</li>
    <li><strong>⏳ Active in Soil for 7 to 10 YEARS from a single application:</strong> Full capital payback achieved in the first season.</li>
  </ul>
</div>

<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin: 20px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
  {dosage_text}
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>Packaging & Direct Online Ordering:</strong><br>
TERAWET-ORIGINAL is supplied in professional <strong>25 kg sacks (360 €)</strong> for commercial acreage and <strong>1 kg packs</strong> for trials. Orders can be placed directly online:
</p>

<p style="margin: 24px 0 28px 0; text-align: left;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">👉 Order online at {site}</a>
</p>

<p style="font-size: 14.5px; line-height: 1.6; color: #475569;">
We are available to calculate exact acreage dosages and expected financial ROI for your property.
</p>"""

            body_plain = f"""{contact_greeting},

Regarding {company} ({crops}) {reg_display}:
{pain_text}

TERAWET-ORIGINAL® (certified potassium superabsorbent, 25 years in EU):
- 💧 50%-60% reduction in irrigation water;
- ⚡ 50% lower pump energy expenses ({trans_local});
- 🧪 30%-40% savings on water-soluble fertilizers;
- 🍇 Complete protection against heat stress and fruit drop;
- 🌱 100% sapling survival with T100 gel;
- ⏳ 7 to 10 YEARS continuous activity from 1 application.

{crop_info['dosage_en'].replace('<strong>', '').replace('</strong>', '')}

Packaging: 25 kg sacks (360 €) & 1 kg packs.
👉 Online orders: {site}"""

        part_html, part_plain = self._get_partnership_proposal(lang)
        body_html = body_html + "\n\n" + part_html
        body_plain = body_plain + "\n\n" + part_plain

        return subject, body_html, body_plain
