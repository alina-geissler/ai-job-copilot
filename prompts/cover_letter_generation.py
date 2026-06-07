"""Prompts, schemas, and rule dictionaries for LLM-based cover letter generation.

Three-call pipeline (executed after job normalisation):
    Call A  → ANALYSIS      (what is truthfully sayable)  → fit_plan (JSON)
    [Backend: check no-gos; resolve gender; select rules]
    Call B  → WRITING       (how to say it)               → letter fields (JSON)
    Call C  → VERIFICATION  (only when must_avoid is set)  → no-go report (JSON)

MODEL: gpt-5-mini recommended for all three calls.
gpt-5-mini is a reasoning model — NO temperature / top_p /
frequency_penalty / presence_penalty. Control via reasoning_effort and
verbosity. Reasoning tokens count against max_output_tokens → set generously.
Fallback gpt-4.1-mini → use *_GPT41 settings (temperature works there).

NOTE: Builder functions (build_*, resolve_*) are adapted to the project's
conventions; they illustrate the principle. Prompts, field names, and JSON
schemas must be used exactly as defined here.
"""

from __future__ import annotations

import json
import logging

from app.schemas.job_normalization import JobNormalizationSchema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model settings
# ---------------------------------------------------------------------------

MODEL = "gpt-5-mini"

ANALYSIS_SETTINGS: dict = {
    "model": MODEL,
    "reasoning": {"effort": "medium"},
    "max_output_tokens": 5000,
}
WRITING_SETTINGS: dict = {
    "model": MODEL,
    "reasoning": {"effort": "low"},
    "max_output_tokens": 4000,
}
VERIFICATION_SETTINGS: dict = {
    "model": MODEL,
    "reasoning": {"effort": "low"},
    "max_output_tokens": 2000,
}

# gpt-4.1-mini fallback (temperature-based, no reasoning)
ANALYSIS_SETTINGS_GPT41: dict    = {"model": "gpt-4.1-mini", "temperature": 0.25, "max_tokens": 1500}
WRITING_SETTINGS_GPT41: dict     = {"model": "gpt-4.1-mini", "temperature": 0.65,
                                     "frequency_penalty": 0.25, "presence_penalty": 0.0, "max_tokens": 1500}
VERIFICATION_SETTINGS_GPT41: dict = {"model": "gpt-4.1-mini", "temperature": 0.0, "max_tokens": 1000}

# Length budget: instructions in WORDS; backend validates CHARACTERS.
LENGTH_BUDGET: dict = {
    "total_words_min":                    330,
    "total_words_max":                    380,
    "total_chars_hard_max":              2300,
    "introduction_words":             "50–70",
    "main_body_qualifications_words": "120–140",
    "main_body_fit_words":             "90–110",
    "conclusion_words":                "50–60",
}


# ---------------------------------------------------------------------------
# Output language
# ---------------------------------------------------------------------------

LANGUAGE_LABELS: dict[str, str] = {"de": "Deutsch", "en": "English"}


def default_output_language(posting_language: str | None) -> str:
    """Return the UI pre-fill value for output language from the normalised job.

    :param posting_language: ISO 639-1 language code from job normalisation.
    :return: Human-readable language label, defaulting to ``"Deutsch"``.
    """
    return LANGUAGE_LABELS.get((posting_language or "de").lower(), "Deutsch")


# ---------------------------------------------------------------------------
# Tone styles (user-controlled — decoupled from INDUSTRY_RULES)
#
# Mapping industry_group → pre-selected tone (UI recommendation):
#   conservative_business   → "formell"
#   dynamic_modern          → "locker"
#   technical_scientific    → "sachlich"
#   social_health_education → "warm"
# ---------------------------------------------------------------------------

INDUSTRY_GROUP_TO_TONE: dict[str, str] = {
    "conservative_business":   "formell",
    "dynamic_modern":          "locker",
    "technical_scientific":    "sachlich",
    "social_health_education": "warm",
}

TONE_STYLES: dict[str, dict[str, str]] = {
    "formell": {
        "tone":           "sachlich, respektvoll, zurückhaltend-selbstbewusst",
        "formality":      "durchgängig Sie; hohe Formalität; klassische Bewerbungssprache",
        "sentence_style": "vollständige, klar strukturierte Sätze; konventioneller Satzbau; keine Umgangssprache",
    },
    "locker": {
        "tone":           "aktiv, energiegeladen, authentisch, nahbar – dabei professionell",
        "formality":      "Sie (sofern nicht anders erkennbar); etwas lockerer, aber kein Slang",
        "sentence_style": "lebendige, prägnante Sätze; aktive Verben; pointiert; abwechslungsreicher Rhythmus",
    },
    "sachlich": {
        "tone":           "präzise, sachlich, faktenorientiert; ruhig-souverän",
        "formality":      "Sie; sachlich-fachlich; Fachterminologie korrekt und gezielt",
        "sentence_style": "klar, logisch aufgebaut, ohne Schnörkel; Belege und Zahlen im Vordergrund",
    },
    "warm": {
        "tone":           "warm, wertschätzend, empathisch – zugleich professionell und verbindlich",
        "formality":      "Sie; freundlich-respektvoll; menschenzugewandt",
        "sentence_style": "klar und zugänglich; persönliche, aber nicht private Sprache; Sinn-/Werteorientierung",
    },
}


