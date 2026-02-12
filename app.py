"""
Lead-Tool V4.0 - Web Edition
Flask-basierte Web-App mit identischen Funktionen wie Desktop-Version
"""
import os
import json
import logging
import threading
import pandas as pd
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Backend-Module (Original-Code!)
from models_v3 import DatabaseV3, CompanyV3, Project, Base
from compliment_generator import ComplimentGenerator
from impressum_scraper_ultimate import ImpressumScraperUltimate
from prompt_manager import PromptManager
from template_compliments import generate_template_compliment

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask App
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'leadtool-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'backups'), exist_ok=True)

# Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database
db = DatabaseV3(db_path=os.path.join(os.path.dirname(__file__), 'data', 'lead_enrichment_v3.db'))
db.create_all()

# Lazy-loaded modules
_compliment_generator = None
_impressum_scraper = None
_prompt_manager = None

def get_compliment_generator():
    global _compliment_generator
    if _compliment_generator is None:
        _compliment_generator = ComplimentGenerator()
    return _compliment_generator

def get_impressum_scraper():
    global _impressum_scraper
    if _impressum_scraper is None:
        _impressum_scraper = ImpressumScraperUltimate()
    return _impressum_scraper

def get_prompt_manager():
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager

# Background task tracking
background_tasks = {}

# ============================================================
# USER MODEL (Simple - kann erweitert werden)
# ============================================================
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# Simple user storage (in production: use database)
users = {
    'admin': User('1', 'admin', generate_password_hash('leadtool2024'))
}

@login_manager.user_loader
def load_user(user_id):
    for user in users.values():
        if user.id == user_id:
            return user
    return None

# ============================================================
# AUTH ROUTES
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = users.get(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Ungültige Anmeldedaten', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ============================================================
# MAIN ROUTES
# ============================================================
@app.route('/')
@login_required
def index():
    """Hauptseite - Lead-Übersicht"""
    session_db = db.get_session()
    projects = session_db.query(Project).order_by(Project.created_at.desc()).all()
    session_db.close()
    return render_template('index.html', projects=projects)

# ============================================================
# API: PROJECTS
# ============================================================
@app.route('/api/projects')
@login_required
def get_projects():
    """Liste aller Projekte"""
    session_db = db.get_session()
    projects = session_db.query(Project).order_by(Project.created_at.desc()).all()
    result = [{
        'id': p.id,
        'name': p.name,
        'lead_count': p.lead_count,
        'created_at': p.created_at.isoformat() if p.created_at else None
    } for p in projects]
    session_db.close()
    return jsonify(result)

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    """Neues Projekt erstellen"""
    data = request.json
    session_db = db.get_session()
    project = Project(
        name=data.get('name', 'Neues Projekt'),
        lead_count=0,
        created_at=datetime.now()
    )
    session_db.add(project)
    session_db.commit()
    project_id = project.id
    session_db.close()
    return jsonify({'id': project_id, 'success': True})

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    """Projekt und alle zugehörigen Leads löschen"""
    session_db = db.get_session()
    try:
        project = session_db.query(Project).filter_by(id=project_id).first()
        if not project:
            session_db.close()
            return jsonify({'error': 'Projekt nicht gefunden'}), 404

        # Alle Leads des Projekts löschen
        deleted_leads = session_db.query(CompanyV3).filter_by(project_id=project_id).delete()

        # Projekt löschen
        session_db.delete(project)
        session_db.commit()

        logger.info(f"Projekt {project_id} mit {deleted_leads} Leads gelöscht")
        session_db.close()
        return jsonify({'success': True, 'deleted_leads': deleted_leads})
    except Exception as e:
        session_db.rollback()
        session_db.close()
        logger.error(f"Fehler beim Löschen von Projekt {project_id}: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# API: LEADS
# ============================================================
@app.route('/api/leads')
@login_required
def get_leads():
    """Leads mit Pagination und Filter - ALLE DB-Felder!"""
    project_id = request.args.get('project_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', '')  # no_names, no_compliment, complete
    category = request.args.get('category', '')  # Kategorie-Filter
    min_rating = request.args.get('min_rating', type=float)
    min_reviews = request.args.get('min_reviews', type=int)

    session_db = db.get_session()
    query = session_db.query(CompanyV3)

    # Project filter
    if project_id:
        query = query.filter(CompanyV3.project_id == project_id)

    # Search filter
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            (CompanyV3.name.ilike(search_term)) |
            (CompanyV3.website.ilike(search_term)) |
            (CompanyV3.first_name.ilike(search_term)) |
            (CompanyV3.last_name.ilike(search_term)) |
            (CompanyV3.email.ilike(search_term)) |
            (CompanyV3.city.ilike(search_term))
        )

    # Kategorie-Filter
    if category:
        query = query.filter(CompanyV3.main_category.ilike(f'%{category}%'))

    # Rating-Filter
    if min_rating is not None:
        query = query.filter(CompanyV3.rating >= min_rating)

    # Reviews-Filter
    if min_reviews is not None:
        query = query.filter(CompanyV3.review_count >= min_reviews)

    # Spezial-Filter (wie im Original)
    if filter_type == 'no_names':
        query = query.filter(
            (CompanyV3.first_name == None) | (CompanyV3.first_name == '') |
            (CompanyV3.last_name == None) | (CompanyV3.last_name == '')
        )
    elif filter_type == 'no_compliment':
        query = query.filter(
            (CompanyV3.compliment == None) | (CompanyV3.compliment == '')
        )
    elif filter_type == 'complete':
        query = query.filter(
            CompanyV3.first_name != None, CompanyV3.first_name != '',
            CompanyV3.last_name != None, CompanyV3.last_name != '',
            CompanyV3.compliment != None, CompanyV3.compliment != ''
        )

    # Count total
    total = query.count()

    # Pagination
    leads = query.offset((page - 1) * per_page).limit(per_page).all()

    # Original-Spalten vom ersten Lead holen (für dynamische Tabelle)
    original_columns = []
    if leads and leads[0].attributes:
        original_columns = leads[0].attributes.get('_original_columns', [])

    # DYNAMISCH: Alle Original-Daten + neue Felder zurückgeben
    leads_data = []
    for l in leads:
        attrs = l.attributes or {}
        original_data = attrs.get('_original_data', {})

        lead_dict = {
            'id': l.id,
            'first_name': l.first_name or '',
            'last_name': l.last_name or '',
            'compliment': l.compliment or '',
            'original_data': original_data  # Alle Original-CSV-Daten!
        }
        leads_data.append(lead_dict)

    result = {
        'leads': leads_data,
        'original_columns': original_columns,  # Spalten-Namen für Tabellen-Header
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }

    session_db.close()
    return jsonify(result)

@app.route('/api/leads/ids')
@login_required
def get_lead_ids():
    """Alle Lead-IDs für Bulk-Auswahl (wie Original: select_all lädt alle IDs)"""
    project_id = request.args.get('project_id', type=int)
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', '')
    category = request.args.get('category', '')
    min_rating = request.args.get('min_rating', type=float)
    min_reviews = request.args.get('min_reviews', type=int)

    session_db = db.get_session()
    query = session_db.query(CompanyV3.id)

    # Gleiche Filter wie get_leads
    if project_id:
        query = query.filter(CompanyV3.project_id == project_id)
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            (CompanyV3.name.ilike(search_term)) |
            (CompanyV3.website.ilike(search_term)) |
            (CompanyV3.first_name.ilike(search_term)) |
            (CompanyV3.last_name.ilike(search_term)) |
            (CompanyV3.email.ilike(search_term)) |
            (CompanyV3.city.ilike(search_term))
        )
    if category:
        query = query.filter(CompanyV3.main_category.ilike(f'%{category}%'))
    if min_rating is not None:
        query = query.filter(CompanyV3.rating >= min_rating)
    if min_reviews is not None:
        query = query.filter(CompanyV3.review_count >= min_reviews)
    if filter_type == 'no_names':
        query = query.filter(
            (CompanyV3.first_name == None) | (CompanyV3.first_name == '') |
            (CompanyV3.last_name == None) | (CompanyV3.last_name == '')
        )
    elif filter_type == 'no_compliment':
        query = query.filter(
            (CompanyV3.compliment == None) | (CompanyV3.compliment == '')
        )
    elif filter_type == 'complete':
        query = query.filter(
            CompanyV3.first_name != None, CompanyV3.first_name != '',
            CompanyV3.last_name != None, CompanyV3.last_name != '',
            CompanyV3.compliment != None, CompanyV3.compliment != ''
        )

    ids = [row[0] for row in query.all()]
    session_db.close()
    return jsonify({'ids': ids, 'count': len(ids)})

