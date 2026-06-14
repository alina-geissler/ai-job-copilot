"""Langfuse client singleton and prompt-hash utility for LLM observability.

Import ``langfuse_client`` in LLM service modules to create traces and
generations.  The client is ``None`` when ``LANGFUSE_PUBLIC_KEY`` is not set,
in which case all ``if langfuse_client:`` guards in callers are no-ops and the
application functions normally without any tracing overhead.

Usage::

    from app.services.llm_tracing import langfuse_client, prompt_hash

    if langfuse_client:
        gen = langfuse_client.generation(name="...", model="...", input=messages)
    response = client.responses.create(...)
    if langfuse_client:
        gen.end(output=response.output_text,
                usage={"input": response.usage.input_tokens,
                       "output": response.usage.output_tokens})
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

try:
    from app.core.config import settings as _settings

    if _settings.langfuse_public_key and _settings.langfuse_secret_key:
        from langfuse import Langfuse

        langfuse_client: "Langfuse | None" = Langfuse(
            public_key=_settings.langfuse_public_key,
            secret_key=_settings.langfuse_secret_key,
            host=_settings.langfuse_host,
        )
        logger.info(
            "Langfuse tracing enabled.",
            extra={"host": _settings.langfuse_host},
        )
    else:
        langfuse_client = None
        logger.info("Langfuse tracing disabled (LANGFUSE_PUBLIC_KEY not set).")

except Exception as _exc:  # noqa: BLE001
    langfuse_client = None
    logger.warning("Langfuse initialisation failed — tracing disabled: %s", _exc)


def prompt_hash(text: str) -> str:
    """Return an 8-character SHA-256 prefix of a prompt string.

    Use as lightweight drift detection: if the prompt text changes without
    bumping the version constant, the hash will differ in Langfuse metadata.

    :param text: Prompt text to hash.
    :return: 8-character hexadecimal string.
    """
    return hashlib.sha256(text.encode()).hexdigest()[:8]