# ---------------------------------------------------------------------------
# Gender cascade (backend) → feeds salutation in Call B
# Returns: "male" | "female" | "unknown"
# ---------------------------------------------------------------------------

def resolve_contact_gender(job: dict | None, normalised_gender: str | None) -> str:
    """Resolve the contact person's gender through a four-step cascade.

    1. Honorific already in the data (Frau/Herr/Mr./Ms./Mrs.) → use it.
    2. LLM-extracted ``contact_person_gender`` from the normalisation call.
    3. ``gender_guesser`` offline library on the first name (commented out
       until the package is confirmed installed; activate when available).
    4. Clean unknown path: when in doubt return ``"unknown"``.
       A wrong Herr/Frau salutation is far more damaging than a neutral one.

    :param job: Raw job dict (may contain ``contact_person`` key).
    :param normalised_gender: Value from ``JobNormalizationSchema.contact_person_gender``.
    :return: ``"male"``, ``"female"``, or ``"unknown"``.
    """
    contact = (job or {}).get("contact_person") or ""
    low = contact.lower()

    # Step 1: honorific in raw data
    if "frau" in low or " ms." in low or " mrs" in low:
        return "female"
    if "herr" in low or " mr." in low:
        return "male"

    # Step 2: normalisation LLM result
    if normalised_gender in ("male", "female"):
        return normalised_gender

    # Step 3: gender_guesser offline library (uncomment when package is installed)
    # import gender_guesser.detector as gd
    # first_name = contact.split()[0] if contact else ""
    # if first_name:
    #     g = gd.Detector(case_sensitive=False).get_gender(first_name)
    #     if g == "male":   return "male"
    #     if g == "female": return "female"

    # Step 4: clean unknown fallback
    return "unknown"


# ---------------------------------------------------------------------------
# Call A — Analysis
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM = """\
Du bist ein erfahrener Karriereberater und Recruiter. Deine Aufgabe ist NICHT,
ein Anschreiben zu schreiben, sondern eine sachliche, wahrheitsgetreue
Eignungs-Analyse zu erstellen, die ein zweiter Schritt zum Schreiben nutzt.

Oberstes Prinzip: WAHRHEIT. Du erfindest nichts. Du leitest jede Aussage aus
den Daten ab (normalisierte Stelle, Bewerberprofil, optionale Zusatzangaben).
Was die Daten nicht hergeben, markierst du als fehlend (null) statt es zu
erfinden. Liegen Zusatzangaben des Bewerbers vor, haben sie Vorrang vor dem
Profil – besonders bei Widersprüchen.
"""

ANALYSIS_PROMPT = """\
Analysiere die Passung zwischen Stelle und Bewerber und gib ausschließlich
gültiges JSON nach dem vorgegebenen Schema zurück.

# DATEN
## Normalisierte Stelle
{job}

## Bewerberprofil
{profile}

## Optionale Zusatzangaben des Bewerbers (haben Vorrang vor dem Profil!)
{extra_details}

## Unternehmenskontext
{company_context}

# WAS DU LIEFERST
1. supported_ats_keywords: Nur action_verbs / ats_priority_keywords /
   domain_keywords aus der Stelle, die durch das Profil WAHRHEITSGEMÄSS gedeckt
   sind. Exakte Schreibweise beibehalten. Lieber wenige echte als viele behauptete.
2. missing_requirements: must_have_competencies / hard_requirements, die der
   Bewerber NICHT erfüllt. Pro Eintrag eine Strategie wählen:
     - "interface": Schnittstellen-/Kollaborationsbezug.
     - "goal": Zukunfts-/Zielbezug (logischer nächster Schritt).
     - "theory": theoretisch bekannt (Studium/Weiterbildung), noch nicht angewandt.
     - "transferable": übertragbare Fähigkeiten aus anderem Kontext.
     - "willingness_to_learn": Lernbereitschaft statt Erfahrung (Einsteiger).
   reframing_note: kurze, konkrete Idee (KEIN fertiger Satz). NIEMALS behaupten,
   eine fehlende Anforderung sei erfüllt; nicht defensiv entschuldigen.
3. evidence_points: 2–4 konkrete Belege aus work_experience / projects /
   hard_skills mit echten Zahlen/Resultaten (figures). Nur was in den Daten steht.
4. company_fit_angle: Warum passt der Bewerber zu DIESEM Unternehmen?
5. candidate_value_proposition: Welcher konkrete Mehrwert?
6. must_include: aus Zusatzangaben (Must-haves) wörtlich übernommene Punkte,
   die zwingend vorkommen müssen. Sonst [].
7. must_avoid: aus Zusatzangaben (No-Gos) Punkte, die unter keinen Umständen
   vorkommen dürfen. Formuliere jeden Punkt als den DAHINTERLIEGENDEN FAKT/das
   Thema – nicht nur die wörtliche Formulierung des Nutzers. Sonst [].
8. salary_line / start_date_line: nur wenn die Stelle danach fragt
   (application_instructions) ODER der Bewerber Angaben macht; sonst null.
   Niemals die Gehaltsspanne des Unternehmens zitieren.
9. notes: Auffälligkeiten (z. B. Wunsch-Arbeitsmodell vs. Stelle), sonst null.

Felder, die in den Daten fehlen: null bzw. leere Liste. Nichts erfinden.
"""

