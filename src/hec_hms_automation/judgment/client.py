"""
Thin, OPTIONAL wrapper around the TypeSafe SDK (``pip install typesafe-sdk``).

Contract: :func:`judge` returns a ``SystemOneResponse`` or ``None``.  ``None``
means "no opinion" (SDK not installed, ``TYPESAFE_API_KEY`` not set, or the
service failed) and callers MUST fall back to their deterministic behaviour.  So
the toolkit works identically -- just without the fuzzy-text help -- on a machine
with no key.

Key handling: the SDK reads ``TYPESAFE_API_KEY`` itself.  This module never
reads, prints, logs or stores the key, and never accepts ``api_key=``.
Keep ``TYPESAFE_LOG_LEVEL`` at its default: ``debug`` logs request bodies.
"""
from __future__ import annotations

import logging
import os
import threading

from .constants import JEV_MODEL

log = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()


def available() -> bool:
    """True when the SDK is importable and a key is present in the environment."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        return False
    try:
        import typesafe_sdk  # noqa: F401
    except ImportError:
        return False
    return True


def _get_client():
    """One reusable client for the whole process (SDK guidance: do not create per call)."""
    global _client
    with _client_lock:
        if _client is None:
            from typesafe_sdk import TypeSafeClient
            _client = TypeSafeClient(model=JEV_MODEL)
        return _client


def judge(state, questions: dict):
    """Ask Jev all ``questions`` about ``state`` in ONE request.

    ``questions`` maps your own ids to typesafe_sdk ``Noul`` / ``Choice`` /
    ``Score`` objects.  Returns the SDK response, or ``None`` for "no opinion".
    The answering model id is logged (``response.model``) for auditability.
    """
    if not available():
        return None
    try:
        resp = _get_client().system_one(state=state, questions=questions)
    except Exception as exc:  # TypeSafeError subclasses, network errors, ...
        # Never echo the exception body at INFO: it may contain request text.
        log.warning("Jev call failed (%s); continuing without judgment.", type(exc).__name__)
        return None
    log.info("Jev answered with model %s (%d input tokens)", resp.model, resp.usage.input_tokens)
    return resp