@app.route('/api/leads/<int:lead_id>')
@login_required
def get_lead(lead_id):
    """Einzelnen Lead abrufen - ALLE DB-Felder!"""
    session_db = db.get_session()
    lead = session_db.query(CompanyV3).get(lead_id)
    if not lead:
        session_db.close()
        return jsonify({'error': 'Lead not found'}), 404

    attrs = lead.attributes or {}
    original_data = attrs.get('_original_data', {})
    original_columns = attrs.get('_original_columns', [])

    result = {
        'id': lead.id,
        'project_id': lead.project_id,
        'first_name': lead.first_name,
        'last_name': lead.last_name,
        'compliment': lead.compliment,
        'original_data': original_data,
        'original_columns': original_columns,
        # Fallback-Felder für Kompatibilität
        'website': lead.website,
        'name': lead.name,
        'description': lead.description,
        'phone': lead.phone,
        'email': lead.email,
        'main_category': lead.main_category,
        'address': lead.address,
        'city': lead.city,
        'zip_code': lead.zip_code,
        'state': lead.state,
        'country': lead.country,
        'rating': lead.rating,
        'review_count': lead.review_count,
        'owner_name': lead.owner_name,
        'review_keywords': lead.review_keywords,
        'link': lead.link,
        'linkedin_url': lead.linkedin_url,
        'confidence_score': lead.confidence_score,
    }
    session_db.close()
    return jsonify(result)

@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
@login_required
def update_lead(lead_id):
    """Lead aktualisieren - ALLE Felder!"""
    data = request.json
    session_db = db.get_session()
    lead = session_db.query(CompanyV3).get(lead_id)
    if not lead:
        session_db.close()
        return jsonify({'error': 'Lead not found'}), 404

    # Alle editierbaren Felder
    editable_fields = [
        'name', 'website', 'description', 'email', 'phone',
        'first_name', 'last_name', 'owner_name',
        'main_category', 'address', 'city', 'zip_code', 'state', 'country',
        'rating', 'review_count', 'review_keywords',
        'link', 'linkedin_url', 'compliment'
    ]

    for key in editable_fields:
        if key in data:
            setattr(lead, key, data[key])

    session_db.commit()
    session_db.close()
    return jsonify({'success': True})

@app.route('/api/leads/<int:lead_id>/compliment', methods=['DELETE'])
@login_required
def delete_lead_compliment(lead_id):
    """Kompliment eines Leads löschen"""
    session_db = db.get_session()
    lead = session_db.query(CompanyV3).get(lead_id)
    if not lead:
        session_db.close()
        return jsonify({'error': 'Lead not found'}), 404

    lead.compliment = None
    session_db.commit()
    session_db.close()
    return jsonify({'success': True})

@app.route('/api/leads/compliments', methods=['DELETE'])
@login_required
def delete_multiple_compliments():
    """Komplimente für mehrere Leads löschen (Bulk)"""
    data = request.json
    lead_ids = data.get('lead_ids', [])

    if not lead_ids:
        return jsonify({'error': 'Keine Leads ausgewählt'}), 400

    session_db = db.get_session()
    deleted = 0
    for lead_id in lead_ids:
        lead = session_db.query(CompanyV3).get(lead_id)
        if lead and lead.compliment:
            lead.compliment = None
            deleted += 1

    session_db.commit()
    session_db.close()
    return jsonify({'success': True, 'deleted': deleted})

# ============================================================
# API: CSV IMPORT - MIT VOLLEM SPALTEN-MAPPING WIE DESKTOP!
# ============================================================