ANALYSIS_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "cover_letter_fit_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "supported_ats_keywords": {"type": "array", "items": {"type": "string"}},
                "missing_requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "requirement":    {"type": "string"},
                            "strategy":       {"type": "string", "enum": [
                                "interface", "goal", "theory",
                                "transferable", "willingness_to_learn"]},
                            "reframing_note": {"type": "string"},
                        },
                        "required": ["requirement", "strategy", "reframing_note"],
                    },
                },
                "evidence_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "claim":        {"type": "string"},
                            "source_field": {"type": "string"},
                            "figures":      {"type": ["string", "null"]},
                        },
                        "required": ["claim", "source_field", "figures"],
                    },
                },
                "company_fit_angle":           {"type": ["string", "null"]},
                "candidate_value_proposition": {"type": ["string", "null"]},
                "must_include": {"type": "array", "items": {"type": "string"}},
                "must_avoid":   {"type": "array", "items": {"type": "string"}},
                "salary_line":     {"type": ["string", "null"]},
                "start_date_line": {"type": ["string", "null"]},
                "notes":           {"type": ["string", "null"]},
            },
            "required": [
                "supported_ats_keywords", "missing_requirements", "evidence_points",
                "company_fit_angle", "candidate_value_proposition",
                "must_include", "must_avoid",
                "salary_line", "start_date_line", "notes"],
        },
    },
}


# ---------------------------------------------------------------------------
# Call B — Writing
# ---------------------------------------------------------------------------

WRITING_SYSTEM = """\
Du bist ein erfahrener Bewerbungs- und Karriereexperte und schreibst
überzeugende, individuelle Anschreiben auf Muttersprachenniveau. Du kennst
die Prinzipien wirksamer, ATS-optimierter Bewerbungen und schreibst
glaubwürdig, präzise und ohne Floskeln. Du erfindest niemals Fakten und
hältst dich strikt an die übergebene Eignungs-Analyse und die Regeln.
"""

WRITING_TASK = """\
Aufgabe: Verfasse aus der Eignungs-Analyse, den Stellen-/Profildaten und den
Regeln ein vollständiges Anschreiben und gib es ausschließlich als gültiges
JSON nach dem Schema zurück.

Ziel: ein ATS-optimiertes, glaubwürdiges, NICHT generisches Anschreiben, das
eine klare Eignung für die Rolle zeigt, relevante Keywords der Stelle natürlich
einbindet und NICHT bloß den Lebenslauf wiederholt.

AUSGABESPRACHE: {target_language}. Schreibe das gesamte Anschreiben
ausschließlich in dieser Sprache – kein einziges Wort in einer anderen Sprache.
ALLE JSON-Feldnamen bleiben englisch und dürfen nicht übersetzt werden.
Verwende korrekte Orthografie der Ausgabesprache; bei Deutsch echte Umlaute
(ä, ö, ü) und ß – niemals Ersatzschreibweisen wie ae/oe/ue/ss.
Die Beispielphrasen und das Vokabular in den industry_rules sind Stilanker, die
Register und Absicht zeigen: Ist die Ausgabesprache nicht Deutsch, übernimm NUR
die Absicht und formuliere idiomatisch in der Ausgabesprache – niemals wörtlich
übersetzen oder fremdsprachige Wendungen einstreuen.

Länge: Das Anschreiben muss auf eine A4-Seite passen; durch das Layout ist der
Platz deutlich kleiner als eine voll mit Text gefüllte Seite. Zielumfang
insgesamt {total_words_min}–{total_words_max} Wörter:
  - introduction:             {introduction_words} Wörter
  - main_body_qualifications: {main_body_qualifications_words} Wörter
  - main_body_fit:            {main_body_fit_words} Wörter
  - conclusion:               {conclusion_words} Wörter
Lieber etwas kürzer als zu lang.
"""

