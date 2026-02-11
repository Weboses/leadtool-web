"""
Prompt Manager - Verwaltet individuelle Prompts für Kompliment-Generierung
"""
import json
import os
import uuid
import logging
from datetime import datetime, timezone
from models_v3 import DatabaseV3, CompanyV3

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PromptManager:
    """Verwaltet Custom Prompts"""

    def __init__(self, prompts_file="custom_prompts.json"):
        self.prompts_file = prompts_file
        self.prompts = self.load_prompts()

    def load_prompts(self):
        """Lädt gespeicherte Prompts"""
        if os.path.exists(self.prompts_file):
            try:
                with open(self.prompts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError, PermissionError) as e:
                logging.warning(f"Prompts konnten nicht geladen werden: {e}")
                return self.get_default_prompts()
        else:
            return self.get_default_prompts()

    def save_prompts(self):
        """Speichert Prompts"""
        with open(self.prompts_file, 'w', encoding='utf-8') as f:
            json.dump(self.prompts, f, indent=2, ensure_ascii=False)

    def get_default_prompts(self):
        """Gibt Standard-Prompts zurück"""
        return {
            "prompts": [
                {
                    "id": "berater_template",
                    "name": "Berater-Template (ohne KI)",
                    "description": "Bewertungsbasierte Komplimente nach bewährtem Muster. Braucht keine API. "
                                   "Staffelung: 5-9 / 10-19 / 20-49 / 50+ Bewertungen. "
                                   "Bei <5 Reviews oder Rating <4.0: neutraler Fallback.",
                    "system_prompt": "",
                    "user_prompt_template": "TEMPLATE_BASED",
                    "target_industries": ["Berater", "Allgemein", "Universal"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "is_default": True,
                    "is_template": True
                }
            ]
        }

    def get_all_prompts(self):
        """Gibt alle Prompts zurück"""
        return self.prompts.get('prompts', [])

    def get_prompt_by_id(self, prompt_id):
        """Gibt Prompt nach ID"""
        for prompt in self.prompts.get('prompts', []):
            if prompt['id'] == prompt_id:
                return prompt
        return None

    def get_prompt_by_name(self, name):
        """Gibt Prompt nach Name"""
        for prompt in self.prompts.get('prompts', []):
            if prompt['name'] == name:
                return prompt
        return None

    def add_prompt(self, name, description, system_prompt, user_prompt_template,
                   target_industries=None):
        """Fügt neuen Prompt hinzu"""

        # Generiere eindeutige ID mit UUID
        prompt_id = f"custom_{uuid.uuid4().hex[:8]}"

        new_prompt = {
            "id": prompt_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "target_industries": target_industries or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_default": False
        }

        if 'prompts' not in self.prompts:
            self.prompts['prompts'] = []

        self.prompts['prompts'].append(new_prompt)
        self.save_prompts()

        return prompt_id

    def update_prompt(self, prompt_id, **kwargs):
        """Aktualisiert Prompt"""
        for i, prompt in enumerate(self.prompts.get('prompts', [])):
            if prompt['id'] == prompt_id:
                # Update felder
                for key, value in kwargs.items():
                    if key in prompt:
                        prompt[key] = value

                prompt['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.prompts['prompts'][i] = prompt
                self.save_prompts()
                return True

        return False

    def delete_prompt(self, prompt_id):
        """Löscht Prompt (nur wenn nicht default)"""
        for i, prompt in enumerate(self.prompts.get('prompts', [])):
            if prompt['id'] == prompt_id:
                if prompt.get('is_default'):
                    return False  # Kann default nicht löschen

                del self.prompts['prompts'][i]
                self.save_prompts()
                return True

        return False

    def build_enriched_context_for_company(self, company):
        """
        Erstellt erweiterten Kontext aus ALLEN verfügbaren Daten.
        Nutzt intelligente Fallbacks wenn review_keywords fehlen.
        """
        context_parts = []

        # === 1. REVIEW_KEYWORDS (wenn vorhanden) ===
        if company.review_keywords and company.review_keywords.strip():
            context_parts.append(f"REVIEW KEYWORDS: {company.review_keywords}")
            context_parts.append("(Diese Keywords stammen aus echten Google-Rezensionen)")

        # === 2. DESCRIPTION (sehr wertvoll!) ===
        if company.description and company.description.strip():
            context_parts.append(f"\nFIRMEN-BESCHREIBUNG: {company.description[:500]}")
            context_parts.append("(Nutze diese Info für spezifische Komplimente)")

        # === 3. OWNER_NAME (Personalisierung!) ===
        if company.owner_name and company.owner_name.strip():
            context_parts.append(f"\nINHABER: {company.owner_name}")
            context_parts.append("(Erwähne den Inhaber wenn passend)")

        # === 4. CATEGORIES (detailliert!) ===
        if company.industries and len(company.industries) > 0:
            categories_str = ', '.join(company.industries[:5])
            context_parts.append(f"\nKATEGORIEN: {categories_str}")

            # Spezielle Kategorien hervorheben
            if len(company.industries) > 1:
                context_parts.append(f"(Vielseitig - {len(company.industries)} Bereiche!)")

        # === 5. WORKDAY_TIMING (Service-Indikator) ===
        if company.workday_timing and company.workday_timing.strip():
            context_parts.append(f"\nÖFFNUNGSZEITEN: {company.workday_timing[:100]}")
            context_parts.append("(Zeigt Erreichbarkeit und Service-Orientierung)")

        # === 6. ADDRESS/LOCATION ===
        if company.city:
            context_parts.append(f"\nSTANDORT: {company.city}")

        # === ZUSAMMENFASSUNG ===
        if not context_parts:
            return "Keine zusätzlichen Details verfügbar."

        return '\n'.join(context_parts)

    def build_prompt_for_company(self, prompt_id, company):
        """Baut vollständigen Prompt für Company mit enriched context"""
        prompt = self.get_prompt_by_id(prompt_id)
        if not prompt:
            return None

        # Zusätzliche Platzhalter für erweiterte Personalisierung
        category = company.main_category or (company.industries[0] if company.industries else 'Unbekannt')

        # === INTELLIGENTER KONTEXT: Nutze ALLE verfügbaren Daten ===
        enriched_context = self.build_enriched_context_for_company(company)

        # Ersetze Platzhalter - erweitert mit enriched context
        try:
            user_prompt = prompt['user_prompt_template'].format(
                studio_name=company.name or "dem Unternehmen",
                name=company.name or "dem Unternehmen",
                average_rating=company.rating or 0,
                rating=company.rating or 0,
                total_reviews=company.review_count or 0,
                reviews=company.review_count or 0,
                review_keywords=enriched_context,  # NUTZE ENRICHED CONTEXT!
                category=category,
                description=company.description or "Keine Beschreibung",
                owner_name=company.owner_name or "Inhaber",
                categories=', '.join(company.industries[:3]) if company.industries else "Keine Kategorien",
                city=company.city or "Unbekannter Standort"
            )
        except KeyError as e:
            # Fallback wenn Platzhalter fehlt
            logging.warning(f"Fehlender Platzhalter {e} in Prompt-Template")
            # Einfacher Fallback
            template = prompt['user_prompt_template']
            template = template.replace('{review_keywords}', enriched_context)
            template = template.replace('{name}', company.name or "dem Unternehmen")
            template = template.replace('{studio_name}', company.name or "dem Unternehmen")
            template = template.replace('{rating}', str(company.rating or 0))
            template = template.replace('{average_rating}', str(company.rating or 0))
            template = template.replace('{reviews}', str(company.review_count or 0))
            template = template.replace('{total_reviews}', str(company.review_count or 0))
            template = template.replace('{category}', category)
            user_prompt = template

        return {
            'system': prompt['system_prompt'],
            'user': user_prompt
        }

    def get_recommended_prompt(self, company):
        """Empfiehlt Prompt basierend auf Industrie"""
        if not company.main_category:
            # Fallback: Erster Prompt
            prompts = self.get_all_prompts()
            return prompts[0]['id'] if prompts else None

        category_lower = company.main_category.lower()

        # Suche passenden Prompt
        for prompt in self.get_all_prompts():
            target_industries = [ind.lower() for ind in prompt.get('target_industries', [])]

            for industry in target_industries:
                if industry in category_lower or category_lower in industry:
                    return prompt['id']

        # Fallback: Erster Prompt
        prompts = self.get_all_prompts()
        return prompts[0]['id'] if prompts else None