# Intelligentes Spalten-Mapping (1:1 wie Desktop-App)
COLUMN_ALIASES = {
    'website': 'website', 'site': 'website', 'url': 'website',
    'web': 'website', 'homepage': 'website', 'webseite': 'website',
    'name': 'name', 'company_name': 'name', 'firmenname': 'name',
    'firma': 'name', 'unternehmen': 'name', 'company': 'name',
    'description': 'description', 'beschreibung': 'description',
    'website_description': 'description',
    'phone': 'phone', 'telefon': 'phone', 'tel': 'phone',
    'telephone': 'phone', 'phone_number': 'phone',
    'email': 'email', 'e-mail': 'email', 'email_1': 'email',
    'mail': 'email', 'e_mail': 'email',
    'first_name': 'first_name', 'vorname': 'first_name',
    'firstname': 'first_name',
    'last_name': 'last_name', 'nachname': 'last_name',
    'lastname': 'last_name', 'surname': 'last_name',
    'main_category': 'main_category', 'category': 'main_category',
    'kategorie': 'main_category', 'branche': 'main_category',
    'kategorie_echt': 'main_category',
    'categories': 'categories', 'subtypes': 'categories',
    'kategorien': 'categories',
    'address': 'address', 'adresse': 'address',
    'full_address': 'address', 'strasse': 'address',
    'city': 'city', 'stadt': 'city', 'ort': 'city',
    'zip_code': 'zip_code', 'postal_code': 'zip_code',
    'plz': 'zip_code', 'postleitzahl': 'zip_code',
    'state': 'state', 'bundesland': 'state', 'region': 'state',
    'country': 'country', 'land': 'country',
    'rating': 'rating', 'bewertung': 'rating',
    'reviews': 'review_count', 'review_count': 'review_count',
    'anzahl_reviews': 'review_count', 'bewertungen': 'review_count',
    'place_id': 'place_id',
    'owner_name': 'owner_name', 'inhaber': 'owner_name',
    'name_for_emails': 'owner_name',
    'review_keywords': 'review_keywords',
    'link': 'link', 'google_maps_link': 'link',
    'query': 'query',
    'competitors': 'competitors',
    'is_spending_on_ads': 'is_spending_on_ads',
    'workday_timing': 'workday_timing',
    'featured_image': 'featured_image',
    'can_claim': 'can_claim',
    'is_temporarily_closed': 'is_temporarily_closed',
    'closed_on': 'closed_on',
    'owner_profile_link': 'owner_profile_link',
    'linkedin': 'linkedin_url', 'linkedin_url': 'linkedin_url',
}

# DB-Felder die direkt gesetzt werden können
DB_FIELDS = {
    'website', 'name', 'description', 'phone', 'email', 'first_name', 'last_name',
    'main_category', 'address', 'city', 'zip_code', 'state', 'country',
    'rating', 'review_count', 'place_id', 'owner_name', 'review_keywords',
    'link', 'query', 'competitors', 'is_spending_on_ads', 'workday_timing',
    'featured_image', 'can_claim', 'is_temporarily_closed', 'closed_on',
    'owner_profile_link', 'linkedin_url'
}