WRITING_GLOBAL_RULES = """\
GLOBALE REGELN
- Wahrheit: Keine erfundenen Erfahrungen, Fähigkeiten, Zahlen oder Abschlüsse.
  Nutze ausschließlich die Eignungs-Analyse und die Daten.
- Zusatzangaben des Bewerbers haben Vorrang vor dem Profil (bei Widersprüchen).
- must_include (aus der Analyse) MUSS vorkommen. must_avoid darf unter KEINEN
  Umständen vorkommen – weder wörtlich noch sinngemäß/angedeutet. Erwähne den
  dahinterliegenden Fakt in keiner Form.
- ATS: Verwende supported_ats_keywords mit EXAKTER Schreibweise, aber natürlich
  und nur wo passend. Niemals Keywords auflisten oder stapeln.
- Fehlende Anforderungen (missing_requirements): NICHT behaupten, sie seien
  erfüllt; aber auch nicht verstecken oder defensiv entschuldigen. Setze die
  vorgegebene Strategie ein und mache daraus ein strategisches Verkaufsargument.
- Fehlende Informationen: vorsichtig und allgemein plausibel formulieren statt
  etwas zu erfinden. Leere Felder einfach weglassen – kein „nicht angegeben",
  keine Platzhalter.
- Kein typischer KI-Stil, keine generischen Standardfloskeln (z. B. NICHT
  „Hiermit bewerbe ich mich um die Stelle als …"). Variiere Satzbau und
  Rhythmus, klinge menschlich und individuell.
- Fließtext OHNE Aufzählungszeichen/Stichpunkte. Keine Wiederholungen.
- Wiederhole nicht den Lebenslauf; verknüpfe Belege mit den Kernanforderungen.
- Achte besonders auf korrekte Rechtschreibung und Zeichensetzung.
- Durchgängig „Sie" (sofern die Tonalitätsregeln nichts anderes ergeben).
- Beachte den TONALITÄTSSTIL (Ton, Formalität, Satzbau – aus Nutzerauswahl;
  hat Vorrang) sowie die industry_rules (Schwerpunkte, Positionierung,
  Vokabular, No-Gos) und hierarchy_rules (Argumentationsebene).

FELD-SPEZIFISCHE REGELN (Output)
- subject_line: „Bewerbung als" + Jobtitel, OHNE Genderzusatz wie „(m/w/d)".
  Die Referenznummer steht NICHT hier (macht das Backend separat).
- salutation: Nutze das vom Backend übergebene contact_person_gender. Leite
  das Geschlecht NICHT selbst aus dem Namen ab.
    - "male"    → „Sehr geehrter Herr {Nachname},"
    - "female"  → „Sehr geehrte Frau {Nachname},"
    - "unknown" bei vorhandenem Ansprechpartner → korrekte neutrale Anrede ohne
      geratenes Herr/Frau.
    - kein Ansprechpartner → KEINE „Sehr geehrte Damen und Herren" und NICHT
      wörtlich „Sehr geehrtes Recruiting-Team"; wähle eine passende,
      professionelle, an das Team/die Personalabteilung gerichtete Alternative.
- introduction: konkrete Rolle, ggf. Fundort der Anzeige, ein prägnanter
  Einstiegssatz zur Motivation und/oder aktuellen Situation. Kein Standardsatz.
- main_body_qualifications: Fähigkeiten/Stärken mit den Kernanforderungen
  verknüpfen; konkrete Beispiele (Zahlen, Erfolge) als Beleg der Eignung.
- main_body_fit: Warum passt das Unternehmen? Was will der Bewerber beitragen?
  Welchen Mehrwert bietet er? (Motivation/Passung.)
  → Beide main_body-Felder OHNE Überschrift, je ein fließender Absatz.
- conclusion: Gehaltsvorstellung und frühester Eintrittstermin nur, wenn in der
  Analyse vorhanden (salary_line / start_date_line); ein einprägsamer
  Schlusssatz zur Motivation; ein selbstbewusster, NICHT bittender Hinweis auf
  ein Gespräch (z. B. „Ich freue mich auf ein persönliches Gespräch.").
"""

