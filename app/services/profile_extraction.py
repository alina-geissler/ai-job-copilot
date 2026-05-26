"""Extract structured candidate profile from CV text using Ollama via the OpenAI SDK.

Send the extracted CV text to a locally running Ollama instance and parse the
response into a CandidateProfile using client.beta.chat.completions.parse.
The SDK converts the LLM JSON response to a CandidateProfile instance
automatically — no manual JSON parsing is required for the LLM output path.
"""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from app.core.config import settings
from app.schemas.profile import CandidateProfile
from prompts.profile_extraction import VERSIONS

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"  # change this to switch the active prompt version
_SYSTEM_PROMPT = VERSIONS[PROMPT_VERSION]


def extract_profile_from_cv_text(cv_text: str) -> tuple[CandidateProfile, str]:
    """Call Ollama to parse CV text into a structured CandidateProfile.

    Uses client.beta.chat.completions.parse with response_format=CandidateProfile.
    The SDK serialises the schema to JSON Schema, sends it to the model, and
    deserialises the response back to a CandidateProfile instance automatically.

    :param cv_text: Raw extracted CV text (Markdown or plain text).
    :return: Tuple of (parsed CandidateProfile, active prompt version string).
    :raises openai.OpenAIError: If the LLM request fails.
    """
    client = OpenAI(
        base_url=settings.llm_api_url,
        api_key="ollama",
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
    )
    completion = client.beta.chat.completions.parse(
        model=settings.llm_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": cv_text},
        ],
        response_format=CandidateProfile,
    )
    return completion.choices[0].message.parsed, PROMPT_VERSION