@app.route('/api/import', methods=['POST'])
@login_required
def import_csv():
    """CSV importieren - speichert ALLE Original-Spalten 1:1!"""
    if 'file' not in request.files:
        return jsonify({'error': 'Keine Datei'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Keine Datei ausgewählt'}), 400

    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Nur CSV-Dateien erlaubt'}), 400

    # Save file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        # Read CSV
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except:
            df = pd.read_csv(filepath, encoding='latin-1')

        # WICHTIG: Original-Spaltennamen und -Reihenfolge speichern!
        original_columns = list(df.columns)
        logger.info(f"CSV hat {len(original_columns)} Spalten: {original_columns[:5]}...")

        # Normalized columns for mapping
        df_normalized = df.copy()
        df_normalized.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]

        # Mapping für Suche/Filter (nur Schlüsselfelder)
        KEY_MAPPINGS = {
            'site': 'website', 'website': 'website', 'url': 'website', 'webseite': 'website',
            'name': 'name', 'company_name': 'name', 'firmenname': 'name',
            'email_1': 'email', 'email': 'email', 'e-mail': 'email',
            'phone': 'phone', 'telefon': 'phone',
            'city': 'city', 'stadt': 'city', 'ort': 'city',
            'rating': 'rating', 'bewertung': 'rating',
            'reviews': 'review_count', 'review_count': 'review_count',
            'category': 'main_category', 'kategorie': 'main_category',
            'full_address': 'address', 'address': 'address', 'adresse': 'address',
            'postal_code': 'zip_code', 'zip_code': 'zip_code', 'plz': 'zip_code',
            'state': 'state', 'bundesland': 'state',
            'country': 'country', 'land': 'country',
        }

        # Create project
        session_db = db.get_session()
        project_name = filename.replace('.csv', '')
        project = Project(
            name=project_name,
            csv_filename=filename,
            lead_count=len(df),
            created_at=datetime.now()
        )
        session_db.add(project)
        session_db.commit()
        project_id = project.id

        # Import leads
        imported = 0
        skipped = 0

        for idx, row in df.iterrows():
            # === ALLES ORIGINAL SPEICHERN ===
            # Speichere die komplette Zeile als Dict mit Original-Spaltennamen
            original_data = {}
            for col in original_columns:
                val = row[col]
                if pd.notna(val):
                    original_data[col] = str(val).strip() if not isinstance(val, (int, float)) else val
                else:
                    original_data[col] = ''

            # Find website (required!)
            website = None
            row_normalized = df_normalized.iloc[idx]
            for csv_col in df_normalized.columns:
                if csv_col in KEY_MAPPINGS and KEY_MAPPINGS[csv_col] == 'website':
                    val = row_normalized.get(csv_col)
                    if pd.notna(val) and str(val).strip():
                        website = str(val).strip()
                        break

            if not website:
                skipped += 1
                continue

            # Create lead
            lead = CompanyV3(project_id=project_id, website=website)

            # Map key fields for search/filter
            for csv_col in df_normalized.columns:
                db_field = KEY_MAPPINGS.get(csv_col)
                if db_field and db_field != 'website':
                    val = row_normalized.get(csv_col)
                    if pd.notna(val):
                        val_str = str(val).strip()
                        if val_str and val_str.lower() != 'nan':
                            if db_field == 'rating':
                                try:
                                    lead.rating = float(val)
                                except:
                                    pass
                            elif db_field == 'review_count':
                                try:
                                    lead.review_count = int(float(val))
                                except:
                                    pass
                            elif hasattr(lead, db_field):
                                setattr(lead, db_field, val_str)

            # === WICHTIG: Speichere ALLE Original-Daten + Spalten-Reihenfolge ===
            lead.attributes = {
                '_original_columns': original_columns,  # Spalten-Reihenfolge
                '_original_data': original_data         # Alle Werte
            }

            session_db.add(lead)
            imported += 1

        session_db.commit()
        session_db.close()

        logger.info(f"CSV-Import fertig: {imported} importiert, {skipped} übersprungen, {len(original_columns)} Spalten")

        return jsonify({
            'success': True,
            'project_id': project_id,
            'imported': imported,
            'skipped': skipped,
            'total': len(df),
            'columns': len(original_columns)
        })

    except Exception as e:
        logger.error(f"Import error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================================
# API: EXPORT
# ============================================================
@app.route('/api/export')
@login_required
def export_csv():
    """Leads als CSV exportieren - Original-Spalten + 3 neue am Ende!"""
    project_id = request.args.get('project_id', type=int)
    lead_ids = request.args.get('lead_ids', '')  # Comma-separated

    session_db = db.get_session()
    query = session_db.query(CompanyV3)

    if lead_ids:
        ids = [int(x) for x in lead_ids.split(',') if x]
        query = query.filter(CompanyV3.id.in_(ids))
    elif project_id:
        query = query.filter(CompanyV3.project_id == project_id)

    leads = query.all()

    if not leads:
        session_db.close()
        return jsonify({'error': 'Keine Leads zum Exportieren'}), 400

    # Hole Original-Spalten vom ersten Lead
    original_columns = []
    first_lead_attrs = leads[0].attributes if leads[0].attributes else {}
    if '_original_columns' in first_lead_attrs:
        original_columns = first_lead_attrs['_original_columns']

    # Neue Spalten die am Ende hinzugefügt werden
    NEW_COLUMNS = ['first_name', 'last_name', 'compliment']

    # Alle Spalten: Original + Neue
    all_columns = original_columns + NEW_COLUMNS

    data = []
    for lead in leads:
        row = {}
        attrs = lead.attributes if lead.attributes else {}
        original_data = attrs.get('_original_data', {})

        # Original-Spalten
        for col in original_columns:
            row[col] = original_data.get(col, '')

        # Neue Spalten am Ende
        row['first_name'] = lead.first_name or ''
        row['last_name'] = lead.last_name or ''
        row['compliment'] = lead.compliment or ''

        data.append(row)

    session_db.close()

    # DataFrame mit korrekter Spalten-Reihenfolge
    df = pd.DataFrame(data, columns=all_columns)
    filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df.to_csv(filepath, index=False, encoding='utf-8')

    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/export/excel')
@login_required
def export_excel():
    """Leads als Excel exportieren - Original-Spalten + 3 neue am Ende!"""
    project_id = request.args.get('project_id', type=int)
    lead_ids = request.args.get('lead_ids', '')

    session_db = db.get_session()
    query = session_db.query(CompanyV3)

    if lead_ids:
        ids = [int(x) for x in lead_ids.split(',') if x]
        query = query.filter(CompanyV3.id.in_(ids))
    elif project_id:
        query = query.filter(CompanyV3.project_id == project_id)

    leads = query.all()

    if not leads:
        session_db.close()
        return jsonify({'error': 'Keine Leads zum Exportieren'}), 400

    # Hole Original-Spalten vom ersten Lead
    original_columns = []
    first_lead_attrs = leads[0].attributes if leads[0].attributes else {}
    if '_original_columns' in first_lead_attrs:
        original_columns = first_lead_attrs['_original_columns']

    # Neue Spalten die am Ende hinzugefügt werden
    NEW_COLUMNS = ['first_name', 'last_name', 'compliment']

    # Alle Spalten: Original + Neue
    all_columns = original_columns + NEW_COLUMNS

    data = []
    for lead in leads:
        row = {}
        attrs = lead.attributes if lead.attributes else {}
        original_data = attrs.get('_original_data', {})

        # Original-Spalten
        for col in original_columns:
            row[col] = original_data.get(col, '')

        # Neue Spalten am Ende
        row['first_name'] = lead.first_name or ''
        row['last_name'] = lead.last_name or ''
        row['compliment'] = lead.compliment or ''

        data.append(row)

    session_db.close()

    # DataFrame mit korrekter Spalten-Reihenfolge
    df = pd.DataFrame(data, columns=all_columns)
    filename = f"leads_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    df.to_excel(filepath, index=False)

    return send_file(filepath, as_attachment=True, download_name=filename)

# ============================================================
# API: NAME FINDER (Bulk) - MIT LOKALER EXTRAKTION WIE ORIGINAL!
# ============================================================

# Deutsche Vornamen-Datenbank (wie im Original)
_KNOWN_FIRST_NAMES = {
    'alexander', 'andreas', 'benjamin', 'christian', 'daniel', 'david', 'dennis', 'dominik',
    'eric', 'erik', 'fabian', 'felix', 'florian', 'frank', 'hans', 'jan', 'jens', 'johannes',
    'jonas', 'julian', 'kai', 'kevin', 'klaus', 'lars', 'lukas', 'marcel', 'marco', 'marcus',
    'mario', 'markus', 'martin', 'matthias', 'max', 'maximilian', 'michael', 'niklas', 'nils',
    'oliver', 'patrick', 'paul', 'peter', 'philipp', 'ralf', 'rene', 'robin', 'sascha',
    'sebastian', 'simon', 'stefan', 'steffen', 'stephan', 'thomas', 'tim', 'tobias', 'tom',
    'uwe', 'wolfgang', 'achim', 'albert', 'alfred', 'armin', 'bernd', 'bernhard', 'boris',
    'carsten', 'christoph', 'claus', 'detlef', 'dieter', 'dirk', 'edgar', 'ernst', 'erwin',
    'franz', 'fred', 'friedhelm', 'friedrich', 'georg', 'gerald', 'gerd', 'gerhard',
    'guido', 'harald', 'hartmut', 'heinrich', 'heinz', 'helmut', 'herbert', 'hermann',
    'holger', 'horst', 'hubert', 'ingo', 'jakob', 'joachim', 'jochen', 'josef',
    'karl', 'karsten', 'kurt', 'leon', 'lothar', 'ludwig', 'manfred', 'manuel', 'marc',
    'mark', 'norbert', 'olaf', 'otto', 'pascal', 'ralph', 'rainer', 'reinhard', 'richard',
    'robert', 'roland', 'rolf', 'rudolf', 'sven', 'theo', 'thorsten', 'torsten', 'udo',
    'ulrich', 'volker', 'walter', 'werner', 'wilhelm', 'willi', 'winfried', 'henning',
    'alexandra', 'andrea', 'angelika', 'anja', 'anna', 'anne', 'annette', 'antje', 'barbara',
    'bianca', 'brigitte', 'carina', 'carmen', 'carolin', 'caroline', 'christina', 'christiane',
    'claudia', 'daniela', 'diana', 'doris', 'elena', 'elke', 'eva', 'franziska', 'gabriele',
    'heike', 'helena', 'ines', 'iris', 'jana', 'jasmin', 'jennifer', 'jessica', 'johanna',
    'julia', 'juliane', 'karin', 'katharina', 'kathrin', 'katja', 'katrin', 'kerstin',
    'kristina', 'lara', 'laura', 'lea', 'lena', 'linda', 'lisa', 'manuela', 'maria',
    'marie', 'marina', 'marion', 'martina', 'melanie', 'michaela', 'monika', 'nadine',
    'natalie', 'nicole', 'nina', 'petra', 'sabine', 'sabrina', 'sandra', 'sara', 'sarah',
    'silke', 'simone', 'sophia', 'stefanie', 'stephanie', 'susanne', 'tanja', 'ulrike',
    'ursula', 'vanessa', 'vera', 'yvonne', 'anita', 'anke', 'astrid', 'beate', 'bettina',
    'christa', 'cornelia', 'dagmar', 'edith', 'elisabeth', 'emma', 'erika', 'frieda',
    'gerda', 'gisela', 'hanna', 'heidi', 'helga', 'hildegard', 'ilse', 'ingrid',
    'jordie', 'melissa', 'christopher', 'epiphanie',
    'wilfried', 'björn', 'lilli', 'jörg', 'ulf',
    'nadia', 'janine', 'evelyn', 'marleen', 'madlen', 'rufus', 'fabio',
    'yevgeniy', 'christoff', 'christof', 'reinfried', 'dorothea',
    'diethelm', 'nico', 'fikriye', 'samia', 'torben', 'ludgerus', 'günter', 'birgit',
    'marcello', 'christine',
}

# Fake/Platzhalter-Namen die NIEMALS akzeptiert werden
_FAKE_NAMES = {
    'mustermann', 'musterfrau', 'mustermensch', 'musterfirma',
    'beispiel', 'example', 'test', 'testing', 'testuser',
    'admin', 'administrator', 'webmaster', 'postmaster',
    'noreply', 'no-reply', 'donotreply',
    'platzhalter', 'placeholder', 'dummy', 'sample',
    'default', 'unknown', 'unbekannt', 'keine', 'keiner',
}

def _is_fake_name(first_name, last_name):
    """Prüft ob ein Name ein Fake/Platzhalter ist"""
    fn = first_name.lower().strip() if first_name else ''
    ln = last_name.lower().strip() if last_name else ''
    if fn in _FAKE_NAMES or ln in _FAKE_NAMES:
        return True
    if ln == 'mustermann' or ln == 'musterfrau':
        return True
    return False

def _extract_name_from_local_data(company):
    """
    Versucht Vor-/Nachname aus vorhandenen Daten zu extrahieren.
    A) attributes (first_name/last_name aus CSV)
    B) Name-Feld (wenn Personenname, z.B. 'Mark Jänsch')
    C) Email (vorname.nachname@...)
    """
    import re as _re
    attrs = company.attributes if company.attributes and isinstance(company.attributes, dict) else {}

    # A) Aus attributes (CSV-Spalten)
    attr_fn = str(attrs.get('first_name', '') or attrs.get('email_1_first_name', '') or '').strip()
    attr_ln = str(attrs.get('last_name', '') or attrs.get('email_1_last_name', '') or '').strip()
    if attr_fn and attr_ln and attr_fn.lower() != 'nan' and attr_ln.lower() != 'nan':
        if not _is_fake_name(attr_fn, attr_ln):
            return attr_fn, attr_ln

    # B) Aus Name-Feld (mehrere Strategien)
    if company.name:
        name = str(company.name).strip()

        # B1) "Inh." / "Inh:" Pattern
        inh_match = _re.search(r'Inh[.:\s]+([A-ZÄÖÜ][a-zäöüß]+)\s+([A-ZÄÖÜ][a-zäöüß]+)', name)
        if inh_match:
            fn, ln = inh_match.group(1), inh_match.group(2)
            if fn.lower() in _KNOWN_FIRST_NAMES and not _is_fake_name(fn, ln):
                return fn, ln

        # B2) "Dr." / "Prof." Pattern
        dr_match = _re.search(r'(?:Dr\.|Prof\.)\s+([A-ZÄÖÜ][a-zäöüß]+)\s+([A-ZÄÖÜ][a-zäöüß]+)', name)
        if dr_match:
            fn, ln = dr_match.group(1), dr_match.group(2)
            if fn.lower() in _KNOWN_FIRST_NAMES and not _is_fake_name(fn, ln):
                return fn, ln

        # B3) Name nach " - "
        if ' - ' in name:
            for segment in name.split(' - '):
                segment = segment.strip()
                seg_parts = segment.split()
                if len(seg_parts) == 2:
                    if seg_parts[0].lower() in _KNOWN_FIRST_NAMES:
                        ln = seg_parts[1].rstrip(',').rstrip('-')
                        if ln and ln[0].isupper() and not _is_fake_name(seg_parts[0], ln):
                            return seg_parts[0], ln

        # B4) Name mit "geb."
        geb_match = _re.search(r'([A-ZÄÖÜ][a-zäöüß]+)\s+([A-ZÄÖÜ][a-zäöüß]+),?\s+geb\.', name)
        if geb_match:
            fn, ln = geb_match.group(1), geb_match.group(2)
            if fn.lower() in _KNOWN_FIRST_NAMES and not _is_fake_name(fn, ln):
                return fn, ln

        # B5) Vorname Nachname am Anfang
        clean = name.split(' - ')[0].split(' | ')[0].split(' (')[0].split(',')[0].strip()
        parts = clean.split()
        if len(parts) >= 2:
            first_word = parts[0].lower()
            if first_word in _KNOWN_FIRST_NAMES:
                last_name = parts[1].rstrip(',').rstrip('-')
                if last_name and last_name[0].isupper() and not _is_fake_name(parts[0], last_name):
                    return parts[0], last_name

        # B6) Vorname Nachname irgendwo im String
        all_words = _re.findall(r'[A-ZÄÖÜa-zäöüß]+', name)
        for i in range(len(all_words) - 1):
            w1 = all_words[i]
            w2 = all_words[i + 1]
            if (w1[0].isupper() and w2[0].isupper()
                    and w1.lower() in _KNOWN_FIRST_NAMES
                    and len(w2) > 2
                    and w2.lower() not in {'personal', 'team', 'consulting', 'gmbh',
                        'group', 'management', 'beratung', 'coaching', 'investment',
                        'unternehmensberatung', 'akademie', 'institut', 'agentur',
                        'partner', 'associates', 'concept', 'solutions', 'service'}
                    and not _is_fake_name(w1, w2)):
                return w1, w2

        # B7) Nachname Vorname (umgekehrt)
        if len(parts) == 2:
            second_word = parts[1].lower()
            if second_word in _KNOWN_FIRST_NAMES:
                fn = parts[1]
                ln = parts[0].rstrip(',').rstrip('-')
                if ln and ln[0].isupper() and not _is_fake_name(fn, ln):
                    return fn, ln

    # C) Aus Email (vorname.nachname@domain.de)
    if company.email:
        email = str(company.email).strip()
        local = email.split('@')[0] if '@' in email else ''
        skip_locals = {'info', 'team', 'post', 'mail', 'contact', 'hello', 'office',
                      'service', 'admin', 'support', 'frage', 'hallo', 'kontakt',
                      'datenschutz', 'st', 'pia', 'skin', 'obank'}
        for sep in ['.', '_', '-']:
            if sep in local:
                ep = local.split(sep, 1)
                if len(ep) == 2:
                    fn_c, ln_c = ep[0], ep[1]
                    if (len(fn_c) > 2 and len(ln_c) > 2
                            and fn_c.isalpha() and ln_c.isalpha()
                            and fn_c.lower() not in skip_locals):
                        fn_lower = fn_c.lower()
                        if fn_lower in _KNOWN_FIRST_NAMES:
                            if not _is_fake_name(fn_c, ln_c):
                                return fn_c.capitalize(), ln_c.capitalize()

    return None, None

@app.route('/api/find-names', methods=['POST'])
@login_required
def find_names():
    """Namen für ausgewählte Leads finden - MIT LOKALER EXTRAKTION!"""
    data = request.json
    lead_ids = data.get('lead_ids', [])

    if not lead_ids:
        return jsonify({'error': 'Keine Leads ausgewählt'}), 400

    # Create task ID
    task_id = f"names_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    import time
    background_tasks[task_id] = {
        'status': 'running',
        'progress': 0,
        'total': len(lead_ids),
        'found': 0,
        'skipped': 0,
        'errors': 0,
        'local_found': 0,  # Aus lokalen Daten gefunden
        'web_found': 0,    # Durch Web-Scraping gefunden
        'current': '',
        'start_time': time.time()
    }

    def worker():
        import time
        scraper = get_impressum_scraper()
        session_db = db.get_session()
        found = 0
        skipped = 0
        errors = 0
        local_found = 0
        web_found = 0

        for idx, lead_id in enumerate(lead_ids):
            if background_tasks[task_id]['status'] == 'cancelled':
                break

            lead = session_db.query(CompanyV3).get(lead_id)
            if not lead:
                skipped += 1
                background_tasks[task_id]['skipped'] = skipped
                continue

            # Skip if already has name
            if lead.first_name and lead.last_name:
                skipped += 1
                background_tasks[task_id]['skipped'] = skipped
                background_tasks[task_id]['progress'] = idx + 1
                continue

            background_tasks[task_id]['current'] = (lead.name or lead.website or '')[:50]
            background_tasks[task_id]['progress'] = idx + 1

            try:
                # ZUERST: Lokale Extraktion versuchen (SCHNELL!)
                fn, ln = _extract_name_from_local_data(lead)

                if fn and ln:
                    lead.first_name = fn
                    lead.last_name = ln
                    session_db.commit()
                    found += 1
                    local_found += 1
                    background_tasks[task_id]['found'] = found
                    background_tasks[task_id]['local_found'] = local_found
                    # Echtzeit-Update: letzter aktualisierter Lead
                    background_tasks[task_id]['last_updated'] = {
                        'id': lead.id,
                        'first_name': fn,
                        'last_name': ln
                    }
                    logger.info(f"[LOCAL] {lead.name}: {fn} {ln}")
                    continue

                # DANN: Web-Scraping nur wenn Website vorhanden und lokal nichts gefunden
                if lead.website:
                    result = scraper.scrape(lead.website)
                    if result.found_name:
                        lead.first_name = result.first_name
                        lead.last_name = result.last_name
                        session_db.commit()
                        found += 1
                        web_found += 1
                        background_tasks[task_id]['found'] = found
                        background_tasks[task_id]['web_found'] = web_found
                        # Echtzeit-Update: letzter aktualisierter Lead
                        background_tasks[task_id]['last_updated'] = {
                            'id': lead.id,
                            'first_name': result.first_name,
                            'last_name': result.last_name
                        }
                        logger.info(f"[WEB] {lead.website}: {result.first_name} {result.last_name}")

            except Exception as e:
                errors += 1
                background_tasks[task_id]['errors'] = errors
                logger.error(f"Name finder error {lead.name}: {e}")

        session_db.close()
        background_tasks[task_id]['status'] = 'completed'
        background_tasks[task_id]['progress'] = len(lead_ids)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return jsonify({'task_id': task_id})

# ============================================================
# API: COMPLIMENT GENERATOR (Bulk) - MIT PROMPT-AUSWAHL WIE ORIGINAL
# ============================================================
@app.route('/api/generate-compliments', methods=['POST'])
@login_required
def generate_compliments():
    """Komplimente für ausgewählte Leads generieren - mit Prompt-Auswahl"""
    data = request.json
    lead_ids = data.get('lead_ids', [])
    prompt_type = data.get('type', 'template')  # 'template' oder 'custom'
    provider = data.get('provider', 'deepseek')
    use_template_only = data.get('is_template', False)  # Template ohne KI

    if not lead_ids:
        return jsonify({'error': 'Keine Leads ausgewählt'}), 400

    # Prompt vorbereiten (nur für KI-basierte Generierung)
    system_prompt = ''
    user_prompt = ''

    if not use_template_only:
        if prompt_type == 'custom':
            system_prompt = data.get('system_prompt', 'Du bist ein Experte für authentische, personalisierte B2B-Kommunikation.')
            user_prompt = data.get('user_prompt', '')
            if not user_prompt:
                return jsonify({'error': 'User-Prompt fehlt'}), 400
        else:
            # Template-Prompt laden
            prompt_id = data.get('prompt_id')
            if prompt_id:
                pm = get_prompt_manager()
                prompt_template = pm.get_prompt_by_id(prompt_id)
                if prompt_template:
                    system_prompt = prompt_template.get('system_prompt', '')
                    user_prompt = prompt_template.get('user_prompt_template', prompt_template.get('prompt', ''))
                else:
                    # Fallback Standard-Prompt
                    system_prompt = 'Du bist ein Experte für authentische B2B-Kommunikation.'
                    user_prompt = """Schreibe ein kurzes, authentisches Kompliment für {name}.
- Bewertung: {rating} Sterne ({reviews} Bewertungen)
- Kategorie: {category}
- Keywords aus Bewertungen: {review_keywords}
Das Kompliment soll 2-3 Sätze lang sein und authentisch klingen."""
            else:
                # Fallback Standard-Prompt
                system_prompt = 'Du bist ein Experte für authentische B2B-Kommunikation.'
                user_prompt = """Schreibe ein kurzes, authentisches Kompliment für {name}.
- Bewertung: {rating} Sterne ({reviews} Bewertungen)
- Kategorie: {category}
- Keywords aus Bewertungen: {review_keywords}
Das Kompliment soll 2-3 Sätze lang sein und authentisch klingen."""

    import time
    task_id = f"compliments_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    background_tasks[task_id] = {
        'status': 'running',
        'progress': 0,
        'total': len(lead_ids),
        'found': 0,
        'generated': 0,
        'skipped': 0,
        'errors': 0,
        'current': '',
        'start_time': time.time(),
        'mode': 'template' if use_template_only else 'ai'
    }

    # Session-Key vor Worker holen (weil Worker in eigenem Thread läuft)
    session_provider, session_api_key = get_session_api_key()

    def worker():
        import time
        generator = None
        if not use_template_only:
            generator = get_compliment_generator()
            # Session-Key hat Priorität
            if session_api_key:
                generator.api_enabled = True
                generator.api_key = session_api_key
                # Provider-spezifische Einstellungen
                if session_provider == 'deepseek':
                    generator.api_base_url = 'https://api.deepseek.com/v1'
                    generator.api_model = 'deepseek-chat'
                elif session_provider == 'openai':
                    generator.api_base_url = 'https://api.openai.com/v1'
                    generator.api_model = 'gpt-4o-mini'
                elif session_provider == 'anthropic':
                    generator.api_base_url = 'https://api.anthropic.com/v1'
                    generator.api_model = 'claude-3-5-sonnet-20241022'
                logger.info(f"Using session API key for {session_provider}")
            else:
                # Fallback: set_provider versucht Umgebungsvariablen/Config
                generator.set_provider(provider)
        session_db = db.get_session()
        generated = 0
        skipped = 0
        errors = 0

        for idx, lead_id in enumerate(lead_ids):
            if background_tasks[task_id]['status'] == 'cancelled':
                break

            lead = session_db.query(CompanyV3).get(lead_id)
            if not lead:
                skipped += 1
                background_tasks[task_id]['skipped'] = skipped
                background_tasks[task_id]['progress'] = idx + 1
                continue

            # Skip if already has compliment
            if lead.compliment:
                skipped += 1
                background_tasks[task_id]['skipped'] = skipped
                background_tasks[task_id]['progress'] = idx + 1
                continue

            background_tasks[task_id]['current'] = (lead.name or lead.website or '')[:50]
            background_tasks[task_id]['progress'] = idx + 1

            try:
                if use_template_only:
                    # Template-basierte Generierung (OHNE KI!)
                    result = generate_template_compliment(lead)
                    compliment_text = result.get('compliment', '')
                    if compliment_text:
                        lead.compliment = compliment_text
                        lead.confidence_score = result.get('confidence_score', 50)
                        session_db.commit()
                        generated += 1
                        background_tasks[task_id]['generated'] = generated
                        background_tasks[task_id]['found'] = generated
                        # Echtzeit-Update
                        background_tasks[task_id]['last_updated'] = {
                            'id': lead.id,
                            'compliment': compliment_text
                        }
                        logger.info(f"[TEMPLATE] {lead.name}: {compliment_text[:50]}...")
                    else:
                        errors += 1
                        background_tasks[task_id]['errors'] = errors
                else:
                    # KI-basierte Generierung
                    result = generator.generate(lead, user_prompt, system_prompt)
                    if result and result.text:
                        lead.compliment = result.text
                        session_db.commit()
                        generated += 1
                        background_tasks[task_id]['generated'] = generated
                        background_tasks[task_id]['found'] = generated
                        # Echtzeit-Update
                        background_tasks[task_id]['last_updated'] = {
                            'id': lead.id,
                            'compliment': result.text[:100] + '...' if len(result.text) > 100 else result.text
                        }
                        logger.info(f"[AI] {lead.name}: OK")
                    else:
                        errors += 1
                        background_tasks[task_id]['errors'] = errors
                        logger.warning(f"[COMPLIMENT] {lead.name}: Kein Ergebnis")
            except Exception as e:
                errors += 1
                background_tasks[task_id]['errors'] = errors
                logger.error(f"Compliment error {lead.name}: {e}")

        session_db.close()
        background_tasks[task_id]['status'] = 'completed'
        background_tasks[task_id]['progress'] = len(lead_ids)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return jsonify({'task_id': task_id})

# ============================================================
# API: TASK STATUS
# ============================================================
@app.route('/api/task/<task_id>')
@login_required
def get_task_status(task_id):
    """Task-Status abrufen"""
    task = background_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@app.route('/api/task/<task_id>/cancel', methods=['POST'])
@login_required
def cancel_task(task_id):
    """Task abbrechen"""
    if task_id in background_tasks:
        background_tasks[task_id]['status'] = 'cancelled'
        return jsonify({'success': True})
    return jsonify({'error': 'Task not found'}), 404

# ============================================================
# API: API CONFIG
# ============================================================
@app.route('/api/config')
@login_required
def get_api_config():
    """API-Konfiguration abrufen - Session > Umgebungsvariablen > Datei"""
    config_path = os.path.join(os.path.dirname(__file__), 'api_config.json')

    # Default config
    config = {
        'providers': {
            'deepseek': {'api_key': '', 'model': 'deepseek-chat'},
            'openai': {'api_key': '', 'model': 'gpt-4o'},
            'anthropic': {'api_key': '', 'model': 'claude-3-5-sonnet-20241022'}
        },
        'active_provider': 'deepseek'
    }

    # Lade aus Datei wenn vorhanden
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)

    # Prüfe Session-Key ZUERST (hat Priorität!)
    session_provider = session.get('api_provider')
    session_key = session.get('api_key')

    if session_key:
        # Session-Key vorhanden
        config['api_connected'] = True
        config['active_provider'] = session_provider
        config['session_active'] = True
        # Markiere den Provider als verbunden
        if session_provider in config.get('providers', {}):
            config['providers'][session_provider]['has_key'] = True

        # Hide keys
        for provider in config.get('providers', {}):
            config['providers'][provider]['api_key'] = ''

        return jsonify(config)

    # Umgebungsvariablen prüfen (für Railway etc.)
    env_keys = {
        'deepseek': os.environ.get('DEEPSEEK_API_KEY', ''),
        'openai': os.environ.get('OPENAI_API_KEY', ''),
        'anthropic': os.environ.get('ANTHROPIC_API_KEY', '')
    }

    for provider, env_key in env_keys.items():
        if env_key:
            config.setdefault('providers', {}).setdefault(provider, {})['api_key'] = env_key

    # Status: ist mindestens ein API-Key konfiguriert?
    api_connected = False
    for provider in config.get('providers', {}).values():
        if provider.get('api_key') and provider['api_key'] != '***hidden***':
            api_connected = True
            break

    config['api_connected'] = api_connected
    config['session_active'] = False

    # Hide API keys für Response
    for provider in config.get('providers', {}):
        if config['providers'][provider].get('api_key'):
            has_key = bool(config['providers'][provider]['api_key'])
            config['providers'][provider]['api_key'] = '***hidden***' if has_key else ''
            config['providers'][provider]['has_key'] = has_key

    return jsonify(config)