FIELD_EXPLANATIONS = """\
ERKLÄRUNG DER FELDER (viele können leer sein – dann ignorieren, nichts
erfinden, keine Platzhalter)

EINGABE – Normalisierte Stelle (relevante Felder):
- canonical_job_title → subject_line (ohne Genderzusatz) und Einleitungsbezug.
- role_summary / responsibilities / core_tasks → Anknüpfung für Qualifikation.
- must_have_competencies / hard_requirements → Belege zuordnen; sonst Strategie.
- nice_to_have_competencies / preferred_requirements → Pluspunkte, optional.
- tools_systems_equipment / methods_processes_standards → konkret benennen, wenn
  beim Bewerber vorhanden.
- ats_priority_keywords / action_verbs / domain_keywords → nur die in
  supported_ats_keywords gelisteten, exakt und natürlich einbauen.
- business_goals / success_signals → Motivation/Passung.
- application_instructions → ob Gehalt/Eintrittstermin erwartet wird.
- posting_language → Vorbelegung der Ausgabesprache (vom Nutzer überschreibbar).

EINGABE – Bewerberprofil:
- work_experience / projects / hard_skills → primäre Belegquellen (mit Zahlen).
- education / certifications / courses → Qualifikationen, auch für theory-Strategie.
- soft_skills / volunteering / languages → unterstützend.
- honors_awards / publications → sparsam, nur als Zusatzglaubwürdigkeit.
- target_role / seniority_level / leadership_experience / salary_expectation /
  availability / work_model / employment_types → Abgleich mit der Stelle.

EINGABE – Optionale Zusatzangaben (Vorrang vor Profil!):
- Must-haves / No-Gos (→ must_include / must_avoid), persönliche Motivation,
  Grund für das Unternehmen, Mehrwert, Eintrittstermin, Gehaltsvorstellung.

EINGABE – company_context: Mission, Produkte, Kultur, Fakten → Passung;
nicht 1:1 abschreiben.

EINGABE – contact_person_gender: vom Backend ("male"/"female"/"unknown") →
nur für die salutation; nicht selbst aus dem Namen ableiten.

EINGABE – tone_style: Ton, Formalität und Satzbau aus der Nutzerauswahl
(„formell"/„locker"/„sachlich"/„warm") – hat Vorrang gegenüber industrie-
spezifischen Stilangaben.

AUSGABE (genau diese Felder, englische Namen, Werte in {target_language}):
- subject_line, salutation, introduction, main_body_qualifications,
  main_body_fit, conclusion
  (Adressblock, Empfänger und Referenznummer erzeugt das Backend separat.)
"""

WRITING_PROMPT = """\
{task}

{global_rules}

{field_explanations}

# TONALITÄTSSTIL (Nutzerauswahl – hat Vorrang; Ton, Formalität, Satzbau)
{tone_style}

# BRANCHENREGELN (weitere Stilaspekte: Schwerpunkte, Positionierung, Vokabular) – industry_rules
{industry_rules}

# HIERARCHIEREGELN (Argumentationsebene) – hierarchy_rules
{hierarchy_rules}

# EIGNUNGS-ANALYSE (verbindliche Grundlage) – fit_plan
{fit_plan}

# KONTEXTDATEN
## Ansprechpartner-Geschlecht (vom Backend, nur für salutation)
{contact_person_gender}
## Stelle
{job}
## Profil
{profile}
## Zusatzangaben
{extra_details}
## Unternehmenskontext
{company_context}

Gib ausschließlich gültiges JSON nach dem Schema zurück.
"""

WRITING_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "cover_letter",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "subject_line":              {"type": "string"},
                "salutation":                {"type": "string"},
                "introduction":              {"type": "string"},
                "main_body_qualifications":  {"type": "string"},
                "main_body_fit":             {"type": "string"},
                "conclusion":                {"type": "string"},
            },
            "required": [
                "subject_line", "salutation", "introduction",
                "main_body_qualifications", "main_body_fit", "conclusion"],
        },
    },
}


# ---------------------------------------------------------------------------
# Call C — Verification (only when fit_plan["must_avoid"] is non-empty)
# ---------------------------------------------------------------------------

VERIFICATION_SYSTEM = """\
You are a strict compliance checker for cover letters. The letter may be written
in German or English. For each forbidden item you receive, decide whether the
letter reveals, states, OR implies the UNDERLYING FACT/topic behind it – not just
the literal wording the user used. Catch paraphrases, euphemisms, and indirect
allusions (e.g. a forbidden "2-year employment gap" is violated by "after some
time away from the workforce" or by date ranges that expose the gap). Be
conservative: if the letter plausibly alludes to the fact, mark it violated.
Output only valid JSON per the schema.
"""

VERIFICATION_PROMPT = """\
# COVER LETTER (full text)
{letter_text}

# FORBIDDEN ITEMS (must NOT appear, in meaning or wording)
{must_avoid}

For EACH forbidden item, return an object:
- no_go: the item text
- violated: true if the letter reveals/states/implies the underlying fact, else false
- evidence: the exact offending sentence/phrase from the letter, or null if not violated
"""

VERIFICATION_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "no_go_report",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "no_go":     {"type": "string"},
                            "violated":  {"type": "boolean"},
                            "evidence":  {"type": ["string", "null"]},
                        },
                        "required": ["no_go", "violated", "evidence"],
                    },
                },
            },
            "required": ["checks"],
        },
    },
}


# ---------------------------------------------------------------------------
# Industry matrix — lookup by industry_group
# NOTE: tone, formality, and sentence_style are NOT here; they come from
# TONE_STYLES (user-controlled).
# ---------------------------------------------------------------------------

