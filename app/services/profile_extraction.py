"""Extract structured candidate profile from CV text using a two-step LLM pipeline.

Step 1: the LLM receives raw CV text and reconstructs it as clean, grouped
plain text (text-only completion, no schema).

Step 2: the LLM maps the step 1 output to a CandidateProfile using structured
output via client.beta.chat.completions.parse.

Both calls share the same OpenAI client instance to avoid redundant setup.
"""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from app.core.config import settings
from app.schemas.profile import CandidateProfile
from prompts.profile_extraction import VERSIONS as STEP2_VERSIONS
from prompts.profile_extraction_step1 import VERSIONS as STEP1_VERSIONS

logger = logging.getLogger(__name__)

STEP1_PROMPT_VERSION = "step1_v1"
_STEP1_SYSTEM_PROMPT = STEP1_VERSIONS[STEP1_PROMPT_VERSION]

STEP2_PROMPT_VERSION = "step2_v3"
_STEP2_SYSTEM_PROMPT = STEP2_VERSIONS[STEP2_PROMPT_VERSION]


def _build_client() -> OpenAI:
    """Create a configured OpenAI client pointed at the active LLM endpoint.

    :return: Configured OpenAI client instance.
    """
    return OpenAI(
        # base_url=settings.llm_api_url,
        base_url=settings.openrouter_api_url,  # for testing
        # api_key="ollama",
        api_key=settings.openrouter_api_key,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
    )


def _call_step1(client: OpenAI, cv_text: str) -> str:
    """Reconstruct raw CV text as clean, grouped plain text.

    Sends the raw CV text to the LLM with a text-reconstruction prompt and
    returns the plain-text response. No structured output format is enforced.

    :param client: Configured OpenAI client.
    :param cv_text: Raw extracted CV text (Markdown or plain text).
    :return: Reconstructed plain text grouped by section.
    :raises openai.OpenAIError: If the LLM request fails.
    """
    completion = client.chat.completions.create(
        # model=settings.llm_model,
        model="qwen/qwen-2.5-7b-instruct",  # for testing
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _STEP1_SYSTEM_PROMPT},
            {"role": "user", "content": cv_text},
        ],
    )
    return completion.choices[0].message.content or ""


def _call_step2(client: OpenAI, step1_text: str) -> CandidateProfile:
    """Map the reconstructed CV text to a structured CandidateProfile.

    Uses client.beta.chat.completions.parse so the SDK serialises the Pydantic
    schema to JSON Schema, enforces it on the model response, and deserialises
    the result back to a CandidateProfile instance automatically.

    :param client: Configured OpenAI client.
    :param step1_text: Reconstructed CV text produced by step 1.
    :return: Parsed CandidateProfile instance.
    :raises openai.OpenAIError: If the LLM request fails.
    """
    completion = client.beta.chat.completions.parse(
        # model=settings.llm_model,
        model="qwen/qwen-2.5-7b-instruct",  # for testing
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _STEP2_SYSTEM_PROMPT},
            {"role": "user", "content": step1_text},
        ],
        response_format=CandidateProfile,
    )
    return completion.choices[0].message.parsed


def extract_profile_from_cv_text(
    cv_text: str,
) -> tuple[CandidateProfile, str, str, str]:
    """Run the two-step CV extraction pipeline.

    Step 1 reconstructs the raw CV text as clean grouped plain text.
    Step 2 maps the reconstructed text to a CandidateProfile using structured
    output. Both calls reuse the same OpenAI client instance.

    :param cv_text: Raw extracted CV text (Markdown or plain text).
    :return: Tuple of (profile, step1_text, step1_version, step2_version).
    :raises openai.OpenAIError: If either LLM request fails.
    """
    client = _build_client()
    step1_text = _call_step1(client, cv_text)
    profile = _call_step2(client, step1_text)
    return profile, step1_text, STEP1_PROMPT_VERSION, STEP2_PROMPT_VERSION