@app.route('/api/config', methods=['POST'])
@login_required
def update_api_config():
    """API-Konfiguration speichern"""
    data = request.json
    config_path = os.path.join(os.path.dirname(__file__), 'api_config.json')

    # Load existing config
    existing = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            existing = json.load(f)

    # Merge (don't overwrite hidden keys)
    for provider, settings in data.get('providers', {}).items():
        if provider not in existing.get('providers', {}):
            existing.setdefault('providers', {})[provider] = settings
        else:
            for key, value in settings.items():
                if value != '***hidden***':
                    existing['providers'][provider][key] = value

    if 'active_provider' in data:
        existing['active_provider'] = data['active_provider']

    with open(config_path, 'w') as f:
        json.dump(existing, f, indent=2)

    return jsonify({'success': True})

@app.route('/api/session-key', methods=['POST'])
@login_required
def set_session_api_key():
    """API-Key in Session speichern (pro User, nicht persistent)"""
    data = request.json
    provider = data.get('provider', 'deepseek')
    api_key = data.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API-Key fehlt'}), 400

    # In Session speichern
    session['api_provider'] = provider
    session['api_key'] = api_key
    session.modified = True

    logger.info(f"API-Key in Session gespeichert: {provider}")
    return jsonify({'success': True, 'provider': provider})