INDUSTRY_RULES: dict[str, dict] = {
    "conservative_business": {
        "key_emphasis": [
            "Verlässlichkeit", "Loyalität", "Fachkompetenz",
            "Diskretion", "Verantwortungsbewusstsein", "belegbare Ergebnisse",
        ],
        "acceptable_self_positioning": (
            "Leistungen faktenbasiert und belegt; Understatement vor Selbstanpreisung"
        ),
        "lexicon_preferred": [
            "fundiert", "verantwortungsvoll", "sorgfältig", "nachhaltig",
            "zuverlässig", "strukturiert", "langfristig",
        ],
        "lexicon_avoid": [
            "modische Buzzwords", "Anglizismen-Häufung",
            "übertriebene Superlative", "Disruption/Game-Changer",
        ],
        "no_gos": [
            "saloppe Ansprache", "Humor", "Selbstüberhöhung",
            "Duzen", "Schlagwörter ohne Substanz",
        ],
        "example_opening": (
            "Mit großem Interesse habe ich Ihre Ausschreibung für die Position als … gelesen."
        ),
        "example_closing": (
            "Über die Gelegenheit zu einem persönlichen Gespräch würde ich mich sehr freuen."
        ),
    },
    "dynamic_modern": {
        "key_emphasis": [
            "Gestaltungswille", "Eigeninitiative", "Lernkurve/Tempo",
            "Wirkung/Impact", "Teamfähigkeit", "Hands-on-Mentalität",
        ],
        "acceptable_self_positioning": (
            "selbstbewusster Auftritt erlaubt; Begeisterung zeigen; "
            "konkrete Wirkung statt Floskeln"
        ),
        "lexicon_preferred": [
            "gestalten", "vorantreiben", "Verantwortung übernehmen",
            "Wirkung", "umsetzen", "Eigeninitiative", "Neugier",
        ],
        "lexicon_avoid": [
            "steif-bürokratische Floskeln", "Behördendeutsch",
            "leere Buzzwords ohne Beleg", "aufgesetzte Coolness",
        ],
        "no_gos": [
            "gestelzte Amtssprache", "reine Phrasen", "Übertreibung ohne Substanz",
        ],
        "example_opening": "Was mich an … reizt: …",
        "example_closing": (
            "Ich freue mich darauf, Ihnen meine Ideen in einem persönlichen Gespräch "
            "vorzustellen."
        ),
    },
    "technical_scientific": {
        "key_emphasis": [
            "methodische Kompetenz", "Problemlösung", "Tools/Technologien",
            "messbare Ergebnisse", "Genauigkeit", "Domänenwissen",
        ],
        "acceptable_self_positioning": (
            "Kompetenz über Nachweise (Projekte, Kennzahlen, Technologien) statt Adjektive"
        ),
        "lexicon_preferred": [
            "entwickelt", "implementiert", "optimiert", "analysiert",
            "methodisch", "skalierbar", "reproduzierbar", "konkrete Tool-/Verfahrensnamen",
        ],
        "lexicon_avoid": [
            "vage Adjektive ohne Beleg", "Marketing-Sprech",
            "emotionale Übertreibung", "unbelegte Superlative",
        ],
        "no_gos": [
            "schwammige Aussagen", "falsch verwendete Fachbegriffe",
            "Übertreibung technischer Fähigkeiten", "Marketing-Floskeln",
        ],
        "example_opening": (
            "Mit meiner Erfahrung in … und fundierten Kenntnissen in … passe ich gut "
            "auf die Anforderungen der Position als … ."
        ),
        "example_closing": (
            "Gerne erläutere ich Ihnen meine fachliche Eignung in einem persönlichen Gespräch."
        ),
    },
    "social_health_education": {
        "key_emphasis": [
            "Verantwortungsbewusstsein", "Empathie", "Zuverlässigkeit",
            "Teamarbeit", "Werte-/Sinnorientierung", "Belastbarkeit",
            "Engagement für Menschen",
        ],
        "acceptable_self_positioning": (
            "Motivation und Haltung dürfen sichtbar sein; "
            "Leistung mit Wirkung auf Menschen verbinden"
        ),
        "lexicon_preferred": [
            "begleiten", "unterstützen", "fördern", "verantwortungsvoll",
            "wertschätzend", "im Team", "Engagement", "Sinn",
        ],
        "lexicon_avoid": [
            "kühle Profit-/Effizienzsprache als Hauptfokus",
            "übertriebene Selbstdarstellung", "Distanz/Technokratie",
            "leere Empathie-Floskeln",
        ],
        "no_gos": [
            "rein leistungs-/profitgetriebene Argumentation",
            "Kälte/Distanz", "Pathos ohne Substanz",
            "Herablassung gegenüber Zielgruppen",
        ],
        "example_opening": (
            "Die Arbeit mit … liegt mir besonders am Herzen, daher hat mich Ihre "
            "Ausschreibung als … sofort angesprochen."
        ),
        "example_closing": (
            "Ich würde mich sehr freuen, Sie und Ihr Team in einem persönlichen "
            "Gespräch kennenzulernen."
        ),
    },
}


# ---------------------------------------------------------------------------
# Hierarchy matrix — lookup by hierarchy_level
# ---------------------------------------------------------------------------

