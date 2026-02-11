"""
Datenmodell V3 - Branchenunabhängig mit Tag-System
Erweitert models.py um flexible Tag-Architektur
"""
import sys
import io
# Fix Windows Console Encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey, Boolean, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timezone


def utc_now():
    """Gibt aktuelle UTC-Zeit zurück (Python 3.12+ kompatibel)"""
    return datetime.now(timezone.utc)

Base = declarative_base()


# ===========================
# Tag-System für Flexibilität
# ===========================

class TagCategory(Base):
    """
    Tag-Kategorien für strukturierte Filterung

    Beispiele:
    - "industries" (Branchen)
    - "technologies" (Technologien/Tools)
    - "languages" (Sprachen)
    - "services" (Dienstleistungen)
    - "certifications" (Zertifikate)
    """
    __tablename__ = 'tag_categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)           # "Branchen", "Technologien"
    slug = Column(String(100), unique=True, nullable=False)  # "industries", "technologies"
    description = Column(Text)
    icon = Column(String(50))                            # Emoji oder Icon-Name
    is_active = Column(Boolean, default=True)

    # Sortierung und Display
    sort_order = Column(Integer, default=0)

    # Meta
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    tags = relationship("Tag", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TagCategory(slug={self.slug}, name={self.name})>"


class Tag(Base):
    """
    Einzelne Tags innerhalb einer Kategorie

    Beispiele:
    - Category "industries": "Zahnarzt", "Anwalt", "E-Commerce", "SaaS"
    - Category "technologies": "Invisalign", "Python", "React", "SAP"
    - Category "languages": "Deutsch", "Englisch", "Spanisch"
    """
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('tag_categories.id'), nullable=False, index=True)

    name = Column(String(200), nullable=False)           # "Zahnarzt", "Python", "Englisch"
    slug = Column(String(200), nullable=False, index=True)  # "zahnarzt", "python", "englisch"

    # Zusätzliche Infos
    description = Column(Text)
    synonyms = Column(JSON)                              # ["Dentist", "Zahnmedizin"]

    # Nutzungs-Statistiken
    usage_count = Column(Integer, default=0)             # Wie oft verwendet?

    # Meta
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    category = relationship("TagCategory", back_populates="tags")

    # Unique constraint: Ein Tag-Name pro Kategorie nur einmal
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

    def __repr__(self):
        return f"<Tag(name={self.name}, category={self.category.slug if self.category else 'N/A'})>"


# ===========================
# Erweiterte Company-Entity
# ===========================

class Project(Base):
    """
    Projekt - Jede CSV-Import-Datei wird einem Projekt zugeordnet.
    Dient zur Organisation und Backup-Sicherheit.
    """
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    csv_filename = Column(String(500))          # Original CSV-Dateiname
    lead_count = Column(Integer, default=0)     # Anzahl Leads
    column_cache = Column(JSON)                 # Gespeicherte Spalten-Infos (für Performance)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    companies = relationship("CompanyV3", back_populates="project", lazy="dynamic")

    def __repr__(self):
        return f"<Project(id={self.id}, name={self.name}, leads={self.lead_count})>"


