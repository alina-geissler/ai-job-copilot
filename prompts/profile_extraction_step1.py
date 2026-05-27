"""Versioned system prompts for CV text reconstruction (pipeline step 1).

Step 1 receives raw CV text and returns it as clean, structured plain text
grouped by section. The output is passed to step 2 for JSON mapping.

Add a new key for each iteration. Never remove old versions — they are the
audit trail. Bump STEP1_PROMPT_VERSION in app/services/profile_extraction.py
to activate a new version.
"""

VERSIONS: dict[str, str] = {
    "step1_v1": """\
You are a CV text reconstruction assistant. Read the provided CV text and rewrite it as clean, 
well-structured plain text grouped by section (e.g. Personal Information, Work Experience, Education, Skills, Languages,
Certifications, Projects, Volunteering, Publications, Honors & Awards, Preferences).
Preserve all information exactly as found — do not add, remove, or infer any details."""
}
