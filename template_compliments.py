"""
Template-basierte Kompliment-Generierung (Berater V16)
Generiert Komplimente nach festen Regeln basierend auf Rating/Reviews,
ohne KI-API-Aufrufe. 1:1 Portierung des bewährten n8n-Workflows.

Regeln (aus Chef-Feedback):
- Bei 1-4 Bewertungen: IMMER NEUTRAL (kein Sterne-Kommentar)
- Erst ab 5+ Bewertungen richtig loben mit Zahlen
- Erster Buchstabe klein (für "Hallo {Name}, {kompliment}")
"""
import random
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# TEMPLATES - 1:1 aus n8n Kompliment-Generator V16
# ═══════════════════════════════════════════════════════════════

TEMPLATES = {
    # 50+ Bewertungen (4.0+) - Richtig beeindruckend!
    'rating_50plus': [
        "über {reviews} zufriedene Kunden und {rating} Sterne, das spricht für sich!",
        "bei über {reviews} Bewertungen und {rating} Sternen machst du offensichtlich alles richtig!",
        "{rating} Sterne bei über {reviews} Bewertungen, das sieht man wirklich selten!",
    ],
    # 20-49 Bewertungen (4.0+) - Sehr gut!
    'rating_20plus': [
        "{reviews} zufriedene Kunden und {rating} Sterne, das spricht für sich!",
        "bei {reviews} Bewertungen und {rating} Sternen machst du offensichtlich einiges richtig!",
        "{rating} Sterne bei {reviews} Bewertungen, das kann sich wirklich sehen lassen!",
    ],
    # 10-19 Bewertungen (4.0+) - Gut!
    'rating_10plus': [
        "{reviews} zufriedene Kunden und {rating} Sterne, das spricht für dich!",
        "bei {reviews} Bewertungen und {rating} Sternen machst du einiges richtig!",
        "{rating} Sterne bei {reviews} Bewertungen, das kann sich sehen lassen!",
    ],
    # 5-9 Bewertungen (4.0+) - Solide!
    'rating_5plus': [
        "{reviews} Bewertungen und {rating} Sterne, das kann sich sehen lassen!",
        "bei {reviews} Bewertungen und {rating} Sternen machst du einiges richtig!",
        "{rating} Sterne bei {reviews} Bewertungen, nicht schlecht!",
    ],
    # NEUTRAL (Rating < 4.0 ODER keine Bewertungen ODER 1-4 Bewertungen)
    'neutral': [
        "bei meiner Recherche bin ich auf dich aufmerksam geworden.",
        "dein Online Auftritt hat mein Interesse geweckt.",
        "bei meiner Suche bin ich auf dich gestoßen.",
        "ich bin bei meiner Recherche auf dich aufmerksam geworden.",
    ],
}


def _format_rating(rating):
    """Formatiert Rating mit Komma statt Punkt (4.5 -> '4,5', 5.0 -> '5')"""
    if rating is None:
        return ""
    r = float(rating)
    if r == int(r):
        return str(int(r))
    return f"{r:.1f}".replace('.', ',')


def _format_reviews(reviews):
    """Formatiert Reviews als ganze Zahl"""
    if reviews is None:
        return "0"
    return str(int(float(reviews)))


def _get_category(rating, reviews):
    """Bestimmt die Template-Kategorie basierend auf Rating/Reviews"""
    r = float(rating) if rating else 0
    rev = int(float(reviews)) if reviews else 0

    # Keine Bewertung oder Rating unter 4.0 → Neutral
    if not r or not rev or r < 4.0:
        return 'neutral'

    # 1-4 Bewertungen: Auch neutral (nicht übertreiben!)
    if rev < 5:
        return 'neutral'

    # Ab 5 Bewertungen: Richtig loben
    if rev >= 50:
        return 'rating_50plus'
    if rev >= 20:
        return 'rating_20plus'
    if rev >= 10:
        return 'rating_10plus'
    return 'rating_5plus'


def generate_template_compliment(company):
    """
    Generiert ein Template-basiertes Kompliment für eine Company.
    1:1 Logik aus dem n8n-Workflow (Berater V16).

    Regeln:
    - Rating >= 4.0 und Reviews >= 5: Bewertungs-basiertes Kompliment
    - Rating < 4.0 ODER Reviews < 5 ODER keine Daten: Neutraler Fallback

    Returns:
        dict mit 'compliment', 'confidence_score', 'overstatement_score', 'has_team'
    """
    rating = getattr(company, 'rating', None)
    reviews = getattr(company, 'review_count', None)

    # Versuche auch reviews aus anderen Feldern
    if reviews is None:
        reviews = getattr(company, 'reviews', None)

    category = _get_category(rating, reviews)
    templates = TEMPLATES[category]
    template = random.choice(templates)

    # Platzhalter ersetzen
    compliment = template.replace('{rating}', _format_rating(rating))
    compliment = compliment.replace('{reviews}', _format_reviews(reviews))

    # Erster Buchstabe klein (für "Hallo {Name}, {kompliment}")
    compliment = compliment[0].lower() + compliment[1:]

    is_rating_based = category != 'neutral'

    return {
        'compliment': compliment,
        'confidence_score': 90 if is_rating_based else 50,
        'overstatement_score': 5,
        'has_team': False
    }


def generate_template_compliment_bulk(companies, progress_callback=None):
    """
    Generiert Template-Komplimente für eine Liste von Companies.

    Args:
        companies: Liste von Company-Objekten
        progress_callback: Optional - Funktion(current, total, company_name)

    Returns:
        dict: {'success': int, 'skipped': int, 'total': int}
    """
    stats = {'success': 0, 'skipped': 0, 'total': len(companies)}

    for idx, company in enumerate(companies):
        if progress_callback:
            name = getattr(company, 'name', None) or getattr(company, 'website', 'Unbekannt')
            progress_callback(idx + 1, len(companies), name)

        # Skip wenn bereits Kompliment vorhanden
        if getattr(company, 'compliment', None):
            stats['skipped'] += 1
            continue

        result = generate_template_compliment(company)
        company.compliment = result['compliment']
        company.confidence_score = result.get('confidence_score', 50)
        company.overstatement_score = result.get('overstatement_score', 0)
        company.has_team = result.get('has_team', False)

        stats['success'] += 1

    return stats
