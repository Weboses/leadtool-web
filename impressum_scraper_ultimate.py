"""
Impressum Scraper - ULTIMATE VERSION
Maximale Erfolgsquote beim Extrahieren von Geschäftsführer-Daten

Features:
- 50+ Keywords für Impressum-Erkennung (DE/EN/Multilingual)
- Strukturierte Daten-Extraktion (JSON-LD, Schema.org, Microdata)
- Footer-First-Strategie (Impressum-Links sind zu 95% im Footer)
- Intelligente Name-Extraktion mit 30+ Patterns
- Multi-Page-Scan (Homepage, Kontakt, About, Footer-Links)
- Robuste Fallbacks auf allen Ebenen
"""
import requests
from bs4 import BeautifulSoup, Comment
import re
import time
import logging
import json
import os
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException as SeleniumTimeout
from webdriver_manager.chrome import ChromeDriverManager
import html as html_module

# Versuche dotenv zu laden (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ContactResult:
    """Strukturiertes Ergebnis der Kontaktdaten-Extraktion"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    position: Optional[str] = None  # z.B. "Geschäftsführer"
    impressum_url: Optional[str] = None
    found_name: bool = False
    found_email: bool = False
    extraction_method: Optional[str] = None  # Wie wurde der Name gefunden
    confidence: float = 0.0  # 0.0 - 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': self.full_name,
            'email': self.email,
            'phone': self.phone,
            'company_name': self.company_name,
            'position': self.position,
            'impressum_url': self.impressum_url,
            'found_name': self.found_name,
            'found_email': self.found_email,
            'extraction_method': self.extraction_method,
            'confidence': self.confidence
        }


class ImpressumScraperUltimate:
    """
    ULTIMATIVER Impressum Scraper
    Ziel: 100% Erfolgsquote beim Finden von Geschäftsführer-Namen
    """
    
    # ===== KONSTANTEN =====
    
    # Erweiterte Keywords für Impressum-Suche (50+)
    IMPRESSUM_KEYWORDS = [
        # Deutsch
        'impressum', 'impressúm', 'impessum',  # inkl. Tippfehler
        'anbieterkennzeichnung', 'anbieterkennung',
        'rechtliche hinweise', 'rechtliches',
        'pflichtangaben', 'gesetzliche angaben',
        'firmendaten', 'unternehmensdaten',
        'angaben gemäß § 5 tmg', 'angaben gemaess § 5 tmg',
        'angaben gemäß telemediengesetz',
        'betreiberangaben', 'seitenbetreiber',
        'verantwortlich für den inhalt',
        'verantwortlich i.s.d. § 55',
        
        # Englisch
        'imprint', 'legal notice', 'legal-notice', 'legalnotice',
        'legal information', 'legal info', 'legal',
        'site notice', 'site-notice', 'sitenotice',
        'disclaimer', 'terms', 'terms of use',
        'about us', 'about-us', 'aboutus',
        'company info', 'company-info', 'companyinfo',
        'corporate information', 'corporate info',
        'publisher information', 'publisher',
        'who we are', 'who-we-are',
        
        # Österreich/Schweiz
        'offenlegung', 'offenlegungspflicht',
        'firmenangaben', 'handelsregister',
        
        # Kombinationen
        'kontakt impressum', 'impressum kontakt',
        'impressum & datenschutz', 'impressum-datenschutz',
        'legal & privacy', 'imprint privacy',
    ]
    
    # Keywords für Footer-Bereiche
    FOOTER_SELECTORS = [
        'footer', '#footer', '.footer',
        '#site-footer', '.site-footer',
        '#page-footer', '.page-footer',
        '#main-footer', '.main-footer',
        '#bottom', '.bottom',
        '#colophon', '.colophon',
        '[role="contentinfo"]',
        '.footer-widgets', '#footer-widgets',
        '.footer-container', '#footer-container',
        '.footer-content', '#footer-content',
        '.footer-bottom', '#footer-bottom',
        '.site-info', '#site-info',
    ]
    
    # Positions-Keywords für Geschäftsführer (priorisiert)
    POSITION_KEYWORDS = [
        # Höchste Priorität - Geschäftsführung
        ('geschäftsführer', 1.0),
        ('geschäftsführerin', 1.0),
        ('geschäftsführung', 1.0),
        ('geschäftsleitung', 1.0),
        ('gf:', 1.0),
        
        # Hohe Priorität - Inhaber
        ('inhaber', 0.95),
        ('inhaberin', 0.95),
        ('einzelunternehmer', 0.95),
        ('einzelunternehmerin', 0.95),
        
        # Hohe Priorität - Vertreten durch
        ('vertreten durch', 0.9),
        ('gesetzlich vertreten', 0.9),
        ('vertretungsberechtigt', 0.9),
        ('vertretungsberechtigter', 0.9),
        
        # Management
        ('ceo', 0.85),
        ('chief executive', 0.85),
        ('managing director', 0.85),
        ('vorstand', 0.85),
        ('vorstandsvorsitzender', 0.85),
        ('vorstandsvorsitzende', 0.85),
        
        # Österreich/Schweiz
        ('prokurist', 0.8),
        ('prokuristin', 0.8),
        ('gesellschafter', 0.75),
        ('gesellschafterin', 0.75),
        
        # Verantwortlich
        ('verantwortlich', 0.7),
        ('v.i.s.d.p.', 0.7),
        ('v.i.s.d.p', 0.7),
        ('inhaltlich verantwortlich', 0.7),
        ('redaktionell verantwortlich', 0.65),
        ('technisch verantwortlich', 0.65),

        # Diensteanbieter
        ('diensteanbieter', 0.9),
        ('diensteanbieterin', 0.9),

        # Eigentümer
        ('eigentümer', 0.6),
        ('eigentümerin', 0.6),
        ('owner', 0.6),
        ('founder', 0.55),
        ('gründer', 0.55),
        ('gründerin', 0.55),

        # Vorsitzender (Vereine)
        ('1. vorsitzender', 0.7),
        ('1. vorsitzende', 0.7),
        ('vorsitzender', 0.65),
        ('vorsitzende', 0.65),
    ]
    
    # Häufige deutsche Vornamen (umfassend - für Validierung)
    COMMON_FIRST_NAMES = {
        # Männlich - häufig
        'alexander', 'andreas', 'benjamin', 'christian', 'daniel', 'david',
        'dennis', 'dominik', 'eric', 'erik', 'fabian', 'felix', 'florian',
        'frank', 'hans', 'jan', 'jens', 'johannes', 'jonas', 'julian',
        'kai', 'kevin', 'klaus', 'lars', 'lukas', 'marcel', 'marco',
        'marcus', 'mario', 'markus', 'martin', 'matthias', 'max',
        'maximilian', 'michael', 'niklas', 'nils', 'oliver', 'patrick',
        'paul', 'peter', 'philipp', 'ralf', 'rene', 'robin', 'sascha',
        'sebastian', 'simon', 'stefan', 'steffen', 'stephan', 'thomas',
        'tim', 'tobias', 'tom', 'uwe', 'wolfgang',
        # Männlich - erweitert
        'achim', 'adalbert', 'adam', 'adrian', 'albert', 'albrecht', 'alfons',
        'alfred', 'ali', 'amin', 'andre', 'anton', 'armin', 'arnd', 'arndt',
        'arne', 'arno', 'arnold', 'arthur', 'august', 'axel',
        'bastian', 'benedikt', 'benno', 'bernd', 'bernhard', 'bert', 'berthold',
        'björn', 'boris', 'bruno', 'burkhard', 'carl', 'carsten', 'christof',
        'christoff', 'christoph', 'christopher', 'claus', 'clemens', 'conrad', 'cornelius',
        'detlef', 'detlev', 'dieter', 'dietmar', 'dietrich', 'dirk',
        'eckhard', 'edgar', 'edmund', 'eduard', 'egon', 'eike', 'ekkehard',
        'elmar', 'emanuele', 'emil', 'enrico', 'erhard', 'ernest', 'ernst',
        'erwin', 'eugen',
        'ferdinand', 'franz', 'frederik', 'friedhelm', 'friedrich', 'fritz',
        'georg', 'gerald', 'gerd', 'gerhard', 'gert', 'gottfried', 'gregor',
        'guido', 'gunnar', 'gunter', 'günter', 'günther', 'gustav', 'gernot',
        'hagen', 'harald', 'hartmut', 'hartwig', 'heiko', 'heiner', 'heinrich',
        'heinz', 'helmut', 'hendrik', 'henning', 'henry', 'herbert', 'hermann',
        'hilmar', 'holger', 'horst', 'hubert', 'hugo', 'ibrahim',
        'ignaz', 'ingo', 'ingolf', 'ivo',
        'jacob', 'jakob', 'joachim', 'jochen', 'jörg', 'jörn', 'josef',
        'joseph', 'jürgen', 'julius', 'justus',
        'karlheinz', 'karl', 'karsten', 'kaspar', 'konrad', 'konstantin',
        'kurt', 'leo', 'leon', 'leonard', 'leopold', 'lorenz', 'lothar',
        'louis', 'ludwig', 'luca', 'ludger', 'lutz', 'manfred',
        'marc', 'marcello', 'mark', 'marius', 'marko', 'marvin', 'mathias',
        'mato', 'maurizio', 'maxim', 'mehmet', 'meinhard', 'mirko', 'miroslav',
        'mohammad', 'moritz', 'muhammed', 'mustafa',
        'nico', 'nicolai', 'nikolai', 'nikolaus', 'norbert',
        'olaf', 'oskar', 'oswald', 'otmar', 'otto', 'pascal',
        'rafael', 'raimund', 'rainer', 'ralph', 'raoul', 'raphael', 'rasso',
        'reiner', 'reinhard', 'reinhold', 'richard', 'rigo', 'robert', 'roger',
        'roland', 'rolf', 'roman', 'ronald', 'rüdiger', 'rudolf', 'rupert',
        'samuel', 'sandro', 'siegfried', 'siegmund', 'sönke', 'sven',
        'theodor', 'thilo', 'thorsten', 'tilman', 'torben', 'torsten', 'tristan',
        'udo', 'ulf', 'ulrich', 'utz',
        'valentin', 'viktor', 'vincent', 'vinzenz', 'volker',
        'waldemar', 'walter', 'werner', 'wilfried', 'wilhelm', 'willi',
        'winfried', 'wolfram',
        'yannick', 'yusuf',
        # Weiblich - häufig
        'alexandra', 'andrea', 'angelika', 'anja', 'anna', 'anne',
        'annette', 'antje', 'barbara', 'bianca', 'brigitte', 'carina',
        'carmen', 'carolin', 'caroline', 'christina', 'christiane',
        'claudia', 'daniela', 'diana', 'doris', 'elena', 'elke', 'eva',
        'franziska', 'gabriele', 'heike', 'helena', 'ines', 'iris',
        'jana', 'jasmin', 'jennifer', 'jessica', 'johanna', 'julia',
        'juliane', 'karin', 'katharina', 'kathrin', 'katja', 'katrin',
        'kerstin', 'kristina', 'lara', 'laura', 'lea', 'lena', 'linda',
        'lisa', 'manuela', 'maria', 'marie', 'marina', 'marion', 'martina',
        'melanie', 'michaela', 'monika', 'nadine', 'natalie', 'nicole',
        'nina', 'petra', 'sabine', 'sabrina', 'sandra', 'sara', 'sarah',
        'silke', 'simone', 'sophia', 'stefanie', 'stephanie', 'susanne',
        'tanja', 'ulrike', 'ursula', 'vanessa', 'vera', 'yvonne',
        # Weiblich - erweitert
        'adelheid', 'agnes', 'agathe', 'aida', 'alice', 'alina', 'amelie',
        'anette', 'angelina', 'anita', 'anke', 'annegret', 'anneliese',
        'annemarie', 'astrid', 'ayse',
        'beate', 'beatrice', 'beatrix', 'bella', 'berta', 'bettina', 'birgit',
        'britta', 'charlotte', 'christa', 'christel', 'christine', 'clara',
        'conny', 'constanze', 'cordula', 'corinna', 'cornelia', 'dagmar',
        'denise', 'dora', 'dorothea', 'dorothee', 'dorrit',
        'edith', 'elfriede', 'elisabeth', 'ella', 'eleonore', 'emilia', 'emily',
        'emma', 'erika', 'erna', 'esther', 'eugenia',
        'fatima', 'felicitas', 'frieda', 'friederike',
        'gabi', 'gerda', 'gerlinde', 'gertrud', 'gisela', 'gudrun', 'gunda',
        'hanna', 'hannah', 'harriet', 'hedwig', 'heidi', 'helga', 'hella',
        'helene', 'henriette', 'herta', 'hilde', 'hildegard',
        'ida', 'ilka', 'ilona', 'ilse', 'imke', 'ina', 'inga', 'ingeborg',
        'ingrid', 'irene', 'isabell', 'isabelle',
        'jaqueline', 'judith', 'jutta',
        'karen', 'karla', 'karoline', 'kirsten', 'klara',
        'larissa', 'leonie', 'liane', 'lidia', 'liesel', 'lilli', 'lina',
        'lotte', 'lucia', 'luise', 'lydia',
        'madeleine', 'magdalena', 'margit', 'margret', 'margot', 'marianne',
        'marita', 'marlene', 'marlies', 'martha', 'mathilde', 'mechthild',
        'meike', 'melissa', 'mia', 'mira', 'miriam', 'mirjam',
        'nadia', 'natascha', 'nele', 'nora',
        'olivia',
        'patricia', 'paula', 'pauline', 'pia',
        'ramona', 'rebecca', 'regina', 'regine', 'renate', 'rita', 'rosa',
        'rosemarie', 'roswitha', 'ruth',
        'selina', 'sibylle', 'sigrid', 'sonja', 'svenja', 'sylvia',
        'tamara', 'tatjana', 'theresa', 'theresia', 'traute', 'trude',
        'ute', 'veronica', 'veronika', 'viola', 'vivien',
        'waltraud', 'wanda', 'wiebke', 'wilhelmine',
        # Internationale Vornamen (häufig in DE)
        'ahmed', 'amir', 'carlo', 'cesare', 'dario', 'diego', 'dimitri',
        'emre', 'enver', 'epiphanie', 'fatih', 'giovanni', 'giuseppe',
        'goran', 'hakan', 'hassan', 'ivan', 'jordie', 'kemal', 'khalid',
        'luca', 'luigi', 'mahmoud', 'marek', 'maroof', 'matteo', 'milan',
        'mohammed', 'nabil', 'omar', 'osman', 'paolo', 'pierre', 'reza',
        'roberto', 'salvatore', 'samir', 'sergej', 'stefano', 'vincenzo',
        'vladislav', 'yasin', 'zoran',
        # Ergänzungen aus CSV-Analyse
        'nadia', 'janine', 'evelyn', 'marleen', 'madlen', 'rufus', 'fabio',
        'yevgeniy', 'reinfried', 'diethelm', 'nico',
        # Ergänzungen aus Impressum-Analyse (fehlende internationale Namen)
        'fikriye', 'samia', 'jordie', 'torben', 'claus', 'niklas',
        'sarah', 'sandra', 'birgit', 'henning', 'wilfried', 'ludgerus',
    }
    
    # Wörter die KEINE Namen sind (Blacklist)
    NAME_BLACKLIST = {
        # Firmenzusätze
        'gmbh', 'gbr', 'ag', 'kg', 'ohg', 'ug', 'mbh', 'co', 'inc', 'ltd',
        'limited', 'corporation', 'corp', 'llc', 'plc', 'se', 'ev', 'eg',
        
        # Rechtsformen ausgeschrieben
        'gesellschaft', 'haftungsbeschränkt', 'haftungsbeschraenkt',
        'aktiengesellschaft', 'kommanditgesellschaft',
        
        # Allgemeine Wörter
        'impressum', 'kontakt', 'email', 'mail', 'telefon', 'tel', 'fax',
        'adresse', 'address', 'straße', 'strasse', 'platz', 'weg', 'allee',
        'herr', 'frau', 'dr', 'prof', 'dipl', 'ing', 'mag', 'rer', 'nat',
        'geschäftsführer', 'geschäftsführerin', 'inhaber', 'inhaberin',
        'vertreten', 'durch', 'verantwortlich', 'für', 'den', 'inhalt',
        'handelsregister', 'registergericht', 'amtsgericht', 'hrb', 'hra',
        'ustid', 'ust', 'steuernummer', 'steuer', 'nummer',
        'registernummer', 'register', 'eintragung',
        'webdesign', 'website', 'webseite', 'homepage', 'internet',
        'copyright', 'alle', 'rechte', 'vorbehalten',
        'datenschutz', 'privacy', 'policy', 'agb', 'terms',
        
        # Städte (die oft fälschlich erkannt werden)
        'berlin', 'münchen', 'hamburg', 'köln', 'frankfurt', 'stuttgart',
        'düsseldorf', 'dortmund', 'essen', 'bremen', 'leipzig', 'dresden',
        'hannover', 'nürnberg', 'duisburg', 'bochum', 'wuppertal',
        
        # Andere
        'germany', 'deutschland', 'austria', 'österreich', 'schweiz',
        'swiss', 'europe', 'europa',

        # Artikel und häufige deutsche Wörter (Falsch-Positiv-Vermeidung)
        'die', 'der', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer',
        'firma', 'unternehmen', 'betrieb', 'verein', 'stiftung', 'institut',
        'agentur', 'beratung', 'consulting', 'service', 'services', 'solutions',
        'akademie', 'academy', 'group', 'gruppe', 'holding', 'management',
        'marketing', 'media', 'digital', 'software', 'technik', 'technology',
        'nach', 'gemäß', 'sowie', 'oder', 'und', 'nicht', 'sind', 'wird',

        # Gerichte und rechtliche Begriffe
        'amtsgericht', 'landgericht', 'oberlandesgericht', 'registergericht',

        # Berufsbezeichnungen (keine Vornamen!)
        'rechtsanwalt', 'rechtsanwältin', 'steuerberater', 'steuerberaterin',
        'wirtschaftsprüfer', 'wirtschaftsprüferin', 'notar', 'notarin',
        'patentanwalt', 'patentanwältin',

        # Deutsche Substantive/Wörter die fälschlich als Namen erkannt werden
        'termine', 'termin', 'angebot', 'angebote', 'leistungen', 'leistung',
        'unser', 'unsere', 'unserem', 'unseren', 'unserer',
        'nordhessen', 'südhessen', 'mittelhessen', 'oberhessen', 'niedersachsen',
        'nordrhein', 'westfalen', 'ostwestfalen', 'oberbayern', 'niederbayern',
        'oberpfalz', 'oberfranken', 'unterfranken', 'mittelfranken', 'schwaben',
        'schleswig', 'holstein', 'mecklenburg', 'vorpommern', 'thüringen',
        'sachsen', 'anhalt', 'brandenburg', 'saarland', 'rheinland', 'pfalz',
        'startseite', 'willkommen', 'herzlich', 'über', 'ueber',
        'kontaktieren', 'informationen', 'information', 'news', 'aktuelles',
        'karriere', 'partner', 'produkte', 'produkt', 'projekt', 'projekte',
        'referenzen', 'referenz', 'portfolio', 'galerie', 'blog', 'presse',
        'kosten', 'preise', 'preis', 'qualität', 'qualitaet',
        'erfahrung', 'erfahrungen', 'bewertung', 'bewertungen',
        'standort', 'standorte', 'filiale', 'filialen', 'zentrale',
        'schulung', 'schulungen', 'seminar', 'seminare', 'workshop', 'workshops',
        'download', 'downloads', 'dokumente', 'dokument', 'formulare',
        'mitarbeiter', 'team', 'personal', 'kollegen',
        'kunden', 'kunde', 'mandanten', 'mandant', 'patienten', 'patient',
        'öffnungszeiten', 'sprechzeiten', 'bürozeiten',
        'anfahrt', 'wegbeschreibung', 'lageplan',
        'datenschutzerklärung', 'nutzungsbedingungen', 'haftungsausschluss',
        'sitemap', 'suche', 'suchen', 'login', 'anmelden', 'registrieren',

        # Platzhaltername
        'mustermann', 'musterfrau', 'musterfirma', 'muster',
    }

    def __init__(self, api_config_file: str = "api_config.json"):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Session für Connection Pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Cache
        self.cache_file = "impressum_cache_v2.json"
        self.cache = self._load_cache()
        
        # ChromeDriver
        self._init_chrome_driver()
        
        # API Config
        self._load_api_config(api_config_file)
        
        # Kompilierte Regex-Patterns (Performance)
        self._compile_patterns()

    def _init_chrome_driver(self):
        """Initialisiert ChromeDriver mit Fallback"""
        self.chrome_driver_path = None
        try:
            self.chrome_driver_path = ChromeDriverManager().install()
            logger.info("✅ ChromeDriver initialisiert")
        except Exception as e:
            logger.warning(f"⚠️ ChromeDriver nicht verfügbar: {e}")

    def _load_cache(self) -> Dict:
        """Lädt Cache aus Datei"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Cache laden fehlgeschlagen: {e}")
        return {}

    def _save_cache(self):
        """Speichert Cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Cache speichern fehlgeschlagen: {e}")

    def _load_api_config(self, config_file: str):
        """Lädt API-Konfiguration"""
        self.api_enabled = False
        self.api_key = ''
        self.api_base_url = ''
        self.api_model = 'deepseek-chat'
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            active_api = config.get('active_api', 'deepseek')
            api_settings = config.get('apis', {}).get(active_api, {})
            
            self.api_enabled = api_settings.get('enabled', False)
            self.api_base_url = api_settings.get('base_url', '')
            self.api_model = api_settings.get('default_model', 'deepseek-chat')
            
            # API Key aus Umgebungsvariable oder Config
            env_var = api_settings.get('api_key_env', '')
            if env_var:
                self.api_key = os.environ.get(env_var, '')
            if not self.api_key:
                self.api_key = api_settings.get('api_key', '')
            
            if self.api_enabled and self.api_key:
                logger.info(f"✅ API konfiguriert: {active_api}")
            else:
                logger.warning("⚠️ API nicht konfiguriert - nur Regex-Fallback")
                
        except Exception as e:
            logger.warning(f"API-Config laden fehlgeschlagen: {e}")

    def _compile_patterns(self):
        """Kompiliert Regex-Patterns für Performance"""
        
        # Name-Extraktions-Patterns (priorisiert)
        self.name_patterns = []
        
        # Pattern-Gruppen mit Priorität
        # Name-Pattern Bausteine (Vorname Nachname, inkl. Bindestrich-Namen wie Müller-Schmidt)
        _NP = r'[A-ZÄÖÜ][a-zäöüß]+'  # Ein Namensteil (z.B. "Christian")
        _NP_H = r'[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)*'  # Namensteil mit Bindestrich (z.B. "Müller-Schmidt")
        # Middle-Initial: "J." oder "H." (für "Franz J. Doll", "Michael H. Lutter")
        _MI = r'(?:[A-ZÄÖÜ]\.\s+)?'
        # Vorname + opt. Middle-Initial + Nachname (2 Teile), Bindestrich-Namen erlaubt bei BEIDEN
        _FULL = f'({_NP_H}\\s+{_MI}{_NP_H})'
        _FULL_NL = _FULL
        # Vorname + opt. zweiter Vorname + Nachname (2-3 Teile)
        _FULL3 = f'({_NP_H}(?:\\s+{_MI}{_NP_H})?\\s+{_MI}{_NP_H})'

        pattern_groups = [
            # Gruppe 1: Geschäftsführer mit Doppelpunkt/Leerzeichen
            (1.0, [
                rf'Geschäftsführer(?:in)?[:\s]+{_FULL}',
                rf'Geschäftsführung[:\s]+{_FULL}',
                rf'GF[:\s]+{_FULL}',
            ]),

            # Gruppe 2: Inhaber
            (0.95, [
                rf'Inhaber(?:in)?[:\s]+{_FULL}',
                rf'Einzelunternehmer(?:in)?[:\s]+{_FULL}',
                rf'Diensteanbieter(?:in)?[:\s]+{_FULL}',
            ]),

            # Gruppe 3: Vertreten durch
            (0.9, [
                rf'[Vv]ertreten\s+durch[:\s]+{_FULL}',
                rf'[Gg]esetzlich\s+vertreten[:\s]+{_FULL}',
                rf'[Vv]ertretungsberechtigt(?:er)?[:\s]+{_FULL}',
            ]),

            # Gruppe 4: CEO/Vorstand (Englisch/Deutsch)
            (0.85, [
                rf'CEO[:\s]+{_FULL}',
                rf'Chief\s+Executive[:\s]+{_FULL}',
                rf'Managing\s+Director[:\s]+{_FULL}',
                rf'Vorstand(?:svorsitzende(?:r)?)?(?:\s+\w+)?[:\s]+{_FULL}',
            ]),

            # Gruppe 5: Verantwortlich (alle Varianten)
            (0.7, [
                rf'[Vv]erantwortlich(?:\s+(?:für|i\.?S\.?d\.?|gem(?:äß|\.)))?[:\s]+{_FULL}',
                # Verantwortlich ... (beliebiger Text bis Zeilenende) \n Name auf nächster Zeile
                rf'[Vv]erantwortlich[^\n]*\n\s*{_FULL_NL}',
                rf'V\.?i\.?S\.?d\.?P\.?[:\s]+{_FULL}',
                rf'V\.?i\.?S\.?d\.?P\.?[^\n]*\n\s*{_FULL_NL}',
                rf'[Ii]nhaltlich\s+[Vv]erantwortlich[:\s]+{_FULL}',
                rf'[Ii]nhaltlich\s+[Vv]erantwortlich[^\n]*\n\s*{_FULL_NL}',
                # "Redaktionell verantwortlich: Name"
                rf'[Rr]edaktionell\s+[Vv]erantwortlich[:\s]+{_FULL}',
                rf'[Rr]edaktionell\s+[Vv]erantwortlich[^\n]*\n\s*{_FULL_NL}',
                # "Technisch Verantwortlicher: Name"
                rf'[Tt]echnisch\s+[Vv]erantwortlich(?:er)?[:\s]+{_FULL}',
                rf'[Tt]echnisch\s+[Vv]erantwortlich(?:er)?[^\n]*\n\s*{_FULL_NL}',
                # "Verantwortlicher für die Datenverarbeitung ... ist Name"
                rf'[Vv]erantwortlich(?:er)?\s+(?:für|fuer)[^\n]*ist\s+{_FULL}',
            ]),

            # Gruppe 6: Mit Titel (Dr., Prof., etc.)
            (0.8, [
                rf'(?:Dr\.|Prof\.|Dipl\.-\w+\.?)\s+{_FULL}',
            ]),

            # Gruppe 7: Sonderformate
            (0.6, [
                # "Name, Geschäftsführer"
                rf'{_FULL_NL},?\s*(?:Geschäftsführer|Inhaber|CEO)',
                # Schlüsselwort gefolgt von Newline, dann Name auf nächster Zeile
                rf'Geschäftsführer(?:in)?[:\s]*\n\s*{_FULL_NL}',
                rf'Inhaber(?:in)?[:\s]*\n\s*{_FULL_NL}',
                rf'[Vv]ertreten\s+durch[:\s]*\n\s*{_FULL_NL}',
                # "Diensteanbieter\nName"
                rf'Diensteanbieter(?:in)?[:\s]*\n\s*{_FULL_NL}',
                # "Name - Berufsbezeichnung" (z.B. "Marc Willi Kückelhaus - Steuerberater")
                rf'{_FULL3}\s*-\s*(?:Steuerberater|Rechtsanwalt|Inhaber|Geschäftsführer|Berater|Ingenieur|Coach|Dozent)',
                # "Name (1. Vorsitzender)" (z.B. "Henning Funk (1. Vorsitzender)")
                rf'{_FULL_NL}\s*\((?:1\.|2\.|Vorsitzende|Geschäftsführ|Inhaber)',
                # "Herr/Frau Vorname Nachname"
                rf'(?:Herr|Frau)\s+{_FULL}',
            ]),

            # Gruppe 8: Impressum-Einleitungen (§ 5 TMG etc.)
            (0.65, [
                # "Angaben gemäß § 5 TMG:\nVorname Nachname"
                rf'(?:Angaben\s+gem(?:äß|\.)\s+§\s*5\s+TMG|Pflichtangaben)[:\s]*\n\s*{_FULL_NL}',
                # "Angaben gemäß § 5 TMG:\nFirmenname\nVorname Nachname"  (Name 2 Zeilen nach Keyword)
                rf'(?:Angaben\s+gem(?:äß|\.)\s+§\s*5\s+TMG|Pflichtangaben)[^\n]*\n[^\n]*\n\s*{_FULL_NL}',
                # "Verantwortlich" + mehrere Zeilen + Name (max 3 Zeilen dazwischen)
                rf'[Vv]erantwortlich[^\n]*\n[^\n]*\n\s*{_FULL_NL}',
                rf'[Vv]erantwortlich[^\n]*\n[^\n]*\n[^\n]*\n\s*{_FULL_NL}',
                # "§ 5 TMG" direkt gefolgt von Name auf nächster Zeile
                rf'§\s*5\s+TMG[^\n]*\n\s*{_FULL_NL}',
            ]),

            # Gruppe 9: Firmenname gefolgt von Personen-Name (ohne Keyword)
            (0.55, [
                # "... GmbH\nVorname Nachname" (Name direkt nach Firmenbezeichnung)
                rf'(?:GmbH|UG|AG|e\.K\.|OHG|KG|mbH|GbR|AöR|Consulting|Beratung)\s*\n\s*{_FULL_NL}',
            ]),
        ]
        
        for priority, patterns in pattern_groups:
            for pattern in patterns:
                try:
                    self.name_patterns.append((priority, re.compile(pattern, re.MULTILINE)))
                except re.error as e:
                    logger.warning(f"Regex-Fehler: {pattern} - {e}")
        
        # E-Mail Pattern
        self.email_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            re.IGNORECASE
        )
        
        # Telefon Pattern
        self.phone_pattern = re.compile(
            r'(?:\+49|0049|0)\s*[\d\s/\-\(\)]{8,}',
            re.IGNORECASE
        )

    # ===== URL NORMALISIERUNG =====
    
    def normalize_url(self, website: str) -> Optional[str]:
        """Normalisiert und validiert Website-URL"""
        if not website:
            return None
        
        website = website.strip().lower()
        
        # Entferne trailing slashes und Pfade
        website = re.sub(r'/+$', '', website)
        
        # Füge https:// hinzu falls fehlt
        if not website.startswith(('http://', 'https://')):
            website = 'https://' + website
        
        # Validiere URL
        try:
            parsed = urlparse(website)
            if not parsed.netloc:
                return None
            # Rekonstruiere saubere URL
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return None

    # ===== IMPRESSUM URL FINDEN =====
    
    def find_impressum_url(self, base_url: str) -> Optional[str]:
        """
        Findet die Impressum-URL auf einer Website
        
        Strategie (in dieser Reihenfolge):
        1. Cache prüfen
        2. Footer-Links analysieren (höchste Trefferquote)
        3. Alle Links auf der Seite durchsuchen
        4. Bekannte URL-Patterns testen
        5. Sitemap durchsuchen
        6. DeepSeek API als Fallback
        """
        # Cache Check
        cache_key = f"impressum:{base_url}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached:
                logger.info(f"📦 Cache-Treffer: {cached}")
                return cached
        
        try:
            # Lade Homepage
            response = self.session.get(base_url, timeout=8)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Strategie 1: Footer-Links (höchste Trefferquote)
            impressum_url = self._find_in_footer(soup, base_url)
            if impressum_url:
                self._cache_impressum(cache_key, impressum_url)
                return impressum_url
            
            # Strategie 2: Alle Links durchsuchen
            impressum_url = self._find_in_all_links(soup, base_url)
            if impressum_url:
                self._cache_impressum(cache_key, impressum_url)
                return impressum_url
            
            # Strategie 3: Bekannte URL-Patterns testen
            impressum_url = self._try_common_paths(base_url)
            if impressum_url:
                self._cache_impressum(cache_key, impressum_url)
                return impressum_url
            
            # Strategie 4+5 (Sitemap/API) uebersprungen - zu langsam fuer Bulk

        except Exception as e:
            logger.error(f"Fehler beim Finden der Impressum-URL: {e}")
        
        # Nichts gefunden
        self._cache_impressum(cache_key, "")
        return None

    def _cache_impressum(self, key: str, value: str):
        """Cached Impressum-URL"""
        self.cache[key] = value
        self._save_cache()

    def _find_in_footer(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Sucht Impressum-Link im Footer (höchste Trefferquote)"""
        logger.info("🔍 Suche im Footer...")
        
        # Finde Footer-Elemente
        footer_elements = []
        for selector in self.FOOTER_SELECTORS:
            try:
                if selector.startswith(('#', '.', '[')):
                    elements = soup.select(selector)
                else:
                    elements = soup.find_all(selector)
                footer_elements.extend(elements)
            except Exception:
                continue
        
        # Falls kein Footer gefunden, nimm die letzten 30% der Seite
        if not footer_elements:
            all_links = soup.find_all('a', href=True)
            if len(all_links) > 10:
                footer_elements = all_links[int(len(all_links) * 0.7):]
        
        # Durchsuche Footer-Links
        for element in footer_elements:
            links = element.find_all('a', href=True) if hasattr(element, 'find_all') else [element]
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True).lower()
                
                # Prüfe auf Impressum-Keywords
                for keyword in self.IMPRESSUM_KEYWORDS:
                    if keyword in text or keyword in href.lower():
                        impressum_url = self._resolve_url(href, base_url)
                        if impressum_url:
                            logger.info(f"✅ Impressum im Footer gefunden: {impressum_url}")
                            return impressum_url
        
        return None

    def _find_in_all_links(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Durchsucht alle Links auf der Seite"""
        logger.info("🔍 Durchsuche alle Links...")
        
        all_links = soup.find_all('a', href=True)
        
        # Erste Runde: Exakte Matches
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            
            # Exakte Keyword-Matches
            for keyword in ['impressum', 'imprint', 'legal notice', 'legal-notice']:
                if keyword == text or href.lower().endswith(f'/{keyword}') or href.lower().endswith(f'/{keyword}/'):
                    impressum_url = self._resolve_url(href, base_url)
                    if impressum_url:
                        logger.info(f"✅ Impressum gefunden (exakt): {impressum_url}")
                        return impressum_url
        
        # Zweite Runde: Partielle Matches
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            
            for keyword in self.IMPRESSUM_KEYWORDS[:20]:  # Top-20 Keywords
                if keyword in text or keyword in href.lower():
                    # Ausschluss: Datenschutz-Links ohne Impressum
                    if 'datenschutz' in text and 'impressum' not in text:
                        continue
                    if 'privacy' in text and 'imprint' not in text:
                        continue
                    
                    impressum_url = self._resolve_url(href, base_url)
                    if impressum_url:
                        logger.info(f"✅ Impressum gefunden (partiell): {impressum_url}")
                        return impressum_url
        
        return None

    def _try_common_paths(self, base_url: str) -> Optional[str]:
        """Testet die haeufigsten Impressum-URLs (schnell, nur 4 Pfade)"""
        common_paths = ['/impressum', '/imprint', '/legal', '/legal-notice']

        for path in common_paths:
            test_url = urljoin(base_url, path)
            try:
                response = self.session.get(test_url, timeout=4)
                if response.status_code == 200:
                    text = response.text.lower()
                    if any(kw in text for kw in ['impressum', 'imprint', 'geschäftsführer', 'inhaber', 'verantwortlich']):
                        return test_url
            except Exception:
                continue

        return None

    def _find_in_sitemap(self, base_url: str) -> Optional[str]:
        """Durchsucht Sitemap nach Impressum"""
        logger.info("🗺️ Durchsuche Sitemap...")
        
        sitemap_urls = [
            urljoin(base_url, '/sitemap.xml'),
            urljoin(base_url, '/sitemap_index.xml'),
            urljoin(base_url, '/sitemap'),
            urljoin(base_url, '/sitemap.xml.gz'),
        ]
        
        for sitemap_url in sitemap_urls:
            try:
                response = self.session.get(sitemap_url, timeout=10)
                if response.status_code == 200:
                    # Parse XML
                    soup = BeautifulSoup(response.text, 'xml')
                    
                    for loc in soup.find_all('loc'):
                        url = loc.text.strip()
                        url_lower = url.lower()
                        
                        for keyword in ['impressum', 'imprint', 'legal-notice', 'legal']:
                            if keyword in url_lower:
                                logger.info(f"✅ Impressum in Sitemap: {url}")
                                return url
            except Exception:
                continue
        
        return None

    def _api_find_impressum(self, html: str, base_url: str) -> Optional[str]:
        """Verwendet DeepSeek API um Impressum-Link zu finden"""
        if not self.api_enabled:
            return None
        
        logger.info("🤖 Verwende DeepSeek API für Impressum-Suche...")
        
        try:
            # Extrahiere nur Links aus HTML (reduziert Token-Verbrauch)
            soup = BeautifulSoup(html, 'html.parser')
            links_info = []
            
            for link in soup.find_all('a', href=True)[:100]:  # Max 100 Links
                href = link.get('href', '')
                text = link.get_text(strip=True)[:50]
                if href and text:
                    links_info.append(f"{text}: {href}")
            
            links_text = "\n".join(links_info[:50])
            
            prompt = (
                "Analysiere diese Links und finde die URL zum Impressum/Imprint/Legal Notice.\n"
                "Antworte NUR mit der gefundenen URL (relativ oder absolut).\n"
                "Falls nicht gefunden: antworte 'NICHT_GEFUNDEN'\n\n"
                f"Base-URL: {base_url}\n\n"
                f"Links:\n{links_text}"
            )
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.api_model,
                'messages': [
                    {'role': 'system', 'content': 'Du bist ein Web-Scraping-Experte. Antworte präzise und kurz.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 100,
                'temperature': 0.1
            }
            
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()['choices'][0]['message']['content'].strip()
            
            if result.upper() == 'NICHT_GEFUNDEN' or not result:
                return None
            
            # Resolve URL
            impressum_url = self._resolve_url(result, base_url)
            if impressum_url:
                logger.info(f"🤖 API gefunden: {impressum_url}")
                return impressum_url
                
        except Exception as e:
            logger.error(f"DeepSeek API Fehler: {e}")
        
        return None

    def _resolve_url(self, href: str, base_url: str) -> Optional[str]:
        """Löst relative URLs auf und validiert"""
        if not href:
            return None
        
        # Entferne Whitespace
        href = href.strip()
        
        # Ignoriere JavaScript/Anchors
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            return None
        
        # Absolute URL
        if href.startswith(('http://', 'https://')):
            return href
        
        # Relative URL
        return urljoin(base_url, href)

    # ===== HTML LADEN =====
    
    def scrape_html(self, url: str, use_selenium: bool = False) -> str:
        """Laedt HTML von URL - schnell, nur requests"""

        try:
            response = self.session.get(url, timeout=8)
            response.raise_for_status()
            # Fix Encoding: requests rät manchmal Latin-1 statt UTF-8
            if response.encoding and response.encoding.lower() in ('iso-8859-1', 'latin-1', 'latin1'):
                response.encoding = response.apparent_encoding or 'utf-8'
            html = response.text

            # Akzeptiere auch kuerzeren Content (Impressum-Seiten sind oft kurz)
            if len(html) >= 500:
                return html

        except Exception as e:
            logger.debug(f"Request fehlgeschlagen: {e}")

        return ""

    def _has_meaningful_content(self, html: str) -> bool:
        """Prüft ob HTML sinnvollen Content hat (nicht nur JS-Loader)"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Entferne Scripts/Styles
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        
        text = soup.get_text(strip=True)
        
        # Mindestens 200 Zeichen Text
        return len(text) >= 200

    def _scrape_with_selenium(self, url: str) -> str:
        """Scraped mit Selenium für JS-heavy Seiten"""
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument(f"user-agent={self.headers['User-Agent']}")
        
        service = Service(self.chrome_driver_path)
        driver = None
        
        try:
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(25)
            driver.get(url)
            
            # Warte auf JS-Rendering
            time.sleep(2.5)
            
            # Scroll um lazy-loaded Content zu triggern
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(0.5)
            
            return driver.page_source
            
        except SeleniumTimeout:
            logger.warning(f"Selenium-Timeout bei {url}")
        except WebDriverException as e:
            logger.error(f"Selenium-Fehler: {e}")
        except Exception as e:
            logger.error(f"Unerwarteter Selenium-Fehler: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        
        return ""

    # ===== TEXT EXTRAKTION =====
    
    def extract_clean_text(self, html: str) -> str:
        """Extrahiert bereinigten Text aus HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Entferne unerwünschte Elemente
            for tag in soup(['script', 'style', 'meta', 'link', 'noscript', 'header', 'nav', 'aside', 'iframe']):
                tag.decompose()

            # Entferne Kommentare
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()

            # Extrahiere Text
            text = soup.get_text(separator='\n', strip=True)

            # Fix doppelt-encodiertes UTF-8 (z.B. "Ã¼" → "ü", "Ã¶" → "ö")
            try:
                text = text.encode('latin-1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass  # Nicht doppelt-encodiert, Text beibehalten

            # Bereinige
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if line and len(line) > 1:
                    lines.append(line)

            return '\n'.join(lines)
            
        except Exception as e:
            logger.warning(f"Text-Extraktion fehlgeschlagen: {e}")
            return ""

    # ===== STRUKTURIERTE DATEN EXTRAKTION =====
    
    def extract_structured_data(self, html: str) -> Dict:
        """Extrahiert strukturierte Daten (JSON-LD, Microdata)"""
        result = {
            'organization': None,
            'person': None,
            'contact_point': None,
        }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # JSON-LD extrahieren
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    
                    # Kann Liste oder einzelnes Objekt sein
                    items = data if isinstance(data, list) else [data]
                    
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        item_type = item.get('@type', '')
                        
                        if item_type in ['Organization', 'LocalBusiness', 'Corporation']:
                            result['organization'] = item
                            
                            # Suche nach Personen
                            if 'founder' in item:
                                result['person'] = item['founder']
                            if 'employee' in item:
                                for emp in (item['employee'] if isinstance(item['employee'], list) else [item['employee']]):
                                    if emp.get('jobTitle', '').lower() in ['geschäftsführer', 'ceo', 'inhaber']:
                                        result['person'] = emp
                            if 'contactPoint' in item:
                                result['contact_point'] = item['contactPoint']
                        
                        elif item_type == 'Person':
                            result['person'] = item
                            
                except json.JSONDecodeError:
                    continue
            
            # Microdata extrahieren (Schema.org)
            for element in soup.find_all(itemtype=re.compile(r'schema\.org/(Person|Organization)', re.I)):
                props = {}
                for prop in element.find_all(itemprop=True):
                    props[prop.get('itemprop')] = prop.get_text(strip=True)
                
                if 'name' in props:
                    if 'Organization' in element.get('itemtype', ''):
                        result['organization'] = props
                    else:
                        result['person'] = props
                        
        except Exception as e:
            logger.debug(f"Strukturierte Daten Extraktion fehlgeschlagen: {e}")
        
        return result

    # ===== NAME EXTRAKTION =====
    
    def extract_name(self, html: str) -> Tuple[Optional[str], Optional[str], float, str]:
        """
        Extrahiert Geschäftsführer-Namen aus HTML
        
        Returns:
            Tuple: (first_name, last_name, confidence, method)
        """
        text = self.extract_clean_text(html)
        
        # Methode 1: Strukturierte Daten
        structured = self.extract_structured_data(html)
        if structured.get('person'):
            person = structured['person']
            # person kann String oder Dict sein - beides behandeln
            if isinstance(person, str):
                name = person
            elif isinstance(person, dict):
                name = person.get('name', '')
            else:
                name = ''
            if name:
                first, last = self._split_name(name)
                if first and last and self._validate_name(first, last):
                    logger.info(f"✅ Name via JSON-LD: {first} {last}")
                    return first, last, 1.0, 'json-ld'
        
        # Methode 2: Regex-Patterns (priorisiert)
        for priority, pattern in self.name_patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Match kann String oder Tuple sein
                name_str = match if isinstance(match, str) else match[0]
                first, last = self._split_name(name_str)
                
                if first and last and self._validate_name(first, last):
                    logger.info(f"✅ Name via Regex (P={priority:.2f}): {first} {last}")
                    return first, last, priority, 'regex'
        
        # Methode 3: DeepSeek API
        if self.api_enabled:
            first, last, conf = self._api_extract_name(text)
            if first and last:
                return first, last, conf, 'api'
        
        # Methode 4: Intelligente Heuristik
        first, last = self._heuristic_extract_name(text)
        if first and last:
            logger.info(f"✅ Name via Heuristik: {first} {last}")
            return first, last, 0.5, 'heuristic'
        
        return None, None, 0.0, 'none'

    def _split_name(self, full_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Teilt vollständigen Namen in Vor- und Nachname"""
        if not full_name:
            return None, None

        # Bereinige
        full_name = full_name.strip()
        full_name = re.sub(r'\s+', ' ', full_name)

        # Entferne Titel und akademische Grade
        titles = ['dr.', 'dr', 'prof.', 'prof', 'dipl.', 'dipl', 'ing.', 'ing',
                  'mag.', 'mag', 'rer.', 'rer', 'nat.', 'nat', 'med.', 'med',
                  'herr', 'frau', 'mr.', 'mr', 'mrs.', 'mrs', 'ms.', 'ms',
                  'dipl.-ing.', 'dipl.-kfm.', 'dipl.-päd.', 'dipl.-betriebsw.',
                  'm.a.', 'b.a.', 'b.sc.', 'm.sc.', 'mba', 'll.m.']

        parts = full_name.split()
        cleaned_parts = []

        for part in parts:
            part_lower = part.lower().rstrip('.,')
            part_lower_raw = part.lower()
            # Entferne Titel (prüfe sowohl mit als auch ohne trailing Punkt)
            if part_lower in titles or part_lower_raw in titles:
                continue
            # Entferne Middle-Initials (z.B. "J.", "H.") - nur einzelner Buchstabe mit Punkt
            if re.match(r'^[A-ZÄÖÜ]\.$', part):
                continue
            # Entferne akademische Grade am Ende (M.A., B.Sc., etc.)
            if re.match(r'^[A-Z]\.[A-Z]\.$', part):
                continue
            cleaned_parts.append(part)

        if len(cleaned_parts) >= 2:
            first_name = cleaned_parts[0]
            last_name = ' '.join(cleaned_parts[1:])
            return first_name, last_name
        elif len(cleaned_parts) == 1:
            return cleaned_parts[0], None

        return None, None

    def _validate_name(self, first_name: str, last_name: str) -> bool:
        """Validiert extrahierten Namen"""
        if not first_name or not last_name:
            return False
        
        first_lower = first_name.lower()
        last_lower = last_name.lower()
        
        # Blacklist-Check (jedes Wort im Namen prüfen)
        all_words = [first_lower] + last_lower.split()
        for word in all_words:
            if word in self.NAME_BLACKLIST:
                return False
        
        # Längen-Check
        if len(first_name) < 2 or len(last_name) < 2:
            return False
        
        if len(first_name) > 30 or len(last_name) > 40:
            return False
        
        # Muss mit Großbuchstaben beginnen
        if not first_name[0].isupper() or not last_name[0].isupper():
            return False
        
        # Keine reinen Zahlen
        if first_name.isdigit() or last_name.isdigit():
            return False
        
        # Keine E-Mail-Adressen
        if '@' in first_name or '@' in last_name:
            return False

        # Deutsche Substantive enden oft auf -ung, -keit, -heit, -tion, -schaft, -nis
        noun_endings = ('ung', 'keit', 'heit', 'tion', 'schaft', 'nis', 'tät',
                        'ment', 'mus', 'ium', 'ieren')
        if first_lower.endswith(noun_endings) or last_lower.endswith(noun_endings):
            return False

        # WICHTIG: Vorname MUSS ein bekannter Vorname sein
        # Sonst werden Firmennamen, Fachbegriffe etc. als Namen erkannt
        first_base = first_lower.split('-')[0]  # "Hans-Joachim" -> "hans"
        if first_base not in self.COMMON_FIRST_NAMES:
            return False

        return True

    def _api_extract_name(self, text: str) -> Tuple[Optional[str], Optional[str], float]:
        """Extrahiert Namen via DeepSeek API"""
        logger.info("🤖 Verwende DeepSeek API für Name-Extraktion...")
        
        try:
            # Sende relevanten Textausschnitt (max 12000 Zeichen)
            text_short = text[:12000]
            
            prompt = f"""AUFGABE: Extrahiere den GESCHÄFTSFÜHRER oder INHABER aus diesem Impressum-Text.

REGELN:
1. Suche nach: Geschäftsführer, Geschäftsführerin, Inhaber, Inhaberin, Vertreten durch, CEO, Managing Director
2. Es muss eine ECHTE PERSON sein (kein Firmenname!)
3. Ignoriere: Webmaster, Datenschutzbeauftragter, technische Kontakte
4. Bei mehreren Geschäftsführern: Nimm den ERSTEN

FORMAT: Antworte EXAKT so: "Vorname Nachname"
Falls nicht gefunden: Antworte "NICHT_GEFUNDEN"

TEXT:
---
{text_short}
---

Antwort:"""

            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': self.api_model,
                'messages': [
                    {'role': 'system', 'content': 'Du bist ein Experte für deutsches Impressum-Recht. Antworte präzise.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 50,
                'temperature': 0.1
            }
            
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()['choices'][0]['message']['content'].strip()
            result = result.replace('"', '').replace("'", '').strip()
            
            if result.upper() == 'NICHT_GEFUNDEN' or not result:
                return None, None, 0.0
            
            first, last = self._split_name(result)
            
            if first and last and self._validate_name(first, last):
                logger.info(f"✅ Name via API: {first} {last}")
                return first, last, 0.9
                
        except Exception as e:
            logger.error(f"DeepSeek API Fehler: {e}")
        
        return None, None, 0.0

    def _heuristic_extract_name(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Intelligente Heuristik für Name-Extraktion als letzter Fallback"""
        
        # Suche nach Zeilen mit Position-Keywords
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Prüfe auf Position-Keywords
            for keyword, _ in self.POSITION_KEYWORDS[:20]:  # Top-20 Keywords
                if keyword in line_lower:
                    # Suche Namen in dieser oder nächsten Zeile
                    search_lines = [line]
                    if i + 1 < len(lines):
                        search_lines.append(lines[i + 1])
                    if i + 2 < len(lines):
                        search_lines.append(lines[i + 2])
                    
                    for search_line in search_lines:
                        # Finde Wörter die wie Namen aussehen
                        words = search_line.split()
                        name_candidates = []
                        
                        for word in words:
                            # Bereinige Wort
                            clean = re.sub(r'[,.:;!?()"\']', '', word)
                            
                            # Prüfe ob es wie ein Name aussieht
                            if (clean and 
                                len(clean) >= 2 and 
                                clean[0].isupper() and 
                                clean.lower() not in self.NAME_BLACKLIST and
                                not clean.isdigit()):
                                name_candidates.append(clean)
                        
                        # Brauchen mindestens 2 Wörter für Vor- und Nachname
                        if len(name_candidates) >= 2:
                            # Validiere mit bekannten Vornamen
                            for j, candidate in enumerate(name_candidates[:-1]):
                                if candidate.lower() in self.COMMON_FIRST_NAMES:
                                    first = candidate
                                    last = ' '.join(name_candidates[j+1:j+3])
                                    
                                    if self._validate_name(first, last):
                                        return first, last
                            
                            # Fallback: Erste zwei Kandidaten
                            first = name_candidates[0]
                            last = name_candidates[1]
                            
                            if self._validate_name(first, last):
                                return first, last
        
        return None, None

    # ===== E-MAIL EXTRAKTION =====
    
    def extract_emails(self, html: str) -> List[str]:
        """Extrahiert E-Mail-Adressen aus HTML"""
        emails = set()
        
        # Dekodiere HTML-Entities
        decoded_html = html_module.unescape(html)
        
        # Standard-Regex
        found = self.email_pattern.findall(decoded_html)
        for email in found:
            email = email.lower().strip()
            if self._validate_email(email):
                emails.add(email)
        
        # mailto: Links
        soup = BeautifulSoup(decoded_html, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'mailto:' in href.lower():
                email = href.lower().replace('mailto:', '').split('?')[0].strip()
                if self._validate_email(email):
                    emails.add(email)
        
        # Obfuskierte E-Mails (at), [at], etc.
        obfuscated_pattern = r'([a-zA-Z0-9._%+-]+)\s*[\[\(]?\s*(?:at|@|AT)\s*[\]\)]?\s*([a-zA-Z0-9.-]+)\s*[\[\(]?\s*(?:dot|\.)\s*[\]\)]?\s*([a-zA-Z]{2,})'
        for match in re.finditer(obfuscated_pattern, decoded_html, re.IGNORECASE):
            email = f"{match.group(1)}@{match.group(2)}.{match.group(3)}".lower()
            if self._validate_email(email):
                emails.add(email)
        
        return list(emails)

    def _validate_email(self, email: str) -> bool:
        """Validiert E-Mail-Adresse"""
        if not email or '@' not in email:
            return False
        
        # Spam-Keywords
        spam_keywords = [
            'example.com', 'test@', 'noreply', 'no-reply', 'donotreply',
            'spam', 'fake', 'dummy', 'sample', 'placeholder',
            'your-email', 'email@', 'test.com', 'localhost',
            'sentry.io', 'wixpress.com', 'wordpress.com', 'squarespace',
            'wix.com', 'godaddy.com', 'ionos.com'
        ]
        
        email_lower = email.lower()
        for keyword in spam_keywords:
            if keyword in email_lower:
                return False
        
        # Struktur-Check
        parts = email.split('@')
        if len(parts) != 2:
            return False
        
        local, domain = parts
        if not local or not domain or '.' not in domain:
            return False
        
        # Mindestlänge
        if len(email) < 6:
            return False
        
        return True

    def select_best_email(self, emails: List[str], company_name: str = None) -> Optional[str]:
        """Wählt die beste E-Mail aus einer Liste"""
        if not emails:
            return None
        
        if len(emails) == 1:
            return emails[0]
        
        # Prioritäts-Präfixe
        priority = ['info@', 'kontakt@', 'contact@', 'office@', 'mail@', 'hello@', 'hallo@']
        
        for prefix in priority:
            for email in emails:
                if email.lower().startswith(prefix):
                    return email
        
        # Domain-Match mit Firmenname
        if company_name:
            company_clean = re.sub(r'[^a-z0-9]', '', company_name.lower())
            for email in emails:
                domain = email.split('@')[1].split('.')[0].lower()
                if company_clean in domain or domain in company_clean:
                    return email
        
        # Fallback: Kürzeste E-Mail (oft die generische)
        return min(emails, key=len)

    # ===== TELEFON EXTRAKTION =====
    
    def extract_phones(self, html: str) -> List[str]:
        """Extrahiert Telefonnummern aus HTML"""
        phones = set()
        
        text = self.extract_clean_text(html)
        
        # Telefon-Patterns
        patterns = [
            r'(?:Tel\.?|Telefon|Phone|Fon)[:\s]+([+\d\s\-/\(\)]{8,})',
            r'(?:\+49|0049|0)\s*[\d\s/\-\(\)]{8,}',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                phone = match.group(0) if match.groups() == () else match.group(1)
                phone = re.sub(r'[^\d+]', '', phone)
                
                if len(phone) >= 8:
                    phones.add(phone)
        
        return list(phones)

    # ===== HAUPTMETHODE =====
    
    def scrape(self, website: str) -> ContactResult:
        """
        HAUPTMETHODE: Scraped alle Kontaktdaten aus Impressum
        OPTIMIERT: Kein Selenium, kurze Timeouts, kein Sleep
        """
        result = ContactResult()

        try:
            # Normalisiere URL
            base_url = self.normalize_url(website)
            if not base_url:
                return result

            # Schritt 1: Finde Impressum-URL
            impressum_url = self.find_impressum_url(base_url)

            if not impressum_url:
                return result

            result.impressum_url = impressum_url

            # Schritt 2: Lade HTML (NUR requests, kein Selenium)
            html = self.scrape_html(impressum_url)

            if not html:
                return result

            # Schritt 3: Extrahiere Namen
            first, last, confidence, method = self.extract_name(html)

            if first and last:
                result.first_name = first
                result.last_name = last
                result.full_name = f"{first} {last}"
                result.found_name = True
                result.confidence = confidence
                result.extraction_method = method

            # Schritt 4: Extrahiere E-Mails
            emails = self.extract_emails(html)

            if emails:
                result.email = self.select_best_email(emails)
                result.found_email = True

            # Schritt 5: Extrahiere Telefon (optional)
            phones = self.extract_phones(html)
            if phones:
                result.phone = phones[0]

        except Exception as e:
            logger.error(f"Scraping-Fehler fuer {website}: {e}")

        return result

    def scrape_multiple(self, websites: List[str], progress_callback=None) -> List[ContactResult]:
        """
        Scraped mehrere Websites
        
        Args:
            websites: Liste von Website-URLs
            progress_callback: Optional - Funktion(current, total, website)
            
        Returns:
            Liste von ContactResult
        """
        results = []
        
        for idx, website in enumerate(websites):
            if progress_callback:
                progress_callback(idx + 1, len(websites), website)
            
            result = self.scrape(website)
            results.append(result)
        
        # Statistiken
        names_found = sum(1 for r in results if r.found_name)
        emails_found = sum(1 for r in results if r.found_email)
        
        logger.info(f"\n📊 STATISTIK:")
        logger.info(f"   Namen gefunden: {names_found}/{len(results)} ({100*names_found/len(results):.1f}%)")
        logger.info(f"   E-Mails gefunden: {emails_found}/{len(results)} ({100*emails_found/len(results):.1f}%)")
        
        return results


# ===== TEST =====
if __name__ == "__main__":
    # Test-URLs
    test_urls = [
        "https://www.example.com",
        # Füge hier echte Test-URLs hinzu
    ]
    
    scraper = ImpressumScraperUltimate()
    
    for url in test_urls:
        print(f"\n{'='*60}")
        result = scraper.scrape(url)
        print(f"Ergebnis: {result.to_dict()}")
