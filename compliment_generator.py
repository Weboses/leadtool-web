"""
Compliment Generator - OPTIMIERTE VERSION
Generiert personalisierte Komplimente/Texte für Kaltakquise

Features:
- Zentrales Platzhalter-Management (30+ Platzhalter)
- Direkte KI-Kommunikation ohne JSON-Zwang
- Intelligente Anrede-Erkennung
- Debug-Modus für Troubleshooting
- Batch-Verarbeitung mit Progress-Callback
"""
import json
import requests
import os
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Versuche dotenv zu laden
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class GenerationResult:
    """Strukturiertes Ergebnis der Text-Generierung"""
    text: str = ""
    success: bool = False
    error: Optional[str] = None
    confidence_score: int = 0
    has_team: bool = False
    tokens_used: int = 0
    model_used: str = ""
    placeholders_replaced: List[str] = field(default_factory=list)
    placeholders_missing: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'success': self.success,
            'error': self.error,
            'confidence_score': self.confidence_score,
            'has_team': self.has_team,
            'tokens_used': self.tokens_used,
            'model_used': self.model_used,
            'placeholders_replaced': self.placeholders_replaced,
            'placeholders_missing': self.placeholders_missing
        }


class ComplimentGenerator:
    """
    Optimierter Compliment/Text Generator für Kaltakquise
    
    Verwendung:
        generator = ComplimentGenerator()
        
        # Mit Custom Prompt
        result = generator.generate(
            company=company_obj,
            prompt="Hallo {anrede} {last_name}, ich habe gesehen dass {name} {rating} Sterne hat...",
            system_prompt="Du bist ein Vertriebsexperte."
        )
        
        print(result.text)  # Der generierte Text
    """
    
    # Deutsche Vornamen für Geschlechts-Erkennung (Anrede)
    MALE_NAMES = {
        'alexander', 'andreas', 'benjamin', 'christian', 'daniel', 'david',
        'dennis', 'dominik', 'eric', 'erik', 'fabian', 'felix', 'florian',
        'frank', 'hans', 'jan', 'jens', 'johannes', 'jonas', 'julian',
        'kai', 'kevin', 'klaus', 'lars', 'lukas', 'marcel', 'marco',
        'marcus', 'mario', 'markus', 'martin', 'matthias', 'max',
        'maximilian', 'michael', 'niklas', 'nils', 'oliver', 'patrick',
        'paul', 'peter', 'philipp', 'ralf', 'rene', 'robin', 'sascha',
        'sebastian', 'simon', 'stefan', 'steffen', 'stephan', 'thomas',
        'tim', 'tobias', 'tom', 'uwe', 'wolfgang', 'achim', 'albert',
        'alfred', 'armin', 'bernd', 'bernhard', 'boris', 'carsten',
        'christoph', 'claus', 'detlef', 'dieter', 'dirk', 'eckhard',
        'edgar', 'egon', 'ernst', 'erwin', 'franz', 'fred', 'friedhelm',
        'friedrich', 'georg', 'gerald', 'gerd', 'gerhard', 'günter',
        'günther', 'guido', 'harald', 'hartmut', 'heinrich', 'heinz',
        'helmut', 'herbert', 'hermann', 'holger', 'horst', 'hubert',
        'ingo', 'jakob', 'joachim', 'jochen', 'jörg', 'josef', 'jürgen',
        'karl', 'karsten', 'kurt', 'leon', 'leopold', 'lothar', 'ludwig',
        'manfred', 'manuel', 'marc', 'norbert', 'olaf', 'otto', 'pascal',
        'ralph', 'rainer', 'reinhard', 'reinhold', 'richard', 'robert',
        'roland', 'rolf', 'rudolf', 'rüdiger', 'sven', 'theo', 'theodor',
        'thorsten', 'torsten', 'udo', 'ulrich', 'volker', 'walter',
        'werner', 'wilhelm', 'willi', 'winfried'
    }
    
    FEMALE_NAMES = {
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
        'adelheid', 'agnes', 'anita', 'anke', 'astrid', 'beate', 'bettina',
        'christa', 'cornelia', 'dagmar', 'dora', 'edith', 'elfriede',
        'elisabeth', 'ella', 'emma', 'erika', 'erna', 'frieda', 'gerda',
        'gertrud', 'gisela', 'greta', 'gudrun', 'hanna', 'hannah', 'hedwig',
        'helene', 'helga', 'hilde', 'hildegard', 'ilse', 'ingrid', 'irene',
        'jutta', 'karla', 'klara', 'lieselotte', 'lotte', 'luise', 'magda',
        'margarete', 'margot', 'marianne', 'marlene', 'marta', 'martha',
        'mathilde', 'meike', 'nora', 'renate', 'rita', 'rosa', 'rosemarie',
        'ruth', 'sonja', 'sophie', 'traute', 'ulla', 'waltraud', 'wiebke'
    }
    
    # Team-Erkennungs-Keywords
    TEAM_KEYWORDS = [
        'team', 'mitarbeiter', 'mitarbeiterin', 'personal', 'angestellte',
        'kollegen', 'kollegin', 'belegschaft', 'mannschaft', 'crew',
        'staff', 'employees', 'wir sind', 'unser team', 'unsere mitarbeiter'
    ]

    def __init__(self, api_config_file: str = "api_config.json", debug: bool = False):
        """
        Initialisiert den Generator
        
        Args:
            api_config_file: Pfad zur API-Konfiguration
            debug: Wenn True, werden Debug-Informationen geloggt
        """
        self.debug = debug
        self.api_config = {}
        self.api_enabled = False
        self.api_key = ""
        self.api_base_url = ""
        self.api_model = "deepseek-chat"
        
        self._load_api_config(api_config_file)
    
    def _load_api_config(self, config_file: str):
        """Lädt API-Konfiguration aus Datei und Umgebungsvariablen"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.api_config = json.load(f)
            
            active_api = self.api_config.get('active_api', 'deepseek')
            api_settings = self.api_config.get('apis', {}).get(active_api, {})
            
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
                logger.info(f"✅ API konfiguriert: {active_api} ({self.api_model})")
            else:
                logger.warning("⚠️ API nicht konfiguriert")
                
        except FileNotFoundError:
            logger.warning(f"API-Config nicht gefunden: {config_file}")
        except json.JSONDecodeError as e:
            logger.error(f"API-Config ungültig: {e}")
    
    def _detect_gender(self, first_name: str) -> str:
        """
        Erkennt Geschlecht basierend auf Vorname
        
        Returns:
            'male', 'female', oder 'unknown'
        """
        if not first_name:
            return 'unknown'
        
        name_lower = first_name.lower().strip()
        
        if name_lower in self.MALE_NAMES:
            return 'male'
        elif name_lower in self.FEMALE_NAMES:
            return 'female'
        
        # Heuristik: Namen die auf 'a' enden sind oft weiblich (im Deutschen)
        if name_lower.endswith('a') and not name_lower.endswith('ja'):
            return 'female'
        
        return 'unknown'
    
    def _get_anrede(self, first_name: str, last_name: str, formal: bool = True) -> str:
        """
        Generiert passende Anrede basierend auf Name
        
        Args:
            first_name: Vorname
            last_name: Nachname
            formal: True für "Herr/Frau", False für informelle Anrede
        
        Returns:
            Anrede-String
        """
        gender = self._detect_gender(first_name)
        
        if formal:
            if gender == 'male':
                return 'Herr'
            elif gender == 'female':
                return 'Frau'
            else:
                # Fallback: Geschlechtsneutral
                return 'Herr/Frau'
        else:
            # Informelle Anrede
            if first_name:
                return first_name
            elif last_name:
                return last_name
            else:
                return ''
    
    def _detect_team(self, text: str) -> bool:
        """Erkennt ob ein Team erwähnt wird"""
        if not text:
            return False
        
        text_lower = text.lower()
        for keyword in self.TEAM_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
    
    def _build_placeholders(self, company) -> Dict[str, str]:
        """
        Erstellt alle verfügbaren Platzhalter für eine Company
        
        Verfügbare Platzhalter:
        - {name} - Firmenname
        - {website} - Website URL
        - {email} - E-Mail Adresse
        - {phone} - Telefonnummer
        - {first_name} - Vorname des Ansprechpartners
        - {last_name} - Nachname des Ansprechpartners
        - {full_name} - Vollständiger Name (Vorname + Nachname)
        - {anrede} - Formelle Anrede (Herr/Frau)
        - {anrede_informell} - Informelle Anrede (Vorname)
        - {anrede_mit_name} - Komplette Anrede (z.B. "Herr Müller")
        - {description} - Firmenbeschreibung
        - {rating} - Google-Bewertung
        - {rating_stars} - Bewertung als Sterne (★★★★☆)
        - {reviews} - Anzahl Bewertungen
        - {review_keywords} - Keywords aus Reviews
        - {category} - Hauptkategorie
        - {categories} - Alle Kategorien (kommasepariert)
        - {city} - Stadt
        - {address} - Vollständige Adresse
        - {zip_code} - PLZ
        - {country} - Land
        - {owner_name} - Inhaber-Name (falls bekannt)
        - {compliment} - Bereits generiertes Kompliment
        - {datum} - Aktuelles Datum
        - {datum_lang} - Datum ausgeschrieben
        """
        
        # Sichere Attribut-Zugriffe
        def safe_get(obj, attr, default=''):
            try:
                val = getattr(obj, attr, default)
                return val if val is not None else default
            except Exception:
                return default
        
        first_name = safe_get(company, 'first_name', '')
        last_name = safe_get(company, 'last_name', '')
        
        # Anrede generieren
        anrede = self._get_anrede(first_name, last_name, formal=True)
        anrede_informell = self._get_anrede(first_name, last_name, formal=False)
        
        # Anrede mit Name
        if anrede and last_name:
            anrede_mit_name = f"{anrede} {last_name}"
        elif first_name:
            anrede_mit_name = first_name
        else:
            anrede_mit_name = ""
        
        # Full Name
        full_name = f"{first_name} {last_name}".strip() if first_name or last_name else ""
        
        # Rating als Sterne
        rating = safe_get(company, 'rating', 0)
        try:
            rating_float = float(rating) if rating else 0
            full_stars = int(rating_float)
            half_star = 1 if (rating_float - full_stars) >= 0.5 else 0
            empty_stars = 5 - full_stars - half_star
            rating_stars = '★' * full_stars + '☆' * (half_star + empty_stars)
        except (ValueError, TypeError):
            rating_stars = '☆☆☆☆☆'
            rating_float = 0
        
        # Kategorien
        industries = safe_get(company, 'industries', [])
        if industries and isinstance(industries, list):
            categories_str = ', '.join(industries[:5])
            main_category = industries[0] if industries else ''
        else:
            categories_str = safe_get(company, 'main_category', '')
            main_category = categories_str
        
        # Datum
        now = datetime.now()
        datum = now.strftime('%d.%m.%Y')
        monate = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
        datum_lang = f"{now.day}. {monate[now.month-1]} {now.year}"
        
        # Platzhalter-Dictionary
        placeholders = {
            # Firma
            '{name}': safe_get(company, 'name', 'Ihrem Unternehmen'),
            '{website}': safe_get(company, 'website', ''),
            '{description}': safe_get(company, 'description', ''),
            
            # Kontakt
            '{email}': safe_get(company, 'email', ''),
            '{phone}': safe_get(company, 'phone', ''),
            
            # Ansprechpartner
            '{first_name}': first_name,
            '{last_name}': last_name,
            '{full_name}': full_name,
            '{anrede}': anrede,
            '{anrede_informell}': anrede_informell,
            '{anrede_mit_name}': anrede_mit_name,
            '{owner_name}': safe_get(company, 'owner_name', ''),
            
            # Bewertungen
            '{rating}': str(rating_float) if rating_float > 0 else 'N/A',
            '{rating_stars}': rating_stars,
            '{reviews}': str(safe_get(company, 'review_count', 0)),
            '{review_keywords}': safe_get(company, 'review_keywords', ''),
            
            # Kategorien
            '{category}': main_category or safe_get(company, 'main_category', ''),
            '{categories}': categories_str,
            
            # Adresse
            '{city}': safe_get(company, 'city', ''),
            '{address}': safe_get(company, 'address', ''),
            '{zip_code}': safe_get(company, 'zip_code', ''),
            '{country}': safe_get(company, 'country', 'Deutschland'),
            
            # Sonstiges
            '{compliment}': safe_get(company, 'compliment', ''),
            '{datum}': datum,
            '{datum_lang}': datum_lang,
        }
        
        # Custom Attributes hinzufügen
        attributes = safe_get(company, 'attributes', {})
        if attributes and isinstance(attributes, dict):
            for key, value in attributes.items():
                placeholders[f'{{{key}}}'] = str(value) if value is not None else ''
        
        return placeholders
    
    def _replace_placeholders(self, text: str, placeholders: Dict[str, str]) -> tuple:
        """
        Ersetzt Platzhalter im Text
        
        Returns:
            Tuple: (processed_text, replaced_list, missing_list)
        """
        replaced = []
        missing = []
        
        # Finde alle Platzhalter im Text
        found_placeholders = re.findall(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', text)
        
        processed_text = text
        for placeholder in found_placeholders:
            if placeholder in placeholders:
                value = placeholders[placeholder]
                if value:  # Nur ersetzen wenn Wert vorhanden
                    processed_text = processed_text.replace(placeholder, value)
                    replaced.append(placeholder)
                else:
                    missing.append(f"{placeholder} (leer)")
            else:
                missing.append(f"{placeholder} (unbekannt)")
        
        return processed_text, replaced, missing
    
    def _call_api(self, system_prompt: str, user_prompt: str, 
                  temperature: float = 0.7, max_tokens: int = 500) -> Dict[str, Any]:
        """
        Ruft die KI-API auf
        
        Returns:
            Dict mit 'text', 'success', 'error', 'tokens_used'
        """
        if not self.api_enabled or not self.api_key:
            return {
                'text': '',
                'success': False,
                'error': 'API nicht konfiguriert',
                'tokens_used': 0
            }
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.api_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        
        if self.debug:
            logger.debug(f"API Request - Model: {self.api_model}")
            logger.debug(f"System Prompt: {system_prompt[:200]}...")
            logger.debug(f"User Prompt: {user_prompt[:200]}...")
        
        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=45
            )
            response.raise_for_status()
            
            result = response.json()
            
            text = result['choices'][0]['message']['content'].strip()
            tokens = result.get('usage', {}).get('total_tokens', 0)
            
            if self.debug:
                logger.debug(f"API Response: {text[:200]}...")
                logger.debug(f"Tokens used: {tokens}")
            
            return {
                'text': text,
                'success': True,
                'error': None,
                'tokens_used': tokens
            }
            
        except requests.exceptions.Timeout:
            return {
                'text': '',
                'success': False,
                'error': 'API-Timeout (45s)',
                'tokens_used': 0
            }
        except requests.exceptions.RequestException as e:
            return {
                'text': '',
                'success': False,
                'error': f'API-Fehler: {str(e)}',
                'tokens_used': 0
            }
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return {
                'text': '',
                'success': False,
                'error': f'Response-Parsing fehlgeschlagen: {str(e)}',
                'tokens_used': 0
            }
    
    def generate(self, company, prompt: str, system_prompt: str = None,
                 temperature: float = 0.7, max_tokens: int = 500) -> GenerationResult:
        """
        Generiert Text für eine Company basierend auf Custom Prompt
        
        Args:
            company: CompanyV3 Objekt (oder ähnliches mit passenden Attributen)
            prompt: User-Prompt mit Platzhaltern (z.B. "Hallo {anrede} {last_name}...")
            system_prompt: Optional - System-Prompt für die KI
            temperature: Kreativität (0.0-1.0)
            max_tokens: Max. Länge der Antwort
        
        Returns:
            GenerationResult mit generiertem Text
        """
        result = GenerationResult()
        result.model_used = self.api_model
        
        # Platzhalter erstellen
        placeholders = self._build_placeholders(company)
        
        # Platzhalter im User-Prompt ersetzen
        processed_prompt, replaced, missing = self._replace_placeholders(prompt, placeholders)
        result.placeholders_replaced = replaced
        result.placeholders_missing = missing
        
        # System-Prompt verarbeiten
        if system_prompt:
            processed_system, _, _ = self._replace_placeholders(system_prompt, placeholders)
        else:
            processed_system = (
                "Du bist ein erfahrener Vertriebsexperte für B2B-Kaltakquise. "
                "Schreibe natürlich, authentisch und personalisiert. "
                "Vermeide Floskeln und generische Phrasen. "
                "Antworte NUR mit dem gewünschten Text, keine Erklärungen oder Zusätze."
            )
        
        if self.debug:
            logger.info(f"📝 Prompt nach Platzhalter-Ersetzung:")
            logger.info(f"   Ersetzt: {replaced}")
            logger.info(f"   Fehlend: {missing}")
        
        # Warnungen für fehlende wichtige Platzhalter
        critical_missing = [p for p in missing if any(x in p for x in ['name', 'anrede', 'first_name', 'last_name'])]
        if critical_missing:
            logger.warning(f"⚠️ Wichtige Platzhalter fehlen: {critical_missing}")
        
        # API aufrufen
        api_result = self._call_api(
            processed_system, 
            processed_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        result.text = api_result['text']
        result.success = api_result['success']
        result.error = api_result['error']
        result.tokens_used = api_result['tokens_used']
        
        # Team-Erkennung aus Review-Keywords
        review_keywords = placeholders.get('{review_keywords}', '')
        result.has_team = self._detect_team(review_keywords)
        
        # Confidence Score basierend auf Datenqualität
        confidence = 50
        if placeholders['{name}'] and placeholders['{name}'] != 'Ihrem Unternehmen':
            confidence += 10
        if placeholders['{first_name}']:
            confidence += 15
        if placeholders['{last_name}']:
            confidence += 10
        if placeholders['{rating}'] and placeholders['{rating}'] != 'N/A':
            confidence += 10
        if placeholders['{review_keywords}']:
            confidence += 5
        result.confidence_score = min(confidence, 100)
        
        if result.success:
            logger.info(f"✅ Text generiert ({result.tokens_used} Tokens)")
        else:
            logger.error(f"❌ Generierung fehlgeschlagen: {result.error}")
        
        return result
    
    def generate_compliment(self, company, prompt_id: str = None) -> Dict[str, Any]:
        """
        Legacy-Methode für Rückwärts-Kompatibilität
        
        Returns:
            Dict im alten Format: {'compliment': str, 'confidence_score': int, ...}
        """
        # Standard-Kompliment-Prompt
        default_prompt = """Schreibe ein kurzes, authentisches Kompliment für {name} basierend auf folgenden Informationen:

- Bewertung: {rating} Sterne ({reviews} Bewertungen)
- Kategorie: {category}
- Keywords aus Bewertungen: {review_keywords}
- Beschreibung: {description}

Das Kompliment soll:
1. Spezifisch auf die Stärken eingehen (basierend auf den Keywords)
2. Die gute Bewertung erwähnen wenn über 4.0
3. Authentisch und nicht übertrieben klingen
4. Maximal 2-3 Sätze lang sein

Schreibe NUR das Kompliment, keine Einleitung oder Erklärung."""

        result = self.generate(company, default_prompt)
        
        return {
            'compliment': result.text,
            'confidence_score': result.confidence_score,
            'overstatement_score': max(0, 100 - result.confidence_score),
            'has_team': result.has_team
        }
    
    def generate_for_companies(self, companies: List, prompt: str, 
                               system_prompt: str = None,
                               progress_callback: Callable = None,
                               save_to_field: str = 'compliment') -> Dict[str, int]:
        """
        Generiert Texte für mehrere Companies
        
        Args:
            companies: Liste von Company-Objekten
            prompt: User-Prompt mit Platzhaltern
            system_prompt: Optional - System-Prompt
            progress_callback: Optional - Funktion(current, total, company_name)
            save_to_field: Feld in dem das Ergebnis gespeichert wird
        
        Returns:
            Dict: {'success': int, 'errors': int, 'total': int}
        """
        stats = {'success': 0, 'errors': 0, 'total': len(companies)}
        
        for idx, company in enumerate(companies):
            try:
                if progress_callback:
                    name = getattr(company, 'name', None) or getattr(company, 'website', 'Unbekannt')
                    progress_callback(idx + 1, len(companies), name)
                
                result = self.generate(company, prompt, system_prompt)
                
                if result.success:
                    # Speichere Ergebnis
                    if hasattr(company, save_to_field):
                        setattr(company, save_to_field, result.text)
                    elif hasattr(company, 'attributes'):
                        if company.attributes is None:
                            company.attributes = {}
                        company.attributes[save_to_field] = result.text
                    
                    # Zusätzliche Felder wenn vorhanden
                    if hasattr(company, 'confidence_score'):
                        company.confidence_score = result.confidence_score
                    if hasattr(company, 'has_team'):
                        company.has_team = result.has_team
                    
                    stats['success'] += 1
                else:
                    logger.error(f"Fehler bei {getattr(company, 'name', '?')}: {result.error}")
                    stats['errors'] += 1
                    
            except Exception as e:
                logger.error(f"Exception bei Company: {e}")
                stats['errors'] += 1
        
        logger.info(f"📊 Generierung abgeschlossen: {stats['success']}/{stats['total']} erfolgreich")
        return stats
    
    def preview_placeholders(self, company) -> Dict[str, str]:
        """
        Zeigt alle verfügbaren Platzhalter und ihre Werte für eine Company
        Nützlich für Debugging und Prompt-Entwicklung
        """
        return self._build_placeholders(company)
    
    def validate_prompt(self, prompt: str, company=None) -> Dict[str, Any]:
        """
        Validiert einen Prompt und zeigt welche Platzhalter verwendet werden
        
        Args:
            prompt: Der zu validierende Prompt
            company: Optional - Company für Wert-Preview
        
        Returns:
            Dict mit Validierungs-Informationen
        """
        # Finde alle Platzhalter im Prompt
        found = re.findall(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', prompt)
        found_unique = list(set(found))
        
        # Bekannte Platzhalter
        known = [
            '{name}', '{website}', '{email}', '{phone}',
            '{first_name}', '{last_name}', '{full_name}',
            '{anrede}', '{anrede_informell}', '{anrede_mit_name}',
            '{description}', '{rating}', '{rating_stars}', '{reviews}',
            '{review_keywords}', '{category}', '{categories}',
            '{city}', '{address}', '{zip_code}', '{country}',
            '{owner_name}', '{compliment}', '{datum}', '{datum_lang}'
        ]
        
        valid = [p for p in found_unique if p in known]
        unknown = [p for p in found_unique if p not in known]
        
        result = {
            'is_valid': len(unknown) == 0,
            'placeholders_found': found_unique,
            'placeholders_valid': valid,
            'placeholders_unknown': unknown,
            'placeholder_count': len(found),
            'unique_count': len(found_unique),
        }
        
        # Werte-Preview wenn Company gegeben
        if company:
            placeholders = self._build_placeholders(company)
            result['preview'] = {p: placeholders.get(p, '???') for p in found_unique}
        
        return result


# ===== ALIAS FÜR RÜCKWÄRTS-KOMPATIBILITÄT =====
class AIColumnProcessor(ComplimentGenerator):
    """
    Alias-Klasse für Rückwärts-Kompatibilität
    Verwendet intern ComplimentGenerator
    """
    
    def get_company_placeholders(self, company) -> Dict[str, str]:
        """Alias für _build_placeholders"""
        return self._build_placeholders(company)
    
    def process_prompt(self, prompt: str, company, system_prompt: str = None) -> Optional[str]:
        """
        Führt einen Prompt für eine Company aus
        
        Returns:
            str: Ergebnis-Text oder None bei Fehler
        """
        result = self.generate(company, prompt, system_prompt)
        return result.text if result.success else None
    
    def process_column_for_companies(self, companies: List, column_name: str, 
                                     prompt: str, system_prompt: str = None,
                                     progress_callback: Callable = None) -> Dict[str, int]:
        """
        Führt Prompt für alle Companies aus und speichert in custom column
        """
        return self.generate_for_companies(
            companies=companies,
            prompt=prompt,
            system_prompt=system_prompt,
            progress_callback=progress_callback,
            save_to_field=column_name
        )


# ===== TEST =====
if __name__ == "__main__":
    # Test-Objekt
    class MockCompany:
        def __init__(self):
            self.name = "Mustermann GmbH"
            self.website = "https://mustermann.de"
            self.email = "info@mustermann.de"
            self.first_name = "Max"
            self.last_name = "Mustermann"
            self.rating = 4.7
            self.review_count = 128
            self.review_keywords = "professionell, schnell, freundliches Team, gute Beratung"
            self.main_category = "IT-Dienstleistungen"
            self.industries = ["IT-Dienstleistungen", "Webentwicklung", "Beratung"]
            self.city = "München"
            self.description = "Ihr Partner für digitale Lösungen"
            self.attributes = {}
    
    # Generator testen
    generator = ComplimentGenerator(debug=True)
    company = MockCompany()
    
    # Platzhalter anzeigen
    print("\n=== VERFÜGBARE PLATZHALTER ===")
    placeholders = generator.preview_placeholders(company)
    for key, value in placeholders.items():
        if value:
            print(f"  {key}: {value}")
    
    # Prompt validieren
    print("\n=== PROMPT VALIDIERUNG ===")
    test_prompt = "Hallo {anrede} {last_name}, ich habe gesehen dass {name} {rating} Sterne hat!"
    validation = generator.validate_prompt(test_prompt, company)
    print(f"  Valid: {validation['is_valid']}")
    print(f"  Platzhalter: {validation['placeholders_found']}")
    print(f"  Preview: {validation.get('preview', {})}")
    
    # Generierung testen (nur wenn API konfiguriert)
    if generator.api_enabled:
        print("\n=== GENERIERUNG ===")
        result = generator.generate(company, test_prompt)
        print(f"  Erfolg: {result.success}")
        print(f"  Text: {result.text}")
        print(f"  Tokens: {result.tokens_used}")