HIERARCHY_RULES: dict[str, dict] = {
    "entry_junior": {
        "argument_structure": (
            "Potenzial-/Lernfokus; Studium, Praktika, Projekte und erste Erfahrungen "
            "nach vorn; Anforderungen mit übertragbaren Belegen verknüpfen"
        ),
        "strategic_focus": (
            "Lernbereitschaft, Motivation, schnelle Einarbeitung, vorhandene Grundlagen; "
            "Lücken über Lernwille/Theoriewissen/übertragbare Fähigkeiten ausgleichen"
        ),
        "leverage_types": [
            "Studien-/Abschlussprojekte", "Praktika & Werkstudententätigkeit",
            "relevante Kurse/Zertifikate", "Engagement/Ehrenamt",
            "schnelle Auffassungsgabe",
        ],
        "opening_line_style": "Motivation + Bezug zur Rolle; frische Energie ohne Anbiederung",
        "balance": {"motivation": "hoch", "evidence": "mittel", "leadership_strategy": "minimal"},
        "proof_expectations": (
            "konkrete Belege aus Studium/Praktika/Projekten (Projektergebnisse, eingesetzte "
            "Tools, ggf. starke Noten) statt langjähriger Berufserfahrung; keine erfundenen "
            "Berufsjahre"
        ),
        "no_gos": [
            "Führungsanspruch behaupten", "Überheblichkeit",
            "reine Theorie ohne Anwendungsbezug",
            "sich kleinmachen/entschuldigen für fehlende Erfahrung",
        ],
    },
    "professional_senior": {
        "argument_structure": (
            "Ergebnis-/Erfahrungsfokus; relevante Stationen und messbare Erfolge "
            "mit den Kernanforderungen verzahnen"
        ),
        "strategic_focus": (
            "nachgewiesene Fachkompetenz, Eigenverantwortung, konkrete Resultate; "
            "Lücken über transferierbare Erfahrung/Schnittstellenkompetenz ausgleichen"
        ),
        "leverage_types": [
            "messbare Erfolge & Kennzahlen", "Fach-/Methodenkompetenz",
            "Projekt-/Prozessverantwortung", "Branchen-/Domänenwissen",
            "Schnittstellenarbeit",
        ],
        "opening_line_style": "souveräner Bezug von Erfahrung zur Rolle; klarer Mehrwert",
        "balance": {"motivation": "mittel", "evidence": "hoch",
                    "leadership_strategy": "mittel (sofern die Rolle es erfordert)"},
        "proof_expectations": (
            "konkrete Resultate mit Zahlen/Kontext (z. B. Umsatz um X % gesteigert, "
            "Team von Y geführt, Prozess um Z verkürzt); Verantwortungsumfang sichtbar machen"
        ),
        "no_gos": [
            "bloße Aufgabenaufzählung wie im Lebenslauf", "Floskeln ohne Beleg",
            "übertriebene Bescheidenheit", "unbelegte Führungsbehauptungen",
        ],
    },
    "executive_c_level": {
        "argument_structure": (
            "Wirkungs-/Strategiefokus; Vision, Verantwortungsumfang, geschäftlicher Impact "
            "und Führung an die Spitze; weniger operative Details"
        ),
        "strategic_focus": (
            "strategischer Beitrag, P&L-/Budget-/Teamverantwortung, "
            "Transformation/Wachstum, Stakeholder-Management; Passung zu den Unternehmenszielen"
        ),
        "leverage_types": [
            "geschäftlicher Impact (Umsatz, Marge, Wachstum)",
            "Führungs-/Organisationsverantwortung (Teamgröße, Budget)",
            "strategische Initiativen/Transformation",
            "Stakeholder-/Boardarbeit", "Marktwissen",
        ],
        "opening_line_style": (
            "souverän, strategisch, auf Augenhöhe; Bezug zwischen eigener Wirkung "
            "und Unternehmenszielen"
        ),
        "balance": {"motivation": "mittel",
                    "evidence": "hoch (auf Ergebnis-/Führungsebene)",
                    "leadership_strategy": "hoch"},
        "proof_expectations": (
            "Ergebnisse auf Unternehmens-/Bereichsebene (Verantwortungsumfang, Budget/"
            "Teamgröße, strategische Resultate); Diskretion bei sensiblen Zahlen wahren"
        ),
        "no_gos": [
            "operative Kleinteiligkeit", "Bittsteller-Ton",
            "Aufzählung von Detailaufgaben", "Übertreibung von Verantwortung",
            "Indiskretion zu früheren Arbeitgebern",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_ALWAYS_SEND = frozenset({
    "canonical_job_title", "role_summary", "company_name", "responsibilities",
    "core_tasks", "must_have_competencies", "nice_to_have_competencies",
    "tools_systems_equipment", "methods_processes_standards", "hard_requirements",
    "preferred_requirements", "years_of_experience_required",
    "type_of_experience_required", "education_requirements", "certifications_required",
    "language_requirements", "soft_skills", "domain_keywords", "ats_priority_keywords",
    "action_verbs", "business_goals", "success_signals", "application_instructions",
    "posting_language",
})

_SEND_WHEN_NONEMPTY = frozenset({
    "department_function", "job_title_variants", "preferred_certifications",
    "licences_authorisations_required", "regulatory_compliance_requirements",
    "benefits_perks", "salary_range", "work_model", "job_location", "employment_type",
})


def _j(x: object) -> str:
    """Serialise ``x`` to compact JSON, returning ``"(leer)"`` for falsy values.

    :param x: Value to serialise.
    :return: JSON string or ``"(leer)"``.
    """
    return json.dumps(x, ensure_ascii=False) if x else "(leer)"


def filter_job_for_llm(norm: JobNormalizationSchema) -> dict:
    """Return a trimmed job dict containing only the fields the LLM should see.

    Fields that drove rule selection (``industry_group``, ``hierarchy_level``)
    and backend-only fields (``contact_person``, ``company_street``, etc.) are
    excluded. Trimming keeps the model focused and reduces hallucination risk.

    :param norm: Normalised job schema instance.
    :return: Dict with always-send fields and non-empty conditional fields.
    """
    raw = norm.model_dump()
    result: dict = {}
    for field in _ALWAYS_SEND:
        result[field] = raw.get(field)
    for field in _SEND_WHEN_NONEMPTY:
        val = raw.get(field)
        if val:
            result[field] = val
    return result


def build_analysis_messages(
    job: dict,
    profile: dict,
    extra_details: dict,
    company_context: str,
) -> list[dict]:
    """Build the message list for Call A (Analysis).

    :param job: Filtered job dict from :func:`filter_job_for_llm`.
    :param profile: LLM-safe candidate profile dict.
    :param extra_details: Optional personalisation fields from the setup form.
    :param company_context: Company background text (may be empty).
    :return: List of ``{"role": ..., "content": ...}`` dicts.
    """
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {"role": "user", "content": ANALYSIS_PROMPT.format(
            job=_j(job),
            profile=_j(profile),
            extra_details=_j(extra_details),
            company_context=_j(company_context) if company_context else "(leer)",
        )},
    ]


def build_writing_messages(
    fit_plan: dict,
    job: dict,
    profile: dict,
    extra_details: dict,
    company_context: str,
    *,
    industry_group: str,
    hierarchy_level: str,
    tone_key: str,
    output_language: str = "Deutsch",
    contact_person_gender: str = "unknown",
) -> list[dict]:
    """Build the message list for Call B (Writing).

    :param fit_plan: Analysis result from Call A.
    :param job: Filtered job dict from :func:`filter_job_for_llm`.
    :param profile: LLM-safe candidate profile dict.
    :param extra_details: Optional personalisation fields.
    :param company_context: Company background text (may be empty).
    :param industry_group: One of the four ``INDUSTRY_RULES`` keys.
    :param hierarchy_level: One of the three ``HIERARCHY_RULES`` keys.
    :param tone_key: User-selected tone; one of the four ``TONE_STYLES`` keys.
    :param output_language: Human-readable language name (e.g. ``"Deutsch"``).
    :param contact_person_gender: ``"male"``, ``"female"``, or ``"unknown"``.
    :return: List of ``{"role": ..., "content": ...}`` dicts.
    """
    task = WRITING_TASK.format(target_language=output_language, **LENGTH_BUDGET)
    field_expl = FIELD_EXPLANATIONS.format(target_language=output_language)
    user_content = WRITING_PROMPT.format(
        task=task,
        global_rules=WRITING_GLOBAL_RULES,
        field_explanations=field_expl,
        tone_style=_j(TONE_STYLES[tone_key]),
        industry_rules=_j(INDUSTRY_RULES[industry_group]),
        hierarchy_rules=_j(HIERARCHY_RULES[hierarchy_level]),
        fit_plan=_j(fit_plan),
        contact_person_gender=contact_person_gender,
        job=_j(job),
        profile=_j(profile),
        extra_details=_j(extra_details),
        company_context=_j(company_context) if company_context else "(leer)",
    )
    return [
        {"role": "system", "content": WRITING_SYSTEM},
        {"role": "user",   "content": user_content},
    ]


def build_verification_messages(
    letter_fields: dict,
    must_avoid: list[str],
) -> list[dict]:
    """Build the message list for Call C (Verification).

    Only call this when ``must_avoid`` is non-empty.

    :param letter_fields: Dict of generated letter fields from Call B.
    :param must_avoid: List of forbidden topics/facts from the fit plan.
    :return: List of ``{"role": ..., "content": ...}`` dicts.
    """
    order = ["subject_line", "salutation", "introduction",
             "main_body_qualifications", "main_body_fit", "conclusion"]
    letter_text = "\n\n".join(str(letter_fields.get(k, "")) for k in order)
    return [
        {"role": "system", "content": VERIFICATION_SYSTEM},
        {"role": "user",   "content": VERIFICATION_PROMPT.format(
            letter_text=letter_text,
            must_avoid=_j(must_avoid),
        )},
    ]