class CompanyV3(Base):
    """
    Company V3 - Branchenunabhängig

    Änderungen gegenüber V2:
    - industry (String) → industries (JSON Array)
    - Neue Felder: custom_tags, attributes
    - Generischer Ansatz für alle Branchen
    """
    __tablename__ = 'companies_v3'

    id = Column(Integer, primary_key=True)

    # Projekt-Zuordnung
    project_id = Column(Integer, ForeignKey('projects.id'), index=True)
    project = relationship("Project", back_populates="companies")

    # Basis-Daten
    website = Column(String(500), index=True, default="")
    name = Column(String(255))
    description = Column(Text)
    phone = Column(String(100))                          # Telefonnummer

    # Kontakt-Person
    first_name = Column(String(100))                     # Vorname
    last_name = Column(String(100))                      # Nachname
    email = Column(String(255))                          # E-Mail

    # === FLEXIBLES BRANCHEN-SYSTEM ===
    # Statt: industry = Column(String) - nur 1 Branche
    # Neu: Array von Branchen
    main_category = Column(String(255), index=True)      # Hauptkategorie (z.B. "Maschinenbauunternehmen")
    industries = Column(JSON)                            # ["Zahnarzt", "Kieferorthopädie"] oder categories array
    sub_industries = Column(JSON)                        # ["Implantologie", "Ästhetik"]

    # === FLEXIBLE TAG-FELDER ===
    technologies = Column(JSON)                          # ["Invisalign", "DVT"] ODER ["Python", "React"]
    languages = Column(JSON)                             # ["Deutsch", "Englisch", "Spanisch"]
    services = Column(JSON)                              # Branchenspezifische Services
    certifications = Column(JSON)                        # Zertifikate

    # === GENERISCHE TAGS ===
    # Für alles, was nicht in Standard-Kategorien passt
    custom_tags = Column(JSON)                           # ["Premium", "Startup", "Remote-First"]

    # === DYNAMISCHE ATTRIBUTE ===
    # Key-Value Store für branchenspezifische Attribute
    attributes = Column(JSON)                            # {"booking_system": "Doctolib", "crm": "Salesforce"}

    # === CSV-SPEZIFISCHE FELDER ===
    place_id = Column(String(255))                       # Google Place ID
    owner_name = Column(String(255))                     # Inhaber-Name
    review_keywords = Column(Text)                       # Review-Keywords
    link = Column(String(500))                           # Google Maps Link
    query = Column(String(255))                          # Such-Query
    is_spending_on_ads = Column(Boolean)                 # Schaltet Werbung
    competitors = Column(Text)                           # Konkurrenten
    workday_timing = Column(Text)                        # Öffnungszeiten
    featured_image = Column(String(500))                 # Bild-URL
    can_claim = Column(Boolean)                          # Kann beansprucht werden
    is_temporarily_closed = Column(Boolean)              # Temporär geschlossen
    closed_on = Column(String(100))                      # Geschlossen an (Tag)
    owner_profile_link = Column(String(500))             # Inhaber-Profil Link

    # Location (wie bisher)
    country = Column(String(100), default="Deutschland", index=True)
    city = Column(String(100), index=True)
    zip_code = Column(String(20), index=True)
    state = Column(String(100))
    address = Column(Text)

    # Company attributes (wie bisher)
    employee_count = Column(Integer)
    company_size = Column(String(20))
    founded_year = Column(Integer)
    revenue_range = Column(String(50))

    # Social & Web (wie bisher)
    linkedin_url = Column(String(500))
    website_text = Column(Text)

    # Ratings (wie bisher)
    rating = Column(Float)
    review_count = Column(Integer)

    # === KOMPLIMENT-GENERIERUNG ===
    compliment = Column(Text)                            # Generiertes Kompliment
    confidence_score = Column(Integer)                   # 1-100
    overstatement_score = Column(Integer)                # 0-100
    has_team = Column(Boolean)                           # Team vorhanden?
    compliment_generated_at = Column(DateTime)           # Wann generiert?
    assigned_prompt_id = Column(String(100))             # ID des zugewiesenen Prompts

    # Meta
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    last_enriched_at = Column(DateTime)

    def __repr__(self):
        return f"<CompanyV3(id={self.id}, name={self.name}, industries={self.industries})>"


# ===========================
# Saved Filter Presets
# ===========================

class FilterPreset(Base):
    """
    Vordefinierte Filter-Sets für verschiedene Branchen

    Beispiele:
    - "Zahnärzte München Premium" → industries: ["Zahnarzt"], city: "München", technologies: ["Invisalign"]
    - "SaaS Startups Berlin" → industries: ["SaaS"], city: "Berlin", custom_tags: ["Startup"]
    """
    __tablename__ = 'filter_presets'

    id = Column(Integer, primary_key=True)

    name = Column(String(255), nullable=False)           # "Premium Zahnärzte München"
    description = Column(Text)

    # Filter-Config als JSON
    filter_config = Column(JSON, nullable=False)         # Komplette Filter-Definition

    # Kategorisierung
    category = Column(String(100))                       # "Healthcare", "Tech", "Legal"
    is_public = Column(Boolean, default=False)           # Öffentlich verfügbar?
    is_template = Column(Boolean, default=False)         # Als Template verwendbar?

    # Usage Stats
    usage_count = Column(Integer, default=0)

    # Meta
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f"<FilterPreset(name={self.name}, category={self.category})>"


