"""
Shared retry-with-backoff wrapper for Gemini API calls. Free-tier rate
limits (roughly 10-15 requests/minute) mean sequential calls — like the
~220 Shariah classifications during a full ingestion run — hit them under
normal use, not just edge cases. Retrying with backoff turns a hard
failure into "waits a bit, then succeeds" for the common case.

Detection is string-matching on the error message rather than a specific
exception type — this sandbox can't verify the exact exception class
google-genai raises for rate limits with certainty, and the SDK is young
enough that this could differ by version. Google's APIs consistently use
"RESOURCE_EXHAUSTED" or a 429 status for quota/rate-limit errors, so
matching on those substrings is more version-resilient than an isinstance
check would be.
"""
import logging
import time

logger = logging.getLogger(__name__)

RATE_LIMIT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "rate limit", "quota")


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc)
    return any(marker.lower() in text.lower() for marker in RATE_LIMIT_MARKERS)


def call_with_retry(fn, *args, max_retries: int = 3, base_delay: float = 10.0, **kwargs):
    """
    Calls fn(*args, **kwargs). On a rate-limit-looking error, waits with
    exponential backoff and retries. On any other error, or after
    exhausting retries, re-raises immediately — this is not a general
    "retry everything" wrapper, only for the specific rate-limit case.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — inspecting arbitrary SDK exceptions
            last_exc = e
            if not is_rate_limit_error(e) or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)
    raise last_exc  # pragma: no cover — unreachable, satisfies type checkers