def get_session_api_key():
    """Holt API-Key aus Session oder Umgebungsvariablen"""
    # Erst Session prüfen
    if 'api_key' in session and session['api_key']:
        return session.get('api_provider', 'deepseek'), session['api_key']

    # Dann Umgebungsvariablen
    for provider, env_var in [('deepseek', 'DEEPSEEK_API_KEY'),
                               ('openai', 'OPENAI_API_KEY'),
                               ('anthropic', 'ANTHROPIC_API_KEY')]:
        key = os.environ.get(env_var, '')
        if key:
            return provider, key

    return None, None

# ============================================================
# API: PROMPTS
# ============================================================
@app.route('/api/prompts')
@login_required
def get_prompts():
    """Prompts abrufen - inkl. Standard-Prompts und Template"""
    pm = get_prompt_manager()
    custom_prompts = pm.get_all_prompts()

    # Template-Option (OHNE KI!) - wie im Original als erste Option
    template_prompt = {
        "id": "template_no_ai",
        "name": "Vorlage (ohne KI)",
        "description": "Schnelle Komplimente basierend auf Rating/Reviews - KEINE API nötig!",
        "is_template": True,  # Flag für Template-basierte Generierung
        "system_prompt": "",
        "prompt": ""
    }

    # Standard-KI-Prompts
    default_prompts = [
        {
            "id": "standard_kurz",
            "name": "Standard (Kurz & Authentisch)",
            "description": "2-3 Sätze, fokussiert auf Rating und Keywords - Benötigt KI-API",
            "is_template": False,
            "system_prompt": "Du bist ein Experte für authentische B2B-Kommunikation.",
            "prompt": """Schreibe ein kurzes, authentisches Kompliment für {name}.
Informationen:
- Rating: {rating} Sterne ({reviews} Bewertungen)
- Keywords aus Bewertungen: {review_keywords}
Schreibe NUR 2-3 Sätze. Sei authentisch, nicht übertrieben."""
        },
        {
            "id": "personalisiert",
            "name": "Personalisiert (mit Namen)",
            "description": "Personalisiert mit Vor-/Nachname wenn verfügbar - Benötigt KI-API",
            "is_template": False,
            "system_prompt": "Du bist ein Experte für personalisierte Geschäftskommunikation.",
            "prompt": """Schreibe ein persönliches Kompliment für {first_name} {last_name} von {name}.
Informationen:
- Rating: {rating} Sterne ({reviews} Bewertungen)
- Stadt: {city}
- Keywords: {review_keywords}
Sprich die Person direkt an. 2-3 Sätze, authentisch."""
        },
        {
            "id": "bewertung_fokus",
            "name": "Bewertungs-Fokus",
            "description": "Betont die guten Bewertungen und Reviews - Benötigt KI-API",
            "is_template": False,
            "system_prompt": "Du bist ein freundlicher Geschäftspartner.",
            "prompt": """Erstelle ein Kompliment für {name} basierend auf deren Bewertungen.
- {rating} Sterne Durchschnitt
- {reviews} Bewertungen
- Keywords: {review_keywords}
Betone die positiven Aspekte aus den Bewertungen. Max 3 Sätze."""
        }
    ]

    # Kombiniere: Template zuerst, dann Custom, dann Standard-KI
    all_prompts = [template_prompt]

    if custom_prompts:
        for cp in custom_prompts:
            if cp.get('id') != 'template_no_ai':
                all_prompts.append(cp)

    # Füge Standard-Prompts hinzu wenn nicht bereits vorhanden
    existing_ids = {p.get('id') for p in all_prompts}
    for dp in default_prompts:
        if dp['id'] not in existing_ids:
            all_prompts.append(dp)

    return jsonify({'prompts': all_prompts})

