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
    "pt": "Portuguese (Português)",
    "hr": "Croatian (Hrvatski)",
    "sl": "Slovenian (Slovenščina)",
    "sk": "Slovak (Slovenčina)",
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
            "fr": "Pour vous désinscrire de ces communications, répondez 'Désinscription'.",
            "pt": "Para cancelar a subscrição, responda com 'Remover'.",
            "hr": "Ako ne želite primati daljnje poruke, odgovorite s 'Odjava'.",
            "sl": "Za odjavo od obvestil odgovorite z 'Odjava'.",
            "sk": "Ak si neželáte dostávať ďalšie správy, odpovedzte 'Odhlásiť'.",
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

        # 8. General Mediterranean Fallback
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

    def _detect_crop_niche(self, lead: Dict[str, str]) -> Dict[str, str]:
        """Classifies crop/segment for targeted agronomic recommendations."""
        text = f"{lead.get('crops', '')} {lead.get('category', '')} {lead.get('company_name', '')}".lower()

        if any(k in text for k in ['οινοποι', 'αμπελ', 'κρασ', 'winery', 'vineyard', 'wine', 'винарна', 'лозя']):
            return {
                "niche": "vineyard",
                "dosage_el": "<strong>Για Αμπελώνες:</strong> 10–15 g TERAWET® T400 στη ριζόσφαιρα κάθε πρέμνου (ή κατά τη φύτευση) εξασφαλίζουν συνεχή διαθεσιμότητα υγρασίας χωρίς υπερβολική βλαστική ανάπτυξη. Αποτρέπεται το θερμικό σοκ, ενισχύεται η σύνθεση ανθοκυανών, ομοιόμορφος δείκτης Brix και σταθερή οξύτητα.",
                "dosage_bg": "<strong>За лозови масиви:</strong> 10–15 г ТЕРАУЕТ Т400 в кореновата зона осигуряват постоянен воден буфер. Предотвратява пригора на гроздето, гарантира едри зърна, отличен захарен градус и стабилен добив.",
                "dosage_en": "<strong>For Vineyards:</strong> 10–15 g TERAWET® T400 applied directly to the root zone of each vine locks in moisture for 7–10 years. Prevents thermal shutdown, protects grape bunches, and secures optimal Brix and balanced acidity."
            }

        if any(k in text for k in ['φυτώρι', 'nursery', 'разсадник', 'garden center', 'κηποτεχν', 'landscape', 'κήπο']):
            return {
                "niche": "nursery",
                "dosage_el": "<strong>Για Φυτώρια & Νέες Φυτεύσεις:</strong> Εμβάπτιση των γυμνών ριζών σε πάστα γέλης TERAWET® T100 (5–8 g/L νερού) εγγυάται <strong>100% επιτυχία ριζοβολίας</strong> χωρίς μεταφυτευτικό σοκ. Για υποστρώματα σε γλάστρες, η ενσωμάτωση T400 (1.5–2 kg/m³) μειώνει τη συχνότητα ποτίσματος κατά 60%.",
                "dosage_bg": "<strong>За разсадници и нови насаждения:</strong> Потапянето на корените в гел-паста ТЕРАУЕТ Т100 (5–8 г/л вода) гарантира <strong>100% прихващане на фиданките</strong>. В субстрати за саксии Т400 съкращава поливките с 60%.",
                "dosage_en": "<strong>For Nurseries & Transplanting:</strong> Dipping bare roots in TERAWET® T100 gel paste (5–8 g/L water) secures <strong>100% root establishment</strong> with zero transplant shock. For pot substrates, T400 reduces irrigation frequency by over 60%."
            }

        if any(k in text for k in ['ελαι', 'olive', 'οπωρ', 'orchard', 'δένδρ', 'овощ', 'ябъл', 'череш', 'прасков', 'εσπεριδ', 'citrus']):
            return {
                "niche": "orchard",
                "dosage_el": "<strong>Για Ελαιώνες & Δενδρώδεις:</strong> 15–25 g TERAWET® T400 ανά δέντρο στη ζώνη των απορροφητικών ριζιδίων. Αποτρέπει την καλοκαιρινή καρπόπτωση, εξασφαλίζει μεγαλύτερη καλίμπρα καρπών και σταθερή ανθοφορία την επόμενη σεζόν.",
                "dosage_bg": "<strong>За овощни градини и маслини:</strong> 15–25 г ТЕРАУЕТ Т400 на дърво в активната коренова зона. Спира окапването на завръза в юлските жеги и гарантира едър, качествен плод.",
                "dosage_en": "<strong>For Orchards & Olive Groves:</strong> 15–25 g TERAWET® T400 per tree in the active feeder root zone. Prevents premature fruit shedding during heatwaves, ensuring superior fruit caliber and oil accumulation."
            }

        # Default / Vegetables / Field / Agro suppliers
        return {
            "niche": "general_agro",
            "dosage_el": "<strong>Για Υπαίθριες & Θερμοκηπιακές Καλλιέργειες:</strong> 2–3 kg TERAWET® T400 ανά στρέμμα (1000 m²) ή 10–15 g ανά φυτό. Δημιουργεί ένα ενεργό υδροστρώμα διάρκειας 7–10 ετών, μειώνοντας την κατανάλωση νερού και λιπασμάτων στο μισό.",
            "dosage_bg": "<strong>За зеленчуци, полски и оранжерийни култури:</strong> 2–3 кг ТЕРАУЕТ Т400 на декар или 10–15 г под корен. Осигурява балансирано хранене и съкращава поливните норми с над 50%.",
            "dosage_en": "<strong>For Commercial Crops & Greenhouses:</strong> 2–3 kg TERAWET® T400 per 1,000 m² (or 10–15 g per root). Forms an active 7–10 year moisture cushion, halving water and fertilizer demands."
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
6. CALL TO ACTION (CTA):
   - Clear, respectful invitation to order online or receive a customized acreage calculation via phone/WhatsApp.
7. FORMAT: Return JSON strictly:
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

Highlight the regional drought reality, the positive transformations with TERAWET, dosage, 25 kg sacks (360 €) / 1 kg packs, and online ordering at https://www.tera-wet.com.
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

    def _generate_with_template(self, lead: Dict[str, str], lang: str, variant: int = 0) -> Tuple[str, str, str]:
        company = (lead.get("company_name") or "Company").strip()
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
            reg_display = reg_info["region_name_en"]
            pain_text = reg_info["pain_en"]

            subject = f"Soluție completă împotriva secetei: Reducerea apei cu 50% și protecția culturilor pentru {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Vă contactăm în legătură cu exploatația agricolă a companiei <strong>{company}</strong> ({crops}). În contextul secetelor severe, al scăderii pânzei freatice și al facturilor uriașe de energie pentru irigații, culturile se confruntă cu un stres termic major.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Vă prezentăm tehnologia dovedită <strong>TERAWET-ORIGINAL®</strong> – polimer superabsorbant reticulat pe bază de <strong>potasiu</strong> (ecologic, non-toxic, fără sodiu dăunător) cu <strong>25 de ani de experiență în Europa</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Transformările Pozitive pentru Ferma Dumneavoastră:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Reducerea consumului de apă cu peste 50%–60%:</strong> Granulele rețin de 400 de ori greutatea lor în apă la nivelul rădăcinii (15–40 cm).</li>
    <li><strong>⚡ Economie de 50% la energia pentru pompare:</strong> Mai puține ore de funcționare a pompelor și prelungirea duratei de viață a utilajelor.</li>
    <li><strong>🧪 Peste 30%–40% economie la îngrășăminte:</strong> Substanțele nutritive nu mai sunt levigate în adâncime.</li>
    <li><strong>🍇 Eliminarea stresului termic & recolte mai mari:</strong> Fără avortarea florilor, calibru uniform și indice Brix optim.</li>
    <li><strong>🌱 Rata de prindere de 100% la transplantare:</strong> Cu pasta de rădăcină T100.</li>
    <li><strong>⏳ Durată activă de 7 până la 10 ANI în sol:</strong> Amortizare completă încă din primul an de utilizare.</li>
  </ul>
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Disponibil în saci profesionali de <strong>25 kg (360 €)</strong> și pachete de test de <strong>1 kg</strong>. Puteți comanda online direct pe:
</p>

<p style="margin: 24px 0 28px 0;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block;">👉 Comandați online pe {site}</a>
</p>"""

            body_plain = f"""{contact_greeting},
TERAWET-ORIGINAL® reduce necesarul de apă de irigare cu 50%-60% timp de 7-10 ani:
- Economie de 50% la pomparea apei;
- 30%-40% economie la îngrășăminte N-P-K;
- 100% rată de prindere la plantare cu gelul T100.
Saci de 25 kg (360 €) și 1 kg.
Comenzi online: {site}"""

        # -------------------------------------------------------------
        # 4. SPANISH COPYWRITER TEMPLATE
        # -------------------------------------------------------------
        elif lang == "es":
            contact_greeting = f"Estimado equipo de {company}" if not contact or contact in ["Team", "Admin"] else f"Estimado/a {contact}"
            reg_display = reg_info["region_name_en"]

            subject = f"50% de ahorro en agua de riego y blindaje frente a la sequía para {company}"

            body_html = f"""<p style="font-size: 15px; color: #1e293b; margin-bottom: 16px;">{contact_greeting},</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Nos ponemos en contacto respecto a la explotación de <strong>{company}</strong> ({crops}). Ante las crecientes restricciones hídricas, olas de calor extremo y el elevado coste energético del bombeo, la gestión eficiente del agua es el factor decisivo para la rentabilidad de su cultivo.
</p>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
<strong>TERAWET-ORIGINAL®</strong> es un polímero superabsorbente reticulado a base de <strong>potasio</strong> (100% ecológico, sin sodio) con <strong>25 años de trayectoria europea</strong> (VANKO 97 EOOD).
</p>

<div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #007001; border-radius: 8px; padding: 18px 20px; margin: 22px 0;">
  <h3 style="color: #007001; margin: 0 0 12px 0; font-size: 16px;">🌱 Transformaciones Positivas para su Explotación:</h3>
  <ul style="margin: 0; padding-left: 20px; color: #1e293b; line-height: 1.7; font-size: 14.5px;">
    <li><strong>💧 Ahorro superior al 50%–60% en agua de riego:</strong> Retiene 400 veces su peso en agua en la zona radicular (15–40 cm).</li>
    <li><strong>⚡ Reducción del 50% en facturas eléctricas de bombeo:</strong> Menos horas de pozo y menor desgaste de bombas.</li>
    <li><strong>🧪 Ahorro de más del 30% en fertilizantes solubles:</strong> Evita la lixiviación hacia aguas profundas.</li>
    <li><strong>🍇 Eliminación del estrés térmico y caída de fruto:</strong> Mayor calibre comercial y maduración homogénea.</li>
    <li><strong>🌱 100% de éxito en trasplante y nuevas plantaciones:</strong> Con la pasta radicular T100.</li>
    <li><strong>⏳ Vida útil activa de 7 a 10 AÑOS en suelo:</strong> Una sola aplicación rentable desde la 1ª campaña.</li>
  </ul>
</div>

<p style="font-size: 15px; line-height: 1.6; color: #334155;">
Disponible en sacos profesionales de <strong>25 kg (360 €)</strong> y paquetes de <strong>1 kg</strong>. Pedidos directos online:
</p>

<p style="margin: 24px 0 28px 0;">
  <a href="{site}" target="_blank" style="background-color: #007001; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 15px; display: inline-block;">👉 Pedir online en {site}</a>
</p>"""

            body_plain = f"""{contact_greeting},
TERAWET-ORIGINAL® ahorra más del 50% de agua de riego durante 7 a 10 años.
Sacos de 25 kg (360 €) y 1 kg.
Pedidos online: {site}"""

        # -------------------------------------------------------------
        # 5. ENGLISH / INTERNATIONAL FALLBACK
        # -------------------------------------------------------------
        else:
            contact_greeting = f"Dear {company} Team" if not contact or contact in ["Team", "Admin"] else f"Dear {contact}"
            reg_display = reg_info["region_name_en"]
            pain_text = reg_info["pain_en"]
            trans_local = reg_info["transform_local_en"]
            dosage_text = crop_info["dosage_en"]

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

        return subject, body_html, body_plain
