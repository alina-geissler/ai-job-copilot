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
from app.services.llm_tracing import langfuse_client, prompt_hash
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


def _call_step1(client: OpenAI, cv_text: str) -> tuple[str, object]:
    """Reconstruct raw CV text as clean, grouped plain text.

    Sends the raw CV text to the LLM with a text-reconstruction prompt and
    returns the plain-text response and the raw completion usage object.

    :param client: Configured OpenAI client.
    :param cv_text: Raw extracted CV text (Markdown or plain text).
    :return: Tuple of (reconstructed text, completion usage).
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
    return completion.choices[0].message.content or "", completion.usage


def _call_step2(client: OpenAI, step1_text: str) -> tuple[CandidateProfile, object]:
    """Map the reconstructed CV text to a structured CandidateProfile.

    Uses client.beta.chat.completions.parse so the SDK serialises the Pydantic
    schema to JSON Schema, enforces it on the model response, and deserialises
    the result back to a CandidateProfile instance automatically.

    :param client: Configured OpenAI client.
    :param step1_text: Reconstructed CV text produced by step 1.
    :return: Tuple of (parsed CandidateProfile, completion usage).
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
    return completion.choices[0].message.parsed, completion.usage


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
    _model = "qwen/qwen-2.5-7b-instruct"

    _lf_trace = None
    if langfuse_client:
        _lf_trace = langfuse_client.trace(
            name="cv-profile-extraction",
            metadata={
                "step1_prompt_version": STEP1_PROMPT_VERSION,
                "step1_prompt_hash": prompt_hash(_STEP1_SYSTEM_PROMPT),
                "step2_prompt_version": STEP2_PROMPT_VERSION,
                "step2_prompt_hash": prompt_hash(_STEP2_SYSTEM_PROMPT),
            },
        )

    _lf_gen1 = None
    if _lf_trace is not None:
        _lf_gen1 = _lf_trace.generation(
            name="step1-reconstruct",
            model=_model,
            metadata={"prompt_version": STEP1_PROMPT_VERSION},
        )
    step1_text, step1_usage = _call_step1(client, cv_text)
    if _lf_gen1 is not None and step1_usage is not None:
        _lf_gen1.end(
            output=step1_text,
            usage={
                "input": step1_usage.prompt_tokens,
                "output": step1_usage.completion_tokens,
            },
        )

    _lf_gen2 = None
    if _lf_trace is not None:
        _lf_gen2 = _lf_trace.generation(
            name="step2-extract",
            model=_model,
            metadata={"prompt_version": STEP2_PROMPT_VERSION},
        )
    profile, step2_usage = _call_step2(client, step1_text)
    if _lf_gen2 is not None and step2_usage is not None:
        _lf_gen2.end(
            output=profile.model_dump_json() if profile is not None else None,
            usage={
                "input": step2_usage.prompt_tokens,
                "output": step2_usage.completion_tokens,
            },
        )

    return profile, step1_text, STEP1_PROMPT_VERSION, STEP2_PROMPT_VERSION