# ===========================
# Database Helper V3
# ===========================

class DatabaseV3:
    """Database Connection Manager V3"""

    def __init__(self, db_path="lead_enrichment_v3.db"):
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        self.Session = sessionmaker(bind=self.engine)

    def create_all(self):
        """Erstellt alle Tabellen"""
        Base.metadata.create_all(self.engine)
        print("✅ Datenbank V3 Schema erstellt!")

    def get_session(self):
        """Gibt eine neue Session zurück"""
        return self.Session()

    def drop_all(self):
        """Löscht alle Tabellen"""
        Base.metadata.drop_all(self.engine)
        print("⚠️  Alle V3 Tabellen gelöscht!")


# ===========================
# Seed Data - Standard-Tags
# ===========================

def seed_standard_tags(db: DatabaseV3):
    """
    Erstellt Standard-Tag-Kategorien und Tags
    für verschiedene Branchen
    """
    session = db.get_session()

    try:
        # === BRANCHEN (Industries) ===
        industries_cat = TagCategory(
            name="Branchen",
            slug="industries",
            description="Geschäftsbereiche und Industrien",
            icon="🏢",
            sort_order=1
        )
        session.add(industries_cat)
        session.flush()

        industries_tags = [
            # Healthcare
            "Zahnarzt", "Arzt", "Kieferorthopäde", "Physiotherapie", "Apotheke",
            # Legal
            "Rechtsanwalt", "Notar", "Steuerberater", "Wirtschaftsprüfer",
            # Tech
            "Software-Entwicklung", "SaaS", "E-Commerce", "IT-Beratung", "Web-Agentur",
            # Services
            "Marketing-Agentur", "PR-Agentur", "Design-Studio", "Unternehmensberatung",
            # Handwerk
            "Elektriker", "Sanitär", "Bau", "Tischlerei", "Malerei",
            # Sonstige
            "Gastronomie", "Einzelhandel", "Logistik", "Immobilien", "Versicherung"
        ]

        for tag_name in industries_tags:
            tag = Tag(
                category_id=industries_cat.id,
                name=tag_name,
                slug=tag_name.lower().replace(" ", "-").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
            )
            session.add(tag)

        # === TECHNOLOGIEN (Technologies) ===
        tech_cat = TagCategory(
            name="Technologien",
            slug="technologies",
            description="Eingesetzte Technologien, Tools und Systeme",
            icon="⚙️",
            sort_order=2
        )
        session.add(tech_cat)
        session.flush()

        tech_tags = [
            # Dental (kompatibel mit alt)
            "Invisalign", "3D-Scanner", "DVT", "Laser", "CEREC", "CAD/CAM",
            # Software/Tech
            "Python", "JavaScript", "React", "Node.js", "AWS", "Docker",
            "Salesforce", "HubSpot", "SAP", "Microsoft 365",
            # Sonstige
            "CRM", "ERP", "Online-Buchung", "E-Payment"
        ]

        for tag_name in tech_tags:
            tag = Tag(
                category_id=tech_cat.id,
                name=tag_name,
                slug=tag_name.lower().replace(" ", "-").replace("/", "-")
            )
            session.add(tag)

        # === SPRACHEN (Languages) ===
        lang_cat = TagCategory(
            name="Sprachen",
            slug="languages",
            description="Gesprochene Sprachen",
            icon="🌐",
            sort_order=3
        )
        session.add(lang_cat)
        session.flush()

        lang_tags = [
            "Deutsch", "Englisch", "Französisch", "Spanisch", "Italienisch",
            "Türkisch", "Russisch", "Arabisch", "Polnisch", "Chinesisch", "Japanisch"
        ]

        for tag_name in lang_tags:
            tag = Tag(
                category_id=lang_cat.id,
                name=tag_name,
                slug=tag_name.lower()
            )
            session.add(tag)

        # === SERVICES ===
        services_cat = TagCategory(
            name="Dienstleistungen",
            slug="services",
            description="Angebotene Dienstleistungen",
            icon="🛠️",
            sort_order=4
        )
        session.add(services_cat)

        session.commit()
        print("✅ Standard-Tags erstellt!")

    except Exception as e:
        session.rollback()
        print(f"❌ Fehler beim Seed: {e}")
    finally:
        session.close()