@app.route('/api/prompts', methods=['POST'])
@login_required
def save_prompt():
    """Prompt speichern"""
    data = request.json
    pm = get_prompt_manager()
    pm.save_prompt(data)
    return jsonify({'success': True})

# ============================================================
# API: BACKUP
# ============================================================
@app.route('/api/backup', methods=['POST'])
@login_required
def create_backup():
    """Datenbank-Backup erstellen"""
    import shutil

    db_path = os.path.join(os.path.dirname(__file__), 'data', 'lead_enrichment_v3.db')
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')

    if os.path.exists(db_path):
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(db_path, backup_path)
        return jsonify({'success': True, 'filename': backup_name})

    return jsonify({'error': 'Database not found'}), 404

# ============================================================
# API: CLEAR DATABASE
# ============================================================
@app.route('/api/leads/clear', methods=['DELETE'])
@login_required
def clear_database():
    """Alle Leads aus der Datenbank löschen"""
    session_db = db.get_session()
    try:
        count = session_db.query(CompanyV3).count()
        if count == 0:
            session_db.close()
            return jsonify({'success': True, 'deleted': 0, 'message': 'Datenbank war bereits leer'})

        session_db.query(CompanyV3).delete()
        session_db.commit()
        session_db.close()

        logger.info(f"Database cleared: {count} leads deleted")
        return jsonify({'success': True, 'deleted': count})
    except Exception as e:
        session_db.rollback()
        session_db.close()
        logger.error(f"Error clearing database: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# API: DELETE PROMPT
# ============================================================
@app.route('/api/prompts/<prompt_id>', methods=['DELETE'])
@login_required
def delete_prompt(prompt_id):
    """Einen Prompt löschen"""
    pm = get_prompt_manager()
    try:
        pm.delete_prompt(prompt_id)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting prompt: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
