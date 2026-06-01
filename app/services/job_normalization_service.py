"""Service functions for job advertisement normalisation.

Coordinate normalisation of raw job text into a structured
``JobNormalizationSchema`` via an OpenAI structured-output call and persist
the result. Eval output is appended to ``evals/job_normalizations.jsonl``
after each successful normalisation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.job_normalization import (
    create_job_normalization,
    get_normalization_by_job_id,
    get_normalization_by_manual_job_id,
)
from app.models.job import Job
from app.models.job_normalization import JobNormalization
from app.schemas.job_normalization import JobNormalizationSchema
from prompts.job_normalization import VERSIONS

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
_SYSTEM_PROMPT = VERSIONS[PROMPT_VERSION]

_EVALS_PATH = Path(__file__).resolve().parents[2] / "evals" / "job_normalizations.jsonl"


def _build_client() -> OpenAI:
    """Create a configured OpenAI client using the default OpenAI endpoint.

    :return: Configured OpenAI client instance.
    """
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
    )


def _append_eval(
    normalization: JobNormalizationSchema,
    *,
    job_id: int | None,
    manual_job_id: int | None,
    prompt_version: str,
    model: str,
) -> None:
    """Append one normalisation result to the evals JSONL file.

    :param normalization: The normalised job schema produced by the LLM.
    :param job_id: FK to the API-sourced Job, or ``None``.
    :param manual_job_id: FK to the ManualJobPosting, or ``None``.
    :param prompt_version: Active prompt version key.
    :param model: Model identifier used for the call.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "model": model,
        "job_id": job_id,
        "manual_job_posting_id": manual_job_id,
        "output": normalization.model_dump(),
    }
    try:
        _EVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _EVALS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("Could not write to evals file %s.", _EVALS_PATH)


def normalize_job(
    raw_text: str,
    existing_job: Job | None = None,
    *,
    job_id: int | None = None,
    manual_job_id: int | None = None,
) -> JobNormalizationSchema:
    """Return a structured normalisation of the given job advertisement text.

    Uses OpenAI structured output (``beta.chat.completions.parse``) to
    extract all ``JobNormalizationSchema`` fields from the raw ad text.

    When ``existing_job`` is provided it indicates the job came from the live
    job-search API. Its ``company``, ``location``, and ``employment_type``
    fields are forwarded to the LLM as optional hints so it can cross-check
    against the ad text; the LLM always prefers the ad text for title and
    variants.

    :param raw_text: Full text of the job advertisement.
    :param existing_job: Optional API-sourced Job record (live search only).
    :param job_id: FK to the API-sourced Job, used for eval logging.
    :param manual_job_id: FK to the ManualJobPosting, used for eval logging.
    :return: Normalised job schema instance.
    :raises openai.OpenAIError: If the LLM request fails.
    """
    client = _build_client()

    # Build the user message from the raw ad text, optionally adding hints.
    user_parts = ["Job advertisement text:\n", raw_text]
    if existing_job is not None:
        hints: list[str] = []
        if existing_job.company:
            hints.append(f"company: {existing_job.company}")
        if existing_job.location:
            hints.append(f"location: {existing_job.location}")
        if existing_job.employment_type:
            hints.append(f"employment_type: {existing_job.employment_type}")
        if hints:
            user_parts.append(
                "\n\nPre-populated hints from the job-search API "
                "(cross-check against the ad text; prefer the ad text where it differs, "
                "especially for company legal form; ignore for canonical_job_title and "
                "job_title_variants):\n" + "\n".join(hints)
            )

    user_message = "".join(user_parts)

    completion = client.beta.chat.completions.parse(
        model=settings.openai_model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format=JobNormalizationSchema,
    )
    result: JobNormalizationSchema = completion.choices[0].message.parsed

    _append_eval(
        result,
        job_id=job_id,
        manual_job_id=manual_job_id,
        prompt_version=PROMPT_VERSION,
        model=settings.openai_model,
    )

    return result


def get_or_create_normalization(
    db: Session,
    *,
    job_id: int | None,
    manual_job_posting_id: int | None,
    raw_text: str,
    existing_job: Job | None = None,
) -> JobNormalization:
    """Return the existing normalisation record or create a new one.

    Checks the database for an existing record keyed by the given job or
    manual posting ID before calling the normalisation service. This avoids
    redundant LLM calls when multiple cover letters are generated for the
    same job.

    :param db: Active database session.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :param raw_text: Full text of the job advertisement.
    :param existing_job: Optional API-sourced Job record for pre-population.
    :return: Existing or newly created JobNormalization record.
    """
    if job_id is not None:
        existing = get_normalization_by_job_id(db, job_id=job_id)
        if existing is not None:
            return existing

    if manual_job_posting_id is not None:
        existing = get_normalization_by_manual_job_id(
            db, manual_job_posting_id=manual_job_posting_id
        )
        if existing is not None:
            return existing

    schema = normalize_job(
        raw_text,
        existing_job=existing_job,
        job_id=job_id,
        manual_job_id=manual_job_posting_id,
    )

    return create_job_normalization(
        db,
        normalized_data=schema.model_dump(),
        llm_model=settings.openai_model,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
    )
